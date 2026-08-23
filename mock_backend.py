from __future__ import annotations

import json
import urllib.request

from config import service_port

SAMPLE_REQUEST = {
    "session_id": "00000000-0000-0000-0000-000000000001",
    "customer_id": "acc_00981234",
    "transaction_type": "withdraw",
    "amount": 5000,
    "timestamp": "2026-08-21T10:15:30Z",
}


def send_sample_request(base_url: str | None = None) -> None:
    target_url = base_url or f"http://127.0.0.1:{service_port()}"
    body = json.dumps(SAMPLE_REQUEST).encode("utf-8")
    request = urllib.request.Request(
        f"{target_url}/sign",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.reason}")


if __name__ == "__main__":
    send_sample_request()
