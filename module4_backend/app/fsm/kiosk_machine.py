import logging

from transitions import Machine

from app.config import settings
from app.fsm.session_context import SessionContext

logger = logging.getLogger(__name__)

# ── States ───────────────────────────────────────────────────────────────────
#
# intent_received is TRANSIENT — the on_enter callback immediately fires the
# correct outbound trigger (auth_needed or no_auth_needed) so the machine
# never rests there. The /api/v1/voice-intent endpoint therefore always returns
# awaiting_auth or awaiting_confirmation, never intent_received.
#
STATES = [
    "idle",
    "intent_received",       # transient — see on_enter_intent_received
    "awaiting_auth",
    "awaiting_confirmation",
    "confirmed",
    "queued",
    "completed",             # customer was served; distinct from expired
    "expired",               # token timed out unclaimed (no-show)
    "error",
]

# ── Transitions ───────────────────────────────────────────────────────────────
#
# Auth gate guards are NOT defined here as transition conditions — the biometrics
# router evaluates can_retry_auth() before choosing which trigger to call.
# This keeps the decision explicit and testable without re-entering the machine.
#
TRANSITIONS = [
    # idle → intent_received (confidence gate checked externally in router)
    {"trigger": "voice_intent_received", "source": "idle",              "dest": "intent_received"},
    # idle → idle (low confidence self-loop; no state change)
    {"trigger": "low_confidence",        "source": "idle",              "dest": "idle"},

    # intent_received → * (auto-fired by on_enter_intent_received)
    {"trigger": "auth_needed",           "source": "intent_received",   "dest": "awaiting_auth"},
    {"trigger": "no_auth_needed",        "source": "intent_received",   "dest": "awaiting_confirmation"},

    # awaiting_auth → awaiting_confirmation (auth passed)
    {"trigger": "auth_passed",           "source": "awaiting_auth",     "dest": "awaiting_confirmation"},
    # awaiting_auth → awaiting_auth (retry; before action increments retry_count)
    {
        "trigger": "auth_failed_retry",
        "source":  "awaiting_auth",
        "dest":    "awaiting_auth",
        "before":  "increment_retry_count",   # fires BEFORE transition; count is updated
    },
    # awaiting_auth → idle (retries exhausted; before logs; after clears context)
    {
        "trigger": "auth_failed_terminal",
        "source":  "awaiting_auth",
        "dest":    "idle",
        "before":  "notify_auth_failed_terminal",
        "after":   "clear_session_data",
    },

    # awaiting_confirmation → confirmed / idle
    {"trigger": "customer_confirmed",    "source": "awaiting_confirmation", "dest": "confirmed"},
    {
        "trigger": "customer_rejected",
        "source":  "awaiting_confirmation",
        "dest":    "idle",
        "after":   "clear_session_data",
    },

    # confirmed → queued (after Security round-trip completes in the router)
    {"trigger": "token_signed",          "source": "confirmed",         "dest": "queued"},

    # queued → terminal states (DISTINCT — served ≠ no-show)
    {"trigger": "transaction_completed", "source": "queued",            "dest": "completed"},
    {"trigger": "token_expired",         "source": "queued",            "dest": "expired"},

    # terminal → idle (ready for next customer)
    {
        "trigger": "session_reset",
        "source":  ["completed", "expired"],
        "dest":    "idle",
        "after":   "clear_session_data",
    },

    # error handling
    {"trigger": "error_occurred", "source": "*",      "dest": "error"},
    {
        "trigger": "error_reset",
        "source":  "error",
        "dest":    "idle",
        "after":   "clear_session_data",
    },
]


class KioskMachine:
    """
    Per-session Finite State Machine.
    One instance per customer session, keyed by session_id in SessionStore.

    The transitions library injects all trigger methods directly onto self
    (e.g. self.voice_intent_received(), self.auth_needed(), ...) and manages
    self.state.  on_enter_<state> methods are auto-discovered as entry callbacks.
    """

    def __init__(self, context: SessionContext) -> None:
        self.context = context
        self._machine = Machine(
            model=self,
            states=STATES,
            transitions=TRANSITIONS,
            initial="idle",
            auto_transitions=False,
            ignore_invalid_triggers=False,
            # No queued=True: nested trigger calls in on_enter_ are processed
            # synchronously so the outer trigger call returns with the final state.
        )

    # ── State Entry Callbacks ─────────────────────────────────────────────────

    def on_enter_intent_received(self) -> None:
        """
        Auto-cascade: intent_received is transient.
        Evaluates backend_auth_needed (computed from intent, NOT from Voice AI's
        requires_auth flag) and immediately fires the correct outbound trigger.
        After this method returns the machine rests in awaiting_auth or
        awaiting_confirmation — never in intent_received.
        """
        if self.context.backend_auth_needed:
            logger.info(
                "[%s] intent='%s' → backend_auth_needed=True → awaiting_auth",
                self.context.session_id,
                self.context.intent,
            )
            self.auth_needed()       # injected trigger; transitions synchronously
        else:
            logger.info(
                "[%s] intent='%s' → backend_auth_needed=False → awaiting_confirmation",
                self.context.session_id,
                self.context.intent,
            )
            self.no_auth_needed()    # injected trigger; transitions synchronously

    # ── Transition Actions ────────────────────────────────────────────────────

    def increment_retry_count(self) -> None:
        """
        `before` action on auth_failed_retry.
        Increments retry_count BEFORE the transition completes so the router's
        next can_retry_auth() check sees the updated value.
        """
        self.context.increment_retry_count()
        logger.warning(
            "[%s] Auth attempt failed. retry_count=%d (max=%d)",
            self.context.session_id,
            self.context.retry_count,
            settings.MAX_AUTH_RETRIES,
        )

    def notify_auth_failed_terminal(self) -> None:
        """Called before the auth_failed_terminal transition fires."""
        logger.error(
            "[%s] Auth failed terminally after %d retries. Session resetting to idle.",
            self.context.session_id,
            self.context.retry_count,
        )

    def clear_session_data(self) -> None:
        """Called after any transition that returns the machine to idle."""
        logger.info(
            "[%s] Session data cleared. FSM → idle. Kiosk ready for next customer.",
            self.context.session_id,
        )
