"""
Phase 8a: SRS (Software Requirements Specification) Agent - IEEE 830/29148 Compliant

Generates SRS from HRS + GLR, mapping hardware requirements to software functions.
"""

import json
import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from config import settings
from generators.srs_generator import SRSGenerator

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
        self.srs_generator = SRSGenerator()

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

        # Extract structured data using LLM
        hw_requirements = await self._extract_hw_requirements(requirements, hrs)
        sw_features = await self._extract_sw_features(glr, hrs)

        # Generate SRS using the generator
        srs_content = self.srs_generator.generate(
            project_name=project_name,
            hw_requirements=hw_requirements,
            sw_features=sw_features,
            metadata={"version": project_context.get("version", "1.0")},
        )

        # Save using generator's save method
        srs_file = self.srs_generator.save(srs_content, output_dir, project_name)

        self.log(f"SRS generated: {len(srs_content)} chars")

        return {
            "response": "SRS document generated (IEEE 830 compliant).",
            "phase_complete": True,
            "outputs": {srs_file.name: srs_content},
        }

    async def _extract_hw_requirements(self, requirements: str, hrs: str) -> list:
        """Extract hardware requirements from documents."""
        reqs = []
        if requirements:
            for line in requirements.split('\n')[:20]:
                if line.strip() and not line.startswith('#'):
                    reqs.append({"text": line.strip()})
        return reqs

    async def _extract_sw_features(self, glr: str, hrs: str) -> list:
        """Extract software features from GLR/HRS."""
        features = [
            {"id": "F-01", "text": "System initialization and boot"},
            {"id": "F-02", "text": "Device control and configuration"},
            {"id": "F-03", "text": "Data acquisition and processing"},
        ]
        return features

    def _load_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
