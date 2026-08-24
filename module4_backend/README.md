# Banking Kiosk Backend — Module 4

Orchestration hub for the voice-assisted banking kiosk.  
Receives from **Voice AI** and **Biometrics**, sends to **Security**, pushes real-time events to the **Staff Portal & Hardware dashboards**.

---

## Stack

| Component | Library |
|---|---|
| API framework | FastAPI (async ASGI) |
| State machine | `transitions` (per-session FSM) |
| Real-time push | Redis Pub/Sub → WebSocket |
| Validation | Pydantic v2 |
| HTTP client | `httpx` (async) |

---

## Quick Start

### 1. Prerequisites

- Python ≥ 3.11
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Redis)

### 2. Install

```bash
cd module4_backend
cp .env.example .env
python -m pip install -r requirements.txt
```

### 3. Start Redis

```bash
docker-compose up -d
```

### 4. Run tests (no Redis needed)

```bash
python -m pytest tests/ -v
```

### 5. Run the full mock stack

Open **five terminals** in `module4_backend/`:

```bash
# T1 — Mock Security server (port 8001)
python mocks/mock_security_server.py

# T2 — Backend (port 8000)
uvicorn app.main:app --reload --port 8000

# T3 — Staff Portal dashboard listener (WebSocket)
python mocks/mock_dashboard_client.py
```

Then run scenarios from a fourth terminal:

```bash
# Scenario A: auth-required withdraw flow (full happy path)
python mocks/mock_voice_ai.py --intent withdraw --amount 5000
# Note the session_id printed, then:
python mocks/mock_biometrics.py --session <SESSION_ID> --status pass
# Then confirm:
curl -X POST http://localhost:8000/api/v1/session/<SESSION_ID>/confirm \
     -H "Content-Type: application/json" \
     -d '{"session_id": "<SESSION_ID>", "confirmed": true}'

# Scenario B: auth fail → retry → terminal (3 failures)
python mocks/mock_voice_ai.py --intent deposit --amount 1000
python mocks/mock_biometrics.py --session <ID> --status fail   # retry_count → 1
python mocks/mock_biometrics.py --session <ID> --status fail   # retry_count → 2
python mocks/mock_biometrics.py --session <ID> --status fail   # terminal → idle

# Scenario C: non-auth flow, customer rejects
python mocks/mock_voice_ai.py --intent send_money --amount 2000
curl -X POST http://localhost:8000/api/v1/session/<ID>/confirm \
     -d '{"session_id": "<ID>", "confirmed": false}'

# Scenario D: security bypass attempt (backend must enforce auth anyway)
python mocks/mock_voice_ai.py --intent withdraw --amount 5000 --force-no-auth
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/voice-intent` | Receive parsed intent from Voice AI |
| `POST` | `/api/v1/biometrics` | Receive auth result from Biometrics |
| `POST` | `/api/v1/session/{id}/confirm` | Customer verbal confirmation (yes/no) |
| `POST` | `/api/v1/teller/{token_id}/call` | Teller calls customer |
| `POST` | `/api/v1/teller/{token_id}/complete` | Teller marks transaction done |
| `POST` | `/api/v1/teller/{token_id}/expire` | Token timed out (also fired internally) |
| `GET` | `/api/v1/session/{id}/state` | Debug: current FSM state |
| `GET` | `/api/v1/token/{token_id}/verify` | Staff Portal: verify token before acting |
| `WS` | `/ws/dashboard` | Staff Portal WebSocket subscription |
| `GET` | `/health` | Health check |

Interactive docs: **http://localhost:8000/docs**

---

## State Machine

```
IDLE → INTENT_RECEIVED* → AWAITING_AUTH or AWAITING_CONFIRMATION
                                    ↓                      ↓
                             (auth pass/retry)      CONFIRMED → QUEUED
                                    ↓                         ↓          ↓
                              AWAITING_CONF         COMPLETED    EXPIRED
                                                         ↓          ↓
                                                        IDLE       IDLE
```
`*` `INTENT_RECEIVED` is transient — auto-cascades immediately on entry.

---

## Configuration

All values are env-overrideable (see `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | |
| `REDIS_QUEUE_CHANNEL` | `kiosk:queue:events` | FLAG 1 — confirm with team |
| `SECURITY_SERVICE_URL` | `http://localhost:8001` | FLAG 4 — real module URL |
| `CONFIDENCE_THRESHOLD` | `0.7` | FLAG 2 — ratify with Voice AI owner |
| `MAX_AUTH_RETRIES` | `2` | FLAG 6 — 3 total attempts |

---

## Project Structure

```
module4_backend/
├── app/
│   ├── main.py             # FastAPI entry point
│   ├── config.py           # Pydantic settings
│   ├── session_store.py    # In-memory session registry
│   ├── fsm/                # KioskMachine + SessionContext
│   ├── routers/            # One file per endpoint group
│   ├── services/           # auth_gate, security_client, queue_manager, redis_publisher
│   ├── models/             # Pydantic models (contract shapes)
│   └── middleware/         # Global error handler
├── mocks/                  # Mock senders for all 4 neighbouring modules
├── tests/                  # 107 unit tests
├── docker-compose.yml      # Redis
└── requirements.txt
```
