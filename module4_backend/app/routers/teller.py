"""
Teller action endpoints — called by the Staff Portal (module 6).

POST /api/v1/teller/{token_id}/call      → emit queue_called event
POST /api/v1/teller/{token_id}/complete  → FSM queued→completed, emit transaction_completed
POST /api/v1/teller/{token_id}/expire    → FSM queued→expired, emit token_expired

The /expire endpoint is also called internally by the background expiry task.
The /complete endpoint cancels the background expiry task so both terminal
states (completed, expired) remain mutually exclusive.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.events import QueueCalledEvent, TokenExpiredEvent, TransactionCompletedEvent
from app.services.queue_manager import queue_manager
from app.services.redis_publisher import publish_event
from app.session_store import session_store

router = APIRouter()
logger = logging.getLogger(__name__)


class TellerCallBody(BaseModel):
    teller_id: str


@router.post("/teller/{token_id}/call")
async def teller_call(token_id: str, body: TellerCallBody):
    """Teller calls the customer to their counter. Emits queue_called event."""
    result = session_store.find_by_token_id(token_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "error_code": "TOKEN_NOT_FOUND"},
        )
    ctx, _ = result

    event = QueueCalledEvent(token_id=token_id, teller_id=body.teller_id)
    await publish_event(event.model_dump())
    logger.info(
        "[%s] queue_called. token_id=%s teller_id=%s",
        ctx.session_id,
        token_id,
        body.teller_id,
    )
    return {"status": "ok"}


@router.post("/teller/{token_id}/complete")
async def teller_complete(token_id: str):
    """
    Teller marks the transaction done.
    Cancels the expiry background task and transitions FSM → completed → idle.
    """
    result = session_store.find_by_token_id(token_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "error_code": "TOKEN_NOT_FOUND"},
        )
    ctx, machine = result

    if machine.state != "queued":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "error",
                "error_code": "INVALID_STATE",
                "error_message": f"Session is in state '{machine.state}', expected 'queued'.",
            },
        )

    # Cancel expiry task — transaction completed before token expired
    if ctx.expiry_task and not ctx.expiry_task.done():
        ctx.expiry_task.cancel()
        logger.info("[%s] Expiry task cancelled (completed first).", ctx.session_id)

    machine.transaction_completed()   # queued → completed
    queue_manager.decrement_queue()

    event = TransactionCompletedEvent(token_id=token_id)
    await publish_event(event.model_dump())
    logger.info("[%s] transaction_completed. token_id=%s", ctx.session_id, token_id)

    # Auto-reset to idle for next customer
    machine.session_reset()
    return {"status": "ok"}


@router.post("/teller/{token_id}/expire")
async def teller_expire(token_id: str):
    """
    Token expired — called by the background expiry task at expires_at.
    Also callable manually by Staff Portal for early expiry.
    Transitions FSM → expired → idle.
    """
    result = session_store.find_by_token_id(token_id)
    if result is None:
        # Session may already be cleaned up by a race with /complete — not an error
        logger.info("Expire called for unknown token %s — already cleaned up.", token_id)
        return {"status": "ok", "note": "Session already cleaned up."}

    ctx, machine = result

    if machine.state != "queued":
        logger.info(
            "[%s] Expire called but state is '%s' — no action.",
            ctx.session_id,
            machine.state,
        )
        return {"status": "ok", "note": f"Session in state '{machine.state}', no action taken."}

    machine.token_expired()   # queued → expired
    queue_manager.decrement_queue()

    event = TokenExpiredEvent(token_id=token_id)
    await publish_event(event.model_dump())
    logger.info("[%s] token_expired. token_id=%s", ctx.session_id, token_id)

    # Auto-reset to idle for next customer
    machine.session_reset()
    return {"status": "ok"}
