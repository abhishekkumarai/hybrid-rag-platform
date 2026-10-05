"""Unit tests for the Temporal-backed document-ingestion scheduling module.

Activities are tested through `temporalio.testing.ActivityEnvironment`, which runs the activity
function directly against a mocked activity context — no Temporal server needed. Workflow
orchestration itself (DocumentIngestWorkflow/DirectoryScanWorkflow) isn't exercised end-to-end here
since that requires `WorkflowEnvironment.start_time_skipping()`, which downloads a test-server
binary; `services.scheduling.client` (the gateway-facing admin surface) is tested with a mocked
Temporal `Client` instead, matching this suite's existing style of mocking Redis in
`test_session_manager.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.client import WorkflowExecutionStatus
from temporalio.testing import ActivityEnvironment

from contracts.chunk import IndexResponse
from contracts.document import Block, DocumentProfile, IngestResponse
from services.scheduling import client as scheduling_client
from services.scheduling.activities import IngestionActivities, compute_file_sha256
from services.scheduling.workflows import ingest_workflow_id


def _sample_ingest_response(doc_id: str = "test_doc") -> IngestResponse:
    return IngestResponse(
        doc_id=doc_id,
        file_path="sample.pdf",
        blocks=[
            Block(
                id="b1", doc_id=doc_id, page=1, bbox=(0.0, 0.0, 10.0, 10.0),
                text="Hello world", type="text", order=0,
            )
        ],
        profile=DocumentProfile(
            route="fast_text", page_count=1, sample_pages=[1], text_coverage=0.9,
            chars_per_page=100.0, image_ratio=0.0, columns=1, table_score=0.0, reason="clean",
        ),
        duration_ms=10.0,
    )


def test_ingest_workflow_id_uses_full_hash():
    assert ingest_workflow_id("abc123") == "ingest-abc123"


def test_scan_directory_discovers_and_dedupes(tmp_path):
    watch_dir = tmp_path / "documents"
    watch_dir.mkdir()
    registry_file = tmp_path / "registry.json"

    activities = IngestionActivities.__new__(IngestionActivities)
    activities.watch_dir = watch_dir
    activities.registry_file = registry_file
    activities.ingestion = MagicMock()
    activities.indexing = MagicMock()

    env = ActivityEnvironment()

    # Nothing yet.
    assert env.run(activities.scan_directory) == []

    doc1 = watch_dir / "doc1.txt"
    doc1.write_text("Document 1", encoding="utf-8")
    doc2 = watch_dir / "doc2.txt"
    doc2.write_text("Document 2", encoding="utf-8")

    discovered = env.run(activities.scan_directory)
    assert {d["file_path"] for d in discovered} == {str(doc1), str(doc2)}
    assert {d["file_hash"] for d in discovered} == {
        compute_file_sha256(doc1), compute_file_sha256(doc2),
    }

    # Re-scanning finds nothing new (claimed in the registry on the first scan).
    assert env.run(activities.scan_directory) == []

    # A failed-but-still-dispatched file is never silently retried (see activities.py docstring).
    doc3 = watch_dir / "doc3.txt"
    doc3.write_text("Document 3", encoding="utf-8")
    discovered_again = env.run(activities.scan_directory)
    assert len(discovered_again) == 1
    assert discovered_again[0]["file_path"] == str(doc3)


def test_ingest_document_activity_parses_via_ingestion_service():
    activities = IngestionActivities.__new__(IngestionActivities)
    activities.ingestion = MagicMock()
    activities.ingestion.parse.return_value = _sample_ingest_response()
    activities.indexing = MagicMock()

    env = ActivityEnvironment()
    result = env.run(activities.ingest_document, "sample.pdf")

    assert result["doc_id"] == "test_doc"
    assert len(result["blocks"]) == 1
    activities.ingestion.parse.assert_called_once()


def test_ingest_document_activity_raises_on_parse_error():
    activities = IngestionActivities.__new__(IngestionActivities)
    activities.ingestion = MagicMock()
    activities.ingestion.parse.return_value = IngestResponse(
        doc_id="x", file_path="bad.pdf",
        profile=DocumentProfile(
            route="fast_text", page_count=0, sample_pages=[], text_coverage=0.0,
            chars_per_page=0.0, image_ratio=0.0, columns=1, table_score=0.0, reason="",
        ),
        duration_ms=1.0, error="Corrupt PDF header",
    )
    activities.indexing = MagicMock()

    env = ActivityEnvironment()
    with pytest.raises(RuntimeError, match="Corrupt PDF header"):
        env.run(activities.ingest_document, "bad.pdf")


def test_index_document_activity_chunks_via_indexing_service():
    activities = IngestionActivities.__new__(IngestionActivities)
    activities.ingestion = MagicMock()
    activities.indexing = MagicMock()
    activities.indexing.chunk_and_index.return_value = IndexResponse(
        doc_id="test_doc", indexed_count=1, duration_ms=5.0,
    )

    raw_blocks = [_sample_ingest_response().blocks[0].model_dump(mode="json")]
    env = ActivityEnvironment()
    result = env.run(activities.index_document, "test_doc", raw_blocks)

    assert result["doc_id"] == "test_doc"
    assert result["indexed_count"] == 1
    called_blocks = activities.indexing.chunk_and_index.call_args.kwargs["blocks"]
    assert called_blocks[0].id == "b1"


@pytest.mark.asyncio
async def test_queue_stats_counts_running_and_failed_workflows():
    mock_client = MagicMock()

    async def fake_list(query: str):
        count = 2 if "Running" in query else 1
        for _ in range(count):
            yield MagicMock()

    mock_client.list_workflows = lambda query: fake_list(query)

    with patch.object(scheduling_client, "get_temporal_client", AsyncMock(return_value=mock_client)):
        stats = await scheduling_client.queue_stats()

    assert stats == {"pending": 0, "processing": 2, "dlq": 1}


@pytest.mark.asyncio
async def test_replay_task_looks_up_file_path_from_registry_and_restarts(tmp_path):
    registry_file = tmp_path / "seen_documents.json"
    registry_file.write_text('{"abc123": "data/documents/report.pdf"}', encoding="utf-8")

    mock_client = MagicMock()
    mock_handle = MagicMock()
    description = MagicMock(status=WorkflowExecutionStatus.FAILED)
    mock_handle.describe = AsyncMock(return_value=description)
    mock_client.get_workflow_handle.return_value = mock_handle
    mock_client.start_workflow = AsyncMock()

    with patch.object(scheduling_client, "get_temporal_client", AsyncMock(return_value=mock_client)), \
         patch.object(scheduling_client, "load_registry", lambda: {"abc123": "data/documents/report.pdf"}):
        replayed = await scheduling_client.replay_task("ingest-abc123")

    assert replayed is True
    mock_client.start_workflow.assert_called_once()
    _, kwargs = mock_client.start_workflow.call_args
    assert kwargs["args"] == ["data/documents/report.pdf", "abc123"]


@pytest.mark.asyncio
async def test_replay_task_returns_false_for_non_failed_workflow():
    mock_client = MagicMock()
    mock_handle = MagicMock()
    mock_handle.describe = AsyncMock(return_value=MagicMock(status=WorkflowExecutionStatus.RUNNING))
    mock_client.get_workflow_handle.return_value = mock_handle

    with patch.object(scheduling_client, "get_temporal_client", AsyncMock(return_value=mock_client)):
        replayed = await scheduling_client.replay_task("ingest-abc123")

    assert replayed is False
