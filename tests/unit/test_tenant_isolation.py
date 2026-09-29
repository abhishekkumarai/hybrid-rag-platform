"""Per-user isolation of projects, documents and derived data (IRA-34).

Two users, Ana and Ben, share one gateway (and one set of indexes). Nothing Ana owns may be read,
changed, searched or even confirmed to exist by Ben."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts.graph import Entity, GraphNeighborhood
from contracts.identity import User
from contracts.retrieval import RetrieveResponse
from services.gateway import api
from services.gateway.chat_pipeline import NO_DOCUMENTS_REFUSAL
from services.graph.traversal import GraphTraverser
from services.identity.access import resolve_scope
from tests.unit.conftest import own_documents

client = TestClient(api.app)

ANA = User(id="usr_ana", email="ana@example.com")
BEN = User(id="usr_ben", email="ben@example.com")
ANA_DOC = "report_1a2b3c4d"


@pytest.fixture(autouse=True)
def _two_users(identity):
    identity.users[ANA.id] = ANA
    identity.users[BEN.id] = BEN
    identity.create_workspace(name="Ana's", owner_id=ANA.id)
    identity.create_workspace(name="Ben's", owner_id=BEN.id)
    own_documents(identity, ANA_DOC, user=ANA)


def as_user(user: User | None) -> None:
    api.app.dependency_overrides[api.optional_user] = lambda: user


@pytest.fixture
def ana_project():
    as_user(ANA)
    sid = client.post("/api/v1/sessions", json={"title": "Ana's", "files": [ANA_DOC]}).json()["id"]
    as_user(BEN)
    return sid


def test_other_users_project_is_invisible(ana_project):
    sid = ana_project
    assert all(s["id"] != sid for s in client.get("/api/v1/sessions").json()["sessions"])
    assert client.get(f"/api/v1/sessions/{sid}").status_code == 404
    assert client.patch(f"/api/v1/sessions/{sid}", json={"title": "mine now"}).status_code == 404
    assert client.post(f"/api/v1/sessions/{sid}/files", json={"files": []}).status_code == 404
    assert client.delete(f"/api/v1/sessions/{sid}/files/{ANA_DOC}").status_code == 404
    assert client.get(f"/api/v1/sessions/{sid}/eval/summary").status_code == 404
    assert client.get(f"/api/v1/sessions/{sid}/shares").status_code == 404
    assert client.post(f"/api/v1/sessions/{sid}/shares").status_code == 404
    assert client.get(f"/api/v1/metrics?session_id={sid}").status_code == 404
    assert client.get(f"/api/v1/feedback/summary?session_id={sid}").status_code == 404
    assert client.get(f"/api/v1/graph/stats?session_id={sid}").status_code == 404
    assert client.delete(f"/api/v1/sessions/{sid}").json() == {"deleted": False}
    chat = client.post("/api/v1/chat", json={"query": "q", "session_id": sid, "stream": False})
    assert chat.status_code == 404

    as_user(ANA)
    detail = client.get(f"/api/v1/sessions/{sid}")
    assert detail.status_code == 200 and detail.json()["session"]["title"] == "Ana's"


def test_feedback_must_name_an_owned_project(ana_project):
    body = {"query_text": "q", "response_text": "a", "rating": "thumbs_up"}
    assert client.post("/api/v1/feedback", json=body).status_code == 422
    assert client.post("/api/v1/feedback", json={**body, "session_id": ana_project}).status_code == 404


def test_cannot_attach_someone_elses_document():
    as_user(BEN)
    sid = client.post("/api/v1/sessions", json={}).json()["id"]
    # By exact id, and by the filename that loosely matches Ana's `report_<hash>` doc
    for name in (ANA_DOC, "report.pdf", "report"):
        r = client.post(f"/api/v1/sessions/{sid}/files", json={"files": [name]})
        assert r.status_code == 404, name
    assert client.post("/api/v1/sessions", json={"files": [ANA_DOC]}).status_code == 404


def test_identical_upload_gives_both_users_access(identity):
    own_documents(identity, ANA_DOC, user=BEN)
    as_user(BEN)
    r = client.post("/api/v1/sessions", json={"files": ["report.pdf"]})
    assert r.status_code == 200 and r.json()["files"] == [ANA_DOC]


def test_resolve_scope_only_matches_within_the_accessible_set():
    accessible = {"report_1a2b3c4d", "notes_99999999"}
    assert resolve_scope(["report.pdf", "notes_99999999", "other.pdf"], accessible) == [
        "report_1a2b3c4d", "notes_99999999",
    ]
    assert resolve_scope(["report.pdf"], {"notes_99999999"}) == []


@patch("services.gateway.api.get_services")
def test_project_without_readable_documents_refuses_without_searching(mock_services):
    retrieval = MagicMock()
    mock_services.return_value = (MagicMock(), MagicMock(), retrieval)
    as_user(BEN)
    data = client.post("/api/v1/chat", json={"query": "What is in the report?", "stream": False}).json()
    assert data["refused"] is True and NO_DOCUMENTS_REFUSAL in data["answer"]
    retrieval.retrieve.assert_not_called()
    retrieval.retrieve_with_graph.assert_not_called()


@patch("services.gateway.api.get_services")
def test_retrieve_is_scoped_to_readable_documents(mock_services, identity):
    retrieval = MagicMock()
    retrieval.retrieve.return_value = RetrieveResponse(query="q", candidates=[], citations=[], duration_ms=1.0)
    mock_services.return_value = (MagicMock(), MagicMock(), retrieval)

    as_user(BEN)
    empty = client.post("/api/v1/retrieve", json={"query_text": "q"}).json()
    assert empty["refused"] is True
    retrieval.retrieve.assert_not_called()
    client.post("/api/v1/retrieve", json={"query_text": "q", "doc_ids": [ANA_DOC]})
    retrieval.retrieve.assert_not_called()

    own_documents(identity, "ben_notes_12345678", user=BEN)
    client.post("/api/v1/retrieve", json={"query_text": "q", "doc_ids": [ANA_DOC, "ben_notes_12345678"]})
    assert retrieval.retrieve.call_args[0][0].doc_ids == ["ben_notes_12345678"]


def test_documents_list_and_file_endpoints_are_per_user():
    as_user(BEN)
    uploads = [d for d in client.get("/api/v1/documents").json()["documents"] if not d["is_web"]]
    assert uploads == []
    assert client.get(f"/api/v1/preview?doc_id={ANA_DOC}").status_code == 404
    assert client.get(f"/api/v1/documents/{ANA_DOC}/raw").status_code == 404
    as_user(ANA)
    docs = client.get("/api/v1/documents").json()["documents"]
    assert [d["doc_id"] for d in docs if not d["is_web"]] == [ANA_DOC]


@patch("services.gateway.api.get_services")
def test_only_an_owner_indexes_and_only_the_first_owner_reindexes(mock_services, identity):
    indexing = MagicMock()
    indexing.bm25.corpus_chunks = [{"doc_id": ANA_DOC}, {"doc_id": ANA_DOC}]
    mock_services.return_value = (MagicMock(), indexing, MagicMock())
    body = {"doc_id": ANA_DOC, "blocks": []}

    as_user(BEN)
    assert client.post("/api/v1/index", json=body).status_code == 404

    own_documents(identity, ANA_DOC, user=BEN)  # Ben uploads identical content later
    r = client.post("/api/v1/index", json=body)
    assert r.status_code == 200 and r.json()["indexed_count"] == 2
    indexing.chunk_and_index.assert_not_called()


def test_unscoped_metrics_cover_only_the_callers_projects(ana_project):
    from contracts.metrics import QueryTelemetry

    ben_sid = client.post("/api/v1/sessions", json={"title": "Ben's"}).json()["id"]
    tracker = api.telemetry_tracker
    ana_q = QueryTelemetry(query_id="q_ana", session_id=ana_project, query_text="ana secret")
    ben_q = QueryTelemetry(query_id="q_ben", session_id=ben_sid, query_text="ben question")
    tracker.record_query(ana_q)
    tracker.record_query(ben_q)
    try:
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == 200
        texts = [t["query_text"] for t in resp.json()["recent_telemetry"]]
        assert "ben question" in texts
        assert "ana secret" not in texts
        assert resp.json()["total_queries"] == 1
    finally:
        tracker._history.remove(ana_q)
        tracker._history.remove(ben_q)


def test_unscoped_ragops_views_cover_only_the_callers_projects(ana_project):
    ben_sid = client.post("/api/v1/sessions", json={"title": "Ben's"}).json()["id"]
    with patch.object(api, "ragops_store") as store:
        store.get_summary.return_value = api.RAGOpsSummary()
        store.export_training_dataset.return_value = []
        assert client.get("/api/v1/feedback/summary").status_code == 200
        assert client.get("/api/v1/ragops/dataset").status_code == 200
    assert store.get_summary.call_args.kwargs["session_ids"] == {ben_sid}
    assert store.export_training_dataset.call_args.kwargs["session_ids"] == {ben_sid}
    assert ana_project not in store.get_summary.call_args.kwargs["session_ids"]


def test_graph_traversal_hides_entities_from_out_of_scope_documents():
    import networkx as nx

    store = MagicMock()
    store.graph = nx.MultiDiGraph()
    store.find_entities_in_text.return_value = [
        Entity(name="Project Falcon", doc_id=ANA_DOC), Entity(name="Budget", doc_id="ben_notes_12345678"),
    ]
    store.get_neighborhood.return_value = GraphNeighborhood(center_entities=["x"])
    res = GraphTraverser(store).query_graph("Project Falcon budget", doc_ids=["ben_notes_12345678"])
    assert [e.name for e in res.matched_entities] == ["Budget"]
