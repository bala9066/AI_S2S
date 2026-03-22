"""
Phase 4: Logical Netlist Generation Agent (KEY INNOVATION)

Generates netlist BEFORE PCB design using AI + NetworkX validation.
This is the core differentiator of Hardware Pipeline.
"""

import json
import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from config import settings
from generators.netlist_generator import NetlistGenerator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert PCB design engineer generating a logical netlist from hardware requirements and component selections.

## KEY INNOVATION:
You generate the netlist BEFORE PCB design (not extracted from schematics). This gives engineers a validated connectivity map before investing weeks in layout.

## YOUR TASK:
Given requirements and selected components, generate:

1. **Netlist JSON** - Machine-readable netlist with:
   - Component instances (U1, R1, C1, etc.)
   - Pin-to-pin connections (net names)
   - Power nets and ground nets
   - Signal types (digital, analog, power, clock)

2. **Mermaid Block Diagram** - Visual representation of the netlist
   - Show major ICs as boxes
   - Show connections with labels
   - Group by functional blocks
   - Show power domains

3. **Validation Notes** - Flag potential issues:
   - Voltage level mismatches
   - Missing decoupling capacitors
   - Unconnected pins
   - Power domain crossing issues

## OUTPUT FORMAT:
Generate a markdown document with:
- Netlist summary table
- Mermaid diagram of connectivity
- Detailed pin-to-pin connection table
- Power budget table
- Validation results (warnings/errors)

Use the `generate_netlist` tool to output the structured data.
"""

GENERATE_NETLIST_TOOL = {
    "name": "generate_netlist",
    "description": "Generate structured netlist data with component instances and connections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "description": "Component instances in the netlist",
                "items": {
                    "type": "object",
                    "properties": {
                        "instance_id": {"type": "string"},
                        "part_number": {"type": "string"},
                        "component_name": {"type": "string"},
                        "reference_designator": {"type": "string"},
                    },
                    "required": ["instance_id", "part_number", "component_name"],
                },
            },
            "edges": {
                "type": "array",
                "description": "Pin-to-pin connections",
                "items": {
                    "type": "object",
                    "properties": {
                        "net_name": {"type": "string"},
                        "from_instance": {"type": "string"},
                        "from_pin": {"type": "string"},
                        "to_instance": {"type": "string"},
                        "to_pin": {"type": "string"},
                        "signal_type": {"type": "string"},
                    },
                    "required": ["net_name", "from_instance", "from_pin", "to_instance", "to_pin"],
                },
            },
            "power_nets": {"type": "array", "items": {"type": "string"}},
            "ground_nets": {"type": "array", "items": {"type": "string"}},
            "mermaid_diagram": {"type": "string"},
            "validation_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["nodes", "edges", "mermaid_diagram"],
    },
}


class NetlistAgent(BaseAgent):
    """Phase 4: Logical netlist generation before PCB design."""

    def __init__(self):
        super().__init__(
            phase_number="P4",
            phase_name="Netlist Generation",
            model=settings.primary_model,  # Opus for complex reasoning
            tools=[GENERATE_NETLIST_TOOL],
            max_tokens=8192,
        )
        self.netlist_generator = NetlistGenerator()

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")

        # Load prior phase outputs
        requirements = self._load_file(output_dir / "requirements.md")
        components = self._load_file(output_dir / "component_recommendations.md")
        hrs = self._load_file(output_dir / f"HRS_{project_name.replace(' ', '_')}.md")

        if not requirements:
            return {
                "response": "Requirements not found. Complete Phase 1 first.",
                "phase_complete": False,
                "outputs": {},
            }

        user_message = f"""Generate a complete logical netlist for:

**Project:** {project_name}

### Requirements:
{requirements[:4000]}

### Selected Components:
{components[:4000]}

### HRS Reference:
{hrs[:3000] if hrs else 'Not yet generated.'}

Generate the netlist using the generate_netlist tool. Include:
1. All component instances with reference designators
2. All pin-to-pin connections
3. Power and ground nets
4. A Mermaid diagram showing the connectivity
5. Validation notes for any potential issues
"""

        response = await self.call_llm(
            messages=[{"role": "user", "content": user_message}],
            system=self.get_system_prompt(project_context),
        )

        outputs = {}
        netlist_data = None

        # Process tool calls
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc["name"] == "generate_netlist":
                    netlist_data = tc["input"]

        if netlist_data:
            # Transform tool call data to generator format
            components = []
            for node in netlist_data.get("nodes", []):
                components.append({
                    "id": node.get("instance_id", ""),
                    "name": node.get("component_name", ""),
                    "type": node.get("part_number", ""),
                    "pins": [],
                    "properties": node,
                })

            connections = []
            for edge in netlist_data.get("edges", []):
                connections.append({
                    "source": edge.get("from_instance", ""),
                    "source_pin": edge.get("from_pin", ""),
                    "target": edge.get("to_instance", ""),
                    "target_pin": edge.get("to_pin", ""),
                    "signal": edge.get("net_name", ""),
                    "type": edge.get("signal_type", "wire"),
                })

            # Use NetlistGenerator to create structured netlist
            generator_netlist = self.netlist_generator.generate(
                project_name=project_name,
                components=components,
                connections=connections,
                metadata=netlist_data.get("metadata", {}),
            )

            # Build outputs through the dict — write_outputs in pipeline_service
            # handles the actual file writes via StorageAdapter (single write path).
            outputs["netlist.json"] = json.dumps(generator_netlist, indent=2)

            # Generate visual markdown with full component/connection tables
            mermaid_diagram = self.netlist_generator.to_mermaid(generator_netlist)
            visual_content = self._build_visual_md(netlist_data, project_name, mermaid_diagram)
            outputs["netlist_visual.md"] = visual_content

            # Run NetworkX validation — always store as JSON string (not dict)
            validation = self._validate_netlist(netlist_data)
            outputs["netlist_validation.json"] = json.dumps(validation, indent=2)

            self.log(f"Netlist: {len(netlist_data.get('nodes', []))} nodes, {len(netlist_data.get('edges', []))} edges")

        else:
            # LLM did not call the generate_netlist tool — produce a fallback
            # document so the phase is never silently "completed" with no output.
            logger.warning("P4: generate_netlist tool was not called — using fallback")
            fallback_md = (
                f"# Logical Netlist — {project_name}\n\n"
                "**Status:** Netlist generation could not be completed automatically.\n\n"
                "The AI model did not return structured netlist data. "
                "Please re-run Phase 4 or verify that Phase 1 requirements are sufficiently detailed.\n\n"
                "## LLM Response\n\n"
                f"{response.get('content', '(no response)')}\n"
            )
            outputs["netlist_visual.md"] = fallback_md

        return {
            "response": response.get("content", "Netlist generated."),
            "phase_complete": bool(netlist_data),
            "outputs": outputs,
        }

    def _build_visual_md(self, data: dict, project_name: str, mermaid: str) -> str:
        lines = [
            f"# Logical Netlist",
            f"## {project_name}",
            "",
            "## Block Diagram",
            "",
            f"```mermaid\n{mermaid}\n```",
            "",
            "## Component Instances",
            "",
            "| Ref | Part Number | Component |",
            "|---|---|---|",
        ]
        for node in data.get("nodes", []):
            lines.append(f"| {node.get('instance_id', '')} | {node.get('part_number', '')} | {node.get('component_name', '')} |")

        lines.extend(["", "## Connections", "", "| Net | From | Pin | To | Pin | Type |", "|---|---|---|---|---|---|"])
        for edge in data.get("edges", []):
            lines.append(
                f"| {edge.get('net_name', '')} | {edge.get('from_instance', '')} | {edge.get('from_pin', '')} "
                f"| {edge.get('to_instance', '')} | {edge.get('to_pin', '')} | {edge.get('signal_type', '')} |"
            )

        # Validation notes
        notes = data.get("validation_notes", [])
        if notes:
            lines.extend(["", "## Validation Notes", ""])
            for note in notes:
                lines.append(f"- {note}")

        return "\n".join(lines)

    def _validate_netlist(self, data: dict) -> dict:
        """Basic netlist validation using NetworkX."""
        try:
            import networkx as nx

            G = nx.DiGraph()
            for node in data.get("nodes", []):
                G.add_node(node["instance_id"], **node)
            for edge in data.get("edges", []):
                G.add_edge(
                    edge["from_instance"], edge["to_instance"],
                    net_name=edge.get("net_name", ""),
                )

            # Check for isolated nodes
            isolated = list(nx.isolates(G))

            # Check for cycles (shouldn't exist in most designs)
            cycles = list(nx.simple_cycles(G))

            return {
                "total_nodes": G.number_of_nodes(),
                "total_edges": G.number_of_edges(),
                "isolated_nodes": isolated,
                "cycles": [list(c) for c in cycles[:5]],
                "is_connected": nx.is_weakly_connected(G) if G.number_of_nodes() > 0 else False,
            }
        except ImportError:
            return {"error": "NetworkX not installed"}
        except Exception as e:
            return {"error": str(e)}

    def _load_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
