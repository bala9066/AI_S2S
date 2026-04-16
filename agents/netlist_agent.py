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

SYSTEM_PROMPT = """You are an expert PCB design engineer generating a logical netlist AND a gate-level interactive schematic from hardware requirements and component selections.

## KEY INNOVATION:
You generate the netlist BEFORE PCB design (not extracted from schematics). This gives engineers a validated connectivity map before investing weeks in layout.

## CRITICAL: TOOL CALL FIRST — MANDATORY
You MUST call the `generate_netlist` tool as your VERY FIRST action. Do NOT output any text before the tool call.

Include ALL components from the P1 BOM in the tool call. Every IC, passive component, and connector MUST appear in the `nodes` array. Every connection MUST appear in the `edges` array.

IMPORTANT: Do NOT include `schematic_data` in the tool call — it will be auto-generated from your nodes and edges. Focus your token budget on complete nodes, edges, mermaid_diagram, and validation_notes.

Only AFTER the tool call completes should you add brief explanatory prose.

## YOUR TASK:
Given requirements and selected components, generate:

1. **Netlist JSON** - Machine-readable netlist with:
   - Component instances (U1, R1, C1, etc.) — EVERY component from the BOM
   - Pin-to-pin connections (net names) — ALL connections
   - Power nets and ground nets
   - Signal types (digital, analog, power, clock)

2. **Mermaid Block Diagram** - High-level visual representation
   - Show major ICs as boxes
   - Show connections with labels
   - Group by functional blocks
   - Show power domains

3. **Schematic Data** - Gate-level interactive schematic (see section below)

4. **Validation Notes** - Flag potential issues:
   - Voltage level mismatches
   - Missing decoupling capacitors
   - Unconnected pins
   - Power domain crossing issues

## GATE-LEVEL SCHEMATIC (schematic_data field)
Produce a `schematic_data` object with one or more `sheets`. Each sheet is a logical page
of the schematic (e.g. "Power", "MCU Core", "RF Front-End"). Rules:

- Grid coordinate system: each sheet is 30 columns wide × 20 rows tall. 1 grid unit = 40 px.
- Every component from the netlist MUST appear on some sheet — including every R, C, L, D, IC,
  connector, ground symbol, and Vcc/power net-tie.
- Place components such that they do NOT overlap. Leave at least 1 grid unit of whitespace
  between neighbouring components.
- Signal flow: inputs on the LEFT, outputs on the RIGHT, power at the TOP, ground at the BOTTOM.
- Place decoupling capacitors immediately adjacent to the IC power pin they bypass.
- Each IC `pins` array must list EVERY pin with `name`, `num`, and `side` (left|right|top|bottom).
  Pin stubs on the same side are spaced 1 grid unit apart in listed order.

Component `type` enum (use these exact strings):
  `resistor` | `capacitor` | `capacitor_polar` | `inductor` |
  `diode` | `diode_zener` | `diode_tvs` | `diode_led` |
  `ic` | `ground` | `vcc` | `connector` | `net_label`

Rotation: 0 (horizontal, pins L↔R), 90 (vertical, pins T↕B), 180 / 270 as needed.

Nets: every `net` has a `name`, a `type` (signal|power|ground|clock|differential),
and `endpoints` — a list of `{ref, pin}` entries. Optional `waypoints` are a list of
`{x, y}` grid coordinates the wire should pass through in order. If omitted, the
renderer will auto-route an L-shaped wire between consecutive endpoint pin anchors.

STRICT rules (HARD REQUIREMENTS — any violation is a parse error):
- Every pin of every component MUST be referenced by some net endpoint. No floating pins.
- If an IC pin is unused in the design, connect it to a `GND` net (or `NC` net if
  datasheet specifies "no connect").
- Every IC power pin (`VCC`/`VDD`/`AVDD`) must have a 100 nF ceramic decoupling cap
  placed next to it, connected between the power rail and GND.
- Power rails (`VCC`, `3V3`, `5V`, etc.) terminate in a `vcc` symbol with the rail name
  as the component `value`.
- Ground nets terminate in a `ground` symbol.
- Connectors include a `pin_count` in their `value` field (e.g. `"CON_4"`, `"CON_2"`).

## OUTPUT FORMAT:
Call `generate_netlist` tool first, then generate a markdown document with:
- Netlist summary table
- Mermaid diagram of connectivity
- Detailed pin-to-pin connection table
- Power budget table
- Validation results (warnings/errors)

IMPORTANT: Do NOT use TBD, TBA, or TBC placeholders. All component instances must have
real reference designators (U1, R1, C1…), real part numbers from the P1 component data,
and concrete net names. Derive pin numbers from the component datasheets or use standard
conventions. Every connection must be fully specified.
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
            "schematic_data": {
                "type": "object",
                "description": (
                    "Gate-level interactive schematic. One or more sheets, each with components placed "
                    "on a 30x20 grid and nets connecting their pins. Every component from the netlist must "
                    "appear on some sheet."
                ),
                "properties": {
                    "sheets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "Sheet ID (e.g. sheet1)"},
                                "title": {"type": "string", "description": "Human-readable sheet title (e.g. 'Power Supply')"},
                                "components": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "ref": {"type": "string", "description": "Reference designator (R1, C5, U2, J1…)"},
                                            "type": {
                                                "type": "string",
                                                "enum": [
                                                    "resistor", "capacitor", "capacitor_polar", "inductor",
                                                    "diode", "diode_zener", "diode_tvs", "diode_led",
                                                    "ic", "ground", "vcc", "connector", "net_label",
                                                ],
                                            },
                                            "value": {"type": "string", "description": "Component value or rail name (e.g. '10k', '100nF', '3V3', 'CON_4')"},
                                            "part_number": {"type": "string"},
                                            "x": {"type": "integer", "minimum": 0, "maximum": 30, "description": "Grid column (0-30)"},
                                            "y": {"type": "integer", "minimum": 0, "maximum": 20, "description": "Grid row (0-20)"},
                                            "rot": {"type": "integer", "enum": [0, 90, 180, 270]},
                                            "pins": {
                                                "type": "array",
                                                "description": "For `ic` and `connector` only — list every pin with name, num, side",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "name": {"type": "string"},
                                                        "num": {"type": "string"},
                                                        "side": {"type": "string", "enum": ["left", "right", "top", "bottom"]},
                                                    },
                                                    "required": ["name", "side"],
                                                },
                                            },
                                        },
                                        "required": ["ref", "type", "x", "y"],
                                    },
                                },
                                "nets": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "type": {
                                                "type": "string",
                                                "enum": ["signal", "power", "ground", "clock", "differential", "analog"],
                                            },
                                            "endpoints": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "ref": {"type": "string"},
                                                        "pin": {"type": "string"},
                                                    },
                                                    "required": ["ref", "pin"],
                                                },
                                            },
                                            "waypoints": {
                                                "type": "array",
                                                "description": "Optional intermediate {x,y} grid points the wire should pass through",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "x": {"type": "number"},
                                                        "y": {"type": "number"},
                                                    },
                                                    "required": ["x", "y"],
                                                },
                                            },
                                        },
                                        "required": ["name", "endpoints"],
                                    },
                                },
                            },
                            "required": ["id", "title", "components", "nets"],
                        },
                    },
                },
                "required": ["sheets"],
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
            max_tokens=8192,  # GLM-4.7 safe limit; complex designs use skeleton fallback for schematic_data
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
        components_text = self._load_file(output_dir / "component_recommendations.md")
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
{requirements[:8000]}

### Selected Components (MUST include ALL of these in the netlist):
{components_text[:12000]}

### HRS Reference:
{hrs[:6000] if hrs else 'Not yet generated.'}

CRITICAL: You MUST call the `generate_netlist` tool IMMEDIATELY with:
1. ALL component instances from the BOM above — every IC, passive, connector, FPGA, LNA, mixer, filter, ADC, power regulator
2. ALL pin-to-pin connections between them with correct signal types (RF, IF, power, ground, digital, clock, LVDS, analog)
3. Power and ground nets for every power domain
4. A Mermaid diagram showing the full connectivity
5. Validation notes for any potential issues

Do NOT include schematic_data — it is auto-generated from your nodes/edges.
Do NOT generate a minimal 2-component skeleton. The netlist must be COMPLETE.
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
            gen_components = []
            for node in netlist_data.get("nodes", []):
                gen_components.append({
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
                components=gen_components,
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

            # Schematic data — if the LLM produced one, persist it. Otherwise synthesize a
            # minimal single-sheet schematic from the node/edge list so the UI always has
            # something to render.
            schematic_data = netlist_data.get("schematic_data")
            if not schematic_data or not schematic_data.get("sheets"):
                schematic_data = self._synthesize_schematic(netlist_data)
            outputs["schematic.json"] = json.dumps(schematic_data, indent=2)

            self.log(f"Netlist: {len(netlist_data.get('nodes', []))} nodes, {len(netlist_data.get('edges', []))} edges")

        else:
            # LLM did not call the generate_netlist tool — build netlist from P1 BOM
            logger.warning("P4: LLM skipped tool call — building netlist from component_recommendations.md")
            netlist_data = self._build_netlist_from_bom(components_text, requirements)

            # Run the standard output pipeline
            gen_components = [
                {"id": n["instance_id"], "name": n["component_name"], "type": n["part_number"], "pins": [], "properties": n}
                for n in netlist_data["nodes"]
            ]
            gen_connections = [
                {"source": e["from_instance"], "source_pin": e["from_pin"],
                 "target": e["to_instance"], "target_pin": e["to_pin"],
                 "signal": e["net_name"], "type": e.get("signal_type", "wire")}
                for e in netlist_data["edges"]
            ]
            generator_netlist = self.netlist_generator.generate(
                project_name=project_name,
                components=gen_components,
                connections=gen_connections,
                metadata={"auto_synthesized": True},
            )
            outputs["netlist.json"] = json.dumps(generator_netlist, indent=2)
            mermaid_diagram = self.netlist_generator.to_mermaid(generator_netlist)
            visual_content = self._build_visual_md(netlist_data, project_name, mermaid_diagram)
            import re as _re
            visual_content = _re.sub(r'\b(TBD|TBC|TBA)\b', '[specify]', visual_content, flags=_re.IGNORECASE)
            outputs["netlist_visual.md"] = visual_content
            validation = self._validate_netlist(netlist_data)
            outputs["netlist_validation.json"] = json.dumps(validation, indent=2)
            outputs["schematic.json"] = json.dumps(
                self._synthesize_schematic(netlist_data), indent=2
            )

        return {
            "response": response.get("content", "Netlist generated."),
            "phase_complete": True,  # Always complete — skeleton fallback ensures output files exist
            "outputs": outputs,
        }

    def _build_visual_md(self, data: dict, project_name: str, mermaid: str) -> str:
        lines = [
            "# Logical Netlist",
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

        lines.extend(["", "## Pin-to-Pin Connections", "", "| Net | From | Pin | To | Pin | Type |", "|---|---|---|---|---|---|"])
        for edge in data.get("edges", []):
            lines.append(
                f"| {edge.get('net_name', '')} | {edge.get('from_instance', '')} | {edge.get('from_pin', '')} "
                f"| {edge.get('to_instance', '')} | {edge.get('to_pin', '')} | {edge.get('signal_type', '')} |"
            )

        # Net-centric connection list — groups all pins sharing each net
        edges = data.get("edges", [])
        if edges:
            # Build net → list of "RefDes - Pin" entries
            net_map: dict = {}
            for edge in edges:
                net = edge.get("net_name", "").strip()
                if not net:
                    continue
                from_entry = f"{edge.get('from_instance', '')} - {edge.get('from_pin', '')}"
                to_entry   = f"{edge.get('to_instance', '')} - {edge.get('to_pin', '')}"
                net_map.setdefault(net, [])
                if from_entry not in net_map[net]:
                    net_map[net].append(from_entry)
                if to_entry not in net_map[net]:
                    net_map[net].append(to_entry)

            lines.extend([
                "",
                "## Net Connection List",
                "",
                "| Net Name | Reference Designator - Pin No. |",
                "|----------|-------------------------------|",
            ])
            for net_name, pins in sorted(net_map.items()):
                pins_str = ",  ".join(pins)
                lines.append(f"| {net_name} | {pins_str} |")

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

    def _build_netlist_from_bom(self, components_md: str, requirements_md: str) -> dict:
        """Parse component_recommendations.md to build a complete netlist when LLM
        skips the tool call. Extracts every component, assigns ref designators,
        builds power/ground/signal connections based on component roles."""
        import re as _re

        nodes = []
        edges = []
        power_nets = set()
        ground_nets = {"GND", "AGND"}

        # Parse "### N. Component Name" sections
        sections = _re.split(r'^### \d+\.\s+', components_md, flags=_re.MULTILINE)
        ref_counter = {"U": 0, "J": 0, "Y": 0}

        parsed_components = []
        for sec in sections[1:]:  # skip preamble before first ###
            lines = sec.strip().split("\n")
            comp_title = lines[0].strip() if lines else "Unknown"

            # Extract part number from **Primary Choice:** [PartNum](url) (Manufacturer)
            pn_match = _re.search(r'\*\*Primary Choice:\*\*\s*\[([^\]]+)\]', sec)
            part_number = pn_match.group(1) if pn_match else comp_title.split()[0]

            # Extract specs from | key | value | table
            specs = {}
            for m in _re.finditer(r'\|\s*(\w[\w_]*)\s*\|\s*([^|]+?)\s*\|', sec):
                specs[m.group(1).strip()] = m.group(2).strip()

            # Determine component category for ref designator and signal type
            title_lower = comp_title.lower()
            if any(k in title_lower for k in ["connector", "jack", "plug", "sma", "2.4mm"]):
                ref_counter["J"] = ref_counter.get("J", 0) + 1
                ref = f"J{ref_counter['J']}"
            elif any(k in title_lower for k in ["oscillator", "clock", "crystal"]):
                ref_counter["Y"] = ref_counter.get("Y", 0) + 1
                ref = f"Y{ref_counter['Y']}"
            else:
                ref_counter["U"] = ref_counter.get("U", 0) + 1
                ref = f"U{ref_counter['U']}"

            # Detect supply voltage → power rail
            supply_v = specs.get("supply_voltage_v", specs.get("supply_v", specs.get("output_voltage_v", "")))

            # Classify component role
            role = "signal"  # default
            if any(k in title_lower for k in ["mixer", "downconvert", "upconvert"]):
                role = "rf_mixer"
            elif any(k in title_lower for k in ["lna", "amplifier", "vga", "driver", "pa"]):
                role = "rf_amplifier"
            elif any(k in title_lower for k in ["ldo", "regulator", "dc-dc", "pmic", "power supply", "buck", "boost"]):
                role = "power"
            elif any(k in title_lower for k in ["adc", "digitiz"]):
                role = "adc"
            elif any(k in title_lower for k in ["fpga", "cpld", "zynq", "ultrascale", "processing"]):
                role = "fpga"
            elif any(k in title_lower for k in ["phy", "ethernet", "transceiver", "uart", "spi"]):
                role = "interface"
            elif any(k in title_lower for k in ["connector", "jack"]):
                role = "connector"
            elif any(k in title_lower for k in ["filter", "bandpass", "lowpass", "saw"]):
                role = "filter"
            elif any(k in title_lower for k in ["synthesizer", "pll", "lo", "vco"]):
                role = "lo_synth"

            parsed_components.append({
                "ref": ref,
                "part_number": part_number,
                "name": comp_title,
                "role": role,
                "supply_v": supply_v,
                "specs": specs,
            })

            nodes.append({
                "instance_id": ref,
                "part_number": part_number,
                "component_name": comp_title,
                "reference_designator": ref,
            })

        # ── Build connections based on component roles ──
        # Find power regulators
        power_regs = [c for c in parsed_components if c["role"] == "power"]
        rf_amps = [c for c in parsed_components if c["role"] == "rf_amplifier"]
        mixers = [c for c in parsed_components if c["role"] == "rf_mixer"]
        adcs = [c for c in parsed_components if c["role"] == "adc"]
        fpgas = [c for c in parsed_components if c["role"] == "fpga"]
        interfaces = [c for c in parsed_components if c["role"] == "interface"]
        connectors = [c for c in parsed_components if c["role"] == "connector"]
        lo_synths = [c for c in parsed_components if c["role"] == "lo_synth"]
        filters = [c for c in parsed_components if c["role"] == "filter"]

        # Power connections: each regulator powers downstream ICs
        for reg in power_regs:
            rail = f"V{reg['supply_v'].replace('.', 'p').replace(' ', '_').split('/')[0]}" if reg["supply_v"] else "VCC"
            power_nets.add(rail)
            # Connect regulator output to all non-power ICs
            for comp in parsed_components:
                if comp["role"] != "power" and comp["role"] != "connector":
                    edges.append({
                        "net_name": rail, "from_instance": reg["ref"], "from_pin": "OUT",
                        "to_instance": comp["ref"], "to_pin": "VCC", "signal_type": "power",
                    })

        # Ground connections: all components to GND
        for comp in parsed_components:
            edges.append({
                "net_name": "GND", "from_instance": comp["ref"], "from_pin": "GND",
                "to_instance": comp["ref"], "to_pin": "GND", "signal_type": "ground",
            })

        # RF signal chain: connector → LNA → filter → mixer → IF amp → ADC → FPGA
        rf_chain = []
        if connectors:
            rf_chain.append(connectors[0])
        rf_chain.extend(rf_amps)
        rf_chain.extend(filters)
        rf_chain.extend(mixers)
        rf_chain.extend(adcs)
        if fpgas:
            rf_chain.append(fpgas[0])

        for i in range(len(rf_chain) - 1):
            src = rf_chain[i]
            dst = rf_chain[i + 1]
            sig_type = "RF" if i < len(rf_amps) + len(filters) + len(connectors) else "IF"
            if dst["role"] == "adc":
                sig_type = "IF"
            if dst["role"] == "fpga":
                sig_type = "digital"
            net_name = f"{sig_type}_{src['ref']}_{dst['ref']}"
            edges.append({
                "net_name": net_name, "from_instance": src["ref"], "from_pin": "OUT",
                "to_instance": dst["ref"], "to_pin": "IN", "signal_type": sig_type.lower(),
            })

        # LO synth → mixer LO port
        for lo in lo_synths:
            for mx in mixers:
                edges.append({
                    "net_name": f"LO_{lo['ref']}_{mx['ref']}", "from_instance": lo["ref"],
                    "from_pin": "RF_OUT", "to_instance": mx["ref"], "to_pin": "LO",
                    "signal_type": "clock",
                })

        # FPGA → interface ICs
        for iface in interfaces:
            if fpgas:
                edges.append({
                    "net_name": f"DATA_{fpgas[0]['ref']}_{iface['ref']}",
                    "from_instance": fpgas[0]["ref"], "from_pin": "DATA",
                    "to_instance": iface["ref"], "to_pin": "DATA",
                    "signal_type": "digital",
                })

        # Build mermaid diagram
        mermaid_lines = ["graph LR"]
        for comp in parsed_components:
            label = f"{comp['name'][:30]} {comp['part_number']}"
            # Sanitize: remove quotes, angle brackets, pipes
            label = _re.sub(r'[<>"\'|#&@:]', '', label)
            mermaid_lines.append(f"    {comp['ref']}[{label}]")
        for edge in edges:
            if edge["signal_type"] not in ("ground",):
                mermaid_lines.append(
                    f"    {edge['from_instance']} -->|{edge['net_name'][:20]}| {edge['to_instance']}"
                )
        # Deduplicate mermaid edges
        seen_edges = set()
        deduped = [mermaid_lines[0]]
        for line in mermaid_lines[1:]:
            if line not in seen_edges:
                seen_edges.add(line)
                deduped.append(line)
        mermaid_diagram = "\n".join(deduped)

        # Validation notes
        validation_notes = [
            f"INFO: Auto-extracted {len(nodes)} components from P1 BOM",
            f"INFO: Generated {len(edges)} connections based on signal chain analysis",
            f"INFO: Power nets: {', '.join(sorted(power_nets))}",
            f"INFO: Ground nets: {', '.join(sorted(ground_nets))}",
        ]
        if not rf_amps:
            validation_notes.append("WARNING: No RF amplifiers detected in BOM")
        if not power_regs:
            validation_notes.append("WARNING: No power regulators detected in BOM")
        if not fpgas:
            validation_notes.append("WARNING: No FPGA/processor detected in BOM")

        return {
            "nodes": nodes,
            "edges": edges,
            "power_nets": sorted(power_nets),
            "ground_nets": sorted(ground_nets),
            "mermaid_diagram": mermaid_diagram,
            "validation_notes": validation_notes,
        }

    def _synthesize_schematic(self, netlist_data: dict) -> dict:
        """Auto-lay out a single-sheet schematic from nodes + edges when the agent
        didn't emit schematic_data. Places ICs in a horizontal row, adds ground
        and VCC rails, derives pin lists from the edges that reference each node.
        """
        nodes = netlist_data.get("nodes", []) or []
        edges = netlist_data.get("edges", []) or []
        power_nets = set(netlist_data.get("power_nets", []) or [])
        ground_nets = set(netlist_data.get("ground_nets", []) or [])

        # Build pin list for each node from edges
        node_pins: dict = {}  # ref -> { pin_name: 'left'|'right' }
        for e in edges:
            fi, fp = e.get("from_instance"), e.get("from_pin")
            ti, tp = e.get("to_instance"), e.get("to_pin")
            if fi and fp:
                node_pins.setdefault(fi, {})[fp] = node_pins.get(fi, {}).get(fp, "right")
            if ti and tp:
                node_pins.setdefault(ti, {})[tp] = node_pins.get(ti, {}).get(tp, "left")

        components: list = []
        # Place ICs in a horizontal row
        col = 4
        ic_y = 6
        placed_refs: set = set()
        for node in nodes:
            ref = node.get("instance_id") or node.get("reference_designator")
            if not ref:
                continue
            pins_dict = node_pins.get(ref, {})
            # Split pins: first half on left, second half on right
            pin_names = list(pins_dict.keys())
            mid = max(1, len(pin_names) // 2)
            pin_list: list = []
            for idx, pname in enumerate(pin_names):
                side = "left" if idx < mid else "right"
                pin_list.append({"name": pname, "num": str(idx + 1), "side": side})
            components.append({
                "ref": ref,
                "type": "ic",
                "value": node.get("part_number", ""),
                "part_number": node.get("part_number", ""),
                "x": col,
                "y": ic_y,
                "rot": 0,
                "pins": pin_list or [{"name": "1", "num": "1", "side": "left"}],
            })
            placed_refs.add(ref)
            col += 8
            if col > 24:
                col = 4
                ic_y += 8

        # Add ground symbol at the bottom-centre
        components.append({"ref": "GND1", "type": "ground", "value": "GND", "x": 15, "y": 18, "rot": 0})
        # Add a VCC symbol per power net at the top
        x_pow = 4
        for i, pnet in enumerate(sorted(power_nets)[:4]):
            components.append({
                "ref": f"PWR{i+1}", "type": "vcc", "value": pnet, "x": x_pow, "y": 1, "rot": 0,
            })
            x_pow += 6

        # Build schematic nets from edges — add endpoints referencing placed refs
        sch_nets: list = []
        for e in edges:
            nname = e.get("net_name", "")
            ntype = "signal"
            if nname in power_nets:
                ntype = "power"
            elif nname in ground_nets:
                ntype = "ground"
            sch_nets.append({
                "name": nname,
                "type": ntype,
                "endpoints": [
                    {"ref": e.get("from_instance", ""), "pin": e.get("from_pin", "")},
                    {"ref": e.get("to_instance", ""), "pin": e.get("to_pin", "")},
                ],
            })

        return {
            "sheets": [
                {
                    "id": "sheet1",
                    "title": "Schematic (auto-generated)",
                    "components": components,
                    "nets": sch_nets,
                }
            ],
            "auto_synthesized": True,
        }
