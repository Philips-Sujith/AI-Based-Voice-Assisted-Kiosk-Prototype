"""
Auth Gate — Backend's source of truth for auth requirement.

The mapping intent → auth_required is DETERMINISTIC and owned by Backend.
Voice AI's `requires_auth` flag is INFORMATIONAL ONLY and must NEVER be used
as the auth-gate decision.  Trusting it would allow a manipulated or buggy
payload to bypass Biometrics entirely on a withdraw/deposit intent.
"""
import logging

logger = logging.getLogger(__name__)

# Frozen mapping — only deposit and withdraw require authentication.
# FLAG 2: if new intents are added, update this set as a team decision.
AUTH_REQUIRED_INTENTS: frozenset = frozenset({"deposit", "withdraw"})


def compute_backend_auth_needed(intent: str) -> bool:
    """
    Returns True if the intent requires biometric authentication.
    This is the ONLY authoritative source for auth-gate decisions.
    """
    return intent in AUTH_REQUIRED_INTENTS


def check_requires_auth_mismatch(intent: str, voice_ai_requires_auth: bool) -> bool:
    """
    Compares Voice AI's requires_auth flag against backend's computed value.
    Returns True if there is a mismatch and logs a security warning.
    The caller must use backend's computed value regardless of the result.
    """
    backend_computed = compute_backend_auth_needed(intent)
    if backend_computed != voice_ai_requires_auth:
        logger.warning(
            "SECURITY MISMATCH detected — intent='%s' backend_auth_needed=%s "
            "but Voice AI sent requires_auth=%s. "
            "Enforcing backend value. Investigate Voice AI model or payload tampering.",
            intent,
            backend_computed,
            voice_ai_requires_auth,
        )
        return True
    return False
