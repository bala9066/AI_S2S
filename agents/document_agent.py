"""
Phase 2: HRS Document Generation Agent (IEEE 29148 Compliant)

Generates a 50-100 page Hardware Requirements Specification in markdown format.
Uses IEEE 29148:2018 section structure with requirement traceability.
"""

import logging
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from config import settings

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

        # Build the prompt with all Phase 1 data
        user_message = f"""Generate a complete IEEE 29148 Hardware Requirements Specification for:

**Project:** {project_name}

## Phase 1 Outputs:

### Requirements:
{requirements_content}

### Block Diagram:
{block_diagram}

### Architecture:
{architecture}

### Component Recommendations:
{components}

Generate the FULL HRS document now. Be thorough and detailed."""

        # Call LLM (may need multiple calls for long documents)
        hrs_content = await self._generate_hrs(user_message, project_name)

        # Save output
        hrs_file = output_dir / f"HRS_{project_name.replace(' ', '_')}.md"
        hrs_file.write_text(hrs_content, encoding="utf-8")

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
