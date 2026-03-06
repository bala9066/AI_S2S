"""
Hardware Pipeline — FastAPI backend.

Design principles applied here:
- Thin route handlers: parse request → call service → return response.
- No business logic in this file (lives in services/).
- CORS restricted to known origins only.
- Secrets validated at startup — missing keys cause an early, clear error.
- Pipeline runs as BackgroundTask (non-blocking, UI polls for status).
- Structured logging via Python logging throughout.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from config import settings
from logging_config import configure_logging

configure_logging()
log = logging.getLogger("hardware_pipeline.api")


# ── Startup / shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup.begin", extra={"env": settings.app_env})

    # 1. Validate secrets — fail fast with a clear message
    _validate_secrets()

    # 2. Initialise DB (creates tables if they don't exist)
    from database.models import get_engine
    get_engine()
    log.info("startup.db_ready")

    # 3. Ensure output directory exists
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    # 4. Seed ChromaDB component index (idempotent)
    try:
        from tools.seed_components import seed_if_empty
        seed_if_empty()
        log.info("startup.chroma_ready")
    except Exception as exc:
        log.debug("startup.chroma_seed_skipped: %s (optional)", exc)

    log.info("startup.complete", extra={"air_gapped": settings.is_air_gapped})
    yield
    log.info("shutdown.complete")


def _validate_secrets() -> None:
    """
    Fail fast if required secrets are missing.
    Logs a clear warning for optional keys so operators know what's degraded.
    """
    if not settings.has_any_llm_key:
        if settings.app_env == "production":
            raise RuntimeError(
                "No LLM API key configured (ANTHROPIC_API_KEY or GLM_API_KEY). "
                "Set at least one before starting in production."
            )
        log.warning("startup.no_llm_key — running in air-gap/Ollama mode")

    optional_keys = {
        "DIGIKEY_CLIENT_ID": settings.digikey_client_id,
        "MOUSER_API_KEY": settings.mouser_api_key,
        "OPENAI_API_KEY": settings.openai_api_key,
    }
    for name, val in optional_keys.items():
        if not val:
            log.info("startup.optional_key_missing: %s (degraded mode)", name)


# ── App factory ────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    description="AI-powered hardware design automation pipeline",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,   # hide Swagger in prod
    redoc_url=None,
)

# CORS: restrict to known origins only (never wildcard in any real deploy)
_ALLOWED_ORIGINS = [
    f"http://localhost:{settings.streamlit_port}",
    f"http://127.0.0.1:{settings.streamlit_port}",
    # Production domain added via CORS_ORIGIN env var
    *([os.environ["CORS_ORIGIN"]] if "CORS_ORIGIN" in os.environ else []),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


# ── Service singletons (created once per process) ─────────────────────────────

def _project_svc():
    from services.project_service import ProjectService
    return ProjectService()

def _chat_svc():
    from services.chat_service import ChatService
    return ChatService()

def _pipeline_svc():
    from services.pipeline_service import PipelineService
    return PipelineService()


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.app_env,
        "air_gapped": settings.is_air_gapped,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ── Projects ───────────────────────────────────────────────────────────────────

@app.post("/api/v1/projects", status_code=201, tags=["projects"])
async def create_project(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    try:
        return _project_svc().create(
            name=name,
            description=body.get("description", ""),
            design_type=body.get("design_type", "rf"),
        )
    except Exception as exc:
        log.exception("api.create_project_failed")
        raise HTTPException(500, str(exc))


@app.get("/api/v1/projects", tags=["projects"])
async def list_projects():
    return _project_svc().list_all()


@app.get("/api/v1/projects/{project_id}", tags=["projects"])
async def get_project(project_id: int):
    proj = _project_svc().get(project_id)
    if not proj:
        raise HTTPException(404, f"Project {project_id} not found")
    return proj


# ── Chat (Phase 1) ─────────────────────────────────────────────────────────────

@app.post("/api/v1/projects/{project_id}/chat", tags=["chat"])
async def chat(project_id: int, body: dict):
    """Send a message to the Phase 1 requirements agent."""
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message is required")

    try:
        result = await _chat_svc().send_message(project_id, message)
        log.info("api.chat_ok",
                 extra={"project_id": project_id, "phase_complete": result.get("phase_complete")})
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        log.exception("api.chat_failed", extra={"project_id": project_id})
        raise HTTPException(500, str(exc))


# ── Pipeline (P2→P8c background execution) ────────────────────────────────────

@app.post("/api/v1/projects/{project_id}/pipeline/run", tags=["pipeline"])
async def run_pipeline(project_id: int, background_tasks: BackgroundTasks):
    """
    Start the full P2→P8c pipeline as a background task.
    Returns immediately; UI should poll GET /projects/{id} for status.
    """
    proj = _project_svc().get(project_id)
    if not proj:
        raise HTTPException(404, f"Project {project_id} not found")

    if _project_svc().get_phase_status(project_id, "P1") != "completed":
        raise HTTPException(400, "Phase 1 must be completed before running the pipeline")

    svc = _pipeline_svc()
    background_tasks.add_task(svc.run_pipeline, project_id)
    log.info("api.pipeline_started", extra={"project_id": project_id})
    return {"status": "pipeline_started", "project_id": project_id}


VALID_PHASES = {"P1", "P2", "P3", "P4", "P5", "P6", "P8a", "P8b", "P8c"}

@app.post("/api/v1/projects/{project_id}/phases/{phase_id}/execute", tags=["pipeline"])
async def execute_single_phase(project_id: int, phase_id: str, background_tasks: BackgroundTasks):
    """Execute one specific phase as a background task."""
    if phase_id not in VALID_PHASES:
        raise HTTPException(400, f"Invalid phase '{phase_id}'. Must be one of: {sorted(VALID_PHASES)}")
    proj = _project_svc().get(project_id)
    if not proj:
        raise HTTPException(404, f"Project {project_id} not found")
    try:
        svc = _pipeline_svc()
        background_tasks.add_task(svc.run_single_phase, project_id, phase_id)
        return {"status": "phase_started", "phase_id": phase_id, "project_id": project_id}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ── Phase status (polling endpoint for UI) ─────────────────────────────────────

@app.get("/api/v1/projects/{project_id}/status", tags=["pipeline"])
async def get_project_status(project_id: int):
    """Lightweight status poll — returns phase_statuses without full conversation."""
    proj = _project_svc().get(project_id)
    if not proj:
        raise HTTPException(404, f"Project {project_id} not found")
    return {
        "project_id": project_id,
        "current_phase": proj.get("current_phase"),
        "phase_statuses": proj.get("phase_statuses", {}),
    }


# ── Test UI (standalone HTML workflow tester) ──────────────────────────────────

@app.get("/testui", response_class=HTMLResponse, tags=["ops"])
async def test_ui():
    """Serve standalone HTML workflow test page (no Streamlit needed)."""
    import pathlib
    p = pathlib.Path(__file__).parent / "test_ui.html"
    if p.exists():
        return HTMLResponse(content=p.read_text(), status_code=200)
    return HTMLResponse(content="<h1>test_ui.html not found</h1>", status_code=404)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.fastapi_host,
        port=settings.fastapi_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
