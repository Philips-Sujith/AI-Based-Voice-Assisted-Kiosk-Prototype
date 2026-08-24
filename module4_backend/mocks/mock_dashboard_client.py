"""
Mock Staff Portal Dashboard Client — WebSocket listener.
Connects to ws://localhost:8000/ws/dashboard and pretty-prints
every queue lifecycle event received from the backend.

Usage:
    python mocks/mock_dashboard_client.py
"""
import asyncio
import json

import websockets

WS_URL = "ws://localhost:8000/ws/dashboard"

# ANSI colours for terminal output
_COLOURS = {
    "new_queue_entry":       "\033[92m",   # green  — new customer in queue
    "queue_called":          "\033[94m",   # blue   — teller called a customer
    "transaction_completed": "\033[96m",   # cyan   — served
    "token_expired":         "\033[91m",   # red    — no-show
    "RESET":                 "\033[0m",
}


def _fmt(event: dict) -> str:
    event_type = event.get("event", "unknown")
    colour = _COLOURS.get(event_type, "")
    reset = _COLOURS["RESET"]
    lines = [f"{colour}▶  EVENT: {event_type.upper()}{reset}"]
    for k, v in event.items():
        if k != "event":
            lines.append(f"   {k}: {v}")
    return "\n".join(lines)


async def listen() -> None:
    print(f"🖥️  Staff Portal Dashboard Mock")
    print(f"   Connecting to {WS_URL} …\n")

    async with websockets.connect(WS_URL) as ws:
        print("✅ Connected.  Waiting for queue events …\n")
        async for raw in ws:
            try:
                event = json.loads(raw)
                print(_fmt(event))
                print()
            except json.JSONDecodeError:
                print(f"[RAW] {raw}")


if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("\nDisconnected.")
