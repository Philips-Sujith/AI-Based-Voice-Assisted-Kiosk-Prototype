"""
Mock Biometrics Sender — sends a fake auth result to the backend.

Usage:
    python mocks/mock_biometrics.py --session <session_id> --status pass
    python mocks/mock_biometrics.py --session <session_id> --status fail
    python mocks/mock_biometrics.py --session <session_id> --status pass --confidence 0.72
"""
import argparse
import json

import httpx

BACKEND_URL = "http://localhost:8000"


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Biometrics sender")
    parser.add_argument("--session", required=True, help="session_id to authenticate")
    parser.add_argument(
        "--status", default="pass", choices=["pass", "fail", "pending"],
        help="auth_status to report"
    )
    parser.add_argument("--customer-id", default="acc_00981234",
                        help="customer_id (only meaningful when status=pass)")
    parser.add_argument("--confidence", type=float, default=0.94,
                        help="Face auth confidence score (0.0 – 1.0)")
    parser.add_argument("--liveness", type=bool, default=True,
                        help="Whether liveness check passed")
    args = parser.parse_args()

    payload = {
        "session_id": args.session,
        "status": "ok",
        "auth_status": args.status,
        # Currently only "face" — fingerprint will be added later with no contract change
        "methods_used": ["face"],
        "confidence_scores": {"face": args.confidence},
        "liveness_passed": args.liveness,
        "customer_id": args.customer_id,
    }

    print(f"\n→ POST {BACKEND_URL}/api/v1/biometrics")
    print(f"  payload: {json.dumps(payload, indent=4)}\n")

    resp = httpx.post(f"{BACKEND_URL}/api/v1/biometrics", json=payload)
    print(f"← Response [{resp.status_code}]:")
    print(json.dumps(resp.json(), indent=4))


if __name__ == "__main__":
    main()
