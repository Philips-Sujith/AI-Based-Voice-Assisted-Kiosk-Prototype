import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings


class SessionContext:
    """
    Per-session data carrier attached to every KioskMachine instance.
    Holds all data collected across the full customer session lifecycle.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id: str = session_id
        self.created_at: datetime = datetime.now(timezone.utc)

        # ── Voice AI payload fields ──────────────────────────────────────────
        self.intent: Optional[str] = None
        self.language: Optional[str] = None
        self.entities: Dict[str, Any] = {}
        self.confidence: float = 0.0
        self.raw_transcript: Optional[str] = None
        # Voice AI's flag — stored for audit/logging only; never used as auth gate
        self.requires_auth_from_voice_ai: Optional[bool] = None

        # ── Backend-computed (source of truth for auth gate) ─────────────────
        self.backend_auth_needed: bool = False

        # ── Biometrics fields ────────────────────────────────────────────────
        self.customer_id: Optional[str] = None           # None for non-auth flows
        self.auth_status: Optional[str] = None
        self.methods_used: List[str] = []                # variable-length array
        self.confidence_scores: Dict[str, float] = {}
        self.liveness_passed: Optional[bool] = None
        self.retry_count: int = 0

        # ── Security / token fields ──────────────────────────────────────────
        self.token_id: Optional[str] = None
        self.qr_payload: Optional[str] = None
        self.hmac_signature: Optional[str] = None
        self.expires_at: Optional[str] = None

        # ── Queue fields ─────────────────────────────────────────────────────
        self.token_number: Optional[int] = None          # sequential daily counter
        self.queue_position: Optional[int] = None

        # ── Background task handle ───────────────────────────────────────────
        self.expiry_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ── Retry helpers ────────────────────────────────────────────────────────

    def increment_retry_count(self) -> None:
        """Called as a `before` action on the auth_failed_retry FSM transition."""
        self.retry_count += 1

    def can_retry_auth(self) -> bool:
        """Guard: true while there are retries remaining."""
        return self.retry_count < settings.MAX_AUTH_RETRIES

    def retries_exhausted(self) -> bool:
        """Guard: true once all retries have been used."""
        return self.retry_count >= settings.MAX_AUTH_RETRIES

    # ── Safe external representation ─────────────────────────────────────────

    def safe_subset(self) -> dict:
        """
        Returns a safe subset of context fields for external exposure.
        Raw biometric scores are deliberately excluded.
        """
        return {
            "session_id": self.session_id,
            "intent": self.intent,
            "language": self.language,
            "entities": self.entities,
            "backend_auth_needed": self.backend_auth_needed,
            "retry_count": self.retry_count,
            "customer_id": self.customer_id,
            "token_id": self.token_id,
            "token_number": self.token_number,
            "queue_position": self.queue_position,
            "expires_at": self.expires_at,
        }
