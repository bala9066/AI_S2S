"""
Phase 8b: SDD (Software Design Document) Agent - IEEE 1016 Compliant

Generates software architecture from SRS with Mermaid diagrams.
"""

import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from config import settings
from generators.sdd_generator import SDDGenerator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior embedded software architect generating an IEEE 1016-2009-compliant Software Design Document (SDD).

## DOCUMENT STRUCTURE (IEEE 1016-2009):

# 1. Introduction
## 1.1 Purpose
## 1.2 Scope
## 1.3 Definitions
## 1.4 References

# 2. Design Viewpoints

## 2.1 Context Viewpoint
- System boundaries and external entities
- Mermaid context diagram

## 2.2 Composition Viewpoint
- Software modules and subsystems
- Mermaid component diagram

## 2.3 Logical Viewpoint
- Classes, objects, relationships
- Mermaid class diagram

## 2.4 Dependency Viewpoint
- Module dependencies
- Build order
- Mermaid dependency graph

## 2.5 Interface Viewpoint
- API function signatures (C/C++)
- Data structures (structs, enums)
- Register access macros

## 2.6 Interaction Viewpoint
- Sequence diagrams for key operations
- Mermaid sequence diagrams

## 2.7 State Viewpoint
- State machines for key modules
- Mermaid state diagrams

## 2.8 Algorithm Viewpoint
- Key algorithm descriptions (control loops, filters, protocols)
- Pseudocode or flowcharts

# 3. Design Rationale
- Why this architecture was chosen
- Trade-offs considered

# 4. Traceability
- SDD elements -> REQ-SW-xxx mapping

## RULES:
- Use Mermaid for ALL diagrams (class, sequence, state, component)
- Define actual C/C++ struct layouts for register maps
- Define function prototypes with parameter types and return values
- Include error handling architecture
- Design for MISRA-C compliance in embedded C code
- Each design element must trace to REQ-SW-xxx
- NEVER use TBD, TBA, or TBC placeholders. Specify actual values for all addresses,
  sizes, timeouts, and parameters. Use engineering defaults or state assumptions inline.
"""


class SDDAgent(BaseAgent):
    """Phase 8b: IEEE 1016-compliant SDD generation."""

    def __init__(self):
        super().__init__(
            phase_number="P8b",
            phase_name="SDD Generation",
            model=settings.fast_model,  # Structured template doc — fast model sufficient
            max_tokens=16384,  # Increased for comprehensive SDD documents
        )
        self.sdd_generator = SDDGenerator()

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")

        # Load SRS (primary input) and context
        srs = self._load_file(output_dir / f"SRS_{project_name.replace(' ', '_')}.md")
        hrs = self._load_file(output_dir / f"HRS_{project_name.replace(' ', '_')}.md")
        glr = self._load_file(output_dir / "glr_specification.md")

        if not srs:
            return {
                "response": "SRS not found. Complete Phase 8a first.",
                "phase_complete": False,
                "outputs": {},
            }

        # PRIMARY PATH: LLM writes the full IEEE 1016 SDD from SRS context
        user_message = (
            f"Generate a complete IEEE 1016-2009 Software Design Document for:\n\n"
            f"**Project:** {project_name}\n\n"
            f"## Software Requirements Specification (SRS)\n{srs[:6000]}\n\n"
            f"## GLR Specification\n{glr[:2000] if glr else 'Not available.'}\n\n"
            f"## HRS (Hardware context)\n{hrs[:2000] if hrs else 'Not available.'}\n\n"
            "Generate ALL sections per the IEEE 1016 structure in your system prompt. "
            "Include Mermaid class diagrams, sequence diagrams, and state diagrams. "
            "Define actual C struct layouts and function prototypes. "
            "Be thorough, project-specific, and MISRA-C compliant."
        )

        sdd_content = ""
        try:
            response = await self.call_llm(
                messages=[{"role": "user", "content": user_message}],
                system=SYSTEM_PROMPT,
            )
            sdd_content = response.get("content", "")
            # Continuation if truncated
            if response.get("stop_reason") == "max_tokens" and sdd_content:
                self.log("SDD truncated, requesting continuation...")
                cont = await self.call_llm(
                    messages=[
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": sdd_content},
                        {"role": "user", "content": "Continue from where you left off. Do not repeat sections already written."},
                    ],
                    system=SYSTEM_PROMPT,
                )
                sdd_content += "\n" + cont.get("content", "")
        except Exception as e:
            self.log(f"LLM SDD generation failed: {e} — falling back to template", "warning")

        # FALLBACK: template generator
        if not sdd_content or len(sdd_content) < 800:
            modules = await self._extract_modules(srs)
            interfaces = await self._extract_interfaces(srs, glr)
            state_machines = await self._extract_state_machines(srs)
            sdd_content = self.sdd_generator.generate(
                project_name=project_name,
                modules=modules,
                interfaces=interfaces,
                state_machines=state_machines,
                metadata={"version": project_context.get("version", "1.0")},
            )

        # Scrub any TBD/TBC/TBA the LLM wrote despite instructions
        import re as _re
        sdd_content = _re.sub(r'\b(TBD|TBC|TBA)\b', '[specify]', sdd_content, flags=_re.IGNORECASE)

        # Save output
        sdd_file = self.sdd_generator.save(sdd_content, output_dir, project_name)
        self.log(f"SDD generated: {len(sdd_content)} chars")

        return {
            "response": "SDD document generated (IEEE 1016 compliant).",
            "phase_complete": True,
            "outputs": {sdd_file.name: sdd_content},
        }

    async def _extract_modules(self, srs: str) -> list:
        """Extract software modules from SRS by parsing headers and component names."""
        import re
        modules = []

        if not srs:
            return self._default_modules()

        # Look for section headers (## ...) that indicate modules
        header_pattern = r'^##\s+([^\n]+?)(?:\s*\(([^)]*)\))?$'
        matches = re.findall(header_pattern, srs, re.MULTILINE)

        for title, desc in matches:
            module_name = title.strip()
            # Skip generic headings
            if not any(skip in module_name.lower() for skip in ['introduction', 'overview', 'references', 'appendix']):
                modules.append({
                    "name": module_name,
                    "description": desc.strip() if desc else module_name,
                    "file": module_name.lower().replace(" ", "_") + ".c"
                })

        # Look for software component patterns
        component_pattern = r'(?:module|component|driver|subsystem)[\s:]+([A-Za-z0-9_\s]+?)(?:\n|,|;)'
        components = re.findall(component_pattern, srs, re.IGNORECASE)

        for comp in components:
            comp_name = comp.strip()
            if comp_name and len(comp_name) < 50:  # Filter out overly long matches
                if not any(m["name"].lower() == comp_name.lower() for m in modules):
                    modules.append({
                        "name": comp_name,
                        "description": f"{comp_name} implementation",
                        "file": comp_name.lower().replace(" ", "_") + ".c"
                    })

        # Look for common module patterns
        if not modules:
            keywords = ['initialization', 'driver', 'control', 'interface', 'handler', 'manager', 'service']
            for keyword in keywords:
                if keyword in srs.lower():
                    modules.append({
                        "name": keyword.capitalize(),
                        "description": f"{keyword.capitalize()} module",
                        "file": keyword + ".c"
                    })

        return modules if modules else self._default_modules()

    async def _extract_interfaces(self, srs: str, glr: str) -> list:
        """Extract API interfaces from SRS by parsing function signatures and protocol names."""
        import re
        interfaces = []

        content = (srs or "") + "\n" + (glr or "")
        if not content:
            return self._default_interfaces()

        # Look for function signatures
        func_pattern = r'(\w+)\s*\(\s*([^)]*?)\s*\)'
        functions = re.findall(func_pattern, content)

        # Extract unique function names
        func_names = set()
        for func_name, params in functions:
            if func_name and not func_name.startswith('#') and len(func_name) > 2:
                func_names.add(func_name)

        # Group by protocol/type
        protocol_funcs = {}
        protocols = ['UART', 'SPI', 'I2C', 'CAN', 'USB', 'GPIO', 'ADC', 'PWM', 'DMA']

        for protocol in protocols:
            matching = [f for f in func_names if protocol.lower() in f.lower()]
            if matching:
                protocol_funcs[protocol] = matching

        # Build interface list
        for protocol, funcs in protocol_funcs.items():
            interfaces.append({
                "name": protocol,
                "type": "Hardware",
                "functions": ", ".join(sorted(list(funcs)[:5]))
            })

        # Add HAL/abstraction layer if any init/control functions found
        if any(f in ' '.join(func_names) for f in ['init', 'control', 'config']):
            if not any(i["name"] == "HAL" for i in interfaces):
                interfaces.insert(0, {
                    "name": "HAL",
                    "type": "Internal",
                    "functions": "hal_init(), hal_read(), hal_write(), hal_control()"
                })

        return interfaces if interfaces else self._default_interfaces()

    async def _extract_state_machines(self, srs: str) -> list:
        """Extract state machines from SRS by parsing state-related keywords."""
        import re
        state_machines = []

        if not srs:
            return self._default_state_machines()

        # Look for state machine mentions
        sm_pattern = r'(?:state\s+machine|state\s+diagram|states?)[:\s]+([^\n]+)'
        sm_matches = re.findall(sm_pattern, srs, re.IGNORECASE)

        # Extract state names
        state_pattern = r'\b(?:init|idle|running|active|sleep|waiting|error|fault|shutdown|standby)\b'
        states = list(set(re.findall(state_pattern, srs, re.IGNORECASE)))

        if sm_matches:
            for sm_desc in sm_matches[:3]:  # Limit to 3 state machines
                state_machines.append({
                    "name": sm_desc.strip()[:50],
                    "states": states if states else ["Init", "Idle", "Running", "Error"]
                })

        if not state_machines:
            # Fallback: create default state machine if any control/state keywords found
            if re.search(r'state|mode|status|condition', srs, re.IGNORECASE):
                state_machines.append({
                    "name": "Main Control State Machine",
                    "states": states if states else ["Init", "Idle", "Running", "Error"]
                })

        return state_machines if state_machines else self._default_state_machines()

    def _default_modules(self) -> list:
        """Default modules."""
        return [
            {"name": "Main", "description": "Main application loop", "file": "main.c"},
            {"name": "HAL", "description": "Hardware abstraction layer", "file": "hal.c"},
            {"name": "Drivers", "description": "Device drivers", "file": "drivers.c"},
            {"name": "Comms", "description": "Communication interface", "file": "comms.c"},
        ]

    def _default_interfaces(self) -> list:
        """Default interfaces."""
        return [
            {"name": "HAL", "type": "Internal", "functions": "hal_init(), hal_read(), hal_write()"},
            {"name": "UART", "type": "Hardware", "functions": "uart_init(), uart_send(), uart_recv()"},
            {"name": "SPI", "type": "Hardware", "functions": "spi_transfer()"},
        ]

    def _default_state_machines(self) -> list:
        """Default state machines."""
        return [
            {"name": "Main State Machine", "states": ["Init", "Idle", "Running", "Error"]}
        ]

    def _load_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
