"""
Phase 7a: Register Description Table (RDT) + Programming Sequence (PSQ) Agent.

Automates the previously-manual parts of Phase 7 (FPGA Design):
  - Generates the Register Description Table (RDT) from GLR/netlist specs
  - Generates the Programming Sequence (PSQ) for device initialisation
  - Outputs structured Markdown documents ready for firmware / RTL use

Configuration: uses the same LLM settings as other agents.
"""

import logging
from pathlib import Path
from typing import Dict

from agents.base_agent import BaseAgent
from config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert FPGA/embedded-systems engineer specialising in register map design and firmware programming sequences.

## YOUR TASK
Given a GLR (Glue Logic Requirements) specification and netlist information, generate:

### 1. Register Description Table (RDT)
A complete table of every memory-mapped register in the design:
- Register name and address (hex)
- Bit-field breakdown: field name, bits [MSB:LSB], access type (R/W/RO/WO/RC), reset value
- Plain-English description per field
- Any special notes (write-protect, shadow, self-clearing, etc.)

### 2. Programming Sequence (PSQ)
An ordered initialisation sequence for bringing the device up safely:
- Step number and phase label (e.g. "Power-On Reset", "Clock Init", "Peripheral Enable")
- Register address + value to write
- Wait/polling conditions where required
- Human-readable rationale for each step

## OUTPUT FORMAT
Use the `generate_rdt_psq` tool to return structured data. Also include a Markdown summary.

## GUIDELINES
- Use 0x-prefixed hex for all addresses and values
- Access types: R (read-only), W (write-only), RW (read-write), RC (read-clears)
- Reset values must match hardware defaults described in the GLR
- Programming sequence must be in correct dependency order
- Flag any registers that require a specific write sequence (e.g. unlock key)
"""

GENERATE_RDT_PSQ_TOOL = {
    "name": "generate_rdt_psq",
    "description": "Generate structured Register Description Table and Programming Sequence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "registers": {
                "type": "array",
                "description": "List of memory-mapped registers",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":         {"type": "string", "description": "Register name (e.g. CTRL_REG)"},
                        "address":      {"type": "string", "description": "Hex address (e.g. 0x0000)"},
                        "reset_value":  {"type": "string", "description": "Reset value (e.g. 0x00)"},
                        "description":  {"type": "string", "description": "Register purpose"},
                        "fields": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name":        {"type": "string"},
                                    "bits":        {"type": "string", "description": "e.g. [7:4]"},
                                    "access":      {"type": "string", "description": "RW / R / W / RC"},
                                    "reset":       {"type": "string", "description": "Reset value for this field"},
                                    "description": {"type": "string"},
                                },
                                "required": ["name", "bits", "access", "description"],
                            },
                        },
                    },
                    "required": ["name", "address", "description", "fields"],
                },
            },
            "programming_sequence": {
                "type": "array",
                "description": "Ordered list of initialisation steps",
                "items": {
                    "type": "object",
                    "properties": {
                        "step":          {"type": "integer"},
                        "phase":         {"type": "string", "description": "Phase label (e.g. Clock Init)"},
                        "register":      {"type": "string", "description": "Register name"},
                        "address":       {"type": "string", "description": "Hex address"},
                        "value":         {"type": "string", "description": "Hex value to write"},
                        "condition":     {"type": "string", "description": "Wait/poll condition (optional)"},
                        "rationale":     {"type": "string", "description": "Why this step is needed"},
                    },
                    "required": ["step", "phase", "register", "address", "value", "rationale"],
                },
            },
            "summary": {
                "type": "string",
                "description": "Short summary of the register map and sequence",
            },
        },
        "required": ["registers", "programming_sequence"],
    },
}


class RdtPsqAgent(BaseAgent):
    """Phase 7a: Register Description Table + Programming Sequence generation."""

    def __init__(self):
        super().__init__(
            phase_number="P7a",
            phase_name="Register Map & Programming Sequence",
            model=settings.primary_model,
            tools=[GENERATE_RDT_PSQ_TOOL],
            max_tokens=8192,
        )

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")

        # Load prior phase outputs
        glr_spec   = self._load_file(output_dir / f"GLR_{project_name.replace(' ', '_')}.md")
        netlist    = self._load_file(output_dir / "netlist_visual.md")
        hrs        = self._load_file(output_dir / f"HRS_{project_name.replace(' ', '_')}.md")

        if not glr_spec:
            self.log("GLR spec not found — using requirements and netlist only")

        user_message = f"""Generate a complete Register Description Table (RDT) and
Programming Sequence (PSQ) for:

**Project:** {project_name}

### GLR Specification:
{glr_spec[:5000] if glr_spec else '(not yet generated — infer from requirements)'}

### Netlist Summary:
{netlist[:3000] if netlist else '(not available)'}

### HRS Reference:
{hrs[:2000] if hrs else '(not available)'}

Use the `generate_rdt_psq` tool to return structured register data and initialisation steps.
Include all memory-mapped registers visible in the GLR / netlist.
"""

        response = await self.call_llm(
            messages=[{"role": "user", "content": user_message}],
            system=self.get_system_prompt(project_context),
        )

        outputs: Dict[str, str] = {}
        rdt_psq_data = None

        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc["name"] == "generate_rdt_psq":
                    rdt_psq_data = tc["input"]
                    break

        if rdt_psq_data:
            outputs["register_description_table.md"] = self._build_rdt_md(
                rdt_psq_data, project_name
            )
            outputs["programming_sequence.md"] = self._build_psq_md(
                rdt_psq_data, project_name
            )
            self.log(
                f"RDT: {len(rdt_psq_data.get('registers', []))} registers, "
                f"PSQ: {len(rdt_psq_data.get('programming_sequence', []))} steps"
            )
        else:
            logger.warning("P7a: generate_rdt_psq tool not called — using fallback")
            fallback = (
                f"# Register Description Table — {project_name}\n\n"
                "**Status:** Automatic generation could not complete.\n\n"
                "The AI model did not return structured register data. "
                "Please re-run Phase 7a or ensure Phase 6 (GLR) has been completed first.\n\n"
                f"## LLM Response\n\n{response.get('content', '(no response)')}\n"
            )
            outputs["register_description_table.md"] = fallback

        return {
            "response": response.get("content", "RDT & PSQ generated."),
            "phase_complete": bool(rdt_psq_data),
            "outputs": outputs,
        }

    # ------------------------------------------------------------------ #
    # Markdown builders
    # ------------------------------------------------------------------ #

    def _build_rdt_md(self, data: dict, project_name: str) -> str:
        lines = [
            "# Register Description Table",
            f"## {project_name}",
            "",
            f"> **Total registers:** {len(data.get('registers', []))}",
            "",
        ]
        if data.get("summary"):
            lines += [data["summary"], ""]

        for reg in data.get("registers", []):
            lines += [
                "---",
                f"### `{reg.get('name', 'REG')}` — Address: `{reg.get('address', '0x??')}`",
                f"**Reset value:** `{reg.get('reset_value', '0x00')}`",
                "",
                reg.get("description", ""),
                "",
                "| Field | Bits | Access | Reset | Description |",
                "|-------|------|--------|-------|-------------|",
            ]
            for f in reg.get("fields", []):
                lines.append(
                    f"| `{f.get('name','')}` | `{f.get('bits','')}` "
                    f"| {f.get('access','')} | `{f.get('reset','0')}` "
                    f"| {f.get('description','')} |"
                )
            lines.append("")

        return "\n".join(lines)

    def _build_psq_md(self, data: dict, project_name: str) -> str:
        steps = data.get("programming_sequence", [])
        lines = [
            "# Programming Sequence (PSQ)",
            f"## {project_name}",
            "",
            f"> **Total steps:** {len(steps)}",
            "",
            "| # | Phase | Register | Address | Value | Condition | Rationale |",
            "|---|-------|----------|---------|-------|-----------|-----------|",
        ]

        for s in steps:
            cond = s.get("condition", "—") or "—"
            lines.append(
                f"| {s.get('step','')} | {s.get('phase','')} "
                f"| `{s.get('register','')}` | `{s.get('address','')}` "
                f"| `{s.get('value','')}` | {cond} "
                f"| {s.get('rationale','')} |"
            )

        lines += [
            "",
            "---",
            "",
            "## Detailed Steps",
            "",
        ]
        for s in steps:
            lines += [
                f"### Step {s.get('step','')} — {s.get('phase','')}",
                f"- **Register:** `{s.get('register','')}` at `{s.get('address','')}`",
                f"- **Write value:** `{s.get('value','')}`",
            ]
            if s.get("condition"):
                lines.append(f"- **Wait/Poll:** {s['condition']}")
            lines += [
                f"- **Rationale:** {s.get('rationale','')}",
                "",
            ]

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # File loader
    # ------------------------------------------------------------------ #

    def _load_file(self, path: Path) -> str:
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                pass
        return ""
