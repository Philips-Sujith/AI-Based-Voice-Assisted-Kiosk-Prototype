"""
Pydantic models for Backend ↔ Security module.
Field names are FROZEN — do not rename without a team decision (contract v0.1).
"""
from typing import Literal, Optional

from pydantic import BaseModel


class SecuritySignRequest(BaseModel):
    """Backend → Security: request to sign a transaction."""
    session_id: str
    customer_id: Optional[str]   # null (None) for non-account-holder flows
    transaction_type: str
    amount: Optional[float] = None
    timestamp: str               # ISO 8601 UTC


class SecuritySignResponse(BaseModel):
    """Security → Backend: signed, ephemeral token."""
    status: Literal["ok", "error"]
    token_id: str
    qr_payload: str              # base64-encoded blob
    hmac_signature: str          # hex-encoded HMAC-SHA256
    expires_at: str              # ISO 8601 UTC — backend enforces expiry
    error_code: Optional[str] = None
    error_message: Optional[str] = None
