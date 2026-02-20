"""Netlist Generator - Pre-PCB netlist generation with NetworkX."""

import logging
import json
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class NetlistGenerator:
    """Generate netlist from component connectivity specification."""

    def generate(self, project_name: str, components: List[Dict], connections: List[Dict], metadata: Dict = None) -> Dict:
        nodes = []
        edges = []

        for comp in components:
            nodes.append({
                "id": comp.get("id", f"U{len(nodes)+1}"),
                "name": comp.get("name", "Component"),
                "type": comp.get("type", "IC"),
                "pins": comp.get("pins", []),
                "properties": comp.get("properties", {}),
            })

        for conn in connections:
            edges.append({
                "source": conn.get("source"),
                "source_pin": conn.get("source_pin"),
                "target": conn.get("target"),
                "target_pin": conn.get("target_pin"),
                "signal": conn.get("signal", "NET"),
                "type": conn.get("type", "wire"),
            })

        return {
            "project": project_name,
            "version": "1.0",
            "nodes": nodes,
            "edges": edges,
            "metadata": metadata or {},
        }

    def to_mermaid(self, netlist: Dict) -> str:
        lines = ["graph TB"]
        for node in netlist.get("nodes", []):
            lines.append(f"    {node['id']}[{node['name']} ({node['type']})]")
        for edge in netlist.get("edges", []):
            lines.append(f"    {edge['source']} -->|{edge.get('signal', '')}| {edge['target']}")
        return "\n".join(lines)

    def save(self, netlist: Dict, output_dir: Path, project_name: str) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        json_path = output_dir / "netlist.json"
        json_path.write_text(json.dumps(netlist, indent=2), encoding="utf-8")
        
        md_path = output_dir / "netlist_visual.md"
        md_path.write_text(f"```mermaid\n{self.to_mermaid(netlist)}\n```\n", encoding="utf-8")
        
        return json_path
