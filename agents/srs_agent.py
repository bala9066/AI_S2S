"""
Phase 8a: SRS (Software Requirements Specification) Agent - IEEE 830/29148 Compliant

Generates SRS from HRS + GLR, mapping hardware requirements to software functions.
"""

import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior software architect generating an IEEE 830/29148-compliant Software Requirements Specification (SRS) for embedded hardware systems.

## DOCUMENT STRUCTURE (IEEE 830 / IEEE 29148:2018):

# 1. Introduction
## 1.1 Purpose
## 1.2 Scope
## 1.3 Definitions, Acronyms, and Abbreviations
## 1.4 References
## 1.5 Overview

# 2. Overall Description
## 2.1 Product Perspective
## 2.2 Product Functions
## 2.3 User Characteristics
## 2.4 Constraints
## 2.5 Assumptions and Dependencies

# 3. Specific Requirements
## 3.1 External Interface Requirements
### 3.1.1 Hardware Interfaces (map from HRS/GLR registers to software APIs)
### 3.1.2 Software Interfaces
### 3.1.3 Communication Interfaces
## 3.2 Functional Requirements (REQ-SW-001, REQ-SW-002, ...)
## 3.3 Performance Requirements
## 3.4 Design Constraints
## 3.5 Software System Attributes
### 3.5.1 Reliability
### 3.5.2 Availability
### 3.5.3 Security
### 3.5.4 Maintainability
### 3.5.5 Portability

# 4. Verification and Validation
## 4.1 Unit Test Requirements
## 4.2 Integration Test Requirements
## 4.3 System Test Requirements

# 5. Traceability Matrix
(REQ-SW-xxx -> REQ-HW-xxx mapping)

# 6. Appendices

## RULES:
- Every software requirement MUST have ID: REQ-SW-001, REQ-SW-002, etc.
- Each REQ-SW-xxx MUST trace back to one or more REQ-HW-xxx
- Map GLR register addresses to C struct definitions
- Define driver API signatures (function prototypes)
- Include Mermaid sequence diagrams for key interactions
- Define error codes and error handling strategy
"""


class SRSAgent(BaseAgent):
    """Phase 8a: IEEE 830-compliant SRS generation."""

    def __init__(self):
        super().__init__(
            phase_number="P8a",
            phase_name="SRS Generation",
            model=settings.primary_model,
            max_tokens=8192,
        )

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")

        # Load prior phase outputs
        requirements = self._load_file(output_dir / "requirements.md")
        hrs = self._load_file(output_dir / f"HRS_{project_name.replace(' ', '_')}.md")
        glr = self._load_file(output_dir / "glr_specification.md")

        user_message = f"""Generate a complete IEEE 830 SRS for:

**Project:** {project_name}

### Hardware Requirements:
{requirements[:3000]}

### HRS (Hardware Requirements Specification):
{hrs[:4000]}

### GLR (Glue Logic Requirements):
{glr[:4000]}

Map hardware requirements to software requirements. Every REQ-SW must trace to REQ-HW.
Define driver APIs, register access functions, and test requirements.
"""

        response = await self.call_llm(
            messages=[{"role": "user", "content": user_message}],
            system=self.get_system_prompt(project_context),
        )

        srs_content = response.get("content", "")

        # Handle truncation
        if response.get("stop_reason") == "max_tokens":
            continuation = await self.call_llm(
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": srs_content},
                    {"role": "user", "content": "Continue from where you left off."},
                ],
                system=self.get_system_prompt(project_context),
            )
            srs_content += "\n" + continuation.get("content", "")

        srs_file = output_dir / f"SRS_{project_name.replace(' ', '_')}.md"
        srs_file.write_text(srs_content, encoding="utf-8")

        self.log(f"SRS generated: {len(srs_content)} chars")

        return {
            "response": "SRS document generated (IEEE 830 compliant).",
            "phase_complete": True,
            "outputs": {srs_file.name: srs_content},
        }

    def _load_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
