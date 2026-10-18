"""Server-side demo sessions for the API.

The browser holds only a random id in an HttpOnly cookie. Everything that decides what a user
may do (role, business) lives here, in the Session built at sign-in, and is never read from a
request body. Sessions are in memory: restarting the server signs everyone out.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from copilot.agent import Session

MAX_SESSIONS = 20  # live sessions at once; the least recently used one is evicted
IDLE_SECONDS = 2 * 60 * 60  # sessions end after 2 hours without a request
MAX_MESSAGES = 40  # chat messages per session that may reach a paid model
MAX_CACHED = 16  # read results kept per session (see Entry.cache)


@dataclass
class Entry:
    session: Session
    assistant: str  # "claude" or "mock"
    lock: threading.Lock = field(default_factory=threading.Lock)  # a Session isn't thread-safe
    messages_used: int = 0
    last_seen: float = 0.0
    # Read results by request (path + query). Every read is deterministic for the session's
    # data, which only changes through chat or the clock: both clear this.
    cache: dict[str, Any] = field(default_factory=dict)

    def remember(self, key: str, make: Callable[[], Any]) -> Any:
        if key not in self.cache:
            while len(self.cache) >= MAX_CACHED:
                del self.cache[next(iter(self.cache))]  # oldest first
            self.cache[key] = make()
        return self.cache[key]


class SessionStore:
    def __init__(
        self,
        max_sessions: int = MAX_SESSIONS,
        idle_seconds: float = IDLE_SECONDS,
        max_messages: int = MAX_MESSAGES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_sessions = max_sessions
        self.idle_seconds = idle_seconds
        self.max_messages = max_messages
        self._clock = clock
        self._entries: dict[str, Entry] = {}
        self._lock = threading.Lock()

    def create(self, session: Session, assistant: str) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._expire()
            while len(self._entries) >= self.max_sessions:
                oldest = min(self._entries, key=lambda k: self._entries[k].last_seen)
                del self._entries[oldest]
            self._entries[sid] = Entry(session, assistant, last_seen=self._clock())
        return sid

    def get(self, sid: str | None) -> Entry | None:
        """The live entry for this id, or None if unknown or expired (it is then removed)."""
        if not sid:
            return None
        with self._lock:
            self._expire()
            entry = self._entries.get(sid)
            if entry is not None:
                entry.last_seen = self._clock()
            return entry

    def end(self, sid: str | None) -> None:
        with self._lock:
            self._entries.pop(sid or "", None)

    def __len__(self) -> int:
        return len(self._entries)

    def _expire(self) -> None:
        cutoff = self._clock() - self.idle_seconds
        for sid in [k for k, e in self._entries.items() if e.last_seen < cutoff]:
            del self._entries[sid]
