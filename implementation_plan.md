# Banking Kiosk — Backend & State Machine (Module 4) — Final Plan v0.3

## Overview

The **orchestration hub** for the voice-assisted banking kiosk. Stack: **Python FastAPI (async ASGI)**, `transitions` (FSM), **Redis Pub/Sub**, WebSockets.

---

## Corrected Architecture Flow

```
Frontend ──audio──► Voice AI ──intent JSON──► Backend
                                                  │
                              ┌───────────────────┤
                              │ (only if deposit  │
                              │  or withdraw)      │
                              ▼                   │
                          Biometrics              │
                              │ auth JSON          │
                              └───────────────────►│
                                                  │
                                                  │──signing request──► Security
                                                  │◄──signed token──────┘
                                                  │
                                                  ▼
                                     Hardware & Staff Portal  (module 6)
                                         one WebSocket connection
                                  new_queue_entry / queue_called /
                              transaction_completed / token_expired
```

---

## Strict Contract Rules

> [!IMPORTANT]
> JSON key names from the module interface contracts are **frozen**. Flag, don't change. All flags are listed at the bottom.

---

## Auth Gate — Security Fix

> [!CAUTION]
> Backend must **never** trust `requires_auth` from Voice AI as its auth-gate decision. A manipulated payload with `requires_auth: false` on a `withdraw` intent must not skip Biometrics.

### Backend-computed auth mapping (source of truth):
```python
AUTH_REQUIRED_INTENTS = {"deposit", "withdraw"}
backend_auth_needed = intent in AUTH_REQUIRED_INTENTS
```

Voice AI's `requires_auth` is **informational only**. If it disagrees with `backend_auth_needed` → log a security warning + emit an internal alert event → enforce Backend's computed value.

---

## Revised State Machine (v0.3 — all four fixes applied)

### States

| State | Meaning |
|---|---|
| `idle` | Kiosk waiting for next customer |
| `intent_received` | **Transient** — entered and immediately exited by an auto-cascade callback (see Fix 2 below) |
| `awaiting_auth` | Waiting for Biometrics result |
| `awaiting_confirmation` | Waiting for customer's verbal reconfirmation of transaction details |
| `confirmed` | Customer confirmed; ready to request signing from Security |
| `queued` | Signed token issued, customer in teller queue |
| `completed` | Teller marked transaction done (customer was served) |
| `expired` | Token timed out unclaimed (customer no-show) |
| `error` | Unrecoverable system fault |

> [!NOTE]
> `auth_failed` is **not a named state** — it is the action taken on a failed auth attempt inside `awaiting_auth`. The FSM stays in `awaiting_auth` on retry, or transitions directly to `idle` when retries are exhausted. This avoids a dead-end state that would require its own reset path.

---

### Fix 1 — `retry_count` Increment is an Explicit Transition Action

The `auth_failed_retry` self-loop on `awaiting_auth` carries an explicit `before` action:

```python
# In kiosk_machine.py — transitions definition
Machine(
    ...
    transitions=[
        {
            "trigger": "auth_failed_retry",
            "source":  "awaiting_auth",
            "dest":    "awaiting_auth",       # self-loop
            "conditions": "can_retry_auth",   # retry_count < MAX_AUTH_RETRIES
            "before":  "increment_retry_count"  # ← explicit action, runs first
        },
        {
            "trigger": "auth_failed_terminal",
            "source":  "awaiting_auth",
            "dest":    "idle",
            "conditions": "retries_exhausted",  # retry_count >= MAX_AUTH_RETRIES
            "before":  "notify_auth_failed_terminal"
        },
        ...
    ]
)

# In session_context.py
def increment_retry_count(self):
    self.retry_count += 1          # runs before guard re-evaluation on next attempt

def can_retry_auth(self):
    return self.retry_count < settings.MAX_AUTH_RETRIES

def retries_exhausted(self):
    return self.retry_count >= settings.MAX_AUTH_RETRIES
```

Execution order on a failed biometrics result:
1. Router calls `machine.trigger("auth_failed_retry")` or `"auth_failed_terminal"`
2. The biometrics router evaluates `can_retry_auth()` **before** calling the trigger, picks the right one
3. If retry: `increment_retry_count()` fires → `retry_count` goes from N to N+1 → FSM stays in `awaiting_auth`
4. If terminal: `notify_auth_failed_terminal()` fires → session clears → FSM → `idle`

This makes it impossible for the guard to evaluate stale data.

---

### Fix 2 — `intent_received` is a Transient State (Auto-Cascade on Entry)

`intent_received` is entered and **immediately exited** by an `on_enter_intent_received` callback. No external caller needs to fire a second trigger. The `/api/v1/voice-intent` endpoint returns the **already-advanced** state, not `intent_received`.

```python
# In kiosk_machine.py
def on_enter_intent_received(self):
    """
    Auto-cascade: evaluate backend_auth_needed and immediately fire
    the correct outbound trigger. intent_received is never a resting state.
    """
    if self.context.backend_auth_needed:
        self.trigger("auth_needed")       # → awaiting_auth
    else:
        self.trigger("no_auth_needed")    # → awaiting_confirmation
```

```python
# In voice_intent.py router — what the caller gets back:
async def receive_voice_intent(payload: VoiceIntentPayload):
    session = get_or_create_session(payload.session_id)
    session.machine.trigger("voice_intent_received")
    # By this point, on_enter_intent_received has already fired and
    # the machine is in awaiting_auth or awaiting_confirmation
    return {
        "status": "ok",
        "session_id": payload.session_id,
        "state": session.machine.state   # "awaiting_auth" or "awaiting_confirmation"
    }
```

This eliminates any risk of a session getting stuck in `intent_received` waiting for a call nobody makes.

---

### Fix 3 — `POST /api/v1/session/{id}/confirm` — Request Body Specified

```json
{
  "session_id": "uuid",
  "confirmed": true
}
```

| Field | Type | Values | Meaning |
|---|---|---|---|
| `session_id` | `string` | UUID v4 | Must match the session in `awaiting_confirmation` |
| `confirmed` | `boolean` | `true` / `false` | `true` → fire `customer_confirmed` → `confirmed`; `false` → fire `customer_rejected` → `idle` |

Handler logic:
```python
async def confirm_transaction(session_id: str, body: ConfirmBody):
    session = get_session(session_id)  # 404 if not found
    if session.machine.state != "awaiting_confirmation":
        raise HTTPException(409, "Session not in awaiting_confirmation state")

    if body.confirmed:
        session.machine.trigger("customer_confirmed")
        # FSM → confirmed → auto-calls Security → FSM → queued
        return {"status": "ok", "state": "queued", "token_id": session.context.token_id}
    else:
        session.machine.trigger("customer_rejected")
        return {"status": "ok", "state": "idle"}
```

Response on confirm (`confirmed: true`):
```json
{ "status": "ok", "state": "queued", "token_id": "uuid", "queue_position": 3 }
```
Response on reject (`confirmed: false`):
```json
{ "status": "ok", "state": "idle" }
```

> [!IMPORTANT]
> **Flag 7**: Voice AI owner must call `POST /api/v1/session/{id}/confirm` with this body after parsing the customer's spoken yes/no. This is a new endpoint in Backend's API that Voice AI needs to be aware of.

---

### Fix 4 — `customer_display_name` — Unambiguous for Elderly & Illiterate Customers

The previous `"Guest #7823"` random-suffix format created two problems: it is opaque to customers who may hear it spoken aloud, and the random suffix has no relationship to anything the customer already knows about their visit.

**New rule**: `customer_display_name` uses a **sequential, session-scoped token number** — the same number printed on the customer's kiosk receipt and read aloud by the Voice AI at the end of the session. This number is what the teller calls out.

| Flow | Format | Example | Spoken by Voice AI |
|---|---|---|---|
| Auth flow (deposit/withdraw) | `"Token [N]"` | `"Token 42"` | *"Your token number is forty-two"* |
| Non-auth flow (open_account/send_money) | `"Token [N]"` | `"Token 43"` | *"Your token number is forty-three"* |

`N` is a **single global daily counter** (`queue_manager.next_token_number()`) that increments for every new session that reaches the `queued` state, regardless of auth flow. It resets at the start of each business day.

No `customer_id`, no random suffix, no UUID fragment — just a simple sequential number that is meaningful, speakable, and printable.

> [!IMPORTANT]
> **Flag 5 (updated)**: Staff Portal owner to confirm: does the teller dashboard need any additional identifying information beyond the token number + transaction type + amount? If the teller needs to see a customer name for auth flows (from bank's dataset), Backend can include it as an optional `customer_name` field alongside `customer_display_name` — but `customer_display_name` stays as `"Token N"` in all cases.

---

### Complete Transition Table (final)

| Trigger | From | To | Guard | Action |
|---|---|---|---|---|
| `voice_intent_received` | `idle` | `intent_received` | confidence ≥ 0.7 | store intent + entities + compute `backend_auth_needed` |
| `low_confidence` | `idle` | `idle` | confidence < 0.7 | signal Voice AI to re-prompt customer |
| `auth_needed` *(auto)* | `intent_received` | `awaiting_auth` | `backend_auth_needed == True` | fired by `on_enter_intent_received` |
| `no_auth_needed` *(auto)* | `intent_received` | `awaiting_confirmation` | `backend_auth_needed == False` | fired by `on_enter_intent_received` |
| `auth_passed` | `awaiting_auth` | `awaiting_confirmation` | `auth_status == "pass"` | store `customer_id`, `confidence_scores` |
| `auth_failed_retry` | `awaiting_auth` | `awaiting_auth` | `retry_count < MAX_AUTH_RETRIES` | **`retry_count += 1`** ← explicit increment |
| `auth_failed_terminal` | `awaiting_auth` | `idle` | `retry_count >= MAX_AUTH_RETRIES` | clear session, notify teller screen |
| `customer_confirmed` | `awaiting_confirmation` | `confirmed` | — | immediately auto-call Security (sign request) |
| `customer_rejected` | `awaiting_confirmation` | `idle` | — | clear session |
| `token_signed` | `confirmed` | `queued` | Security returns `status == "ok"` | assign `token_number`, publish `new_queue_entry` |
| `transaction_completed` | `queued` | `completed` | — | cancel expiry task, publish `transaction_completed` |
| `token_expired` | `queued` | `expired` | expiry task fires at `expires_at` | publish `token_expired` |
| `session_reset` | `completed` | `idle` | — | clear session context |
| `session_reset` | `expired` | `idle` | — | clear session context |
| `error_occurred` | `*` | `error` | — | log + publish error alert |
| `error_reset` | `error` | `idle` | — | operator/timeout resets kiosk |

---

### Full FSM Flow (v0.3)

```
IDLE
 │
 │ [voice_intent_received — confidence ≥ 0.7]
 ▼
INTENT_RECEIVED  ← transient; on_enter immediately fires auto-cascade
 │
 │ Backend computes backend_auth_needed from intent (not from requires_auth flag)
 │
 ├──[auth_needed, auto]─────────────────────────────────────────────────────────┐
 │                                                                               ▼
 │                                                                       AWAITING_AUTH
 │                                                                               │
 │                                                           ┌──[auth_passed]────┘
 │                                                           │
 │                                     [auth_status ≠ "pass"]
 │                                                           │
 │                                              retry_count < MAX_AUTH_RETRIES?
 │                                             ┌──Yes──┘              └──No──┐
 │                                   retry_count += 1                        ▼
 │                                             │                            IDLE
 │                                             ▼                     (session cleared,
 │                                       AWAITING_AUTH                next customer)
 │                                       (retry attempt)
 │                                             │
 │                                     [auth_passed eventually]
 │                                             │
 │                                             ▼
 └──[no_auth_needed, auto]────────► AWAITING_CONFIRMATION ◄─────────────────────┘
                                               │
                         Voice AI re-prompts customer with transaction summary:
                              "Confirm: [intent] ₹[amount] — say yes or no"
                                               │
                              ┌──[customer_confirmed]──┐  ┌──[customer_rejected]──┐
                              │                        │  │                       │
                              ▼                        │  ▼                       │
                          CONFIRMED                    │  IDLE                    │
                              │                        │  (restart for            │
                   Backend → Security (sign)           │   next customer)         │
                   Security → Backend (token)          └──────────────────────────┘
                   Backend assigns Token N
                   Backend → Staff Portal WS
                              │
                           QUEUED
                    [expiry background task running]
                              │
               ┌──────────────┴──────────────┐
               │                             │
   [transaction_completed]          [token_expired — bg task fires]
               │                             │
           COMPLETED                     EXPIRED
               │                             │
               └────────────┬────────────────┘
                            │[session_reset]
                           IDLE
                      (next customer)
```

---

## Project Layout

```
module4_backend/
├── app/
│   ├── main.py                   # FastAPI app, lifespan, router registration
│   ├── config.py                 # Pydantic BaseSettings — CONFIDENCE_THRESHOLD,
│   │                             #   MAX_AUTH_RETRIES, SECURITY_SERVICE_URL, REDIS_URL
│   ├── session_store.py          # In-memory dict + Redis TTL for active sessions
│   │
│   ├── fsm/
│   │   ├── kiosk_machine.py      # transitions FSM — states, triggers, guards,
│   │   │                         #   on_enter callbacks, increment_retry_count action
│   │   └── session_context.py    # Per-session data: intent, entities, auth scores,
│   │                             #   retry_count, backend_auth_needed, token_id,
│   │                             #   token_number, queue_position, customer_id
│   │
│   ├── routers/
│   │   ├── voice_intent.py       # POST /api/v1/voice-intent
│   │   ├── biometrics.py         # POST /api/v1/biometrics
│   │   ├── confirmation.py       # POST /api/v1/session/{id}/confirm
│   │   │                         #   body: { "session_id": "uuid", "confirmed": bool }
│   │   ├── teller.py             # POST /api/v1/teller/{token_id}/call|complete|expire
│   │   ├── session.py            # GET  /api/v1/session/{id}/state
│   │   ├── token_verify.py       # GET  /api/v1/token/{token_id}/verify
│   │   └── ws_dashboard.py       # WS   /ws/dashboard
│   │
│   ├── services/
│   │   ├── auth_gate.py          # AUTH_REQUIRED_INTENTS set, mismatch detection
│   │   ├── security_client.py    # Async HTTP → Security module
│   │   ├── queue_manager.py      # Sequential token counter, expiry task launcher
│   │   └── redis_publisher.py    # Publish to kiosk:queue:events
│   │
│   ├── models/
│   │   ├── voice_intent.py       # Pydantic — Voice AI payload
│   │   ├── biometrics.py         # Pydantic — Biometrics payload
│   │   ├── security.py           # Pydantic — Security request + response
│   │   ├── confirmation.py       # Pydantic — { session_id, confirmed: bool }
│   │   └── events.py             # Pydantic — all 4 WS event shapes
│   │
│   └── middleware/
│       └── error_handler.py      # Global exc → { "status": "error", ... }
│
├── mocks/
│   ├── mock_voice_ai.py          # CLI: send fake intent payload
│   ├── mock_biometrics.py        # CLI: send fake auth result
│   ├── mock_security_server.py   # Fake Security HTTP endpoint
│   └── mock_dashboard_client.py  # WS listener — prints Staff Portal events
│
├── tests/
│   ├── test_fsm.py               # All FSM paths, auto-cascade, retry increment
│   ├── test_auth_gate.py         # Mismatch detection, bypass prevention
│   ├── test_voice_intent.py      # Confidence gate, returns advanced state
│   ├── test_biometrics.py        # Retry increment, terminal transition
│   ├── test_confirmation.py      # confirm/reject, state guards
│   ├── test_queue.py             # Token number sequence, completed vs expired
│   └── test_contracts.py         # No key drift — validates JSON shapes
│
├── requirements.txt
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## REST API Endpoints

| Method | Path | Called by | Returns |
|---|---|---|---|
| `POST` | `/api/v1/voice-intent` | Voice AI | `{ status, session_id, state }` — state is `awaiting_auth` or `awaiting_confirmation` (never `intent_received`) |
| `POST` | `/api/v1/biometrics` | Biometrics | `{ status, session_id, state, retry_count? }` |
| `POST` | `/api/v1/session/{id}/confirm` | Voice AI | `{ status, state, token_id?, queue_position? }` |
| `POST` | `/api/v1/teller/{token_id}/call` | Staff Portal | `{ status }` |
| `POST` | `/api/v1/teller/{token_id}/complete` | Staff Portal | `{ status }` |
| `POST` | `/api/v1/teller/{token_id}/expire` | bg task | `{ status }` |
| `GET` | `/api/v1/session/{id}/state` | Debug / Frontend | current FSM state + safe context |
| `GET` | `/api/v1/token/{token_id}/verify` | Staff Portal | transaction details + expiry check |
| `WS` | `/ws/dashboard` | Staff Portal | subscribe to `kiosk:queue:events` |

---

## WebSocket Events (one module, one connection)

```json
{ "event": "new_queue_entry",        "token_id": "uuid",
  "customer_display_name": "Token 42",
  "transaction_type": "withdraw",    "amount": 5000,
  "queue_position": 3,               "issued_at": "2026-08-21T10:15:35Z" }

{ "event": "queue_called",           "token_id": "uuid", "teller_id": "t_02" }
{ "event": "transaction_completed",  "token_id": "uuid" }
{ "event": "token_expired",          "token_id": "uuid" }
```

Redis channel: `kiosk:queue:events`

---

## Flags for Team Review

> [!IMPORTANT]
> **Flag 1 — Redis channel naming**: `kiosk:queue:events` (global dashboard events), `kiosk:session:{session_id}:events` (per-session). Staff Portal and Voice AI owners must confirm subscription targets.

> [!IMPORTANT]
> **Flag 2 — Confidence threshold = 0.7**: Env-overrideable. Must be ratified jointly with Voice AI owner.

> [!IMPORTANT]
> **Flag 3 — `open_account` entity fields**: Accepted as a passthrough dict until Voice AI owner finalises field list.

> [!IMPORTANT]
> **Flag 4 — Security module URL**: `SECURITY_SERVICE_URL` env var. No code changes when real module is built.

> [!IMPORTANT]
> **Flag 5 — `customer_display_name`**: Fixed as `"Token N"` (sequential). If teller dashboard also needs a customer name for auth flows, Backend can add optional `customer_name` field — team decision, not a unilateral one.

> [!IMPORTANT]
> **Flag 6 — MAX_AUTH_RETRIES = 2** (3 total attempts): Team — Biometrics owner + product — must ratify.

> [!IMPORTANT]
> **Flag 7 — `/api/v1/session/{id}/confirm` caller**: Voice AI owner must call this endpoint with `{ "session_id": "...", "confirmed": bool }` after parsing the customer's spoken yes/no. New contract addition Voice AI needs to absorb.

---

## Verification Plan

### Automated Tests
```bash
pip install -r requirements.txt
pytest tests/ -v --tb=short
```

### End-to-End Mock Run
```bash
# Terminal 1 — Redis
docker-compose up redis

# Terminal 2 — mock Security server
python mocks/mock_security_server.py

# Terminal 3 — backend
uvicorn app.main:app --reload --port 8000

# Terminal 4 — Staff Portal WS listener
python mocks/mock_dashboard_client.py

# Scenario A: full auth flow, withdraw, confirm
python mocks/mock_voice_ai.py --intent withdraw --amount 5000
python mocks/mock_biometrics.py --session <id> --status pass
curl -X POST http://localhost:8000/api/v1/session/<id>/confirm \
     -H "Content-Type: application/json" \
     -d '{"session_id": "<id>", "confirmed": true}'

# Scenario B: auth fail → retry → terminal (3 fails)
python mocks/mock_voice_ai.py --intent deposit --amount 1000
python mocks/mock_biometrics.py --session <id> --status fail  # retry_count → 1
python mocks/mock_biometrics.py --session <id> --status fail  # retry_count → 2
python mocks/mock_biometrics.py --session <id> --status fail  # terminal → idle

# Scenario C: non-auth flow, customer rejects
python mocks/mock_voice_ai.py --intent send_money --amount 2000
curl -X POST http://localhost:8000/api/v1/session/<id>/confirm \
     -d '{"session_id": "<id>", "confirmed": false}'  # → idle

# Scenario D: token expiry (completed vs expired distinction)
python mocks/mock_voice_ai.py --intent withdraw --amount 3000
python mocks/mock_biometrics.py --session <id> --status pass
curl ... confirm true   # → queued, expiry task running
# wait for expires_at → token_expired event on dashboard WS

# Scenario E: security bypass attempt
python mocks/mock_voice_ai.py --intent withdraw --amount 5000 --force-no-auth
# Backend logs security mismatch warning, enforces auth anyway
```
