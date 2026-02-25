"""
Phase 8c: Code Generation + Review Agent

Generates C/C++ drivers, Qt GUI skeleton, tests from SRS+SDD.
Includes automated code review with MISRA-C checking.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent
from config import settings
from generators.driver_generator import DriverGenerator

# Optional import for code reviewer
try:
    from reviewers.code_reviewer import CodeReviewer
    CODE_REVIEWER_AVAILABLE = True
except ImportError:
    CODE_REVIEWER_AVAILABLE = False
    logging.warning("CodeReviewer not available, using LLM-based review only")

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior embedded software engineer generating production-ready C/C++ code from SRS and SDD specifications.

## YOUR TASK:
Generate the following code artifacts:

### 1. Device Drivers (C)
- Register access layer (HAL)
- Driver initialization and configuration
- Interrupt handlers
- DMA transfer functions
- Error handling with error codes
- MISRA-C 2012 compliant

### 2. Qt GUI Application (C++)
- Main window with device status
- Configuration panels
- Real-time data display
- Serial/USB communication handler

### 3. Test Suite
- Unit tests for each driver function
- Integration tests for hardware interaction
- Mock hardware layer for testing without hardware

### 4. Code Review Report
- MISRA-C compliance check results
- Code quality score (0-100)
- Security vulnerability assessment
- Recommendations for improvement

## CODE STANDARDS:
- C11 for drivers, C++17 for GUI
- MISRA-C 2012 for embedded C (no dynamic allocation, no recursion)
- Doxygen comments for all public APIs
- Error handling: return error codes, no exceptions in C
- All functions shall have single entry/exit point
- Maximum cyclomatic complexity: 10

## OUTPUT FORMAT:
Generate each file with its full path and complete content.
Wrap each file in a code block with the filename as a comment.
End with a code_review_report.md containing the quality analysis.
"""


class CodeAgent(BaseAgent):
    """Phase 8c: Code generation + automated review."""

    def __init__(self):
        super().__init__(
            phase_number="P8c",
            phase_name="Code Generation",
            model=settings.primary_model,
            max_tokens=8192,
        )
        self.driver_generator = DriverGenerator()
        if CODE_REVIEWER_AVAILABLE:
            self.code_reviewer = CodeReviewer()
        else:
            self.code_reviewer = None

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")

        # Load SRS and SDD (primary inputs)
        srs = self._load_file(output_dir / f"SRS_{project_name.replace(' ', '_')}.md")
        sdd = self._load_file(output_dir / f"SDD_{project_name.replace(' ', '_')}.md")
        glr = self._load_file(output_dir / "glr_specification.md")

        if not srs or not sdd:
            return {
                "response": "SRS and SDD required. Complete Phases 8a and 8b first.",
                "phase_complete": False,
                "outputs": {},
            }

        # Extract structured data from SRS/SDD/GLR
        components = await self._extract_components(glr)
        registers = await self._extract_registers(glr, srs)

        # Use DriverGenerator to create base code files
        generated_files = self.driver_generator.generate(
            project_name=project_name,
            components=components,
            registers=registers,
            metadata={"srs": srs[:1000], "sdd": sdd[:1000]},
        )

        # Save generated files using generator's save method
        saved_paths = self.driver_generator.save(generated_files, output_dir)

        # Create outputs dict
        outputs = {}
        for path in saved_paths:
            rel_path = path.relative_to(output_dir)
            outputs[str(rel_path)] = path.read_text(encoding="utf-8")

        # Generate code review report using CodeReviewer
        review_report = await self._generate_review_report(generated_files, project_name)
        review_file = output_dir / "code_review_report.md"
        review_file.write_text(review_report, encoding="utf-8")
        outputs["code_review_report.md"] = review_report

        self.log(f"Code generated: {len(outputs)} files")

        return {
            "response": f"Code generation complete. {len(outputs)} files generated with review report.",
            "phase_complete": True,
            "outputs": outputs,
        }

    async def _extract_components(self, glr: str) -> List[Dict]:
        """Extract component information from GLR/netlist content."""
        import re
        components = []

        if not glr:
            return self._default_components()

        # Look for component definitions with types
        # Pattern: Component Type: Name or Component: Name (Type)
        comp_pattern = r'(?:component|device|ic|chip|module)[\s:]+([A-Za-z0-9_\-]+)[\s]*(?:\(([^)]+)\))?'
        matches = re.findall(comp_pattern, glr, re.IGNORECASE)

        for comp_name, comp_type in matches:
            if comp_name:
                components.append({
                    "name": comp_name.strip(),
                    "type": comp_type.strip() if comp_type else "Device",
                    "description": f"{comp_name} component"
                })

        # Look for common IC/chip names
        ic_pattern = r'\b(STM32|ARM|ATMEL|PIC|NXP|TI|Cortex|FPGA|ASIC|MCU|CPU|GPIO|UART|SPI|I2C|ADC|DAC|Sensor)\b'
        ics = set(re.findall(ic_pattern, glr, re.IGNORECASE))

        for ic in ics:
            if not any(c["name"].lower() == ic.lower() for c in components):
                components.append({
                    "name": ic,
                    "type": "IC" if ic in ["STM32", "ARM", "ATMEL", "PIC", "NXP"] else "Peripheral",
                    "description": f"{ic} device"
                })

        # Look for netlist entry patterns
        netlist_pattern = r'U\d+\s+([A-Za-z0-9_\-]+)'
        netlists = re.findall(netlist_pattern, glr)

        for comp_ref in netlists:
            if not any(c["name"].lower() == comp_ref.lower() for c in components):
                components.append({
                    "name": comp_ref,
                    "type": "Component",
                    "description": f"{comp_ref} component"
                })

        return components if components else self._default_components()

    async def _extract_registers(self, glr: str, srs: str) -> List[Dict]:
        """Extract register definitions from GLR/SRS content."""
        import re
        registers = []

        content = (glr or "") + "\n" + (srs or "")
        if not content:
            return self._default_registers()

        # Pattern 1: Register definitions with addresses (0xAA, 0x00AA, etc.)
        reg_pattern = r'(?:register|reg|address|addr)[:\s]+([A-Za-z0-9_]+)[:\s]*(0x[0-9A-Fa-f]+)'
        matches = re.findall(reg_pattern, content, re.IGNORECASE)

        for reg_name, reg_addr in matches:
            registers.append({
                "name": reg_name.strip(),
                "address": reg_addr.lower(),
                "width": 32,  # Default width
                "access": "RW"
            })

        # Pattern 2: Hex addresses without explicit register names
        addr_pattern = r'(0x[0-9A-Fa-f]{2,8})[:\s]*([A-Za-z0-9_]*)'
        addr_matches = re.findall(addr_pattern, content)

        addr_count = {}
        for addr, name in addr_matches:
            if addr not in [r["address"] for r in registers]:
                reg_name = name.strip() if name else f"REG_{addr}"
                if not reg_name:
                    reg_name = f"REG_{addr}"
                    # Track multiple registers at same address
                    if addr in addr_count:
                        addr_count[addr] += 1
                        reg_name += f"_{addr_count[addr]}"
                    else:
                        addr_count[addr] = 0

                registers.append({
                    "name": reg_name,
                    "address": addr.lower(),
                    "width": 8,
                    "access": "RW"
                })

        # Pattern 3: Bit field definitions (for access type detection)
        bitfield_pattern = r'(?:read|write|readonly|readwrite|ro|rw|wo)\s*(?:only|able)?[:\s]*([A-Za-z0-9_]+)'
        bitfield_matches = re.findall(bitfield_pattern, content, re.IGNORECASE)

        # Update access types if we find read/write patterns
        for i, reg in enumerate(registers):
            if 'read' in content.lower() and 'write' in content.lower():
                reg["access"] = "RW"
            elif 'readonly' in content.lower() or 'read' in content.lower():
                reg["access"] = "RO"
            elif 'writeonly' in content.lower() or ('write' in content.lower() and 'read' not in content.lower()):
                reg["access"] = "WO"

        return registers if registers else self._default_registers()

    def _default_components(self) -> List[Dict]:
        """Default components."""
        return [
            {"name": "MCU", "type": "Microcontroller", "description": "Main microcontroller unit"},
            {"name": "Sensor", "type": "Peripheral", "description": "Sensor interface"},
            {"name": "Actuator", "type": "Peripheral", "description": "Actuator control"},
        ]

    def _default_registers(self) -> List[Dict]:
        """Default registers."""
        return [
            {"name": "CTRL_REG", "address": "0x00", "width": 8, "access": "RW"},
            {"name": "STATUS_REG", "address": "0x01", "width": 8, "access": "RO"},
            {"name": "DATA_REG", "address": "0x02", "width": 8, "access": "RW"},
        ]

    async def _generate_review_report(self, generated_files: Dict[str, str], project_name: str) -> str:
        """Generate code review report using CodeReviewer or LLM fallback."""
        try:
            # Combine all generated files for review
            all_code = "\n\n".join([f"// {filename}\n{content}" for filename, content in generated_files.items()])

            # Use CodeReviewer if available
            if self.code_reviewer:
                review_result = self.code_reviewer.review_code(
                    code=all_code,
                    language="c",
                    standards=["MISRA-C-2012"]
                )

                return f"""# Code Review Report

**Project:** {project_name}
**Date:** {review_result.get('timestamp', 'N/A')}

## Summary
- Total Issues Found: {review_result.get('total_issues', 0)}
- Critical: {review_result.get('critical_issues', 0)}
- Warning: {review_result.get('warnings', 0)}
- Info: {review_result.get('info', 0)}

## Findings
{review_result.get('details', 'No details available.')}

## Recommendations
{review_result.get('recommendations', 'No recommendations available.')}
"""
            else:
                # Fallback to LLM-based review
                return await self._llm_review(all_code, project_name)

        except Exception as e:
            self.log(f"Code review failed: {e}", "warning")
            return f"# Code Review Report\n\nReview completed with warnings. Error: {str(e)}"

    async def _llm_review(self, code: str, project_name: str) -> str:
        """Fallback LLM-based code review."""
        review_prompt = f"""Review the following generated C/C++ code for project {project_name}.

Analyze:
1. MISRA-C 2012 compliance (for C code)
2. Code quality score (0-100) with breakdown
3. Security vulnerabilities (buffer overflows, injection, etc.)
4. Coding standards adherence
5. Error handling completeness
6. Documentation quality
7. Specific recommendations for improvement

Code to review:
{code[:8000]}

Output as a structured markdown report with tables for findings.
"""
        try:
            response = await self.call_llm(
                messages=[{"role": "user", "content": review_prompt}],
                system="You are a senior code reviewer specializing in embedded C/C++ and MISRA-C compliance.",
                model=settings.fast_model,
            )
            return f"# Code Review Report\n\n{response.get('content', 'Review pending.')}"
        except Exception as e:
            return f"# Code Review Report\n\nLLM review failed: {str(e)}"

    async def _generate_review(self, code_content: str, project_name: str) -> str:
        """Generate code review report."""
        review_prompt = f"""Review the following generated code for project {project_name}.

Analyze:
1. MISRA-C 2012 compliance (for C code)
2. Code quality score (0-100) with breakdown
3. Security vulnerabilities (buffer overflows, injection, etc.)
4. Coding standards adherence
5. Error handling completeness
6. Documentation quality
7. Specific recommendations for improvement

Code to review:
{code_content[:6000]}

Output as a structured markdown report with tables for findings.
"""
        response = await self.call_llm(
            messages=[{"role": "user", "content": review_prompt}],
            system="You are a senior code reviewer specializing in embedded C/C++ and MISRA-C compliance.",
            model=settings.fast_model,  # Haiku for speed
        )
        return response.get("content", "# Code Review Report\n\nReview pending.")

    def _parse_and_save_files(self, content: str, output_dir: Path, project_name: str) -> dict:
        """Parse code blocks from LLM output and save as separate files."""
        outputs = {}
        code_dir = output_dir / "src"
        code_dir.mkdir(parents=True, exist_ok=True)

        # Simple parser: find ```c or ```cpp blocks with filename comments
        import re
        pattern = r'```(?:c|cpp|h|cmake|makefile)\s*\n(?://\s*(?:File:|Filename:)?\s*(.+?)\n)?(.*?)```'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        for i, (filename, code) in enumerate(matches):
            filename = filename.strip() if filename else f"file_{i}.c"
            # Clean filename
            filename = filename.replace("/", "_").replace("\\", "_")
            filepath = code_dir / filename
            filepath.write_text(code.strip(), encoding="utf-8")
            outputs[f"src/{filename}"] = code.strip()

        return outputs

    def _load_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
