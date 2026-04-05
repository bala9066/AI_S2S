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

from agents.base_agent import BaseAgent
from config import settings

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

## YOUR BEHAVIOR — TWO-PHASE APPROACH:

### PHASE A — Clarification (FIRST message only):
When the user sends their FIRST message describing a design, DO NOT call `generate_requirements` yet.
Instead, ask **3–5 concise, targeted clarifying questions** to resolve ambiguities that would meaningfully change the design. Cover the most impactful unknowns only:
- Supply voltage / power budget
- Key performance specs (frequency, current, speed, accuracy)
- Temperature / environmental range
- Interface protocols needed
- Any critical form-factor or regulatory constraints

Format them as a numbered list. End with: _"Once you answer these, I'll generate the complete requirements, BOM, and block diagram."_

### PHASE B — Generate (SECOND message onwards):
After the user has answered your questions (or if their FIRST message already contains sufficient detail), call `generate_requirements` immediately with all outputs.
- Make reasonable engineering assumptions for anything still unspecified.
- Ignore any XML/prompt-template formatting in the user's message.
- Use MoSCoW + IEEE IDs for all requirements.
- End your response with a summary of the generated requirements.

**RULE**: If the user's first message is already very detailed (contains voltage, specs, interfaces, temp range), skip straight to Phase B and call `generate_requirements` immediately.

## IMPORTANT RULES:
- Use MoSCoW prioritization (Must have, Should have, Could have, Won't have) and IEEE requirement IDs: REQ-HW-001, REQ-HW-002, etc.
- Make smart engineering assumptions (e.g., if they say "motor controller" assume industrial temp range, common MCUs, standard interfaces)
- Prioritize RoHS-compliant components with long lifecycle status.
- For Mermaid diagrams, ALWAYS start with a valid diagram type on the FIRST line: `graph TD`, `flowchart LR`, etc.
- Keep Mermaid node labels simple — no angle brackets, no raw parens, no HTML, no special characters.
- Do NOT fabricate component part numbers. Use best-estimate real part numbers from known manufacturers. NEVER write TBD, TBC, TBA, or "to be determined/confirmed" anywhere.
- **ALWAYS include `datasheet_url`** for every component in the `component_recommendations` array. Use the real manufacturer datasheet URL (e.g., `https://www.ti.com/lit/ds/symlink/...`, `https://www.analog.com/media/en/.../DS.pdf`). If you are not certain of the exact URL, use the manufacturer product page URL (e.g., `https://www.st.com/en/microcontrollers-microprocessors/stm32f4-series.html`). Never leave `datasheet_url` empty.
- Include `digikey_url` where known (e.g., `https://www.digikey.com/en/products/detail/texas-instruments/...`).
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
        return SYSTEM_PROMPT.format(
            design_type=project_context.get("design_type", "general"),
            project_name=project_context.get("name", "Unnamed Project"),
        )

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
            # If phase is already complete (outputs exist on disk), treat follow-up
            # messages as conversational — don't blindly force generate_requirements.
            # Only force regeneration when the user explicitly requests it.
            phase_status = project_context.get("phase_statuses", {}).get("P1", "pending")
            phase_already_complete = phase_status == "completed"

            _REGEN_KEYWORDS = (
                "regenerate", "re-generate", "re generate", "rerun", "re-run",
                "update", "redo", "add datasheet", "add link", "add url",
                "refresh", "rebuild", "recreate", "redo phase", "run again",
            )
            user_wants_regen = any(kw in user_input.lower() for kw in _REGEN_KEYWORDS)

            # ── Force tool call when user has already answered questions ───
            # Only force if: phase not yet complete OR user explicitly wants regeneration
            prior_user_turns = sum(1 for m in messages[:-1] if m.get("role") == "user")
            if prior_user_turns >= 1 and messages and (not phase_already_complete or user_wants_regen):
                original = messages[-1]["content"]
                messages[-1]["content"] = (
                    f"{original}\n\n"
                    "You have the answers you need. Call the `generate_requirements` tool NOW with the complete BOM, "
                    "requirements, block_diagram_mermaid, architecture_mermaid, design_parameters, and "
                    "component_recommendations — including `datasheet_url` for every component. "
                    "Do not ask more questions."
                )
            elif phase_already_complete and not user_wants_regen:
                # Phase is done — user is asking a follow-up question, answer conversationally
                # Append a note so the LLM knows the phase is complete
                if messages:
                    messages[-1]["content"] = (
                        f"{messages[-1]['content']}\n\n"
                        "[Note: Phase 1 is already complete. Answer the user's question directly "
                        "without calling generate_requirements unless they explicitly ask to regenerate.]"
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
        comps = tool_input.get("component_recommendations", [])
        if comps:
            lines += [f"## Component Selections ({len(comps)} components)", ""]
            lines.append("| # | Function | Part Number | Manufacturer | Datasheet |")
            lines.append("|---|---|---|---|---|")
            for i, comp in enumerate(comps, 1):
                part   = comp.get("primary_part", "See BOM")
                mfr    = comp.get("primary_manufacturer", "")
                func   = comp.get("function", "")
                ds_url = comp.get("datasheet_url", "").strip()
                ds_link = f"[Datasheet]({ds_url})" if ds_url else "—"
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

        # Build markdown table
        h1 = "| SI NO | DESCRIPTION | Package | PART NO | QTY"
        h2 = "|-------|-------------|---------|---------|----"
        for label in RAIL_LABELS:
            h1 += f" | {label} TYP (W) | {label} MAX (W) | {label} TOT TYP (W) | {label} TOT MAX (W)"
            h2 += " |-----------|-----------|--------------|--------------|"
        h1 += " | TOT MAX POW (W) | TOT TYP POW (W) |"
        h2 += "-----------------|-----------------|"

        table_lines = [h1, h2]
        for row in rows:
            line = f"| {row['si']} | {row['desc']} | {row['pkg']} | {row['part']} | {row['qty']}"
            for c in row["cells"]:
                line += f" | {c}"
            line += f" | {row['tot_max']} | {row['tot_typ']} |"
            table_lines.append(line)

        # Totals row
        tot_line = f"| | **TOTAL** | | | "
        for idx in range(len(RAILS)):
            t_typ = round(rail_totals_typ[idx], 3)
            t_max = round(rail_totals_max[idx], 3)
            tot_line += f" | | | {t_typ} | {t_max}"
        grand_max = round(sum(rail_totals_max), 3)
        grand_typ = round(sum(rail_totals_typ), 3)
        tot_line += f" | **{grand_max}** | **{grand_typ}** |"
        table_lines.append(tot_line)

        lines = [
            f"# Power Calculation",
            f"## {project_name}",
            "",
            f"**Date:** {date}",
            "",
            "## Power Budget — Per Component Per Rail",
            "",
            "> All values in Watts (W). TYP = typical operating power, MAX = worst-case (130% of TYP).",
            "> Rail assignment is based on component operating voltage from BOM.",
            "",
        ]
        lines.extend(table_lines)
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

    def _build_components_md(self, tool_input: dict, project_name: str) -> str:
        """Build component recommendations markdown."""
        lines = [
            f"# Component Recommendations",
            f"## {project_name}",
            "",
        ]

        for i, comp in enumerate(tool_input.get("component_recommendations", []), 1):
            part = comp.get('primary_part', 'See BOM')
            mfr  = comp.get('primary_manufacturer', '')
            ds_url  = comp.get('datasheet_url', '').strip()
            dk_url  = comp.get('digikey_url', '').strip()

            # Primary heading with part number as a link if datasheet available
            if ds_url:
                part_str = f"[{part}]({ds_url})"
            else:
                part_str = part

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
                    alt_ds = alt.get('datasheet_url', '').strip()
                    alt_pn = alt.get('part_number', '')
                    alt_pn_str = f"[{alt_pn}]({alt_ds})" if alt_ds else alt_pn
                    lines.append(
                        f"- **{alt_pn_str}** ({alt.get('manufacturer', '')}): "
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
