from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

REQUEST_FIELDS = (
    "session_id",
    "customer_id",
    "transaction_type",
    "amount",
    "timestamp",
)
RESPONSE_FIELDS = (
    "status",
    "token_id",
    "qr_payload",
    "hmac_signature",
    "expires_at",
)


@dataclass(frozen=True)
class SigningRequest:
    session_id: str
    customer_id: str
    transaction_type: str
    amount: Decimal
    timestamp: datetime

    @classmethod
    def from_values(
        cls,
        session_id: str,
        customer_id: str,
        transaction_type: str,
        amount: Decimal,
        timestamp: datetime,
    ) -> "SigningRequest":
        return cls(session_id, customer_id, transaction_type, amount, timestamp)

    def token_values(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "customer_id": self.customer_id,
            "transaction_type": self.transaction_type,
            "amount": int(self.amount),
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
        }


@dataclass(frozen=True)
class SigningResponse:
    status: str
    token_id: str
    qr_payload: str
    hmac_signature: str
    expires_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "token_id": self.token_id,
            "qr_payload": self.qr_payload,
            "hmac_signature": self.hmac_signature,
            "expires_at": self.expires_at,
        }
