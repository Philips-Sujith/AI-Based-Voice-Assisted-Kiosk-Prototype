# Face Authentication (kiosk biometrics adapter)

Face is the only biometric. It both **identifies the account** (1:N ArcFace match against `face_embeddings`) and **confirms a live person** (MediaPipe blink + MiniFASNet anti-spoof).

Fingerprint / WebAuthn are not used.

## Backend payload (fixed)

`POST /face-auth/verify-event` returns this shape (and the verify page forwards the same seven fields to `POST /mock-backend/event`):

```json
{
  "session_id": "uuid",
  "status": "ok",
  "auth_status": "pass | fail | pending",
  "methods_used": ["face"],
  "confidence_scores": { "face": 0.94 },
  "liveness_passed": true,
  "customer_id": "acc_00981234 or null for non-account-holders"
}
```

## What runs on verify

1. **Liveness** — MediaPipe Face Mesh eye-aspect-ratio over ~2.5 seconds of frames. A real blink (open → closed → open) is required. A still photo will not pass.
2. **Anti-spoof** — **Silent-Face MiniFASNet** (MiniFASNetV2 + MiniFASNetV1SE ONNX, softmax fused). Models download into `models/` on first run. If download fails, Laplacian variance + FFT moiré heuristics are used instead. Check `GET /face-auth/capabilities` → `anti_spoof.backend`.
3. **Identify** — ArcFace embedding (InsightFace `buffalo_l`) compared with cosine similarity to every row in `face_embeddings`. Default threshold **0.6** (`FACE_MATCH_THRESHOLD`). No match → `auth_status: fail`, `customer_id: null`.

## Seed data

SQLite table `fake_accounts` (6 demo rows such as `acc_00981234` / Test Customer 1). Enrollments go to `face_embeddings`.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set `FACE_AUTH_BASE_URL` to your public HTTPS origin (ngrok). Camera access needs a secure context on a real phone.

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Enroll: `/face-auth/enroll`
- Verify: `/face-auth/verify`
- Health: `/health`
- Mock Backend: `POST /mock-backend/event`

First InsightFace run downloads `buffalo_l`. First anti-spoof run downloads MiniFASNet ONNX weights.
