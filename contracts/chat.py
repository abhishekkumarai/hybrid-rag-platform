"""Typed contracts for the /api/v1/chat pipeline (IRA-16).

One pipeline (`services.gateway.chat_pipeline.ChatPipeline`) yields these events; the streaming
endpoint serializes each one as an SSE frame and the non-streaming endpoint folds them into a single
JSON response. Keeping the events typed is what stops the two transports drifting apart again.

Wire compatibility: each event's SSE `event:` name and `data:` payload are exactly what the endpoint
emitted before these contracts existed (the UI and existing clients parse them).
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field

from contracts.agent import AgentStep
from contracts.metrics import QueryTelemetry, RetrievalEvalScores
from contracts.retrieval import Citation

RetrievalMode = Literal["auto", "agentic", "graph", "direct"]


class ChatTurnRequest(BaseModel):
    """Fully-resolved parameters for one chat turn (request fields merged over project settings)."""

    query: str = Field(min_length=1)
    session_id: str
    conversation_id: str | None = None
    model: str
    mode: RetrievalMode = "auto"
    top_k: int = 20
    top_rerank: int = 6
    temperature: float = 0.7
    compactor_budget: int = 3072
    min_score_threshold: float = 0.15
    ef_search: int | None = None
    # Exact doc_ids the project may read. [] refuses the turn without retrieving (a project with no
    # readable documents); None is unscoped and reserved for internal callers with no project.
    doc_ids: list[str] | None = None
    system_prompt: str | None = None


class SessionEvent(BaseModel):
    kind: Literal["session"] = "session"
    session_id: str
    conversation_id: str | None = None


class ModeEvent(BaseModel):
    kind: Literal["mode"] = "mode"
    mode: Literal["agentic", "graph"]


class AgentStepEvent(BaseModel):
    kind: Literal["agent_step"] = "agent_step"
    step: AgentStep


class TokenEvent(BaseModel):
    kind: Literal["token"] = "token"
    token: str


class ErrorEvent(BaseModel):
    kind: Literal["error"] = "error"
    error: str


class EvalEvent(BaseModel):
    kind: Literal["eval"] = "eval"
    scores: RetrievalEvalScores


class TelemetryEvent(BaseModel):
    kind: Literal["telemetry"] = "telemetry"
    telemetry: QueryTelemetry


class DoneEvent(BaseModel):
    """Final event of every turn, answered or refused."""

    kind: Literal["done"] = "done"
    refused: bool = False
    answer: str | None = Field(default=None, description="Answer with provenance section, or the refusal text")
    raw_answer: str | None = Field(default=None, description="Model output before provenance formatting")
    citations: list[Citation] = Field(default_factory=list)
    top_score: float = 0.0
    is_agentic: bool = False
    mode: str | None = None
    agent_steps: list[AgentStep] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list)
    error: str | None = Field(default=None, description="Generation error, if the model call failed")


ChatEvent = Union[
    SessionEvent, ModeEvent, AgentStepEvent, TokenEvent, ErrorEvent, EvalEvent, TelemetryEvent, DoneEvent
]
