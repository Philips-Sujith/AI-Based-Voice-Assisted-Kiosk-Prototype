"""
Confirmation step tests — customer confirm/reject transitions for both flows.
"""
import pytest

from app.fsm.kiosk_machine import KioskMachine
from app.fsm.session_context import SessionContext
from app.services.auth_gate import compute_backend_auth_needed


def _in_awaiting_confirmation(intent: str = "send_money"):
    ctx = SessionContext(f"conf-{intent}")
    ctx.intent = intent
    ctx.confidence = 0.91
    ctx.backend_auth_needed = compute_backend_auth_needed(intent)
    m = KioskMachine(ctx)
    m.voice_intent_received()
    if ctx.backend_auth_needed:
        m.auth_passed()
    assert m.state == "awaiting_confirmation", (
        f"Expected awaiting_confirmation for intent={intent}, got {m.state}"
    )
    return ctx, m


class TestConfirmation:
    @pytest.mark.parametrize("intent", ["send_money", "open_account", "withdraw", "deposit"])
    def test_confirmed_transitions_to_confirmed(self, intent):
        _, m = _in_awaiting_confirmation(intent)
        m.customer_confirmed()
        assert m.state == "confirmed"

    @pytest.mark.parametrize("intent", ["send_money", "open_account", "withdraw", "deposit"])
    def test_rejected_transitions_to_idle(self, intent):
        _, m = _in_awaiting_confirmation(intent)
        m.customer_rejected()
        assert m.state == "idle"

    def test_confirmation_required_for_non_auth_flow(self):
        """Non-auth flows must still require customer confirmation."""
        _, m = _in_awaiting_confirmation(intent="send_money")
        assert m.state == "awaiting_confirmation"

    def test_confirmation_required_after_auth(self):
        """Auth flows must also require confirmation before signing."""
        _, m = _in_awaiting_confirmation(intent="withdraw")
        assert m.state == "awaiting_confirmation"

    def test_confirmed_then_token_signed(self):
        _, m = _in_awaiting_confirmation()
        m.customer_confirmed()
        m.token_signed()
        assert m.state == "queued"
