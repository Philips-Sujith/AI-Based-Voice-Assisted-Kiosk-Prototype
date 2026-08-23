from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PORT = 8105
DEFAULT_SESSION_DIR = Path("/run/security-qr-service/sessions")
DEFAULT_QR_OUTPUT_DIR = Path("qr_output")
TOKEN_TTL_SECONDS = 1800


def service_port() -> int:
    raw_port = os.environ.get("SECURITY_SVC_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("SECURITY_SVC_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("SECURITY_SVC_PORT must be between 1 and 65535")
    return port


def session_directory() -> Path:
    return Path(os.environ.get("SECURITY_SVC_SESSION_DIR", str(DEFAULT_SESSION_DIR)))


def qr_output_directory() -> Path:
    return Path(os.environ.get("SECURITY_SVC_QR_OUTPUT_DIR", str(DEFAULT_QR_OUTPUT_DIR)))


def key_file() -> Path | None:
    configured = os.environ.get("SECURITY_SVC_KEY_FILE")
    return Path(configured) if configured else None
