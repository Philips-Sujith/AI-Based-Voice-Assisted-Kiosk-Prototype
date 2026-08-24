"""
HTTP client for the Security module.
Backend sends a signing request and receives a signed QR token in return.
Security owns key management; backend never sees or stores the signing key.

FLAG 4: Real Security module URL is injected via SECURITY_SERVICE_URL env var.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models.security import SecuritySignRequest, SecuritySignResponse

logger = logging.getLogger(__name__)


async def request_token_signing(request: SecuritySignRequest) -> SecuritySignResponse:
    """
    POST to the Security module's /sign endpoint.
    Raises httpx.HTTPStatusError on HTTP error responses.
    Raises ValueError if Security returns status != 'ok'.
    """
    logger.info(
        "Requesting token signing from Security. session_id=%s transaction_type=%s amount=%s",
        request.session_id,
        request.transaction_type,
        request.amount,
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.SECURITY_SERVICE_URL}/sign",
            json=request.model_dump(),
        )
        response.raise_for_status()
        data = response.json()

    if data.get("status") != "ok":
        raise ValueError(
            f"Security service returned error: "
            f"{data.get('error_code')} — {data.get('error_message')}"
        )

    signed = SecuritySignResponse(**data)
    logger.info(
        "Token signed. token_id=%s expires_at=%s",
        signed.token_id,
        signed.expires_at,
    )
    return signed
