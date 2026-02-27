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

# ── Professional CSS Design System ────────────────────────────────────────────
st.markdown("""
<style>
/* ── Google Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Root tokens ── */
:root {
  --bg-primary:    #0F172A;
  --bg-secondary:  #1E293B;
  --bg-card:       #1E293B;
  --bg-main:       #F8FAFC;
  --accent:        #3B82F6;
  --accent-light:  #60A5FA;
  --accent-glow:   rgba(59,130,246,0.15);
  --success:       #10B981;
  --warning:       #F59E0B;
  --danger:        #EF4444;
  --text-primary:  #1E293B;
  --text-muted:    #64748B;
  --text-light:    #94A3B8;
  --border:        #E2E8F0;
  --radius-sm:     6px;
  --radius-md:     10px;
  --radius-lg:     16px;
  --shadow-sm:     0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.05);
  --shadow-md:     0 4px 6px -1px rgba(0,0,0,.08), 0 2px 4px -1px rgba(0,0,0,.04);
  --shadow-lg:     0 10px 15px -3px rgba(0,0,0,.08), 0 4px 6px -2px rgba(0,0,0,.04);
}

/* ── Global font ── */
html, body, [class*="css"] {
  font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: var(--bg-primary) !important;
  border-right: 1px solid rgba(255,255,255,0.06);
}
[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
[data-testid="stSidebar"] .sidebar-logo {
  padding: 8px 0 20px 0;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  margin-bottom: 20px;
}
[data-testid="stSidebar"] .sidebar-logo h1 {
  font-size: 22px !important;
  font-weight: 700 !important;
  color: #F1F5F9 !important;
  margin: 0 !important;
}
[data-testid="stSidebar"] .sidebar-logo p {
  font-size: 11px !important;
  color: #64748B !important;
  margin: 2px 0 0 0 !important;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

/* ── Main content area ── */
.main .block-container {
  padding: 1.5rem 2.5rem 2rem 2.5rem;
  max-width: 1200px;
}

/* ── Page header ── */
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 0 16px 0;
  border-bottom: 2px solid var(--border);
  margin-bottom: 24px;
}
.page-header .ph-icon {
  width: 40px; height: 40px;
  background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%);
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  box-shadow: 0 4px 12px rgba(59,130,246,0.3);
}
.page-header .ph-title { font-size: 26px; font-weight: 700; color: var(--text-primary); }
.page-header .ph-sub   { font-size: 13px; color: var(--text-muted); margin-top: 2px; }

/* ── Tab navigation ── */
.tab-nav {
  display: flex;
  gap: 4px;
  background: #F1F5F9;
  border-radius: var(--radius-md);
  padding: 4px;
  margin-bottom: 24px;
}
.tab-nav-btn {
  flex: 1;
  padding: 8px 4px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--text-muted);
  border: none;
  background: transparent;
}
.tab-nav-btn.active {
  background: white;
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

/* ── Cards ── */
.card {
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 16px;
}
.card-sm {
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px;
  box-shadow: var(--shadow-sm);
}

/* ── Chat bubbles ── */
.chat-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
}
.chat-msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  max-width: 90%;
}
.chat-msg.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.chat-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; flex-shrink: 0;
}
.chat-avatar.user-av { background: var(--accent); color: white; }
.chat-avatar.bot-av  { background: #EFF6FF; border: 1px solid #BFDBFE; }
.chat-bubble {
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.6;
  box-shadow: var(--shadow-sm);
}
.chat-bubble.user {
  background: var(--accent);
  color: white;
  border-bottom-right-radius: 4px;
}
.chat-bubble.bot {
  background: white;
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
}

/* ── Phase badges ── */
.phase-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: 20px;
  font-size: 12px; font-weight: 600; margin: 3px 2px;
  border: 1px solid transparent;
}
.phase-badge.pending    { background: #F8FAFC; border-color: #E2E8F0; color: #94A3B8; }
.phase-badge.active     { background: #EFF6FF; border-color: #BFDBFE; color: #2563EB; }
.phase-badge.done       { background: #ECFDF5; border-color: #A7F3D0; color: #059669; }
.phase-badge.failed     { background: #FEF2F2; border-color: #FECACA; color: #DC2626; }
.phase-badge.draft      { background: #FFFBEB; border-color: #FDE68A; color: #D97706; }

/* ── Phase stepper (Pipeline tab) ── */
.stepper { display: flex; flex-direction: column; gap: 0; }
.step-row {
  display: flex; align-items: stretch; gap: 0;
  position: relative;
}
.step-connector {
  width: 2px; background: #E2E8F0;
  margin: 0 19px;
  min-height: 20px;
}
.step-connector.done { background: var(--success); }
.step-node {
  width: 40px; height: 40px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; font-weight: 700; flex-shrink: 0;
  border: 2px solid #E2E8F0;
  background: white; color: var(--text-muted);
  z-index: 1;
}
.step-node.done    { background: var(--success); border-color: var(--success); color: white; }
.step-node.active  { background: var(--accent);  border-color: var(--accent);  color: white;
                     box-shadow: 0 0 0 4px var(--accent-glow); }
.step-node.failed  { background: var(--danger);  border-color: var(--danger);  color: white; }
.step-card {
  flex: 1;
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  margin: 0 0 8px 12px;
  box-shadow: var(--shadow-sm);
  display: flex; align-items: center; justify-content: space-between;
}
.step-card.active { border-color: var(--accent); border-left: 3px solid var(--accent); }
.step-card.done   { border-color: #A7F3D0; border-left: 3px solid var(--success); }
.step-card.failed { border-color: #FECACA; border-left: 3px solid var(--danger); }
.step-name { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.step-sub  { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.step-dur  { font-size: 11px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }

/* ── Pipeline bar (mini, overview) ── */
.pipeline-bar { display: flex; gap: 3px; margin: 16px 0; }
.pb-seg {
  flex: 1; height: 8px; border-radius: 4px;
  background: #E2E8F0; position: relative;
}
.pb-seg.done   { background: var(--success); }
.pb-seg.active { background: var(--accent); animation: pulse 1.5s ease-in-out infinite; }
.pb-seg.failed { background: var(--danger); }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.5; } }

/* ── Metric cards ── */
.metric-grid { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
.metric-card-pro {
  flex: 1; min-width: 140px;
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  box-shadow: var(--shadow-sm);
  text-align: center;
}
.metric-card-pro .mv { font-size: 32px; font-weight: 700; color: var(--accent); line-height: 1; }
.metric-card-pro .ml { font-size: 12px; color: var(--text-muted); margin-top: 6px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; }
.metric-card-pro .mi { font-size: 22px; margin-bottom: 4px; }

/* ── Feature cards (overview) ── */
.feature-grid { display: flex; gap: 12px; margin: 20px 0; }
.feature-card {
  flex: 1;
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 20px;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s ease;
}
.feature-card:hover { box-shadow: var(--shadow-md); }
.feature-card .fc-icon { font-size: 28px; margin-bottom: 10px; }
.feature-card .fc-title { font-weight: 700; font-size: 15px; color: var(--text-primary); margin-bottom: 6px; }
.feature-card .fc-desc  { font-size: 13px; color: var(--text-muted); line-height: 1.5; }

/* ── Status indicator ── */
.status-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; margin-right: 6px;
}
.status-dot.online  { background: var(--success); box-shadow: 0 0 0 2px rgba(16,185,129,0.2); }
.status-dot.offline { background: #94A3B8; }

/* ── Processing indicator ── */
.proc-indicator {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 20px;
  background: #EFF6FF;
  border: 1px solid #BFDBFE;
  border-radius: var(--radius-md);
  margin: 10px 0;
  font-weight: 500; color: #1D4ED8; font-size: 14px;
}
.proc-spinner {
  width: 20px; height: 20px;
  border: 3px solid #BFDBFE;
  border-top-color: #2563EB;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Approve / action buttons ── */
.approve-btn-wrap { margin: 16px 0; }
.approve-btn-wrap [data-testid="baseButton-primary"] {
  background: linear-gradient(135deg, #10B981, #059669) !important;
  border: none !important;
  font-weight: 600 !important;
  font-size: 15px !important;
  padding: 12px 24px !important;
  border-radius: var(--radius-md) !important;
  box-shadow: 0 4px 12px rgba(16,185,129,0.3) !important;
}

/* ── Document cards ── */
.doc-card {
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px 18px;
  margin-bottom: 8px;
  display: flex; align-items: center; justify-content: space-between;
  box-shadow: var(--shadow-sm);
}
.doc-card .doc-name { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.doc-card .doc-meta { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.doc-card .doc-badge {
  font-size: 11px; font-weight: 600;
  padding: 3px 10px; border-radius: 12px;
  background: var(--accent-glow); color: var(--accent);
}

/* ── Section headers ── */
.section-header {
  font-size: 20px; font-weight: 700; color: var(--text-primary);
  margin: 0 0 4px 0;
}
.section-sub {
  font-size: 13px; color: var(--text-muted);
  margin-bottom: 20px;
}

/* ── Alert banners ── */
.alert-success {
  background: #ECFDF5; border: 1px solid #A7F3D0;
  border-left: 4px solid var(--success);
  border-radius: var(--radius-md);
  padding: 14px 18px; color: #065F46; font-size: 14px;
  margin: 12px 0;
}
.alert-info {
  background: #EFF6FF; border: 1px solid #BFDBFE;
  border-left: 4px solid var(--accent);
  border-radius: var(--radius-md);
  padding: 14px 18px; color: #1E40AF; font-size: 14px;
  margin: 12px 0;
}
.alert-warn {
  background: #FFFBEB; border: 1px solid #FDE68A;
  border-left: 4px solid var(--warning);
  border-radius: var(--radius-md);
  padding: 14px 18px; color: #92400E; font-size: 14px;
  margin: 12px 0;
}

/* ── Sidebar project card ── */
.proj-info-card {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  margin: 12px 0;
}
.proj-info-card .pn { font-size: 15px; font-weight: 700; color: #F1F5F9 !important; }
.proj-info-card .pt { font-size: 11px; color: #64748B !important; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 2px; }

/* ── API key badges ── */
.key-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 600; margin: 2px 0;
}
.key-badge.ok  { background: rgba(16,185,129,0.15); color: #10B981; }
.key-badge.off { background: rgba(148,163,184,0.15); color: #94A3B8; }

/* ── Progress bar ── */
.prog-bar-wrap { margin: 8px 0 16px 0; }
.prog-bar-track { height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; }
.prog-bar-fill  { height: 6px; background: linear-gradient(90deg, #3B82F6, #60A5FA); border-radius: 3px; transition: width 0.4s ease; }
.prog-label { font-size: 11px; color: #64748B !important; margin-top: 4px; text-align: right; }

/* ── Sticker tags ── */
.tag {
  display: inline-block; padding: 2px 8px;
  background: #EFF6FF; color: var(--accent);
  border-radius: 4px; font-size: 11px; font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}

/* ── Form styling ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
  border-radius: var(--radius-md) !important;
  border: 1.5px solid var(--border) !important;
  font-family: 'Inter', sans-serif !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-glow) !important;
}

/* ── Primary button ── */
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #3B82F6, #2563EB) !important;
  border: none !important;
  border-radius: var(--radius-md) !important;
  font-weight: 600 !important;
  box-shadow: 0 4px 12px rgba(59,130,246,0.3) !important;
  transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"]:hover {
  box-shadow: 0 6px 16px rgba(59,130,246,0.4) !important;
  transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
  border-radius: var(--radius-md) !important;
  font-weight: 500 !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
  background: #F8FAFC !important;
  border-radius: var(--radius-md) !important;
  font-weight: 600 !important;
  font-size: 14px !important;
}
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
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(f"{_API}{path}")
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        return None
    except Exception as exc:
        log.warning("api.get_failed path=%s: %s", path, exc)
        return None


def _api_post(path: str, body: dict, timeout: float = 180.0) -> dict | None:
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
    return _api_get(f"/api/v1/projects/{project_id}")


def _load_project_status(project_id: int) -> dict:
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
        # Brand header
        st.markdown("""
        <div class="sidebar-logo">
          <h1>⚡ Hardware Pipeline</h1>
          <p>AI-Powered EE Design Automation</p>
        </div>
        """, unsafe_allow_html=True)

        if "project_id" in st.session_state:
            proj_id = st.session_state.project_id
            proj = _load_project_from_api(proj_id) or st.session_state.get("current_project", {})
            statuses = proj.get("phase_statuses", {})

            # Project info card
            st.markdown(f"""
            <div class="proj-info-card">
              <div class="pn">📁 {proj.get('name', '—')}</div>
              <div class="pt">{proj.get('design_type', '—')} design</div>
            </div>
            """, unsafe_allow_html=True)

            # Progress bar
            done_count = sum(1 for pid, _, _, auto in PHASE_META if auto
                             and _phase_status(statuses, pid) == "completed")
            total_auto = sum(1 for _, _, _, auto in PHASE_META if auto)
            pct = int(done_count / total_auto * 100) if total_auto else 0
            st.markdown(f"""
            <div class="prog-bar-wrap">
              <div class="prog-bar-track">
                <div class="prog-bar-fill" style="width:{pct}%"></div>
              </div>
              <div class="prog-label">{done_count}/{total_auto} phases · {pct}%</div>
            </div>
            """, unsafe_allow_html=True)

            # Phase status pills
            st.markdown("**Pipeline Status**")
            for pid, num, name, _ in PHASE_META:
                status = _phase_status(statuses, pid)
                icon = {"pending":"○","in_progress":"◉","completed":"●",
                        "failed":"✕","draft_pending":"◑"}.get(status, "○")
                css = {"pending":"pending","in_progress":"active","completed":"done",
                       "failed":"failed","draft_pending":"draft"}.get(status, "pending")
                st.markdown(
                    f'<div class="phase-badge {css}">'
                    f'<span>{icon}</span> P{num} {name}</div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown("""
            <div class="alert-info" style="background:rgba(59,130,246,0.08);border-color:rgba(59,130,246,0.2);color:#93C5FD;">
              No project loaded.<br>Create one to begin.
            </div>
            """, unsafe_allow_html=True)

        # System section
        st.markdown("---")
        online = not settings.is_air_gapped
        dot_cls = "online" if online else "offline"
        mode_txt = "Online" if online else "Air-Gapped"
        st.markdown(f"""
        <div style="font-size:12px;color:#94A3B8;margin-bottom:8px;">
          <span class="status-dot {dot_cls}"></span><strong style="color:#CBD5E1">{mode_txt}</strong>
          &nbsp;·&nbsp;<span class="tag">{settings.primary_model}</span>
        </div>
        """, unsafe_allow_html=True)

        # API key badges
        st.markdown('<div style="font-size:11px;color:#475569;margin-bottom:4px;">API KEYS</div>',
                    unsafe_allow_html=True)
        for provider, (ok, _) in settings.get_api_key_status().items():
            cls = "ok" if ok else "off"
            icon = "✓" if ok else "—"
            st.markdown(
                f'<span class="key-badge {cls}">{icon} {provider}</span>',
                unsafe_allow_html=True
            )


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
        statuses = _load_project_status(st.session_state.project_id)

    # Mini pipeline progress bar
    segs = ""
    for pid, _, _, _ in PHASE_META:
        status = _phase_status(statuses, pid)
        cls = "done" if status == "completed" else ("active" if status == "in_progress" else "")
        segs += f'<div class="pb-seg {cls}" title="{pid}"></div>'
    st.markdown(f'<div class="pipeline-bar">{segs}</div>', unsafe_allow_html=True)

    # Feature cards
    st.markdown("""
    <div class="feature-grid">
      <div class="feature-card">
        <div class="fc-icon">📋</div>
        <div class="fc-title">IEEE Standards</div>
        <div class="fc-desc">HRS (29148), SRS (830), SDD (1016) — audit-ready, fully traceable requirements</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">🔌</div>
        <div class="fc-title">Smart Netlist</div>
        <div class="fc-desc">Visual connectivity graph before PCB layout with DRC checks via NetworkX</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">✅</div>
        <div class="fc-title">Compliance</div>
        <div class="fc-desc">RoHS / REACH / FCC rules engine — PASS / FAIL / REVIEW status per component</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">💻</div>
        <div class="fc-title">Code Generation</div>
        <div class="fc-desc">C/C++ drivers + test suites, reviewed with tree-sitter AST analysis</div>
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
        <div class="ph-sub">Create a project and jump straight into the AI design chat</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.container():
        with st.form("new_project_form", clear_on_submit=False):
            col1, col2 = st.columns([2, 1])
            with col1:
                name = st.text_input(
                    "Project Name *",
                    placeholder="e.g., BLDC Motor Controller 10kW"
                )
                description = st.text_area(
                    "Description",
                    placeholder="Brief description of the hardware design…",
                    height=110
                )
            with col2:
                design_type = st.selectbox(
                    "Design Type *",
                    ["general", "rf", "motor_control", "power", "digital", "sensor", "industrial"],
                    format_func=lambda x: {
                        "general": "⚙️ General",
                        "rf": "📡 RF / Wireless",
                        "motor_control": "⚡ Motor Control",
                        "power": "🔋 Power Electronics",
                        "digital": "💻 Digital Logic",
                        "sensor": "📊 Sensor / IoT",
                        "industrial": "🏭 Industrial",
                    }.get(x, x)
                )
                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
                submitted = st.form_submit_button(
                    "🚀 Create & Start",
                    type="primary",
                    use_container_width=True
                )

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
            _reset_chat()
            st.markdown(f'<div class="alert-success">✅ Project <strong>{name}</strong> created! Redirecting to chat…</div>',
                        unsafe_allow_html=True)
            log.info("ui.new_project", extra={"project_id": result["id"]})
            time.sleep(0.6)
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
    statuses = _load_project_status(proj_id)
    phase1_status = _phase_status(statuses, "P1")
    proj = _load_project_from_api(proj_id) or st.session_state.get("current_project", {})

    # Project tag line
    dt_icons = {"motor_control":"⚡","rf":"📡","power":"🔋","digital":"💻",
                 "sensor":"📊","industrial":"🏭","general":"⚙️"}
    dt = proj.get("design_type","general")
    st.markdown(
        f'<div style="margin-bottom:16px;font-size:13px;color:var(--text-muted);">'
        f'{dt_icons.get(dt,"⚙️")} <strong>{proj.get("name","")}</strong>'
        f' &nbsp;·&nbsp; <span class="tag">{dt}</span></div>',
        unsafe_allow_html=True
    )

    # Phase 1 complete banner
    if phase1_status == "completed":
        st.markdown('<div class="alert-success">✅ <strong>Phase 1 Complete!</strong> Requirements and block diagrams generated. Ready to run the full pipeline.</div>',
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

    # Render chat history using st.chat_message (native Streamlit, most reliable)
    for idx, msg in enumerate(st.session_state.chat_messages):
        with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
            _render_markdown_with_mermaid(msg["content"], key_prefix=f"chat_{idx}")

    # Approval / input area
    if phase1_status != "completed":
        if st.session_state.get("draft_pending"):
            st.markdown("")
            st.markdown("""
            <div class="alert-info">
              📋 <strong>Draft ready for review.</strong> Approve to generate full IEEE documentation, or request changes below.
            </div>
            """, unsafe_allow_html=True)

            col_a, col_b = st.columns([1, 2])
            with col_a:
                st.markdown('<div class="approve-btn-wrap">', unsafe_allow_html=True)
                if st.button("✅ Approve — Generate Full Docs", type="primary",
                             use_container_width=True, key="btn_approve"):
                    _send_chat("Approved. Please generate the full requirements documents.")
                st.markdown('</div>', unsafe_allow_html=True)
            with col_b:
                change_text = st.text_input(
                    "Request changes…",
                    key="change_input",
                    placeholder="e.g., change voltage to 24V, add CAN bus interface"
                )
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
            unsafe_allow_html=True,
        )

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
                unsafe_allow_html=True
            )
            if result.get("outputs"):
                with st.expander("📁 Generated Files", expanded=True):
                    for fname in result["outputs"]:
                        st.markdown(f'<span class="tag">📄 {fname}</span>', unsafe_allow_html=True)
            st.rerun()


# ── Pipeline ───────────────────────────────────────────────────────────────────

def _start_pipeline(project_id: int):
    result = _api_post(f"/api/v1/projects/{project_id}/pipeline/run", {})
    if result:
        st.query_params["tab"] = "pipeline"
        st.rerun()
    else:
        st.error("Could not start pipeline — is the API server running?")


def _phase_step_html(pid: str, num: str, name: str, status: str, statuses: dict,
                     is_last: bool = False) -> str:
    """Render a single pipeline stepper step."""
    icon_map = {
        "pending":      ("○", ""),
        "in_progress":  ("◉", "active"),
        "completed":    ("✓", "done"),
        "failed":       ("✕", "failed"),
        "draft_pending":("◑", "active"),
    }
    icon, node_cls = icon_map.get(status, ("○", ""))
    card_cls = node_cls

    dur = statuses.get(pid, {}).get("duration_seconds", "")
    dur_html = f'<div class="step-dur">{dur:.1f}s</div>' if isinstance(dur, (int, float)) and dur else ""

    status_label = {
        "pending": "Pending",
        "in_progress": "Processing…",
        "completed": "Complete",
        "failed": "Failed",
        "draft_pending": "Draft Ready",
    }.get(status, status.title())

    return f"""
    <div style="display:flex;align-items:flex-start;gap:0;margin-bottom:8px;">
      <div style="display:flex;flex-direction:column;align-items:center;margin-right:12px;">
        <div class="step-node {node_cls}">{icon}</div>
        {'<div style="width:2px;flex:1;background:' + ('#10B981' if status=='completed' else '#E2E8F0') + ';min-height:16px;margin:2px 0"></div>' if not is_last else ''}
      </div>
      <div class="step-card {card_cls}" style="margin-bottom:8px;">
        <div>
          <div class="step-name">P{num} · {name}</div>
          <div class="step-sub">{status_label}</div>
        </div>
        {dur_html}
      </div>
    </div>
    """


def render_pipeline():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">🔄</div>
      <div>
        <div class="ph-title">Pipeline Execution</div>
        <div class="ph-sub">Automated phase-by-phase design generation</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if "project_id" not in st.session_state:
        st.markdown('<div class="alert-info">Create a project first.</div>',
                    unsafe_allow_html=True)
        return

    proj_id = st.session_state.project_id
    statuses = _load_project_status(proj_id)
    proj = _load_project_from_api(proj_id) or st.session_state.get("current_project", {})

    dt = proj.get("design_type", "general")
    st.markdown(
        f'<div style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">'
        f'📁 <strong>{proj.get("name","")}</strong> &nbsp;·&nbsp; <span class="tag">{dt}</span></div>',
        unsafe_allow_html=True
    )

    # Summary metrics
    auto_ids = ["P1","P2","P3","P4","P6","P8a","P8b","P8c"]
    done = sum(1 for p in auto_ids if _phase_status(statuses, p) == "completed")
    total = len(auto_ids)
    pct = int(done / total * 100) if total else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Phases Complete", f"{done}/{total}")
    with c2:
        st.metric("Progress", f"{pct}%")
    with c3:
        in_prog_list = [p for p in auto_ids if _phase_status(statuses, p) == "in_progress"]
        st.metric("Running", len(in_prog_list))
    with c4:
        fail_list = [p for p in auto_ids if _phase_status(statuses, p) == "failed"]
        st.metric("Failed", len(fail_list))

    st.progress(pct / 100)
    st.markdown("")

    if _phase_status(statuses, "P1") != "completed":
        st.markdown('<div class="alert-warn">⚠️ <strong>Complete Phase 1</strong> (Design Chat) first before running the pipeline.</div>',
                    unsafe_allow_html=True)
        if st.button("💬 Go to Design Chat", type="primary"):
            st.query_params["tab"] = "chat"; st.rerun()
        return

    remaining = [p for p in auto_ids if _phase_status(statuses, p) != "completed"]
    in_progress = [p for p in auto_ids if _phase_status(statuses, p) == "in_progress"]

    if not remaining:
        st.markdown('<div class="alert-success">🎉 <strong>All phases complete!</strong> Your full design package is ready.</div>',
                    unsafe_allow_html=True)
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

    elif in_progress:
        st.markdown(
            f'<div class="alert-info">🔄 Pipeline running… current: <strong>{", ".join(in_progress)}</strong></div>',
            unsafe_allow_html=True
        )

    else:
        col_l, col_r = st.columns([3, 1])
        with col_l:
            st.markdown(f'<div style="font-size:13px;color:var(--text-muted);">'
                        f'{len(remaining)} phases remaining: {", ".join(remaining)}</div>',
                        unsafe_allow_html=True)
        with col_r:
            if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
                _start_pipeline(proj_id)

    # Stepper
    st.markdown("#### Phase Details")
    stepper_html = ""
    visible = [(pid, num, name) for pid, num, name, auto in PHASE_META
               if pid not in ("P5", "P7")]
    for i, (pid, num, name) in enumerate(visible):
        status = _phase_status(statuses, pid)
        is_last = (i == len(visible) - 1)
        stepper_html += _phase_step_html(pid, num, name, status, statuses, is_last)
    st.markdown(stepper_html, unsafe_allow_html=True)

    # Auto-refresh while pipeline is running
    if in_progress:
        time.sleep(5)
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

    proj = _load_project_from_api(st.session_state.project_id) \
           or st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", ""))

    if not output_dir.exists():
        st.markdown('<div class="alert-info">No documents yet — complete Phase 1 in Design Chat.</div>',
                    unsafe_allow_html=True)
        return

    proj_name = proj.get("name", "project").replace(" ", "_").lower()
    doc_map = {
        "requirements.md":              ("P1",  "Hardware Requirements"),
        "block_diagram.md":             ("P1",  "Block Diagram"),
        "architecture.md":              ("P1",  "System Architecture"),
        "component_recommendations.md": ("P1",  "Component Recommendations"),
        f"HRS_{proj_name}.md":          ("P2",  "HRS — Hardware Requirements Spec"),
        "compliance_report.md":         ("P3",  "Compliance Report"),
        "netlist_visual.md":            ("P4",  "Netlist Visualization"),
        "glr_specification.md":         ("P6",  "GLR — Glue Logic Requirements"),
        f"SRS_{proj_name}.md":          ("P8a", "SRS — Software Requirements Spec"),
        f"SDD_{proj_name}.md":          ("P8b", "SDD — Software Design Document"),
        "code_review_report.md":        ("P8c", "Code Review Report"),
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
        st.markdown('<div class="alert-info">No documents generated yet. Complete Phase 1 in Design Chat.</div>',
                    unsafe_allow_html=True)
        return

    # Summary metrics row
    total_size = sum(f.stat().st_size for f, _, _ in doc_files) / 1024
    st.markdown(f"""
    <div class="metric-grid">
      <div class="metric-card-pro">
        <div class="mi">📄</div>
        <div class="mv">{len(doc_files)}</div>
        <div class="ml">Documents</div>
      </div>
      <div class="metric-card-pro">
        <div class="mi">💾</div>
        <div class="mv">{total_size:.0f}</div>
        <div class="ml">Total KB</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Document list
    for fpath, phase, label in doc_files:
        size_kb = fpath.stat().st_size / 1024
        with st.expander(f"📄 [{phase}] {label}  ·  {size_kb:.1f} KB", expanded=False):
            content = fpath.read_text(encoding="utf-8")
            tab_view, tab_raw = st.tabs(["📖 Rendered", "🗒️ Raw Markdown"])
            with tab_view:
                _render_markdown_with_mermaid(content, key_prefix=f"doc_{fpath.name}")
            with tab_raw:
                st.code(content, language="markdown")
            st.download_button(
                f"⬇️ Download {fpath.name}", data=content,
                file_name=fpath.name, mime="text/markdown",
                key=f"dl_{fpath.name}"
            )


# ── Netlist ────────────────────────────────────────────────────────────────────

def render_netlist():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">🔌</div>
      <div>
        <div class="ph-title">Netlist Viewer</div>
        <div class="ph-sub">Phase 4 · Component connectivity graph</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if "project_id" not in st.session_state:
        st.markdown('<div class="alert-info">No project loaded.</div>', unsafe_allow_html=True)
        return

    proj = _load_project_from_api(st.session_state.project_id) \
           or st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", ""))
    netlist_visual = output_dir / "netlist_visual.md"
    netlist_json = output_dir / "netlist.json"

    if not netlist_visual.exists() and not netlist_json.exists():
        st.markdown('<div class="alert-info">Netlist not generated yet — run the pipeline through Phase 4.</div>',
                    unsafe_allow_html=True)
        return

    if netlist_visual.exists():
        content = netlist_visual.read_text(encoding="utf-8")
        st.markdown("### Visual Netlist")
        _render_markdown_with_mermaid(content, key_prefix="netlist")
        st.download_button("⬇️ Download Netlist Visual", data=content,
                           file_name="netlist_visual.md", mime="text/markdown",
                           key="dl_netlist_visual")

    if netlist_json.exists():
        st.markdown("---")
        st.markdown("### Netlist Data")
        json_content = netlist_json.read_text(encoding="utf-8")
        try:
            netlist_data = json.loads(json_content)
            nodes = netlist_data.get("nodes", [])
            edges = netlist_data.get("edges", [])
            power_nets = netlist_data.get("power_nets", [])
            c1, c2, c3 = st.columns(3)
            c1.metric("Components", len(nodes))
            c2.metric("Connections", len(edges))
            c3.metric("Power Nets", len(power_nets))
            if nodes:
                st.markdown("#### Component Instances")
                st.dataframe(
                    [{"Instance": n.get("instance_id"), "Part": n.get("part_number"),
                      "Component": n.get("component_name")} for n in nodes],
                    use_container_width=True
                )
            if edges:
                st.markdown("#### Connections")
                st.dataframe(
                    [{"From": e.get("from"), "To": e.get("to"),
                      "Net": e.get("net_name")} for e in edges],
                    use_container_width=True
                )
        except json.JSONDecodeError:
            st.code(json_content, language="json")
        st.download_button("⬇️ Download netlist.json", data=json_content,
                           file_name="netlist.json", mime="application/json",
                           key="dl_netlist_json")


# ── Code Review ────────────────────────────────────────────────────────────────

def render_code_review():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">🔍</div>
      <div>
        <div class="ph-title">Code Review</div>
        <div class="ph-sub">Phase 8c · Generated source + AST analysis</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if "project_id" not in st.session_state:
        st.markdown('<div class="alert-info">No project loaded.</div>', unsafe_allow_html=True)
        return

    proj = _load_project_from_api(st.session_state.project_id) \
           or st.session_state.get("current_project", {})
    output_dir = Path(proj.get("output_dir", ""))
    review_file = output_dir / "code_review_report.md"
    src_dir = output_dir / "src"
    src_files = list(src_dir.rglob("*.*")) if src_dir.exists() else []

    if not review_file.exists() and not src_files:
        st.markdown('<div class="alert-info">Code not generated yet — run the full pipeline first.</div>',
                    unsafe_allow_html=True)
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
        st.markdown("---")

    if review_file.exists():
        st.markdown("### Code Review Report")
        content = review_file.read_text(encoding="utf-8")
        _render_markdown_with_mermaid(content, key_prefix="review")
        st.download_button("⬇️ Download Review Report", data=content,
                           file_name="code_review_report.md", mime="text/markdown",
                           key="dl_review")


# ── Dashboard ──────────────────────────────────────────────────────────────────

def render_dashboard():
    st.markdown("""
    <div class="page-header">
      <div class="ph-icon">📊</div>
      <div>
        <div class="ph-title">Projects Dashboard</div>
        <div class="ph-sub">All projects at a glance</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    projects = _api_get("/api/v1/projects")
    if projects is None:
        try:
            from services.project_service import ProjectService
            projects = ProjectService().list_all()
        except Exception as exc:
            st.error(f"Could not load projects: {exc}")
            return

    if not projects:
        st.markdown('<div class="alert-info">No projects yet — create one in <strong>New Project</strong>.</div>',
                    unsafe_allow_html=True)
        return

    completed = sum(1 for p in projects if p.get("current_phase") == "DONE")
    in_prog = len(projects) - completed
    total_phases_done = sum(
        sum(1 for v in (p.get("phase_statuses") or {}).values()
            if isinstance(v, dict) and v.get("status") == "completed")
        for p in projects
    )

    st.markdown(f"""
    <div class="metric-grid">
      <div class="metric-card-pro">
        <div class="mi">📁</div>
        <div class="mv">{len(projects)}</div>
        <div class="ml">Total Projects</div>
      </div>
      <div class="metric-card-pro">
        <div class="mi">🔄</div>
        <div class="mv">{in_prog}</div>
        <div class="ml">In Progress</div>
      </div>
      <div class="metric-card-pro">
        <div class="mi">✅</div>
        <div class="mv">{completed}</div>
        <div class="ml">Completed</div>
      </div>
      <div class="metric-card-pro">
        <div class="mi">⚡</div>
        <div class="mv">{total_phases_done}</div>
        <div class="ml">Total Phases Run</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    for p in projects:
        phase_statuses = p.get("phase_statuses") or {}
        done_count = sum(1 for v in phase_statuses.values()
                         if isinstance(v, dict) and v.get("status") == "completed")
        with st.expander(
            f"📁 {p['name']}  ·  {p.get('design_type','')}  ·  "
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
