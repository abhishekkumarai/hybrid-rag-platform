"""Background ingest jobs (IRA-60): parse -> index -> attach runs server-side and is pollable."""

import fitz
import pytest
from fastapi.testclient import TestClient

from contracts.document import IngestResponse
from services.gateway import api
from services.ingestion import jobs as jobs_mod
from services.ingestion.jobs import IngestJobRunner, IngestJobStore
from tests.unit.conftest import TEST_USER

client = TestClient(api.app)


class _InlineRunner(IngestJobRunner):
    """Runs a job on the calling thread so a test can assert on its final state."""

    def submit(self, job, work):
        self._run(job, work)


@pytest.fixture(autouse=True)
def inline_jobs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    store = IngestJobStore(lambda: None)
    monkeypatch.setattr(api, "ingest_jobs", store)
    monkeypatch.setattr(api, "ingest_runner", _InlineRunner(store))
    indexed = []
    monkeypatch.setattr(api, "_index_owned", lambda doc_id, blocks, user: indexed.append((doc_id, len(blocks))))
    return indexed


def _pdf(text: str = "The Falcon cluster has 48 GB of memory.") -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), text, fontsize=12)
    return doc.tobytes()


def _upload(session_id: str, name: str = "falcon.pdf", pdf: bytes | None = None):
    return client.post(
        "/api/v1/ingest/jobs",
        data={"session_id": session_id},
        files={"file": (name, pdf if pdf is not None else _pdf(), "application/pdf")},
    )


def test_upload_job_parses_indexes_and_attaches(make_project, inline_jobs):
    project = make_project()
    r = _upload(project.id)
    assert r.status_code == 202, r.text
    assert "user_id" not in r.json() and "runner_id" not in r.json()

    (job,) = client.get("/api/v1/ingest/jobs", params={"session_id": project.id}).json()["jobs"]
    assert job["status"] == "done" and job["stage"] == "Ready" and job["source"] == "falcon.pdf"
    assert job["doc_id"].startswith("falcon_") and job["blocks"]
    assert inline_jobs == [(job["doc_id"], job["blocks"])]
    assert job["doc_id"] in api.session_manager.get_session(project.id)[0].files


def test_parse_error_fails_the_job_without_attaching(make_project, monkeypatch):
    project = make_project()
    failed = IngestResponse.model_construct(doc_id="x", error="no extractable text", blocks=[])
    monkeypatch.setattr(api, "_parse_owned_upload", lambda *a, **k: failed)
    assert _upload(project.id).status_code == 202

    (job,) = client.get("/api/v1/ingest/jobs").json()["jobs"]
    assert job["status"] == "failed" and job["error"] == "no extractable text"
    assert api.session_manager.get_session(project.id)[0].files == []


def test_url_job_fetches_server_side(make_project, monkeypatch):
    project = make_project()
    monkeypatch.setattr(api, "url_to_pdf", lambda url, **k: ("example_com_falcon.pdf", _pdf()))
    r = client.post("/api/v1/ingest/jobs/url", json={"url": "https://example.com/falcon", "session_id": project.id})
    assert r.status_code == 202, r.text
    (job,) = client.get("/api/v1/ingest/jobs").json()["jobs"]
    assert job["kind"] == "url" and job["status"] == "done"
    assert job["doc_id"] in api.session_manager.get_session(project.id)[0].files


def test_unfetchable_url_fails_the_job(make_project):
    project = make_project()
    client.post("/api/v1/ingest/jobs/url", json={"url": "http://127.0.0.1:6333/", "session_id": project.id})
    (job,) = client.get("/api/v1/ingest/jobs").json()["jobs"]
    assert job["status"] == "failed" and "publicly reachable" in job["error"]


def test_someone_elses_project_is_a_404():
    assert _upload("sess_nope").status_code == 404


def test_listing_is_scoped_to_project_and_user(make_project):
    a, b = make_project(), make_project()
    _upload(a.id, "a.pdf", _pdf("alpha document text"))
    _upload(b.id, "b.pdf", _pdf("bravo document text"))
    assert [j["source"] for j in client.get("/api/v1/ingest/jobs", params={"session_id": a.id}).json()["jobs"]] == ["a.pdf"]
    assert len(client.get("/api/v1/ingest/jobs").json()["jobs"]) == 2

    api.ingest_jobs.create(user_id="usr_other", session_id=a.id, kind="file", source="theirs.pdf")
    assert all(j["source"] != "theirs.pdf" for j in client.get("/api/v1/ingest/jobs").json()["jobs"])


def test_dismiss_only_finished_jobs_of_the_caller(make_project):
    project = make_project()
    _upload(project.id)
    (job,) = client.get("/api/v1/ingest/jobs").json()["jobs"]
    running = api.ingest_jobs.create(user_id=TEST_USER.id, session_id=project.id, kind="file", source="busy.pdf")
    foreign = api.ingest_jobs.create(user_id="usr_other", session_id=project.id, kind="file", source="x.pdf")

    assert client.delete(f"/api/v1/ingest/jobs/{running.id}").status_code == 409
    assert client.delete(f"/api/v1/ingest/jobs/{foreign.id}").status_code == 404
    assert client.delete(f"/api/v1/ingest/jobs/{job['id']}").json() == {"deleted": True}
    assert job["id"] not in [j["id"] for j in client.get("/api/v1/ingest/jobs").json()["jobs"]]


def test_a_job_from_a_dead_gateway_process_is_reported_failed():
    store = IngestJobStore(lambda: None)
    job = store.create(user_id="u", session_id="s", kind="file", source="big.pdf")
    store.update(job.id, status="running", runner_id="a-previous-process")

    (listed,) = store.list_for("u")
    assert listed.status == "failed" and "restarted" in listed.error
    assert store.get(job.id).status == "failed"


def test_a_live_job_is_left_alone():
    store = IngestJobStore(lambda: None)
    job = store.create(user_id="u", session_id="s", kind="file", source="big.pdf")
    assert job.runner_id == jobs_mod.RUNNER_ID
    store.update(job.id, status="running", stage="Parsing")
    assert store.list_for("u")[0].status == "running"
