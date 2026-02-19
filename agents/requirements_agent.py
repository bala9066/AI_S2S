"""
Phase 1: Requirements Capture + Component Selection Agent

This agent:
1. Engages in natural conversation to understand hardware requirements
2. Asks clarifying questions (voltage, frequency, temp range, etc.)
3. Extracts structured requirements with IEEE-style IDs (REQ-HW-001)
4. Generates block diagram and architecture in Mermaid
5. Recommends components with 2-3 alternatives

Outputs: requirements.md, block_diagram.md, architecture.md, component_recommendations.md
"""

import json
import logging
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert hardware design engineer with 25+ years of experience across RF/wireless, motor control, power electronics, industrial control, sensor systems, and high-speed digital design.

You work for a defense electronics company. Your role is to help engineers capture complete hardware design requirements through natural conversation.

## YOUR BEHAVIOR:

1. **Ask clarifying questions** - Never assume. Ask about:
   - Operating voltage range, power requirements
   - Frequency bands (for RF), switching frequency (for power)
   - Temperature range (commercial/industrial/military)
   - Compliance requirements (RoHS, REACH, FCC, CE, MIL-STD)
   - Interface requirements (SPI, I2C, UART, Ethernet, USB)
   - Performance targets (accuracy, bandwidth, efficiency)
   - Environmental constraints (vibration, humidity, altitude)
   - Production volume (affects component selection)

2. **Guide the conversation** - Ask 3-5 questions at a time, not everything at once.

3. **When you have enough information** (typically after 3-5 exchanges), generate the complete output by calling the `generate_requirements` tool.

## IMPORTANT RULES:
- Always respond in a helpful, mentoring tone
- Suggest best practices when relevant (grounding, decoupling, thermal management)
- Flag potential issues early (EMI concerns, thermal limits, power budget)
- Think about the FULL system, not just individual components
- Use IEEE requirement IDs: REQ-HW-001, REQ-HW-002, etc.
- Prioritize components that are RoHS compliant and have long lifecycle status

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
                        "priority": {"type": "string", "enum": ["shall", "should", "may"]},
                        "verification_method": {
                            "type": "string",
                            "enum": ["test", "analysis", "inspection", "demonstration"],
                        },
                    },
                    "required": ["req_id", "category", "title", "description"],
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
                        "alternatives": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "part_number": {"type": "string"},
                                    "manufacturer": {"type": "string"},
                                    "trade_off": {"type": "string"},
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


class RequirementsAgent(BaseAgent):
    """Phase 1: Conversational requirements capture and component selection."""

    def __init__(self):
        super().__init__(
            phase_number="P1",
            phase_name="Requirements Capture",
            model=settings.primary_model,
            tools=[GENERATE_REQUIREMENTS_TOOL],
            max_tokens=8192,
        )

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT.format(
            design_type=project_context.get("design_type", "general"),
            project_name=project_context.get("name", "Unnamed Project"),
        )

    async def execute(self, project_context: dict, user_input: str) -> dict:
        """
        Execute Phase 1 conversation turn.

        Returns:
            dict with 'response' (text to show user), 'phase_complete' (bool),
            'outputs' (dict of filename->content if complete), 'parameters' (extracted params)
        """
        system = self.get_system_prompt(project_context)

        # Build messages from conversation history
        history = project_context.get("conversation_history", [])
        messages = []
        for msg in history:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        # If no history, this is the first message
        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": user_input})

        # Call Claude
        response = await self.call_llm(
            messages=messages,
            system=system,
        )

        # Check if the agent called generate_requirements tool
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc["name"] == "generate_requirements":
                    # Generate all output files
                    outputs = self._generate_output_files(
                        tc["input"],
                        project_context.get("output_dir", "output"),
                        project_context.get("name", "project"),
                    )
                    return {
                        "response": response.get("content", "") + "\n\nPhase 1 complete! All requirements documents have been generated.",
                        "phase_complete": True,
                        "outputs": outputs,
                        "parameters": tc["input"].get("design_parameters", {}),
                    }

        # Normal conversation response
        return {
            "response": response.get("content", ""),
            "phase_complete": False,
            "outputs": {},
            "parameters": {},
        }

    def _generate_output_files(
        self, tool_input: dict, output_dir: str, project_name: str
    ) -> dict:
        """Generate all Phase 1 output markdown files."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        outputs = {}

        # 1. requirements.md
        req_content = self._build_requirements_md(tool_input, project_name)
        req_file = output_path / "requirements.md"
        req_file.write_text(req_content, encoding="utf-8")
        outputs["requirements.md"] = req_content

        # 2. block_diagram.md
        block_mermaid = tool_input.get("block_diagram_mermaid", "")
        block_content = f"# System Block Diagram\n## {project_name}\n\n```mermaid\n{block_mermaid}\n```\n"
        block_file = output_path / "block_diagram.md"
        block_file.write_text(block_content, encoding="utf-8")
        outputs["block_diagram.md"] = block_content

        # 3. architecture.md
        arch_mermaid = tool_input.get("architecture_mermaid", "")
        if arch_mermaid:
            arch_content = f"# System Architecture\n## {project_name}\n\n```mermaid\n{arch_mermaid}\n```\n"
        else:
            arch_content = f"# System Architecture\n## {project_name}\n\n*Architecture diagram will be generated with HRS.*\n"
        arch_file = output_path / "architecture.md"
        arch_file.write_text(arch_content, encoding="utf-8")
        outputs["architecture.md"] = arch_content

        # 4. component_recommendations.md
        comp_content = self._build_components_md(tool_input, project_name)
        comp_file = output_path / "component_recommendations.md"
        comp_file.write_text(comp_content, encoding="utf-8")
        outputs["component_recommendations.md"] = comp_content

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
            lines.append("| ID | Title | Description | Priority | Verification |")
            lines.append("|---|---|---|---|---|")
            for req in cat_reqs:
                lines.append(
                    f"| {req.get('req_id', '')} | {req.get('title', '')} | "
                    f"{req.get('description', '')} | {req.get('priority', 'shall')} | "
                    f"{req.get('verification_method', 'test')} |"
                )
            lines.append("")

        return "\n".join(lines)

    def _build_components_md(self, tool_input: dict, project_name: str) -> str:
        """Build component recommendations markdown."""
        lines = [
            f"# Component Recommendations",
            f"## {project_name}",
            "",
        ]

        for i, comp in enumerate(tool_input.get("component_recommendations", []), 1):
            lines.extend([
                f"### {i}. {comp.get('function', 'Component')}",
                "",
                f"**Primary Choice:** {comp.get('primary_part', 'TBD')} ({comp.get('primary_manufacturer', '')})",
                "",
                f"*{comp.get('primary_description', '')}*",
                "",
            ])

            # Key specs
            specs = comp.get("primary_key_specs", {})
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
                    lines.append(
                        f"- **{alt.get('part_number', '')}** ({alt.get('manufacturer', '')}): "
                        f"{alt.get('trade_off', '')}"
                    )
                lines.append("")

            # Rationale
            rationale = comp.get("selection_rationale", "")
            if rationale:
                lines.append(f"**Selection Rationale:** {rationale}")
                lines.append("")

        return "\n".join(lines)
