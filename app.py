"""
Hardware Pipeline - Streamlit Main Entry Point
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Hardware Pipeline",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
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
        except Exception:
            st.text("Config not loaded")

    # Main content
    st.title("Hardware Pipeline")
    st.markdown("**AI-Powered Hardware Design Automation** | IEEE Compliant | Air-Gap Ready")
    st.divider()

    # Tabs for main workflow
    tab_new, tab_chat, tab_docs, tab_netlist, tab_code, tab_dashboard = st.tabs([
        "New Project", "Design Chat", "Documents",
        "Netlist Viewer", "Code Review", "Dashboard"
    ])

    with tab_new:
        render_new_project()

    with tab_chat:
        render_design_chat()

    with tab_docs:
        render_documents()

    with tab_netlist:
        render_netlist_viewer()

    with tab_code:
        render_code_review()

    with tab_dashboard:
        render_dashboard()


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
            import httpx
            try:
                with httpx.Client() as client:
                    resp = client.post(
                        "http://localhost:8000/api/v1/projects",
                        json={"name": name, "description": description, "design_type": design_type},
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        st.session_state.current_project = result
                        st.session_state.project_id = result["id"]
                        st.success(f"Project '{name}' created! Switch to 'Design Chat' to start.")
                    else:
                        st.error(f"Error: {resp.text}")
            except httpx.ConnectError:
                # Fallback: direct DB creation without API
                st.warning("API server not running. Creating project directly...")
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
                st.success(f"Project '{name}' created locally! Switch to 'Design Chat' to start.")


def render_design_chat():
    """Phase 1: Conversational requirements capture."""
    st.header("Design Chat - Requirements Capture")

    if "project_id" not in st.session_state:
        st.info("Create a project first in the 'New Project' tab.")
        return

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
                        st.success("Phase 1 Complete! Requirements captured.")
                        if result.get("outputs"):
                            with st.expander("Generated Files"):
                                for fname, content in result["outputs"].items():
                                    st.markdown(f"**{fname}**")
                                    st.code(content[:500] + "..." if len(content) > 500 else content)

                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    st.error(error_msg)
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": error_msg}
                    )


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
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    f"Download {md_file.name}",
                    content,
                    file_name=md_file.name,
                    mime="text/markdown",
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
    except Exception as e:
        st.error(f"Database error: {e}")


if __name__ == "__main__":
    main()
