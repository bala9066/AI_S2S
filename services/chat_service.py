"""
ChatService — handles Phase 1 conversational requirements capture.

Responsible for:
- Routing user messages to RequirementsAgent
- Persisting conversation history to DB (via ProjectService, async methods)
- Resolving phase_complete signals and updating phase status in DB
- Writing output files through StorageAdapter

app.py never calls the agent directly — it calls this service.
All DB writes use async session methods so the FastAPI event loop is not blocked.
"""

from __future__ import annotations

import logging
from typing import Optional

from config import settings
from services.project_service import ProjectService
from services.storage import StorageAdapter

log = logging.getLogger(__name__)


class ChatService:
    """Orchestrates Phase 1 chat: user → agent → DB → UI response."""

    def __init__(
        self,
        project_service: Optional[ProjectService] = None,
        storage: Optional[StorageAdapter] = None,
    ):
        self._proj_svc = project_service or ProjectService()
        self._storage = storage or StorageAdapter.local(settings.output_dir)

    async def send_message(self, project_id: int, user_message: str) -> dict:
        """
        Send a message to the Phase 1 agent and persist everything to DB.

        Returns:
            {
                "response": str,           — text to display in chat
                "draft_pending": bool,     — show Approve/Change buttons
                "phase_complete": bool,    — Phase 1 is done
                "outputs": {filename: content},
            }
        """
        proj = await self._proj_svc.async_get(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        # Persist user message first (so it's saved even if agent crashes)
        # Uses async session — does not block the event loop
        await self._proj_svc.async_append_conversation(project_id, "user", user_message)

        # Build context with full conversation history (re-fetch to include new message)
        proj = await self._proj_svc.async_get(project_id)
        history = proj.get("conversation_history", [])

        # Call the agent
        from agents.requirements_agent import RequirementsAgent
        agent = RequirementsAgent()

        try:
            result = await agent.execute(
                project_context={
                    "project_id": project_id,
                    "name": proj["name"],
                    "design_type": proj["design_type"],
                    "conversation_history": history,
                    "output_dir": proj["output_dir"],
                },
                user_input=user_message,
            )
        except Exception:
            log.exception("chat.agent_failed", extra={"project_id": project_id})
            raise

        response_text = result.get("response", "")
        phase_complete = result.get("phase_complete", False)
        draft_pending = result.get("draft_pending", False)
        outputs = result.get("outputs", {})

        # Persist assistant reply (async)
        await self._proj_svc.async_append_conversation(
            project_id=project_id,
            role="assistant",
            content=response_text,
            design_parameters=result.get("parameters"),
        )

        # Write output files through StorageAdapter (sync file I/O — acceptable)
        if outputs:
            self._storage.write_outputs(proj["name"], outputs)

        # Update phase status atomically in DB (async)
        if phase_complete:
            await self._proj_svc.async_set_phase_status(project_id, "P1", "completed")
            log.info("chat.phase1_complete", extra={"project_id": project_id})
        elif draft_pending:
            await self._proj_svc.async_set_phase_status(project_id, "P1", "draft_pending")
            log.info("chat.draft_pending", extra={"project_id": project_id})

        return {
            "response": response_text,
            "draft_pending": draft_pending,
            "phase_complete": phase_complete,
            "outputs": {k: str(v) for k, v in outputs.items()},
            "model_used": result.get("model_used", ""),
        }
