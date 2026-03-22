"""
Phase 6: GLR (Glue Logic Requirements) Generation Agent

Generates complete I/O specifications that bridge hardware design to FPGA implementation.
"""

import json
import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from config import settings
from generators.glr_generator import GLRGenerator

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

IMPORTANT: Do NOT use TBD, TBA, or TBC placeholders. Derive specific values from the
provided component data (datasheets, netlist), use engineering defaults, or state a
justified assumption inline (e.g., "assumed 3.3V I/O based on FPGA bank default").
Every register address, timing value, and signal specification must be concrete.
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
        self.glr_generator = GLRGenerator()

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

        # Parse netlist data for generator
        netlist_data = {}
        if netlist_json:
            try:
                netlist_data = json.loads(netlist_json)
            except Exception as e:
                self.log(f"Failed to parse netlist JSON: {e}", "warning")

        # Extract structured requirements using LLM
        structured_reqs = await self._extract_requirements(requirements)

        # Generate GLR using the generator
        glr_content = self.glr_generator.generate(
            project_name=project_name,
            netlist=netlist_data,
            requirements=structured_reqs,
            metadata={"date": requirements[:500] if requirements else ""},
        )

        # Save using generator's save method
        glr_file = self.glr_generator.save(glr_content, output_dir, project_name)

        self.log(f"GLR generated: {len(glr_content)} chars")

        return {
            "response": "GLR specification generated.",
            "phase_complete": True,
            "outputs": {glr_file.name: glr_content},
        }

    async def _extract_requirements(self, requirements_content: str) -> list:
        """Extract structured requirements from markdown using LLM."""
        if not requirements_content:
            return []

        try:
            import re
            # Simple extraction of requirement lines
            reqs = []
            for line in requirements_content.split('\n'):
                if line.strip().startswith('-') or line.strip().startswith('*'):
                    reqs.append({"text": line.strip('- *').strip()})
            return reqs[:10]  # Limit to first 10
        except Exception:
            return []

    def _load_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
