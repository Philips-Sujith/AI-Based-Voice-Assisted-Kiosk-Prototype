"""
POST /api/v1/biometrics
Receives the biometrics auth result from the Biometrics module.
Only valid when the session is in awaiting_auth state.

Retry logic:
  - can_retry_auth() is evaluated BEFORE calling the trigger.
  - auth_failed_retry trigger carries a `before` action that increments retry_count.
  - After MAX_AUTH_RETRIES failures the session resets to idle.
"""
import logging

from fastapi import APIRouter, HTTPException

from app.models.biometrics import BiometricsPayload
from app.session_store import session_store

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/biometrics")
async def receive_biometrics(payload: BiometricsPayload):
    """
    Called by the Biometrics module after face auth resolves.
    Only invoked when the session intent was deposit or withdraw (requires_auth flows).
    """
    if payload.status != "ok":
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": payload.error_code or "BIOMETRICS_ERROR",
                "error_message": payload.error_message or "Biometrics reported an error.",
            },
        )

    session = session_store.get_session(payload.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "SESSION_NOT_FOUND",
                "error_message": f"No active session for session_id '{payload.session_id}'.",
            },
        )

    context, machine = session

    if machine.state != "awaiting_auth":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "error",
                "error_code": "INVALID_STATE",
                "error_message": (
                    f"Session is in state '{machine.state}', expected 'awaiting_auth'. "
                    "Biometrics result arrived out of order."
                ),
            },
        )

    # Store biometrics data in session context
    context.auth_status = payload.auth_status
    context.methods_used = payload.methods_used   # variable-length; iterate, don't index
    context.confidence_scores = payload.confidence_scores
    context.liveness_passed = payload.liveness_passed

    # ── Auth passed ────────────────────────────────────────────────────────
    if payload.auth_status == "pass":
        context.customer_id = payload.customer_id
        machine.auth_passed()
        logger.info(
            "[%s] Auth passed. customer_id=%s methods=%s → state='%s'",
            payload.session_id,
            payload.customer_id,
            payload.methods_used,
            machine.state,
        )
        return {
            "status": "ok",
            "session_id": payload.session_id,
            "state": machine.state,   # awaiting_confirmation
        }

    # ── Auth failed ────────────────────────────────────────────────────────
    # Evaluate can_retry_auth() BEFORE firing the trigger so we pick the right one.
    # The auth_failed_retry trigger's `before` action then increments retry_count.
    if context.can_retry_auth():
        machine.auth_failed_retry()   # before action: retry_count += 1
        logger.warning(
            "[%s] Auth failed. retry_count=%d. Prompting retry.",
            payload.session_id,
            context.retry_count,
        )
        return {
            "status": "ok",
            "session_id": payload.session_id,
            "state": machine.state,   # awaiting_auth (retry)
            "retry_count": context.retry_count,
            "action": "retry_auth",
        }
    else:
        machine.auth_failed_terminal()
        logger.error(
            "[%s] Auth failed terminally after %d retries. FSM → idle.",
            payload.session_id,
            context.retry_count,
        )
        return {
            "status": "ok",
            "session_id": payload.session_id,
            "state": machine.state,   # idle
            "action": "session_ended",
            "message": "Maximum authentication retries exceeded. Session has been reset.",
        }
