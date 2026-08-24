"""
Biometrics router tests — retry increment correctness and terminal transition.
"""
import pytest

from app.config import settings
from app.fsm.kiosk_machine import KioskMachine
from app.fsm.session_context import SessionContext
from app.services.auth_gate import compute_backend_auth_needed


def _in_awaiting_auth():
    ctx = SessionContext("bio-test")
    ctx.intent = "withdraw"
    ctx.confidence = 0.91
    ctx.backend_auth_needed = True
    m = KioskMachine(ctx)
    m.voice_intent_received()
    assert m.state == "awaiting_auth"
    return ctx, m


class TestRetryIncrement:
    def test_count_zero_before_any_failure(self):
        ctx, _ = _in_awaiting_auth()
        assert ctx.retry_count == 0

    def test_single_failure_increments_to_one(self):
        ctx, m = _in_awaiting_auth()
        m.auth_failed_retry()
        assert ctx.retry_count == 1

    def test_two_failures_increments_to_two(self):
        ctx, m = _in_awaiting_auth()
        m.auth_failed_retry()
        m.auth_failed_retry()
        assert ctx.retry_count == 2

    def test_count_never_decrements(self):
        ctx, m = _in_awaiting_auth()
        m.auth_failed_retry()
        m.auth_failed_retry()
        count_after_two = ctx.retry_count
        assert count_after_two == 2

    def test_can_retry_before_max(self):
        ctx, _ = _in_awaiting_auth()
        ctx.retry_count = settings.MAX_AUTH_RETRIES - 1
        assert ctx.can_retry_auth() is True

    def test_retries_exhausted_at_max(self):
        ctx, _ = _in_awaiting_auth()
        ctx.retry_count = settings.MAX_AUTH_RETRIES
        assert ctx.retries_exhausted() is True

    def test_terminal_resets_to_idle(self):
        ctx, m = _in_awaiting_auth()
        ctx.retry_count = settings.MAX_AUTH_RETRIES
        m.auth_failed_terminal()
        assert m.state == "idle"


class TestAuthPassAfterRetry:
    def test_pass_after_one_fail(self):
        ctx, m = _in_awaiting_auth()
        m.auth_failed_retry()
        assert ctx.retry_count == 1
        m.auth_passed()
        assert m.state == "awaiting_confirmation"

    def test_pass_after_two_fails(self):
        ctx, m = _in_awaiting_auth()
        m.auth_failed_retry()
        m.auth_failed_retry()
        assert ctx.retry_count == 2
        m.auth_passed()
        assert m.state == "awaiting_confirmation"
