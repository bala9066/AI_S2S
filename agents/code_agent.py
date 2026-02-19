"""
Phase 8c: Code Generation + Review Agent

Generates C/C++ drivers, Qt GUI skeleton, tests from SRS+SDD.
Includes automated code review with MISRA-C checking.
"""

import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from config import settings

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

        user_message = f"""Generate complete production-ready code for:

**Project:** {project_name}

### SRS:
{srs[:4000]}

### SDD:
{sdd[:5000]}

### GLR (Register Map):
{glr[:3000]}

Generate:
1. C driver files (hal.h, hal.c, driver.h, driver.c)
2. Qt GUI skeleton (main.cpp, mainwindow.h, mainwindow.cpp)
3. Test files (test_driver.c)
4. Makefile or CMakeLists.txt
5. Code review report

Output each file with its path. Follow MISRA-C for C code.
"""

        response = await self.call_llm(
            messages=[{"role": "user", "content": user_message}],
            system=self.get_system_prompt(project_context),
        )

        code_content = response.get("content", "")

        # Handle truncation
        if response.get("stop_reason") == "max_tokens":
            continuation = await self.call_llm(
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": code_content},
                    {"role": "user", "content": "Continue generating the remaining files."},
                ],
                system=self.get_system_prompt(project_context),
            )
            code_content += "\n" + continuation.get("content", "")

        # Parse and save individual files
        outputs = self._parse_and_save_files(code_content, output_dir, project_name)

        # Save the raw generation as well
        gen_file = output_dir / "generated_code.md"
        gen_file.write_text(code_content, encoding="utf-8")
        outputs["generated_code.md"] = code_content

        # Generate code review report
        review_report = await self._generate_review(code_content, project_name)
        review_file = output_dir / "code_review_report.md"
        review_file.write_text(review_report, encoding="utf-8")
        outputs["code_review_report.md"] = review_report

        self.log(f"Code generated: {len(outputs)} files")

        return {
            "response": f"Code generation complete. {len(outputs)} files generated with review report.",
            "phase_complete": True,
            "outputs": outputs,
        }

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
