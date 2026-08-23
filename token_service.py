from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from config import TOKEN_TTL_SECONDS
from crypto import sign_hmac_sha256
from models import SigningRequest, SigningResponse
from qr_payload import build_token_data, encode_qr_payload
from session_store import SessionStore


class ExpiredTokenError(ValueError):
    pass


class TokenService:
    def __init__(self, signing_key: bytes, session_store: SessionStore) -> None:
        self._signing_key = signing_key
        self._session_store = session_store

    def sign(self, request: SigningRequest, now: datetime | None = None) -> SigningResponse:
        generation_time = now or datetime.now(timezone.utc)
        expires_at = generation_time + timedelta(seconds=TOKEN_TTL_SECONDS)

        token_id = str(uuid4())
        token_data = build_token_data(request.token_values(), token_id, expires_at)
        qr_payload = encode_qr_payload(token_data)
        signature = sign_hmac_sha256(self._signing_key, token_data)
        self._session_store.put(
            token_id,
            {"expires_epoch": expires_at.timestamp(), "token_data": token_data.decode("utf-8")},
        )
        return SigningResponse(
            status="ok",
            token_id=token_id,
            qr_payload=qr_payload,
            hmac_signature=signature,
            expires_at=expires_at.isoformat().replace("+00:00", "Z"),
        )

    def consume(self, token_id: str) -> dict[str, object]:
        record = self._session_store.consume(token_id, now=time.time())
        if record is None:
            raise ExpiredTokenError("token is missing or expired")
        return record
