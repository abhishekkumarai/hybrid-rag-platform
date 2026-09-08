"""Session and conversational memory manager backed by Redis with in-memory fallback."""

from __future__ import annotations

import time
from typing import Any

from contracts.session import ChatMessage, ChatSession, SessionParameters, UpdateSessionRequest
from services.common.logger import get_logger

logger = get_logger("session.manager")


class SessionManager:
    """Manages multi-turn conversation sessions, workspace parameters, and message history."""

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0) -> None:
        self.host = host
        self.port = port
        self.db = db
        self.redis_client: Any = None
        self._in_memory_sessions: dict[str, ChatSession] = {}
        self._in_memory_messages: dict[str, list[ChatMessage]] = {}

        self._init_redis()

    def _init_redis(self) -> None:
        try:
            import redis

            client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                socket_timeout=1.0,
                decode_responses=True,
            )
            client.ping()
            self.redis_client = client
            logger.info(f"SessionManager connected to Redis at {self.host}:{self.port}")
        except Exception as e:
            logger.warning(f"SessionManager could not connect to Redis ({e}); using in-memory store")
            self.redis_client = None

    def create_session(
        self,
        title: str | None = None,
        system_prompt: str | None = None,
        parameters: SessionParameters | None = None,
        files: list[str] | None = None,
    ) -> ChatSession:
        """Creates a new conversational chat session with scoped parameters, prompt, and files."""
        session = ChatSession(
            title=title or "New Conversation",
            system_prompt=system_prompt,
            parameters=parameters or SessionParameters(),
            files=list(dict.fromkeys(files or [])),
        )
        if self.redis_client:
            try:
                # Store metadata in hash
                self.redis_client.hset("rag:sessions:meta", session.id, session.model_dump_json())
            except Exception as e:
                logger.error(f"Error persisting session to Redis: {e}")
                self._in_memory_sessions[session.id] = session
        else:
            self._in_memory_sessions[session.id] = session

        logger.info(
            f"Created session '{session.id}' (title='{session.title}', files={len(session.files)}, model='{session.parameters.model}')"
        )
        return session

    def list_sessions(self) -> list[ChatSession]:
        """Lists all registered chat sessions sorted by updated_at descending."""
        sessions: list[ChatSession] = []
        if self.redis_client:
            try:
                raw_data = self.redis_client.hgetall("rag:sessions:meta")
                for _, s_json in raw_data.items():
                    sessions.append(ChatSession.model_validate_json(s_json))
            except Exception as e:
                logger.error(f"Error fetching sessions from Redis: {e}")
                sessions = list(self._in_memory_sessions.values())
        else:
            sessions = list(self._in_memory_sessions.values())

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def get_session(self, session_id: str) -> tuple[ChatSession | None, list[ChatMessage]]:
        """Retrieves session metadata and chronological message history."""
        # 1. Fetch Session Metadata
        session: ChatSession | None = None
        if self.redis_client:
            try:
                raw_meta = self.redis_client.hget("rag:sessions:meta", session_id)
                if raw_meta:
                    session = ChatSession.model_validate_json(raw_meta)
            except Exception as e:
                logger.error(f"Error fetching session meta {session_id}: {e}")
                session = self._in_memory_sessions.get(session_id)
        else:
            session = self._in_memory_sessions.get(session_id)

        if not session:
            return None, []

        # 2. Fetch Messages
        messages: list[ChatMessage] = []
        if self.redis_client:
            try:
                raw_msgs = self.redis_client.lrange(f"rag:sessions:{session_id}:messages", 0, -1)
                for m_json in raw_msgs:
                    messages.append(ChatMessage.model_validate_json(m_json))
            except Exception as e:
                logger.error(f"Error fetching session messages {session_id}: {e}")
                messages = self._in_memory_messages.get(session_id, [])
        else:
            messages = self._in_memory_messages.get(session_id, [])

        return session, messages

    def append_message(self, session_id: str, message: ChatMessage) -> None:
        """Appends a new turn message to the session history and updates metadata."""
        now = time.time()
        if self.redis_client:
            try:
                self.redis_client.rpush(f"rag:sessions:{session_id}:messages", message.model_dump_json())
                # Update session metadata
                raw_meta = self.redis_client.hget("rag:sessions:meta", session_id)
                if raw_meta:
                    sess = ChatSession.model_validate_json(raw_meta)
                    sess.updated_at = now
                    sess.message_count += 1
                    # Auto-update title from first user query if default
                    if sess.title == "New Conversation" and message.role == "user":
                        sess.title = message.content[:45] + ("..." if len(message.content) > 45 else "")
                    self.redis_client.hset("rag:sessions:meta", session_id, sess.model_dump_json())
            except Exception as e:
                logger.error(f"Error appending message to Redis: {e}")
                self._append_in_memory(session_id, message, now)
        else:
            self._append_in_memory(session_id, message, now)

    def _append_in_memory(self, session_id: str, message: ChatMessage, timestamp: float) -> None:
        if session_id not in self._in_memory_messages:
            self._in_memory_messages[session_id] = []
        self._in_memory_messages[session_id].append(message)
        sess = self._in_memory_sessions.get(session_id)
        if sess:
            sess.updated_at = timestamp
            sess.message_count += 1
            if sess.title == "New Conversation" and message.role == "user":
                sess.title = message.content[:45] + ("..." if len(message.content) > 45 else "")

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session and its message history."""
        deleted = False
        if self.redis_client:
            try:
                self.redis_client.hdel("rag:sessions:meta", session_id)
                self.redis_client.delete(f"rag:sessions:{session_id}:messages")
                deleted = True
            except Exception as e:
                logger.error(f"Error deleting session {session_id} from Redis: {e}")

        if session_id in self._in_memory_sessions:
            del self._in_memory_sessions[session_id]
            deleted = True
        if session_id in self._in_memory_messages:
            del self._in_memory_messages[session_id]

        logger.info(f"Deleted session '{session_id}' (success={deleted})")
        return deleted

    def update_session(self, session_id: str, update_req: UpdateSessionRequest) -> ChatSession | None:
        """Updates session title, system prompt, parameters, or attached files."""
        session, _ = self.get_session(session_id)
        if not session:
            return None

        if update_req.title is not None:
            session.title = update_req.title
        if update_req.system_prompt is not None:
            session.system_prompt = update_req.system_prompt
        if update_req.parameters is not None:
            session.parameters = update_req.parameters
        if update_req.files is not None:
            session.files = list(dict.fromkeys(update_req.files))

        session.updated_at = time.time()

        if self.redis_client:
            try:
                self.redis_client.hset("rag:sessions:meta", session.id, session.model_dump_json())
            except Exception as e:
                logger.error(f"Error updating session in Redis: {e}")
                self._in_memory_sessions[session.id] = session
        else:
            self._in_memory_sessions[session.id] = session

        logger.info(f"Updated session '{session.id}' (title='{session.title}', files={len(session.files)})")
        return session

    def attach_files(self, session_id: str, files: list[str]) -> ChatSession | None:
        """Attaches one or more documents to a session workspace."""
        session, _ = self.get_session(session_id)
        if not session:
            return None

        combined = session.files + files
        session.files = list(dict.fromkeys(combined))
        session.updated_at = time.time()

        if self.redis_client:
            try:
                self.redis_client.hset("rag:sessions:meta", session.id, session.model_dump_json())
            except Exception as e:
                logger.error(f"Error updating session files in Redis: {e}")
                self._in_memory_sessions[session.id] = session
        else:
            self._in_memory_sessions[session.id] = session

        return session

    def detach_file(self, session_id: str, doc_id: str) -> ChatSession | None:
        """Detaches a specific document from a session workspace."""
        session, _ = self.get_session(session_id)
        if not session:
            return None

        session.files = [f for f in session.files if f != doc_id]
        session.updated_at = time.time()

        if self.redis_client:
            try:
                self.redis_client.hset("rag:sessions:meta", session.id, session.model_dump_json())
            except Exception as e:
                logger.error(f"Error updating session files in Redis: {e}")
                self._in_memory_sessions[session.id] = session
        else:
            self._in_memory_sessions[session.id] = session

        return session

    def get_session_filter(self, session_id: str | None) -> list[str] | None:
        """Returns document IDs scoped to this session, or None if no filter applies."""
        if not session_id:
            return None
        session, _ = self.get_session(session_id)
        if not session or not session.files:
            return None
        return session.files

    def build_conversation_context(self, session_id: str, max_turns: int = 4) -> str:
        """Formats the last N conversation turns into a prompt context prefix."""
        _, messages = self.get_session(session_id)
        if not messages:
            return ""

        # Take last max_turns user/assistant pairs
        relevant = messages[-(max_turns * 2) :]
        lines: list[str] = []
        for m in relevant:
            role_label = "User" if m.role == "user" else "Assistant"
            lines.append(f"{role_label}: {m.content}")

        return "\n".join(lines)

    def reformulate_query(self, query: str, session_id: str | None) -> str:
        """Enriches anaphoric follow-up queries with entity keywords from recent turns."""
        if not session_id:
            return query

        anaphoric_triggers = {"he", "his", "him", "she", "her", "it", "its", "they", "their", "there", "that company", "that role"}
        words = set(query.lower().split())
        has_anaphora = bool(words.intersection(anaphoric_triggers))

        if not has_anaphora:
            return query

        _, messages = self.get_session(session_id)
        if not messages:
            return query

        # Exclude the current query if it was already appended to avoid self-referencing
        prior_user_turns = [m.content for m in messages if m.role == "user" and m.content.strip() != query.strip()]
        if not prior_user_turns:
            return query

        first_query = prior_user_turns[0]
        last_query = prior_user_turns[-1]
        logger.info(f"Query reformulation triggered: '{query}' using prior turns: '{last_query}'")
        if first_query != last_query:
            return f"{first_query} {last_query} - {query}"
        return f"{last_query} - {query}"

