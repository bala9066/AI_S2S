"""
Hardware Pipeline — Streamlit UI
Professional UX with draft-approve flow for Phase 1, auto-progression through all phases.
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path

import httpx
import streamlit as st

# Mermaid rendering — graceful fallback
try:
    import streamlit_mermaid as stmd
    MERMAID_AVAILABLE = True
except ImportError:
    MERMAID_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hardware Pipeline",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Clean Light Theme CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
/* Phase status pills */
.phase-pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    margin: 2px 0;
}
.phase-pending  { background:#f0f0f0; color:#888; }
.phase-active   { background:#dbeafe; color:#1d4ed8; }
.phase-done     { background:#dcfce7; color:#16a34a; }
.phase-failed   { background:#fee2e2; color:#dc2626; }

/* Pipeline progress bar */
.pipeline-bar {
    display: flex;
    align-items: center;
    gap: 0;
    margin: 16px 0;
}
.pipe-step {
    flex: 1;
    text-align: center;
    padding: 10px 4px;
    font-size: 11px;
    font-weight: 600;
    border-top: 4px solid #e5e7eb;
    color: #9ca3af;
}
.pipe-step.done  { border-color: #22c55e; color: #16a34a; background: #f0fdf4; }
.pipe-step.active{ border-color: #3b82f6; color: #1d4ed8; background: #eff6ff; }

/* Metric cards */
.metric-card {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px 20px;
    text-align: center;
}
.metric-card .metric-value { font-size: 28px; font-weight: 700; color: #2563eb; }
.metric-card .metric-label { font-size: 12px; color: #6b7280; margin-top: 4px; }

/* Processing indicator */
.processing-indicator {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 20px;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    margin: 8px 0;
    font-weight: 500;
    color: #1d4ed8;
}
.processing-indicator .spinner {
    width: 20px; height: 20px;
    border: 3px solid #bfdbfe;
    border-top: 3px solid #2563eb;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}
@keyframes spin { 100% { transform: rotate(360deg); } }

/* Phase execution card */
.phase-exec-card {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
}
.phase-exec-card.running { border-left: 4px solid #3b82f6; }
.phase-exec-card.done { border-left: 4px solid #22c55e; }
.phase-exec-card.failed { border-left: 4px solid #ef4444; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ─────────────────────────────────────────────────────────────────

PHASE_META = [
    ("P1",  "1", "Requirements",    "agents.requirements_agent"),
    ("P2",  "2", "HRS Document",    "agents.document_agent"),
    ("P3",  "3", "Compliance",      "agents.compliance_agent"),
    ("P4",  "4", "Netlist",         "agents.netlist_agent"),
    ("P5",  "5", "PCB (Manual)",    None),
    ("P6",  "6", "GLR",             "agents.glr_agent"),
    ("P7",  "7", "FPGA (Manual)",   None),
    ("P8a", "8a","SRS",             "agents.srs_agent"),
    ("P8b", "8b","SDD",             "agents.sdd_agent"),
    ("P8c", "8c","Code + Review",   "agents.code_agent"),
]

AUTO_PHASES = ["P1", "P2", "P3", "P4", "P6", "P8a", "P8b", "P8c"]

APPROVAL_KEYWORDS = {"approve", "approved", "yes", "ok", "okay", "looks good",
                     "good", "correct", "proceed", "go ahead", "lgtm", "perfect", "great"}


def _is_approval(text: str) -> bool:
    return any(kw in text.lower() for kw in APPROVAL_KEYWORDS)


def _phase_status(statuses: dict, pid: str) -> str:
    return statuses.get(pid, {}).get("status", "pending")


def _create_project_db(name: str, description: str, design_type: str):
    from database.models import get_session, ProjectDB
    session = get_session()
    project_dir = Path("output") / name.replace(" ", "_").lower()
    project_dir.mkdir(parents=True, exist_ok=True)
    db_proj = ProjectDB(name=name, description=description,
                        design_type=design_type, output_dir=str(project_dir))
    session.add(db_proj)
    session.commit()
    result = {"id": db_proj.id, "name": name, "design_type": design_type,
              "output_dir": str(project_dir), "phase_statuses": {}}
    session.close()
    return result


def _update_phase_status(pid: str, status: str, extra: dict = None):
    if "current_project" in st.session_state:
        statuses = st.session_state.current_project.get("phase_statuses", {})
        entry = {"status": status}
        if extra:
            entry.update(extra)
        statuses[pid] = entry
        st.session_state.current_project["phase_statuses"] = statuses


def _render_mermaid(code: str, key: str = None):
    """Render a Mermaid diagram visually, with fallback to code block."""
    # Clean up the code — remove ```mermaid fences if present
    code = code.strip()
    code = re.sub(r'^```mermaid\s*', '', code)
    code = re.sub(r'\s*```$', '', code)
    code = code.strip()

    if not code:
        return

    if MERMAID_AVAILABLE:
        try:
            stmd.st_mermaid(code, key=key)
        except Exception:
            st.code(code, language="mermaid")
    else:
        st.code(code, language="mermaid")


def _render_markdown_with_mermaid(content: str, key_prefix: str = "md"):
    """Render markdown content, replacing mermaid code blocks with visual diagrams."""
    # Split on mermaid code blocks
    parts = re.split(r'```mermaid\s*\n(.*?)\n\s*```', content, flags=re.DOTALL)

    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Regular markdown
            if part.strip():
                st.markdown(part)
        else:
            # Mermaid diagram
            _render_mermaid(part, key=f"{key_prefix}_mermaid_{i}")


# ─── Sidebar ─────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("## ⚡ Hardware Pipeline")
        st.caption("AI-Powered Hardware Design Automation")
        st.divider()

        if "current_project" in st.session_state:
            proj = st.session_state.current_project
            st.markdown(f"**Project:** {proj.get('name', '—')}")
            st.markdown(f"**Type:** `{proj.get('design_type', '—')}`")
            st.divider()

            st.markdown("### Pipeline Status")
            statuses = proj.get("phase_statuses", {})
            for pid, num, name, _ in PHASE_META:
                status = _phase_status(statuses, pid)
                icon = {"pending": "⬜", "in_progress": "🔄",
                        "completed": "✅", "failed": "❌", "skipped": "⏭️"}.get(status, "⬜")
                css = {"pending": "phase-pending", "in_progress": "phase-active",
                       "completed": "phase-done", "failed": "phase-failed"}.get(status, "phase-pending")
                st.markdown(
                    f'<span class="phase-pill {css}">{icon} P{num} {name}</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No project loaded. Create one to begin.")

        st.divider()

        st.markdown("### System")
        try:
            from config import settings
            mode_label = "🔴 Air-Gapped" if settings.is_air_gapped else "🟢 Online"
            st.markdown(f"**Mode:** {mode_label}")
            st.caption(f"Primary: `{settings.primary_model}`")
            st.caption(f"Fast: `{settings.fast_model}`")
            st.divider()
            st.markdown("### API Keys")
            for provider, (ok, icon) in settings.get_api_key_status().items():
                st.caption(f"{icon} {provider}")
        except Exception as e:
            st.caption(f"Config error: {e}")


# ─── Tab nav ─────────────────────────────────────────────────────────────────

TABS = {
    "overview":   "🏠 Overview",
    "new":        "➕ New Project",
    "chat":       "💬 Design Chat",
    "pipeline":   "🔄 Pipeline",
    "docs":       "📄 Documents",
    "netlist":    "🔌 Netlist",
    "code":       "🔍 Code Review",
    "dashboard":  "📊 Dashboard",
}


def render_tab_nav():
    current = st.query_params.get("tab", "overview")
    cols = st.columns(len(TABS))
    for i, (key, label) in enumerate(TABS.items()):
        with cols[i]:
            btn_type = "primary" if key == current else "secondary"
            if st.button(label, use_container_width=True, type=btn_type, key=f"tab_{key}"):
                st.query_params["tab"] = key
                st.rerun()
    st.divider()
    return current


# ─── Overview ────────────────────────────────────────────────────────────────

def render_overview():
    st.markdown("## Welcome to Hardware Pipeline")
    st.markdown("**AI-Powered Hardware Design Automation** — From requirements to production-ready code.")

    st.markdown("### End-to-End Design Pipeline")
    statuses = {}
    if "current_project" in st.session_state:
        statuses = st.session_state.current_project.get("phase_statuses", {})

    steps_html = '<div class="pipeline-bar">'
    for pid, num, name, _ in PHASE_META:
        status = _phase_status(statuses, pid)
        css = "done" if status == "completed" else ("active" if status == "in_progress" else "")
        steps_html += f'<div class="pipe-step {css}">P{num}<br>{name}</div>'
    steps_html += "</div>"
    st.markdown(steps_html, unsafe_allow_html=True)

    st.markdown("")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("#### 📋 IEEE Docs")
        st.caption("HRS (29148), SRS (830), SDD (1016) — audit-ready, traceable requirements")
    with c2:
        st.markdown("#### 🔌 Netlist")
        st.caption("Visual connectivity graph before PCB layout, with DRC checks via NetworkX")
    with c3:
        st.markdown("#### ✅ Compliance")
        st.caption("RoHS / REACH / FCC rules engine with PASS / FAIL / REVIEW status")
    with c4:
        st.markdown("#### 💻 Code Gen")
        st.caption("C/C++ drivers + test suites, reviewed with tree-sitter AST analysis")

    st.divider()

    st.markdown("### Quick Start")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("➕ New Project", use_container_width=True, type="primary"):
            st.query_params["tab"] = "new"
            st.rerun()
    with col2:
        if st.button("📊 Dashboard", use_container_width=True):
            st.query_params["tab"] = "dashboard"
            st.rerun()
    with col3:
        if st.button("📄 Documents", use_container_width=True):
            st.query_params["tab"] = "docs"
            st.rerun()


# ─── New Project ─────────────────────────────────────────────────────────────

def render_new_project():
    st.markdown("## ➕ New Project")
    st.caption("Create a project and jump straight into the AI design chat.")

    with st.form("new_project_form", clear_on_submit=False):
        col1, col2 = st.columns([2, 1])
        with col1:
            name = st.text_input("Project Name *",
                                 placeholder="e.g., BLDC Motor Controller 10kW")
            description = st.text_area("Description",
                                       placeholder="Brief description of the hardware design…",
                                       height=100)
        with col2:
            design_type = st.selectbox(
                "Design Type *",
                ["general", "rf", "motor_control", "power", "digital", "sensor", "industrial"],
            )
            st.markdown("")
            submitted = st.form_submit_button("🚀 Create & Start", type="primary",
                                              use_container_width=True)

        if submitted:
            if not name.strip():
                st.error("Project name is required.")
                return

            from config import settings
            with st.spinner("Creating project…"):
                try:
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.post(
                            f"{settings.api_base_url}/api/v1/projects",
                            json={"name": name, "description": description,
                                  "design_type": design_type},
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            result["phase_statuses"] = {}
                            result["design_type"] = design_type
                            st.session_state.current_project = result
                            st.session_state.project_id = result["id"]
                            _reset_chat()
                            st.success(f"✅ Project '{name}' created!")
                            st.query_params["tab"] = "chat"
                            st.rerun()
                        else:
                            st.error(f"API error {resp.status_code}: {resp.text}")
                except httpx.ConnectError:
                    st.warning("API server not running — creating locally…")
                    result = _create_project_db(name, description, design_type)
                    st.session_state.current_project = result
                    st.session_state.project_id = result["id"]
                    _reset_chat()
                    st.success(f"✅ Project '{name}' created locally!")
                    st.query_params["tab"] = "chat"
                    st.rerun()
                except Exception as e:
                    logger.exception("Error creating project")
                    st.error(f"Error: {e}")


# ─── Design Chat (Phase 1) ──────────────────────────────────────────────────

def _reset_chat():
    st.session_state.chat_messages = [
        {
            "role": "assistant",
            "content": (
                "👋 **Welcome to Hardware Pipeline!**\n\n"
                "Tell me what you want to design — I'll instantly generate a **draft block diagram** "
                "for you to review. No long questionnaires.\n\n"
                "**Examples:**\n"
                "- *3-phase BLDC motor controller, 10kW, 48V bus*\n"
                "- *RF amplifier, 40dBm output, 2.4GHz*\n"
                "- *48V → 3.3V/5V/12V power supply, 200W total*\n\n"
                "Just describe your design and I'll produce a draft in seconds. ⚡"
            ),
        }
    ]
    st.session_state.draft_pending = False
    st.session_state.current_draft = None
    st.session_state.phase1_complete = False
    st.session_state.pipeline_running = False


def render_design_chat():
    st.markdown("## 💬 Design Chat — Phase 1: Requirements")

    if "project_id" not in st.session_state:
        st.info("Create a project first in **New Project**.")
        if st.button("➕ Create Project", type="primary"):
            st.query_params["tab"] = "new"
            st.rerun()
        return

    proj = st.session_state.current_project
    st.caption(f"Project: **{proj.get('name')}** · Type: `{proj.get('design_type', 'general')}`")

    # Phase 1 complete → offer to run full pipeline
    if st.session_state.get("phase1_complete") and not st.session_state.get("pipeline_running"):
        st.success("✅ **Phase 1 Complete!** Requirements and block diagrams generated.")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("🚀 Run Full Pipeline (P2→P8c)", use_container_width=True, type="primary",
                         key="btn_run_pipeline"):
                st.session_state.pipeline_running = True
                st.query_params["tab"] = "pipeline"
                st.rerun()
        with c2:
            if st.button("📄 View Documents", use_container_width=True, key="btn_view_docs"):
                st.query_params["tab"] = "docs"
                st.rerun()
        with c3:
            if st.button("🔄 New Chat", use_container_width=True, key="btn_new_chat"):
                _reset_chat()
                st.rerun()
        st.divider()

    if "chat_messages" not in st.session_state:
        _reset_chat()

    # Chat history — render with mermaid support
    for idx, msg in enumerate(st.session_state.chat_messages):
        with st.chat_message(msg["role"]):
            _render_markdown_with_mermaid(msg["content"], key_prefix=f"chat_{idx}")

    # Approval buttons
    if st.session_state.get("draft_pending") and not st.session_state.get("phase1_complete"):
        st.markdown("")
        col_a, col_b = st.columns([1, 2])
        with col_a:
            if st.button("✅ Approve — Generate Full Docs", type="primary",
                         use_container_width=True, key="btn_approve"):
                _handle_chat_input("Approved. Please generate the full requirements documents.")
        with col_b:
            change_text = st.text_input("Or describe changes…", key="change_input",
                                        placeholder="e.g., change voltage to 24V, add CAN bus interface")
            if st.button("🔄 Apply Changes", use_container_width=True, key="btn_changes"):
                if change_text.strip():
                    _handle_chat_input(change_text.strip())

    elif not st.session_state.get("phase1_complete"):
        if user_input := st.chat_input("Describe your hardware design…"):
            _handle_chat_input(user_input)


def _handle_chat_input(user_input: str):
    st.session_state.chat_messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        start_time = time.time()

        is_approval = _is_approval(user_input)
        action_text = "Generating full requirements documentation…" if is_approval else "Generating draft block diagram…"

        status_placeholder.markdown(
            f'<div class="processing-indicator">'
            f'<div class="spinner"></div>'
            f'{action_text}'
            f'</div>',
            unsafe_allow_html=True,
        )

        try:
            from agents.requirements_agent import RequirementsAgent

            agent = RequirementsAgent()
            proj = st.session_state.current_project

            result = asyncio.run(agent.execute(
                project_context={
                    "project_id": proj.get("id"),
                    "name": proj.get("name", ""),
                    "design_type": proj.get("design_type", "general"),
                    "conversation_history": st.session_state.chat_messages,
                    "output_dir": proj.get("output_dir", "output"),
                },
                user_input=user_input,
            ))

            elapsed = time.time() - start_time
            status_placeholder.empty()

            response = result.get("response", "Processing…")
            _render_markdown_with_mermaid(response, key_prefix="response")
            st.caption(f"⏱️ Generated in {elapsed:.1f}s")
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": response}
            )

            if result.get("draft_pending"):
                st.session_state.draft_pending = True
                st.session_state.current_draft = result.get("draft", {})

            if result.get("phase_complete"):
                st.session_state.phase1_complete = True
                st.session_state.draft_pending = False
                _update_phase_status("P1", "completed")
                st.balloons()
                st.success(f"✅ **Phase 1 Complete!** ({elapsed:.1f}s)")
                if result.get("outputs"):
                    with st.expander("📁 Generated Files", expanded=True):
                        for fname in result["outputs"]:
                            st.markdown(f"- 📄 `{fname}`")
                st.rerun()

        except ImportError as e:
            status_placeholder.empty()
            st.error(f"Module missing: {e}")
        except Exception as e:
            status_placeholder.empty()
            logger.exception("Chat error")
            st.error(f"Error: {e}")


# ─── Pipeline Execution (P2→P8c) ─────────────────────────────────────────────

def render_pipeline():
    st.markdown("## 🔄 Pipeline Execution")

    if "project_id" not in st.session_state:
        st.info("Create a project first.")
        return

    proj = st.session_state.current_project
    st.caption(f"Project: **{proj.get('name')}** · Type: `{proj.get('design_type', 'general')}`")

    # Show progress bar
    statuses = proj.get("phase_statuses", {})
    steps_html = '<div class="pipeline-bar">'
    for pid, num, name, _ in PHASE_META:
        status = _phase_status(statuses, pid)
        css = "done" if status == "completed" else ("active" if status == "in_progress" else "")
        steps_html += f'<div class="pipe-step {css}">P{num}<br>{name}</div>'
    steps_html += "</div>"
    st.markdown(steps_html, unsafe_allow_html=True)
    st.markdown("")

    if _phase_status(statuses, "P1") != "completed":
        st.warning("Complete Phase 1 (Design Chat) first before running the pipeline.")
        if st.button("💬 Go to Design Chat", type="primary"):
            st.query_params["tab"] = "chat"
            st.rerun()
        return

    remaining_phases = [p for p in AUTO_PHASES if p != "P1" and _phase_status(statuses, p) != "completed"]

    if not remaining_phases:
        st.success("✅ **All phases complete!** Your design package is ready.")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("📄 View Documents", type="primary", use_container_width=True):
                st.query_params["tab"] = "docs"
                st.rerun()
        with c2:
            if st.button("🔌 View Netlist", use_container_width=True):
                st.query_params["tab"] = "netlist"
                st.rerun()
        with c3:
            if st.button("🔍 Code Review", use_container_width=True):
                st.query_params["tab"] = "code"
                st.rerun()
        return

    if st.session_state.get("pipeline_running"):
        _execute_remaining_phases(remaining_phases)
    else:
        st.markdown(f"**{len(remaining_phases)} phases remaining:** {', '.join(remaining_phases)}")
        if st.button("🚀 Run Remaining Phases", type="primary", use_container_width=True):
            st.session_state.pipeline_running = True
            st.rerun()


def _execute_remaining_phases(phases_to_run: list):
    proj = st.session_state.current_project
    output_dir = proj.get("output_dir", "output")

    prior_outputs = _read_all_outputs(output_dir)

    phase_names = {pid: name for pid, _, name, _ in PHASE_META}
    total = len(phases_to_run)
    progress_bar = st.progress(0, text="Starting pipeline…")

    for i, phase_id in enumerate(phases_to_run):
        phase_name = phase_names.get(phase_id, phase_id)
        progress_bar.progress((i) / total, text=f"Running {phase_id}: {phase_name}…")

        card_placeholder = st.empty()
        card_placeholder.markdown(
            f'<div class="phase-exec-card running">'
            f'<strong>🔄 {phase_id}: {phase_name}</strong> — Processing…'
            f'</div>',
            unsafe_allow_html=True,
        )
        _update_phase_status(phase_id, "in_progress")

        start_time = time.time()
        try:
            result = _execute_single_phase(phase_id, proj, prior_outputs)
            elapsed = time.time() - start_time

            _update_phase_status(phase_id, "completed")
            card_placeholder.markdown(
                f'<div class="phase-exec-card done">'
                f'<strong>✅ {phase_id}: {phase_name}</strong> — Completed in {elapsed:.1f}s'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Accumulate outputs for subsequent phases
            if result and result.get("outputs"):
                for fname, content in result["outputs"].items():
                    prior_outputs[fname] = content

        except Exception as e:
            elapsed = time.time() - start_time
            _update_phase_status(phase_id, "failed")
            card_placeholder.markdown(
                f'<div class="phase-exec-card failed">'
                f'<strong>❌ {phase_id}: {phase_name}</strong> — Failed after {elapsed:.1f}s: {str(e)[:120]}'
                f'</div>',
                unsafe_allow_html=True,
            )
            logger.exception(f"Phase {phase_id} failed")
            continue

    progress_bar.progress(1.0, text="Pipeline complete!")
    st.session_state.pipeline_running = False
    st.success("✅ **Pipeline complete!** All automated phases have been executed.")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📄 View Documents", type="primary", use_container_width=True, key="pipe_docs"):
            st.query_params["tab"] = "docs"
            st.rerun()
    with c2:
        if st.button("🔌 View Netlist", use_container_width=True, key="pipe_netlist"):
            st.query_params["tab"] = "netlist"
            st.rerun()
    with c3:
        if st.button("🔍 Code Review", use_container_width=True, key="pipe_code"):
            st.query_params["tab"] = "code"
            st.rerun()


def _read_all_outputs(output_dir: str) -> dict:
    """Read all existing output files for pipeline context."""
    outputs = {}
    output_path = Path(output_dir)
    if output_path.exists():
        # Read all markdown files
        for md_file in output_path.glob("*.md"):
            try:
                outputs[md_file.name] = md_file.read_text(encoding="utf-8")
            except Exception:
                pass
        # Read all json files
        for json_file in output_path.glob("*.json"):
            try:
                outputs[json_file.name] = json_file.read_text(encoding="utf-8")
            except Exception:
                pass
        # Read source files
        src_dir = output_path / "src"
        if src_dir.exists():
            for src_file in src_dir.rglob("*.*"):
                try:
                    outputs[f"src/{src_file.name}"] = src_file.read_text(encoding="utf-8")
                except Exception:
                    pass
    return outputs


def _execute_single_phase(phase_id: str, proj: dict, prior_outputs: dict) -> dict:
    """Execute a single phase using its agent."""
    project_context = {
        "project_id": proj.get("id"),
        "name": proj.get("name", ""),
        "design_type": proj.get("design_type", "general"),
        "output_dir": proj.get("output_dir", "output"),
        "conversation_history": [],
        "design_parameters": {},
        "prior_phase_outputs": prior_outputs,
    }

    agent_module_map = {
        "P2": ("agents.document_agent", "DocumentAgent"),
        "P3": ("agents.compliance_agent", "ComplianceAgent"),
        "P4": ("agents.netlist_agent", "NetlistAgent"),
        "P6": ("agents.glr_agent", "GLRAgent"),
        "P8a": ("agents.srs_agent", "SRSAgent"),
        "P8b": ("agents.sdd_agent", "SDDAgent"),
        "P8c": ("agents.code_agent", "CodeAgent"),
    }

    if phase_id not in agent_module_map:
        raise ValueError(f"No agent for phase {phase_id}")

    module_path, class_name = agent_module_map[phase_id]
    import importlib
    module = importlib.import_module(module_path)
    agent_class = getattr(module, class_name)
    agent = agent_class()

    result = asyncio.run(agent.execute(project_context, ""))
    return result


# ─── Documents ───────────────────────────────────────────────────────────────

def render_documents():
    st.markdown("## 📄 Generated Documents")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", "output"))
    proj_name = proj.get("name", "project").replace(" ", "_").lower()

    if not output_dir.exists():
        st.info("No documents yet — complete Phase 1 in Design Chat.")
        return

    # Collect all document files with phase labels
    doc_files = []
    doc_map = {
        "requirements.md": ("P1", "Hardware Requirements"),
        "block_diagram.md": ("P1", "Block Diagram"),
        "architecture.md": ("P1", "System Architecture"),
        "component_recommendations.md": ("P1", "Component Recommendations"),
        f"HRS_{proj_name}.md": ("P2", "HRS — Hardware Requirements Specification"),
        "compliance_report.md": ("P3", "Compliance Report"),
        "netlist_visual.md": ("P4", "Netlist Visualization"),
        "glr_specification.md": ("P6", "GLR — Glue Logic Requirements"),
        f"SRS_{proj_name}.md": ("P8a", "SRS — Software Requirements Specification"),
        f"SDD_{proj_name}.md": ("P8b", "SDD — Software Design Document"),
        "code_review_report.md": ("P8c", "Code Review Report"),
    }

    for fname, (phase, label) in doc_map.items():
        fpath = output_dir / fname
        if fpath.exists():
            doc_files.append((fpath, phase, label))

    # Also pick up any .md files not in the map
    for fpath in sorted(output_dir.glob("*.md")):
        if fpath.name not in doc_map:
            doc_files.append((fpath, "—", fpath.stem.replace("_", " ").title()))

    if not doc_files:
        st.info("No documents generated yet. Complete Phase 1 in Design Chat.")
        return

    # Summary metrics
    st.markdown(f"**{len(doc_files)} documents generated**")
    cols = st.columns(min(len(doc_files), 4))
    for i, (f, phase, label) in enumerate(doc_files[:4]):
        with cols[i]:
            size_kb = f.stat().st_size / 1024
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-value">{size_kb:.1f}KB</div>'
                f'<div class="metric-label">{phase}: {f.name}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    st.markdown("")

    # Document viewer
    for fpath, phase, label in doc_files:
        with st.expander(f"📄 [{phase}] {label}", expanded=False):
            content = fpath.read_text(encoding="utf-8")
            tab_view, tab_raw = st.tabs(["Rendered", "Raw Markdown"])
            with tab_view:
                _render_markdown_with_mermaid(content, key_prefix=f"doc_{fpath.name}")
            with tab_raw:
                st.code(content, language="markdown")
            st.download_button(
                label=f"⬇️ Download {fpath.name}",
                data=content,
                file_name=fpath.name,
                mime="text/markdown",
                key=f"dl_{fpath.name}",
            )


# ─── Netlist Viewer ──────────────────────────────────────────────────────────

def render_netlist():
    st.markdown("## 🔌 Netlist Viewer — Phase 4")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", "output"))

    # Check for netlist files
    netlist_visual = output_dir / "netlist_visual.md"
    netlist_json = output_dir / "netlist.json"

    if not netlist_visual.exists() and not netlist_json.exists():
        st.info("Netlist not generated yet — run the pipeline through Phase 4.")
        return

    # Visual netlist with mermaid diagrams
    if netlist_visual.exists():
        content = netlist_visual.read_text(encoding="utf-8")
        st.markdown("### Visual Netlist")
        _render_markdown_with_mermaid(content, key_prefix="netlist")
        st.download_button("⬇️ Download Netlist Visual", data=content,
                           file_name="netlist_visual.md", mime="text/markdown",
                           key="dl_netlist_visual")

    # JSON netlist data
    if netlist_json.exists():
        st.divider()
        st.markdown("### Netlist Data (JSON)")
        json_content = netlist_json.read_text(encoding="utf-8")
        try:
            netlist_data = json.loads(json_content)

            # Summary metrics
            nodes = netlist_data.get("nodes", [])
            edges = netlist_data.get("edges", [])
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Components", len(nodes))
            with c2:
                st.metric("Connections", len(edges))
            with c3:
                power_nets = netlist_data.get("power_nets", [])
                st.metric("Power Nets", len(power_nets))

            # Node table
            if nodes:
                st.markdown("#### Component Instances")
                node_data = [{"Instance": n.get("instance_id", ""),
                              "Part": n.get("part_number", ""),
                              "Component": n.get("component_name", "")}
                             for n in nodes]
                st.dataframe(node_data, use_container_width=True)

            # Edge table
            if edges:
                st.markdown("#### Connections")
                edge_data = [{"From": e.get("from", ""),
                              "To": e.get("to", ""),
                              "Net": e.get("net_name", "")}
                             for e in edges]
                st.dataframe(edge_data, use_container_width=True)

        except json.JSONDecodeError:
            st.code(json_content, language="json")

        st.download_button("⬇️ Download netlist.json", data=json_content,
                           file_name="netlist.json", mime="application/json",
                           key="dl_netlist_json")


# ─── Code Review ─────────────────────────────────────────────────────────────

def render_code_review():
    st.markdown("## 🔍 Code Review — Phase 8c")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", "output"))

    # Code review report
    review_file = output_dir / "code_review_report.md"

    # Source files
    src_dir = output_dir / "src"
    src_files = list(src_dir.rglob("*.*")) if src_dir.exists() else []

    if not review_file.exists() and not src_files:
        st.info("Code not generated yet — run the full pipeline first.")
        return

    # Generated source files
    if src_files:
        st.markdown(f"### Generated Source Files ({len(src_files)} files)")
        for src_file in sorted(src_files):
            rel_path = src_file.relative_to(output_dir)
            lang = "c" if src_file.suffix in (".c", ".h") else "cpp"
            with st.expander(f"💻 {rel_path}", expanded=False):
                content = src_file.read_text(encoding="utf-8")
                st.code(content, language=lang)
                st.download_button(
                    f"⬇️ Download {src_file.name}",
                    data=content,
                    file_name=src_file.name,
                    key=f"dl_src_{src_file.name}",
                )
        st.divider()

    # Code review report
    if review_file.exists():
        st.markdown("### Code Review Report")
        content = review_file.read_text(encoding="utf-8")
        _render_markdown_with_mermaid(content, key_prefix="review")
        st.download_button("⬇️ Download Review Report", data=content,
                           file_name="code_review_report.md", mime="text/markdown",
                           key="dl_review")


# ─── Dashboard ───────────────────────────────────────────────────────────────

def render_dashboard():
    st.markdown("## 📊 Projects Dashboard")

    try:
        from database.models import get_session, ProjectDB
        session = get_session()
        projects = session.query(ProjectDB).order_by(ProjectDB.created_at.desc()).all()

        if not projects:
            st.info("No projects yet — create one in **New Project**.")
            session.close()
            return

        total = len(projects)
        completed = sum(1 for p in projects if p.current_phase == "DONE")
        in_progress = total - completed
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-value">{total}</div>'
                f'<div class="metric-label">Total Projects</div>'
                f'</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-value">{in_progress}</div>'
                f'<div class="metric-label">In Progress</div>'
                f'</div>', unsafe_allow_html=True)
        with c3:
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-value">{completed}</div>'
                f'<div class="metric-label">Completed</div>'
                f'</div>', unsafe_allow_html=True)

        st.markdown("")

        for p in projects:
            phase_statuses = p.phase_statuses or {}
            completed_phases = sum(
                1 for v in phase_statuses.values() if v.get("status") == "completed"
            )
            total_phases = 8

            with st.expander(
                f"📁 {p.name}  ·  `{p.design_type}`  ·  "
                f"Phase {p.current_phase or 'P1'}  ·  "
                f"{completed_phases}/{total_phases} phases done",
                expanded=False,
            ):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.caption(f"**Created:** {p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else '—'}")
                    st.caption(f"**Output:** `{p.output_dir}`")
                with col2:
                    for pid, num, name, _ in PHASE_META:
                        status = _phase_status(phase_statuses, pid)
                        icon = {"completed": "✅", "in_progress": "🔄",
                                "failed": "❌", "skipped": "⏭️"}.get(status, "⬜")
                        st.caption(f"{icon} P{num} {name}")
                with col3:
                    if st.button("Load →", key=f"load_{p.id}", type="primary",
                                 use_container_width=True):
                        st.session_state.current_project = {
                            "id": p.id,
                            "name": p.name,
                            "design_type": p.design_type,
                            "output_dir": p.output_dir,
                            "phase_statuses": p.phase_statuses or {},
                        }
                        st.session_state.project_id = p.id
                        _reset_chat()
                        st.query_params["tab"] = "chat"
                        st.rerun()

        session.close()

    except ImportError as e:
        st.error(f"Database module not found: {e}")
    except Exception as e:
        logger.exception("Dashboard error")
        st.error(f"Database error: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()

    st.markdown("# ⚡ Hardware Pipeline")
    st.caption("AI-Powered Hardware Design Automation · IEEE Compliant · Air-Gap Ready")
    st.divider()

    current_tab = render_tab_nav()

    if current_tab == "overview":
        render_overview()
    elif current_tab == "new":
        render_new_project()
    elif current_tab == "chat":
        render_design_chat()
    elif current_tab == "pipeline":
        render_pipeline()
    elif current_tab == "docs":
        render_documents()
    elif current_tab == "netlist":
        render_netlist()
    elif current_tab == "code":
        render_code_review()
    elif current_tab == "dashboard":
        render_dashboard()


if __name__ == "__main__":
    main()
