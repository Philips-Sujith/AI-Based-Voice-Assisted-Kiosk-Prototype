"""
FSM unit tests — covers every state transition in the state machine.
Tests are grouped by the flow they exercise.
"""
import pytest

from app.config import settings
from app.fsm.kiosk_machine import KioskMachine
from app.fsm.session_context import SessionContext
from app.services.auth_gate import compute_backend_auth_needed


def make(session_id: str = "test-001", intent: str = "withdraw",
         confidence: float = 0.91) -> tuple[SessionContext, KioskMachine]:
    ctx = SessionContext(session_id)
    ctx.intent = intent
    ctx.confidence = confidence
    ctx.backend_auth_needed = compute_backend_auth_needed(intent)
    machine = KioskMachine(ctx)
    return ctx, machine


# ── Initial state ─────────────────────────────────────────────────────────────

class TestInitialState:
    def test_starts_idle(self):
        _, m = make()
        assert m.state == "idle"


# ── Auth-required flows (deposit / withdraw) ──────────────────────────────────

class TestAuthRequiredFlow:
    def test_withdraw_cascades_to_awaiting_auth(self):
        _, m = make(intent="withdraw")
        m.voice_intent_received()
        assert m.state == "awaiting_auth"

    def test_deposit_cascades_to_awaiting_auth(self):
        _, m = make(intent="deposit")
        m.voice_intent_received()
        assert m.state == "awaiting_auth"

    def test_intent_received_is_never_a_resting_state(self):
        """After voice_intent_received the machine must not stay in intent_received."""
        _, m = make(intent="withdraw")
        m.voice_intent_received()
        assert m.state != "intent_received"

    def test_auth_passed_goes_to_awaiting_confirmation(self):
        _, m = make(intent="withdraw")
        m.voice_intent_received()
        m.auth_passed()
        assert m.state == "awaiting_confirmation"


# ── No-auth flows (send_money / open_account) ─────────────────────────────────

class TestNoAuthFlow:
    def test_send_money_cascades_to_awaiting_confirmation(self):
        _, m = make(intent="send_money")
        m.voice_intent_received()
        assert m.state == "awaiting_confirmation"

    def test_open_account_cascades_to_awaiting_confirmation(self):
        _, m = make(intent="open_account")
        m.voice_intent_received()
        assert m.state == "awaiting_confirmation"

    def test_no_auth_skips_awaiting_auth_entirely(self):
        _, m = make(intent="send_money")
        m.voice_intent_received()
        assert m.state not in {"awaiting_auth", "intent_received"}


# ── Retry logic ───────────────────────────────────────────────────────────────

class TestRetryLogic:
    def _in_awaiting_auth(self):
        ctx, m = make(intent="withdraw")
        m.voice_intent_received()
        return ctx, m

    def test_initial_retry_count_is_zero(self):
        ctx, _ = self._in_awaiting_auth()
        assert ctx.retry_count == 0

    def test_retry_increments_count(self):
        ctx, m = self._in_awaiting_auth()
        m.auth_failed_retry()
        assert ctx.retry_count == 1

    def test_each_retry_increments_separately(self):
        ctx, m = self._in_awaiting_auth()
        m.auth_failed_retry()
        m.auth_failed_retry()
        assert ctx.retry_count == 2

    def test_retry_stays_in_awaiting_auth(self):
        ctx, m = self._in_awaiting_auth()
        m.auth_failed_retry()
        assert m.state == "awaiting_auth"

    def test_terminal_resets_to_idle(self):
        ctx, m = self._in_awaiting_auth()
        ctx.retry_count = settings.MAX_AUTH_RETRIES   # simulate exhausted retries
        m.auth_failed_terminal()
        assert m.state == "idle"

    def test_auth_pass_after_one_retry(self):
        """Customer can still pass after a failed attempt."""
        ctx, m = self._in_awaiting_auth()
        m.auth_failed_retry()
        assert m.state == "awaiting_auth"
        m.auth_passed()
        assert m.state == "awaiting_confirmation"

    def test_low_confidence_stays_idle(self):
        _, m = make(confidence=0.4)
        m.low_confidence()
        assert m.state == "idle"


# ── Confirmation step ─────────────────────────────────────────────────────────

class TestConfirmationStep:
    def _in_awaiting_confirmation(self, intent="send_money"):
        ctx, m = make(intent=intent)
        m.voice_intent_received()
        if ctx.backend_auth_needed:
            m.auth_passed()
        assert m.state == "awaiting_confirmation"
        return ctx, m

    def test_confirmed_goes_to_confirmed(self):
        _, m = self._in_awaiting_confirmation()
        m.customer_confirmed()
        assert m.state == "confirmed"

    def test_rejected_goes_to_idle(self):
        _, m = self._in_awaiting_confirmation()
        m.customer_rejected()
        assert m.state == "idle"

    def test_confirmation_required_even_after_auth(self):
        _, m = self._in_awaiting_confirmation(intent="withdraw")
        assert m.state == "awaiting_confirmation"


# ── Queued and terminal states ────────────────────────────────────────────────

class TestQueuedAndTerminal:
    def _in_queued(self, intent="send_money"):
        ctx, m = make(intent=intent)
        m.voice_intent_received()
        if ctx.backend_auth_needed:
            m.auth_passed()
        m.customer_confirmed()
        m.token_signed()
        assert m.state == "queued"
        return ctx, m

    def test_token_signed_goes_to_queued(self):
        _, m = self._in_queued()
        assert m.state == "queued"

    def test_transaction_completed_goes_to_completed(self):
        _, m = self._in_queued()
        m.transaction_completed()
        assert m.state == "completed"

    def test_token_expired_goes_to_expired(self):
        _, m = self._in_queued()
        m.token_expired()
        assert m.state == "expired"

    def test_completed_and_expired_are_distinct(self):
        """Served ≠ no-show — the two terminal outcomes must be distinguishable."""
        _, m1 = self._in_queued()
        _, m2 = self._in_queued()
        m1.transaction_completed()
        m2.token_expired()
        assert m1.state == "completed"
        assert m2.state == "expired"
        assert m1.state != m2.state

    def test_completed_resets_to_idle(self):
        _, m = self._in_queued()
        m.transaction_completed()
        m.session_reset()
        assert m.state == "idle"

    def test_expired_resets_to_idle(self):
        _, m = self._in_queued()
        m.token_expired()
        m.session_reset()
        assert m.state == "idle"


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_error_from_idle(self):
        _, m = make()
        m.error_occurred()
        assert m.state == "error"

    def test_error_from_awaiting_auth(self):
        _, m = make(intent="withdraw")
        m.voice_intent_received()
        m.error_occurred()
        assert m.state == "error"

    def test_error_reset_to_idle(self):
        _, m = make()
        m.error_occurred()
        m.error_reset()
        assert m.state == "idle"
