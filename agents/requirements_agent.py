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

# Optional import for ComponentSearchTool (ChromaDB has Python 3.14+ compatibility issues)
try:
    from tools.component_search import ComponentSearchTool
    COMPONENT_SEARCH_AVAILABLE = True
except (ImportError, Exception) as e:
    COMPONENT_SEARCH_AVAILABLE = False
    ComponentSearchTool = None
    logging.warning(f"ComponentSearchTool not available: {e}. Agent will use LLM fallback for component recommendations.")

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
        # Only add search tool if ComponentSearchTool is available
        tools = [GENERATE_REQUIREMENTS_TOOL]
        if COMPONENT_SEARCH_AVAILABLE:
            tools.append(SEARCH_COMPONENTS_TOOL)

        super().__init__(
            phase_number="P1",
            phase_name="Requirements Capture",
            model=settings.primary_model,
            tools=tools,
            max_tokens=8192,
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

        # Define tool handlers (only add search_components if available)
        tool_handlers = {
            "generate_requirements": None,  # Special handling below
        }

        if COMPONENT_SEARCH_AVAILABLE and self.component_search:
            tool_handlers["search_components"] = self._handle_search_components

        # Call Claude with tool support
        response = await self.call_llm_with_tools(
            messages=messages,
            system=system,
            tool_handlers=tool_handlers,
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
                        "response": response.get("content", "") + "\n\n✅ Phase 1 complete! All requirements documents have been generated.",
                        "phase_complete": True,
                        "outputs": outputs,
                        "parameters": tc["input"].get("design_parameters", {}),
                    }

        # Smart fallback: Check if response contains complete requirements without tool call
        # (for models like GLM-4 that don't support Claude-style tool calling)
        response_content = response.get("content", "")
        if self._detect_complete_requirements(response_content):
            self.log("Detected complete requirements in response (tool call not used)", "info")
            # Parse the response and generate output files
            parsed_data = self._parse_requirements_response(response_content, project_context.get("name", "project"))
            if parsed_data:
                outputs = self._generate_output_files(
                    parsed_data,
                    project_context.get("output_dir", "output"),
                    project_context.get("name", "project"),
                )
                return {
                    "response": response_content + "\n\n✅ Phase 1 complete! All requirements documents have been generated.",
                    "phase_complete": True,
                    "outputs": outputs,
                    "parameters": parsed_data.get("design_parameters", {}),
                }

        # Normal conversation response
        return {
            "response": response_content,
            "phase_complete": False,
            "outputs": {},
            "parameters": {},
        }

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
                        "similarity_score": r.similarity_score,
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

    def _detect_complete_requirements(self, response_content: str) -> bool:
        """
        Detect if the response contains a complete requirements document.
        This is a fallback for models that don't support tool calling (e.g., GLM-4).
        """
        # Look for key indicators of a complete requirements document
        indicators = [
            # Requirement IDs present
            bool(re.search(r'REQ-HW-\d+', response_content, re.IGNORECASE)),
            # Hardware requirements header
            'hardware requirements' in response_content.lower(),
            'requirements document' in response_content.lower(),
            # Project summary section
            'project summary' in response_content.lower(),
            # Design parameters table
            'design parameters' in response_content.lower() or 'parameter' in response_content.lower(),
            # Component recommendations
            'component recommendations' in response_content.lower() or 'component' in response_content.lower(),
            # Next steps or conclusion phrases
            any(phrase in response_content.lower() for phrase in [
                'next steps', 'phase complete', 'requirements captured',
                'would you like me to', 'shall i proceed'
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
                    priority = "shall"
                    if "should" in context.lower():
                        priority = "should"
                    elif "may" in context.lower():
                        priority = "may"

                    requirements.append({
                        "req_id": req_id,
                        "category": "functional",
                        "title": title,
                        "description": description,
                        "priority": priority,
                        "verification_method": "test"
                    })

            # Ensure we have at least some requirements
            if len(requirements) < 3:
                # Add default requirements based on conversation
                requirements = [
                    {"req_id": "REQ-HW-001", "category": "functional", "title": "System Functionality",
                     "description": "System shall meet the functional requirements described in the conversation.", "priority": "shall", "verification_method": "test"},
                    {"req_id": "REQ-HW-002", "category": "performance", "title": "Performance Targets",
                     "description": "System shall meet the performance targets specified.", "priority": "shall", "verification_method": "test"},
                    {"req_id": "REQ-HW-003", "category": "environmental", "title": "Environmental Conditions",
                     "description": "System shall operate within the specified environmental conditions.", "priority": "shall", "verification_method": "test"},
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
                    "primary_part": "TBD",
                    "primary_manufacturer": "TBD",
                    "primary_description": "Primary controller to be selected based on final requirements.",
                    "primary_key_specs": {},
                    "alternatives": [],
                    "selection_rationale": "To be selected in detailed design phase."
                }
            ]

        return components
