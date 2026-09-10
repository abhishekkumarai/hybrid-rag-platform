"""Unit tests for multi-session workspace isolation, document scoping, custom personas, and parameters."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from contracts.retrieval import Candidate, Citation, RetrieveResponse
from contracts.session import SessionParameters
from services.gateway.api import app, session_manager

client = TestClient(app)


def test_session_scoped_crud_and_patch():
    """Validates session lifecycle REST endpoints: creation, retrieval, patching, and deletion."""
    # 1. Create Session
    create_payload = {
        "title": "SEC Audit Workspace",
        "system_prompt": "You are a senior financial auditor.",
        "parameters": {
            "model": "llama3.1:8b",
            "temperature": 0.2,
            "retrieval_mode": "direct",
            "top_k": 10,
            "min_score_threshold": 0.2,
            "compactor_budget": 2048,
        },
        "files": ["10k_nvda_2024.pdf", "10q_nvda_q3.pdf"],
    }
    res = client.post("/api/v1/sessions", json=create_payload)
    assert res.status_code == 200
    sess_data = res.json()
    sess_id = sess_data["id"]
    assert sess_data["title"] == "SEC Audit Workspace"
    assert sess_data["system_prompt"] == "You are a senior financial auditor."
    assert sess_data["parameters"]["model"] == "llama3.1:8b"
    assert sess_data["parameters"]["temperature"] == 0.2
    assert sess_data["files"] == ["10k_nvda_2024.pdf", "10q_nvda_q3.pdf"]

    # 2. Get Session Detail
    detail_res = client.get(f"/api/v1/sessions/{sess_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["session"]["id"] == sess_id
    assert detail_data["messages"] == []

    # 3. Patch Session (update prompt and parameters)
    patch_payload = {
        "title": "Updated SEC Audit Workspace",
        "system_prompt": "You are a strict SEC compliance officer.",
        "parameters": {
            "model": "mistral:7b",
            "temperature": 0.1,
            "retrieval_mode": "agentic",
            "top_k": 8,
            "min_score_threshold": 0.25,
            "compactor_budget": 3072,
        },
    }
    patch_res = client.patch(f"/api/v1/sessions/{sess_id}", json=patch_payload)
    assert patch_res.status_code == 200
    patched_data = patch_res.json()
    assert patched_data["title"] == "Updated SEC Audit Workspace"
    assert patched_data["system_prompt"] == "You are a strict SEC compliance officer."
    assert patched_data["parameters"]["model"] == "mistral:7b"
    assert patched_data["parameters"]["temperature"] == 0.1
    assert patched_data["files"] == ["10k_nvda_2024.pdf", "10q_nvda_q3.pdf"]

    # 4. Attach Additional Files
    attach_res = client.post(f"/api/v1/sessions/{sess_id}/files", json={"files": ["cashflow_statement.pdf"]})
    assert attach_res.status_code == 200
    assert "cashflow_statement.pdf" in attach_res.json()["files"]
    assert len(attach_res.json()["files"]) == 3

    # 5. Detach File
    detach_res = client.delete(f"/api/v1/sessions/{sess_id}/files/10q_nvda_q3.pdf")
    assert detach_res.status_code == 200
    assert "10q_nvda_q3.pdf" not in detach_res.json()["files"]
    assert len(detach_res.json()["files"]) == 2

    # 6. Delete Session
    del_res = client.delete(f"/api/v1/sessions/{sess_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # Confirm 404 after deletion
    get_after = client.get(f"/api/v1/sessions/{sess_id}")
    assert get_after.status_code == 404


@patch("services.gateway.api.requests.post")
@patch("services.gateway.api.get_services")
def test_session_scoped_document_isolation(mock_get_services, mock_ollama_post):
    """Verifies that queries in Session A scoped to Doc A never query Doc B candidates."""
    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()
    mock_retrieval = MagicMock()

    candidate_a = Candidate(
        id="chunk_a1",
        doc_id="alpha_report.pdf",
        page=1,
        bbox=(10, 10, 200, 50),
        text="Alpha Corp Q4 net income $42M",
        rerank_score=0.92,
    )
    citation_a = Citation(
        doc_id="alpha_report.pdf",
        page=1,
        bbox=(10, 10, 200, 50),
        snippet="Alpha Corp Q4 net income $42M",
        formatted_badge="[alpha_report.pdf: p.1]",
    )

    candidate_b = Candidate(
        id="chunk_b1",
        doc_id="beta_report.pdf",
        page=1,
        bbox=(20, 20, 300, 80),
        text="Beta Corp Q4 net revenue $95M",
        rerank_score=0.89,
    )
    citation_b = Citation(
        doc_id="beta_report.pdf",
        page=1,
        bbox=(20, 20, 300, 80),
        snippet="Beta Corp Q4 net revenue $95M",
        formatted_badge="[beta_report.pdf: p.1]",
    )

    def fake_retrieve(query_obj):
        # Enforce doc_ids isolation
        if query_obj.doc_ids == ["alpha_report.pdf"]:
            return RetrieveResponse(
                query=query_obj.query_text,
                candidates=[candidate_a],
                citations=[citation_a],
                refused=False,
                top_score=0.92,
                duration_ms=10.0,
            )
        elif query_obj.doc_ids == ["beta_report.pdf"]:
            return RetrieveResponse(
                query=query_obj.query_text,
                candidates=[candidate_b],
                citations=[citation_b],
                refused=False,
                top_score=0.89,
                duration_ms=10.0,
            )
        return RetrieveResponse(
            query=query_obj.query_text,
            candidates=[candidate_a, candidate_b],
            citations=[citation_a, citation_b],
            refused=False,
            top_score=0.92,
            duration_ms=10.0,
        )

    mock_retrieval.retrieve.side_effect = fake_retrieve
    mock_get_services.return_value = (mock_ingestion, mock_indexing, mock_retrieval)

    # Mock Ollama generation
    mock_ollama_resp = MagicMock()
    mock_ollama_resp.json.return_value = {"response": "Verified answer based on isolated document."}
    mock_ollama_post.return_value = mock_ollama_resp

    # Create Session A (scoped to alpha_report.pdf)
    sess_a = session_manager.create_session(
        title="Session Alpha",
        files=["alpha_report.pdf"],
        parameters=SessionParameters(retrieval_mode="direct"),
    )

    # Create Session B (scoped to beta_report.pdf)
    sess_b = session_manager.create_session(
        title="Session Beta",
        files=["beta_report.pdf"],
        parameters=SessionParameters(retrieval_mode="direct"),
    )

    # Query in Session A
    chat_a_res = client.post(
        "/api/v1/chat",
        json={"query": "What was Q4 performance?", "session_id": sess_a.id, "stream": False},
    )
    assert chat_a_res.status_code == 200
    a_json = chat_a_res.json()
    assert len(a_json["citations"]) == 1
    assert a_json["citations"][0]["doc_id"] == "alpha_report.pdf"

    # Verify retrieval was called with doc_ids=["alpha_report.pdf"]
    call_args_a = mock_retrieval.retrieve.call_args[0][0]
    assert call_args_a.doc_ids == ["alpha_report.pdf"]

    # Query in Session B
    chat_b_res = client.post(
        "/api/v1/chat",
        json={"query": "What was Q4 performance?", "session_id": sess_b.id, "stream": False},
    )
    assert chat_b_res.status_code == 200
    b_json = chat_b_res.json()
    assert len(b_json["citations"]) == 1
    assert b_json["citations"][0]["doc_id"] == "beta_report.pdf"

    # Verify retrieval was called with doc_ids=["beta_report.pdf"]
    call_args_b = mock_retrieval.retrieve.call_args[0][0]
    assert call_args_b.doc_ids == ["beta_report.pdf"]


@patch("services.gateway.api.requests.post")
@patch("services.gateway.api.get_services")
def test_session_custom_system_persona_and_parameters(mock_get_services, mock_ollama_post):
    """Verifies that custom system persona and runtime parameters are passed to Ollama."""
    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()
    mock_retrieval = MagicMock()

    candidate = Candidate(
        id="chunk_1",
        doc_id="report.pdf",
        page=1,
        bbox=(0, 0, 100, 100),
        text="Revenue was $100M.",
        rerank_score=0.90,
    )
    citation = Citation(
        doc_id="report.pdf",
        page=1,
        bbox=(0, 0, 100, 100),
        snippet="Revenue was $100M.",
        formatted_badge="[report.pdf: p.1]",
    )
    mock_retrieval.retrieve.return_value = RetrieveResponse(
        query="What was revenue?",
        candidates=[candidate],
        citations=[citation],
        refused=False,
        top_score=0.90,
        duration_ms=5.0,
    )
    mock_get_services.return_value = (mock_ingestion, mock_indexing, mock_retrieval)

    mock_ollama_resp = MagicMock()
    mock_ollama_resp.json.return_value = {"response": "As a strict auditor, verified revenue is $100M."}
    mock_ollama_post.return_value = mock_ollama_resp

    # Create Session with custom persona & parameters
    sess = session_manager.create_session(
        title="Custom Persona Workspace",
        system_prompt="You are a strict SEC compliance examiner.",
        parameters=SessionParameters(
            model="mistral:7b",
            temperature=0.15,
            retrieval_mode="direct",
        ),
    )

    res = client.post(
        "/api/v1/chat",
        json={"query": "What was revenue?", "session_id": sess.id, "stream": False},
    )
    assert res.status_code == 200

    # Inspect the prompt passed to Ollama
    ollama_call = mock_ollama_post.call_args[1]["json"]
    assert ollama_call["model"] == "mistral:7b"
    assert ollama_call["options"]["temperature"] == 0.15
    assert "System Persona & Directives:\nYou are a strict SEC compliance examiner." in ollama_call["prompt"]


@patch("requests.post")
@patch("services.gateway.api.get_services")
def test_session_model_override_and_patch_persistence(mock_get_services, mock_ollama_post):
    """Verifies that changing a model on a session via PATCH preserves existing parameters and governs chat."""
    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()
    mock_retrieval = MagicMock()

    mock_retrieval.retrieve.return_value = RetrieveResponse(
        query="Test query",
        candidates=[],
        fused_candidates=[],
        reranked_candidates=[],
        citations=[],
        duration_ms=2.0,
    )
    mock_get_services.return_value = (mock_ingestion, mock_indexing, mock_retrieval)

    mock_ollama_resp = MagicMock()
    mock_ollama_resp.json.return_value = {"response": "Model test response."}
    mock_ollama_post.return_value = mock_ollama_resp

    # 1. Create session with custom temperature and initial model
    sess = session_manager.create_session(
        title="Model Testing Workspace",
        parameters=SessionParameters(
            model="llama3.2:3b",
            temperature=0.35,
            top_k=7,
        ),
    )
    assert sess.parameters.model == "llama3.2:3b"
    assert sess.parameters.temperature == 0.35
    assert sess.parameters.top_k == 7

    # 2. Patch only the model to qwen2.5:7b
    patch_res = client.patch(
        f"/api/v1/sessions/{sess.id}",
        json={"parameters": {"model": "qwen2.5:7b"}},
    )
    assert patch_res.status_code == 200
    patched_sess = patch_res.json()
    assert patched_sess["parameters"]["model"] == "qwen2.5:7b"
    # Verify other parameters were preserved
    assert patched_sess["parameters"]["temperature"] == 0.35
    assert patched_sess["parameters"]["top_k"] == 7

    # 3. Call /api/v1/chat without explicit model in request (uses default or relies on session model)
    chat_res = client.post(
        "/api/v1/chat",
        json={"query": "Test query", "session_id": sess.id, "stream": False},
    )
    assert chat_res.status_code == 200
    ollama_call = mock_ollama_post.call_args[1]["json"]
    assert ollama_call["model"] == "qwen2.5:7b"
    assert ollama_call["options"]["temperature"] == 0.35


def test_scoped_graph_metrics_ragops():
    """Validates that graph stats, observability metrics, and ragops support session_id scoping."""
    # 1. Create a session with specific files
    sess = session_manager.create_session(
        title="Scoped Test Workspace",
        files=["test_doc_alpha.pdf"],
    )

    # 2. Test graph stats endpoint with session_id
    res_graph = client.get(f"/api/v1/graph/stats?session_id={sess.id}")
    assert res_graph.status_code == 200
    graph_data = res_graph.json()
    assert "total_entities" in graph_data
    assert "total_relations" in graph_data

    # 3. Test observability metrics endpoint with session_id
    res_metrics = client.get(f"/api/v1/metrics?session_id={sess.id}")
    assert res_metrics.status_code == 200
    metrics_data = res_metrics.json()
    assert "uptime_seconds" in metrics_data
    assert "total_queries" in metrics_data

    # 4. Test RAGOps feedback summary endpoint with session_id
    res_summary = client.get(f"/api/v1/feedback/summary?session_id={sess.id}")
    assert res_summary.status_code == 200
    summary_data = res_summary.json()
    assert "total_feedback" in summary_data
    assert "satisfaction_rate_pct" in summary_data

    # 5. Test RAGOps dataset export endpoint with session_id
    res_dataset = client.get(f"/api/v1/ragops/dataset?session_id={sess.id}")
    assert res_dataset.status_code == 200
    assert isinstance(res_dataset.json(), list)


def test_neo4j_graph_store_operations_and_fallback():
    """Validates Neo4jGraphStore entity/relation registration, neighborhood queries, and stats."""
    from contracts.graph import Entity, Relation
    from services.graph.neo4j_store import Neo4jGraphStore

    store = Neo4jGraphStore(uri="bolt://127.0.0.1:7687", auto_load=False) if hasattr(Neo4jGraphStore, "auto_load") else Neo4jGraphStore()

    # 1. Add entities
    e1 = Entity(name="NVIDIA Corp", category="ORGANIZATION", doc_id="nvda_2024.pdf", chunk_id="c_1")
    e2 = Entity(name="Datacenter Revenue", category="METRIC", doc_id="nvda_2024.pdf", chunk_id="c_2")
    store.add_entity(e1)
    store.add_entity(e2)

    # 2. Add relation
    r1 = Relation(source="NVIDIA Corp", predicate="reports", target="Datacenter Revenue", doc_id="nvda_2024.pdf", chunk_id="c_1", weight=0.95)
    store.add_relation(r1)

    # 3. Query neighborhood
    neighborhood = store.get_neighborhood("NVIDIA Corp", max_depth=1)
    assert len(neighborhood.entities) >= 1
    names = [e.name for e in neighborhood.entities]
    assert "NVIDIA Corp" in names or "Datacenter Revenue" in names

    # 4. Scoped stats
    stats_scoped = store.get_stats(doc_ids=["nvda_2024.pdf"])
    assert stats_scoped["num_nodes"] >= 1
    assert stats_scoped["num_edges"] >= 1

    stats_empty = store.get_stats(doc_ids=["nonexistent.pdf"])
    assert stats_empty["num_nodes"] == 0

