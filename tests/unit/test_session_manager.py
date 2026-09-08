"""Unit tests for the SessionManager and conversational memory capabilities."""

from unittest.mock import MagicMock, patch

from contracts.session import ChatMessage, ChatSession, CreateSessionRequest
from services.session.manager import SessionManager


def test_session_contracts():
    session = ChatSession(title="Research Discussion")
    assert session.title == "Research Discussion"
    assert session.message_count == 0
    assert session.id is not None

    msg = ChatMessage(role="user", content="Explain HNSW indexing")
    assert msg.role == "user"
    assert msg.content == "Explain HNSW indexing"
    assert msg.timestamp > 0

    req = CreateSessionRequest(title="Custom Title")
    assert req.title == "Custom Title"


def test_session_manager_in_memory():
    # Force in-memory by disabling Redis connection
    with patch("redis.Redis") as mock_redis_cls:
        mock_redis_cls.side_effect = Exception("Redis unavailable")
        manager = SessionManager(host="nonexistent", port=9999)
        assert manager.redis_client is None

    # Create Session
    session = manager.create_session(title="Test Session")
    assert session.id in manager._in_memory_sessions
    assert session.title == "Test Session"

    # List Sessions
    sessions = manager.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == session.id

    # Append User Message
    msg1 = ChatMessage(role="user", content="Who is the candidate?")
    manager.append_message(session.id, msg1)

    sess, msgs = manager.get_session(session.id)
    assert sess is not None
    assert sess.message_count == 1
    assert len(msgs) == 1
    assert msgs[0].content == "Who is the candidate?"

    # Append Assistant Message
    msg2 = ChatMessage(role="assistant", content="The candidate is Abhishek Kumar.")
    manager.append_message(session.id, msg2)

    sess, msgs = manager.get_session(session.id)
    assert sess.message_count == 2
    assert len(msgs) == 2

    # Context window formatting
    context = manager.build_conversation_context(session.id, max_turns=2)
    assert "User: Who is the candidate?" in context
    assert "Assistant: The candidate is Abhishek Kumar." in context

    # Query reformulation test
    reformulated = manager.reformulate_query("What was his previous role?", session.id)
    assert "Who is the candidate?" in reformulated
    assert "What was his previous role?" in reformulated

    # Non-anaphoric query should not be reformulated
    neutral_query = "What is the capital of France?"
    assert manager.reformulate_query(neutral_query, session.id) == neutral_query

    # Delete Session
    deleted = manager.delete_session(session.id)
    assert deleted is True
    sess_after, msgs_after = manager.get_session(session.id)
    assert sess_after is None
    assert msgs_after == []


def test_session_manager_auto_title():
    with patch("redis.Redis") as mock_redis_cls:
        mock_redis_cls.side_effect = Exception("Redis unavailable")
        manager = SessionManager()

    # Create session with default title
    session = manager.create_session()
    assert session.title == "New Conversation"

    # First user message should auto-generate title
    long_prompt = "Can you describe the distributed vector database and hybrid search pipeline?"
    manager.append_message(session.id, ChatMessage(role="user", content=long_prompt))

    sess, _ = manager.get_session(session.id)
    assert sess is not None
    assert sess.title.startswith("Can you describe the distributed vector datab")
    assert sess.title.endswith("...")


def test_session_manager_redis_mocked():
    mock_redis = MagicMock()
    # Mock ping
    mock_redis.ping.return_value = True

    with patch("redis.Redis", return_value=mock_redis):
        manager = SessionManager(host="127.0.0.1", port=6379)
        assert manager.redis_client is not None

        # Create session
        session = manager.create_session("Redis Session")
        mock_redis.hset.assert_called()

        # List sessions
        mock_redis.hgetall.return_value = {
            session.id: session.model_dump_json()
        }
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].id == session.id

        # Get session
        mock_redis.hget.return_value = session.model_dump_json()
        msg = ChatMessage(role="user", content="Hello Redis")
        mock_redis.lrange.return_value = [msg.model_dump_json()]

        sess, msgs = manager.get_session(session.id)
        assert sess.id == session.id
        assert len(msgs) == 1
        assert msgs[0].content == "Hello Redis"

        # Delete session
        manager.delete_session(session.id)
        mock_redis.hdel.assert_called_with("rag:sessions:meta", session.id)
        mock_redis.delete.assert_called_with(f"rag:sessions:{session.id}:messages")


def test_session_scoped_parameters_and_files():
    from contracts.session import SessionParameters, UpdateSessionRequest

    with patch("redis.Redis") as mock_redis_cls:
        mock_redis_cls.side_effect = Exception("Redis unavailable")
        manager = SessionManager()

    params = SessionParameters(
        model="mistral:7b",
        temperature=0.2,
        retrieval_mode="agentic",
        top_k=8,
        min_score_threshold=0.25,
        compactor_budget=2048,
    )
    session = manager.create_session(
        title="Scoped Session",
        system_prompt="You are a strict financial auditor.",
        parameters=params,
        files=["q3_report.pdf", "balance_sheet.pdf"],
    )

    assert session.title == "Scoped Session"
    assert session.system_prompt == "You are a strict financial auditor."
    assert session.parameters.model == "mistral:7b"
    assert session.parameters.temperature == 0.2
    assert session.parameters.compactor_budget == 2048
    assert session.files == ["q3_report.pdf", "balance_sheet.pdf"]

    # Filter retrieval test
    doc_filter = manager.get_session_filter(session.id)
    assert doc_filter == ["q3_report.pdf", "balance_sheet.pdf"]
    assert manager.get_session_filter("nonexistent") is None

    # Attach files test
    manager.attach_files(session.id, ["audit_notes.pdf", "q3_report.pdf"])
    sess, _ = manager.get_session(session.id)
    assert sess.files == ["q3_report.pdf", "balance_sheet.pdf", "audit_notes.pdf"]

    # Detach file test
    manager.detach_file(session.id, "balance_sheet.pdf")
    sess, _ = manager.get_session(session.id)
    assert sess.files == ["q3_report.pdf", "audit_notes.pdf"]

    # Update session test
    updated = manager.update_session(
        session.id,
        UpdateSessionRequest(
            title="Updated Title",
            system_prompt="New System Prompt",
            parameters=SessionParameters(temperature=0.9),
        ),
    )
    assert updated.title == "Updated Title"
    assert updated.system_prompt == "New System Prompt"
    assert updated.parameters.temperature == 0.9
