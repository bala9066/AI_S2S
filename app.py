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

# ── Project ID persistence (survives page refresh via URL params) ─────────────
if "project_id" not in st.session_state:
    _qp = st.query_params.get("project_id")
    if _qp:
        try:
            st.session_state.project_id = int(_qp)
        except (ValueError, TypeError):
            pass

# ── CSS (loaded from file, cached per session) ────────────────────────────────
@st.cache_resource
def _load_css():
    css_file = Path(__file__).parent / "static" / "style.css"
    if css_file.exists():
        return f"<style>{css_file.read_text(encoding='utf-8')}</style>"
    return ""

st.markdown(_load_css(), unsafe_allow_html=True)


# ── Constants ─────────────────────────────────────────────────────────────────

# Phase metadata: (id, display_num, short_name, description, auto_run)
PHASE_META = [
    ("P1",  "1",   "Design & Requirements",    "AI-powered design chat — block diagram + requirements capture",   True),
    ("P2",  "2",   "HRS Document",             "IEEE 29148 Hardware Requirements Specification",                   True),
    ("P3",  "3",   "Compliance Check",          "RoHS / REACH / FCC / MIL-STD rules engine",                       True),
    ("P4",  "4",   "Netlist Generation",        "Visual connectivity graph with DRC checks",                       True),
    ("P5",  "5",   "PCB Layout",               "Manual — Gerber/ODB++ export ready",                               False),
    ("P6",  "6",   "GLR Specification",         "Glue Logic Requirements for FPGA/CPLD",                           True),
    ("P7",  "7",   "FPGA Design",              "Manual — RTL/synthesis ready",                                     False),
    ("P8a", "8a",  "SRS Document",              "IEEE 830 Software Requirements Specification",                    True),
    ("P8b", "8b",  "SDD Document",              "IEEE 1016 Software Design Description",                           True),
    ("P8c", "8c",  "Code + Review",             "C/C++ drivers, test suites, AST review",                          True),
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

# ── Shared httpx client (connection pooling — avoids socket churn) ────────────
@st.cache_resource
def _get_http_client():
    return httpx.Client(timeout=10.0, base_url=_API)


# ── API helpers ───────────────────────────────────────────────────────────────

def _api_get(path: str, timeout: float = 10.0):
    try:
        r = _get_http_client().get(path, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        return None
    except Exception as exc:
        log.warning("api.get_failed path=%s: %s", path, exc)
        return None


def _api_post(path: str, body: dict, timeout: float = 180.0):
    try:
        r = _get_http_client().post(path, json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        return None
    except Exception as exc:
        log.warning("api.post_failed path=%s: %s", path, exc)
        return None


def _load_project(project_id: int):
    return _api_get(f"/api/v1/projects/{project_id}")


def _load_status(project_id: int) -> dict:
    """Load phase statuses — always fresh from DB via API."""
    data = _api_get(f"/api/v1/projects/{project_id}/status") or {}
    return data.get("phase_statuses", {})


def _phase_status(statuses: dict, pid: str) -> str:
    return statuses.get(pid, {}).get("status", "pending")


# ── Mermaid utilities ─────────────────────────────────────────────────────────

def _sanitize_mermaid(code: str) -> str:
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
        st.markdown("""
        <div class="sidebar-brand">
          <h1>⚡ Hardware Pipeline</h1>
          <p>AI-Powered EE Design Automation</p>
        </div>
        """, unsafe_allow_html=True)

        if "project_id" in st.session_state:
            proj_id = st.session_state.project_id
            proj = _load_project(proj_id) or st.session_state.get("current_project", {})
            statuses = proj.get("phase_statuses", {})

            st.markdown(f"""
            <div class="proj-card">
              <div class="pn">📁 {proj.get('name', '—')}</div>
              <div class="pt">{proj.get('design_type', '—')} design</div>
            </div>
            """, unsafe_allow_html=True)

            done = sum(1 for pid, _, _, _, auto in PHASE_META if auto
                       and _phase_status(statuses, pid) == "completed")
            total = sum(1 for _, _, _, _, auto in PHASE_META if auto)
            pct = int(done / total * 100) if total else 0
            st.markdown(f"""
            <div class="prog-track"><div class="prog-fill" style="width:{pct}%"></div></div>
            <div class="prog-label">{done}/{total} phases · {pct}%</div>
            """, unsafe_allow_html=True)

            st.markdown("**Pipeline Status**")
            for pid, num, name, _, _ in PHASE_META:
                status = _phase_status(statuses, pid)
                icon = {"pending": "○", "in_progress": "◉", "completed": "●",
                        "failed": "✕", "draft_pending": "◑"}.get(status, "○")
                css = {"completed": "done", "in_progress": "active", "failed": "failed"}.get(status, "")
                st.markdown(f'<div class="phase-pill {css}">{icon} P{num} {name}</div>',
                            unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="alert-info">No project loaded.<br>Create one to begin.</div>
            """, unsafe_allow_html=True)

        # System info
        st.markdown("---")
        online = not settings.is_air_gapped
        mode = "Online" if online else "Air-Gapped"
        dot = "🟢" if online else "🔴"
        st.markdown(f"""
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
          {dot} <strong style="color:var(--text-secondary)">{mode}</strong>
          &nbsp;·&nbsp;<span class="tag">{settings.primary_model}</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">API KEYS</div>',
                    unsafe_allow_html=True)
        for provider, (ok, _) in settings.get_api_key_status().items():
            cls = "ok" if ok else "off"
            icon = "✓" if ok else "—"
            st.markdown(f'<span class="key-badge {cls}">{icon} {provider}</span>',
                        unsafe_allow_html=True)


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
    st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)
    return current


# ── Overview ───────────────────────────────────────────────────────────────────

def render_overview():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">⚡</div>
      <div>
        <div class="ph-title">Hardware Pipeline</div>
        <div class="ph-sub">AI-Powered Hardware Design · IEEE Compliant · Air-Gap Ready</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    statuses = {}
    if "project_id" in st.session_state:
        statuses = _load_status(st.session_state.project_id)

    st.markdown("""
    <div class="feature-grid">
      <div class="feature-card">
        <div class="fc-icon">📋</div>
        <div class="fc-title">IEEE Standards</div>
        <div class="fc-desc">HRS (29148), SRS (830), SDD (1016) — audit-ready, fully traceable</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">🔌</div>
        <div class="fc-title">Smart Netlist</div>
        <div class="fc-desc">Visual connectivity graph before PCB layout with DRC checks</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">✅</div>
        <div class="fc-title">Compliance</div>
        <div class="fc-desc">RoHS / REACH / FCC rules engine — PASS / FAIL / REVIEW</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">💻</div>
        <div class="fc-title">Code Generation</div>
        <div class="fc-desc">C/C++ drivers + test suites, reviewed with AST analysis</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("➕ Start New Project", use_container_width=True, type="primary"):
            st.query_params["tab"] = "new"; st.rerun()
    with col2:
        if st.button("📊 View Dashboard", use_container_width=True):
            st.query_params["tab"] = "dashboard"; st.rerun()
    with col3:
        if st.button("📄 Browse Documents", use_container_width=True):
            st.query_params["tab"] = "docs"; st.rerun()


# ── New Project ────────────────────────────────────────────────────────────────

def render_new_project():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">➕</div>
      <div>
        <div class="ph-title">New Project</div>
        <div class="ph-sub">Create a project and jump into the AI design chat</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Load existing projects
    existing = _api_get("/api/v1/projects") or []
    if existing:
        st.markdown("##### 📂 Load Existing Project")
        proj_names = {p["id"]: f"{p['name']} ({p['design_type']})" for p in existing}
        selected = st.selectbox("Select a project", options=list(proj_names.keys()),
                                format_func=lambda x: proj_names[x], key="load_existing")
        if st.button("📂 Load Project", use_container_width=True):
            st.session_state.project_id = selected
            st.session_state.current_project = next(p for p in existing if p["id"] == selected)
            st.query_params["project_id"] = str(selected)
            st.query_params["tab"] = "chat"
            _reset_chat()
            st.rerun()
        st.markdown("---")

    st.markdown("##### ✨ Create New Project")
    with st.form("new_project_form", clear_on_submit=False):
        col1, col2 = st.columns([2, 1])
        with col1:
            name = st.text_input("Project Name *", placeholder="e.g., BLDC Motor Controller 10kW")
            description = st.text_area("Description",
                                       placeholder="Brief description of the hardware design…",
                                       height=110)
        with col2:
            design_type = st.selectbox("Design Type *",
                ["general", "rf", "motor_control", "power", "digital", "sensor", "industrial"],
                format_func=lambda x: {
                    "general": "⚙️ General", "rf": "📡 RF / Wireless",
                    "motor_control": "⚡ Motor Control", "power": "🔋 Power Electronics",
                    "digital": "💻 Digital Logic", "sensor": "📊 Sensor / IoT",
                    "industrial": "🏭 Industrial",
                }.get(x, x))
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("🚀 Create & Start", type="primary",
                                              use_container_width=True)

    if submitted:
        if not name.strip():
            st.markdown('<div class="alert-warn">⚠️ Project name is required.</div>',
                        unsafe_allow_html=True)
            return
        with st.spinner("Creating project…"):
            result = _api_post("/api/v1/projects",
                               {"name": name, "description": description,
                                "design_type": design_type})
            if result is None:
                try:
                    from services.project_service import ProjectService
                    result = ProjectService().create(name, description, design_type)
                except Exception as exc:
                    st.error(f"Failed to create project: {exc}")
                    return

            st.session_state.current_project = result
            st.session_state.project_id = result["id"]
            st.query_params["project_id"] = str(result["id"])
            _reset_chat()
            st.markdown(f'<div class="alert-success">✅ Project <strong>{name}</strong> created!</div>',
                        unsafe_allow_html=True)
            log.info("ui.new_project", extra={"project_id": result["id"]})
            time.sleep(0.5)
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
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">💬</div>
      <div>
        <div class="ph-title">Design Chat</div>
        <div class="ph-sub">Phase 1 · AI Requirements Capture</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if "project_id" not in st.session_state:
        st.markdown('<div class="alert-info">Create a project first in <strong>New Project</strong>.</div>',
                    unsafe_allow_html=True)
        if st.button("➕ Create Project", type="primary"):
            st.query_params["tab"] = "new"; st.rerun()
        return

    proj_id = st.session_state.project_id
    statuses = _load_status(proj_id)
    phase1_status = _phase_status(statuses, "P1")
    proj = _load_project(proj_id) or st.session_state.get("current_project", {})

    dt_icons = {"motor_control": "⚡", "rf": "📡", "power": "🔋", "digital": "💻",
                "sensor": "📊", "industrial": "🏭", "general": "⚙️"}
    dt = proj.get("design_type", "general")
    st.markdown(
        f'<div style="margin-bottom:16px;font-size:13px;color:var(--text-muted);">'
        f'{dt_icons.get(dt, "⚙️")} <strong>{proj.get("name", "")}</strong>'
        f' &nbsp;·&nbsp; <span class="tag">{dt}</span></div>',
        unsafe_allow_html=True)

    # Phase 1 complete banner
    if phase1_status == "completed":
        st.markdown('<div class="alert-success">✅ <strong>Phase 1 Complete!</strong> '
                    'Requirements and block diagrams generated. Ready to run the pipeline.</div>',
                    unsafe_allow_html=True)
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
        st.markdown("---")

    if "chat_messages" not in st.session_state:
        _reset_chat()

    for idx, msg in enumerate(st.session_state.chat_messages):
        with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
            _render_markdown_with_mermaid(msg["content"], key_prefix=f"chat_{idx}")

    if phase1_status != "completed":
        if st.session_state.get("draft_pending"):
            st.markdown("""
            <div class="alert-info">📋 <strong>Draft ready for review.</strong>
            Approve to generate full IEEE documentation, or request changes below.</div>
            """, unsafe_allow_html=True)
            col_a, col_b = st.columns([1, 2])
            with col_a:
                if st.button("✅ Approve — Generate Full Docs", type="primary",
                             use_container_width=True, key="btn_approve"):
                    _send_chat("Approved. Please generate the full requirements documents.")
            with col_b:
                change_text = st.text_input("Request changes…", key="change_input",
                                            placeholder="e.g., change voltage to 24V, add CAN bus")
                if st.button("🔄 Apply Changes", use_container_width=True, key="btn_changes"):
                    if change_text.strip():
                        _send_chat(change_text.strip())
        else:
            if user_input := st.chat_input("Describe your hardware design…"):
                _send_chat(user_input)


def _send_chat(user_input: str):
    proj_id = st.session_state.project_id
    st.session_state.chat_messages.append({"role": "user", "content": user_input})

    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    with st.chat_message("assistant", avatar="🤖"):
        placeholder = st.empty()
        is_approval = any(kw in user_input.lower()
                          for kw in ("approve", "yes", "ok", "good", "proceed", "go ahead"))
        action = "Generating full requirements documentation…" if is_approval \
                 else "Generating draft block diagram…"
        placeholder.markdown(
            f'<div class="proc-indicator"><div class="proc-spinner"></div>{action}</div>',
            unsafe_allow_html=True)

        t0 = time.time()
        result = _api_post(f"/api/v1/projects/{proj_id}/chat",
                           {"message": user_input}, timeout=300.0)

        if result is None:
            try:
                from services.chat_service import ChatService
                import asyncio
                result = asyncio.run(ChatService().send_message(proj_id, user_input))
            except Exception as exc:
                placeholder.empty()
                st.error(f"Error: {exc}")
                return

        elapsed = time.time() - t0
        placeholder.empty()

        response = result.get("response", "")
        _render_markdown_with_mermaid(response, key_prefix="resp")
        st.caption(f"⏱️ Generated in {elapsed:.1f}s")
        st.session_state.chat_messages.append({"role": "assistant", "content": response})

        if result.get("draft_pending"):
            st.session_state.draft_pending = True
            st.rerun()

        if result.get("phase_complete"):
            st.session_state.draft_pending = False
            st.balloons()
            st.markdown(
                f'<div class="alert-success">🎉 <strong>Phase 1 Complete!</strong> '
                f'Generated in {elapsed:.1f}s. Full documentation ready.</div>',
                unsafe_allow_html=True)
            if result.get("outputs"):
                with st.expander("📁 Generated Files", expanded=True):
                    for fname in result["outputs"]:
                        st.markdown(f'<span class="tag">📄 {fname}</span>', unsafe_allow_html=True)
            st.rerun()


# ── Pipeline (Split into Individual Phase Cards) ─────────────────────────────

def _start_pipeline(project_id: int):
    result = _api_post(f"/api/v1/projects/{project_id}/pipeline/run", {})
    if result:
        st.query_params["tab"] = "pipeline"
        st.rerun()
    else:
        st.error("Could not start pipeline — is the API server running?")


def _phase_card_html(pid, num, name, desc, status, statuses, auto):
    """Render a single phase as a glassmorphism card with rich status info."""
    status_cls = {"completed": "completed", "in_progress": "running",
                  "failed": "failed", "draft_pending": "running"}.get(status, "")
    badge_cls = {"completed": "badge-completed", "in_progress": "badge-running",
                 "failed": "badge-failed", "draft_pending": "badge-running"}.get(status, "badge-pending")
    status_label = {"pending": "Pending", "in_progress": "Running…",
                    "completed": "✓ Complete", "failed": "✕ Failed",
                    "draft_pending": "Draft Ready"}.get(status, status.title())

    # Phase icons for each specific phase
    phase_icons = {
        "P1": "🎨", "P2": "📋", "P3": "✅", "P4": "🔌",
        "P5": "📐", "P6": "⚙️", "P7": "💎", "P8a": "📄",
        "P8b": "📘", "P8c": "💻",
    }
    icon_display = phase_icons.get(pid, "📦")

    # Status icon for the node
    status_icon = {"completed": "✓", "in_progress": "⟳", "failed": "✕",
                   "draft_pending": "◑"}.get(status, num)

    dur = statuses.get(pid, {}).get("duration_seconds", "")
    dur_html = (f'<span class="pc-badge badge-completed" style="margin-left:auto;">'
                f'⏱ {dur:.1f}s</span>') \
               if isinstance(dur, (int, float)) and dur else ""

    manual = "" if auto else \
        '<span class="pc-badge badge-pending" style="margin-left:8px;">MANUAL</span>'

    # Error detail for failed phases
    err = statuses.get(pid, {}).get("error", "")
    err_html = f'<div class="pc-error">⚠️ {err}</div>' if err and status == "failed" else ""

    return f"""
    <div class="phase-card {status_cls}">
      <div class="pc-header">
        <div class="pc-num">{status_icon}</div>
        <div>
          <div class="pc-title">{icon_display} P{num} · {name}</div>
          <div class="pc-desc">{desc}</div>
        </div>
      </div>
      <div class="pc-meta">
        <span class="pc-badge {badge_cls}">{status_label}</span>
        {manual}{dur_html}
      </div>
      {err_html}
    </div>
    """


def render_pipeline():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">🔄</div>
      <div>
        <div class="ph-title">Pipeline</div>
        <div class="ph-sub">Phase-by-phase automated design generation</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if "project_id" not in st.session_state:
        st.markdown('<div class="alert-info">Create a project first.</div>', unsafe_allow_html=True)
        return

    proj_id = st.session_state.project_id
    statuses = _load_status(proj_id)
    proj = _load_project(proj_id) or st.session_state.get("current_project", {})

    dt = proj.get("design_type", "general")
    st.markdown(
        f'<div style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">'
        f'📁 <strong>{proj.get("name", "")}</strong> &nbsp;·&nbsp; <span class="tag">{dt}</span></div>',
        unsafe_allow_html=True)

    # Summary metrics
    auto_ids = [pid for pid, _, _, _, auto in PHASE_META if auto]
    done = sum(1 for p in auto_ids if _phase_status(statuses, p) == "completed")
    total = len(auto_ids)
    pct = int(done / total * 100) if total else 0
    in_prog = [p for p in auto_ids if _phase_status(statuses, p) == "in_progress"]
    fail_list = [p for p in auto_ids if _phase_status(statuses, p) == "failed"]

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Completed", f"{done}/{total}")
    with c2: st.metric("Progress", f"{pct}%")
    with c3: st.metric("Running", len(in_prog))
    with c4: st.metric("Failed", len(fail_list))

    st.progress(pct / 100)

    # ── Action banner based on pipeline state ──────────────────────────────
    p1_status = _phase_status(statuses, "P1")
    remaining = [p for p in auto_ids if p != "P1" and _phase_status(statuses, p) != "completed"]

    if not remaining and p1_status == "completed":
        st.markdown('<div class="alert-success">🎉 <strong>All phases complete!</strong> '
                    'Full design package ready.</div>', unsafe_allow_html=True)
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

    elif p1_status not in ("completed", "draft_pending"):
        st.markdown(
            '<div class="alert-warn">⚠️ <strong>Complete Phase 1</strong> (Design Chat) '
            'first before running the pipeline.</div>', unsafe_allow_html=True)
        if st.button("💬 Go to Design Chat", type="primary"):
            st.query_params["tab"] = "chat"; st.rerun()

    elif p1_status == "draft_pending":
        st.markdown(
            '<div class="alert-info">📋 <strong>Draft Ready</strong> — approve your design '
            'in the Design Chat to unlock the pipeline.</div>', unsafe_allow_html=True)
        if st.button("💬 Go to Design Chat", type="primary"):
            st.query_params["tab"] = "chat"; st.rerun()

    elif in_prog:
        st.markdown(f'<div class="alert-info">🔄 Pipeline running… '
                    f'current: <strong>{", ".join(in_prog)}</strong></div>',
                    unsafe_allow_html=True)
    else:
        col_l, col_r = st.columns([3, 1])
        with col_l:
            st.markdown(f'<div style="font-size:13px;color:var(--text-muted);">'
                        f'{len(remaining)} phases remaining</div>', unsafe_allow_html=True)
        with col_r:
            if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
                _start_pipeline(proj_id)

    # ── Phase cards (each phase as its own card) ──────────────────────────
    st.markdown("#### 📋 Phase Details")

    # Group: Phase 1 (Design)
    st.markdown('<div class="phase-group-label">🎨 Design & Requirements</div>',
                unsafe_allow_html=True)
    pid, num, name, desc, auto = PHASE_META[0]
    status = _phase_status(statuses, pid)
    st.markdown(_phase_card_html(pid, num, name, desc, status, statuses, auto),
                unsafe_allow_html=True)

    # Group: Documentation (P2-P3)
    st.markdown('<div class="phase-group-label">📋 Documentation & Compliance</div>',
                unsafe_allow_html=True)
    for pid, num, name, desc, auto in PHASE_META[1:3]:
        status = _phase_status(statuses, pid)
        st.markdown(_phase_card_html(pid, num, name, desc, status, statuses, auto),
                    unsafe_allow_html=True)
        # Per-phase run button
        if auto and pid != "P1" and p1_status == "completed":
            if status in ("pending", "failed"):
                if st.button(f"▶ Run P{num}", key=f"run_{pid}", use_container_width=False):
                    result = _api_post(f"/api/v1/projects/{proj_id}/phases/{pid}/execute", {})
                    if result:
                        st.rerun()
            elif status == "completed":
                if st.button(f"📄 View P{num} Output", key=f"view_{pid}", use_container_width=False):
                    st.query_params["tab"] = "docs"; st.rerun()

    # Group: Hardware Design (P4-P5)
    st.markdown('<div class="phase-group-label">🔌 Hardware Design</div>',
                unsafe_allow_html=True)
    for pid, num, name, desc, auto in PHASE_META[3:5]:
        status = _phase_status(statuses, pid)
        st.markdown(_phase_card_html(pid, num, name, desc, status, statuses, auto),
                    unsafe_allow_html=True)
        if auto and pid != "P1" and p1_status == "completed":
            if status in ("pending", "failed"):
                if st.button(f"▶ Run P{num}", key=f"run_{pid}", use_container_width=False):
                    result = _api_post(f"/api/v1/projects/{proj_id}/phases/{pid}/execute", {})
                    if result:
                        st.rerun()
            elif status == "completed":
                if st.button(f"📄 View P{num} Output", key=f"view_{pid}", use_container_width=False):
                    st.query_params["tab"] = "docs"; st.rerun()

    # Group: Logic & FPGA (P6-P7)
    st.markdown('<div class="phase-group-label">⚙️ Logic & FPGA</div>',
                unsafe_allow_html=True)
    for pid, num, name, desc, auto in PHASE_META[5:7]:
        status = _phase_status(statuses, pid)
        st.markdown(_phase_card_html(pid, num, name, desc, status, statuses, auto),
                    unsafe_allow_html=True)
        if auto and pid != "P1" and p1_status == "completed":
            if status in ("pending", "failed"):
                if st.button(f"▶ Run P{num}", key=f"run_{pid}", use_container_width=False):
                    result = _api_post(f"/api/v1/projects/{proj_id}/phases/{pid}/execute", {})
                    if result:
                        st.rerun()
            elif status == "completed":
                if st.button(f"📄 View P{num} Output", key=f"view_{pid}", use_container_width=False):
                    st.query_params["tab"] = "docs"; st.rerun()

    # Group: Software (P8a-P8c)
    st.markdown('<div class="phase-group-label">💻 Software & Code</div>',
                unsafe_allow_html=True)
    for pid, num, name, desc, auto in PHASE_META[7:10]:
        status = _phase_status(statuses, pid)
        st.markdown(_phase_card_html(pid, num, name, desc, status, statuses, auto),
                    unsafe_allow_html=True)
        if auto and pid != "P1" and p1_status == "completed":
            if status in ("pending", "failed"):
                if st.button(f"▶ Run P{num}", key=f"run_{pid}", use_container_width=False):
                    result = _api_post(f"/api/v1/projects/{proj_id}/phases/{pid}/execute", {})
                    if result:
                        st.rerun()
            elif status == "completed":
                if st.button(f"📄 View P{num} Output", key=f"view_{pid}", use_container_width=False):
                    st.query_params["tab"] = "docs"; st.rerun()

    # Auto-refresh while pipeline is running (non-blocking via fragment)
    if in_prog:
        _auto_refresh_placeholder = st.empty()
        _auto_refresh_placeholder.markdown(
            '<div class="proc-indicator" style="margin-top:12px;">'
            '<div class="proc-spinner"></div>Pipeline running… auto-refreshing in 3s</div>',
            unsafe_allow_html=True)
        time.sleep(3)
        st.rerun()


# ── Documents ──────────────────────────────────────────────────────────────────

def render_documents():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">📄</div>
      <div>
        <div class="ph-title">Generated Documents</div>
        <div class="ph-sub">IEEE-compliant design documentation</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if "project_id" not in st.session_state:
        st.markdown('<div class="alert-info">No project loaded.</div>', unsafe_allow_html=True)
        return

    proj = _load_project(st.session_state.project_id) \
           or st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", ""))

    if not output_dir.exists():
        st.markdown('<div class="alert-info">No documents yet — complete Phase 1 in Design Chat.</div>',
                    unsafe_allow_html=True)
        return

    proj_name = proj.get("name", "project").replace(" ", "_").lower()
    doc_map = {
        "requirements.md":              ("P1",  "🎨 Hardware Requirements"),
        "block_diagram.md":             ("P1",  "🎨 Block Diagram"),
        "architecture.md":              ("P1",  "🎨 System Architecture"),
        "component_recommendations.md": ("P1",  "🎨 Component Recommendations"),
        f"HRS_{proj_name}.md":          ("P2",  "📋 HRS — Hardware Requirements Spec"),
        "compliance_report.md":         ("P3",  "✅ Compliance Report"),
        "netlist_visual.md":            ("P4",  "🔌 Netlist Visualization"),
        "glr_specification.md":         ("P6",  "⚙️ GLR — Glue Logic Requirements"),
        f"SRS_{proj_name}.md":          ("P8a", "📄 SRS — Software Requirements Spec"),
        f"SDD_{proj_name}.md":          ("P8b", "📘 SDD — Software Design Description"),
        "driver_code.md":               ("P8c", "💻 Driver Code"),
        "code_review.md":               ("P8c", "💻 Code Review"),
    }

    found_any = False
    for fname, (phase, label) in doc_map.items():
        fpath = output_dir / fname
        if fpath.exists():
            found_any = True
            st.markdown(f"""
            <div class="doc-card">
              <div>
                <div class="dc-name">{label}</div>
                <div class="dc-phase">{phase} · {fname}</div>
              </div>
              <span class="tag">{phase}</span>
            </div>
            """, unsafe_allow_html=True)
            with st.expander(f"View {label}"):
                content = fpath.read_text(encoding="utf-8")
                _render_markdown_with_mermaid(content, key_prefix=f"doc_{fname}")

    if not found_any:
        st.markdown('<div class="alert-info">No documents generated yet.</div>',
                    unsafe_allow_html=True)


# ── Netlist ────────────────────────────────────────────────────────────────────

def render_netlist():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">🔌</div>
      <div>
        <div class="ph-title">Netlist Visualization</div>
        <div class="ph-sub">Phase 4 · Component connectivity graph</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if "project_id" not in st.session_state:
        st.markdown('<div class="alert-info">No project loaded.</div>', unsafe_allow_html=True)
        return

    proj = _load_project(st.session_state.project_id) or {}
    output_dir = Path(proj.get("output_dir", ""))
    netlist_file = output_dir / "netlist_visual.md"

    if netlist_file.exists():
        content = netlist_file.read_text(encoding="utf-8")
        _render_markdown_with_mermaid(content, key_prefix="netlist")
    else:
        statuses = _load_status(st.session_state.project_id)
        p4_status = _phase_status(statuses, "P4")
        if p4_status == "in_progress":
            st.markdown('<div class="alert-info">🔄 Netlist generation in progress…</div>',
                        unsafe_allow_html=True)
        elif p4_status == "failed":
            err = statuses.get("P4", {}).get("error", "Unknown error")
            st.markdown(f'<div class="alert-warn">⚠️ Netlist generation failed: {err}</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="alert-info">Run the pipeline to generate netlist (Phase 4).</div>',
                        unsafe_allow_html=True)


# ── Code Review ────────────────────────────────────────────────────────────────

def render_code_review():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">🔍</div>
      <div>
        <div class="ph-title">Code Review</div>
        <div class="ph-sub">Phase 8c · Generated drivers and test suites</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if "project_id" not in st.session_state:
        st.markdown('<div class="alert-info">No project loaded.</div>', unsafe_allow_html=True)
        return

    proj = _load_project(st.session_state.project_id) or {}
    output_dir = Path(proj.get("output_dir", ""))

    for fname, label in [("driver_code.md", "Driver Code"), ("code_review.md", "Review Report")]:
        fpath = output_dir / fname
        if fpath.exists():
            with st.expander(f"📄 {label}", expanded=True):
                content = fpath.read_text(encoding="utf-8")
                _render_markdown_with_mermaid(content, key_prefix=f"code_{fname}")

    if not any((output_dir / f).exists() for f in ["driver_code.md", "code_review.md"]):
        st.markdown('<div class="alert-info">Run the pipeline to generate code (Phase 8c).</div>',
                    unsafe_allow_html=True)


# ── Dashboard ──────────────────────────────────────────────────────────────────

def render_dashboard():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">📊</div>
      <div>
        <div class="ph-title">Project Dashboard</div>
        <div class="ph-sub">Overview of all projects and pipeline status</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    projects = _api_get("/api/v1/projects") or []
    if not projects:
        st.markdown('<div class="alert-info">No projects yet. Create one in New Project.</div>',
                    unsafe_allow_html=True)
        return

    st.metric("Total Projects", len(projects))

    for p in projects:
        phase_statuses = p.get("phase_statuses") or {}
        done_count = sum(1 for v in phase_statuses.values()
                         if v.get("status") == "completed")
        auto_total = sum(1 for _, _, _, _, auto in PHASE_META if auto)
        pct = int(done_count / auto_total * 100) if auto_total else 0

        st.markdown(f"""
        <div class="glass-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div style="font-weight:700;font-size:16px;color:var(--text-primary);">
                📁 {p.get('name', '—')}
              </div>
              <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">
                <span class="tag">{p.get('design_type', 'general')}</span>
                &nbsp;·&nbsp;{done_count}/{auto_total} phases · {pct}%
              </div>
            </div>
          </div>
          <div class="prog-track" style="margin-top:12px;">
            <div class="prog-fill" style="width:{pct}%"></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("Open", key=f"open_{p['id']}", use_container_width=True):
                st.session_state.project_id = p["id"]
                st.session_state.current_project = p
                st.query_params["project_id"] = str(p["id"])
                st.query_params["tab"] = "pipeline"
                st.rerun()

        # Phase status row
        for pid, num, name, _, _ in PHASE_META:
            status = _phase_status(phase_statuses, pid)
            if status != "pending":
                icon = {"completed": "●", "in_progress": "◉", "failed": "✕"}.get(status, "○")
                st.markdown(f'<span style="font-size:11px;color:var(--text-muted);margin-right:8px;">'
                            f'{icon} P{num}</span>', unsafe_allow_html=True)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()
    tab = render_tab_nav()

    if tab == "overview":    render_overview()
    elif tab == "new":       render_new_project()
    elif tab == "chat":      render_design_chat()
    elif tab == "pipeline":  render_pipeline()
    elif tab == "docs":      render_documents()
    elif tab == "netlist":   render_netlist()
    elif tab == "code":      render_code_review()
    elif tab == "dashboard": render_dashboard()


if __name__ == "__main__":
    main()
