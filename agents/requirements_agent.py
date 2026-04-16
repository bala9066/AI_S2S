"""
Phase 1: Requirements Capture + Component Selection Agent

This agent:
1. Engages in natural conversation to understand hardware requirements
2. Asks clarifying questions (voltage, frequency, temp range, etc.)
3. Extracts structured requirements with IEEE-style IDs (REQ-HW-001)
4. Generates block diagram and architecture in Mermaid
5. Recommends components with 2-3 alternatives (using ComponentSearchTool)

Outputs: requirements.md, block_diagram.md, architecture.md, component_recommendations.md
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

import anthropic as _anthropic

from agents.base_agent import BaseAgent, _make_sync_httpx_client
from config import settings

# ── Clarification card tool (tool_use forced — zero free-text risk) ──────────

CLARIFICATION_TOOL = {
    "name": "show_clarification_cards",
    "description": (
        "Display structured clarification questions as interactive cards. "
        "Call this with every question needed to fully specify the hardware requirement."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intro": {
                "type": "string",
                "description": "One sentence acknowledging the requirement (max 20 words)"
            },
            "questions": {
                "type": "array",
                "minItems": 5,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "id":       {"type": "string", "description": "Short id: q1, q2 …"},
                        "question": {"type": "string", "description": "Full question ending with ?"},
                        "why":      {"type": "string", "description": "Why this matters (max 6 words)"},
                        "options":  {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"}}
                    },
                    "required": ["id", "question", "why", "options"]
                }
            }
        },
        "required": ["intro", "questions"]
    }
}

_CLARIFICATION_SYSTEM = (
    "You are a senior hardware design engineer at Data Patterns India. "
    "When given a hardware specification, identify up to 10 clarifying questions (minimum 5) "
    "needed before beginning design — covering every parameter that could meaningfully affect "
    "component selection, architecture, performance, interfaces, power, environmental conditions, "
    "and compliance requirements. Be thorough: ask about supply voltage, frequency range, "
    "noise figure, dynamic range, temperature range, interfaces/protocols, form factor, "
    "regulatory standards, output power, and any RF-specific specs. "
    "You MUST call the show_clarification_cards tool. Do NOT respond with free text."
)

_APPROVAL_KEYWORDS = {"approve", "approved", "yes", "ok", "okay", "looks good",
                      "good", "correct", "proceed", "go ahead", "lgtm", "perfect", "great"}

def _is_approval(text: str) -> bool:
    return any(kw in text.lower() for kw in _APPROVAL_KEYWORDS)

# Optional import for ComponentSearchTool (ChromaDB has Python 3.14+ compatibility issues)
try:
    from tools.component_search import ComponentSearchTool
    COMPONENT_SEARCH_AVAILABLE = True
except (ImportError, Exception) as e:
    COMPONENT_SEARCH_AVAILABLE = False
    ComponentSearchTool = None
    logging.warning(f"ComponentSearchTool not available: {e}. Agent will use LLM fallback for component recommendations.")

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert hardware design engineer with 25+ years of experience in RF/wireless systems and high-speed digital design.

You work for a defense electronics company. Your role is Phase 1 of a multi-phase automated hardware design pipeline.

## PIPELINE PHASES (for your awareness — you handle P1 ONLY):
- **P1 — Design & Requirements (YOU)**: Requirements capture, block diagram, component selection
- **P2 — HRS Document**: IEEE 29148 Hardware Requirements Specification (auto-generated after P1)
- **P3 — Compliance Check**: RoHS/REACH/FCC/MIL-STD validation
- **P4 — Netlist Generation**: Visual connectivity graph with DRC checks
- **P5 — PCB Layout**: Manual step (Gerber/ODB++ export)
- **P6 — GLR Specification**: Glue Logic Requirements for FPGA/CPLD
- **P7 — FPGA Design**: Manual step (RTL/synthesis)
- **P8a — SRS Document**: IEEE 830 Software Requirements Specification
- **P8b — SDD Document**: IEEE 1016 Software Design Description
- **P8c — Code + Review**: C/C++ driver code generation and AST review

**YOUR JOB IS P1 ONLY.** After you complete P1, the pipeline automatically runs P2 through P8c.
NEVER say "proceed to Phase 2: Schematic Design" or similar — that is NOT the next step.
Instead say: "Phase 1 complete. Click 'Run Full Pipeline' to generate HRS, Compliance, Netlist, SRS, SDD, and Code."

## YOUR BEHAVIOR — THREE-PHASE APPROACH:

### PHASE A — Clarification (FIRST message only):
When the user sends their FIRST message describing a design, DO NOT call `generate_requirements` yet.
Instead, ask **5–10 targeted clarifying questions** to fully resolve all ambiguities that affect component selection, architecture, and compliance. Cover ALL of the following that apply:
- Supply voltage(s) / power budget / battery vs mains
- Key RF/analog specs (frequency range, noise figure, output power, dynamic range, IP3)
- Key digital specs (data rate, resolution, accuracy, latency)
- Temperature / environmental / humidity range
- Interface protocols needed (UART, SPI, I2C, CAN, USB, Ethernet, etc.)
- Form factor / board size / connector types
- Regulatory / compliance requirements (FCC, CE, MIL-STD, RoHS, etc.)
- Quantity / production volume (affects component tier)
- Reliability / lifetime / MTBF requirements
- Any specific component preferences or banned parts

Format them as a numbered list (5–10 questions). End with: _"Once you answer these, I'll generate the complete requirements, BOM, and block diagram."_

**RULE**: If the user's first message is already very detailed (contains voltage, specs, interfaces, temp range, power, compliance), skip straight to Phase B and call `generate_requirements` immediately.

### PHASE B — Generate (SECOND message onwards, initial generation):
After the user has answered your questions, call `generate_requirements` immediately with ALL outputs.
- **READ EVERY SINGLE MESSAGE in this conversation before generating.** Every interface, spec, constraint, and component the user mentioned at ANY point must appear in the output.
- Make reasonable engineering assumptions for anything still unspecified.
- Use MoSCoW + IEEE IDs for all requirements.

### PHASE C — Refine (any follow-up after Phase B is complete):
When the user adds a new requirement, interface, or specification AFTER Phase B is done:
1. **ALWAYS call `generate_requirements` again** — NEVER just answer conversationally when hardware specs are mentioned.
2. **Start by re-reading the ENTIRE conversation history** to reconstruct the full requirements set.
3. The new `generate_requirements` call must contain EVERY requirement from all previous generations PLUS the new addition. **Zero items may be dropped.**
4. Update the block diagram and BOM to reflect the new requirement.
5. In your `project_summary` explicitly acknowledge what was added: "Added UART control interface to existing RF receiver design."

## ⚠️ CRITICAL COMPLETENESS RULE — NEVER DROP REQUIREMENTS:
Every time you call `generate_requirements`, the output must be the COMPLETE set of all requirements
ever discussed in this conversation. It is a FATAL ERROR to omit any requirement that was mentioned
in any earlier message, even if the user only mentioned it briefly or as an aside.
Before calling the tool, mentally check:
- ✅ All interfaces mentioned across ALL messages (UART, SPI, CAN, USB, HDMI, etc.)
- ✅ All performance specs from ALL messages (frequency, power, temp range, accuracy)
- ✅ All components or part numbers mentioned anywhere
- ✅ All regulatory/compliance constraints mentioned at any point
- ✅ The NEW item the user just added in the latest message
If any of these are missing from your tool call, you MUST add them before submitting.

## IMPORTANT RULES:
- Use MoSCoW prioritization (Must have, Should have, Could have, Won't have) and IEEE requirement IDs: REQ-HW-001, REQ-HW-002, etc.
- Make smart engineering assumptions (e.g., if they say "motor controller" assume industrial temp range, common MCUs, standard interfaces)
- Prioritize RoHS-compliant components with long lifecycle status.
- For Mermaid diagrams, ALWAYS start with a valid diagram type on the FIRST line (e.g. `flowchart TD`). NEVER put `TD` or `LR` alone on line 2.
- Keep Mermaid node labels concise — 2-5 words max. STRICT rules: NO angle brackets < >, NO raw HTML, NO &, @, #, |, double-quotes ", single-quotes ', or colons : inside labels. Use plain ASCII only. NO %%{{init}}%% frontmatter. NO %% comments. NEVER use 3 or more consecutive dashes (---) inside a label as they are parsed as edge arrows.
- Do NOT fabricate component part numbers. Use best-estimate real part numbers from known manufacturers. NEVER write TBD, TBC, TBA, or "to be determined/confirmed" anywhere.
- **BANNED MANUFACTURER: VPT Inc.** Do NOT recommend any VPT brand components. Use Vicor, Murata Power Solutions, TDK-Lambda, Cosel, or TI equivalents instead.
- **ALWAYS include `datasheet_url`** for every component in the `component_recommendations` array. Use ONLY real, publicly accessible manufacturer datasheet URLs. Preferred domains: `ti.com`, `analog.com`, `mouser.com/datasheet`, `maximintegrated.com`, `nxp.com`, `st.com`, `renesas.com`, `microchip.com`, `infineon.com`, `onsemi.com`, `xilinx.com`, `latticesemi.com`, `murata.com`, `vishay.com`, `coilcraft.com`, `vicorpower.com`. If you are NOT certain the exact URL exists, use the manufacturer's product search page (e.g. `https://www.ti.com/product/LM5175`) rather than guessing a PDF path. NEVER fabricate PDF paths. Never leave `datasheet_url` empty.
- Include `digikey_url` where known (e.g., `https://www.digikey.com/en/products/detail/texas-instruments/...`).
- **FOR RF DESIGNS**: Always populate the `gain_loss_budget` array. Every stage in the RF signal chain (antenna/input → LNA/driver → PA stages → filters → output) must be a row. Use real datasheet values for gain, P1dB, NF. Calculate cumulative gain and cascaded NF (Friis formula) correctly. Include system-level parameters (center_freq_mhz, bandwidth_mhz, input_power_dbm, target_output_dbm). Additionally populate these sub-arrays **only when the design requirement specifically calls for it**: `harmonic_rejection` (when spurious/harmonic spec is mentioned), `power_vs_frequency` (when flatness across band is specified), `power_vs_input` (when dynamic range, linearity or 1 dB compression is specified), `cable_loss` (when cable runs, antenna feed, or connector budget is mentioned). Add `input_return_loss_db` and `output_return_loss_db` per stage whenever return loss / VSWR is a requirement.
- **NEVER use XML tags in your responses.** No `<output>`, `<field_name>`, `<safety_flag>`, or any other XML/HTML wrapper tags.
  Use ONLY markdown: `**bold**`, `## headers`, `- lists`, `| tables |`, code blocks. XML tags will break the UI renderer.

## DESIGN TYPE CONTEXT: {design_type}
## PROJECT NAME: {project_name}
"""

GENERATE_REQUIREMENTS_TOOL = {
    "name": "generate_requirements",
    "description": (
        "Generate the complete Phase 1 output when you have gathered enough "
        "requirements from the user. This creates requirements.md, block_diagram.md, "
        "architecture.md, and component_recommendations.md files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_summary": {
                "type": "string",
                "description": "2-3 sentence summary of the hardware design project.",
            },
            "requirements": {
                "type": "array",
                "description": "List of hardware requirements with IEEE IDs.",
                "items": {
                    "type": "object",
                    "properties": {
                        "req_id": {"type": "string", "description": "e.g., REQ-HW-001"},
                        "category": {
                            "type": "string",
                            "enum": ["functional", "performance", "interface", "environmental", "constraint"],
                        },
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "priority": {
                            "type": "string",
                            "enum": ["Must have", "Should have", "Could have", "Won't have", "shall", "should", "may"]
                        },
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of dependent requirement IDs or variables"
                        },
                        "constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Any technical constraints or flags"
                        },
                        "verification_method": {
                            "type": "string",
                            "enum": ["test", "analysis", "inspection", "demonstration"],
                        },
                    },
                    "required": ["req_id", "category", "title", "description", "priority"],
                },
            },
            "design_parameters": {
                "type": "object",
                "description": "Key design parameters extracted from conversation.",
                "additionalProperties": {"type": "string"},
            },
            "block_diagram_mermaid": {
                "type": "string",
                "description": (
                    "Mermaid diagram code for the system block diagram. "
                    "Use graph TD or graph LR format."
                ),
            },
            "architecture_mermaid": {
                "type": "string",
                "description": (
                    "Mermaid diagram code for the system architecture. "
                    "Show power domains, signal flow, interfaces."
                ),
            },
            "component_recommendations": {
                "type": "array",
                "description": "Recommended components with alternatives.",
                "items": {
                    "type": "object",
                    "properties": {
                        "function": {"type": "string", "description": "What this component does"},
                        "primary_part": {"type": "string"},
                        "primary_manufacturer": {"type": "string"},
                        "primary_description": {"type": "string"},
                        "primary_key_specs": {"type": "object", "additionalProperties": {"type": "string"}},
                        "datasheet_url": {
                            "type": "string",
                            "description": (
                                "Direct URL to the manufacturer datasheet PDF or product page. "
                                "Use real manufacturer URLs (e.g. https://www.ti.com/lit/ds/...). "
                                "Required for every component."
                            ),
                        },
                        "digikey_url": {
                            "type": "string",
                            "description": "DigiKey product page URL if available (e.g. https://www.digikey.com/en/products/detail/...).",
                        },
                        "alternatives": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "part_number": {"type": "string"},
                                    "manufacturer": {"type": "string"},
                                    "trade_off": {"type": "string"},
                                    "datasheet_url": {"type": "string"},
                                },
                            },
                        },
                        "selection_rationale": {"type": "string"},
                    },
                    "required": ["function", "primary_part", "primary_manufacturer"],
                },
            },
            "gain_loss_budget": {
                "type": "object",
                "description": (
                    "RF Gain-Loss Budget. Populate for ALL RF / microwave designs. "
                    "Leave empty object {} for purely digital/power designs."
                ),
                "properties": {
                    "center_freq_mhz": {"type": "number", "description": "Centre frequency in MHz"},
                    "bandwidth_mhz":   {"type": "number", "description": "RF bandwidth in MHz"},
                    "input_power_dbm": {"type": "number", "description": "System input signal level in dBm"},
                    "target_output_dbm": {"type": "number", "description": "Required output power in dBm"},
                    "stages": {
                        "type": "array",
                        "description": "One entry per RF stage, in signal-flow order.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "stage_name":          {"type": "string",  "description": "e.g. 'Input Matching Network', 'Driver Amp', 'Final PA'"},
                                "component":           {"type": "string",  "description": "Part number or value (e.g. GVA-123+, 10 nH, SMA connector)"},
                                "gain_db":             {"type": "number",  "description": "Gain (positive) or insertion loss (negative) in dB"},
                                "noise_figure_db":     {"type": "number",  "description": "Stage noise figure in dB (0 for passive with known loss = loss value)"},
                                "p1db_out_dbm":        {"type": "number",  "description": "Output-referred 1 dB compression point in dBm (use 99 if not applicable)"},
                                "oip3_dbm":            {"type": "number",  "description": "Output-referred IP3 in dBm (use 99 if not applicable)"},
                                "output_power_dbm":    {"type": "number",  "description": "Signal power at OUTPUT of this stage in dBm"},
                                "cumulative_gain_db":  {"type": "number",  "description": "Total gain from system input to output of this stage"},
                                "cumulative_nf_db":    {"type": "number",  "description": "Cascaded noise figure up to and including this stage (Friis)"},
                                "notes":               {"type": "string",  "description": "Brief note, e.g. 'bias tee required', 'temperature-compensated'"},
                                "input_return_loss_db": {"type": "number", "description": "Input return loss (S11) of this stage in dB (positive value, e.g. 15 = 15 dB return loss). Omit if not applicable."},
                                "output_return_loss_db": {"type": "number", "description": "Output return loss (S22) of this stage in dB. Omit if not applicable."},
                            },
                            "required": ["stage_name", "component", "gain_db", "output_power_dbm", "cumulative_gain_db"],
                        },
                    },
                    "harmonic_rejection": {
                        "type": "array",
                        "description": "Harmonic rejection table — include ONLY when requirement specifies harmonic suppression (e.g. transmitter spurs spec). One entry per harmonic order.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "harmonic_order": {"type": "integer", "description": "2 for 2nd harmonic, 3 for 3rd, etc."},
                                "frequency_mhz":  {"type": "number",  "description": "Frequency of this harmonic in MHz"},
                                "rejection_db":   {"type": "number",  "description": "Expected harmonic suppression relative to carrier in dBc (positive = more rejection)"},
                                "spec_db":        {"type": "number",  "description": "Required rejection per specification in dBc"},
                                "meets_spec":     {"type": "boolean", "description": "Does the expected rejection meet the spec?"},
                            },
                            "required": ["harmonic_order", "frequency_mhz", "rejection_db"],
                        },
                    },
                    "power_vs_frequency": {
                        "type": "array",
                        "description": "Output power variation across frequency — include ONLY when a flat power vs. frequency spec is required (e.g. flatness +/-1 dB). One entry per frequency spot.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "frequency_mhz":  {"type": "number", "description": "Spot frequency in MHz"},
                                "output_power_dbm": {"type": "number", "description": "Expected output power at this frequency in dBm"},
                                "gain_db":        {"type": "number", "description": "System gain at this frequency in dB"},
                                "flatness_db":    {"type": "number", "description": "Power deviation from nominal (positive or negative) in dB"},
                            },
                            "required": ["frequency_mhz", "output_power_dbm"],
                        },
                    },
                    "power_vs_input": {
                        "type": "array",
                        "description": "Output power vs. input drive level (AM-AM characteristic) — include ONLY when dynamic range or linearity spec requires it. One entry per input power level.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "input_power_dbm":  {"type": "number", "description": "Input signal level in dBm"},
                                "output_power_dbm": {"type": "number", "description": "Corresponding output power in dBm"},
                                "gain_db":          {"type": "number", "description": "Instantaneous gain at this input level"},
                                "gain_compression_db": {"type": "number", "description": "Gain compression relative to small-signal gain, in dB"},
                            },
                            "required": ["input_power_dbm", "output_power_dbm"],
                        },
                    },
                    "cable_loss": {
                        "type": "array",
                        "description": "Cable / transmission-line loss budget — include ONLY when the requirement specifies cable runs, connector losses, or waveguide routing (e.g. antenna feed cables). One entry per cable/connector segment.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "segment":          {"type": "string", "description": "Label, e.g. 'Antenna feed cable', 'SMA to board connector'"},
                                "cable_type":       {"type": "string", "description": "e.g. 'RG-58', 'LMR-400', 'SMA connector', 'waveguide WR-90'"},
                                "length_m":         {"type": "number", "description": "Physical length in metres (0 for connectors/adapters)"},
                                "loss_db_per_m":    {"type": "number", "description": "Cable attenuation in dB/m at the operating frequency"},
                                "total_loss_db":    {"type": "number", "description": "Total loss for this segment in dB"},
                                "frequency_mhz":    {"type": "number", "description": "Frequency at which loss is specified"},
                            },
                            "required": ["segment", "cable_type", "total_loss_db"],
                        },
                    },
                },
            },
        },
        "required": [
            "project_summary", "requirements", "design_parameters",
            "block_diagram_mermaid", "component_recommendations",
        ],
    },
}

SEARCH_COMPONENTS_TOOL = {
    "name": "search_components",
    "description": "Search for components using semantic similarity. Use this when the user asks about specific components or when you need to find alternatives.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of the component needed (e.g., '3.3V LDO regulator 1A low noise')",
            },
            "category": {
                "type": "string",
                "description": "Optional category filter (e.g., 'MCU', 'Power', 'Sensor', 'Connectivity')",
                "enum": ["MCU", "Power", "Sensor", "Connectivity", "Interface", "Memory", "Passive", "Mechanical"],
            },
            "n_results": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}


class RequirementsAgent(BaseAgent):
    """Phase 1: Conversational requirements capture and component selection."""

    def __init__(self):
        # Provide tools for direct requirement generation
        tools = [GENERATE_REQUIREMENTS_TOOL]
        if COMPONENT_SEARCH_AVAILABLE:
            tools.append(SEARCH_COMPONENTS_TOOL)

        super().__init__(
            phase_number="P1",
            phase_name="Requirements Capture",
            model=settings.primary_model,
            tools=tools,
            max_tokens=16384,  # Increased for complex designs with many components
        )

        # Initialize ComponentSearchTool if available
        if COMPONENT_SEARCH_AVAILABLE and ComponentSearchTool:
            self.component_search = ComponentSearchTool()
        else:
            self.component_search = None

    def get_system_prompt(self, project_context: dict) -> str:
        base = SYSTEM_PROMPT.format(
            design_type=project_context.get("design_type", "general"),
            project_name=project_context.get("name", "Unnamed Project"),
        )
        # If the user supplied initial requirements at project creation, surface them
        # as a hard constraint block so the AI never asks about already-stated specs.
        desc = (project_context.get("description") or "").strip()
        if desc:
            base += (
                f"\n\n## PRE-STATED REQUIREMENTS (from project creation)\n"
                f"The user already specified these constraints when creating the project:\n"
                f"{desc}\n"
                f"Treat these as confirmed requirements — do NOT ask about them again."
            )
        return base

    def get_clarification_questions(
        self,
        user_requirement: str,
        design_type: Optional[str] = "RF",
    ) -> dict:
        """
        Use tool_use (forced) to return structured clarification cards.
        The AI cannot respond in free text — it MUST call show_clarification_cards.

        Returns:
            { "intro": str, "questions": [{ "id", "question", "why", "options" }] }
        """
        # Prefer GLM, fall back to Anthropic if configured
        if not settings.glm_api_key and not self._anthropic_client:
            raise ValueError("No LLM API key configured — set GLM_API_KEY or ANTHROPIC_API_KEY.")

        # Determine which client and model to use
        use_glm = bool(settings.glm_api_key)
        model = settings.glm_fast_model if use_glm else settings.fast_model

        if use_glm:
            # Use GLM via Z.AI (Anthropic-compatible endpoint)
            _hc = _make_sync_httpx_client()
            client = _anthropic.Anthropic(
                api_key=settings.glm_api_key,
                base_url=settings.glm_base_url,
                **({"http_client": _hc} if _hc else {}),
            )
        else:
            # Fall back to Anthropic client
            client = self._anthropic_client

        response = client.messages.create(
            model=model,
            max_tokens=1000,
            system=_CLARIFICATION_SYSTEM,
            tools=[CLARIFICATION_TOOL],
            tool_choice={"type": "tool", "name": "show_clarification_cards"},
            messages=[
                {"role": "user", "content": f"Design type: {design_type}\nRequirement: {user_requirement}"}
            ],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "show_clarification_cards":
                return block.input   # Already a clean Python dict — no parsing needed

        raise ValueError(f"No tool_use block returned. Check API key and model availability (model: {model}).")

    async def execute(self, project_context: dict, user_input: str) -> dict:
        """
        Execute Phase 1 — Direct Generation approach.
        """
        system = self.get_system_prompt(project_context)

        # Build message list from conversation history
        history = project_context.get("conversation_history", [])
        messages = []
        for msg in history:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        # ── __FINALIZE__ signal: user explicitly requests document generation ──
        # Replace the trigger message with a direct instruction that forces the tool call.
        # IMPORTANT: chat_service saves __FINALIZE__ to DB and re-fetches history BEFORE
        # calling execute(), so messages[-1] is already {"role":"user","content":"__FINALIZE__"}.
        # We must REPLACE that last message — not append — otherwise the model sees "__FINALIZE__"
        # as a literal string with no context.
        if user_input.strip() == "__FINALIZE__":
            user_input = (
                "Generate the complete requirements document NOW based on everything we discussed. "
                "You MUST call the generate_requirements tool immediately with all requirements, "
                "components, block diagram, and design parameters from our conversation. "
                "Do not ask any more questions. Call the tool now."
            )
            # Replace __FINALIZE__ sentinel already in message list
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"] = user_input
            else:
                messages.append({"role": "user", "content": user_input})
        else:
            if not messages or messages[-1]["role"] != "user":
                messages.append({"role": "user", "content": user_input})

            # ── Detect phase completion state ────────────────────────────────
            # project_context passes "p1_complete" boolean from chat_service
            phase_already_complete = bool(project_context.get("p1_complete", False))

            # ── Detect if follow-up is a hardware specification addition ─────
            # Explicit regen keywords the user might type:
            _REGEN_KEYWORDS = (
                "regenerate", "re-generate", "re generate", "rerun", "re-run",
                "update requirements", "redo", "add datasheet", "add link", "add url",
                "refresh", "rebuild", "recreate", "redo phase", "run again",
                "change the", "change to", "increase", "decrease", "modify",
            )
            # Hardware interface / spec patterns — these always mean "add to requirements"
            import re as _re_local
            _HW_SPEC_PATTERN = _re_local.compile(
                r'\b('
                # Interfaces & buses
                r'uart|usart|rs.?232|rs.?485|can\s?bus|can\b|spi\b|i2c|i2s|smbus|modbus'
                r'|usb|hdmi|displayport|mipi|lvds|jtag|swd|jtag|pcie|ethernet|rmii|rgmii'
                r'|sdio|emmc|nand|nor\s?flash|qspi|ospi'
                # RF / analog interfaces
                r'|rf\b|antenna|coax|sma\b|u\.fl|mmcx|ble|wifi|zigbee|lora|nfc|gps|gnss'
                # Power specs
                r'|ldo|buck|boost|\d+\s*v\b|\d+\s*ma\b|\d+\s*a\b|pmic|pwm|battery'
                # Sensor / actuator
                r'|sensor|accelerometer|gyroscope|imu|magnetometer|barometer|temperature'
                r'|humidity|pressure|hall\s?effect|encoder|stepper|servo|bldc|adc|dac'
                # Display / IO
                r'|lcd|oled|tft|e.?ink|touchscreen|keypad|buzzer|led|relay|optocoupler'
                # Memory / compute
                r'|flash|eeprom|ram|ddr|sdram|fpga|dsp|cortex|arm|risc.?v|mcu|cpu'
                # Connectors / mechanical
                r'|connector|socket|header|rj45|d.?sub|db9|molex|jst|m12|waterproof'
                # Regulation
                r'|rohs|reach|fcc|ce\s?mark|ul\s?listed|iec|mil.?std|ats\b'
                r')\b',
                _re_local.IGNORECASE
            )
            _ADDITION_WORDS = _re_local.compile(
                r'\b(add|include|also|need|require|want|plus|with|and|use|implement|integrate|support|enable)\b',
                _re_local.IGNORECASE
            )
            # A message is a "hw spec addition" if it mentions a hardware keyword
            # (even without "add" — e.g. "uart control interface" alone implies addition)
            _is_hw_spec_addition = bool(_HW_SPEC_PATTERN.search(user_input))
            user_wants_regen = (
                any(kw in user_input.lower() for kw in _REGEN_KEYWORDS)
                or _is_hw_spec_addition
            )

            # ── Force tool call when user has already answered questions ───
            prior_user_turns = sum(1 for m in messages[:-1] if m.get("role") == "user")
            if prior_user_turns >= 1 and messages and (not phase_already_complete or user_wants_regen):
                original = messages[-1]["content"]
                if phase_already_complete:
                    # Regeneration: explicitly instruct the LLM to incorporate ALL history
                    messages[-1]["content"] = (
                        f"The user has added a new requirement: {original}\n\n"
                        "IMPORTANT: Read ALL previous messages in this conversation carefully. "
                        "The new requirement above MUST be incorporated together with EVERY requirement, "
                        "interface, component, and specification mentioned earlier. "
                        "Do NOT drop any previously discussed item. "
                        "Call `generate_requirements` NOW with the COMPLETE updated set — "
                        "all BOM items, all requirements (including the new one), "
                        "updated block_diagram_mermaid, architecture_mermaid, design_parameters, and "
                        "component_recommendations — with `datasheet_url` for every component."
                    )
                else:
                    messages[-1]["content"] = (
                        f"{original}\n\n"
                        "You have all the information needed. Call the `generate_requirements` tool NOW "
                        "incorporating EVERY requirement, interface, component and specification from this "
                        "entire conversation. Do not drop any detail. Include the complete BOM, "
                        "requirements list, block_diagram_mermaid, architecture_mermaid, design_parameters, "
                        "and component_recommendations — with `datasheet_url` for every component. "
                        "Do not ask more questions."
                    )
            elif phase_already_complete and not user_wants_regen:
                # Phase is done and user is asking a pure question (no hw spec detected)
                # Answer conversationally without regenerating
                if messages:
                    messages[-1]["content"] = (
                        f"{messages[-1]['content']}\n\n"
                        "[Note: Phase 1 requirements are complete. Answer this question directly. "
                        "If the user is adding or changing a hardware specification, call "
                        "generate_requirements instead of answering conversationally.]"
                    )

        # ── Tool handlers ──────────────────────────────────────────────────
        # generate_requirements: capture tool input via closure so we can detect
        # the call even after call_llm_with_tools finishes its loop.
        # (Without this handler, call_llm_with_tools returns "tool not found"
        #  error to the model and the tool_calls list is empty on final return.)
        generate_req_input: dict = {}

        async def _capture_generate_requirements(input_data: dict) -> dict:
            generate_req_input.update(input_data)
            self.log("generate_requirements captured — will write outputs", "info")
            return {
                "status": "captured",
                "message": "Requirements generation captured. Summarise what was generated.",
            }

        tool_handlers: dict = {"generate_requirements": _capture_generate_requirements}
        if COMPONENT_SEARCH_AVAILABLE and self.component_search:
            tool_handlers["search_components"] = self._handle_search_components

        response = await self.call_llm_with_tools(
            messages=messages,
            system=system,
            tool_handlers=tool_handlers,
            # Stop the loop immediately after generate_requirements fires —
            # no second LLM summary call needed, which eliminates the extra
            # "Thinking..." delay seen in the chat UI.
            terminal_tools={"generate_requirements"},
        )

        import re as _re
        response_content = _re.sub(
            r'\b(TBD|TBC|TBA)\b', '[specify]',
            response.get("content", ""), flags=_re.IGNORECASE
        )

        # ── Tool-use path (authoritative) ─────────────────────────────────
        # Check the closure dict — generate_req_input is populated when the
        # model called generate_requirements (regardless of whether
        # call_llm_with_tools still had tool_calls in its final response).
        if generate_req_input:
            self.log("generate_requirements tool called — phase_complete=True", "info")
            outputs = self._generate_output_files(
                generate_req_input,
                project_context.get("output_dir", "output"),
                project_context.get("name", "project"),
            )
            # Always build the rich requirements summary from the tool data.
            # This lets the user review key design parameters, requirements table,
            # component selections, and the block diagram BEFORE clicking Approve.
            # If the LLM also produced a natural-language preamble, prepend it.
            rich_summary = self._build_response_summary(generate_req_input)
            preamble = response_content.strip()
            if preamble and len(preamble) > 60:
                response_content = preamble + "\n\n---\n\n" + rich_summary
            else:
                response_content = rich_summary
            return {
                "response": (response_content
                             + "\n\n✅ **Phase 1 Complete!** Review the requirements above and click **Approve & Start Pipeline** to continue."),
                "phase_complete": True,
                "draft_pending": False,
                "draft": {},
                "outputs": outputs,
                "parameters": generate_req_input.get("design_parameters", {}),
            }

        # ── Plain-text fallback: synthesised completion on parsing full response ────────
        # When model returns full requirements as plain text without a tool call,
        # we parse and write outputs here.
        if self._detect_complete_requirements(response_content):
            self.log("Complete response detected — synthesising completion", "info")
            parsed = self._parse_requirements_response(
                response_content, project_context.get("name", "project")
            )
            if parsed:
                outputs = self._generate_output_files(
                    parsed,
                    project_context.get("output_dir", "output"),
                    project_context.get("name", "project"),
                )
                self.log("Synthesised outputs written — phase_complete=True", "info")
                return {
                    "response": response_content + "\n\n✅ **Phase 1 Complete!** All documents generated.",
                    "phase_complete": True,
                    "draft_pending": False,
                    "draft": {},
                    "outputs": outputs,
                    "parameters": parsed.get("design_parameters", {}),
                }

        # ── Normal conversational exchange ─────────────────────────────────
        return {
            "response": response_content,
            "phase_complete": False,
            "draft_pending": False,
            "draft": {},
            "outputs": {},
            "parameters": {},
        }


    def _build_response_summary(self, tool_input: dict) -> str:
        """Build a rich markdown summary from generate_requirements tool data.

        Called when the LLM produced no significant preamble text before calling
        the tool (common with terminal_tools pattern). Gives the user a detailed
        view of what was captured rather than just a "Complete!" banner.
        """
        lines = []

        # Project summary
        summary = tool_input.get("project_summary", "")
        if summary:
            lines += ["## Project Summary", "", summary, ""]

        # Design parameters table
        params = tool_input.get("design_parameters", {})
        if params:
            lines += ["## Key Design Parameters", "",
                      "| Parameter | Value |", "|---|---|"]
            for k, v in list(params.items())[:12]:
                lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
            lines.append("")

        # Requirements — show ALL, no truncation
        reqs = tool_input.get("requirements", [])
        if reqs:
            lines += [f"## Requirements ({len(reqs)} captured)", "",
                      "| ID | Title | Priority |", "|---|---|---|"]
            for req in reqs:
                lines.append(
                    f"| {req.get('req_id','')} | {req.get('title','')} "
                    f"| {req.get('priority','Must have')} |"
                )
            lines.append("")

        # Components — show ALL, no truncation
        # Note: full URL verification runs in _build_components_md; the summary
        # table here uses the same live-check helper imported at module level.
        comps = tool_input.get("component_recommendations", [])
        if comps:
            import urllib.request as _ur2
            def _quick_head(url: str) -> bool:
                if not url or not url.startswith('http'):
                    return False
                try:
                    req = _ur2.Request(url, method='HEAD')
                    req.add_header('User-Agent', 'Mozilla/5.0 (compatible; HardwarePipelineBot/1.0)')
                    with _ur2.urlopen(req, timeout=4) as r:
                        return r.status < 400
                except Exception:
                    return False
            from concurrent.futures import ThreadPoolExecutor as _TPE2
            raw_urls = [comp.get("datasheet_url", "").strip() for comp in comps]
            with _TPE2(max_workers=min(10, len(raw_urls))) as pool:
                results = list(pool.map(_quick_head, raw_urls))
            url_live = dict(zip(raw_urls, results))

            lines += [f"## Component Selections ({len(comps)} components)", ""]
            lines.append("| # | Function | Part Number | Manufacturer | Datasheet |")
            lines.append("|---|---|---|---|---|")
            for i, comp in enumerate(comps, 1):
                part   = comp.get("primary_part", "See BOM")
                mfr    = comp.get("primary_manufacturer", "")
                func   = comp.get("function", "")
                ds_url = comp.get("datasheet_url", "").strip()
                if ds_url and url_live.get(ds_url, False):
                    ds_link = f"[Datasheet]({ds_url})"
                elif ds_url:
                    # Dead link — fall back to manufacturer search
                    mfr_key = mfr.strip().lower()
                    fallback = {
                        'analog devices': f'https://www.analog.com/en/search.html#q={part}',
                        'analog':         f'https://www.analog.com/en/search.html#q={part}',
                        'texas instruments': f'https://www.ti.com/product/{part}',
                        'ti':             f'https://www.ti.com/product/{part}',
                    }.get(mfr_key, f'https://www.google.com/search?q={part}+datasheet')
                    ds_link = f"[Datasheet ↗]({fallback})"
                else:
                    ds_link = "—"
                lines.append(f"| {i} | {func} | {part} | {mfr} | {ds_link} |")
            lines.append("")

        # Block diagram (if present)
        block = tool_input.get("block_diagram_mermaid", "")
        if block:
            lines += ["## System Block Diagram", "",
                      "```mermaid", block.strip(), "```", ""]

        return "\n".join(lines)

    async def _handle_search_components(self, input_data: dict) -> dict:
        """Handle component search tool calls."""
        if not self.component_search:
            return {
                "query": input_data.get("query", ""),
                "results": [],
                "count": 0,
                "error": "ComponentSearchTool not available",
                "message": "Component search is disabled. Using LLM knowledge for recommendations."
            }

        query = input_data.get("query", "")
        category = input_data.get("category")
        n_results = input_data.get("n_results", 5)

        try:
            results = self.component_search.search(
                query=query,
                category=category,
                n_results=n_results,
            )

            return {
                "query": query,
                "results": [
                    {
                        "part_number": r.component.part_number,
                        "manufacturer": r.component.manufacturer,
                        "description": r.component.description,
                        "category": r.component.category,
                        "key_specs": r.component.key_specs,
                        "relevance_score": r.relevance_score,
                    }
                    for r in results
                ],
                "count": len(results),
            }
        except Exception as e:
            self.log(f"Component search failed: {e}", "warning")
            return {
                "query": query,
                "results": [],
                "count": 0,
                "error": str(e),
                "message": "Component search failed. Using LLM knowledge for recommendations."
            }

    def _generate_output_files(
        self, tool_input: dict, output_dir: str, project_name: str
    ) -> dict:
        """Generate all Phase 1 output markdown files."""
        output_path = Path(output_dir)
        import re as _re

        def _scrub(text: str) -> str:
            """Strip TBD/TBC/TBA placeholders the LLM may have written despite instructions."""
            return _re.sub(r'\b(TBD|TBC|TBA)\b', '[specify]', text, flags=_re.IGNORECASE)

        output_path.mkdir(parents=True, exist_ok=True)
        outputs = {}

        # 1. requirements.md
        req_content = _scrub(self._build_requirements_md(tool_input, project_name))
        req_file = output_path / "requirements.md"
        req_file.write_text(req_content, encoding="utf-8")
        outputs["requirements.md"] = req_content

        # 2. block_diagram.md
        block_mermaid = tool_input.get("block_diagram_mermaid", "")
        block_content = _scrub(f"# System Block Diagram\n## {project_name}\n\n```mermaid\n{block_mermaid}\n```\n")
        block_file = output_path / "block_diagram.md"
        block_file.write_text(block_content, encoding="utf-8")
        outputs["block_diagram.md"] = block_content

        # 3. architecture.md
        arch_mermaid = tool_input.get("architecture_mermaid", "")
        if arch_mermaid:
            arch_content = f"# System Architecture\n## {project_name}\n\n```mermaid\n{arch_mermaid}\n```\n"
        else:
            arch_content = f"# System Architecture\n## {project_name}\n\n*Architecture diagram will be generated with HRS.*\n"
        arch_content = _scrub(arch_content)
        arch_file = output_path / "architecture.md"
        arch_file.write_text(arch_content, encoding="utf-8")
        outputs["architecture.md"] = arch_content

        # 4. component_recommendations.md
        comp_content = _scrub(self._build_components_md(tool_input, project_name))
        comp_file = output_path / "component_recommendations.md"
        comp_file.write_text(comp_content, encoding="utf-8")
        outputs["component_recommendations.md"] = comp_content

        # 5. power_calculation.md
        power_content = _scrub(self._build_power_calc_md(tool_input, project_name))
        power_file = output_path / "power_calculation.md"
        power_file.write_text(power_content, encoding="utf-8")
        outputs["power_calculation.md"] = power_content

        # 6. gain_loss_budget.md — generated for all designs; non-RF designs get header-only file
        glb_content = _scrub(self._build_gain_loss_budget_md(tool_input, project_name))
        glb_file = output_path / "gain_loss_budget.md"
        glb_file.write_text(glb_content, encoding="utf-8")
        outputs["gain_loss_budget.md"] = glb_content

        self.log(f"Generated {len(outputs)} Phase 1 output files in {output_path}")
        return outputs

    def _build_requirements_md(self, tool_input: dict, project_name: str) -> str:
        """Build IEEE-style requirements.md."""
        lines = [
            f"# Hardware Requirements",
            f"## {project_name}",
            "",
            "## 1. Project Summary",
            "",
            tool_input.get("project_summary", ""),
            "",
            "## 2. Design Parameters",
            "",
            "| Parameter | Value |",
            "|---|---|",
        ]

        for key, value in tool_input.get("design_parameters", {}).items():
            lines.append(f"| {key.replace('_', ' ').title()} | {value} |")

        lines.extend(["", "## 3. Requirements", ""])

        # Group by category
        reqs = tool_input.get("requirements", [])
        categories = {}
        for req in reqs:
            cat = req.get("category", "general")
            categories.setdefault(cat, []).append(req)

        for cat, cat_reqs in categories.items():
            lines.append(f"### 3.{list(categories.keys()).index(cat)+1} {cat.title()} Requirements")
            lines.append("")
            lines.append("| ID | Title | Description | Priority | Validation | Dependencies | Constraints |")
            lines.append("|---|---|---|---|---|---|---|")
            for req in cat_reqs:
                deps = ", ".join(req.get('dependencies', [])) or "None"
                constraints = ", ".join(req.get('constraints', [])) or "None"
                lines.append(
                    f"| {req.get('req_id', '')} | {req.get('title', '')} | "
                    f"{req.get('description', '')} | {req.get('priority', 'Must have')} | "
                    f"{req.get('verification_method', 'test')} | "
                    f"{deps} | {constraints} |"
                )
            lines.append("")

        return "\n".join(lines)

    def _build_power_calc_md(self, tool_input: dict, project_name: str) -> str:
        """Build a per-component, per-rail power budget table matching the CSV template format."""
        from datetime import datetime
        comps = tool_input.get("component_recommendations", [])
        date = datetime.now().strftime("%d-%m-%Y")

        # Helper: try to extract a numeric value from a string like "3.3V", "100mA", "500mW"
        def parse_num(s: str, unit: str = "") -> float:
            import re as _re
            if not s:
                return 0.0
            s = str(s)
            m = _re.search(r'[\d.]+', s)
            if not m:
                return 0.0
            val = float(m.group())
            if "m" + unit.lower() in s.lower():  # mA, mW
                val /= 1000.0
            return val

        # Determine the primary supply rail for a component given its specs
        def infer_rail(comp: dict) -> float:
            specs = comp.get("primary_key_specs", {}) or {}
            for key in ("supply_voltage", "voltage", "vcc", "vdd", "operating_voltage"):
                v = specs.get(key, "")
                if v:
                    val = parse_num(v, "V")
                    if val > 0:
                        return val
            # Infer from function name
            func = comp.get("function", "").lower()
            if any(k in func for k in ("5v", "five", "usb")):
                return 5.0
            if any(k in func for k in ("2.5", "ddr")):
                return 2.5
            if any(k in func for k in ("1.8", "core")):
                return 1.8
            return 3.3  # default

        def infer_current(comp: dict) -> float:
            specs = comp.get("primary_key_specs", {}) or {}
            for key in ("supply_current", "current", "icc", "idd", "quiescent_current",
                        "operating_current", "typical_current"):
                v = specs.get(key, "")
                if v:
                    val = parse_num(v, "A")
                    if val > 0:
                        return val
            # Rough defaults by component function
            func = comp.get("function", "").lower()
            if "fpga" in func:
                return 0.500
            if any(k in func for k in ("mcu", "microcontroller", "processor")):
                return 0.150
            if any(k in func for k in ("transceiver", "rf", "amplifier", "pa")):
                return 0.300
            if any(k in func for k in ("adc", "dac")):
                return 0.050
            if any(k in func for k in ("flash", "memory", "eeprom")):
                return 0.030
            if any(k in func for k in ("regulator", "power", "ldo", "dc-dc")):
                return 0.010
            if any(k in func for k in ("resistor", "capacitor", "inductor", "passive")):
                return 0.001
            return 0.050  # generic IC default

        # Rails we track
        RAILS = [5.0, 3.3, 2.5, 1.8]
        RAIL_LABELS = ["5V", "3.3V", "2.5V", "1.8V"]

        rows = []
        rail_totals_typ = [0.0] * len(RAILS)
        rail_totals_max = [0.0] * len(RAILS)

        for i, comp in enumerate(comps, 1):
            func = comp.get("function", f"Component {i}")
            part = comp.get("primary_part", "—")
            specs = comp.get("primary_key_specs", {}) or {}
            pkg = specs.get("package", specs.get("Package", "—"))

            rail_v = infer_rail(comp)
            i_typ = infer_current(comp)
            i_max = i_typ * 1.30  # 30% margin for max

            p_typ = round(rail_v * i_typ, 3)
            p_max = round(rail_v * i_max, 3)

            # Find closest rail index
            closest = min(range(len(RAILS)), key=lambda idx: abs(RAILS[idx] - rail_v))

            # Build per-rail cells; only the matching rail gets values
            cells = []
            for idx in range(len(RAILS)):
                if idx == closest:
                    cells += [p_typ, p_max, p_typ, p_max]
                    rail_totals_typ[idx] += p_typ
                    rail_totals_max[idx] += p_max
                else:
                    cells += ["", "", "", ""]

            row = {
                "si": i,
                "desc": func,
                "pkg": pkg,
                "part": part,
                "qty": 1,
                "cells": cells,
                "tot_typ": p_typ,
                "tot_max": p_max,
            }
            rows.append(row)

        # Build split markdown tables (one per rail group) to avoid column overflow.
        # RAIL groups: [0]=5V, [1]=3.3V, [2]=2.5V, [3]=1.8V  → split 0-1 and 2-3
        grand_max = round(sum(rail_totals_max), 3)
        grand_typ = round(sum(rail_totals_typ), 3)

        def build_rail_table(rail_indices: list) -> list:
            """Emit a compact markdown table for the given rail indices."""
            sel_labels = [RAIL_LABELS[i] for i in rail_indices]
            # Header
            h1 = "| SI | Description | Part No | Qty"
            for lbl in sel_labels:
                h1 += f" | {lbl} TYP (W) | {lbl} MAX (W)"
            h1 += " | Total TYP (W) | Total MAX (W) |"
            # Separator: auto-built from column count so it always matches the header
            ncols = h1.count('|') - 1
            h2 = '| ' + ' | '.join(['---'] * ncols) + ' |'
            t_lines = [h1, h2]
            for row in rows:
                tot_typ_row = 0.0
                tot_max_row = 0.0
                line = f"| {row['si']} | {row['desc']} | {row['part']} | {row['qty']}"
                for ri in rail_indices:
                    # cells layout: 4 values per rail [typ, max, tot_typ, tot_max]
                    base = ri * 4
                    typ_w = row["cells"][base]
                    max_w = row["cells"][base + 1]
                    line += f" | {typ_w if typ_w != '' else '—'} | {max_w if max_w != '' else '—'}"
                    if isinstance(typ_w, float):
                        tot_typ_row += typ_w
                    if isinstance(max_w, float):
                        tot_max_row += max_w
                line += f" | {round(tot_typ_row, 3) if tot_typ_row else '—'} | {round(tot_max_row, 3) if tot_max_row else '—'} |"
                t_lines.append(line)
            # Totals row
            tot_line = "| | **TOTALS** | | "
            for ri in rail_indices:
                t_typ = round(rail_totals_typ[ri], 3)
                t_max = round(rail_totals_max[ri], 3)
                tot_line += f" | **{t_typ}** | **{t_max}**"
            sub_typ = round(sum(rail_totals_typ[i] for i in rail_indices), 3)
            sub_max = round(sum(rail_totals_max[i] for i in rail_indices), 3)
            tot_line += f" | **{sub_typ}** | **{sub_max}** |"
            t_lines.append(tot_line)
            return t_lines

        table_a = build_rail_table([0, 1])   # 5V and 3.3V
        table_b = build_rail_table([2, 3])   # 2.5V and 1.8V

        lines = [
            f"# Power Calculation",
            f"## {project_name}",
            "",
            f"**Date:** {date}",
            "",
            "> All values in Watts (W). TYP = typical operating power, MAX = worst-case (130% of TYP).",
            "> Rail assignment is based on component operating voltage from BOM.",
            "",
            "## Power Budget — 5 V & 3.3 V Rails",
            "",
        ]
        lines.extend(table_a)
        lines += [
            "",
            "## Power Budget — 2.5 V & 1.8 V Rails",
            "",
        ]
        lines.extend(table_b)
        lines += [
            "",
            "---",
            "",
            "## Power Summary",
            "",
            "| Rail | Typical Power (W) | Max Power (W) |",
            "|------|-------------------|---------------|",
        ]
        for idx, label in enumerate(RAIL_LABELS):
            t = round(rail_totals_typ[idx], 3)
            m = round(rail_totals_max[idx], 3)
            lines.append(f"| {label} | {t} | {m} |")
        lines += [
            f"| **TOTAL** | **{grand_typ}** | **{grand_max}** |",
            "",
            "> Note: Power values are estimated from component datasheets and design parameters.",
            "> Actual measurements should be taken during hardware bring-up and updated in this table.",
        ]

        return "\n".join(lines)

    def _build_gain_loss_budget_md(self, tool_input: dict, project_name: str) -> str:
        """Build RF Gain-Loss Budget markdown from tool_input['gain_loss_budget']."""
        from datetime import datetime
        glb = tool_input.get("gain_loss_budget") or {}
        stages = glb.get("stages", [])

        lines = [
            f"# RF Gain-Loss Budget",
            f"## {project_name}",
            "",
            f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d')}  ",
            f"**Document Status:** AI-GENERATED — verify against final component datasheets",
            "",
        ]

        # --- System parameters table ---
        freq   = glb.get("center_freq_mhz")
        bw     = glb.get("bandwidth_mhz")
        p_in   = glb.get("input_power_dbm")
        p_out  = glb.get("target_output_dbm")

        if any(v is not None for v in [freq, bw, p_in, p_out]):
            lines += [
                "## 1. System Parameters",
                "",
                "| Parameter | Value | Unit |",
                "|-----------|-------|------|",
            ]
            if freq   is not None: lines.append(f"| Centre Frequency    | {freq}   | MHz  |")
            if bw     is not None: lines.append(f"| RF Bandwidth        | {bw}     | MHz  |")
            if p_in   is not None: lines.append(f"| Input Signal Level  | {p_in}   | dBm  |")
            if p_out  is not None: lines.append(f"| Target Output Power | {p_out}  | dBm  |")
            if p_in is not None and p_out is not None:
                req_gain = round(p_out - p_in, 1)
                lines.append(f"| Required System Gain | {req_gain} | dB   |")
            lines.append("")

        if not stages:
            lines += [
                "## 2. Stage Budget",
                "",
                "> No stage data provided — re-run Phase 1 for an RF design to populate this table.",
                "",
            ]
            return "\n".join(lines)

        # --- Stage-by-stage table ---
        lines += [
            "## 2. Stage-by-Stage Gain / Loss Budget",
            "",
            "| # | Stage | Component | Gain/Loss (dB) | Cum. Gain (dB) | Output Power (dBm) | NF (dB) | Cum. NF (dB) | P1dB Out (dBm) | OIP3 (dBm) | Notes |",
            "|---|-------|-----------|---------------|----------------|-------------------|---------|-------------|---------------|-----------|-------|",
        ]

        for i, st in enumerate(stages, 1):
            name     = st.get("stage_name", "—")
            comp     = st.get("component", "—")
            gain     = st.get("gain_db", "—")
            cum_gain = st.get("cumulative_gain_db", "—")
            p_out_st = st.get("output_power_dbm", "—")
            nf       = st.get("noise_figure_db", "—")
            cum_nf   = st.get("cumulative_nf_db", "—")
            p1db     = st.get("p1db_out_dbm", "—")
            oip3     = st.get("oip3_dbm", "—")
            notes    = st.get("notes", "")

            # Format gain with sign
            if isinstance(gain, (int, float)):
                gain_str = f"+{gain:.1f}" if gain >= 0 else f"{gain:.1f}"
            else:
                gain_str = str(gain)

            # Hide 99 placeholder values (means "N/A")
            p1db_str = "N/A" if p1db == 99 else (f"{p1db:.1f}" if isinstance(p1db, (int, float)) else str(p1db))
            oip3_str = "N/A" if oip3 == 99 else (f"{oip3:.1f}" if isinstance(oip3, (int, float)) else str(oip3))

            nf_str     = f"{nf:.2f}"     if isinstance(nf,     (int, float)) else str(nf)
            cum_nf_str = f"{cum_nf:.2f}" if isinstance(cum_nf, (int, float)) else str(cum_nf)
            cum_gain_s = f"{cum_gain:.1f}" if isinstance(cum_gain, (int, float)) else str(cum_gain)
            p_out_s    = f"{p_out_st:.1f}" if isinstance(p_out_st, (int, float)) else str(p_out_st)

            lines.append(
                f"| {i} | {name} | {comp} | {gain_str} | {cum_gain_s} | {p_out_s} | {nf_str} | {cum_nf_str} | {p1db_str} | {oip3_str} | {notes} |"
            )

        lines.append("")

        # --- Summary ---
        if stages:
            last = stages[-1]
            total_gain = last.get("cumulative_gain_db")
            sys_nf     = stages[0].get("cumulative_nf_db") if stages else None  # first stage NF dominates
            final_nf   = last.get("cumulative_nf_db")
            final_pout = last.get("output_power_dbm")

            lines += [
                "## 3. Budget Summary",
                "",
                "| Metric | Value | Unit |",
                "|--------|-------|------|",
            ]
            if total_gain is not None:
                lines.append(f"| Total System Gain     | {total_gain:.1f}  | dB  |")
            if final_pout is not None:
                lines.append(f"| Final Output Power    | {final_pout:.1f}  | dBm |")
            if final_nf is not None:
                lines.append(f"| Cascaded System NF    | {final_nf:.2f} | dB  |")
            if p_in is not None and p_out is not None and total_gain is not None:
                margin = round(p_out - (p_in + total_gain), 1)
                margin_str = f"{'+' if margin >= 0 else ''}{margin}"
                lines.append(f"| Output Power Margin   | {margin_str} | dB  |")
            lines.append("")

        # Determine next section number dynamically
        sec = 4

        # --- Return Loss per stage (if at least one stage has S11/S22 data) ---
        rl_stages = [s for s in stages if s.get("input_return_loss_db") is not None or s.get("output_return_loss_db") is not None]
        if rl_stages:
            lines += [
                f"## {sec}. Return Loss — Per Stage",
                "",
                "| # | Stage | Component | S11 — Input RL (dB) | S22 — Output RL (dB) | Notes |",
                "|---|-------|-----------|---------------------|----------------------|-------|",
            ]
            for i, st in enumerate(rl_stages, 1):
                s11 = st.get("input_return_loss_db")
                s22 = st.get("output_return_loss_db")
                lines.append(
                    f"| {i} | {st.get('stage_name', '—')} | {st.get('component', '—')}"
                    f" | {f'{s11:.1f}' if s11 is not None else '—'}"
                    f" | {f'{s22:.1f}' if s22 is not None else '—'}"
                    f" | {st.get('notes', '')} |"
                )
            lines += ["", "> Return loss values are referenced to 50 Ω. Higher value = better match.", ""]
            sec += 1

        # --- Harmonic Rejection (only when data provided) ---
        harmonics = glb.get("harmonic_rejection") or []
        if harmonics:
            lines += [
                f"## {sec}. Harmonic Rejection",
                "",
                "| Harmonic Order | Frequency (MHz) | Expected Rejection (dBc) | Required Spec (dBc) | Pass/Fail |",
                "|----------------|-----------------|--------------------------|---------------------|-----------|",
            ]
            for h in harmonics:
                order    = h.get("harmonic_order", "?")
                freq     = h.get("frequency_mhz", "?")
                rej      = h.get("rejection_db")
                spec     = h.get("spec_db")
                meets    = h.get("meets_spec")
                rej_str  = f"{rej:.1f}" if isinstance(rej, (int, float)) else "—"
                spec_str = f"{spec:.1f}" if isinstance(spec, (int, float)) else "—"
                pf       = ("✓ PASS" if meets else "✗ FAIL") if meets is not None else "—"
                lines.append(f"| {order}H | {freq} | {rej_str} | {spec_str} | {pf} |")
            lines += ["", "> Higher rejection (more negative dBc) is better. Filter may be required if spec is not met.", ""]
            sec += 1

        # --- Output Power vs Frequency (flatness) ---
        pvf = glb.get("power_vs_frequency") or []
        if pvf:
            lines += [
                f"## {sec}. Output Power vs Frequency",
                "",
                "| Frequency (MHz) | Output Power (dBm) | Gain (dB) | Flatness (dB) |",
                "|-----------------|--------------------|-----------|---------------|",
            ]
            for row in pvf:
                f_mhz = row.get("frequency_mhz", "?")
                pout  = row.get("output_power_dbm")
                gain  = row.get("gain_db")
                flat  = row.get("flatness_db")
                lines.append(
                    f"| {f_mhz}"
                    f" | {f'{pout:.1f}' if isinstance(pout, (int, float)) else '—'}"
                    f" | {f'{gain:.1f}' if isinstance(gain, (int, float)) else '—'}"
                    f" | {f'{flat:+.1f}' if isinstance(flat, (int, float)) else '—'} |"
                )
            lines += ["", "> Flatness measured relative to midband output power.", ""]
            sec += 1

        # --- Output Power vs Input Power (AM-AM / compression) ---
        pvi = glb.get("power_vs_input") or []
        if pvi:
            lines += [
                f"## {sec}. Output Power vs Input Drive Level (AM-AM)",
                "",
                "| Input (dBm) | Output (dBm) | Gain (dB) | Compression (dB) |",
                "|-------------|--------------|-----------|------------------|",
            ]
            for row in pvi:
                pin  = row.get("input_power_dbm")
                pout = row.get("output_power_dbm")
                gain = row.get("gain_db")
                comp = row.get("gain_compression_db")
                lines.append(
                    f"| {f'{pin:.1f}' if isinstance(pin, (int, float)) else '—'}"
                    f" | {f'{pout:.1f}' if isinstance(pout, (int, float)) else '—'}"
                    f" | {f'{gain:.1f}' if isinstance(gain, (int, float)) else '—'}"
                    f" | {f'{comp:.1f}' if isinstance(comp, (int, float)) else '—'} |"
                )
            lines += ["", "> Compression > 0 dB indicates onset of saturation.", ""]
            sec += 1

        # --- Cable Loss Budget ---
        cable = glb.get("cable_loss") or []
        if cable:
            lines += [
                f"## {sec}. Cable & Connector Loss Budget",
                "",
                "| Segment | Cable/Connector Type | Length (m) | Loss/m (dB/m) | Total Loss (dB) | Frequency (MHz) |",
                "|---------|----------------------|------------|---------------|-----------------|-----------------|",
            ]
            total_cable_loss = 0.0
            for row in cable:
                seg   = row.get("segment", "—")
                ctype = row.get("cable_type", "—")
                length = row.get("length_m", 0)
                loss_m = row.get("loss_db_per_m")
                total  = row.get("total_loss_db", 0)
                f_mhz  = row.get("frequency_mhz", "—")
                total_cable_loss += total if isinstance(total, (int, float)) else 0
                lines.append(
                    f"| {seg} | {ctype}"
                    f" | {length if length else '—'}"
                    f" | {f'{loss_m:.3f}' if isinstance(loss_m, (int, float)) else '—'}"
                    f" | {f'{total:.2f}' if isinstance(total, (int, float)) else '—'}"
                    f" | {f_mhz} |"
                )
            lines += [
                f"| **TOTAL** | | | | **{round(total_cable_loss, 2)}** | |",
                "",
                "> Cable loss must be compensated by additional gain or accepted as part of system link budget.",
                "",
            ]
            sec += 1

        # --- Friis formula reminder ---
        lines += [
            f"## {sec}. Cascade Noise Figure — Friis Formula",
            "",
            "$$F_{{sys}} = F_1 + \\frac{{F_2 - 1}}{{G_1}} + \\frac{{F_3 - 1}}{{G_1 G_2}} + \\cdots$$",
            "",
            "Where *F* = linear noise factor (not dB), *G* = linear gain.",
            "The first stage NF dominates — minimise LNA/driver NF for best system sensitivity.",
            "",
            "---",
            "> **Note:** All values are estimated from component datasheets at 25 °C nominal.",
            "> Verify with bench measurements (spectrum analyser + noise source) during hardware bring-up.",
        ]

        return "\n".join(lines)

    def _build_components_md(self, tool_input: dict, project_name: str) -> str:
        """Build component recommendations markdown.
        All datasheet URLs are verified via HTTP HEAD before inclusion —
        dead links are replaced with a manufacturer product-search fallback.
        """
        import re as _re
        import urllib.request as _urllib
        import urllib.parse as _urllib_parse
        import urllib.error as _urllib_err
        from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _as_completed

        # ── URL bad-pattern filter (fast, no network) ──────────────────────────
        _BAD_PATTERNS = [
            r'/vpt[/-]', r'vptpower\.com', r'\bvpt\b',
        ]
        def _filter_url(url: str) -> str:
            if not url or not url.startswith('http'):
                return ''
            for pat in _BAD_PATTERNS:
                if _re.search(pat, url, _re.IGNORECASE):
                    return ''
            return url

        # ── Manufacturer → product-search fallback URL builder ─────────────────
        _MFR_SEARCH: dict = {
            'analog devices':        'https://www.analog.com/en/search.html#q={part}',
            'analog':                'https://www.analog.com/en/search.html#q={part}',
            'texas instruments':     'https://www.ti.com/product/{part}',
            'ti':                    'https://www.ti.com/product/{part}',
            'nxp':                   'https://www.nxp.com/search#q={part}',
            'nxp semiconductors':    'https://www.nxp.com/search#q={part}',
            'st':                    'https://www.st.com/en/search.html#q={part}',
            'stmicroelectronics':    'https://www.st.com/en/search.html#q={part}',
            'microchip':             'https://www.microchip.com/search/searchresults/{part}',
            'microchip technology':  'https://www.microchip.com/search/searchresults/{part}',
            'infineon':              'https://www.infineon.com/cms/en/product/search/?q={part}',
            'infineon technologies': 'https://www.infineon.com/cms/en/product/search/?q={part}',
            'onsemi':                'https://www.onsemi.com/search?q={part}',
            'on semiconductor':      'https://www.onsemi.com/search?q={part}',
            'xilinx':                'https://www.xilinx.com/search/site-keyword-search.html#q={part}',
            'amd':                   'https://www.amd.com/en/search/site-keyword-search.html#q={part}',
            'amd (xilinx)':          'https://www.amd.com/en/search/site-keyword-search.html#q={part}',
            'lattice':               'https://www.latticesemi.com/products#{part}',
            'lattice semiconductor': 'https://www.latticesemi.com/products#{part}',
            'renesas':               'https://www.renesas.com/en/search?keywords={part}',
            'murata':                'https://www.murata.com/en-us/partdetail/{part}',
            'vicor':                 'https://www.vicorpower.com/search?q={part}',
            'te connectivity':       'https://www.te.com/en/search.html#q={part}',
            'mouser':                'https://www.mouser.com/Search/Refine?Keyword={part}',
        }
        def _fallback_url(part: str, mfr: str) -> str:
            """Build a manufacturer search page URL for the given part number."""
            key = mfr.strip().lower()
            template = _MFR_SEARCH.get(key, 'https://www.google.com/search?q={part}+datasheet')
            return template.format(part=_urllib_parse.quote(part, safe=''))

        # ── Live HTTP HEAD check (5 s timeout, follows one redirect) ───────────
        def _head_ok(url: str) -> bool:
            try:
                req = _urllib.Request(url, method='HEAD')
                req.add_header('User-Agent',
                               'Mozilla/5.0 (compatible; HardwarePipelineBot/1.0)')
                with _urllib.urlopen(req, timeout=5) as resp:
                    return resp.status < 400
            except Exception:
                # Try GET as fallback (some servers block HEAD)
                try:
                    req2 = _urllib.Request(url)
                    req2.add_header('User-Agent',
                                    'Mozilla/5.0 (compatible; HardwarePipelineBot/1.0)')
                    with _urllib.urlopen(req2, timeout=5) as resp2:
                        return resp2.status < 400
                except Exception:
                    return False

        # ── Collect all URLs that need validation ──────────────────────────────
        comps = tool_input.get("component_recommendations", [])
        # Build list of (url, part, mfr) tuples to check in parallel
        to_check: list[tuple[str, str, str]] = []
        for comp in comps:
            part = comp.get('primary_part', '')
            mfr  = comp.get('primary_manufacturer', '')
            raw_ds = _filter_url(comp.get('datasheet_url', '').strip())
            if raw_ds:
                to_check.append((raw_ds, part, mfr))
            for alt in comp.get('alternatives', []):
                raw_alt = _filter_url(alt.get('datasheet_url', '').strip())
                if raw_alt:
                    to_check.append((raw_alt, alt.get('part_number', part), mfr))

        # Parallel HEAD checks — max 10 workers
        url_ok: dict[str, bool] = {}
        if to_check:
            urls_unique = list({u for u, _, _ in to_check})
            with _TPE(max_workers=min(10, len(urls_unique))) as pool:
                fut_map = {pool.submit(_head_ok, u): u for u in urls_unique}
                for fut in _as_completed(fut_map):
                    url_ok[fut_map[fut]] = fut.result()

        def _verified_url(raw_url: str, part: str, mfr: str) -> str:
            """Return raw_url if live, else a manufacturer search page fallback."""
            filtered = _filter_url(raw_url)
            if not filtered:
                return _fallback_url(part, mfr)
            if url_ok.get(filtered, False):
                return filtered
            # URL is dead — use manufacturer search page
            return _fallback_url(part, mfr)

        # ── Build markdown ─────────────────────────────────────────────────────
        lines = [
            "# Component Recommendations",
            f"## {project_name}",
            "",
        ]

        for i, comp in enumerate(comps, 1):
            part = comp.get('primary_part', 'See BOM')
            mfr  = comp.get('primary_manufacturer', '')
            ds_url = _verified_url(comp.get('datasheet_url', '').strip(), part, mfr)
            dk_url = comp.get('digikey_url', '').strip()

            # Primary heading with part number as a link if datasheet available
            part_str = f"[{part}]({ds_url})" if ds_url else part

            lines.extend([
                f"### {i}. {comp.get('function', 'Component')}",
                "",
                f"**Primary Choice:** {part_str} ({mfr})",
                "",
                f"*{comp.get('primary_description', '')}*",
                "",
            ])

            # Quick-link row for datasheet / DigiKey
            links = []
            if ds_url:
                links.append(f"[📄 Datasheet]({ds_url})")
            if dk_url:
                links.append(f"[🛒 DigiKey]({dk_url})")
            if links:
                lines.append("  ".join(links))
                lines.append("")

            # Key specs — remove 'datasheet' key if LLM stuffed the URL there
            specs = {k: v for k, v in (comp.get("primary_key_specs") or {}).items()
                     if k.lower() not in ("datasheet", "datasheet_url", "digikey", "digikey_url")}
            if specs:
                lines.append("| Spec | Value |")
                lines.append("|---|---|")
                for k, v in specs.items():
                    lines.append(f"| {k} | {v} |")
                lines.append("")

            # Alternatives
            alts = comp.get("alternatives", [])
            if alts:
                lines.append("**Alternatives:**")
                for alt in alts:
                    alt_pn  = alt.get('part_number', '')
                    alt_mfr = alt.get('manufacturer', mfr)
                    alt_ds  = _verified_url(alt.get('datasheet_url', '').strip(), alt_pn, alt_mfr)
                    alt_pn_str = f"[{alt_pn}]({alt_ds})" if alt_ds else alt_pn
                    lines.append(
                        f"- **{alt_pn_str}** ({alt_mfr}): "
                        f"{alt.get('trade_off', '')}"
                    )
                lines.append("")

            # Rationale
            rationale = comp.get("selection_rationale", "")
            if rationale:
                lines.append(f"**Selection Rationale:** {rationale}")
                lines.append("")

        return "\n".join(lines)


    def _detect_complete_requirements(self, response_content: str) -> bool:
        """
        Detect if the response contains a complete requirements document.
        This is a fallback for models that don't support tool calling (e.g., GLM-4).
        """
        content_lower = response_content.lower()

        # Strong signal: long response (>2000 chars) with multiple REQ-HW IDs = almost certainly complete
        req_count = len(re.findall(r'REQ-HW-\d+', response_content, re.IGNORECASE))
        if len(response_content) > 2000 and req_count >= 3:
            return True

        # Look for key indicators of a complete requirements document
        indicators = [
            # Requirement IDs present
            req_count >= 1,
            # Hardware requirements header
            'hardware requirements' in content_lower,
            'requirements document' in content_lower,
            # Project summary section
            'project summary' in content_lower,
            # Design parameters table
            'design parameters' in content_lower or 'parameter' in content_lower,
            # Component recommendations
            'component recommendations' in content_lower or 'component' in content_lower,
            # Next steps or conclusion phrases (broader set)
            any(phrase in content_lower for phrase in [
                'next steps', 'phase complete', 'requirements captured',
                'would you like me to', 'shall i proceed',
                'work on next', 'let me know what', 'phase 1 deliverable',
                'deliverable', 'generated your', 'complete requirements',
            ]),
        ]

        # Need at least 4 indicators to consider it complete
        return sum(indicators) >= 4

    def _parse_requirements_response(self, response_content: str, project_name: str) -> Optional[dict]:
        """
        Parse a complete requirements response into structured format.
        This is a fallback for models that don't support tool calling.
        """
        try:
            # Extract project summary
            summary_match = re.search(
                r'(?:Project Summary|##\s*\d*\s*Summary)[\s:]*\n+(.*?)(?=##|\n\n|\Z)',
                response_content,
                re.IGNORECASE | re.DOTALL
            )
            project_summary = (summary_match.group(1).strip()[:500]
                             if summary_match else "Hardware design project captured from conversation.")

            # Extract requirement entries
            requirements = []
            req_pattern = r'(?:REQ-HW[-_]?\d+|\|\s*REQ[-_]?HW[-_]?\d+)'
            for match in re.finditer(req_pattern, response_content, re.IGNORECASE):
                # Try to extract the full requirement table row
                start = max(0, match.start() - 200)
                end = min(len(response_content), match.end() + 500)
                context = response_content[start:end]

                req_id = re.search(r'REQ[-_]?HW[-_]?\d+', match.group(0), re.IGNORECASE)
                if req_id:
                    req_id = req_id.group(0).upper().replace('_', '-')

                    # Parse requirement details from table or list
                    title_match = re.search(r'\|\s*' + re.escape(req_id) + r'\s*\|\s*([^|]+)', context, re.IGNORECASE)
                    title = title_match.group(1).strip() if title_match else "Hardware Requirement"

                    desc_match = re.search(r'\|\s*' + re.escape(req_id) + r'\s*\|\s*[^|]*\|\s*([^|]+)', context, re.IGNORECASE)
                    description = (desc_match.group(1).strip() if desc_match
                                 else "Extracted from requirements conversation.")

                    # Detect priority
                    priority = "Must have"
                    ctx_lower = context.lower()
                    if "should" in ctx_lower or "should have" in ctx_lower:
                        priority = "Should have"
                    elif "could" in ctx_lower or "could have" in ctx_lower or "may" in ctx_lower:
                        priority = "Could have"
                    elif "won't" in ctx_lower or "wont" in ctx_lower:
                        priority = "Won't have"

                    requirements.append({
                        "req_id": req_id,
                        "category": "functional",
                        "title": title,
                        "description": description,
                        "priority": priority,
                        "verification_method": "test",
                        "dependencies": [],
                        "constraints": []
                    })

            # Ensure we have at least some requirements
            if len(requirements) < 3:
                # Add default requirements based on conversation
                requirements = [
                    {"req_id": "REQ-HW-001", "category": "functional", "title": "System Functionality",
                     "description": "System shall meet the functional requirements described in the conversation.", "priority": "Must have", "verification_method": "test", "dependencies": [], "constraints": []},
                    {"req_id": "REQ-HW-002", "category": "performance", "title": "Performance Targets",
                     "description": "System shall meet the performance targets specified.", "priority": "Must have", "verification_method": "test", "dependencies": [], "constraints": []},
                    {"req_id": "REQ-HW-003", "category": "environmental", "title": "Environmental Conditions",
                     "description": "System shall operate within the specified environmental conditions.", "priority": "Must have", "verification_method": "test", "dependencies": [], "constraints": []},
                ]

            # Extract design parameters from any tables or key-value pairs
            design_parameters = {}
            param_patterns = [
                r'\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|',  # Markdown tables
                r'([A-Z][a-zA-Z\s]+?)\s*[:=]\s*([^\n]+)',  # Key: Value
            ]

            for pattern in param_patterns:
                for match in re.finditer(pattern, response_content):
                    key = match.group(1).strip()
                    value = match.group(2).strip()
                    # Skip if looks like a table header or unrelated
                    if key.lower() not in ['parameter', 'value', 'id', 'title', 'description', 'priority']:
                        key_clean = re.sub(r'\s+', '_', key.lower())
                        design_parameters[key_clean] = value
                        if len(design_parameters) >= 15:  # Limit extracted parameters
                            break

            # Add default parameters if none found
            if not design_parameters:
                design_parameters = {
                    "input_voltage": "As specified",
                    "output_power": "As specified",
                    "frequency_range": "As specified",
                    "temperature_range": "As specified",
                }

            # Extract or generate block diagram mermaid
            block_diagram = self._extract_or_generate_mermaid(response_content, "block")

            # Extract or generate architecture mermaid
            architecture = self._extract_or_generate_mermaid(response_content, "architecture")

            # Extract component recommendations
            component_recommendations = self._extract_components(response_content)

            return {
                "project_summary": project_summary,
                "requirements": requirements[:20],  # Limit to 20 requirements
                "design_parameters": design_parameters,
                "block_diagram_mermaid": block_diagram,
                "architecture_mermaid": architecture,
                "component_recommendations": component_recommendations,
            }

        except Exception as e:
            self.log(f"Failed to parse requirements response: {e}", "warning")
            return None

    def _extract_or_generate_mermaid(self, response_content: str, diagram_type: str) -> str:
        """Extract mermaid diagram from response or generate a default one."""
        # Look for mermaid code blocks
        mermaid_match = re.search(
            r'```mermaid\s*(.*?)```',
            response_content,
            re.DOTALL | re.IGNORECASE
        )
        if mermaid_match:
            return mermaid_match.group(1).strip()

        # Generate a default diagram
        if diagram_type == "block":
            return '''graph TD
    PWR[Power Input] --> PWR_DIST[Power Distribution]
    PWR_DIST --> MCU[Control/Digital Processing]
    PWR_DIST --> RF[RF/Analog Front End]
    MCU --> CTRL[Control Interfaces]
    RF --> OUT[Output/Load]
    style PWR fill:#f9f,stroke:#333,stroke-width:2px
    style MCU fill:#bbf,stroke:#333,stroke-width:2px
    style RF fill:#bfb,stroke:#333,stroke-width:2px'''
        else:
            return '''graph LR
    subgraph POWER["Power Domain"]
        PWR_IN[Input] --> REG[Regulators]
    end
    subgraph DIGITAL["Digital Domain"]
        MCU[Controller]
    end
    subgraph ANALOG["Analog/RF Domain"]
        AFE[Front End]
    end
    POWER --> DIGITAL
    POWER --> ANALOG
    DIGITAL --> ANALOG'''

    def _extract_components(self, response_content: str) -> list:
        """Extract component recommendations from response."""
        components = []

        # Look for component tables or lists
        # Pattern: Part Number | Manufacturer | Description
        table_pattern = r'\|\s*([A-Z0-9][-A-Z0-9]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|'
        for match in re.finditer(table_pattern, response_content):
            part_number = match.group(1).strip()
            manufacturer = match.group(2).strip()
            description = match.group(3).strip()

            # Skip if looks like a header or not a component
            if (len(part_number) >= 3 and
                part_number not in ['PART NUMBER', 'PART', 'NUMBER'] and
                manufacturer not in ['MANUFACTURER', 'MFR', 'VENDOR']):
                components.append({
                    "function": description[:50],
                    "primary_part": part_number,
                    "primary_manufacturer": manufacturer,
                    "primary_description": description,
                    "primary_key_specs": {},
                    "alternatives": [],
                    "selection_rationale": "Extracted from requirements document."
                })
                if len(components) >= 10:
                    break

        # If no components found in tables, add placeholder
        if not components:
            components = [
                {
                    "function": "Controller/MCU",
                    "primary_part": "See component recommendations",
                    "primary_manufacturer": "Various",
                    "primary_description": "Primary controller selected based on design requirements.",
                    "primary_key_specs": {},
                    "alternatives": [],
                    "selection_rationale": "Selected in component recommendation phase."
                }
            ]

        return components
