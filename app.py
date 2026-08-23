from __future__ import annotations

import json
import base64
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from config import key_file, qr_output_directory, service_port, session_directory
from crypto import KeyConfigurationError, load_signing_key
from qr_generator import generate_qr
from session_store import SessionStore, SessionStoreError
from token_service import ExpiredTokenError, TokenService
from validation import RequestValidationError, validate_request


class SecurityHandler(BaseHTTPRequestHandler):
    token_service: TokenService
    qr_output_dir = qr_output_directory()

    def do_POST(self) -> None:
        if self.path == "/qr/generate":
            self._generate_random_qr()
            return
        if self.path != "/sign":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0 or length > 64 * 1024:
                raise RequestValidationError("invalid request size")
            data: Any = json.loads(self.rfile.read(length))
            request = validate_request(data)
            response = self.token_service.sign(request)
        except (json.JSONDecodeError, RequestValidationError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except ExpiredTokenError as exc:
            self.send_error(HTTPStatus.GONE, str(exc))
            return
        self._send_json(HTTPStatus.OK, response.as_dict())

    def _generate_random_qr(self) -> None:
        try:
            request_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "invalid request size")
            return
        if request_length != 0:
            self.send_error(HTTPStatus.BAD_REQUEST, "request body must be empty")
            return
        try:
            output_path, _ = generate_qr(self.qr_output_dir)
            image_data = base64.b64encode(output_path.read_bytes()).decode("ascii")
            response = {
                "status": "ok",
                "qr_id": output_path.stem,
                "qr_image_base64": image_data,
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        except (OSError, ValueError):
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "unable to generate QR code")
            return
        self._send_json(HTTPStatus.OK, response)

    def _send_json(self, status: HTTPStatus, body: dict[str, str]) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def create_server() -> ThreadingHTTPServer:
    key = load_signing_key(key_file())
    store = SessionStore(session_directory())
    store.purge_expired()
    SecurityHandler.token_service = TokenService(key, store)
    return ThreadingHTTPServer(("127.0.0.1", service_port()), SecurityHandler)


def main() -> None:
    try:
        server = create_server()
    except (KeyConfigurationError, SessionStoreError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
