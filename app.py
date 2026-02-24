"""
Hardware Pipeline — Streamlit UI
High-level, professional UX with draft-approve flow for Phase 1.
"""

import asyncio
import logging
from pathlib import Path

import httpx
import streamlit as st

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hardware Pipeline",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Global */
[data-testid="stAppViewContainer"] { background: #0f1117; }
[data-testid="stSidebar"] { background: #161b22; border-right: 1px solid #30363d; }

/* Phase status pills */
.phase-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    margin: 2px 0;
}
.phase-pending  { background:#21262d; color:#8b949e; }
.phase-active   { background:#1f4e8a; color:#58a6ff; }
.phase-done     { background:#1a4731; color:#3fb950; }
.phase-failed   { background:#4c1d1d; color:#f85149; }

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
    padding: 8px 4px;
    font-size: 11px;
    font-weight: 600;
    border-top: 3px solid #30363d;
    color: #8b949e;
}
.pipe-step.done  { border-color: #3fb950; color: #3fb950; }
.pipe-step.active{ border-color: #58a6ff; color: #58a6ff; }

/* Draft approval card */
.approval-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
    margin: 12px 0;
}

/* Metric cards */
.metric-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 14px 18px;
    text-align: center;
}
.metric-card .metric-value { font-size: 28px; font-weight: 700; color: #58a6ff; }
.metric-card .metric-label { font-size: 12px; color: #8b949e; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ─────────────────────────────────────────────────────────────────

PHASE_META = [
    ("P1",  "1", "Requirements",    "agents.requirements_agent"),
    ("P2",  "2", "HRS Document",    None),
    ("P3",  "3", "Compliance",      None),
    ("P4",  "4", "Netlist",         None),
    ("P5",  "5", "PCB (Manual)",    None),
    ("P6",  "6", "GLR",             None),
    ("P7",  "7", "FPGA (Manual)",   None),
    ("P8a", "8a","SRS",             None),
    ("P8b", "8b","SDD",             None),
    ("P8c", "8c","Code + Review",   None),
]

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


# ─── Sidebar ─────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("## ⚡ Hardware Pipeline")
        st.caption("AI-Powered Hardware Design Automation")
        st.divider()

        # Current project info
        if "current_project" in st.session_state:
            proj = st.session_state.current_project
            st.markdown(f"**Project:** {proj.get('name', '—')}")
            st.markdown(f"**Type:** `{proj.get('design_type', '—')}`")
            st.divider()

            # Phase status list
            st.markdown("### Pipeline Status")
            statuses = proj.get("phase_statuses", {})
            for pid, num, name, _ in PHASE_META:
                status = _phase_status(statuses, pid)
                icon = {"pending": "⬜", "in_progress": "🔄",
                        "completed": "✅", "failed": "❌", "skipped": "⏭️"}.get(status, "⬜")
                css  = {"pending": "phase-pending", "in_progress": "phase-active",
                        "completed": "phase-done", "failed": "phase-failed"}.get(status, "phase-pending")
                st.markdown(
                    f'<span class="phase-pill {css}">{icon} P{num} {name}</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No project loaded. Create one to begin.")

        st.divider()

        # System info
        st.markdown("### System")
        try:
            from config import settings
            mode_color = "#f85149" if settings.is_air_gapped else "#3fb950"
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
    st.markdown("")

    # Pipeline visual
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

    # Feature cards
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

    # Quick actions
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
    st.markdown("")

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
                help="Helps the AI tailor component recommendations",
            )
            st.markdown("")
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


# ─── Design Chat (Phase 1) ────────────────────────────────────────────────────

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

    # ── Phase complete banner ─────────────────────────────────────────────────
    if st.session_state.get("phase1_complete"):
        st.success("✅ **Phase 1 Complete!** All requirement documents generated.")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("📄 View Documents", use_container_width=True, type="primary"):
                st.query_params["tab"] = "docs"
                st.rerun()
        with c2:
            if st.button("🔌 View Netlist", use_container_width=True):
                st.query_params["tab"] = "netlist"
                st.rerun()
        with c3:
            if st.button("🔄 New Chat", use_container_width=True):
                _reset_chat()
                st.rerun()
        st.divider()

    # Initialise chat
    if "chat_messages" not in st.session_state:
        _reset_chat()

    # ── Chat history ──────────────────────────────────────────────────────────
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Approval buttons (shown when a draft is pending) ──────────────────────
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

    # ── Chat input ────────────────────────────────────────────────────────────
    elif not st.session_state.get("phase1_complete"):
        if user_input := st.chat_input("Describe your hardware design…"):
            _handle_chat_input(user_input)


def _handle_chat_input(user_input: str):
    """Process a user message through the RequirementsAgent."""
    st.session_state.chat_messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("⚡ Generating draft…"):
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

                response = result.get("response", "Processing…")
                st.markdown(response)
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": response}
                )

                # Update draft state
                if result.get("draft_pending"):
                    st.session_state.draft_pending = True
                    st.session_state.current_draft = result.get("draft", {})

                # Phase complete
                if result.get("phase_complete"):
                    st.session_state.phase1_complete = True
                    st.session_state.draft_pending = False
                    st.balloons()
                    st.success("✅ **Phase 1 Complete!**")
                    if result.get("outputs"):
                        with st.expander("📁 Generated Files", expanded=True):
                            for fname in result["outputs"]:
                                st.markdown(f"- 📄 `{fname}`")
                    st.rerun()

            except ImportError as e:
                st.error(f"Module missing: {e}")
            except Exception as e:
                logger.exception("Chat error")
                st.error(f"Error: {e}")


# ─── Documents ───────────────────────────────────────────────────────────────

def render_documents():
    st.markdown("## 📄 Generated Documents")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", "output"))

    if not output_dir.exists():
        st.info("No documents yet — complete Phase 1 in Design Chat.")
        return

    md_files = sorted(output_dir.glob("*.md"))
    if not md_files:
        st.info("No documents generated yet.")
        return

    # Summary metrics row
    cols = st.columns(len(md_files) if len(md_files) <= 4 else 4)
    for i, f in enumerate(md_files[:4]):
        with cols[i]:
            size_kb = f.stat().st_size / 1024
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-value">{size_kb:.1f}KB</div>'
                f'<div class="metric-label">{f.name}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    st.markdown("")

    # Document viewer
    for md_file in md_files:
        with st.expander(f"📄 {md_file.stem.replace('_', ' ').title()}", expanded=False):
            content = md_file.read_text(encoding="utf-8")
            tab_view, tab_raw = st.tabs(["Rendered", "Raw Markdown"])
            with tab_view:
                st.markdown(content)
            with tab_raw:
                st.code(content, language="markdown")
            st.download_button(
                label=f"⬇️ Download {md_file.name}",
                data=content,
                file_name=md_file.name,
                mime="text/markdown",
                key=f"dl_{md_file.name}",
            )


# ─── Netlist Viewer ──────────────────────────────────────────────────────────

def render_netlist():
    st.markdown("## 🔌 Netlist Viewer — Phase 4")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", "output"))
    netlist_file = output_dir / "netlist_visual.md"

    if netlist_file.exists():
        content = netlist_file.read_text(encoding="utf-8")
        st.markdown(content)
        st.download_button("⬇️ Download Netlist", data=content,
                           file_name="netlist_visual.md", mime="text/markdown")
    else:
        st.info("Netlist not generated yet — complete Phases 1–4 first.")
        st.markdown("""
**Phase 4 will generate:**
- `netlist.json` — machine-readable netlist
- `netlist_visual.md` — Mermaid connectivity diagram
- `block_diagram.svg` — exportable diagram

Complete Phase 1 (Design Chat) to begin.
""")


# ─── Code Review ─────────────────────────────────────────────────────────────

def render_code_review():
    st.markdown("## 🔍 Code Review — Phase 8c")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", "output"))
    review_file = output_dir / "code_review_report.md"

    if review_file.exists():
        content = review_file.read_text(encoding="utf-8")
        st.markdown(content)
        st.download_button("⬇️ Download Review Report", data=content,
                           file_name="code_review_report.md", mime="text/markdown")
    else:
        st.info("Code not generated yet — complete all phases first.")
        st.markdown("""
**Phase 8c will generate:**
- `drivers/` — C/C++ device driver source files
- `tests/` — unit and integration tests
- `code_review_report.md` — quality score + MISRA-C compliance report
""")


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

        # Summary metrics
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

        # Project list
        for p in projects:
            phase_statuses = p.phase_statuses or {}
            completed_phases = sum(
                1 for v in phase_statuses.values() if v.get("status") == "completed"
            )
            total_phases = 8  # automated phases

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
                    # Mini phase progress
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
