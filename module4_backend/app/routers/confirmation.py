"""
POST /api/v1/session/{session_id}/confirm
Customer verbal reconfirmation step.  Called by Voice AI after it parses
the customer's spoken yes/no in response to the transaction summary prompt.

Request body: { "session_id": "uuid", "confirmed": true | false }

On confirmed=true:
  1. FSM → confirmed
  2. Backend → Security (async HTTP sign request)
  3. Security → Backend (signed token)
  4. FSM → queued
  5. Assign token number + queue position
  6. Publish new_queue_entry to Staff Portal via Redis
  7. Launch background expiry task
  Returns: { status, state, token_id, token_number, queue_position, qr_payload, expires_at }

On confirmed=false:
  FSM → idle
  Returns: { status, state }

FLAG 7: Voice AI owner must call this endpoint after parsing the customer's
spoken yes/no.  This is a new contract addition Voice AI needs to absorb.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.models.confirmation import ConfirmationBody
from app.models.events import NewQueueEntryEvent
from app.models.security import SecuritySignRequest
from app.services.queue_manager import queue_manager
from app.services.redis_publisher import publish_event
from app.services.security_client import request_token_signing
from app.session_store import session_store

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/session/{session_id}/confirm")
async def confirm_transaction(session_id: str, body: ConfirmationBody):
    """
    Customer verbal reconfirmation.  Valid only when FSM is in awaiting_confirmation.
    """
    if body.session_id != session_id:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "SESSION_ID_MISMATCH",
                "error_message": "Path session_id and body session_id do not match.",
            },
        )

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

    if machine.state != "awaiting_confirmation":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "error",
                "error_code": "INVALID_STATE",
                "error_message": (
                    f"Session is in state '{machine.state}', "
                    "expected 'awaiting_confirmation'."
                ),
            },
        )

    # ── Customer rejected ──────────────────────────────────────────────────
    if not body.confirmed:
        machine.customer_rejected()
        logger.info("[%s] Customer rejected. FSM → idle.", session_id)
        return {"status": "ok", "state": "idle"}

    # ── Customer confirmed ─────────────────────────────────────────────────
    machine.customer_confirmed()
    logger.info(
        "[%s] Customer confirmed. FSM → confirmed. Calling Security.", session_id
    )

    # Build the signing request (customer_id is None/null for non-auth flows)
    sign_request = SecuritySignRequest(
        session_id=session_id,
        customer_id=context.customer_id,
        transaction_type=context.intent,
        amount=context.entities.get("amount"),
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    # ── Security round-trip ────────────────────────────────────────────────
    try:
        signed = await request_token_signing(sign_request)
    except Exception as exc:
        machine.error_occurred()
        logger.error("[%s] Security service failed: %s", session_id, exc)
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "error_code": "SECURITY_SERVICE_ERROR",
                "error_message": str(exc),
            },
        )

    # Store signed token data in context
    context.token_id = signed.token_id
    context.qr_payload = signed.qr_payload
    context.hmac_signature = signed.hmac_signature
    context.expires_at = signed.expires_at

    # FSM → queued
    machine.token_signed()

    # Assign token number and queue position (sequential daily counter)
    context.token_number = queue_manager.next_token_number()
    context.queue_position = queue_manager.current_queue_size()

    # "Token N" — the same number spoken aloud, printed on receipt, shown on dashboard
    customer_display_name = f"Token {context.token_number}"

    # Publish new_queue_entry to Staff Portal via Redis Pub/Sub
    event = NewQueueEntryEvent(
        token_id=signed.token_id,
        customer_display_name=customer_display_name,
        transaction_type=context.intent,
        amount=context.entities.get("amount"),
        queue_position=context.queue_position,
        issued_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    await publish_event(event.model_dump())

    # Launch background expiry task — cancelled by /complete if teller acts first
    context.expiry_task = queue_manager.launch_expiry_task(
        session_id=session_id,
        token_id=signed.token_id,
        expires_at=signed.expires_at,
    )

    logger.info(
        "[%s] Queued. token_id=%s token_number=%d position=%d expires_at=%s",
        session_id,
        signed.token_id,
        context.token_number,
        context.queue_position,
        signed.expires_at,
    )

    return {
        "status": "ok",
        "state": machine.state,          # queued
        "token_id": signed.token_id,
        "token_number": context.token_number,
        "queue_position": context.queue_position,
        "qr_payload": signed.qr_payload,
        "expires_at": signed.expires_at,
    }
