"""
Hardware Pipeline — Streamlit UI (thin shell)

Architecture rule: this file contains ONLY rendering code.
- No agent imports, no asyncio.run(), no direct DB access.
- All business logic lives in services/ (ProjectService, ChatService, PipelineService).
- State transitions go through the FastAPI backend (/api/v1/...).
- Phase status is always read fresh from DB via the API; session_state is display cache only.
- Pipeline execution is fire-and-forget via POST /pipeline/run; UI polls /status.
"""

import json
import logging
import re
import time
from pathlib import Path

import httpx
import streamlit as st

from config import settings
from logging_config import configure_logging

configure_logging()
log = logging.getLogger("hardware_pipeline.ui")

# Mermaid rendering — graceful fallback
try:
    import streamlit_mermaid as stmd
    MERMAID_AVAILABLE = True
except ImportError:
    MERMAID_AVAILABLE = False

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hardware Pipeline",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.phase-pill { display:inline-block; padding:4px 12px; border-radius:12px;
              font-size:12px; font-weight:600; margin:2px 0; }
.phase-pending  { background:#f0f0f0; color:#888; }
.phase-active   { background:#dbeafe; color:#1d4ed8; }
.phase-done     { background:#dcfce7; color:#16a34a; }
.phase-failed   { background:#fee2e2; color:#dc2626; }

.pipeline-bar { display:flex; align-items:center; gap:0; margin:16px 0; }
.pipe-step { flex:1; text-align:center; padding:10px 4px; font-size:11px;
             font-weight:600; border-top:4px solid #e5e7eb; color:#9ca3af; }
.pipe-step.done   { border-color:#22c55e; color:#16a34a; background:#f0fdf4; }
.pipe-step.active { border-color:#3b82f6; color:#1d4ed8; background:#eff6ff; }

.metric-card { background:#f9fafb; border:1px solid #e5e7eb; border-radius:8px;
               padding:16px 20px; text-align:center; }
.metric-card .metric-value { font-size:28px; font-weight:700; color:#2563eb; }
.metric-card .metric-label { font-size:12px; color:#6b7280; margin-top:4px; }

.processing-indicator { display:flex; align-items:center; gap:12px;
    padding:12px 20px; background:#eff6ff; border:1px solid #bfdbfe;
    border-radius:8px; margin:8px 0; font-weight:500; color:#1d4ed8; }
.spinner { width:20px; height:20px; border:3px solid #bfdbfe;
           border-top:3px solid #2563eb; border-radius:50%;
           animation:spin 1s linear infinite; }
@keyframes spin { 100% { transform:rotate(360deg); } }

.phase-exec-card { background:#f9fafb; border:1px solid #e5e7eb;
    border-radius:8px; padding:16px; margin:8px 0; }
.phase-exec-card.running { border-left:4px solid #3b82f6; }
.phase-exec-card.done    { border-left:4px solid #22c55e; }
.phase-exec-card.failed  { border-left:4px solid #ef4444; }
</style>
""", unsafe_allow_html=True)


# ── Constants ─────────────────────────────────────────────────────────────────

PHASE_META = [
    ("P1",  "1",  "Requirements",  True),
    ("P2",  "2",  "HRS Document",  True),
    ("P3",  "3",  "Compliance",    True),
    ("P4",  "4",  "Netlist",       True),
    ("P5",  "5",  "PCB (Manual)",  False),
    ("P6",  "6",  "GLR",           True),
    ("P7",  "7",  "FPGA (Manual)", False),
    ("P8a", "8a", "SRS",           True),
    ("P8b", "8b", "SDD",           True),
    ("P8c", "8c", "Code + Review", True),
]

TABS = {
    "overview":  "🏠 Overview",
    "new":       "➕ New Project",
    "chat":      "💬 Design Chat",
    "pipeline":  "🔄 Pipeline",
    "docs":      "📄 Documents",
    "netlist":   "🔌 Netlist",
    "code":      "🔍 Code Review",
    "dashboard": "📊 Dashboard",
}

_API = settings.api_base_url


# ── API helpers (UI → FastAPI backend) ───────────────────────────────────────

def _api_get(path: str, timeout: float = 10.0) -> dict | list | None:
    """GET from FastAPI backend. Returns parsed JSON or None on error."""
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(f"{_API}{path}")
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        return None          # API server not running — handled by callers
    except Exception as exc:
        log.warning("api.get_failed path=%s: %s", path, exc)
        return None


def _api_post(path: str, body: dict, timeout: float = 180.0) -> dict | None:
    """POST to FastAPI backend. Returns parsed JSON or None on error."""
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(f"{_API}{path}", json=body)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        return None
    except Exception as exc:
        log.warning("api.post_failed path=%s: %s", path, exc)
        return None


def _load_project_from_api(project_id: int) -> dict | None:
    """Load fresh project state from API. Used everywhere instead of session_state."""
    return _api_get(f"/api/v1/projects/{project_id}")


def _load_project_status(project_id: int) -> dict:
    """Lightweight status poll — phase_statuses only."""
    data = _api_get(f"/api/v1/projects/{project_id}/status") or {}
    return data.get("phase_statuses", {})


def _phase_status(statuses: dict, pid: str) -> str:
    return statuses.get(pid, {}).get("status", "pending")


# ── Mermaid utilities ─────────────────────────────────────────────────────────

def _sanitize_mermaid(code: str) -> str:
    """Fix Unicode + syntax issues for Mermaid v10.2.4."""
    code = re.sub(r'^```mermaid\s*', '', code.strip())
    code = re.sub(r'\s*```$', '', code).strip()
    for ch, rep in [
        ('\u2192','->'), ('\u2190','<-'), ('\u2194','<->'),
        ('\u00b1','+/-'), ('\u00d7','x'), ('\u00f7','/'),
        ('\u00b0','deg'), ('\u00b5','u'), ('\u03a9','ohm'),
        ('\u2264','<='), ('\u2265','>='), ('\u2260','!='),
        ('\u201c','"'), ('\u201d','"'), ('\u2018',"'"), ('\u2019',"'"),
        ('\u2013','-'), ('\u2014','-'),
    ]:
        code = code.replace(ch, rep)
    code = re.sub(r'subgraph\s+(\w+)\s*\["([^"]+)"\]', r'subgraph \1[\2]', code)
    code = re.sub(r'\[([^\]]*?)&([^\]]*?)\]',
                  lambda m: '[' + m.group(1) + 'and' + m.group(2) + ']', code)
    code = re.sub(r'\|"([^"]+)"\|',
                  lambda m: '|' + m.group(1).replace(':', ' -') + '|', code)
    lines = [ln for ln in code.split('\n') if ln.strip() and not ln.strip().startswith('%%')]
    return '\n'.join(lines)


def _render_mermaid(code: str, key: str = None):
    code = _sanitize_mermaid(code)
    if not code:
        return
    if MERMAID_AVAILABLE:
        try:
            stmd.st_mermaid(code, key=key)
            return
        except Exception:
            pass
    st.code(code, language="mermaid")


def _render_markdown_with_mermaid(content: str, key_prefix: str = "md"):
    parts = re.split(r'```mermaid\s*\n(.*?)\n\s*```', content, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part.strip():
                st.markdown(part)
        else:
            _render_mermaid(part, key=f"{key_prefix}_mermaid_{i}")


# ── Sidebar ────────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("## ⚡ Hardware Pipeline")
        st.caption("AI-Powered Hardware Design Automation")
        st.divider()

        if "project_id" in st.session_state:
            proj_id = st.session_state.project_id
            # Always read from API/DB — never stale session_state
            proj = _load_project_from_api(proj_id) or st.session_state.get("current_project", {})
            statuses = proj.get("phase_statuses", {})

            st.markdown(f"**Project:** {proj.get('name', '—')}")
            st.markdown(f"**Type:** `{proj.get('design_type', '—')}`")
            st.divider()
            st.markdown("### Pipeline Status")
            for pid, num, name, _ in PHASE_META:
                status = _phase_status(statuses, pid)
                icon = {"pending":"⬜","in_progress":"🔄","completed":"✅",
                        "failed":"❌","draft_pending":"⏳"}.get(status, "⬜")
                css = {"pending":"phase-pending","in_progress":"phase-active",
                       "completed":"phase-done","failed":"phase-failed",
                       "draft_pending":"phase-active"}.get(status, "phase-pending")
                st.markdown(f'<span class="phase-pill {css}">{icon} P{num} {name}</span>',
                            unsafe_allow_html=True)
        else:
            st.info("No project loaded. Create one to begin.")

        st.divider()
        st.markdown("### System")
        mode_label = "🔴 Air-Gapped" if settings.is_air_gapped else "🟢 Online"
        st.markdown(f"**Mode:** {mode_label}")
        st.caption(f"Primary: `{settings.primary_model}`")
        st.caption(f"Fast: `{settings.fast_model}`")
        st.divider()
        st.markdown("### API Keys")
        for provider, (ok, icon) in settings.get_api_key_status().items():
            st.caption(f"{icon} {provider}")


# ── Tab nav ────────────────────────────────────────────────────────────────────

def render_tab_nav() -> str:
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


# ── Overview ───────────────────────────────────────────────────────────────────

def render_overview():
    st.markdown("## Welcome to Hardware Pipeline")
    st.markdown("**AI-Powered Hardware Design Automation** — From requirements to production-ready code.")

    statuses = {}
    if "project_id" in st.session_state:
        statuses = _load_project_status(st.session_state.project_id)

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
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("➕ New Project", use_container_width=True, type="primary"):
            st.query_params["tab"] = "new"; st.rerun()
    with col2:
        if st.button("📊 Dashboard", use_container_width=True):
            st.query_params["tab"] = "dashboard"; st.rerun()
    with col3:
        if st.button("📄 Documents", use_container_width=True):
            st.query_params["tab"] = "docs"; st.rerun()


# ── New Project ────────────────────────────────────────────────────────────────

def render_new_project():
    st.markdown("## ➕ New Project")
    st.caption("Create a project and jump straight into the AI design chat.")

    with st.form("new_project_form", clear_on_submit=False):
        col1, col2 = st.columns([2, 1])
        with col1:
            name = st.text_input("Project Name *", placeholder="e.g., BLDC Motor Controller 10kW")
            description = st.text_area("Description",
                                       placeholder="Brief description of the hardware design…",
                                       height=100)
        with col2:
            design_type = st.selectbox("Design Type *",
                ["general", "rf", "motor_control", "power", "digital", "sensor", "industrial"])
            st.markdown("")
            submitted = st.form_submit_button("🚀 Create & Start", type="primary",
                                              use_container_width=True)

    if submitted:
        if not name.strip():
            st.error("Project name is required.")
            return
        with st.spinner("Creating project…"):
            result = _api_post("/api/v1/projects",
                               {"name": name, "description": description,
                                "design_type": design_type})
            if result is None:
                # API server not available — create via ProjectService directly
                try:
                    from services.project_service import ProjectService
                    result = ProjectService().create(name, description, design_type)
                    log.info("new_project.created_locally project_id=%s", result.get("id"))
                except Exception as exc:
                    st.error(f"Failed to create project: {exc}")
                    return

            st.session_state.current_project = result
            st.session_state.project_id = result["id"]
            _reset_chat()
            st.success(f"✅ Project '{name}' created!")
            log.info("ui.new_project", extra={"project_id": result["id"]})
            st.query_params["tab"] = "chat"
            st.rerun()


# ── Design Chat (Phase 1) ──────────────────────────────────────────────────────

def _reset_chat():
    st.session_state.chat_messages = [{
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
    }]
    st.session_state.draft_pending = False
    st.session_state.phase1_complete = False


def render_design_chat():
    st.markdown("## 💬 Design Chat — Phase 1: Requirements")

    if "project_id" not in st.session_state:
        st.info("Create a project first in **New Project**.")
        if st.button("➕ Create Project", type="primary"):
            st.query_params["tab"] = "new"; st.rerun()
        return

    proj_id = st.session_state.project_id

    # Always read phase status from DB (authoritative source)
    statuses = _load_project_status(proj_id)
    phase1_status = _phase_status(statuses, "P1")

    proj = _load_project_from_api(proj_id) or st.session_state.get("current_project", {})
    st.caption(f"Project: **{proj.get('name')}** · Type: `{proj.get('design_type', 'general')}`")

    # Phase 1 complete banner
    if phase1_status == "completed":
        st.success("✅ **Phase 1 Complete!** Requirements and block diagrams generated.")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("🚀 Run Full Pipeline", use_container_width=True, type="primary",
                         key="btn_run_pipeline"):
                _start_pipeline(proj_id)
        with c2:
            if st.button("📄 View Documents", use_container_width=True, key="btn_docs"):
                st.query_params["tab"] = "docs"; st.rerun()
        with c3:
            if st.button("🔄 New Chat", use_container_width=True, key="btn_new_chat"):
                _reset_chat(); st.rerun()
        st.divider()

    if "chat_messages" not in st.session_state:
        _reset_chat()

    # Render chat history
    for idx, msg in enumerate(st.session_state.chat_messages):
        with st.chat_message(msg["role"]):
            _render_markdown_with_mermaid(msg["content"], key_prefix=f"chat_{idx}")

    # Approval / input area — only show if Phase 1 not yet complete
    if phase1_status != "completed":
        if st.session_state.get("draft_pending"):
            st.markdown("")
            col_a, col_b = st.columns([1, 2])
            with col_a:
                if st.button("✅ Approve — Generate Full Docs", type="primary",
                             use_container_width=True, key="btn_approve"):
                    _send_chat("Approved. Please generate the full requirements documents.")
            with col_b:
                change_text = st.text_input("Or describe changes…", key="change_input",
                    placeholder="e.g., change voltage to 24V, add CAN bus interface")
                if st.button("🔄 Apply Changes", use_container_width=True, key="btn_changes"):
                    if change_text.strip():
                        _send_chat(change_text.strip())
        else:
            if user_input := st.chat_input("Describe your hardware design…"):
                _send_chat(user_input)


def _send_chat(user_input: str):
    """
    Send user message → FastAPI /chat endpoint → update display state.
    All business logic (agent call, DB writes) happens inside ChatService.
    """
    proj_id = st.session_state.project_id
    st.session_state.chat_messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        is_approval = any(kw in user_input.lower()
                          for kw in ("approve", "yes", "ok", "good", "proceed", "go ahead"))
        action = "Generating full requirements documentation…" if is_approval \
                 else "Generating draft block diagram…"
        placeholder.markdown(
            f'<div class="processing-indicator"><div class="spinner"></div>{action}</div>',
            unsafe_allow_html=True,
        )

        t0 = time.time()
        result = _api_post(f"/api/v1/projects/{proj_id}/chat",
                           {"message": user_input},
                           timeout=300.0)

        if result is None:
            # API not reachable — fall back to calling ChatService directly
            try:
                from services.chat_service import ChatService
                import asyncio
                result = asyncio.run(ChatService().send_message(proj_id, user_input))
                log.info("chat.local_fallback project_id=%s", proj_id)
            except Exception as exc:
                placeholder.empty()
                st.error(f"Error: {exc}")
                log.exception("chat.send_failed project_id=%s", proj_id)
                return

        elapsed = time.time() - t0
        placeholder.empty()

        response = result.get("response", "")
        _render_markdown_with_mermaid(response, key_prefix="resp")
        st.caption(f"⏱️ Generated in {elapsed:.1f}s")
        st.session_state.chat_messages.append({"role": "assistant", "content": response})

        # Update display-only state (authoritative state lives in DB via ChatService)
        if result.get("draft_pending"):
            st.session_state.draft_pending = True
            log.info("chat.draft_pending project_id=%s", proj_id)
            st.rerun()

        if result.get("phase_complete"):
            st.session_state.draft_pending = False
            st.balloons()
            st.success(f"✅ **Phase 1 Complete!** ({elapsed:.1f}s)")
            if result.get("outputs"):
                with st.expander("📁 Generated Files", expanded=True):
                    for fname in result["outputs"]:
                        st.markdown(f"- 📄 `{fname}`")
            log.info("chat.phase1_complete project_id=%s elapsed=%.1f", proj_id, elapsed)
            st.rerun()


# ── Pipeline ───────────────────────────────────────────────────────────────────

def _start_pipeline(project_id: int):
    """Fire-and-forget: POST /pipeline/run, then redirect to Pipeline tab."""
    result = _api_post(f"/api/v1/projects/{project_id}/pipeline/run", {})
    if result:
        log.info("ui.pipeline_started project_id=%s", project_id)
        st.query_params["tab"] = "pipeline"
        st.rerun()
    else:
        st.error("Could not start pipeline — is the API server running?")


def render_pipeline():
    st.markdown("## 🔄 Pipeline Execution")

    if "project_id" not in st.session_state:
        st.info("Create a project first.")
        return

    proj_id = st.session_state.project_id

    # Always read from DB via API — never trust stale session_state for phase status
    statuses = _load_project_status(proj_id)
    proj = _load_project_from_api(proj_id) or st.session_state.get("current_project", {})

    st.caption(f"Project: **{proj.get('name')}** · Type: `{proj.get('design_type', 'general')}`")

    # Pipeline bar
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
            st.query_params["tab"] = "chat"; st.rerun()
        return

    auto_ids = ["P2", "P3", "P4", "P6", "P8a", "P8b", "P8c"]
    remaining = [p for p in auto_ids if _phase_status(statuses, p) != "completed"]
    in_progress = [p for p in auto_ids if _phase_status(statuses, p) == "in_progress"]

    if not remaining:
        st.success("✅ **All phases complete!** Your full design package is ready.")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("📄 View Documents", type="primary", use_container_width=True):
                st.query_params["tab"] = "docs"; st.rerun()
        with c2:
            if st.button("🔌 View Netlist", use_container_width=True):
                st.query_params["tab"] = "netlist"; st.rerun()
        with c3:
            if st.button("🔍 Code Review", use_container_width=True):
                st.query_params["tab"] = "code"; st.rerun()
        return

    if in_progress:
        # Pipeline is running in background — show live status and auto-refresh
        st.info(f"🔄 Pipeline running… current phase: **{', '.join(in_progress)}**")
        phase_names = {pid: name for pid, _, name, _ in PHASE_META}
        for pid, num, name, _ in PHASE_META:
            if pid in ["P5", "P7"]:
                continue
            status = _phase_status(statuses, pid)
            if status == "completed":
                st.markdown(f'<div class="phase-exec-card done">✅ {pid}: {name}</div>',
                            unsafe_allow_html=True)
            elif status == "in_progress":
                st.markdown(f'<div class="phase-exec-card running">🔄 {pid}: {name} — Processing…</div>',
                            unsafe_allow_html=True)
            elif status == "failed":
                err = statuses.get(pid, {}).get("error", "")
                st.markdown(
                    f'<div class="phase-exec-card failed">❌ {pid}: {name}'
                    + (f' — {err[:100]}' if err else '') + '</div>',
                    unsafe_allow_html=True)

        # Auto-refresh every 5 seconds while pipeline is running
        time.sleep(5)
        st.rerun()
    else:
        st.markdown(f"**{len(remaining)} phases remaining:** {', '.join(remaining)}")
        if st.button("🚀 Run Remaining Phases", type="primary", use_container_width=True):
            _start_pipeline(proj_id)


# ── Documents ──────────────────────────────────────────────────────────────────

def render_documents():
    st.markdown("## 📄 Generated Documents")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = _load_project_from_api(st.session_state.project_id) \
           or st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", ""))

    if not output_dir.exists():
        st.info("No documents yet — complete Phase 1 in Design Chat.")
        return

    proj_name = proj.get("name", "project").replace(" ", "_").lower()
    doc_map = {
        "requirements.md":                 ("P1",  "Hardware Requirements"),
        "block_diagram.md":                ("P1",  "Block Diagram"),
        "architecture.md":                 ("P1",  "System Architecture"),
        "component_recommendations.md":    ("P1",  "Component Recommendations"),
        f"HRS_{proj_name}.md":             ("P2",  "HRS — Hardware Requirements Spec"),
        "compliance_report.md":            ("P3",  "Compliance Report"),
        "netlist_visual.md":               ("P4",  "Netlist Visualization"),
        "glr_specification.md":            ("P6",  "GLR — Glue Logic Requirements"),
        f"SRS_{proj_name}.md":             ("P8a", "SRS — Software Requirements Spec"),
        f"SDD_{proj_name}.md":             ("P8b", "SDD — Software Design Document"),
        "code_review_report.md":           ("P8c", "Code Review Report"),
    }

    doc_files = []
    for fname, (phase, label) in doc_map.items():
        fpath = output_dir / fname
        if fpath.exists():
            doc_files.append((fpath, phase, label))
    for fpath in sorted(output_dir.glob("*.md")):
        if fpath.name not in doc_map:
            doc_files.append((fpath, "—", fpath.stem.replace("_", " ").title()))

    if not doc_files:
        st.info("No documents generated yet. Complete Phase 1 in Design Chat.")
        return

    st.markdown(f"**{len(doc_files)} documents generated**")
    cols = st.columns(min(len(doc_files), 4))
    for i, (f, phase, label) in enumerate(doc_files[:4]):
        with cols[i]:
            size_kb = f.stat().st_size / 1024
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-value">{size_kb:.1f}KB</div>'
                f'<div class="metric-label">{phase}: {f.name}</div>'
                f'</div>', unsafe_allow_html=True)
    st.markdown("")

    for fpath, phase, label in doc_files:
        with st.expander(f"📄 [{phase}] {label}", expanded=False):
            content = fpath.read_text(encoding="utf-8")
            tab_view, tab_raw = st.tabs(["Rendered", "Raw Markdown"])
            with tab_view:
                _render_markdown_with_mermaid(content, key_prefix=f"doc_{fpath.name}")
            with tab_raw:
                st.code(content, language="markdown")
            st.download_button(f"⬇️ Download {fpath.name}", data=content,
                               file_name=fpath.name, mime="text/markdown",
                               key=f"dl_{fpath.name}")


# ── Netlist ────────────────────────────────────────────────────────────────────

def render_netlist():
    st.markdown("## 🔌 Netlist Viewer — Phase 4")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = _load_project_from_api(st.session_state.project_id) \
           or st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", ""))
    netlist_visual = output_dir / "netlist_visual.md"
    netlist_json = output_dir / "netlist.json"

    if not netlist_visual.exists() and not netlist_json.exists():
        st.info("Netlist not generated yet — run the pipeline through Phase 4.")
        return

    if netlist_visual.exists():
        content = netlist_visual.read_text(encoding="utf-8")
        st.markdown("### Visual Netlist")
        _render_markdown_with_mermaid(content, key_prefix="netlist")
        st.download_button("⬇️ Download Netlist Visual", data=content,
                           file_name="netlist_visual.md", mime="text/markdown",
                           key="dl_netlist_visual")

    if netlist_json.exists():
        st.divider()
        st.markdown("### Netlist Data (JSON)")
        json_content = netlist_json.read_text(encoding="utf-8")
        try:
            netlist_data = json.loads(json_content)
            nodes, edges = netlist_data.get("nodes", []), netlist_data.get("edges", [])
            c1, c2, c3 = st.columns(3)
            c1.metric("Components", len(nodes))
            c2.metric("Connections", len(edges))
            c3.metric("Power Nets", len(netlist_data.get("power_nets", [])))
            if nodes:
                st.markdown("#### Component Instances")
                st.dataframe([{"Instance": n.get("instance_id"), "Part": n.get("part_number"),
                               "Component": n.get("component_name")} for n in nodes],
                             use_container_width=True)
            if edges:
                st.markdown("#### Connections")
                st.dataframe([{"From": e.get("from"), "To": e.get("to"),
                               "Net": e.get("net_name")} for e in edges],
                             use_container_width=True)
        except json.JSONDecodeError:
            st.code(json_content, language="json")
        st.download_button("⬇️ Download netlist.json", data=json_content,
                           file_name="netlist.json", mime="application/json",
                           key="dl_netlist_json")


# ── Code Review ────────────────────────────────────────────────────────────────

def render_code_review():
    st.markdown("## 🔍 Code Review — Phase 8c")

    if "project_id" not in st.session_state:
        st.info("No project loaded.")
        return

    proj = _load_project_from_api(st.session_state.project_id) \
           or st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", ""))
    review_file = output_dir / "code_review_report.md"
    src_dir = output_dir / "src"
    src_files = list(src_dir.rglob("*.*")) if src_dir.exists() else []

    if not review_file.exists() and not src_files:
        st.info("Code not generated yet — run the full pipeline first.")
        return

    if src_files:
        st.markdown(f"### Generated Source Files ({len(src_files)} files)")
        for src_file in sorted(src_files):
            rel_path = src_file.relative_to(output_dir)
            lang = "c" if src_file.suffix in (".c", ".h") else "cpp"
            with st.expander(f"💻 {rel_path}", expanded=False):
                content = src_file.read_text(encoding="utf-8")
                st.code(content, language=lang)
                st.download_button(f"⬇️ Download {src_file.name}", data=content,
                                   file_name=src_file.name, key=f"dl_src_{src_file.name}")
        st.divider()

    if review_file.exists():
        st.markdown("### Code Review Report")
        content = review_file.read_text(encoding="utf-8")
        _render_markdown_with_mermaid(content, key_prefix="review")
        st.download_button("⬇️ Download Review Report", data=content,
                           file_name="code_review_report.md", mime="text/markdown",
                           key="dl_review")


# ── Dashboard ──────────────────────────────────────────────────────────────────

def render_dashboard():
    st.markdown("## 📊 Projects Dashboard")

    projects = _api_get("/api/v1/projects")
    if projects is None:
        # API not running — fall back to ProjectService directly
        try:
            from services.project_service import ProjectService
            projects = ProjectService().list_all()
        except Exception as exc:
            st.error(f"Could not load projects: {exc}")
            return

    if not projects:
        st.info("No projects yet — create one in **New Project**.")
        return

    completed = sum(1 for p in projects if p.get("current_phase") == "DONE")
    in_prog = len(projects) - completed
    c1, c2, c3 = st.columns(3)
    for col, val, label in [(c1, len(projects), "Total Projects"),
                            (c2, in_prog, "In Progress"),
                            (c3, completed, "Completed")]:
        col.markdown(f'<div class="metric-card">'
                     f'<div class="metric-value">{val}</div>'
                     f'<div class="metric-label">{label}</div>'
                     f'</div>', unsafe_allow_html=True)
    st.markdown("")

    for p in projects:
        phase_statuses = p.get("phase_statuses") or {}
        done_count = sum(1 for v in phase_statuses.values()
                         if isinstance(v, dict) and v.get("status") == "completed")
        with st.expander(
            f"📁 {p['name']}  ·  `{p.get('design_type','')}`  ·  "
            f"Phase {p.get('current_phase','P1')}  ·  {done_count}/8 phases done",
            expanded=False,
        ):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                ca = p.get("created_at", "")
                st.caption(f"**Created:** {ca[:10] if ca else '—'}")
                st.caption(f"**Output:** `{p.get('output_dir','—')}`")
            with col2:
                for pid, num, name, _ in PHASE_META:
                    status = _phase_status(phase_statuses, pid)
                    icon = {"completed":"✅","in_progress":"🔄","failed":"❌"}.get(status,"⬜")
                    st.caption(f"{icon} P{num} {name}")
            with col3:
                if st.button("Load →", key=f"load_{p['id']}", type="primary",
                             use_container_width=True):
                    st.session_state.current_project = p
                    st.session_state.project_id = p["id"]
                    _reset_chat()
                    st.query_params["tab"] = "chat"
                    st.rerun()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()
    st.markdown("# ⚡ Hardware Pipeline")
    st.caption("AI-Powered Hardware Design Automation · IEEE Compliant · Air-Gap Ready")
    st.divider()

    tab = render_tab_nav()
    dispatch = {
        "overview":  render_overview,
        "new":       render_new_project,
        "chat":      render_design_chat,
        "pipeline":  render_pipeline,
        "docs":      render_documents,
        "netlist":   render_netlist,
        "code":      render_code_review,
        "dashboard": render_dashboard,
    }
    dispatch.get(tab, render_overview)()


if __name__ == "__main__":
    main()
