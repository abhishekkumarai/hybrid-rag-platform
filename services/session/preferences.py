"""Per-user preferences (IRA-56), kept next to projects in Redis with an in-memory fallback."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from contracts.session import UserPreferences
from services.common.logger import get_logger

logger = get_logger("session.preferences")

_KEY = "rag:user_prefs"


class PreferencesStore:
    # The Redis client is fetched on each call so the store follows the session manager's connection
    # (and its in-memory fallback), instead of holding a second, possibly stale, client.
    def __init__(self, redis_client: Callable[[], Any]):
        self._redis = redis_client
        self._memory: dict[str, UserPreferences] = {}

    def get(self, user_id: str) -> UserPreferences:
        client = self._redis()
        if client is not None:
            try:
                raw = client.hget(_KEY, user_id)
                if raw:
                    return UserPreferences.model_validate_json(raw)
                return UserPreferences()
            except Exception as exc:
                logger.error(f"Error reading preferences for {user_id}: {exc}")
        return self._memory.get(user_id, UserPreferences())

    def save(self, user_id: str, prefs: UserPreferences) -> UserPreferences:
        client = self._redis()
        if client is not None:
            try:
                client.hset(_KEY, user_id, prefs.model_dump_json())
                return prefs
            except Exception as exc:
                logger.error(f"Error saving preferences for {user_id}: {exc}")
        self._memory[user_id] = prefs
        return prefs
