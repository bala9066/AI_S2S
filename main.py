"""
Hardware Pipeline - FastAPI Server
Serves the backend API for the Streamlit UI and agent orchestration.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database.models import get_engine, get_session, ProjectDB, PhaseOutputDB
from schemas.project import ProjectCreate, Project

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info(f"Starting {settings.app_name}...")
    get_engine()  # Initialize DB
    output_dir = settings.base_dir / "output"
    output_dir.mkdir(exist_ok=True)
    logger.info(f"Database initialized. Output dir: {output_dir}")

    # Seed ChromaDB with sample components if empty
    from tools.seed_components import seed_if_empty
    seed_if_empty()

    yield
    # Shutdown
    logger.info("Shutting down Hardware Pipeline.")


app = FastAPI(
    title=settings.app_name,
    description="AI-powered hardware design automation pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health Check ---

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.app_env,
        "air_gapped": settings.is_air_gapped,
        "timestamp": datetime.now().isoformat(),
    }


# --- Project CRUD ---

@app.post("/api/v1/projects", response_model=dict)
async def create_project(project: ProjectCreate):
    """Create a new hardware design project."""
    session = get_session()
    try:
        # Create output directory
        project_dir = settings.base_dir / "output" / project.name.replace(" ", "_").lower()
        project_dir.mkdir(parents=True, exist_ok=True)

        db_project = ProjectDB(
            name=project.name,
            description=project.description,
            design_type=project.design_type,
            output_dir=str(project_dir),
        )
        session.add(db_project)
        session.commit()
        session.refresh(db_project)

        return {
            "id": db_project.id,
            "name": db_project.name,
            "output_dir": db_project.output_dir,
            "message": f"Project '{db_project.name}' created successfully.",
        }
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/api/v1/projects")
async def list_projects():
    """List all projects."""
    session = get_session()
    try:
        projects = session.query(ProjectDB).order_by(ProjectDB.created_at.desc()).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "design_type": p.design_type,
                "current_phase": p.current_phase,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in projects
        ]
    finally:
        session.close()


@app.get("/api/v1/projects/{project_id}")
async def get_project(project_id: int):
    """Get project details."""
    session = get_session()
    try:
        project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "design_type": project.design_type,
            "current_phase": project.current_phase,
            "phase_statuses": project.phase_statuses or {},
            "conversation_history": project.conversation_history or [],
            "design_parameters": project.design_parameters or {},
            "output_dir": project.output_dir,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        }
    finally:
        session.close()


# --- Phase Execution ---

@app.post("/api/v1/projects/{project_id}/phases/{phase_number}/execute")
async def execute_phase(project_id: int, phase_number: str, body: dict = {}):
    """Execute a specific phase for a project."""
    session = get_session()
    try:
        project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        user_input = body.get("user_input", "")

        # Import orchestrator lazily to avoid circular imports
        from agents.orchestrator import OrchestratorAgent
        orchestrator = OrchestratorAgent()

        result = await orchestrator.execute_phase(
            project_id=project_id,
            phase_number=phase_number,
            user_input=user_input,
            session=session,
        )

        return result
    except Exception as e:
        logger.error(f"Phase {phase_number} execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# --- Chat (Phase 1 Conversational) ---

@app.post("/api/v1/projects/{project_id}/chat")
async def chat(project_id: int, body: dict):
    """Send a message to the Phase 1 Requirements Agent."""
    session = get_session()
    try:
        project = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        user_message = body.get("message", "")
        if not user_message:
            raise HTTPException(status_code=400, detail="Message is required")

        from agents.requirements_agent import RequirementsAgent
        agent = RequirementsAgent()

        # Load conversation history
        history = project.conversation_history or []
        history.append({"role": "user", "content": user_message})

        result = await agent.execute(
            project_context={
                "project_id": project.id,
                "name": project.name,
                "design_type": project.design_type,
                "conversation_history": history,
                "output_dir": project.output_dir,
            },
            user_input=user_message,
        )

        # Save updated conversation history
        history.append({"role": "assistant", "content": result.get("response", "")})
        project.conversation_history = history
        project.design_parameters = result.get("parameters", project.design_parameters)
        session.commit()

        return {
            "response": result.get("response", ""),
            "phase_complete": result.get("phase_complete", False),
            "outputs": result.get("outputs", {}),
        }
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# --- Run ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.fastapi_host,
        port=settings.fastapi_port,
        reload=settings.debug,
    )
