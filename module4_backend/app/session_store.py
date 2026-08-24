import logging
from typing import Dict, Optional, Tuple

from app.fsm.session_context import SessionContext
from app.fsm.kiosk_machine import KioskMachine

logger = logging.getLogger(__name__)

# Type alias for a session entry
SessionEntry = Tuple[SessionContext, KioskMachine]


class SessionStore:
    """
    In-memory registry of all active sessions, keyed by session_id.
    One SessionContext + KioskMachine pair per customer session.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionEntry] = {}

    def create_session(self, session_id: str) -> SessionEntry:
        context = SessionContext(session_id)
        machine = KioskMachine(context)
        self._sessions[session_id] = (context, machine)
        logger.info("[%s] Session created.", session_id)
        return context, machine

    def get_session(self, session_id: str) -> Optional[SessionEntry]:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> SessionEntry:
        if session_id not in self._sessions:
            return self.create_session(session_id)
        return self._sessions[session_id]

    def remove_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("[%s] Session removed.", session_id)

    def find_by_token_id(self, token_id: str) -> Optional[SessionEntry]:
        """Linear search by token_id — acceptable for single-kiosk session counts."""
        for ctx, machine in self._sessions.values():
            if ctx.token_id == token_id:
                return ctx, machine
        return None

    def count(self) -> int:
        return len(self._sessions)


# Module-level singleton — imported by all routers
session_store = SessionStore()
