"""
Phase 2: HRS Document Generation Agent (IEEE 29148 Compliant)

Generates a 50-100 page Hardware Requirements Specification in markdown format.
Uses IEEE 29148:2018 section structure with requirement traceability.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from config import settings
from generators.hrs_generator import HRSGenerator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior hardware documentation engineer producing an IEEE 29148:2018-compliant Hardware Requirements Specification (HRS).

You will be given:
- Project requirements (with REQ-HW-xxx IDs)
- Component recommendations
- Design parameters
- Block diagram and architecture descriptions

## YOUR TASK:
Generate a COMPLETE, DETAILED Hardware Requirements Specification following this IEEE 29148 structure:

### DOCUMENT STRUCTURE (YOU MUST FOLLOW THIS EXACTLY):

# 1. Introduction
## 1.1 Purpose
## 1.2 Scope
## 1.3 Definitions, Acronyms, and Abbreviations
## 1.4 References
## 1.5 Overview

# 2. System Overview
## 2.1 System Description
## 2.2 System Block Diagram
## 2.3 System Architecture
## 2.4 Operating Environment

# 3. Hardware Requirements
## 3.1 Functional Requirements
## 3.2 Performance Requirements
## 3.3 Interface Requirements
### 3.3.1 External Interfaces
### 3.3.2 Internal Interfaces
### 3.3.3 Communication Interfaces
## 3.4 Environmental Requirements
## 3.5 Power Requirements
## 3.6 Physical Requirements

# 4. Design Constraints
## 4.1 Standards Compliance
## 4.2 Component Constraints
## 4.3 Manufacturing Constraints

# 5. Verification Requirements
## 5.1 Test Requirements
## 5.2 Analysis Requirements
## 5.3 Inspection Requirements

# 6. Bill of Materials (Preliminary)

# 7. Traceability Matrix

## RULES:
- Every requirement MUST have an ID (REQ-HW-xxx) and be traceable
- Include Mermaid diagrams where appropriate (block diagrams, timing, data flow)
- Be DETAILED and SPECIFIC - this is a production document, not a summary
- Include actual calculations (power budget, thermal analysis) where relevant
- Reference specific component part numbers from the recommendations
- Use tables for structured data (BOM, pin assignments, power budget)
- Target 50-100 pages of content (be thorough)
"""


class DocumentAgent(BaseAgent):
    """Phase 2: IEEE 29148-compliant HRS generation."""

    def __init__(self):
        super().__init__(
            phase_number="P2",
            phase_name="HRS Generation",
            model=settings.fast_model,  # Haiku for speed on large doc generation
            max_tokens=8192,
        )
        self.hrs_generator = HRSGenerator()

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")

        # Load Phase 1 outputs
        requirements_content = self._load_file(output_dir / "requirements.md")
        block_diagram = self._load_file(output_dir / "block_diagram.md")
        architecture = self._load_file(output_dir / "architecture.md")
        components = self._load_file(output_dir / "component_recommendations.md")

        if not requirements_content:
            return {
                "response": "Phase 1 outputs not found. Please complete Requirements Capture first.",
                "phase_complete": False,
                "outputs": {},
            }

        # PRIMARY PATH: LLM writes the full IEEE 29148 document from P1 context
        user_message = (
            f"Generate a complete IEEE 29148:2018 Hardware Requirements Specification for:\n\n"
            f"**Project:** {project_name}\n\n"
            f"## Phase 1 Requirements\n{requirements_content[:5000]}\n\n"
            f"## Block Diagram\n{block_diagram[:2000] if block_diagram else 'Not captured.'}\n\n"
            f"## System Architecture\n{architecture[:2000] if architecture else 'Not captured.'}\n\n"
            f"## Component Recommendations\n{components[:3000] if components else 'Not captured.'}\n\n"
            "Generate ALL sections per the IEEE 29148 structure in your system prompt. "
            "Be thorough and project-specific. Include real power calculations, interface tables, "
            "and Mermaid diagrams. Do NOT skip any section."
        )

        hrs_content = ""
        try:
            hrs_content = await self._generate_hrs(user_message, project_name)
        except Exception as e:
            self.log(f"LLM HRS generation failed: {e} — falling back to template", "warning")

        # FALLBACK: template generator if LLM failed or returned too little
        if not hrs_content or len(hrs_content) < 800:
            structured_requirements = await self._extract_requirements(requirements_content, project_name)
            component_data = await self._extract_components(components)
            metadata = {
                "version": project_context.get("version", "1.0"),
                "author": project_context.get("author", "Hardware Pipeline AI"),
                "input_voltage": project_context.get("design_parameters", {}).get("input_voltage", "12-24"),
                "max_power": project_context.get("design_parameters", {}).get("max_power", "TBD"),
                "temp_min": project_context.get("design_parameters", {}).get("temp_min", "-40"),
                "temp_max": project_context.get("design_parameters", {}).get("temp_max", "+85"),
            }
            hrs_content = self.hrs_generator.generate(
                project_name=project_name,
                requirements=structured_requirements,
                component_data=component_data,
                metadata=metadata,
            )

        # Save output
        hrs_file = self.hrs_generator.save(hrs_content, output_dir, project_name)
        self.log(f"HRS generated: {len(hrs_content)} chars -> {hrs_file}")

        return {
            "response": f"HRS document generated ({len(hrs_content)} characters).",
            "phase_complete": True,
            "outputs": {hrs_file.name: hrs_content},
        }

    async def _generate_hrs(self, user_message: str, project_name: str) -> str:
        """Generate HRS, potentially in multiple LLM calls for long documents."""
        system = self.get_system_prompt({})

        response = await self.call_llm(
            messages=[{"role": "user", "content": user_message}],
            system=system,
        )

        hrs_content = response.get("content", "")

        # If the document seems truncated, ask for continuation
        if response.get("stop_reason") == "max_tokens":
            self.log("HRS truncated, requesting continuation...")
            continuation = await self.call_llm(
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": hrs_content},
                    {"role": "user", "content": "Continue from where you left off. Do not repeat any sections."},
                ],
                system=system,
            )
            hrs_content += "\n" + continuation.get("content", "")

        return hrs_content

    def _load_file(self, path: Path) -> str:
        """Load a file's content or return empty string."""
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    async def _extract_requirements(self, requirements_content: str, project_name: str) -> list:
        """Extract structured requirements from markdown using LLM."""
        system_prompt = """Extract structured hardware requirements from the markdown content.
Return a JSON array of requirements with fields: id, text, priority (HIGH/MEDIUM/LOW)."""

        try:
            response = await self.call_llm(
                messages=[{
                    "role": "user",
                    "content": f"Extract structured requirements from:\n\n{requirements_content[:8000]}\n\nReturn JSON array."
                }],
                system=system_prompt,
            )

            content = response.get("content", "")
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            self.log(f"Failed to extract structured requirements: {e}", "warning")

        # Fallback: return basic structure
        return [
            {"id": "REQ-HW-001", "text": "System shall meet all specified requirements", "priority": "HIGH"}
        ]

    async def _extract_components(self, components_content: str) -> dict:
        """Extract component data from markdown."""
        if not components_content:
            return {}

        return {
            "components_markdown": components_content[:5000],
        }
