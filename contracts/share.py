"""Pydantic contracts for public chat share links and forking them into a project (IRA-35)."""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field

from contracts.retrieval import Citation
from contracts.session import SessionParameters


class SharedMessage(BaseModel):
    """A message as a public viewer sees it: internal metadata (eval scores, query ids) is stripped."""

    role: str
    content: str
    citations: list[Citation] = Field(default_factory=list)
    timestamp: float


class ShareSnapshot(BaseModel):
    """A chat frozen at share time. Messages added to the source project later are never exposed."""

    title: str
    system_prompt: str | None = None
    parameters: SessionParameters = Field(default_factory=SessionParameters)
    messages: list[SharedMessage] = Field(default_factory=list)
    doc_ids: list[str] = Field(
        default_factory=list,
        description="Documents a viewer may preview and a fork is granted read access to",
    )
    created_at: float = Field(default_factory=time.time)


class Share(BaseModel):
    """A stored share. Only a hash of the URL token is kept, so a leaked database can't mint URLs."""

    id: str = Field(default_factory=lambda: f"shr_{uuid.uuid4().hex[:12]}")
    token_hash: str
    session_id: str
    owner_id: str
    snapshot: ShareSnapshot
    created_at: float = Field(default_factory=time.time)
    revoked_at: float | None = None
    view_count: int = 0


class ShareSummary(BaseModel):
    """What the owner sees in the share list; the full URL is shown only once, at creation."""

    id: str
    session_id: str
    created_at: float
    message_count: int
    revoked: bool


class CreateShareResponse(BaseModel):
    url: str
    token: str
    share: ShareSummary


class ShareListResponse(BaseModel):
    shares: list[ShareSummary]


class ForkResponse(BaseModel):
    session_id: str
