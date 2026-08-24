"""
Mock Security Server — runs on port 8001.
Simulates the Security module's /sign endpoint.
Signs tokens with a deterministic fake HMAC-SHA256 so the full
Backend state machine can be exercised without the real Security module.

Usage:
    python mocks/mock_security_server.py
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Mock Security Server", version="0.1.0-mock")

# Mock signing key — never used outside this mock
_MOCK_SECRET = b"mock-secret-key-DO-NOT-USE-IN-PROD"


@app.post("/sign")
async def sign_token(body: dict):
    """
    Receives a SecuritySignRequest, produces a signed token.
    Mirrors the exact Security → Backend response contract (v0.1).
    """
    token_id = str(uuid.uuid4())
    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=10)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build the payload that would be embedded in the QR code
    qr_data = {
        "token_id": token_id,
        "session_id": body.get("session_id"),
        "customer_id": body.get("customer_id"),
        "transaction_type": body.get("transaction_type"),
        "amount": body.get("amount"),
        "expires_at": expires_at,
    }
    payload_bytes = json.dumps(qr_data, sort_keys=True).encode()
    import base64
    qr_payload = base64.b64encode(payload_bytes).decode()

    # HMAC-SHA256 signature
    hmac_sig = hmac.new(_MOCK_SECRET, payload_bytes, hashlib.sha256).hexdigest()

    print(
        f"  [mock-security] Signed token_id={token_id} "
        f"for session={body.get('session_id')}"
    )

    return {
        "status": "ok",
        "token_id": token_id,
        "qr_payload": qr_payload,
        "hmac_signature": hmac_sig,
        "expires_at": expires_at,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-security"}


if __name__ == "__main__":
    print("🔐 Mock Security Server starting on http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")
