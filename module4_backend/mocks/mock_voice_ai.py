"""
Mock Voice AI Sender — drives the backend with fake intent payloads.

Usage:
    python mocks/mock_voice_ai.py --intent withdraw --amount 5000
    python mocks/mock_voice_ai.py --intent send_money --amount 2000
    python mocks/mock_voice_ai.py --intent open_account
    python mocks/mock_voice_ai.py --intent deposit --amount 1000 --confidence 0.5
    python mocks/mock_voice_ai.py --intent withdraw --amount 5000 --force-no-auth
        (security bypass test — backend must reject and enforce auth anyway)
"""
import argparse
import json
import uuid

import httpx

BACKEND_URL = "http://localhost:8000"

# Default entity shapes per intent (matching contract v0.1)
_ENTITY_DEFAULTS = {
    "withdraw":     {"amount": 5000,  "account_number": "XXXX1234"},
    "deposit":      {"amount": 1000,  "account_number": "XXXX1234"},
    "send_money":   {"amount": 2000,  "recipient_account_number": "9876543210"},
    "open_account": {"name": "Test User", "dob": "1990-01-15",
                     "address": "123 Main St, Chennai", "phone": "9876543210"},
}

# Correct requires_auth per the contract — used unless --force-no-auth is set
_CORRECT_REQUIRES_AUTH = {
    "withdraw": True,
    "deposit":  True,
    "send_money":   False,
    "open_account": False,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Voice AI sender")
    parser.add_argument(
        "--intent", default="withdraw",
        choices=list(_ENTITY_DEFAULTS), help="Intent to send"
    )
    parser.add_argument("--amount", type=int, default=None,
                        help="Override amount in entities")
    parser.add_argument("--session-id", default=None,
                        help="Reuse an existing session_id")
    parser.add_argument("--confidence", type=float, default=0.91,
                        help="Confidence score (0.0 – 1.0)")
    parser.add_argument("--language", default="ta",
                        choices=["ta", "en", "tanglish"])
    parser.add_argument(
        "--force-no-auth", action="store_true",
        help="Send requires_auth=False even for auth-required intents (security test)",
    )
    args = parser.parse_args()

    session_id = args.session_id or str(uuid.uuid4())
    entities = dict(_ENTITY_DEFAULTS.get(args.intent, {}))
    if args.amount is not None and "amount" in entities:
        entities["amount"] = args.amount

    requires_auth = _CORRECT_REQUIRES_AUTH[args.intent]
    if args.force_no_auth:
        requires_auth = False
        print(
            f"\n⚠️  SECURITY TEST: forcing requires_auth=False "
            f"for intent='{args.intent}'. Backend must enforce auth anyway."
        )

    payload = {
        "session_id": session_id,
        "status": "ok",
        "language": args.language,
        "intent": args.intent,
        "requires_auth": requires_auth,
        "entities": entities,
        "confidence": args.confidence,
        "raw_transcript": f"[mock transcript for intent={args.intent}]",
    }

    print(f"\n→ POST {BACKEND_URL}/api/v1/voice-intent")
    print(f"  session_id : {session_id}")
    print(f"  payload    : {json.dumps(payload, indent=4)}\n")

    resp = httpx.post(f"{BACKEND_URL}/api/v1/voice-intent", json=payload)
    print(f"← Response [{resp.status_code}]:")
    print(json.dumps(resp.json(), indent=4))
    print(f"\n💡 session_id for next step: {session_id}")


if __name__ == "__main__":
    main()
