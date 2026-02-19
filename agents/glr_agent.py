"""
Phase 6: GLR (Glue Logic Requirements) Generation Agent

Generates complete I/O specifications that bridge hardware design to FPGA implementation.
"""

import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a hardware-FPGA interface specification expert.

Generate a Glue Logic Requirements (GLR) document that provides complete I/O specifications
for FPGA implementation. This document bridges Phase 4 (Netlist) and Phase 7 (FPGA HDL).

## DOCUMENT STRUCTURE (IEEE 29148 adapted):

# 1. Introduction
## 1.1 Purpose
## 1.2 Scope
## 1.3 FPGA Device Selection

# 2. I/O Requirements
## 2.1 Input Signals
## 2.2 Output Signals
## 2.3 Bidirectional Signals

# 3. Pin Assignment Table
(Complete table: Pin Number, Signal Name, Direction, Voltage Level, Drive Strength, Pull-up/down)

# 4. Timing Requirements
## 4.1 Clock Domains
## 4.2 Setup/Hold Times
## 4.3 Propagation Delays

# 5. Interface Specifications
## 5.1 SPI Interfaces
## 5.2 I2C Interfaces
## 5.3 UART Interfaces
## 5.4 Custom Interfaces

# 6. Register Map
(Address, Register Name, Width, Access, Reset Value, Description)

# 7. Verification Requirements

Include Mermaid timing diagrams where appropriate.
All signal names must be consistent with the netlist from Phase 4.
"""


class GLRAgent(BaseAgent):
    """Phase 6: Glue Logic Requirements generation."""

    def __init__(self):
        super().__init__(
            phase_number="P6",
            phase_name="GLR Generation",
            model=settings.primary_model,
            max_tokens=8192,
        )

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")

        # Load prior outputs
        requirements = self._load_file(output_dir / "requirements.md")
        netlist_visual = self._load_file(output_dir / "netlist_visual.md")
        netlist_json = self._load_file(output_dir / "netlist.json")

        user_message = f"""Generate a complete GLR document for:

**Project:** {project_name}

### Requirements:
{requirements[:3000]}

### Netlist:
{netlist_visual[:4000]}

### Netlist Data:
{netlist_json[:3000]}

Generate the full GLR specification with pin assignments, timing, register map, and interface specs.
"""

        response = await self.call_llm(
            messages=[{"role": "user", "content": user_message}],
            system=self.get_system_prompt(project_context),
        )

        glr_content = response.get("content", "")
        glr_file = output_dir / "glr_specification.md"
        glr_file.write_text(glr_content, encoding="utf-8")

        self.log(f"GLR generated: {len(glr_content)} chars")

        return {
            "response": "GLR specification generated.",
            "phase_complete": True,
            "outputs": {glr_file.name: glr_content},
        }

    def _load_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
