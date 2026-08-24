"""
Queue manager tests — sequential token numbering, queue size, daily reset,
and the completed-vs-expired distinction at the FSM level.
"""
import pytest

from app.services.queue_manager import QueueManager


class TestQueueManager:
    def setup_method(self):
        self.qm = QueueManager()

    def test_first_token_is_one(self):
        assert self.qm.next_token_number() == 1

    def test_sequential_numbering(self):
        nums = [self.qm.next_token_number() for _ in range(5)]
        assert nums == [1, 2, 3, 4, 5]

    def test_queue_size_increments(self):
        self.qm.next_token_number()
        self.qm.next_token_number()
        assert self.qm.current_queue_size() == 2

    def test_decrement_reduces_queue_size(self):
        self.qm.next_token_number()
        self.qm.next_token_number()
        self.qm.decrement_queue()
        assert self.qm.current_queue_size() == 1

    def test_decrement_never_below_zero(self):
        self.qm.decrement_queue()
        assert self.qm.current_queue_size() == 0

    def test_daily_reset_restarts_counter(self):
        self.qm.next_token_number()
        self.qm.next_token_number()
        self.qm.reset_daily()
        assert self.qm.next_token_number() == 1

    def test_daily_reset_clears_queue_size(self):
        self.qm.next_token_number()
        self.qm.reset_daily()
        assert self.qm.current_queue_size() == 0

    def test_token_number_continues_after_decrement(self):
        """Token numbers are NOT recycled after a customer is served; only reset daily."""
        t1 = self.qm.next_token_number()
        self.qm.decrement_queue()   # customer 1 served or expired
        t2 = self.qm.next_token_number()
        assert t2 == t1 + 1

    def test_display_name_format(self):
        """Validate the Token N display name convention."""
        n = self.qm.next_token_number()
        display = f"Token {n}"
        assert display == "Token 1"


class TestCompletedVsExpiredDistinction:
    """The two terminal states must produce different FSM states."""

    def _make_queued(self):
        from app.fsm.kiosk_machine import KioskMachine
        from app.fsm.session_context import SessionContext

        ctx = SessionContext("q-test")
        ctx.intent = "send_money"
        ctx.confidence = 0.91
        ctx.backend_auth_needed = False
        m = KioskMachine(ctx)
        m.voice_intent_received()
        m.customer_confirmed()
        m.token_signed()
        assert m.state == "queued"
        return ctx, m

    def test_completed_state_name(self):
        _, m = self._make_queued()
        m.transaction_completed()
        assert m.state == "completed"

    def test_expired_state_name(self):
        _, m = self._make_queued()
        m.token_expired()
        assert m.state == "expired"

    def test_states_are_not_equal(self):
        _, m1 = self._make_queued()
        _, m2 = self._make_queued()
        m1.transaction_completed()
        m2.token_expired()
        assert m1.state != m2.state
