"""
ProjectService — authoritative source of truth for project + phase lifecycle.

Rules:
- DB is always written first; session_state/UI is derived from DB reads.
- Phase status transitions are atomic: in_progress → completed|failed.
- No business logic may live in app.py or route handlers.

Session strategy:
- Sync  methods (create, get, list_all, set_phase_status, …):
    Used by FastAPI route handlers and Streamlit — SQLite is fast enough for
    these short, infrequent reads/writes.
- Async methods (async_set_phase_status, async_append_conversation, …):
    Used inside PipelineService / ChatService background tasks so they never
    block the FastAPI async event loop.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from config import settings
from database.models import (
    get_session,
    get_async_session_factory,
    ProjectDB,
    PhaseOutputDB,
)
from services.storage import StorageAdapter

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data-transfer types (plain dicts — no Pydantic dependency in service layer)
# ---------------------------------------------------------------------------

def _project_to_dict(p: ProjectDB) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description or "",
        "design_type": p.design_type or "general",
        "current_phase": p.current_phase or "P1",
        "phase_statuses": dict(p.phase_statuses or {}),
        "conversation_history": list(p.conversation_history or []),
        "design_parameters": dict(p.design_parameters or {}),
        "output_dir": p.output_dir or "",
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ---------------------------------------------------------------------------
# ProjectService
# ---------------------------------------------------------------------------

class ProjectService:
    """Manages project lifecycle and phase status — DB is the single source of truth."""

    def __init__(self, storage: Optional[StorageAdapter] = None):
        self._storage = storage or StorageAdapter.local(settings.output_dir)

    # ── CRUD ────────────────────────────────────────────────────────────────

    def create(self, name: str, description: str = "", design_type: str = "rf") -> dict:
        """Create a project in the DB and its output directory."""
        session = get_session()
        try:
            output_dir = self._storage.project_dir(name)
            db = ProjectDB(
                name=name,
                description=description,
                design_type=design_type,
                output_dir=str(output_dir),
                current_phase="P1",
                phase_statuses={},
                conversation_history=[],
            )
            session.add(db)
            session.commit()
            session.refresh(db)
            log.info("project.created", extra={"project_id": db.id, "project_name": name})
            return _project_to_dict(db)
        except Exception:
            session.rollback()
            log.exception("project.create_failed", extra={"project_name": name})
            raise
        finally:
            session.close()

    def get(self, project_id: int) -> Optional[dict]:
        """Load project from DB — always fresh, never from session state."""
        session = get_session()
        try:
            # Force fresh read — expire all cached objects and flush any pending state
            session.expire_all()
            p = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            return _project_to_dict(p) if p else None
        finally:
            session.close()

    def list_all(self) -> list[dict]:
        session = get_session()
        try:
            rows = session.query(ProjectDB).order_by(ProjectDB.created_at.desc()).all()
            return [_project_to_dict(p) for p in rows]
        finally:
            session.close()

    # ── Phase status ────────────────────────────────────────────────────────

    # All AI phase IDs downstream of P1 — must be reset when P1 requirements change
    _DOWNSTREAM_AI_PHASES = ["P2", "P3", "P4", "P6", "P7a", "P8a", "P8b", "P8c"]

    def set_phase_status(
        self,
        project_id: int,
        phase_id: str,
        status: str,            # "in_progress" | "completed" | "failed"
        extra: Optional[dict] = None,
        reset_downstream: bool = False,
    ) -> dict:
        """
        Atomically update a phase's status in the DB.
        Returns the full updated phase_statuses dict.

        Args:
            reset_downstream: When True AND phase_id == 'P1' AND status == 'completed',
                              reset all downstream AI phases to 'pending' because P1
                              requirements changed and all outputs are now stale.
        """
        session = get_session()
        try:
            p = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if not p:
                raise ValueError(f"Project {project_id} not found")

            statuses = dict(p.phase_statuses or {})
            was_already_complete = statuses.get(phase_id, {}).get("status") == "completed"
            entry: dict = {"status": status, "updated_at": datetime.utcnow().isoformat()}
            if extra:
                entry.update(extra)
            statuses[phase_id] = entry

            # When P1 is RE-completed (was already done → new requirements submitted),
            # reset all downstream AI phases to pending so they pick up fresh requirements.
            if (phase_id == "P1" and status == "completed"
                    and (reset_downstream or was_already_complete)):
                ts = datetime.utcnow().isoformat()
                for ds_phase in self._DOWNSTREAM_AI_PHASES:
                    if ds_phase in statuses:
                        statuses[ds_phase] = {"status": "pending", "updated_at": ts}
                log.info(
                    "phase.downstream_reset: P1 requirements updated — "
                    "downstream phases reset to pending",
                    extra={"project_id": project_id},
                )

            p.phase_statuses = statuses
            flag_modified(p, "phase_statuses")  # force SQLAlchemy to detect JSON column change
            if status == "completed" and phase_id == "P1":
                p.current_phase = "P2"
            session.commit()

            log.info(
                "phase.status_updated",
                extra={"project_id": project_id, "phase": phase_id, "status": status},
            )
            return statuses
        except Exception:
            session.rollback()
            log.exception("phase.status_update_failed",
                          extra={"project_id": project_id, "phase": phase_id})
            raise
        finally:
            session.close()

    def get_phase_status(self, project_id: int, phase_id: str) -> str:
        """Return status string for a phase, defaulting to 'pending'."""
        proj = self.get(project_id)
        if not proj:
            return "pending"
        return proj["phase_statuses"].get(phase_id, {}).get("status", "pending")

    # ── Conversation history ─────────────────────────────────────────────────

    def append_conversation(
        self,
        project_id: int,
        role: str,
        content: str,
        design_parameters: Optional[dict] = None,
    ) -> None:
        """Append a message to the project's conversation history in DB."""
        session = get_session()
        try:
            p = session.query(ProjectDB).filter(ProjectDB.id == project_id).first()
            if not p:
                raise ValueError(f"Project {project_id} not found")
            history = list(p.conversation_history or [])
            history.append({"role": role, "content": content})
            p.conversation_history = history
            flag_modified(p, "conversation_history")  # force SQLAlchemy to detect JSON column change
            if design_parameters:
                p.design_parameters = {**(p.design_parameters or {}), **design_parameters}
                flag_modified(p, "design_parameters")
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Phase outputs ────────────────────────────────────────────────────────

    def record_phase_output(
        self,
        project_id: int,
        phase_id: str,
        phase_name: str,
        content: str,
        output_type: str = "markdown",
        file_path: str = "",
        model_used: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        duration_seconds: float = 0.0,
        status: str = "completed",
        error_message: str = "",
    ) -> None:
        session = get_session()
        try:
            row = PhaseOutputDB(
                project_id=project_id,
                phase_number=phase_id,
                phase_name=phase_name,
                output_type=output_type,
                file_path=file_path,
                content=content,
                model_used=model_used,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                duration_seconds=duration_seconds,
                status=status,
                error_message=error_message,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
            session.add(row)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Async variants (used by background-task services) ───────────────────
    # These mirror the sync methods above but use AsyncSession so they don't
    # block the FastAPI event loop during long pipeline runs.

    async def async_set_phase_status(
        self,
        project_id: int,
        phase_id: str,
        status: str,
        extra: Optional[dict] = None,
        reset_downstream: bool = False,
    ) -> dict:
        """Async version of set_phase_status — safe to call from background tasks."""
        factory = get_async_session_factory()
        async with factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(ProjectDB).where(ProjectDB.id == project_id)
                )
                p = result.scalar_one_or_none()
                if not p:
                    raise ValueError(f"Project {project_id} not found")

                statuses = dict(p.phase_statuses or {})
                was_already_complete = statuses.get(phase_id, {}).get("status") == "completed"
                entry: dict = {"status": status, "updated_at": datetime.utcnow().isoformat()}
                if extra:
                    entry.update(extra)
                statuses[phase_id] = entry

                # When P1 requirements are updated (re-completed), reset all downstream
                # AI phases to pending so they pick up the fresh requirements.md.
                if (phase_id == "P1" and status == "completed"
                        and (reset_downstream or was_already_complete)):
                    ts = datetime.utcnow().isoformat()
                    for ds_phase in self._DOWNSTREAM_AI_PHASES:
                        if ds_phase in statuses:
                            statuses[ds_phase] = {"status": "pending", "updated_at": ts}
                    log.info(
                        "phase.downstream_reset (async): P1 updated — downstream set to pending",
                        extra={"project_id": project_id},
                    )

                p.phase_statuses = statuses
                flag_modified(p, "phase_statuses")  # force SQLAlchemy to detect JSON column change
                if status == "completed" and phase_id == "P1":
                    p.current_phase = "P2"

            log.info(
                "phase.status_updated (async)",
                extra={"project_id": project_id, "phase": phase_id, "status": status},
            )
            return statuses

    async def async_get(self, project_id: int) -> Optional[dict]:
        """Async version of get — reads project from DB without blocking."""
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(ProjectDB).where(ProjectDB.id == project_id)
            )
            p = result.scalar_one_or_none()
            return _project_to_dict(p) if p else None

    async def async_append_conversation(
        self,
        project_id: int,
        role: str,
        content: str,
        design_parameters: Optional[dict] = None,
    ) -> None:
        """Async version of append_conversation."""
        factory = get_async_session_factory()
        async with factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(ProjectDB).where(ProjectDB.id == project_id)
                )
                p = result.scalar_one_or_none()
                if not p:
                    raise ValueError(f"Project {project_id} not found")
                history = list(p.conversation_history or [])
                history.append({"role": role, "content": content})
                p.conversation_history = history
                flag_modified(p, "conversation_history")  # force SQLAlchemy to detect JSON column change
                if design_parameters:
                    p.design_parameters = {**(p.design_parameters or {}), **design_parameters}
                    flag_modified(p, "design_parameters")

    async def async_record_phase_output(
        self,
        project_id: int,
        phase_id: str,
        phase_name: str,
        content: str,
        output_type: str = "markdown",
        file_path: str = "",
        model_used: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        duration_seconds: float = 0.0,
        status: str = "completed",
        error_message: str = "",
    ) -> None:
        """Async version of record_phase_output."""
        factory = get_async_session_factory()
        async with factory() as session:
            async with session.begin():
                row = PhaseOutputDB(
                    project_id=project_id,
                    phase_number=phase_id,
                    phase_name=phase_name,
                    output_type=output_type,
                    file_path=file_path,
                    content=content,
                    model_used=model_used,
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                    duration_seconds=duration_seconds,
                    status=status,
                    error_message=error_message,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                )
                session.add(row)

    async def async_get_phase_status(self, project_id: int, phase_id: str) -> str:
        """Async version of get_phase_status."""
        proj = await self.async_get(project_id)
        if not proj:
            return "pending"
        return proj["phase_statuses"].get(phase_id, {}).get("status", "pending")
