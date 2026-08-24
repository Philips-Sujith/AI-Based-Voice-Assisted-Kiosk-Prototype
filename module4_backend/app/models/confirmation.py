"""Pydantic model for the customer confirmation endpoint request body."""
from pydantic import BaseModel


class ConfirmationBody(BaseModel):
    """
    Body for POST /api/v1/session/{session_id}/confirm.
    Sent by Voice AI after parsing the customer's spoken yes/no.

    confirmed=True  → fire customer_confirmed → FSM proceeds to signing
    confirmed=False → fire customer_rejected  → FSM resets to idle
    """
    session_id: str
    confirmed: bool
