"""Session and conversational memory manager backed by Redis with in-memory fallback."""

from __future__ import annotations

import time
from typing import Any

from contracts.session import (
    ChatMessage,
    ChatSession,
    Conversation,
    SessionParameters,
    UpdateSessionRequest,
)
from services.common.logger import get_logger

logger = get_logger("session.manager")

DEFAULT_CONVERSATION_TITLE = "Main"


class SessionManager:
    """Manages multi-turn conversation sessions, workspace parameters, and message history.

    A session (project) can own multiple conversations (IRA-24): documents, settings, and persona
    stay on the `ChatSession`, while message history is scoped per `Conversation`. Callers that omit
    `conversation_id` transparently get the project's oldest/default conversation, so pre-IRA-24
    callers and data keep working."""

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0) -> None:
        self.host = host
        self.port = port
        self.db = db
        self.redis_client: Any = None
        self._in_memory_sessions: dict[str, ChatSession] = {}
        self._in_memory_messages: dict[str, list[ChatMessage]] = {}
        self._in_memory_conversations: dict[str, dict[str, Conversation]] = {}
        self._in_memory_conv_messages: dict[str, list[ChatMessage]] = {}

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
        owner_id: str | None = None,
        forked_from: str | None = None,
        workspace_id: str | None = None,
    ) -> ChatSession:
        """Creates a new conversational chat session with scoped parameters, prompt, and files."""
        session = ChatSession(
            title=title or "New Conversation",
            system_prompt=system_prompt,
            parameters=parameters or SessionParameters(),
            files=list(dict.fromkeys(files or [])),
            owner_id=owner_id,
            forked_from=forked_from,
            workspace_id=workspace_id,
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

    def list_sessions(self, owner_id: str | None = None, workspace_id: str | None = None) -> list[ChatSession]:
        """Lists chat sessions sorted by updated_at descending; only `owner_id`'s or `workspace_id`'s
        when given.

        Filtering the one meta hash (rather than keeping a per-user index set) means ownership has a
        single source of truth that can't drift out of sync with the session records."""
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

        if owner_id is not None:
            sessions = [s for s in sessions if s.owner_id == owner_id]
        if workspace_id is not None:
            sessions = [s for s in sessions if s.workspace_id == workspace_id]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def get_owned(self, session_id: str, owner_id: str) -> tuple[ChatSession | None, list[ChatMessage]]:
        """Like `get_session`, but a session owned by someone else is reported as missing (IRA-34)."""
        session, messages = self.get_session(session_id)
        if not session or session.owner_id != owner_id:
            return None, []
        return session, messages

    def get_for_member(
        self, session_id: str, member_workspace_ids: set[str]
    ) -> tuple[ChatSession | None, list[ChatMessage]]:
        """Like `get_owned`, but visible to any member of the project's workspace (IRA-46).

        A session with no `workspace_id` predates workspaces and isn't visible here even to its
        owner — callers should fall back to `get_owned` for those until they're backfilled."""
        session, messages = self.get_session(session_id)
        if not session or session.workspace_id is None or session.workspace_id not in member_workspace_ids:
            return None, []
        return session, messages

    def adopt_unowned(self, owner_id: str) -> int:
        """Assigns every session that predates accounts to `owner_id`. Returns how many changed."""
        adopted = 0
        for session in self.list_sessions():
            if session.owner_id is None:
                session.owner_id = owner_id
                self._save(session)
                adopted += 1
        return adopted

    def stamp_workspace_for_owner(self, owner_id: str, workspace_id: str) -> int:
        """Stamps every one of `owner_id`'s sessions that has no workspace yet. Returns how many changed."""
        stamped = 0
        for session in self.list_sessions(owner_id=owner_id):
            if session.workspace_id is None:
                session.workspace_id = workspace_id
                self._save(session)
                stamped += 1
        return stamped

    def _save(self, session: ChatSession) -> None:
        if self.redis_client:
            try:
                self.redis_client.hset("rag:sessions:meta", session.id, session.model_dump_json())
                return
            except Exception as e:
                logger.error(f"Error persisting session to Redis: {e}")
        self._in_memory_sessions[session.id] = session

    def get_session(self, session_id: str) -> tuple[ChatSession | None, list[ChatMessage]]:
        """Retrieves session metadata and the default conversation's message history.

        Kept for callers that predate IRA-24 (e.g. `SessionDetailResponse`) — it always resolves to
        the project's default/first conversation, migrating any pre-IRA-24 flat history into it."""
        session = self._get_session_meta(session_id)
        if not session:
            return None, []

        conversation_id = self._resolve_default_conversation(session_id)
        messages = self._get_conv_messages(session_id, conversation_id)
        return session, messages

    def _get_session_meta(self, session_id: str) -> ChatSession | None:
        if self.redis_client:
            try:
                raw_meta = self.redis_client.hget("rag:sessions:meta", session_id)
                if raw_meta:
                    return ChatSession.model_validate_json(raw_meta)
                return None
            except Exception as e:
                logger.error(f"Error fetching session meta {session_id}: {e}")
                return self._in_memory_sessions.get(session_id)
        return self._in_memory_sessions.get(session_id)

    # ------------------------------------------------------------------
    # Conversations (IRA-24)
    # ------------------------------------------------------------------

    def _conv_meta_key(self, session_id: str) -> str:
        return f"rag:sessions:{session_id}:conversations"

    def _conv_messages_key(self, session_id: str, conversation_id: str) -> str:
        return f"rag:sessions:{session_id}:conv:{conversation_id}:messages"

    def _legacy_messages_key(self, session_id: str) -> str:
        return f"rag:sessions:{session_id}:messages"

    def _save_conversation(self, conversation: Conversation) -> None:
        if self.redis_client:
            try:
                self.redis_client.hset(
                    self._conv_meta_key(conversation.session_id),
                    conversation.id,
                    conversation.model_dump_json(),
                )
                return
            except Exception as e:
                logger.error(f"Error persisting conversation to Redis: {e}")
        self._in_memory_conversations.setdefault(conversation.session_id, {})[conversation.id] = conversation

    def _raw_list_conversations(self, session_id: str) -> list[Conversation]:
        if self.redis_client:
            try:
                raw = self.redis_client.hgetall(self._conv_meta_key(session_id))
                return [Conversation.model_validate_json(v) for v in raw.values()]
            except Exception as e:
                logger.error(f"Error listing conversations for {session_id}: {e}")
        return list(self._in_memory_conversations.get(session_id, {}).values())

    def _resolve_default_conversation(self, session_id: str) -> str:
        """Returns the project's oldest conversation id, migrating legacy flat history if needed."""
        existing = self._raw_list_conversations(session_id)
        if existing:
            existing.sort(key=lambda c: c.created_at)
            return existing[0].id

        # Lazily migrate a pre-IRA-24 flat message list into a new default conversation (idempotent:
        # once the conversation exists above, this branch never runs again for this session).
        legacy_messages = self._read_raw_messages(self._legacy_messages_key(session_id))
        conversation = Conversation(
            session_id=session_id,
            title=DEFAULT_CONVERSATION_TITLE,
            message_count=len(legacy_messages),
        )
        if legacy_messages:
            self._write_raw_messages(self._conv_messages_key(session_id, conversation.id), legacy_messages)
            conversation.created_at = legacy_messages[0].timestamp
            conversation.updated_at = legacy_messages[-1].timestamp
        self._save_conversation(conversation)
        return conversation.id

    def _read_raw_messages(self, key: str) -> list[ChatMessage]:
        if self.redis_client:
            try:
                raw_msgs = self.redis_client.lrange(key, 0, -1)
                return [ChatMessage.model_validate_json(m) for m in raw_msgs]
            except Exception as e:
                logger.error(f"Error fetching messages {key}: {e}")
                return []
        return list(self._in_memory_messages.get(key, []))

    def _write_raw_messages(self, key: str, messages: list[ChatMessage]) -> None:
        if self.redis_client:
            try:
                if messages:
                    self.redis_client.rpush(key, *(m.model_dump_json() for m in messages))
                return
            except Exception as e:
                logger.error(f"Error writing messages {key}: {e}")
        self._in_memory_messages[key] = list(messages)

    def resolve_conversation_id(self, session_id: str, conversation_id: str | None = None) -> str:
        """Returns `conversation_id` unchanged, or the project's default conversation id if omitted."""
        return conversation_id or self._resolve_default_conversation(session_id)

    def list_conversations(self, session_id: str) -> list[Conversation]:
        """Lists a project's chat threads, oldest first, migrating legacy history if needed."""
        self._resolve_default_conversation(session_id)
        conversations = self._raw_list_conversations(session_id)
        conversations.sort(key=lambda c: c.created_at)
        return conversations

    def create_conversation(self, session_id: str, title: str | None = None) -> Conversation | None:
        """Starts a new, empty chat thread within a project."""
        if not self._get_session_meta(session_id):
            return None
        conversation = Conversation(session_id=session_id, title=title or "New Chat")
        self._save_conversation(conversation)
        return conversation

    def rename_conversation(self, session_id: str, conversation_id: str, title: str) -> Conversation | None:
        conversations = self._raw_list_conversations(session_id)
        conversation = next((c for c in conversations if c.id == conversation_id), None)
        if not conversation:
            return None
        conversation.title = title
        conversation.updated_at = time.time()
        self._save_conversation(conversation)
        return conversation

    def delete_conversation(self, session_id: str, conversation_id: str) -> bool:
        """Deletes one chat thread. Refuses to delete a project's last remaining conversation."""
        conversations = self.list_conversations(session_id)
        if len(conversations) <= 1 or not any(c.id == conversation_id for c in conversations):
            return False

        if self.redis_client:
            try:
                self.redis_client.hdel(self._conv_meta_key(session_id), conversation_id)
                self.redis_client.delete(self._conv_messages_key(session_id, conversation_id))
            except Exception as e:
                logger.error(f"Error deleting conversation {conversation_id}: {e}")
        self._in_memory_conversations.get(session_id, {}).pop(conversation_id, None)
        self._in_memory_messages.pop(self._conv_messages_key(session_id, conversation_id), None)
        return True

    def _get_conv_messages(self, session_id: str, conversation_id: str) -> list[ChatMessage]:
        return self._read_raw_messages(self._conv_messages_key(session_id, conversation_id))

    def get_conversation_messages(
        self, session_id: str, conversation_id: str | None
    ) -> tuple[Conversation | None, list[ChatMessage]]:
        """Retrieves one conversation's metadata and message history. `None` resolves to the default."""
        resolved_id = conversation_id or self._resolve_default_conversation(session_id)
        conversations = self._raw_list_conversations(session_id)
        conversation = next((c for c in conversations if c.id == resolved_id), None)
        if not conversation:
            return None, []
        return conversation, self._get_conv_messages(session_id, resolved_id)

    def append_message(
        self, session_id: str, message: ChatMessage, conversation_id: str | None = None
    ) -> None:
        """Appends a new turn message to a conversation's history and updates both metadata records."""
        now = time.time()
        resolved_id = conversation_id or self._resolve_default_conversation(session_id)
        key = self._conv_messages_key(session_id, resolved_id)

        if self.redis_client:
            try:
                self.redis_client.rpush(key, message.model_dump_json())
            except Exception as e:
                logger.error(f"Error appending message to Redis: {e}")
                self._in_memory_messages.setdefault(key, []).append(message)
        else:
            self._in_memory_messages.setdefault(key, []).append(message)

        # Update conversation metadata (title auto-fill + counters)
        conversations = self._raw_list_conversations(session_id)
        conversation = next((c for c in conversations if c.id == resolved_id), None)
        if conversation:
            conversation.updated_at = now
            conversation.message_count += 1
            if conversation.title in ("New Chat", DEFAULT_CONVERSATION_TITLE) and message.role == "user":
                conversation.title = message.content[:45] + ("..." if len(message.content) > 45 else "")
            self._save_conversation(conversation)

        # Update project metadata (bumps gallery ordering, keeps message_count as a project-wide total)
        session = self._get_session_meta(session_id)
        if session:
            session.updated_at = now
            session.message_count += 1
            if session.title == "New Conversation" and message.role == "user":
                session.title = message.content[:45] + ("..." if len(message.content) > 45 else "")
            self._save(session)

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session, all its conversations, and their message history."""
        deleted = False
        conversation_ids = [c.id for c in self._raw_list_conversations(session_id)]
        if self.redis_client:
            try:
                self.redis_client.hdel("rag:sessions:meta", session_id)
                self.redis_client.delete(self._conv_meta_key(session_id))
                for conversation_id in conversation_ids:
                    self.redis_client.delete(self._conv_messages_key(session_id, conversation_id))
                self.redis_client.delete(self._legacy_messages_key(session_id))
                deleted = True
            except Exception as e:
                logger.error(f"Error deleting session {session_id} from Redis: {e}")

        if session_id in self._in_memory_sessions:
            del self._in_memory_sessions[session_id]
            deleted = True
        self._in_memory_messages.pop(session_id, None)
        self._in_memory_conversations.pop(session_id, None)
        for conversation_id in conversation_ids:
            self._in_memory_messages.pop(self._conv_messages_key(session_id, conversation_id), None)

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
            # Preserve existing session parameters if only a subset was provided in the update
            current_params_dict = session.parameters.model_dump()
            update_params_dict = update_req.parameters.model_dump(exclude_unset=True)
            current_params_dict.update(update_params_dict)
            session.parameters = SessionParameters(**current_params_dict)
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

    def build_conversation_context(
        self,
        session_id: str,
        conversation_id: str | None = None,
        max_turns: int = 4,
        max_answer_chars: int = 240,
    ) -> str:
        """Formats the last N turns as a compact reference-resolution aid for the prompt.

        Assistant turns are cut to their answer (the appended "Verified Sources" provenance block
        is dropped) and truncated: history exists to resolve "he"/"that" in the next question, and a
        long verbatim prior answer is what small models copy instead of answering the new
        question (IRA-17)."""
        if conversation_id:
            messages = self._get_conv_messages(session_id, conversation_id)
        else:
            _, messages = self.get_session(session_id)
        if not messages:
            return ""

        relevant = messages[-(max_turns * 2) :]
        lines: list[str] = []
        for m in relevant:
            if m.role == "user":
                lines.append(f"User: {m.content.strip()}")
                continue
            answer = m.content.split("\n---\n", 1)[0].strip()
            answer = " ".join(answer.split())
            if len(answer) > max_answer_chars:
                answer = answer[:max_answer_chars].rsplit(" ", 1)[0] + " ..."
            lines.append(f"Assistant: {answer}")

        return "\n".join(lines)

    def reformulate_query(
        self, query: str, session_id: str | None, conversation_id: str | None = None
    ) -> str:
        """Enriches short anaphoric follow-up queries with context from recent turns."""
        if not session_id:
            return query

        query_words = query.strip().split()
        # Full queries with 8+ words have sufficient context on their own
        if len(query_words) >= 8:
            return query

        anaphoric_triggers = {"he", "his", "him", "she", "her", "it", "its", "they", "their", "there", "that", "this", "these", "those"}
        words = set(w.lower().strip(".,?!:;") for w in query_words)
        has_anaphora = bool(words.intersection(anaphoric_triggers))

        if not has_anaphora:
            return query

        if conversation_id:
            messages = self._get_conv_messages(session_id, conversation_id)
        else:
            _, messages = self.get_session(session_id)
        if not messages:
            return query

        # Exclude the current query if it was already appended to avoid self-referencing
        prior_user_turns = [m.content for m in messages if m.role == "user" and m.content.strip() != query.strip()]
        if not prior_user_turns:
            return query

        last_query = prior_user_turns[-1].strip()
        logger.info(f"Query reformulation triggered for short query: '{query}' with context: '{last_query}'")
        return f"{query} ({last_query})"
