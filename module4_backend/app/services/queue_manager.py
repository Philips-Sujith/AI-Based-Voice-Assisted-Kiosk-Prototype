"""
Queue Manager — sequential daily token numbers and background expiry tasks.

Token numbers are simple, sequential integers (1, 2, 3 …) that reset at the
start of each business day.  The same number is spoken aloud to the customer,
printed on the receipt, and shown on the teller dashboard as
customer_display_name = "Token N".  This makes it unambiguous for elderly and
illiterate customers who need to match what they heard to what the teller calls.
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


class QueueManager:
    def __init__(self) -> None:
        self._counter: int = 0          # sequential token number (resets daily)
        self._queue_size: int = 0       # currently in-queue count

    # ── Token numbering ───────────────────────────────────────────────────────

    def next_token_number(self) -> int:
        """Assign and return the next sequential token number for the day."""
        self._counter += 1
        self._queue_size += 1
        return self._counter

    def current_queue_size(self) -> int:
        return self._queue_size

    def decrement_queue(self) -> None:
        """Call when a customer completes or expires — shrinks the live queue count."""
        self._queue_size = max(0, self._queue_size - 1)

    def reset_daily(self) -> None:
        """Reset counter and queue size at the start of a new business day."""
        self._counter = 0
        self._queue_size = 0
        logger.info("Queue counter reset for new business day.")

    # ── Expiry task ───────────────────────────────────────────────────────────

    def launch_expiry_task(
        self,
        session_id: str,
        token_id: str,
        expires_at: str,
        backend_base_url: str = "http://localhost:8000",
    ) -> "asyncio.Task[None]":
        """
        Spawns a background asyncio task that sleeps until expires_at and then
        calls POST /api/v1/teller/{token_id}/expire on this backend.

        The teller's /complete endpoint cancels this task if the transaction
        completes before expiry — ensuring completed ≠ expired at all times.
        """
        task: asyncio.Task[None] = asyncio.create_task(
            self._expiry_watcher(session_id, token_id, expires_at, backend_base_url),
            name=f"expiry-{token_id[:8]}",
        )
        logger.info(
            "[%s] Expiry task launched for token %s. expires_at=%s",
            session_id,
            token_id,
            expires_at,
        )
        return task

    async def _expiry_watcher(
        self,
        session_id: str,
        token_id: str,
        expires_at: str,
        backend_base_url: str,
    ) -> None:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        wait_seconds = (expires_dt - datetime.now(timezone.utc)).total_seconds()

        try:
            if wait_seconds > 0:
                logger.debug(
                    "[%s] Expiry watcher sleeping %.1fs.", session_id, wait_seconds
                )
                await asyncio.sleep(wait_seconds)
        except asyncio.CancelledError:
            logger.info(
                "[%s] Expiry task cancelled — transaction completed first.", session_id
            )
            return

        logger.info(
            "[%s] Token %s expired. Calling /expire endpoint.", session_id, token_id
        )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{backend_base_url}/api/v1/teller/{token_id}/expire"
                )
        except Exception as exc:
            logger.error(
                "[%s] Failed to reach /expire endpoint for token %s: %s",
                session_id,
                token_id,
                exc,
            )


# Module-level singleton
queue_manager = QueueManager()
