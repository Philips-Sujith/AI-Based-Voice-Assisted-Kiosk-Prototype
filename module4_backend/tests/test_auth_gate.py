"""
Auth gate tests — validates the security bypass prevention logic.
"""
import pytest

from app.services.auth_gate import (
    AUTH_REQUIRED_INTENTS,
    check_requires_auth_mismatch,
    compute_backend_auth_needed,
)


class TestComputeBackendAuthNeeded:
    def test_withdraw_requires_auth(self):
        assert compute_backend_auth_needed("withdraw") is True

    def test_deposit_requires_auth(self):
        assert compute_backend_auth_needed("deposit") is True

    def test_send_money_no_auth(self):
        assert compute_backend_auth_needed("send_money") is False

    def test_open_account_no_auth(self):
        assert compute_backend_auth_needed("open_account") is False

    def test_unknown_intent_no_auth(self):
        assert compute_backend_auth_needed("unknown") is False

    def test_empty_intent_no_auth(self):
        assert compute_backend_auth_needed("") is False


class TestMismatchDetection:
    def test_no_mismatch_withdraw_true(self):
        assert check_requires_auth_mismatch("withdraw", True) is False

    def test_no_mismatch_deposit_true(self):
        assert check_requires_auth_mismatch("deposit", True) is False

    def test_no_mismatch_send_money_false(self):
        assert check_requires_auth_mismatch("send_money", False) is False

    def test_no_mismatch_open_account_false(self):
        assert check_requires_auth_mismatch("open_account", False) is False

    def test_bypass_attempt_withdraw_false(self):
        """Critical: withdraw with requires_auth=False is a bypass attempt."""
        assert check_requires_auth_mismatch("withdraw", False) is True

    def test_bypass_attempt_deposit_false(self):
        """Critical: deposit with requires_auth=False is a bypass attempt."""
        assert check_requires_auth_mismatch("deposit", False) is True

    def test_unusual_send_money_true(self):
        """Not a security risk but still a mismatch worth flagging."""
        assert check_requires_auth_mismatch("send_money", True) is True


class TestAuthRequiredIntents:
    def test_is_frozenset(self):
        assert isinstance(AUTH_REQUIRED_INTENTS, frozenset)

    def test_exact_contents(self):
        assert AUTH_REQUIRED_INTENTS == frozenset({"deposit", "withdraw"})

    def test_is_immutable(self):
        with pytest.raises((AttributeError, TypeError)):
            AUTH_REQUIRED_INTENTS.add("send_money")  # type: ignore[attr-defined]
