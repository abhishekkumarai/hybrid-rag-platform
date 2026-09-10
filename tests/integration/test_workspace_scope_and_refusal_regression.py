"""Integration and regression test suite for:
1. Workspace-scoped document ID resolution (fixing false-positive refusal on attached documents).
2. Per-workspace retrieval mode local scoping and persistence.
3. Per-workspace and global embedding/ingestion route scoping and overrides.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from contracts.document import IngestRequest
from contracts.retrieval import Candidate, Citation, RetrieveResponse, SearchQuery
from services.gateway.api import app
from services.indexing.service import IndexingService
from services.ingestion.service import IngestionService
from services.retrieval.service import RetrievalService


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "system_architecture_spec.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "Enterprise System Architecture Overview\n"
        "The distributed platform relies on an NVIDIA RTX 3050 GPU with 6GB VRAM.\n"
        "PostgreSQL operates on port 5432 and Qdrant vector database serves on port 6333.\n"
        "FlashRank cross-encoder reranks top-20 candidates down to top-6 with a minimum refusal threshold of 0.15.",
        fontsize=12,
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_workspace_doc_id_mismatch_regression(sample_pdf: Path, tmp_path: Path):
    """Regression test: Ensures attached workspace documents (e.g. system_architecture_spec.pdf)

    match chunks indexed with hashed doc_ids (e.g. system_architecture_spec_81b5f5cd) and do NOT falsely refuse.
    """
    ingestion = IngestionService()
    indexing = IndexingService(in_memory=True, bm25_dir=tmp_path / "bm25")
    retrieval = RetrievalService(qdrant_store=indexing.qdrant, bm25_store=indexing.bm25)

    # Ingest document: creates hashed doc_id
    ingest_res = ingestion.parse(IngestRequest(file_path=str(sample_pdf)))
    hashed_doc_id = ingest_res.doc_id
    assert hashed_doc_id.startswith("system_architecture_spec_")

    # Index blocks
    index_res = indexing.chunk_and_index(doc_id=hashed_doc_id, blocks=ingest_res.blocks)
    assert index_res.indexed_count >= 1

    query_text = "What GPU and VRAM are used in the platform?"

    # 1. Scoped query using raw filename (as stored in session workspace files)
    res_filename = retrieval.retrieve(
        SearchQuery(query_text=query_text, top_k=10, top_rerank=3, doc_ids=["system_architecture_spec.pdf"])
    )
    assert not res_filename.refused, "Scoped retrieval with filename must not be refused"
    assert len(res_filename.candidates) >= 1
    assert res_filename.candidates[0].doc_id == hashed_doc_id

    # 2. Scoped query using stem
    res_stem = retrieval.retrieve(
        SearchQuery(query_text=query_text, top_k=10, top_rerank=3, doc_ids=["system_architecture_spec"])
    )
    assert not res_stem.refused
    assert len(res_stem.candidates) >= 1

    # 3. Scoped query using exact hashed doc_id
    res_exact = retrieval.retrieve(
        SearchQuery(query_text=query_text, top_k=10, top_rerank=3, doc_ids=[hashed_doc_id])
    )
    assert not res_exact.refused
    assert len(res_exact.candidates) >= 1

    # 4. Scoped query with an unrelated file -> Must isolate and refuse (0 candidates)
    res_isolated = retrieval.retrieve(
        SearchQuery(query_text=query_text, top_k=10, top_rerank=3, doc_ids=["other_report.pdf"])
    )
    assert res_isolated.refused
    assert len(res_isolated.candidates) == 0


def test_per_workspace_retrieval_mode_scoping():
    """Verifies that retrieval mode is locally scoped per workspace session,

    persisted via PATCH, and loaded correctly across different sessions.
    """
    client = TestClient(app)

    # 1. Create Workspace A with 'direct' mode
    res_a = client.post(
        "/api/v1/sessions",
        json={
            "title": "Direct Mode Workspace",
            "parameters": {"retrieval_mode": "direct", "model": "llama3.2:3b"},
        },
    )
    assert res_a.status_code == 200
    sess_a_id = res_a.json()["id"]
    assert res_a.json()["parameters"]["retrieval_mode"] == "direct"

    # 2. Create Workspace B with 'graph' mode
    res_b = client.post(
        "/api/v1/sessions",
        json={
            "title": "Graph Mode Workspace",
            "parameters": {"retrieval_mode": "graph", "model": "mistral:7b"},
        },
    )
    assert res_b.status_code == 200
    sess_b_id = res_b.json()["id"]
    assert res_b.json()["parameters"]["retrieval_mode"] == "graph"

    # 3. Create Workspace C with default ('auto') mode
    res_c = client.post(
        "/api/v1/sessions",
        json={"title": "Auto Mode Workspace"},
    )
    assert res_c.status_code == 200
    sess_c_id = res_c.json()["id"]
    assert res_c.json()["parameters"]["retrieval_mode"] == "auto"

    # 4. Update Workspace C to 'agentic' mode via PATCH
    patch_c = client.patch(
        f"/api/v1/sessions/{sess_c_id}",
        json={"parameters": {"retrieval_mode": "agentic"}},
    )
    assert patch_c.status_code == 200
    assert patch_c.json()["parameters"]["retrieval_mode"] == "agentic"

    # 5. Fetch all three and verify independence / local scoping
    get_a = client.get(f"/api/v1/sessions/{sess_a_id}").json()["session"]
    get_b = client.get(f"/api/v1/sessions/{sess_b_id}").json()["session"]
    get_c = client.get(f"/api/v1/sessions/{sess_c_id}").json()["session"]

    assert get_a["parameters"]["retrieval_mode"] == "direct"
    assert get_b["parameters"]["retrieval_mode"] == "graph"
    assert get_c["parameters"]["retrieval_mode"] == "agentic"


def test_per_workspace_embedding_route_scoping():
    """Verifies that document embedding / ingestion route is scoped per workspace and can be set via session parameters."""
    client = TestClient(app)

    # 1. Create Workspace with 'layout' route
    res = client.post(
        "/api/v1/sessions",
        json={
            "title": "Layout Doc Workspace",
            "parameters": {"embedding_route": "layout"},
        },
    )
    assert res.status_code == 200
    sess_id = res.json()["id"]
    assert res.json()["parameters"]["embedding_route"] == "layout"

    # 2. Update to 'ocr' via PATCH
    patch_res = client.patch(
        f"/api/v1/sessions/{sess_id}",
        json={"parameters": {"embedding_route": "ocr"}},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["parameters"]["embedding_route"] == "ocr"

    # 3. Verify persistence on GET
    get_res = client.get(f"/api/v1/sessions/{sess_id}").json()["session"]
    assert get_res["parameters"]["embedding_route"] == "ocr"


@patch("services.gateway.api.requests.post")
@patch("services.gateway.api.get_services")
def test_chat_uses_workspace_retrieval_mode(mock_get_services, mock_ollama_post):
    """Verifies that calling /api/v1/chat with default mode='auto' inherits the workspace's configured retrieval mode."""
    client = TestClient(app)

    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()
    mock_retrieval = MagicMock()

    candidate = Candidate(
        id="c1",
        doc_id="system_architecture_spec.pdf",
        page=1,
        bbox=(0, 0, 100, 100),
        text="Verified architecture text",
        rerank_score=0.85,
    )
    citation = Citation(
        doc_id="system_architecture_spec.pdf",
        page=1,
        bbox=(0, 0, 100, 100),
        snippet="Verified architecture text",
        formatted_badge="[p.1]",
    )
    mock_retrieval.retrieve.return_value = RetrieveResponse(
        query="What is the architecture?",
        candidates=[candidate],
        citations=[citation],
        refused=False,
        top_score=0.85,
        duration_ms=10.0,
    )
    mock_get_services.return_value = (mock_ingestion, mock_indexing, mock_retrieval)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "The architecture is verified."}
    mock_ollama_post.return_value = mock_resp

    # Create workspace with direct mode
    sess = client.post(
        "/api/v1/sessions",
        json={"title": "Direct Workspace", "parameters": {"retrieval_mode": "direct"}},
    ).json()

    # Post query without specifying mode
    chat_res = client.post(
        "/api/v1/chat",
        json={"query": "What is the architecture?", "session_id": sess["id"], "stream": False},
    )
    assert chat_res.status_code == 200
    assert not chat_res.json()["refused"]
    # Verify retrieval.retrieve was called (direct path)
    assert mock_retrieval.retrieve.called
