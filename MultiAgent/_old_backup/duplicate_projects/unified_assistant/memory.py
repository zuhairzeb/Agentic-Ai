"""Bounded in-process conversation memory scoped to each Chainlit session."""

from collections import defaultdict
from threading import RLock
import re


_SENSITIVE_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN-like identifier
    re.compile(r"\b\d{13,19}\b"),  # payment-card/account-like digit string
    re.compile(r"\b(?:\+?\d[\d .()\-]{7,}\d)\b"),  # phone number
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b(?:api[_ -]?key|password|passwd|secret|token)\s*[:=]", re.I),
)


def is_sensitive_memory(value: str) -> bool:
    """Conservatively reject likely credentials and personal contact/ID data."""
    return any(pattern.search(value) for pattern in _SENSITIVE_PATTERNS)


class SessionMemory:
    def __init__(self, max_turns: int = 20):
        self._histories: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._lock = RLock()
        self.max_turns = max_turns

    def get(self, session_id: str) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._histories.get(session_id, []))

    def add_turn(self, session_id: str, user: str, assistant: str) -> None:
        with self._lock:
            history = self._histories[session_id]
            history.extend((("user", user), ("assistant", assistant)))
            del history[:-self.max_turns * 2]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._histories.pop(session_id, None)


session_memory = SessionMemory()
