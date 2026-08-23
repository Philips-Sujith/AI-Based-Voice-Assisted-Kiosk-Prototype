from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any


def build_token_data(
    request_values: dict[str, Any], token_id: str, expires_at: datetime
) -> bytes:
    token_data = {
        **request_values,
        "token_id": token_id,
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
    }
    return json.dumps(
        token_data,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def encode_qr_payload(token_data: bytes) -> str:
    return base64.b64encode(token_data).decode("ascii")
