"""
POST /api/v1/voice-intent
Receives a parsed intent from Voice AI, validates it, populates the session
context, fires the FSM, and returns the already-advanced state.

Key invariant: this endpoint NEVER returns state='intent_received'.
By the time the trigger call returns, on_enter_intent_received has already
auto-cascaded to awaiting_auth or awaiting_confirmation.
"""
import logging

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.voice_intent import VoiceIntentPayload
from app.services.auth_gate import check_requires_auth_mismatch, compute_backend_auth_needed
from app.session_store import session_store

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/voice-intent")
async def receive_voice_intent(payload: VoiceIntentPayload):
    """
    Entry point for every customer session.
    Called once by Voice AI after it has fully parsed an utterance into intent + entities.
    """
    if payload.status != "ok":
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": payload.error_code or "VOICE_AI_ERROR",
                "error_message": payload.error_message or "Voice AI reported an error.",
            },
        )

    context, machine = session_store.get_or_create(payload.session_id)

    # Session must be idle before accepting a new intent
    if machine.state != "idle":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "error",
                "error_code": "SESSION_NOT_IDLE",
                "error_message": (
                    f"Session '{payload.session_id}' is in state '{machine.state}'. "
                    "Cannot accept a new intent until the session resets to idle."
                ),
            },
        )

    # Populate context with Voice AI data
    context.intent = payload.intent
    context.language = payload.language
    context.entities = payload.entities
    context.confidence = payload.confidence
    context.raw_transcript = payload.raw_transcript
    context.requires_auth_from_voice_ai = payload.requires_auth  # stored for audit

    # ── Auth gate (security-critical) ──────────────────────────────────────
    # Backend derives auth requirement from intent — independent of Voice AI's flag.
    # Any mismatch is logged as a security warning; backend's value always wins.
    context.backend_auth_needed = compute_backend_auth_needed(payload.intent)
    check_requires_auth_mismatch(payload.intent, payload.requires_auth)

    # ── Confidence gate ────────────────────────────────────────────────────
    if payload.confidence < settings.CONFIDENCE_THRESHOLD:
        machine.low_confidence()
        logger.info(
            "[%s] Low confidence %.2f < %.2f. Signalling re-prompt.",
            payload.session_id,
            payload.confidence,
            settings.CONFIDENCE_THRESHOLD,
        )
        return {
            "status": "ok",
            "session_id": payload.session_id,
            "state": machine.state,   # idle
            "action": "re_prompt",
            "message": (
                f"Confidence {payload.confidence:.2f} is below threshold "
                f"{settings.CONFIDENCE_THRESHOLD}. Please re-prompt the customer."
            ),
        }

    # ── Fire FSM ────────────────────────────────────────────────────────────
    # voice_intent_received → intent_received → auto-cascade (on_enter callback)
    # → awaiting_auth  (if deposit/withdraw)
    # → awaiting_confirmation  (if send_money/open_account)
    # The call returns only after the cascade completes.
    machine.voice_intent_received()

    logger.info(
        "[%s] Voice intent accepted. intent='%s' backend_auth_needed=%s → state='%s'",
        payload.session_id,
        payload.intent,
        context.backend_auth_needed,
        machine.state,
    )

    return {
        "status": "ok",
        "session_id": payload.session_id,
        "state": machine.state,   # awaiting_auth or awaiting_confirmation
    }
