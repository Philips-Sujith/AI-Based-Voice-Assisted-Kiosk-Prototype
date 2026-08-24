"""
WS /ws/dashboard
Real-time WebSocket push to the Staff Portal & Hardware dashboards (module 6).
Subscribes to the kiosk:queue:events Redis Pub/Sub channel and forwards
all four queue lifecycle event types verbatim to every connected dashboard client.

FLAG 1: Channel name is kiosk:queue:events — Staff Portal must subscribe here.
"""
import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.redis_publisher import get_redis

router = APIRouter()
logger = logging.getLogger(__name__)

# Track connected dashboard clients (for logging/monitoring)
_connected_clients: set[WebSocket] = set()


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket) -> None:
    """
    Staff Portal subscribes here.  One WebSocket connection receives all four
    event types: new_queue_entry, queue_called, transaction_completed, token_expired.
    """
    await websocket.accept()
    _connected_clients.add(websocket)
    logger.info("Staff Portal connected. Active clients: %d", len(_connected_clients))

    redis_client = await get_redis()
    pubsub: aioredis.client.PubSub = redis_client.pubsub()
    await pubsub.subscribe(settings.REDIS_QUEUE_CHANNEL)

    async def forward_redis_to_ws() -> None:
        """Read from Redis Pub/Sub and push to the WebSocket client."""
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])

    async def watch_client_disconnect() -> None:
        """Drain any keep-alive pings and detect a clean client disconnect."""
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass

    forward_task = asyncio.create_task(forward_redis_to_ws())
    disconnect_task = asyncio.create_task(watch_client_disconnect())

    try:
        # Wait until the client disconnects or the forward task errors
        _done, pending = await asyncio.wait(
            [forward_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    except Exception as exc:
        logger.error("Dashboard WebSocket error: %s", exc)
    finally:
        await pubsub.unsubscribe(settings.REDIS_QUEUE_CHANNEL)
        await pubsub.aclose()
        _connected_clients.discard(websocket)
        logger.info(
            "Staff Portal disconnected. Active clients: %d", len(_connected_clients)
        )
