"""
GET /api/v1/token/{token_id}/verify
Used by the Staff Portal before a teller acts on a token.
Verifies the token exists, checks expiry, and returns transaction details.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.session_store import session_store

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/token/{token_id}/verify")
async def verify_token(token_id: str):
    """
    Staff Portal calls this when a customer presents their QR code.
    Returns transaction details if the token is valid and unexpired.
    """
    result = session_store.find_by_token_id(token_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "TOKEN_NOT_FOUND",
                "error_message": f"No session found for token_id '{token_id}'.",
            },
        )
    ctx, machine = result

    # Enforce expiry — Backend is responsible per the contract
    if ctx.expires_at:
        expires_dt = datetime.fromisoformat(ctx.expires_at.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires_dt:
            raise HTTPException(
                status_code=410,
                detail={
                    "status": "error",
                    "error_code": "TOKEN_EXPIRED",
                    "error_message": f"Token expired at {ctx.expires_at}.",
                },
            )

    return {
        "status": "ok",
        "token_id": token_id,
        "session_id": ctx.session_id,
        "fsm_state": machine.state,
        "transaction_type": ctx.intent,
        "amount": ctx.entities.get("amount"),
        "customer_id": ctx.customer_id,       # None for non-auth flows
        "token_number": ctx.token_number,
        "queue_position": ctx.queue_position,
        "expires_at": ctx.expires_at,
        "hmac_signature": ctx.hmac_signature,  # teller portal can re-verify server-side
    }
