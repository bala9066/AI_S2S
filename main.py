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

import functools
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List

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
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


# ── Service singletons (created once per process) ─────────────────────────────
# lru_cache ensures a single instance is reused for the lifetime of the process.

@functools.lru_cache(maxsize=1)
def _project_svc():
    from services.project_service import ProjectService
    return ProjectService()

@functools.lru_cache(maxsize=1)
def _chat_svc():
    from services.chat_service import ChatService
    return ChatService()

@functools.lru_cache(maxsize=1)
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


@app.get("/api/v1/projects/{project_id}/documents/{filename}", tags=["projects"])
async def get_document(project_id: int, filename: str):
    proj = _project_svc().get(project_id)
    if not proj:
        raise HTTPException(404, f"Project {project_id} not found")
    output_dir = proj.get("output_dir")
    if not output_dir:
        raise HTTPException(404, "Project has no output directory yet")

    file_path = os.path.join(output_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404, f"Document {filename} not found")

    return FileResponse(file_path)


@app.get("/api/v1/projects/{project_id}/documents", tags=["projects"])
async def list_documents(project_id: int):
    """List all available output files for a project."""
    proj = _project_svc().get(project_id)
    output_dir = proj.get("output_dir") if proj else None
    if not output_dir:
        return []
    try:
        files = []
        for f in os.listdir(output_dir):
            full = os.path.join(output_dir, f)
            if os.path.isfile(full):
                files.append({"name": f, "size": os.path.getsize(full)})
        return sorted(files, key=lambda x: x["name"])
    except Exception:
        return []


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


class ResetPhasesRequest(BaseModel):
    phase_ids: List[str]

@app.post("/api/v1/projects/{project_id}/phases/reset", tags=["pipeline"])
async def reset_phases(project_id: int, body: ResetPhasesRequest, background_tasks: BackgroundTasks):
    """
    Reset given phases to 'pending' then immediately re-run the pipeline.
    Used by the frontend 'Re-run all stale' button after requirements change.
    """
    proj = _project_svc().get(project_id)
    if not proj:
        raise HTTPException(404, f"Project {project_id} not found")
    if not body.phase_ids:
        raise HTTPException(400, "phase_ids must not be empty")

    # Validate phase IDs
    invalid = [p for p in body.phase_ids if p not in VALID_PHASES]
    if invalid:
        raise HTTPException(400, f"Invalid phase IDs: {invalid}")

    # Reset each phase status to pending
    svc = _project_svc()
    for phase_id in body.phase_ids:
        svc.set_phase_status(project_id, phase_id, "pending")

    log.info("api.phases_reset", extra={"project_id": project_id, "phase_ids": body.phase_ids})

    # Kick off the pipeline — it will now run all the reset phases
    pipeline = _pipeline_svc()
    background_tasks.add_task(pipeline.run_pipeline, project_id)
    return {"status": "pipeline_started", "reset_phases": body.phase_ids, "project_id": project_id}


@app.get("/api/v1/projects/{project_id}/export", tags=["projects"])
async def export_project_zip(project_id: int):
    """
    Stream all project output documents as a ZIP archive.
    Frontend uses this for the 'Download All Documents' button.
    """
    import io, zipfile, pathlib

    proj = _project_svc().get(project_id)
    if not proj:
        raise HTTPException(404, f"Project {project_id} not found")

    output_dir = proj.get("output_dir")
    if not output_dir:
        raise HTTPException(404, "No output directory for this project")

    out_path = pathlib.Path(output_dir)
    if not out_path.exists():
        raise HTTPException(404, "Output directory does not exist")

    # Collect all files in output dir (non-recursive by default, recursive if nested)
    files = list(out_path.rglob("*"))
    doc_files = [f for f in files if f.is_file()]

    if not doc_files:
        raise HTTPException(404, "No documents found to export")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in doc_files:
            zf.write(f, f.relative_to(out_path))
    buf.seek(0)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (proj.get("name") or "project"))
    filename = f"{safe_name}_documents.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@app.get("/app", response_class=HTMLResponse, tags=["ops"])
async def serve_frontend():
    """Serve the React v5 frontend bundle at http://localhost:8000/app"""
    import pathlib
    p = pathlib.Path(__file__).parent / "frontend" / "bundle.html"
    if p.exists():
        return HTMLResponse(content=p.read_text(encoding="utf-8", errors="replace"), status_code=200)
    return HTMLResponse(content="<h1>Frontend not built yet. Run the React build.</h1>", status_code=404)


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
