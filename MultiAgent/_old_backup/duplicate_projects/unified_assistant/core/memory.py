"""Small in-process chat history, scoped to a Chainlit session."""

from collections import defaultdict
from threading import RLock


class SessionMemory:
    """Store user/assistant turns for the current process only."""

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
