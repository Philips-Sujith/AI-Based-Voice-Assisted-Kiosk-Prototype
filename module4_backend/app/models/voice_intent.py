"""
Pydantic model for Voice AI → Backend payload.
Field names are FROZEN — do not rename without a team decision (contract v0.1).
"""
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class VoiceIntentPayload(BaseModel):
    session_id: str
    status: Literal["ok", "error"]
    language: str
    intent: str
    # Informational only — backend recomputes auth requirement from intent.
    # Stored for audit/mismatch detection; NEVER used as the auth gate.
    requires_auth: bool
    entities: Dict[str, Any] = {}
    confidence: float = Field(ge=0.0, le=1.0)
    raw_transcript: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
