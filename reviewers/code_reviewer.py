"""
Code Reviewer - Static analysis and MISRA-C checking for generated C/C++ code.

This module provides code quality analysis, MISRA-C 2012 compliance checking,
and security vulnerability detection for embedded systems code.
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class CodeReviewer:
    """
    Review generated code for quality and MISRA-C compliance.

    This class performs static analysis on C/C++ code to detect:
    - MISRA-C 2012 rule violations
    - Security vulnerabilities
    - Code quality issues
    - Documentation gaps
    """

    def __init__(self):
        """Initialize the CodeReviewer with rule configurations."""
        self.misra_rules = self._load_misra_rules()
        self.security_rules = self._load_security_rules()
        self.quality_rules = self._load_quality_rules()

    def review_code(
        self,
        code: str,
        language: str = "c",
        standards: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Review code for compliance and quality issues.

        Args:
            code: Source code to review
            language: Programming language (c, cpp, etc.)
            standards: List of standards to check (e.g., ["MISRA-C-2012"])

        Returns:
            Dictionary with review results including:
            - timestamp: Review timestamp
            - total_issues: Total number of issues found
            - critical_issues: Count of critical issues
            - warnings: Count of warnings
            - info: Count of info messages
            - details: Detailed findings
            - recommendations: Improvement suggestions
        """
        findings = []

        # Run various checks
        if standards and "MISRA-C-2012" in standards:
            findings.extend(self._check_misra_c(code))

        findings.extend(self._check_security(code))
        findings.extend(self._check_quality(code))
        findings.extend(self._check_documentation(code))
        findings.extend(self._check_complexity(code))

        # Calculate scores
        score = self._calculate_score(findings, len(code.splitlines()))

        # Categorize issues
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        warnings = sum(1 for f in findings if f.get("severity") == "warning")
        info = sum(1 for f in findings if f.get("severity") == "info")

        return {
            "timestamp": datetime.now().isoformat(),
            "total_issues": len(findings),
            "critical_issues": critical,
            "warnings": warnings,
            "info": info,
            "score": score,
            "details": self._format_findings(findings),
            "recommendations": self._generate_recommendations(findings),
        }

    def _load_misra_rules(self) -> Dict[str, str]:
        """Load MISRA-C 2012 rule definitions."""
        return {
            "21.1": "Dynamic memory allocation shall not be used",
            "15.1": "goto statement shall not be used",
            "14.4": "No statement after control flow break",
            "13.6": "Numeric literal suffixes",
            "12.5": "No unnecessary statements",
            "10.3": "No nested expressions > 3 levels",
            "8.5": "No unused parameters",
            "7.4": "No string literals in code",
        }

    def _load_security_rules(self) -> Dict[str, str]:
        """Load security rule definitions."""
        return {
            "buffer_overflow": "Potential buffer overflow",
            "injection": "Code injection vulnerability",
            "integer_overflow": "Integer overflow possible",
            "format_string": "Format string vulnerability",
        }

    def _load_quality_rules(self) -> Dict[str, str]:
        """Load code quality rule definitions."""
        return {
            "long_function": "Function too long (>50 lines)",
            "complex": "Cyclomatic complexity too high",
            "magic_numbers": "Magic numbers without constants",
            "naming": "Naming convention violation",
        }

    def _check_misra_c(self, code: str) -> List[Dict[str, Any]]:
        """Check for MISRA-C 2012 violations."""
        findings = []

        # Rule 21.1: Dynamic memory allocation
        if re.search(r'\b(malloc|calloc|realloc|free|alloca)\s*\(', code):
            findings.append({
                "rule": "MISRA-C 21.1",
                "severity": "warning",
                "category": "MISRA-C",
                "message": "Dynamic memory allocation detected",
                "line": self._find_line_number(code, 'malloc'),
            })

        # Rule 15.1: goto statements
        if re.search(r'\bgoto\s+', code):
            findings.append({
                "rule": "MISRA-C 15.1",
                "severity": "warning",
                "category": "MISRA-C",
                "message": "goto statement detected",
                "line": self._find_line_number(code, 'goto'),
            })

        # Rule 14.4: Statement after control flow break
        if re.search(r'\b(return|break|continue)\s*;\s*[^}\s]', code):
            findings.append({
                "rule": "MISRA-C 14.4",
                "severity": "info",
                "category": "MISRA-C",
                "message": "Unreachable code after control flow break",
                "line": None,
            })

        # Check for recursion (MISRA-C 17.2)
        if self._detect_recursion(code):
            findings.append({
                "rule": "MISRA-C 17.2",
                "severity": "warning",
                "category": "MISRA-C",
                "message": "Recursion detected",
                "line": None,
            })

        return findings

    def _check_security(self, code: str) -> List[Dict[str, Any]]:
        """Check for security vulnerabilities."""
        findings = []

        # Unsafe functions
        unsafe_functions = {
            'gets': 'Buffer overflow vulnerability',
            'strcpy': 'Buffer overflow, use strncpy',
            'strcat': 'Buffer overflow, use strncat',
            'sprintf': 'Buffer overflow, use snprintf',
            'scanf': 'Potential buffer overflow',
            'sscanf': 'Potential buffer overflow',
        }

        for func, issue in unsafe_functions.items():
            if re.search(rf'\b{func}\s*\(', code):
                findings.append({
                    "rule": "SECURITY",
                    "severity": "critical",
                    "category": "Security",
                    "message": f"Unsafe function {func}: {issue}",
                    "line": self._find_line_number(code, func),
                })

        # Format string vulnerabilities
        if re.search(r'printf\s*\(\s*[^"]', code):
            findings.append({
                "rule": "FORMAT_STRING",
                "severity": "warning",
                "category": "Security",
                "message": "Potential format string vulnerability",
                "line": self._find_line_number(code, 'printf'),
            })

        # Integer overflow potential
        if re.search(r'\(\s*(int|uint\d+_t)\s*\)\s*[^)]+\s*[\+\-\*]\s*[^)]+\s*\)', code):
            findings.append({
                "rule": "INTEGER_OVERFLOW",
                "severity": "warning",
                "category": "Security",
                "message": "Potential integer overflow in cast expression",
                "line": None,
            })

        return findings

    def _check_quality(self, code: str) -> List[Dict[str, Any]]:
        """Check for code quality issues."""
        findings = []
        lines = code.splitlines()

        # Check function length
        in_function = False
        function_start = 0
        brace_count = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.search(r'\w+\s+\w+\s*\([^)]*\)\s*\{?', stripped):
                in_function = True
                function_start = i

            if '{' in line:
                brace_count += line.count('{')
            if '}' in line:
                brace_count -= line.count('}')
                if in_function and brace_count == 0:
                    func_len = i - function_start
                    if func_len > 50:
                        findings.append({
                            "rule": "LONG_FUNCTION",
                            "severity": "info",
                            "category": "Quality",
                            "message": f"Function too long: {func_len} lines (recommend <50)",
                            "line": function_start,
                        })
                    in_function = False

        # Check comment ratio
        comment_lines = sum(1 for line in lines if line.strip().startswith('//'))
        code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith('//'))
        if code_lines > 0:
            comment_ratio = comment_lines / code_lines
            if comment_ratio < 0.1:
                findings.append({
                    "rule": "LOW_COMMENTS",
                    "severity": "info",
                    "category": "Quality",
                    "message": f"Low comment ratio: {comment_ratio:.1%} (recommend >10%)",
                    "line": None,
                })

        # Check for magic numbers
        magic_numbers = re.findall(r'(?<![a-zA-Z0-9_])(\d{2,})(?![a-zA-Z0-9_])', code)
        if len(magic_numbers) > 5:
            findings.append({
                "rule": "MAGIC_NUMBERS",
                "severity": "info",
                "category": "Quality",
                "message": f"Multiple magic numbers found: {len(magic_numbers)} (use named constants)",
                "line": None,
            })

        return findings

    def _check_documentation(self, code: str) -> List[Dict[str, Any]]:
        """Check for documentation gaps."""
        findings = []

        # Check for missing function comments
        functions = re.findall(r'^\s*(?:static\s+)?(?:inline\s+)?(?:\w+\s+)+\*?\s*(\w+)\s*\([^)]*\)\s*\{', code, re.MULTILINE)
        for func in functions:
            # Look for documentation before function
            func_pattern = r'/\*\*[^*]*\*+(?:[^/*][^*]*\*+)*/[^{]*\b' + re.escape(func) + r'\s*\('
            if not re.search(func_pattern, code, re.DOTALL):
                findings.append({
                    "rule": "DOCUMENTATION",
                    "severity": "info",
                    "category": "Documentation",
                    "message": f"Function '{func}' missing documentation comment",
                    "line": self._find_line_number(code, func),
                })

        # Check for file header
        if not re.search(r'/\*\*.*?File.*?\*+', code, re.DOTALL):
            findings.append({
                "rule": "FILE_HEADER",
                "severity": "info",
                "category": "Documentation",
                "message": "Missing file header documentation",
                "line": 1,
            })

        return findings

    def _check_complexity(self, code: str) -> List[Dict[str, Any]]:
        """Check cyclomatic complexity."""
        findings = []

        # Simple complexity check: count decision points
        decision_keywords = [r'if', r'else if', r'for', r'while', r'case', r'catch', r'&&', r'\|\|']
        complexity = sum(len(re.findall(rf'\b{kw}\b', code)) for kw in decision_keywords)

        if complexity > 50:
            findings.append({
                "rule": "COMPLEXITY",
                "severity": "warning",
                "category": "Complexity",
                "message": f"High cyclomatic complexity: {complexity} (recommend <50)",
                "line": None,
            })

        return findings

    def _detect_recursion(self, code: str) -> bool:
        """Detect recursive function calls."""
        # Simple heuristic: function calls itself
        return bool(re.search(r'\b(\w+)\s*\([^)]*\)\s*\{[^}]*\1\s*\(', code, re.DOTALL))

    def _find_line_number(self, code: str, pattern: str) -> int:
        """Find line number of a pattern in code."""
        lines = code.splitlines()
        for i, line in enumerate(lines, 1):
            if pattern in line:
                return i
        return None

    def _calculate_score(self, findings: List[Dict], line_count: int) -> int:
        """Calculate code quality score (0-100)."""
        score = 100

        for finding in findings:
            severity = finding.get("severity", "info")
            if severity == "critical":
                score -= 15
            elif severity == "warning":
                score -= 5
            elif severity == "info":
                score -= 1

        return max(0, score)

    def _format_findings(self, findings: List[Dict]) -> str:
        """Format findings as a readable string."""
        if not findings:
            return "No issues found. Code meets all checked standards."

        lines = ["## Detailed Findings\n"]
        lines.append("| Severity | Category | Rule | Message | Line |")
        lines.append("|----------|----------|------|---------|------|")

        for finding in findings[:50]:  # Limit to 50 findings
            severity = finding.get("severity", "info").upper()
            category = finding.get("category", "General")
            rule = finding.get("rule", "N/A")
            message = finding.get("message", "")
            line = finding.get("line", "N/A")

            # Truncate long messages
            if len(message) > 50:
                message = message[:47] + "..."

            lines.append(f"| {severity:8s} | {category:8s} | {rule} | {message} | {line} |")

        if len(findings) > 50:
            lines.append(f"\n*... and {len(findings) - 50} more findings*")

        return "\n".join(lines)

    def _generate_recommendations(self, findings: List[Dict]) -> str:
        """Generate improvement recommendations based on findings."""
        recommendations = []

        # Categorize findings
        critical_count = sum(1 for f in findings if f.get("severity") == "critical")
        misra_count = sum(1 for f in findings if f.get("category") == "MISRA-C")
        security_count = sum(1 for f in findings if f.get("category") == "Security")
        quality_count = sum(1 for f in findings if f.get("category") == "Quality")

        if critical_count > 0:
            recommendations.append(f"**CRITICAL**: Address {critical_count} critical security issues immediately")

        if misra_count > 0:
            recommendations.append(f"**MISRA-C**: {misra_count} MISRA-C violations found. Review and fix for compliance")

        if security_count > 0:
            recommendations.append(f"**Security**: {security_count} security issues detected. Use safe library functions")

        if quality_count > 0:
            recommendations.append(f"**Quality**: {quality_count} quality improvements suggested")

        if not recommendations:
            recommendations.append("**Excellent**: Code meets all checked standards. Continue following these practices!")

        return "\n\n".join(recommendations)
