"""Pydantic data contracts for conversational chat sessions, workspace isolation, and message history."""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from contracts.retrieval import Citation


class SessionParameters(BaseModel):
    """Runtime LLM and retrieval execution parameters scoped to a session."""

    model: str = "llama3.2:3b"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    retrieval_mode: Literal["auto", "agentic", "graph", "direct"] = "auto"
    embedding_route: Literal["auto", "fast_text", "layout", "ocr"] = "auto"
    top_k: int = Field(default=20, ge=1, le=100)
    top_rerank: int = Field(default=6, ge=1, le=20)
    min_score_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    compactor_budget: int = Field(default=3072, ge=512, le=8192)
    stream: bool = True


class ChatMessage(BaseModel):
    """A single turn in a conversational chat session."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: Literal["user", "assistant", "system"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
    latency_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatSession(BaseModel):
    """Metadata and scoped workspace state for a conversational session."""

    id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    title: str = "New Conversation"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    message_count: int = 0
    files: list[str] = Field(default_factory=list, description="Document IDs scoped to this session")
    system_prompt: str | None = Field(default=None, description="Custom system persona instructions for this session")
    parameters: SessionParameters = Field(default_factory=SessionParameters, description="Runtime execution parameters")


class CreateSessionRequest(BaseModel):
    """Request payload to initialize a new session with custom settings."""

    title: str | None = None
    system_prompt: str | None = None
    parameters: SessionParameters | None = None
    files: list[str] | None = None


class UpdateSessionRequest(BaseModel):
    """Request payload to partially update session metadata, prompt, parameters, or files."""

    title: str | None = None
    system_prompt: str | None = None
    parameters: SessionParameters | None = None
    files: list[str] | None = None


class AttachFilesRequest(BaseModel):
    """Request payload to attach documents to a session."""

    files: list[str]


class SessionListResponse(BaseModel):
    sessions: list[ChatSession]


class SessionDetailResponse(BaseModel):
    session: ChatSession
    messages: list[ChatMessage]
