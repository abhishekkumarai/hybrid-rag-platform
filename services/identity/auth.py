"""Opaque bearer tokens (login cookies and share URLs) and login throttling (IRA-33)."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

AUTH_COOKIE = "ri_auth"


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Only this digest is stored, so read access to the database can't be turned into a login or
    a working share URL. Tokens are high-entropy random, so an unsalted fast hash is sufficient."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginRateLimiter:
    """Sliding-window cap on failed logins per (email, client) key. Per-process memory is enough for
    the single gateway process this app runs; it resets on restart, which only relaxes the limit."""

    def __init__(self, max_attempts: int, window_s: int) -> None:
        self.max_attempts = max_attempts
        self.window_s = window_s
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and q[0] <= now - self.window_s:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.time())) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.time()
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
