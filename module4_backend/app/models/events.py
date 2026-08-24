"""
Pydantic models for all four WebSocket queue lifecycle events.
Field names are FROZEN — do not rename without a team decision (contract v0.1).
All four events are pushed to the single Staff Portal WebSocket connection (module 6).
"""
from typing import Literal, Optional

from pydantic import BaseModel


class NewQueueEntryEvent(BaseModel):
    event: Literal["new_queue_entry"] = "new_queue_entry"
    token_id: str
    # Unified "Token N" format — same number spoken aloud and printed on receipt.
    # FLAG 5: Staff Portal owner to confirm if an additional customer_name field
    # is needed for auth flows alongside this display name.
    customer_display_name: str
    transaction_type: str
    amount: Optional[float] = None
    queue_position: int
    issued_at: str   # ISO 8601 UTC


class QueueCalledEvent(BaseModel):
    event: Literal["queue_called"] = "queue_called"
    token_id: str
    teller_id: str


class TransactionCompletedEvent(BaseModel):
    event: Literal["transaction_completed"] = "transaction_completed"
    token_id: str


class TokenExpiredEvent(BaseModel):
    event: Literal["token_expired"] = "token_expired"
    token_id: str
