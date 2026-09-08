"""Unit tests for the SOA FastAPI Gateway."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from contracts.retrieval import Candidate, Citation, RetrieveResponse
from services.gateway.api import app

client = TestClient(app)


def test_gateway_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert "qdrant" in data["services"]
    assert "redis" in data["services"]
    assert "ollama" in data["services"]


def test_gateway_root_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@patch("services.gateway.api.get_services")
def test_gateway_retrieve(mock_get_services):
    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()
    mock_retrieval = MagicMock()

    candidate = Candidate(
        id="chunk_1",
        doc_id="doc_1",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        text="Sample candidate text",
        rerank_score=0.88,
    )
    citation = Citation(
        doc_id="doc_1",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        snippet="Sample candidate text",
        formatted_badge="[doc_1: Page 1, (0.0, 0.0, 100.0, 100.0)]",
    )
    mock_retrieval.retrieve.return_value = RetrieveResponse(
        query="What is the architecture?",
        candidates=[candidate],
        citations=[citation],
        refused=False,
        top_score=0.88,
        duration_ms=12.5,
    )

    mock_get_services.return_value = (mock_ingestion, mock_indexing, mock_retrieval)

    payload = {
        "query_text": "What is the architecture?",
        "top_k": 5,
        "top_rerank": 2,
    }
    response = client.post("/api/v1/retrieve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "What is the architecture?"
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["id"] == "chunk_1"
    assert data["refused"] is False


@patch("services.gateway.api.requests.post")
@patch("services.gateway.api.get_services")
def test_gateway_chat_sync(mock_get_services, mock_requests_post):
    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()
    mock_retrieval = MagicMock()

    candidate = Candidate(
        id="chunk_1",
        doc_id="arch_doc",
        page=1,
        bbox=(50.0, 50.0, 200.0, 100.0),
        text="The system uses an RTX 3050 GPU with 6GB VRAM.",
        rerank_score=0.95,
    )
    citation = Citation(
        doc_id="arch_doc",
        page=1,
        bbox=(50.0, 50.0, 200.0, 100.0),
        snippet="The system uses an RTX 3050 GPU with 6GB VRAM.",
        formatted_badge="[arch_doc: Page 1, (50.0, 50.0, 200.0, 100.0)]",
    )
    mock_retrieval.retrieve.return_value = RetrieveResponse(
        query="What GPU is used?",
        candidates=[candidate],
        citations=[citation],
        refused=False,
        top_score=0.95,
        duration_ms=15.0,
    )
    mock_get_services.return_value = (mock_ingestion, mock_indexing, mock_retrieval)

    # Mock Ollama generation
    mock_ollama_resp = MagicMock()
    mock_ollama_resp.status_code = 200
    mock_ollama_resp.json.return_value = {"response": "The platform runs on an RTX 3050."}
    mock_requests_post.return_value = mock_ollama_resp

    chat_payload = {
        "query": "What GPU is used?",
        "top_k": 5,
        "top_rerank": 2,
        "stream": False,
        "model": "llama3.2:3b",
    }
    response = client.post("/api/v1/chat", json=chat_payload)
    assert response.status_code == 200
    data = response.json()
    assert "The platform runs on an RTX 3050." in data["answer"]
    assert "Verified Sources" in data["answer"]
    assert len(data["citations"]) == 1
    assert data["refused"] is False


def test_gateway_session_lifecycle():
    # 1. Create Session
    resp = client.post("/api/v1/sessions", json={"title": "Unit Test Session"})
    assert resp.status_code == 200
    sess = resp.json()
    sess_id = sess["id"]
    assert sess["title"] == "Unit Test Session"

    # 2. List Sessions
    resp_list = client.get("/api/v1/sessions")
    assert resp_list.status_code == 200
    sessions = resp_list.json()["sessions"]
    assert any(s["id"] == sess_id for s in sessions)

    # 3. Get Session Detail
    resp_detail = client.get(f"/api/v1/sessions/{sess_id}")
    assert resp_detail.status_code == 200
    data = resp_detail.json()
    assert data["session"]["id"] == sess_id
    assert isinstance(data["messages"], list)

    # 4. Delete Session
    resp_del = client.delete(f"/api/v1/sessions/{sess_id}")
    assert resp_del.status_code == 200
    assert resp_del.json()["deleted"] is True

    # 5. Verify 404
    resp_404 = client.get(f"/api/v1/sessions/{sess_id}")
    assert resp_404.status_code == 404


def test_gateway_metrics_endpoint():
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    metrics = resp.json()
    assert "uptime_seconds" in metrics
    assert "total_queries" in metrics
    assert "avg_retrieval_ms" in metrics
    assert "services" in metrics


def test_gateway_feedback_endpoints():
    # 1. Record thumbs up feedback
    req_up = {
        "session_id": "sess_gw_1",
        "query_text": "What is the dense latency?",
        "response_text": "The latency is 18.5 ms.",
        "citations": [],
        "rating": "thumbs_up",
        "comment": "Super fast",
    }
    resp_up = client.post("/api/v1/feedback", json=req_up)
    assert resp_up.status_code == 200
    data_up = resp_up.json()
    assert data_up["id"] is not None
    assert data_up["rating"] == "thumbs_up"

    # 2. Record thumbs down feedback with citations to mine hard negatives
    req_down = {
        "session_id": "sess_gw_2",
        "query_text": "What is the token budget?",
        "response_text": "The budget is 10000 tokens.",
        "citations": [
            {"doc_id": "doc_wrong", "text": "Wrong passage text with outdated token budget", "score": 0.35}
        ],
        "rating": "thumbs_down",
        "comment": "Hallucinated token budget",
    }
    resp_down = client.post("/api/v1/feedback", json=req_down)
    assert resp_down.status_code == 200
    data_down = resp_down.json()
    assert data_down["rating"] == "thumbs_down"

    # 3. Check feedback summary
    resp_sum = client.get("/api/v1/feedback/summary")
    assert resp_sum.status_code == 200
    summary = resp_sum.json()
    assert summary["total_feedback"] >= 2
    assert summary["thumbs_up"] >= 1
    assert summary["thumbs_down"] >= 1

    # 4. Check dataset export
    resp_dataset = client.get("/api/v1/ragops/dataset")
    assert resp_dataset.status_code == 200
    dataset = resp_dataset.json()
    assert isinstance(dataset, list)
    assert any(d.get("query") == "What is the token budget?" for d in dataset)


@patch("services.gateway.api.requests.post")
@patch("services.gateway.api.get_agentic_coordinator")
@patch("services.gateway.api.get_services")
def test_gateway_chat_agentic_sync(mock_get_services, mock_get_coordinator, mock_requests_post):
    from contracts.agent import AgentStep, CRAGAssessment, DecompositionPlan, SubQuery

    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()
    mock_retrieval = MagicMock()
    mock_get_services.return_value = (mock_ingestion, mock_indexing, mock_retrieval)

    candidate = Candidate(
        id="chunk_1",
        doc_id="arch_doc",
        page=1,
        bbox=(50.0, 50.0, 200.0, 100.0),
        text="The system uses FlashRank CPU reranking.",
        rerank_score=0.91,
    )
    citation = Citation(
        doc_id="arch_doc",
        page=1,
        bbox=(50.0, 50.0, 200.0, 100.0),
        snippet="The system uses FlashRank CPU reranking.",
        formatted_badge="[arch_doc: Page 1]",
    )
    step = AgentStep(
        step_type="decomposition",
        step_index=1,
        title="Query Decomposition",
        detail="Decomposed into 2 sub-queries",
    )
    plan = DecompositionPlan(
        original_query="Compare X and Y",
        is_multi_hop=True,
        sub_queries=[
            SubQuery(query_text="What is X?", rationale="Aspect 1", hop_index=0),
            SubQuery(query_text="What is Y?", rationale="Aspect 2", hop_index=1),
        ],
    )
    crag = CRAGAssessment(status="CONFIDENT", top_score=0.91)

    coordinator = MagicMock()
    coordinator.decomposer.is_multi_hop_candidate.return_value = True
    coordinator.run_plan.return_value = ([candidate], [citation], [step], plan, crag, False)
    coordinator.build_agentic_prompt.return_value = "Comparative prompt"
    mock_get_coordinator.return_value = coordinator

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "Comparative analysis: X is dense, Y is sparse."}
    mock_requests_post.return_value = mock_resp

    payload = {
        "query": "Compare X and Y",
        "stream": False,
        "mode": "agentic",
    }
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_agentic"] is True
    assert len(data["agent_steps"]) == 1
    assert len(data["sub_queries"]) == 2
    assert "Comparative analysis" in data["raw_answer"]


def test_gateway_graph_extract():
    payload = {
        "text": "The NVIDIA RTX 3050 has 6GB VRAM and runs on CPU with FlashRank.",
        "doc_id": "test_doc",
        "chunk_id": "c1",
    }
    response = client.post("/api/v1/graph/extract", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "entities" in data
    assert "relations" in data
    entity_names = [e["name"] for e in data["entities"]]
    assert "NVIDIA RTX 3050" in entity_names


def test_gateway_graph_stats():
    response = client.get("/api/v1/graph/stats")
    assert response.status_code == 200
    data = response.json()
    assert "num_nodes" in data
    assert "num_edges" in data
    assert "entity_categories" in data


def test_gateway_compact():
    payload = {
        "query": "What is the dense latency of RTX 3050?",
        "candidates": [
            {
                "id": "c1",
                "doc_id": "doc1",
                "page": 1,
                "bbox": [0.0, 0.0, 100.0, 100.0],
                "text": "The RTX 3050 achieves 18.5 ms dense latency. Filler clause about weather.",
                "rerank_score": 0.9,
            }
        ],
        "budget_tokens": 500,
    }
    response = client.post("/api/v1/compact", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "chunks" in data
    assert data["total_compressed_tokens"] > 0
    assert len(data["chunks"]) == 1
    assert data["chunks"][0]["doc_id"] == "doc1"


def test_gateway_session_scoped_lifecycle():
    # 1. Create Session with Scoped Parameters & Files
    create_payload = {
        "title": "Quantum Research",
        "system_prompt": "You are a quantum computing specialist.",
        "parameters": {
            "model": "qwen2.5:7b",
            "temperature": 0.3,
            "retrieval_mode": "agentic",
            "top_k": 10,
            "compactor_budget": 2048,
        },
        "files": ["quantum_gates.pdf"],
    }
    res = client.post("/api/v1/sessions", json=create_payload)
    assert res.status_code == 200
    session_data = res.json()
    sess_id = session_data["id"]
    assert session_data["title"] == "Quantum Research"
    assert session_data["system_prompt"] == "You are a quantum computing specialist."
    assert session_data["parameters"]["model"] == "qwen2.5:7b"
    assert session_data["parameters"]["temperature"] == 0.3
    assert session_data["files"] == ["quantum_gates.pdf"]

    # 2. Attach Files
    attach_res = client.post(f"/api/v1/sessions/{sess_id}/files", json={"files": ["qubits.pdf"]})
    assert attach_res.status_code == 200
    assert "qubits.pdf" in attach_res.json()["files"]
    assert "quantum_gates.pdf" in attach_res.json()["files"]

    # 3. Detach File
    detach_res = client.delete(f"/api/v1/sessions/{sess_id}/files/quantum_gates.pdf")
    assert detach_res.status_code == 200
    assert "quantum_gates.pdf" not in detach_res.json()["files"]
    assert "qubits.pdf" in detach_res.json()["files"]

    # 4. Patch Session Parameters
    patch_res = client.patch(
        f"/api/v1/sessions/{sess_id}",
        json={"title": "Supercomputing", "parameters": {"temperature": 0.1}},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Supercomputing"
    assert patch_res.json()["parameters"]["temperature"] == 0.1

    # 5. Clean up
    del_res = client.delete(f"/api/v1/sessions/{sess_id}")
    assert del_res.status_code == 200


@patch("services.gateway.api.requests.post")
@patch("services.gateway.api.get_services")
def test_gateway_chat_auto_session(mock_get_services, mock_requests_post):
    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()
    mock_retrieval = MagicMock()

    candidate = Candidate(
        id="c1",
        doc_id="d1",
        page=1,
        bbox=(0.0, 0.0, 50.0, 50.0),
        text="Dense chunk",
        rerank_score=0.95,
    )
    citation = Citation(
        doc_id="d1",
        page=1,
        bbox=(0.0, 0.0, 50.0, 50.0),
        snippet="Dense chunk",
        formatted_badge="[d1: Page 1, (0.0, 0.0, 50.0, 50.0)]",
    )
    mock_retrieval.retrieve.return_value = RetrieveResponse(
        query="Auto-session query",
        candidates=[candidate],
        citations=[citation],
        refused=False,
        top_score=0.95,
        duration_ms=10.0,
    )
    mock_get_services.return_value = (mock_ingestion, mock_indexing, mock_retrieval)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "Auto-session response text."}
    mock_requests_post.return_value = mock_resp

    # Request without session_id - should auto-create session and return session_id
    payload = {
        "query": "Auto-session query",
        "stream": False,
        "mode": "direct",
    }
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["session_id"].startswith("sess_")




