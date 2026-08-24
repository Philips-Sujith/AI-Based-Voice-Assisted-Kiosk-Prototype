"""GET /api/v1/session/{session_id}/state — debug / Frontend introspection."""
import logging

from fastapi import APIRouter, HTTPException

from app.session_store import session_store

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/session/{session_id}/state")
async def get_session_state(session_id: str):
    """Returns the current FSM state and a safe subset of the session context."""
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "SESSION_NOT_FOUND",
                "error_message": f"No active session for session_id '{session_id}'.",
            },
        )
    context, machine = session
    return {
        "status": "ok",
        "session_id": session_id,
        "state": machine.state,
        "context": context.safe_subset(),
        "active_sessions": session_store.count(),
    }
