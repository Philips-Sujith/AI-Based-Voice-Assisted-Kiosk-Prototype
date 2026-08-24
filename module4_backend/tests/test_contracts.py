"""
Contract tests — validates that no JSON key names have drifted from the
module interface contracts (v0.1).  These tests are the canary for contract
drift: if a field is renamed here, the corresponding module integration breaks.
"""
import pytest

from app.models.biometrics import BiometricsPayload
from app.models.confirmation import ConfirmationBody
from app.models.events import (
    NewQueueEntryEvent,
    QueueCalledEvent,
    TokenExpiredEvent,
    TransactionCompletedEvent,
)
from app.models.security import SecuritySignRequest, SecuritySignResponse
from app.models.voice_intent import VoiceIntentPayload


class TestVoiceIntentContract:
    def test_all_required_fields_present(self):
        p = VoiceIntentPayload(
            session_id="s-uuid",
            status="ok",
            language="ta",
            intent="withdraw",
            requires_auth=True,
            entities={"amount": 5000, "account_number": "XXXX1234"},
            confidence=0.91,
            raw_transcript="test",
        )
        assert p.session_id == "s-uuid"
        assert p.language == "ta"
        assert p.intent == "withdraw"
        assert p.requires_auth is True
        assert p.confidence == 0.91

    def test_field_names_match_contract(self):
        fields = set(VoiceIntentPayload.model_fields.keys())
        for expected in ("session_id", "status", "language", "intent",
                         "requires_auth", "entities", "confidence", "raw_transcript"):
            assert expected in fields, f"Missing field: {expected}"

    def test_entities_defaults_to_empty_dict(self):
        p = VoiceIntentPayload(
            session_id="s", status="ok", language="en",
            intent="send_money", requires_auth=False, confidence=0.88,
        )
        assert p.entities == {}


class TestBiometricsContract:
    def test_all_required_fields(self):
        p = BiometricsPayload(
            session_id="s-uuid",
            status="ok",
            auth_status="pass",
            methods_used=["face"],
            confidence_scores={"face": 0.94},
            liveness_passed=True,
            customer_id="acc_00981234",
        )
        assert p.auth_status == "pass"
        assert p.methods_used == ["face"]
        assert p.customer_id == "acc_00981234"

    def test_methods_used_is_variable_length(self):
        """Variable-length array — fingerprint can be added later with no contract change."""
        p1 = BiometricsPayload(
            session_id="s1", status="ok", auth_status="pass",
            methods_used=["face"],
            confidence_scores={"face": 0.9},
            liveness_passed=True, customer_id="acc_001",
        )
        p2 = BiometricsPayload(
            session_id="s2", status="ok", auth_status="pass",
            methods_used=["face", "fingerprint"],
            confidence_scores={"face": 0.9, "fingerprint": 0.97},
            liveness_passed=True, customer_id="acc_002",
        )
        assert len(p1.methods_used) == 1
        assert len(p2.methods_used) == 2

    def test_field_names_match_contract(self):
        fields = set(BiometricsPayload.model_fields.keys())
        for expected in ("session_id", "status", "auth_status", "methods_used",
                         "confidence_scores", "liveness_passed", "customer_id"):
            assert expected in fields, f"Missing field: {expected}"


class TestSecurityContract:
    def test_sign_request_null_customer_id(self):
        """Non-account-holder flows send customer_id=None (JSON null)."""
        req = SecuritySignRequest(
            session_id="s", customer_id=None,
            transaction_type="send_money", amount=2000,
            timestamp="2026-08-21T10:15:30Z",
        )
        assert req.customer_id is None

    def test_sign_request_with_customer_id(self):
        req = SecuritySignRequest(
            session_id="s", customer_id="acc_00981234",
            transaction_type="withdraw", amount=5000,
            timestamp="2026-08-21T10:15:30Z",
        )
        assert req.customer_id == "acc_00981234"

    def test_sign_response_fields(self):
        resp = SecuritySignResponse(
            status="ok",
            token_id="tok-uuid",
            qr_payload="base64blob",
            hmac_signature="hexhmac",
            expires_at="2026-08-21T10:25:30Z",
        )
        assert resp.token_id == "tok-uuid"
        assert resp.hmac_signature == "hexhmac"
        assert resp.expires_at == "2026-08-21T10:25:30Z"

    def test_sign_response_field_names(self):
        fields = set(SecuritySignResponse.model_fields.keys())
        for expected in ("status", "token_id", "qr_payload", "hmac_signature", "expires_at"):
            assert expected in fields, f"Missing field: {expected}"


class TestConfirmationContract:
    def test_confirmed_true(self):
        b = ConfirmationBody(session_id="s", confirmed=True)
        assert b.confirmed is True

    def test_confirmed_false(self):
        b = ConfirmationBody(session_id="s", confirmed=False)
        assert b.confirmed is False

    def test_field_names(self):
        fields = set(ConfirmationBody.model_fields.keys())
        assert "session_id" in fields
        assert "confirmed" in fields


class TestQueueEventContracts:
    def test_new_queue_entry_discriminator(self):
        e = NewQueueEntryEvent(
            token_id="tok", customer_display_name="Token 42",
            transaction_type="withdraw", amount=5000,
            queue_position=3, issued_at="2026-08-21T10:15:35Z",
        )
        assert e.event == "new_queue_entry"
        assert e.customer_display_name == "Token 42"

    def test_queue_called_discriminator(self):
        e = QueueCalledEvent(token_id="tok", teller_id="t_02")
        assert e.event == "queue_called"
        assert e.teller_id == "t_02"

    def test_transaction_completed_discriminator(self):
        e = TransactionCompletedEvent(token_id="tok")
        assert e.event == "transaction_completed"

    def test_token_expired_discriminator(self):
        e = TokenExpiredEvent(token_id="tok")
        assert e.event == "token_expired"

    def test_new_queue_entry_field_names(self):
        fields = set(NewQueueEntryEvent.model_fields.keys())
        for expected in ("event", "token_id", "customer_display_name",
                         "transaction_type", "amount", "queue_position", "issued_at"):
            assert expected in fields, f"Missing field in NewQueueEntryEvent: {expected}"

    def test_queue_called_field_names(self):
        fields = set(QueueCalledEvent.model_fields.keys())
        assert "event" in fields
        assert "token_id" in fields
        assert "teller_id" in fields

    def test_token_number_display_format(self):
        """customer_display_name must be 'Token N' — not a random or UUID-based string."""
        e = NewQueueEntryEvent(
            token_id="tok", customer_display_name="Token 7",
            transaction_type="deposit", queue_position=1,
            issued_at="2026-08-21T10:00:00Z",
        )
        assert e.customer_display_name.startswith("Token ")
        token_number = e.customer_display_name.split(" ")[1]
        assert token_number.isdigit(), "Token number must be a plain integer"
