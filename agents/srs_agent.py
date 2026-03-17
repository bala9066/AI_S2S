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

        # PRIMARY PATH: LLM writes the full IEEE 830 SRS from project context
        user_message = (
            f"Generate a complete IEEE 830/29148 Software Requirements Specification for:\n\n"
            f"**Project:** {project_name}\n\n"
            f"## Hardware Requirements Specification (P2)\n{hrs[:5000] if hrs else 'Not yet generated — use P1 requirements below.'}\n\n"
            f"## P1 Requirements\n{requirements[:3000] if requirements else 'Not captured.'}\n\n"
            f"## GLR Specification (P6)\n{glr[:3000] if glr else 'Not yet generated.'}\n\n"
            "Generate ALL sections per the IEEE 830 structure in your system prompt. "
            "Map every HW requirement to SW requirements with REQ-SW-xxx IDs. "
            "Include Mermaid sequence diagrams, define C function prototypes, "
            "error codes, and RTOS considerations. Be thorough and project-specific."
        )

        srs_content = ""
        try:
            response = await self.call_llm(
                messages=[{"role": "user", "content": user_message}],
                system=SYSTEM_PROMPT,
            )
            srs_content = response.get("content", "")
            # Continuation if truncated
            if response.get("stop_reason") == "max_tokens" and srs_content:
                self.log("SRS truncated, requesting continuation...")
                cont = await self.call_llm(
                    messages=[
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": srs_content},
                        {"role": "user", "content": "Continue from where you left off. Do not repeat sections already written."},
                    ],
                    system=SYSTEM_PROMPT,
                )
                srs_content += "\n" + cont.get("content", "")
        except Exception as e:
            self.log(f"LLM SRS generation failed: {e} — falling back to template", "warning")

        # FALLBACK: template generator
        if not srs_content or len(srs_content) < 800:
            hw_requirements = await self._extract_hw_requirements(requirements, hrs)
            sw_features = await self._extract_sw_features(glr, hrs)
            srs_content = self.srs_generator.generate(
                project_name=project_name,
                hw_requirements=hw_requirements,
                sw_features=sw_features,
                metadata={"version": project_context.get("version", "1.0")},
            )

        # Save output
        srs_file = self.srs_generator.save(srs_content, output_dir, project_name)
        self.log(f"SRS generated: {len(srs_content)} chars")

        return {
            "response": "SRS document generated (IEEE 830 compliant).",
            "phase_complete": True,
            "outputs": {srs_file.name: srs_content},
        }

    async def _extract_hw_requirements(self, requirements: str, hrs: str) -> list:
        """Extract hardware requirements from documents using REQ-HW-xxx patterns."""
        import re
        reqs = []

        # Search in HRS first, then requirements
        content = hrs if hrs else requirements
        if not content:
            return []

        # Pattern: REQ-HW-nnn with optional title and description
        pattern = r'REQ-HW-(\d+)[:\s]+([^\n]+?)(?:\n|$)'
        matches = re.findall(pattern, content, re.MULTILINE)

        for req_id, title in matches:
            reqs.append({
                "req_id": f"REQ-HW-{req_id}",
                "title": title.strip(),
                "description": title.strip()
            })

        # Fallback: extract from header sections mentioning hardware
        if not reqs:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if any(keyword in line.lower() for keyword in ['hardware', 'interface', 'pin', 'power', 'voltage', 'frequency']):
                    if line.strip() and not line.startswith('#'):
                        reqs.append({
                            "req_id": f"REQ-HW-{len(reqs)+1:03d}",
                            "title": line.strip(),
                            "description": line.strip()
                        })

        return reqs if reqs else [
            {"req_id": "REQ-HW-001", "title": "System Power", "description": "System must operate from 3.3V or 5V supply"},
            {"req_id": "REQ-HW-002", "title": "Communication", "description": "System must support UART/SPI/I2C interfaces"},
        ]

    async def _extract_sw_features(self, glr: str, hrs: str) -> list:
        """Extract software features from GLR/HRS content."""
        import re
        features = []

        # Search for interface protocols and control algorithms
        content = (glr + "\n" + hrs) if (glr or hrs) else ""
        if not content:
            return self._default_sw_features()

        # Look for protocol mentions
        protocol_pattern = r'\b(SPI|I2C|UART|CAN|USB|GPIO|ADC|PWM|DMA|RTC)\b'
        protocols = set(re.findall(protocol_pattern, content, re.IGNORECASE))

        for i, protocol in enumerate(sorted(protocols), 1):
            features.append({
                "id": f"F-{i:02d}",
                "name": f"{protocol.upper()} Interface Driver",
                "text": f"Support for {protocol} protocol communication"
            })

        # Look for control/algorithm keywords
        algo_keywords = [
            (r'control\s+loop|controller|servo', 'Control Loop'),
            (r'filter|filtering|calibration', 'Signal Filtering'),
            (r'interrupt|timer|timing', 'Interrupt Handler'),
            (r'initialization|boot|startup', 'System Initialization'),
            (r'error\s+handling|fault|exception', 'Error Handling'),
            (r'state\s+machine|transition', 'State Machine'),
            (r'data\s+acquisition|sampling|conversion', 'Data Acquisition'),
        ]

        for pattern, feature_name in algo_keywords:
            if re.search(pattern, content, re.IGNORECASE):
                idx = len(features) + 1
                features.append({
                    "id": f"F-{idx:02d}",
                    "name": feature_name,
                    "text": f"{feature_name} and processing"
                })

        # Return defaults if no patterns matched
        return features if features else self._default_sw_features()

    def _default_sw_features(self) -> list:
        """Default software features."""
        return [
            {"id": "F-01", "name": "System Initialization", "text": "System initialization and boot"},
            {"id": "F-02", "name": "Device Control", "text": "Device control and configuration"},
            {"id": "F-03", "name": "Data Acquisition", "text": "Data acquisition and processing"},
        ]

    def _load_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
