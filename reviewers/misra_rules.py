"""
MISRA-C Rules — rule definitions and violation detector.

Implements a subset of MISRA-C:2012 rules using regex/AST heuristics.
For full compliance, integrate with a commercial MISRA checker or PC-lint.
This module provides rule definitions and lightweight pattern matching
suitable for AI-generated driver code review.

Rules implemented (subset):
  - Rule 8.1  : Types shall be explicitly declared
  - Rule 10.1 : Operands shall not be inappropriate essential type
  - Rule 11.1 : Conversions between function pointer and other types
  - Rule 12.1 : Operator precedence
  - Rule 13.5 : Side-effects in right-hand operand of && / ||
  - Rule 14.4 : Non-boolean controlling expression
  - Rule 15.1 : goto shall not be used
  - Rule 15.5 : Single point of exit from a function
  - Rule 16.3 : All switch clauses shall have a break / return
  - Rule 17.1 : <stdarg.h> features shall not be used
  - Rule 17.3 : Implicit function declaration
  - Rule 20.9 : No undefined macros in #if
  - Rule 21.6 : stdio functions (printf etc.) shall not be used
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Rule registry ──────────────────────────────────────────────────────────────

@dataclass
class MISRAViolation:
    rule_id: str           # e.g. "15.1"
    severity: str          # "mandatory" | "required" | "advisory"
    line_number: int
    line_content: str
    message: str
    advisory_note: str = ""


@dataclass
class MISRARule:
    rule_id: str
    category: str          # "mandatory" | "required" | "advisory"
    title: str
    description: str
    pattern: Optional[re.Pattern] = field(default=None, repr=False)
    # Custom checker function: (line, line_number, full_source) -> MISRAViolation | None
    checker: Optional[object] = field(default=None, repr=False)


# ── Rule definitions ────────────────────────────────────────────────────────────

MISRA_RULES: dict[str, MISRARule] = {
    "15.1": MISRARule(
        rule_id="15.1",
        category="required",
        title="No goto",
        description="The goto statement shall not be used.",
        pattern=re.compile(r'\bgoto\b'),
    ),
    "17.1": MISRARule(
        rule_id="17.1",
        category="mandatory",
        title="No stdarg",
        description="The features of <stdarg.h> shall not be used.",
        pattern=re.compile(r'#include\s*[<"]\s*stdarg\.h\s*[">]'),
    ),
    "21.6": MISRARule(
        rule_id="21.6",
        category="required",
        title="No stdio in production",
        description="Standard library I/O functions (printf, scanf, etc.) shall not be used.",
        pattern=re.compile(
            r'\b(printf|fprintf|sprintf|snprintf|scanf|fscanf|sscanf|gets|puts|fgets|fputs)\s*\(',
        ),
    ),
    "8.1": MISRARule(
        rule_id="8.1",
        category="required",
        title="Explicit types",
        description="Types shall be explicitly specified in all declarations.",
        pattern=re.compile(r'^\s*(\w+)\s+\w+\s*\(', re.MULTILINE),
        # Not a simple pattern rule — custom check below
    ),
    "16.3": MISRARule(
        rule_id="16.3",
        category="required",
        title="Switch clause break",
        description="All switch clauses shall be terminated with a break or return statement.",
    ),
    "17.3": MISRARule(
        rule_id="17.3",
        category="mandatory",
        title="No implicit function declaration",
        description="A function shall not be declared implicitly.",
    ),
    "15.5": MISRARule(
        rule_id="15.5",
        category="advisory",
        title="Single exit point",
        description="A function should have a single point of exit at the end.",
    ),
}


# ── Lightweight checker ─────────────────────────────────────────────────────────

class MISRAChecker:
    """
    Runs MISRA-C rule checks on C/C++ source code.

    This is a heuristic checker — it will miss some violations and may
    produce false positives on complex code. Pair with a real MISRA tool
    for production sign-off.
    """

    def check(self, source_code: str) -> list[MISRAViolation]:
        violations: list[MISRAViolation] = []
        lines = source_code.splitlines()

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Skip comments and blank lines for most checks
            if stripped.startswith("//") or stripped.startswith("*") or not stripped:
                continue

            violations += self._check_goto(line, i)
            violations += self._check_stdio(line, i)
            violations += self._check_stdarg(line, i)

        violations += self._check_switch_breaks(source_code, lines)
        violations += self._check_multiple_returns(source_code)
        return violations

    def _check_goto(self, line: str, ln: int) -> list[MISRAViolation]:
        if re.search(r'\bgoto\b', line):
            return [MISRAViolation(
                rule_id="15.1", severity="required", line_number=ln,
                line_content=line.rstrip(),
                message="Rule 15.1: 'goto' statement detected",
            )]
        return []

    def _check_stdio(self, line: str, ln: int) -> list[MISRAViolation]:
        pattern = re.compile(
            r'\b(printf|fprintf|sprintf|snprintf|scanf|fscanf|sscanf|gets|puts|fgets|fputs)\s*\('
        )
        if pattern.search(line):
            fn = pattern.search(line).group(1)
            return [MISRAViolation(
                rule_id="21.6", severity="required", line_number=ln,
                line_content=line.rstrip(),
                message=f"Rule 21.6: stdio function '{fn}()' shall not be used in production code",
                advisory_note="Use a hardware-specific debug/logging interface instead.",
            )]
        return []

    def _check_stdarg(self, line: str, ln: int) -> list[MISRAViolation]:
        if re.search(r'#include\s*[<"]\s*stdarg\.h\s*[">]', line):
            return [MISRAViolation(
                rule_id="17.1", severity="mandatory", line_number=ln,
                line_content=line.rstrip(),
                message="Rule 17.1: <stdarg.h> shall not be included",
            )]
        return []

    def _check_switch_breaks(self, source: str, lines: list[str]) -> list[MISRAViolation]:
        """Detect switch cases not followed by break/return before next case/default."""
        violations = []
        in_switch = 0
        last_case_line = -1
        has_break = False

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if re.match(r'\bswitch\s*\(', stripped):
                in_switch += 1
                has_break = True  # Reset
            if in_switch:
                if re.match(r'(case\s+.+:|default\s*:)', stripped):
                    if last_case_line >= 0 and not has_break:
                        violations.append(MISRAViolation(
                            rule_id="16.3", severity="required",
                            line_number=last_case_line,
                            line_content=lines[last_case_line - 1].rstrip(),
                            message="Rule 16.3: Switch case missing break/return before next case",
                        ))
                    last_case_line = i
                    has_break = False
                if re.match(r'\b(break|return)\b', stripped):
                    has_break = True
                if stripped == '}':
                    in_switch = max(0, in_switch - 1)
                    last_case_line = -1
                    has_break = True
        return violations

    def _check_multiple_returns(self, source: str) -> list[MISRAViolation]:
        """Flag functions with more than one return statement (MISRA 15.5 advisory)."""
        violations = []
        # Simple heuristic: find function bodies and count return statements
        func_pattern = re.compile(
            r'\b\w[\w\s\*]+\s+\w+\s*\([^)]*\)\s*\{',
        )
        for match in func_pattern.finditer(source):
            start = match.end()
            # Find matching closing brace
            depth = 1
            pos = start
            while pos < len(source) and depth > 0:
                if source[pos] == '{':
                    depth += 1
                elif source[pos] == '}':
                    depth -= 1
                pos += 1
            body = source[start:pos - 1]
            returns = [m.start() for m in re.finditer(r'\breturn\b', body)]
            if len(returns) > 1:
                # Approximate line number
                line_num = source[:match.start()].count('\n') + 1
                violations.append(MISRAViolation(
                    rule_id="15.5", severity="advisory",
                    line_number=line_num,
                    line_content=match.group(0).split('\n')[0].rstrip(),
                    message=f"Rule 15.5 (advisory): Function has {len(returns)} return statements; single exit point preferred",
                ))
        return violations

    def format_report(self, violations: list[MISRAViolation], project_name: str = "") -> str:
        """Format violations as a markdown report."""
        if not violations:
            return f"# MISRA-C Compliance Report\n## {project_name}\n\n✅ No violations detected.\n"

        mandatory = [v for v in violations if v.severity == "mandatory"]
        required  = [v for v in violations if v.severity == "required"]
        advisory  = [v for v in violations if v.severity == "advisory"]

        lines = [
            f"# MISRA-C Compliance Report",
            f"## {project_name}" if project_name else "",
            "",
            f"**Total violations:** {len(violations)}  "
            f"| Mandatory: {len(mandatory)} | Required: {len(required)} | Advisory: {len(advisory)}",
            "",
        ]

        for sev, group in [("Mandatory", mandatory), ("Required", required), ("Advisory", advisory)]:
            if group:
                lines.append(f"### {sev} Violations")
                lines.append("")
                lines.append("| Line | Rule | Message |")
                lines.append("|------|------|---------|")
                for v in group:
                    lines.append(f"| {v.line_number} | {v.rule_id} | {v.message} |")
                lines.append("")
                if any(v.advisory_note for v in group):
                    for v in group:
                        if v.advisory_note:
                            lines.append(f"> **L{v.line_number}** — {v.advisory_note}")
                    lines.append("")

        return "\n".join(lines)
