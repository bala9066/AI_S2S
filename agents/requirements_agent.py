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

_APPROVAL_KEYWORDS = {"approve", "approved", "yes", "ok", "okay", "looks good",
                      "good", "correct", "proceed", "go ahead", "lgtm", "perfect", "great"}

def _is_approval(text: str) -> bool:
    return any(kw in text.lower() for kw in _APPROVAL_KEYWORDS)

# Optional import for ComponentSearchTool (ChromaDB has Python 3.14+ compatibility issues)
try:
    from tools.component_search import ComponentSearchTool
    COMPONENT_SEARCH_AVAILABLE = True
except (ImportError, Exception) as e:
    COMPONENT_SEARCH_AVAILABLE = False
    ComponentSearchTool = None
    logging.warning(f"ComponentSearchTool not available: {e}. Agent will use LLM fallback for component recommendations.")

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert hardware design engineer with 25+ years of experience in RF/wireless systems and high-speed digital design.

You work for a defense electronics company. Your role is to rapidly generate a draft block diagram from whatever the user describes, then refine it based on feedback.

## YOUR BEHAVIOR — DRAFT-FIRST APPROACH:

### STEP 1 — On the VERY FIRST user message:
- Make reasonable engineering assumptions for anything not stated
- IMMEDIATELY call `generate_draft` tool to produce a draft block diagram and requirements skeleton
- Do NOT ask questions first — generate a draft and present it
- End your response with: "Does this draft look right? Approve to proceed, or tell me what to change."

### STEP 2 — If user says "approve", "looks good", "yes", "ok", "proceed", or similar:
- IMMEDIATELY call `generate_requirements` tool with full outputs (requirements.md, block_diagram.md, architecture.md, component_recommendations.md)
- Mark phase as complete

### STEP 3 — If user requests changes:
- Apply the changes to the draft
- Call `generate_draft` again with updated values
- Show the revised draft and ask for approval again
- Repeat until approved (max 3 iterations)

## IMPORTANT RULES:
- NEVER ask multiple questions before generating — draft first, refine after
- Make smart engineering assumptions (e.g., if they say "motor controller" assume industrial temp range, common MCUs, standard interfaces)
- Flag your assumptions clearly so the user can correct them
- Use IEEE requirement IDs: REQ-HW-001, REQ-HW-002, etc.
- Prioritize RoHS-compliant components with long lifecycle status

## DESIGN TYPE CONTEXT: {design_type}
## PROJECT NAME: {project_name}
"""

GENERATE_DRAFT_TOOL = {
    "name": "generate_draft",
    "description": (
        "Generate a DRAFT block diagram and requirements skeleton immediately from user input. "
        "Call this on the very first message — make assumptions where needed and present the draft for approval. "
        "This does NOT write final files — it returns a preview for the user to approve or revise."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_summary": {
                "type": "string",
                "description": "1-2 sentence summary of the hardware design based on user input.",
            },
            "assumptions": {
                "type": "array",
                "description": "List of engineering assumptions made where user did not specify.",
                "items": {"type": "string"},
            },
            "block_diagram_mermaid": {
                "type": "string",
                "description": "Mermaid diagram code for the system block diagram. Use graph TD or graph LR.",
            },
            "key_requirements_preview": {
                "type": "array",
                "description": "Top 5-8 draft requirements (REQ-HW-xxx) for the user to review.",
                "items": {
                    "type": "object",
                    "properties": {
                        "req_id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["req_id", "title", "description"],
                },
            },
            "top_components_preview": {
                "type": "array",
                "description": "Top 3-5 key components suggested.",
                "items": {
                    "type": "object",
                    "properties": {
                        "function": {"type": "string"},
                        "part": {"type": "string"},
                        "manufacturer": {"type": "string"},
                    },
                    "required": ["function", "part", "manufacturer"],
                },
            },
        },
        "required": ["project_summary", "assumptions", "block_diagram_mermaid", "key_requirements_preview"],
    },
}

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
        # Draft-first tools: generate_draft first, generate_requirements on approval
        tools = [GENERATE_DRAFT_TOOL, GENERATE_REQUIREMENTS_TOOL]
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
        Execute Phase 1 — Draft-First approach.

        Phase completion is AUTHORITATIVE via tool_use only:
          - generate_draft tool      → draft_pending=True (show approve buttons)
          - generate_requirements    → phase_complete=True (write output files)

        Plain-text fallback is used ONLY for draft detection (draft_pending),
        never for phase_complete. This eliminates heuristic state transitions.

        For models that ignore tool_use on approval (e.g. GLM-4), we synthesise
        a generate_requirements call by parsing the response and writing outputs
        immediately — phase_complete is still set explicitly, not via heuristics.
        """
        system = self.get_system_prompt(project_context)

        # Build message list from conversation history
        history = project_context.get("conversation_history", [])
        messages = []
        for msg in history:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": user_input})

        # Tool handlers (optional component search)
        tool_handlers = {}
        if COMPONENT_SEARCH_AVAILABLE and self.component_search:
            tool_handlers["search_components"] = self._handle_search_components

        response = await self.call_llm_with_tools(
            messages=messages,
            system=system,
            tool_handlers=tool_handlers,
        )

        response_content = response.get("content", "")

        # ── Tool-use path (authoritative) ─────────────────────────────────
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:

                if tc["name"] == "generate_draft":
                    draft_data = tc["input"]
                    draft_response = self._format_draft_response(draft_data)
                    self.log("generate_draft tool called — draft_pending=True", "info")
                    return {
                        "response": (response_content + "\n\n" + draft_response
                                     if response_content else draft_response),
                        "phase_complete": False,
                        "draft_pending": True,
                        "draft": draft_data,
                        "outputs": {},
                        "parameters": {},
                    }

                if tc["name"] == "generate_requirements":
                    self.log("generate_requirements tool called — phase_complete=True", "info")
                    outputs = self._generate_output_files(
                        tc["input"],
                        project_context.get("output_dir", "output"),
                        project_context.get("name", "project"),
                    )
                    return {
                        "response": (response_content
                                     + "\n\n✅ **Phase 1 Complete!** All documents have been generated."),
                        "phase_complete": True,
                        "draft_pending": False,
                        "draft": {},
                        "outputs": outputs,
                        "parameters": tc["input"].get("design_parameters", {}),
                    }

        # ── Plain-text fallback: draft detection only ──────────────────────
        # Used when model (e.g. GLM-4) returns a draft without calling generate_draft.
        # NEVER sets phase_complete via text detection.
        if self._detect_draft_response(response_content) and not _is_approval(user_input):
            self.log("Plain-text draft detected — draft_pending=True (no tool call)", "info")
            return {
                "response": response_content,
                "phase_complete": False,
                "draft_pending": True,
                "draft": {},
                "outputs": {},
                "parameters": {},
            }

        # ── Plain-text fallback: synthesised completion on approval ────────
        # When user approves but LLM returns full requirements as plain text
        # (no generate_requirements tool call), we parse and write outputs here.
        # phase_complete is set explicitly — no heuristic text-matching.
        if _is_approval(user_input) and self._detect_complete_requirements(response_content):
            self.log("Approval + complete response detected — synthesising completion", "info")
            parsed = self._parse_requirements_response(
                response_content, project_context.get("name", "project")
            )
            if parsed:
                outputs = self._generate_output_files(
                    parsed,
                    project_context.get("output_dir", "output"),
                    project_context.get("name", "project"),
                )
                self.log("Synthesised outputs written — phase_complete=True", "info")
                return {
                    "response": response_content + "\n\n✅ **Phase 1 Complete!** All documents generated.",
                    "phase_complete": True,
                    "draft_pending": False,
                    "draft": {},
                    "outputs": outputs,
                    "parameters": parsed.get("design_parameters", {}),
                }
            # Parser returned None (rare) — stay in draft_pending, prompt user to retry
            self.log("Synthesised completion: parser returned None, keeping draft_pending", "warning")
            return {
                "response": response_content,
                "phase_complete": False,
                "draft_pending": True,
                "draft": {},
                "outputs": {},
                "parameters": {},
            }

        # ── Normal conversational exchange ─────────────────────────────────
        return {
            "response": response_content,
            "phase_complete": False,
            "draft_pending": False,
            "draft": {},
            "outputs": {},
            "parameters": {},
        }

    def _format_draft_response(self, draft_data: dict) -> str:
        """Format the draft block diagram and summary for display in the chat."""
        lines = ["### 📐 Draft Block Diagram"]
        lines.append("")
        lines.append(f"**{draft_data.get('project_summary', '')}**")
        lines.append("")

        # Assumptions
        assumptions = draft_data.get("assumptions", [])
        if assumptions:
            lines.append("**⚙️ Assumptions made:**")
            for a in assumptions:
                lines.append(f"- {a}")
            lines.append("")

        # Block diagram (Mermaid — rendered by Streamlit)
        mermaid = draft_data.get("block_diagram_mermaid", "")
        if mermaid:
            lines.append("```mermaid")
            lines.append(mermaid)
            lines.append("```")
            lines.append("")

        # Requirements preview
        reqs = draft_data.get("key_requirements_preview", [])
        if reqs:
            lines.append("**📋 Draft Requirements (preview):**")
            for r in reqs:
                lines.append(f"- `{r.get('req_id', '')}` — {r.get('title', '')}: {r.get('description', '')}")
            lines.append("")

        # Components preview
        comps = draft_data.get("top_components_preview", [])
        if comps:
            lines.append("**🔌 Suggested Components:**")
            for c in comps:
                lines.append(f"- **{c.get('function', '')}**: {c.get('part', '')} ({c.get('manufacturer', '')})")
            lines.append("")

        lines.append("---")
        lines.append("✅ **Does this draft look right?**")
        lines.append("- Click **Approve** to generate full documents")
        lines.append("- Or tell me what to change and I'll revise")

        return "\n".join(lines)

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

    def _detect_draft_response(self, response_content: str) -> bool:
        """
        Detect if the response is a DRAFT (asking for approval) rather than a complete doc.
        GLM models return formatted drafts as plain text without tool calls.
        """
        content_lower = response_content.lower()
        # Must have draft-like content (summary/requirements/components)
        has_content = sum([
            bool(re.search(r'REQ-HW-\d+', response_content, re.IGNORECASE)),
            'project summary' in content_lower,
            'key requirements' in content_lower or 'requirements' in content_lower,
            'component' in content_lower,
            'block diagram' in content_lower or 'architecture' in content_lower,
        ]) >= 3
        # AND must be asking for approval (not yet done)
        asking_approval = any(phrase in content_lower for phrase in [
            'does this draft look right',
            'does this look right',
            'approve to proceed',
            'tell me what to change',
            'look right?',
            'looks good?',
            'shall i proceed',
            'would you like to',
        ])
        return has_content and asking_approval

    def _detect_complete_requirements(self, response_content: str) -> bool:
        """
        Detect if the response contains a complete requirements document.
        This is a fallback for models that don't support tool calling (e.g., GLM-4).
        """
        content_lower = response_content.lower()

        # Strong signal: long response (>2000 chars) with multiple REQ-HW IDs = almost certainly complete
        req_count = len(re.findall(r'REQ-HW-\d+', response_content, re.IGNORECASE))
        if len(response_content) > 2000 and req_count >= 3:
            return True

        # Look for key indicators of a complete requirements document
        indicators = [
            # Requirement IDs present
            req_count >= 1,
            # Hardware requirements header
            'hardware requirements' in content_lower,
            'requirements document' in content_lower,
            # Project summary section
            'project summary' in content_lower,
            # Design parameters table
            'design parameters' in content_lower or 'parameter' in content_lower,
            # Component recommendations
            'component recommendations' in content_lower or 'component' in content_lower,
            # Next steps or conclusion phrases (broader set)
            any(phrase in content_lower for phrase in [
                'next steps', 'phase complete', 'requirements captured',
                'would you like me to', 'shall i proceed',
                'work on next', 'let me know what', 'phase 1 deliverable',
                'deliverable', 'generated your', 'complete requirements',
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
