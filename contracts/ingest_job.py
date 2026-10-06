"""Background ingest jobs (IRA-60): an upload or URL that is parsed, indexed and attached server-side."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "done", "failed"]
JobKind = Literal["file", "url"]


class IngestJob(BaseModel):
    """One source being added to a project. Clients poll these instead of driving the steps themselves,
    so progress survives a tab change or a page reload."""

    id: str
    user_id: str
    session_id: str
    kind: JobKind
    source: str = Field(description="Filename for an upload, the URL for a web source")
    status: JobStatus = "queued"
    stage: str = Field(default="Queued", description="Human-readable current step")
    doc_id: str | None = None
    blocks: int | None = None
    error: str | None = None
    # Which gateway process owns the job; one from a previous process can never finish (IRA-60).
    runner_id: str = ""
    created_at: float
    updated_at: float


class IngestJobUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    session_id: str
    route: Literal["fast_text", "layout", "ocr", "paddleocr"] | None = None


class IngestJobListResponse(BaseModel):
    jobs: list[IngestJob]
