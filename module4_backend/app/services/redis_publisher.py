"""
Redis Pub/Sub publisher for queue lifecycle events.
All four event types (new_queue_entry, queue_called, transaction_completed,
token_expired) are published to the single kiosk:queue:events channel.

FLAG 1: Channel name confirmed as kiosk:queue:events — Staff Portal must subscribe here.
"""
import json
import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    """Return the module-level Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis_client


async def publish_event(event: dict) -> None:
    """Publish a queue lifecycle event dict to the global broadcast channel."""
    client = await get_redis()
    payload = json.dumps(event)
    await client.publish(settings.REDIS_QUEUE_CHANNEL, payload)
    logger.info(
        "Published event '%s' (token_id=%s) → channel '%s'",
        event.get("event"),
        event.get("token_id"),
        settings.REDIS_QUEUE_CHANNEL,
    )


async def close_redis() -> None:
    """Cleanly close the Redis connection on application shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed.")
