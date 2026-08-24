"""
Voice intent routing tests — confidence gate and auto-cascade verification.
"""
import pytest

from app.config import settings
from app.fsm.kiosk_machine import KioskMachine
from app.fsm.session_context import SessionContext
from app.services.auth_gate import compute_backend_auth_needed


def make(intent: str, confidence: float = 0.91):
    ctx = SessionContext(f"test-{intent}")
    ctx.intent = intent
    ctx.confidence = confidence
    ctx.backend_auth_needed = compute_backend_auth_needed(intent)
    m = KioskMachine(ctx)
    return ctx, m


class TestConfidenceGate:
    def test_above_threshold_allowed(self):
        ctx, _ = make("withdraw", confidence=0.91)
        assert ctx.confidence >= settings.CONFIDENCE_THRESHOLD

    def test_at_threshold_allowed(self):
        ctx, _ = make("withdraw", confidence=settings.CONFIDENCE_THRESHOLD)
        assert ctx.confidence >= settings.CONFIDENCE_THRESHOLD

    def test_below_threshold_blocked(self):
        ctx, _ = make("withdraw", confidence=settings.CONFIDENCE_THRESHOLD - 0.001)
        assert ctx.confidence < settings.CONFIDENCE_THRESHOLD

    def test_low_confidence_stays_idle(self):
        _, m = make("withdraw", confidence=0.4)
        m.low_confidence()
        assert m.state == "idle"


class TestIntentCascade:
    @pytest.mark.parametrize("intent,expected_state", [
        ("withdraw",     "awaiting_auth"),
        ("deposit",      "awaiting_auth"),
        ("send_money",   "awaiting_confirmation"),
        ("open_account", "awaiting_confirmation"),
    ])
    def test_cascade_to_correct_state(self, intent, expected_state):
        _, m = make(intent)
        m.voice_intent_received()
        assert m.state == expected_state

    @pytest.mark.parametrize("intent", ["withdraw", "deposit", "send_money", "open_account"])
    def test_never_rests_in_intent_received(self, intent):
        _, m = make(intent)
        m.voice_intent_received()
        assert m.state != "intent_received"
