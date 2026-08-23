# Security QR Service

This project contains two separate capabilities:

1. A standalone random QR generator that creates scannable PNG files.
2. A security service that signs fixed backend requests and returns the existing fixed API response.

The random QR generator is not connected to security tokens or `qr_payload`.

## Installation

The standalone generator can run on Windows, Linux, or WSL2 with Python 3.11+.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Random QR generator

Each payload contains 128 bits by default from `secrets.token_bytes()` and is encoded as URL-safe Base64 text before QR encoding. Each output receives a unique `random_qr_<uuid>.png` filename. Existing files are never silently overwritten. The CLI prints generated paths only, not complete payload secrets. Use `--payload-bytes` to request more entropy.

By default, files are written to `qr_output/` relative to the current directory.

```bash
python qr_generator.py --output-dir qr_output --count 2 --payload-bytes 16
```

QR rendering options are also configurable. The default error correction is `H` for stronger scan recovery:

```bash
python qr_generator.py --output-dir qr_output --count 3 --box-size 8 --border 4 --error-correction H
```

The generated PNGs are independent from the security service and contain only their own random text payload.

The same HTTP service also exposes `POST /qr/generate` for clients that need a random QR PNG. The endpoint reuses `qr_generator.py`, writes a new uniquely named PNG under `SECURITY_SVC_QR_OUTPUT_DIR` (default `qr_output`), and returns:

```json
{
	"status": "ok",
	"qr_id": "random_qr_<uuid>",
	"qr_image_base64": "<base64 PNG>",
	"generated_at": "<ISO-8601 UTC timestamp>"
}
```

The random QR endpoint is independent of `/sign`, `TokenService`, and the security service's `qr_payload`. It does not log the random payload or expose signing-key material.

## Security service

The signing service is intended for Linux or WSL2 because session records require a real Linux tmpfs mount. It exposes:

```text
POST http://127.0.0.1:8105/sign
```

`SECURITY_SVC_PORT` controls the port and defaults to `8105`. The service accepts exactly the fixed request fields and returns exactly `status`, `token_id`, `qr_payload`, `hmac_signature`, and `expires_at`.

`qr_payload` is Base64-encoded canonical UTF-8 JSON token data. It is not a PNG. HMAC-SHA256 is calculated over the canonical token data using PyCryptodome.

Tokens expire exactly 30 minutes, or 1800 seconds, after server-side token generation time:

```text
generation_time = current server UTC time
expires_at = generation_time + 1800 seconds
```

The incoming request timestamp remains transaction data and does not control token lifetime.

Configure a production signing key with `SECURITY_SVC_KEY_FILE`, pointing to a protected service-readable key file. For development only, `SECURITY_SVC_KEY_B64` may provide a Base64 key of at least 32 bytes. Never commit either secret.

Example Linux/WSL2 setup:

```bash
sudo mkdir -p /run/security-qr-service/sessions
sudo mount -t tmpfs -o size=16M,mode=0700 tmpfs /run/security-qr-service
export SECURITY_SVC_KEY_B64="<development-only-base64-key>"
python app.py
```

Session data is refused unless the configured directory is on Linux tmpfs. Consumed records are deleted immediately; expired records are removed during startup purge. No session data is written to the repository or persistent disk by the service design.

## Mock Backend

With the security service running:

```bash
python mock_backend.py
```

The mock sends the exact fixed sample request to the service and reads `SECURITY_SVC_PORT` through the shared configuration. It never receives the signing key. The supplied sample timestamp is historical and is expected to be rejected as expired.

## Tests

Run the complete suite after Python and dependencies are available:

```bash
pytest -q
```

The random QR tests generate PNGs, verify PNG structure, decode them with OpenCV, and confirm decoded payload equality for 100 independent codes, uniqueness, configurable rendering, and no-overwrite behavior. Security tests cover validation, HMAC integrity, token consumption, exact expiry, 30-minute lifetime, and response schema. tmpfs-specific tests are skipped outside Linux.

Random QR payloads are not authentication tokens and are not signed by the security service. Do not use this standalone generator for banking authorization, identity, or transaction approval without a separate authenticated protocol.
