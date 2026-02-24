"""
Hardware Pipeline - Streamlit Main Entry Point
"""

import streamlit as st
from pathlib import Path
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Hardware Pipeline",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    # Initialize tab from query params (allows programmatic switching)
    if "tab" not in st.query_params:
        st.query_params["tab"] = "new"
    current_tab = st.query_params["tab"]

    # Sidebar
    with st.sidebar:
        st.title("Hardware Pipeline")
        st.caption("AI-Powered Hardware Design Automation")
        st.divider()

        st.markdown("### Pipeline Phases")
        phases = [
            ("1️⃣", "Requirements Capture", "P1"),
            ("2️⃣", "HRS Generation", "P2"),
            ("3️⃣", "Compliance Validation", "P3"),
            ("4️⃣", "Netlist Generation", "P4"),
            ("5️⃣", "PCB Layout (Manual)", "P5"),
            ("6️⃣", "GLR Generation", "P6"),
            ("7️⃣", "FPGA HDL (Manual)", "P7"),
            ("8a", "SRS Generation", "P8a"),
            ("8b", "SDD Generation", "P8b"),
            ("8c", "Code Generation", "P8c"),
        ]

        # Show phase status if project is loaded
        if "current_project" in st.session_state:
            project = st.session_state.current_project
            statuses = project.get("phase_statuses", {})
            for icon, name, phase_id in phases:
                status = statuses.get(phase_id, {}).get("status", "pending")
                status_icon = {
                    "pending": "⬜", "in_progress": "🔄",
                    "completed": "✅", "failed": "❌", "skipped": "⏭️"
                }.get(status, "⬜")
                st.text(f"{status_icon} {icon} {name}")
        else:
            for icon, name, _ in phases:
                st.text(f"⬜ {icon} {name}")

        st.divider()
        st.markdown("### System Info")
        try:
            from config import settings
            st.text(f"Mode: {'Air-Gapped' if settings.is_air_gapped else 'Online'}")
            st.text(f"Primary: {settings.primary_model}")
            st.text(f"Fast: {settings.fast_model}")

            st.divider()
            st.markdown("### API Key Status")
            api_status = settings.get_api_key_status()
            configured_count = sum(1 for is_configured, _ in api_status.values() if is_configured)
            st.caption(f"{configured_count}/{len(api_status)} configured")
            for provider, (_, icon) in api_status.items():
                st.text(f"{icon} {provider}")
        except ImportError:
            st.text("Config not loaded")
        except Exception as e:
            st.text(f"Config error: {e}")

    # Main content
    st.title("Hardware Pipeline")
    st.markdown("**AI-Powered Hardware Design Automation** | IEEE Compliant | Air-Gap Ready")
    st.divider()

    # Tab definitions with icons
    tabs = {
        "new": "📝 New Project",
        "chat": "💬 Design Chat",
        "docs": "📄 Documents",
        "netlist": "🔌 Netlist Viewer",
        "code": "🔍 Code Review",
        "dashboard": "📊 Dashboard",
    }

    # Render tab buttons
    cols = st.columns(len(tabs))
    for i, (key, label) in enumerate(tabs.items()):
        with cols[i]:
            if st.button(label, use_container_width=True, type="primary" if key == current_tab else "secondary"):
                st.query_params["tab"] = key
                st.rerun()

    st.divider()

    # Render active tab content
    if current_tab == "new":
        render_new_project()
    elif current_tab == "chat":
        render_design_chat()
    elif current_tab == "docs":
        render_documents()
    elif current_tab == "netlist":
        render_netlist_viewer()
    elif current_tab == "code":
        render_code_review()
    elif current_tab == "dashboard":
        render_dashboard()


def _create_project_directly(name: str, description: str, design_type: str) -> None:
    """Helper function to create project directly in database."""
    from database.models import get_session, ProjectDB

    session = get_session()
    project_dir = Path("output") / name.replace(" ", "_").lower()
    project_dir.mkdir(parents=True, exist_ok=True)
    db_proj = ProjectDB(
        name=name, description=description,
        design_type=design_type, output_dir=str(project_dir),
    )
    session.add(db_proj)
    session.commit()
    st.session_state.current_project = {
        "id": db_proj.id, "name": name, "output_dir": str(project_dir)
    }
    st.session_state.project_id = db_proj.id
    session.close()
    st.success(f"Project '{name}' created locally!")
    # Auto-switch to Design Chat tab
    st.query_params["tab"] = "chat"
    st.rerun()


def render_new_project():
    """New project creation form."""
    st.header("Create New Project")

    with st.form("new_project_form"):
        name = st.text_input("Project Name", placeholder="e.g., BLDC Motor Controller 10kW")
        description = st.text_area(
            "Description",
            placeholder="Brief description of the hardware design project..."
        )
        design_type = st.selectbox(
            "Design Type",
            ["general", "rf", "motor_control", "power", "digital", "sensor", "industrial"],
            help="Helps the AI tailor its questions and component recommendations"
        )

        submitted = st.form_submit_button("Create Project", type="primary")

        if submitted and name:
            from config import settings
            api_url = f"{settings.api_base_url}/api/v1/projects"

            with st.spinner("Creating project..."):
                try:
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.post(
                            api_url,
                            json={"name": name, "description": description, "design_type": design_type},
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            st.session_state.current_project = result
                            st.session_state.project_id = result["id"]
                            st.success(f"Project '{name}' created!")
                            # Auto-switch to Design Chat tab
                            st.query_params["tab"] = "chat"
                            st.rerun()
                        elif resp.status_code in (400, 422):
                            st.error(f"Validation error: {resp.text}")
                        elif resp.status_code == 500:
                            st.error("Server error. Please try again or contact support.")
                        else:
                            st.error(f"Error {resp.status_code}: {resp.text}")
                except httpx.ConnectError:
                    # Fallback: direct DB creation without API
                    st.warning("API server not running. Creating project directly...")
                    _create_project_directly(name, description, design_type)
                except httpx.TimeoutException:
                    st.error("Request timed out. The API server may be busy.")
                except httpx.HTTPError as e:
                    st.error(f"HTTP error: {e}")
                except Exception as e:
                    logger.exception("Unexpected error creating project")
                    st.error(f"Unexpected error: {e}")


def render_design_chat():
    """Phase 1: Conversational requirements capture."""
    st.header("Design Chat - Requirements Capture")

    if "project_id" not in st.session_state:
        st.info("Create a project first in the 'New Project' tab.")
        return

    # Show phase completion status if previously completed
    if st.session_state.get("phase1_complete"):
        st.success("✅ **Phase 1 Complete!** Requirements have been captured.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📄 View Generated Documents", use_container_width=True):
                st.query_params["tab"] = "docs"
                st.rerun()
        with col2:
            if st.button("🔄 Start New Requirements Chat", use_container_width=True):
                st.session_state.chat_messages = []
                st.session_state.phase1_complete = False
                st.rerun()
        st.divider()

    # Initialize chat history
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": (
                    "Welcome to Hardware Pipeline! I'm your AI design assistant.\n\n"
                    "Tell me about the hardware you want to design. For example:\n"
                    "- *'Design a 3-phase BLDC motor controller with 10kW output, 48V bus'*\n"
                    "- *'I need an RF amplifier with 40dBm output at 2.4GHz'*\n"
                    "- *'Design a power supply: 48V input, 3.3V/5V/12V outputs, 200W total'*\n\n"
                    "I'll ask clarifying questions to understand your requirements fully."
                ),
            }
        ]

    # Display chat messages
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if user_input := st.chat_input("Describe your hardware design..."):
        # Add user message
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Get AI response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    import asyncio
                    from agents.requirements_agent import RequirementsAgent

                    agent = RequirementsAgent()
                    project = st.session_state.current_project

                    result = asyncio.run(agent.execute(
                        project_context={
                            "project_id": project.get("id"),
                            "name": project.get("name", ""),
                            "design_type": project.get("design_type", "general"),
                            "conversation_history": st.session_state.chat_messages,
                            "output_dir": project.get("output_dir", "output"),
                        },
                        user_input=user_input,
                    ))

                    response = result.get("response", "I'm processing your request...")
                    st.markdown(response)
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": response}
                    )

                    # Show generated outputs if phase complete
                    if result.get("phase_complete"):
                        st.session_state.phase1_complete = True
                        st.balloons()  # Celebration animation
                        st.success("✅ **Phase 1 Complete!** Requirements captured successfully.")

                        # Show generated files with better formatting
                        if result.get("outputs"):
                            st.markdown("### 📁 Generated Documents")
                            cols = st.columns(min(4, len(result["outputs"])))
                            for i, fname in enumerate(result["outputs"].keys()):
                                with cols[i % len(cols)]:
                                    st.info(f"**{fname}**")

                            with st.expander("📄 View Document Contents", expanded=False):
                                for fname, content in result["outputs"].items():
                                    st.markdown(f"**{fname}**")
                                    st.code(content, language="markdown", height=200)

                            # Add action buttons
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                if st.button("📄 View Documents", use_container_width=True):
                                    st.query_params["tab"] = "docs"
                                    st.rerun()
                            with col2:
                                if st.button("🔄 New Chat", use_container_width=True):
                                    st.session_state.chat_messages = []
                                    st.session_state.phase1_complete = False
                                    st.rerun()
                            with col3:
                                st.markdown("*Phase 1 done!*")

                except ImportError as e:
                    error_msg = f"Module not found: {e}. Please ensure all dependencies are installed."
                    logger.error(f"Import error: {e}")
                    st.error(error_msg)
                except asyncio.TimeoutError:
                    error_msg = "The AI request timed out. Please try again."
                    st.error(error_msg)
                except ConnectionError as e:
                    error_msg = "Connection error. Please check your network and API keys."
                    logger.error(f"Connection error: {e}")
                    st.error(error_msg)
                except Exception as e:
                    logger.exception("Unexpected error in design chat")
                    st.error(f"Error: {str(e)}")


def render_documents():
    """View and download generated documents (HRS, SRS, SDD, GLR)."""
    st.header("Generated Documents")

    if "project_id" not in st.session_state:
        st.info("Create a project first.")
        return

    project = st.session_state.get("current_project", {})
    output_dir = Path(project.get("output_dir", "output"))

    if not output_dir.exists():
        st.info("No documents generated yet. Complete the design phases first.")
        return

    # Find all .md files in output
    md_files = sorted(output_dir.glob("*.md"))
    if not md_files:
        st.info("No documents generated yet.")
        return

    for md_file in md_files:
        with st.expander(f"📄 {md_file.name}", expanded=False):
            content = md_file.read_text(encoding="utf-8")
            st.markdown(content)
            st.download_button(
                label=f"Download {md_file.name}",
                data=content,
                file_name=md_file.name,
                mime="text/markdown",
                key=f"download_{md_file.name}",
            )


def render_netlist_viewer():
    """Phase 4: Interactive netlist visualization."""
    st.header("Netlist Viewer")

    if "project_id" not in st.session_state:
        st.info("Create a project first.")
        return

    project = st.session_state.get("current_project", {})
    output_dir = Path(project.get("output_dir", "output"))
    netlist_file = output_dir / "netlist_visual.md"

    if netlist_file.exists():
        content = netlist_file.read_text(encoding="utf-8")
        st.markdown(content)
    else:
        st.info("Netlist not generated yet. Complete Phases 1-4 first.")


def render_code_review():
    """Phase 8c: Code review results."""
    st.header("Code Review")

    if "project_id" not in st.session_state:
        st.info("Create a project first.")
        return

    project = st.session_state.get("current_project", {})
    output_dir = Path(project.get("output_dir", "output"))
    review_file = output_dir / "code_review_report.md"

    if review_file.exists():
        content = review_file.read_text(encoding="utf-8")
        st.markdown(content)
    else:
        st.info("Code not generated yet. Complete all phases first.")


def render_dashboard():
    """Project overview dashboard."""
    st.header("Dashboard")

    # Load all projects
    try:
        from database.models import get_session, ProjectDB
        session = get_session()
        projects = session.query(ProjectDB).order_by(ProjectDB.created_at.desc()).all()

        if not projects:
            st.info("No projects yet. Create one in the 'New Project' tab.")
            return

        for p in projects:
            with st.expander(f"📁 {p.name} ({p.design_type})", expanded=(len(projects) == 1)):
                col1, col2, col3 = st.columns(3)
                col1.metric("Phase", p.current_phase or "P1")
                col2.metric("Type", p.design_type)
                col3.metric("Created", p.created_at.strftime("%Y-%m-%d") if p.created_at else "N/A")

                if st.button(f"Load Project", key=f"load_{p.id}"):
                    st.session_state.current_project = {
                        "id": p.id,
                        "name": p.name,
                        "design_type": p.design_type,
                        "output_dir": p.output_dir,
                        "phase_statuses": p.phase_statuses or {},
                    }
                    st.session_state.project_id = p.id
                    st.session_state.chat_messages = []
                    st.rerun()

        session.close()
    except ImportError as e:
        st.error(f"Database module not found: {e}")
    except OSError as e:
        st.error(f"Database connection error: {e}")
    except Exception as e:
        logger.exception("Dashboard error")
        st.error(f"Database error: {e}")


if __name__ == "__main__":
    main()
