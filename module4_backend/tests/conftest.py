"""Shared pytest fixtures."""
import pytest


@pytest.fixture(autouse=True)
def reset_queue_manager():
    """Reset the queue manager's daily counter between every test."""
    from app.services.queue_manager import queue_manager
    queue_manager.reset_daily()
    yield
    queue_manager.reset_daily()
