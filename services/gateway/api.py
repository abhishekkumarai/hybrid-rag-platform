"""FastAPI Gateway exposing the unified SOA microservice endpoints for the RAG platform."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, AsyncGenerator

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from components.citation_formatter import CitationFormatterComponent
from contracts.agent import AgentStep
from contracts.chunk import IndexResponse
from contracts.compactor import CompactedContext, CompactorRequest
from contracts.document import Block, IngestRequest, IngestResponse
from contracts.feedback import FeedbackRecord, FeedbackRequest, RAGOpsSummary
from contracts.graph import GraphExtractionResult, GraphRAGResponse, GraphSearchQuery
from contracts.metrics import QueryTelemetry, SystemMetrics
from contracts.retrieval import RetrieveResponse, SearchQuery
from contracts.session import (
    AttachFilesRequest,
    ChatMessage,
    ChatSession,
    CreateSessionRequest,
    SessionDetailResponse,
    SessionListResponse,
    UpdateSessionRequest,
)
from services.common.config import load_config
from services.common.logger import get_logger
from services.feedback.store import RAGOpsStore
from services.graph.extractor import EntityRelationshipExtractor
from services.indexing.service import IndexingService
from services.ingestion.service import IngestionService
from services.ingestion.visualizer import render_page_with_bbox, resolve_document_path
from services.retrieval.agentic import AgenticCoordinator
from services.retrieval.compactor import ContextCompactor
from services.retrieval.service import RetrievalService
from services.scheduler.dlq_manager import DLQManager
from services.scheduler.queue import RedisTaskQueue
from services.session.manager import SessionManager
from services.telemetry.tracker import TelemetryTracker

logger = get_logger("gateway.api")
settings = load_config()

session_manager = SessionManager(
    host=settings.storage.redis_host,
    port=settings.storage.redis_port,
)
telemetry_tracker = TelemetryTracker()
ragops_store = RAGOpsStore(
    redis_host=settings.storage.redis_host,
    redis_port=settings.storage.redis_port,
)

app = FastAPI(
    title="Hybrid RAG Platform SOA Gateway",
    description="Unified REST and SSE Streaming Microservice Gateway for Local Hybrid RAG",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services initialized lazily
_ingestion_service: IngestionService | None = None
_indexing_service: IndexingService | None = None
_retrieval_service: RetrievalService | None = None
_agentic_coordinator: AgenticCoordinator | None = None


def get_services() -> tuple[IngestionService, IndexingService, RetrievalService]:
    global _ingestion_service, _indexing_service, _retrieval_service
    if _ingestion_service is None:
        _ingestion_service = IngestionService()
    if _indexing_service is None:
        _indexing_service = IndexingService(
            qdrant_host=settings.storage.qdrant_host,
            qdrant_port=settings.storage.qdrant_port,
        )
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(
            qdrant_store=_indexing_service.qdrant,
            bm25_store=_indexing_service.bm25,
            graph_store=_indexing_service.graph,
            ollama_url=settings.hardware.ollama_base_url,
        )
    return _ingestion_service, _indexing_service, _retrieval_service


def get_agentic_coordinator() -> AgenticCoordinator:
    global _agentic_coordinator
    if _agentic_coordinator is None:
        _, _, retrieval = get_services()
        _agentic_coordinator = AgenticCoordinator(
            retrieval_service=retrieval,
            graph_traverser=retrieval.traverser,
            compactor=retrieval.compactor,
        )
    return _agentic_coordinator


class GraphExtractRequest(BaseModel):
    text: str = Field(min_length=1, description="Raw text from which to extract entities and relations")
    doc_id: str | None = None
    chunk_id: str | None = None


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, description="User question")
    session_id: str | None = Field(default=None, description="Active chat session ID for multi-turn conversational memory")
    top_k: int = Field(default=20, ge=1, le=100)
    top_rerank: int = Field(default=6, ge=1, le=20)
    stream: bool = Field(default=True, description="Whether to stream response tokens via SSE")
    model: str = Field(default="llama3.2:3b", description="Ollama model name")
    mode: str = Field(default="auto", description="Retrieval mode: 'auto', 'agentic', 'graph', or 'direct'")


class ChunkAndIndexRequest(BaseModel):
    doc_id: str
    blocks: list[Block]


@app.get("/api/v1/health")
def health_check() -> dict[str, Any]:
    """Inspects connectivity to all underlying local microservices."""
    # 1. Qdrant health
    qdrant_ok = False
    try:
        r = requests.get(f"http://{settings.storage.qdrant_host}:{settings.storage.qdrant_port}/collections", timeout=2.0)
        qdrant_ok = (r.status_code == 200)
    except Exception:
        pass

    # 2. Redis health
    redis_ok = False
    try:
        import redis
        client = redis.Redis(host=settings.storage.redis_host, port=settings.storage.redis_port, socket_timeout=1.0)
        redis_ok = bool(client.ping())
    except Exception:
        pass

    # 3. Ollama health
    ollama_ok = False
    try:
        r = requests.get(f"{settings.hardware.ollama_base_url}/api/tags", timeout=2.0)
        ollama_ok = (r.status_code == 200)
    except Exception:
        pass

    # 4. Neo4j health
    _, indexing, _ = get_services()
    neo4j_ok = getattr(indexing.graph, "is_connected", False)

    status = "healthy" if (qdrant_ok and ollama_ok) else "degraded"
    return {
        "status": status,
        "services": {
            "qdrant": {"alive": qdrant_ok, "port": settings.storage.qdrant_port},
            "redis": {"alive": redis_ok, "port": settings.storage.redis_port},
            "ollama": {"alive": ollama_ok, "url": settings.hardware.ollama_base_url},
            "neo4j": {"alive": neo4j_ok, "uri": settings.storage.neo4j_uri},
        },
        "hardware_profile": settings.hardware.profile,
    }


class ModelInfo(BaseModel):
    name: str
    size_bytes: int | None = None
    modified_at: str | None = None
    digest: str | None = None
    is_default: bool = False


class ModelListResponse(BaseModel):
    models: list[ModelInfo]
    default_model: str
    hardware_profile: str
    ollama_alive: bool


@app.get("/api/v1/models", response_model=ModelListResponse)
def list_available_models() -> ModelListResponse:
    """Lists locally installed Ollama models and indicates the default active model."""
    default_model = "llama3.1:8b" if settings.hardware.profile == "quality" else "llama3.2:3b"
    models: list[ModelInfo] = []
    ollama_alive = False

    try:
        r = requests.get(f"{settings.hardware.ollama_base_url}/api/tags", timeout=2.0)
        if r.status_code == 200:
            ollama_alive = True
            data = r.json()
            for m in data.get("models", []):
                name = m.get("name", "")
                if name:
                    models.append(
                        ModelInfo(
                            name=name,
                            size_bytes=m.get("size"),
                            modified_at=m.get("modified_at"),
                            digest=m.get("digest"),
                            is_default=(name == default_model or name.startswith(default_model)),
                        )
                    )
    except Exception as e:
        logger.warning(f"Could not fetch models from Ollama ({settings.hardware.ollama_base_url}): {e}")

    if not models:
        fallback_models = [
            default_model,
            "llama3.2:3b" if default_model != "llama3.2:3b" else "llama3.1:8b",
            "qwen2.5:7b",
            "deepseek-r1:8b",
            "mistral:7b",
        ]
        models = [
            ModelInfo(
                name=m,
                is_default=(m == default_model),
            )
            for m in fallback_models
        ]

    if not any(m.is_default for m in models) and models:
        models[0].is_default = True

    return ModelListResponse(
        models=models,
        default_model=default_model,
        hardware_profile=settings.hardware.profile,
        ollama_alive=ollama_alive,
    )

class GpuModelVram(BaseModel):
    name: str
    size_vram_bytes: int
    size_vram_gb: float
    context_length: int | None = None


class GpuStatusResponse(BaseModel):
    gpu_name: str = "NVIDIA GeForce RTX 3050 6GB Laptop GPU"
    total_vram_mb: float = 6144.0
    used_vram_mb: float = 0.0
    free_vram_mb: float = 6144.0
    vram_percent: float = 0.0
    models: list[GpuModelVram] = []
    source: str = "ollama_ps"


@app.get("/api/v1/hardware/gpu", response_model=GpuStatusResponse)
def get_gpu_hardware_status() -> GpuStatusResponse:
    """Returns live VRAM telemetry from Ollama active model allocations and GPU memory."""
    total_mb = 6144.0
    used_bytes = 0
    active_models: list[GpuModelVram] = []

    try:
        import json
        import socket
        import urllib.request

        # Resolve host.docker.internal to concrete IP if needed to prevent container urllib3 proxy routing issues
        base_url = settings.hardware.ollama_base_url
        if "host.docker.internal" in base_url:
            try:
                host_ip = socket.gethostbyname("host.docker.internal")
                base_url = base_url.replace("host.docker.internal", host_ip)
            except Exception:
                pass

        req = urllib.request.Request(f"{base_url}/api/ps")
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for m in data.get("models", []):
                vram_b = m.get("size_vram", 0) or m.get("size", 0)
                used_bytes += vram_b
                active_models.append(
                    GpuModelVram(
                        name=m.get("name", "unknown"),
                        size_vram_bytes=vram_b,
                        size_vram_gb=round(vram_b / (1024**3), 2),
                        context_length=m.get("context_length"),
                    )
                )
    except Exception as e:
        logger.warning(f"Could not query Ollama /api/ps: {e}")

    # Fallback/refinement via nvidia-smi if accessible
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 2:
                used_mb = float(parts[0])
                tot_mb = float(parts[1])
                return GpuStatusResponse(
                    gpu_name="NVIDIA GeForce RTX 3050 6GB Laptop GPU",
                    total_vram_mb=tot_mb,
                    used_vram_mb=used_mb,
                    free_vram_mb=max(0.0, tot_mb - used_mb),
                    vram_percent=round((used_mb / tot_mb) * 100, 1),
                    models=active_models,
                    source="nvidia_smi",
                )
    except Exception:
        pass

    used_mb = round(used_bytes / (1024 * 1024), 1)
    free_mb = max(0.0, total_mb - used_mb)
    pct = round((used_mb / total_mb) * 100, 1) if total_mb else 0.0

    return GpuStatusResponse(
        gpu_name="NVIDIA GeForce RTX 3050 6GB Laptop GPU",
        total_vram_mb=total_mb,
        used_vram_mb=used_mb,
        free_vram_mb=free_mb,
        vram_percent=pct,
        models=active_models,
        source="ollama_ps",
    )


@app.get("/api/v1/queue/stats")
def queue_stats() -> dict[str, int]:
    """Returns real-time task count for pending, processing, and dead-letter queues."""
    queue = RedisTaskQueue()
    return queue.get_stats()


@app.get("/api/v1/queue/dlq")
def list_dlq(limit: int = 50) -> list[dict[str, Any]]:
    """Lists dead-letter queue items requiring operator inspection."""
    dlq_mgr = DLQManager()
    return dlq_mgr.list_dead_letters(limit=limit)


@app.post("/api/v1/queue/dlq/replay")
def replay_dlq(task_id: str | None = None) -> dict[str, Any]:
    """Replays all dead-letter tasks or a specific task back to the pending queue."""
    dlq_mgr = DLQManager()
    if task_id:
        success = dlq_mgr.replay_task(task_id)
        return {"replayed": 1 if success else 0, "task_id": task_id}
    replayed = dlq_mgr.replay_all()
    return {"replayed": replayed}


@app.get("/api/v1/documents")
def list_documents() -> dict:
    """Lists indexed and available documents in data/documents with metadata."""
    doc_dir = Path("data/documents")
    docs = []
    if doc_dir.exists():
        for f in sorted(doc_dir.glob("*.pdf")):
            page_count = 1
            try:
                import fitz
                doc = fitz.open(str(f))
                page_count = len(doc)
                doc.close()
            except Exception:
                pass
            docs.append({
                "name": f.name,
                "doc_id": f.name,
                "pages": page_count,
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
    return {"documents": docs}


@app.get("/api/v1/documents/{doc_id}/raw")
def get_raw_document(doc_id: str) -> Response:
    """Serves the raw PDF binary for browser preview or download."""
    doc_path = resolve_document_path(doc_id)
    if not doc_path:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return Response(
        content=doc_path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc_path.name}"'},
    )


@app.get("/api/v1/preview")
def preview_page(
    doc_id: str,
    page: int = 1,
    x0: float | None = None,
    y0: float | None = None,
    x1: float | None = None,
    y1: float | None = None,
    bbox: str | None = None,
    zoom: float = 1.5,
) -> Response:
    """Renders a visual PNG snapshot of the document page with the provenance bounding box highlighted."""
    doc_path = resolve_document_path(doc_id)
    if not doc_path:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    target_bbox: tuple[float, float, float, float] | None = None
    if x0 is not None and y0 is not None and x1 is not None and y1 is not None:
        target_bbox = (x0, y0, x1, y1)
    elif bbox:
        try:
            parts = [float(p.strip()) for p in bbox.split(",")]
            if len(parts) == 4:
                target_bbox = (parts[0], parts[1], parts[2], parts[3])
        except Exception:
            pass

    try:
        png_bytes = render_page_with_bbox(doc_path, page_num=page, bbox=target_bbox, zoom=zoom)
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rendering page preview: {e}")


@app.get("/api/v1/figures/{figure_name}")
@app.get("/data/figures/{figure_name}")
def get_figure_image(figure_name: str) -> Response:
    """Serves an extracted figure or diagram PNG crop."""
    fig_path = Path("data/figures") / figure_name
    if not fig_path.exists() or not fig_path.is_file():
        raise HTTPException(status_code=404, detail=f"Figure '{figure_name}' not found")
    return Response(content=fig_path.read_bytes(), media_type="image/png")


@app.post("/api/v1/ingest", response_model=IngestResponse)
def ingest_file(
    file: UploadFile = File(...),
    route: str | None = Form(default=None),
) -> IngestResponse:
    """Accepts multipart PDF file upload, stores to data/documents/, probes layout, and extracts blocks."""
    upload_dir = Path("data/documents")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / (file.filename or "uploaded_document.pdf")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ingestion, _, _ = get_services()
    profile_override = route if route in ("fast_text", "layout", "ocr") else None
    res = ingestion.parse(IngestRequest(file_path=str(file_path), profile_override=profile_override))
    logger.info(f"API Ingest: uploaded '{file.filename}' -> {len(res.blocks)} blocks ({res.profile.route})")
    return res


@app.post("/api/v1/index", response_model=IndexResponse)
def index_blocks(req: ChunkAndIndexRequest) -> IndexResponse:
    """Chunks layout blocks with heading hierarchy & table windowing, then indexes into Qdrant & BM25s."""
    _, indexing, _ = get_services()
    res = indexing.chunk_and_index(doc_id=req.doc_id, blocks=req.blocks)
    return res


@app.post("/api/v1/retrieve", response_model=RetrieveResponse)
def retrieve(query: SearchQuery) -> RetrieveResponse:
    """Executes parallel dense and sparse search, RRF fusion (k=60), and FlashRank cross-encoder reranking."""
    _, _, retrieval = get_services()
    return retrieval.retrieve(query)


# --- Conversational Session Management Endpoints ---


@app.post("/api/v1/sessions", response_model=ChatSession)
def create_session(req: CreateSessionRequest | None = None) -> ChatSession:
    """Creates a new conversational session with optional custom prompt, parameters, and scoped files."""
    if req:
        return session_manager.create_session(
            title=req.title,
            system_prompt=req.system_prompt,
            parameters=req.parameters,
            files=req.files,
        )
    return session_manager.create_session()


@app.get("/api/v1/sessions", response_model=SessionListResponse)
def list_sessions() -> SessionListResponse:
    """Lists all active conversational sessions sorted by recency."""
    return SessionListResponse(sessions=session_manager.list_sessions())


@app.get("/api/v1/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str) -> SessionDetailResponse:
    """Retrieves session metadata and historical message thread."""
    sess, msgs = session_manager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return SessionDetailResponse(session=sess, messages=msgs)


@app.patch("/api/v1/sessions/{session_id}", response_model=ChatSession)
def update_session(session_id: str, req: UpdateSessionRequest) -> ChatSession:
    """Partially updates session title, system prompt, parameters, or attached files."""
    updated = session_manager.update_session(session_id, req)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return updated


@app.post("/api/v1/sessions/{session_id}/files", response_model=ChatSession)
def attach_files_to_session(session_id: str, req: AttachFilesRequest) -> ChatSession:
    """Attaches documents to a session workspace."""
    updated = session_manager.attach_files(session_id, req.files)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return updated


@app.delete("/api/v1/sessions/{session_id}/files/{doc_id}", response_model=ChatSession)
def detach_file_from_session(session_id: str, doc_id: str) -> ChatSession:
    """Detaches a specific document from a session workspace."""
    updated = session_manager.detach_file(session_id, doc_id)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return updated


@app.delete("/api/v1/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, bool]:
    """Deletes a conversational session and its thread history."""
    deleted = session_manager.delete_session(session_id)
    return {"deleted": deleted}


# --- System Observability & Telemetry Endpoint ---


@app.get("/api/v1/metrics", response_model=SystemMetrics)
def get_metrics(session_id: str | None = None) -> SystemMetrics:
    """Returns real-time pipeline telemetry, latency breakdown, and microservice status, optionally scoped to a session."""
    _, indexing, _ = get_services()
    return telemetry_tracker.get_system_metrics(
        qdrant_host=settings.storage.qdrant_host,
        qdrant_port=settings.storage.qdrant_port,
        redis_host=settings.storage.redis_host,
        redis_port=settings.storage.redis_port,
        bm25_store=indexing.bm25,
        session_id=session_id,
    )


async def sse_chat_generator(
    query_text: str,
    top_k: int,
    top_rerank: int,
    model_name: str,
    session_id: str,
    mode: str = "auto",
    system_prompt: str | None = None,
    temperature: float = 0.7,
    doc_ids: list[str] | None = None,
    compactor_budget: int = 3072,
    min_score_threshold: float = 0.15,
) -> AsyncGenerator[str, None]:
    """Streams Ollama generation tokens via SSE with agentic multi-hop support and live telemetry."""
    t_start = time.perf_counter()
    _, _, retrieval = get_services()
    coordinator = get_agentic_coordinator()

    # Emit session identifier to client
    yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"

    # 1. Session Memory & Context Window
    retrieval_query = session_manager.reformulate_query(query_text, session_id)
    history_context = session_manager.build_conversation_context(session_id, max_turns=3)
    user_msg = ChatMessage(role="user", content=query_text)
    session_manager.append_message(session_id, user_msg)

    # 2. Determine Agentic vs Standard Execution
    is_agentic = (mode == "agentic") or (
        mode == "auto" and coordinator.decomposer.is_multi_hop_candidate(retrieval_query)
    )

    agent_steps: list[AgentStep] = []
    sub_queries_list: list[str] = []

    if is_agentic:
        yield f"event: mode\ndata: {json.dumps({'mode': 'agentic'})}\n\n"
        t_ret_start = time.perf_counter()
        candidates, citations, agent_steps, decomp_plan, crag_res, refused = coordinator.run_plan(
            query=retrieval_query,
            top_k=top_k,
            top_rerank=top_rerank,
            force_multi_hop=(mode == "agentic"),
            context_budget=compactor_budget,
            doc_ids=doc_ids,
        )
        retrieval_ms = (time.perf_counter() - t_ret_start) * 1000
        sub_queries_list = [sq.query_text for sq in decomp_plan.sub_queries]

        for step in agent_steps:
            yield f"event: agent_step\ndata: {step.model_dump_json()}\n\n"

        if refused:
            total_ms = (time.perf_counter() - t_start) * 1000
            refusal_msg = (
                "I could not locate sufficiently relevant information in the indexed documents "
                f"to answer your question with confidence (relevance cutoff threshold: {min_score_threshold:.2f})."
            )
            telemetry = QueryTelemetry(
                session_id=session_id,
                query_text=query_text,
                rerank_ms=round(retrieval_ms, 2),
                total_ms=round(total_ms, 2),
                refused=True,
                top_score=crag_res.top_score,
                citations_count=0,
            )
            telemetry_tracker.record_query(telemetry)
            session_manager.append_message(
                session_id,
                ChatMessage(role="assistant", content=refusal_msg, latency_ms=round(total_ms, 2)),
            )
            yield f"event: token\ndata: {json.dumps({'token': refusal_msg})}\n\n"
            yield f"event: telemetry\ndata: {telemetry.model_dump_json()}\n\n"
            yield f"event: done\ndata: {json.dumps({'citations': [], 'refused': True, 'top_score': crag_res.top_score, 'is_agentic': True, 'agent_steps': [s.model_dump() for s in agent_steps], 'sub_queries': sub_queries_list})}\n\n"
            return

        prompt = coordinator.build_agentic_prompt(
            query=query_text,
            candidates=candidates,
            decomp_plan=decomp_plan,
            history_context=history_context,
            graph_context=(
                coordinator.last_graph_response.subgraph_text
                if coordinator.last_graph_response
                else ""
            ),
            compacted_context=coordinator.last_compacted_context,
        )
        if system_prompt:
            prompt = f"System Persona & Directives:\n{system_prompt}\n\n{prompt}"
        top_score = candidates[0].rerank_score if candidates else 0.0
        final_citations = citations

    elif mode == "graph":
        yield f"event: mode\ndata: {json.dumps({'mode': 'graph'})}\n\n"
        t_ret_start = time.perf_counter()
        search_res, graph_res = retrieval.retrieve_with_graph(
            SearchQuery(
                query_text=retrieval_query,
                top_k=top_k,
                top_rerank=top_rerank,
                min_rerank_score=min_score_threshold,
                doc_ids=doc_ids,
            )
        )
        retrieval_ms = (time.perf_counter() - t_ret_start) * 1000

        if graph_res and graph_res.relations:
            g_step = AgentStep(
                step_type="graph_traversal",
                step_index=1,
                title="GraphRAG Relational Traversal",
                detail=(
                    f"Discovered {len(graph_res.relations)} relational facts and "
                    f"{len(graph_res.connected_chunk_ids)} connected chunks"
                ),
                data={
                    "entities": [e.name for e in graph_res.matched_entities],
                    "relations_count": len(graph_res.relations),
                    "subgraph_text": graph_res.subgraph_text,
                },
            )
            agent_steps.append(g_step)
            yield f"event: agent_step\ndata: {g_step.model_dump_json()}\n\n"

        if search_res.refused and not (graph_res and graph_res.relations):
            total_ms = (time.perf_counter() - t_start) * 1000
            refusal_msg = (
                "I could not locate sufficiently relevant information in the indexed documents "
                "or knowledge graph to answer your question with confidence."
            )
            telemetry = QueryTelemetry(
                session_id=session_id,
                query_text=query_text,
                rerank_ms=round(retrieval_ms, 2),
                total_ms=round(total_ms, 2),
                refused=True,
                top_score=search_res.top_score,
                citations_count=0,
            )
            telemetry_tracker.record_query(telemetry)
            session_manager.append_message(
                session_id,
                ChatMessage(role="assistant", content=refusal_msg, latency_ms=round(total_ms, 2)),
            )
            yield f"event: token\ndata: {json.dumps({'token': refusal_msg})}\n\n"
            yield f"event: telemetry\ndata: {telemetry.model_dump_json()}\n\n"
            yield f"event: done\ndata: {json.dumps({'citations': [], 'refused': True, 'top_score': search_res.top_score, 'is_agentic': False, 'mode': 'graph', 'agent_steps': [s.model_dump() for s in agent_steps]})}\n\n"
            return

        comp_context = retrieval.compact_results(
            query=retrieval_query,
            candidates=search_res.candidates,
            budget_tokens=compactor_budget,
        )
        if comp_context.dropped_chunks_count > 0 or comp_context.deduplicated_sentences_count > 0:
            c_step = AgentStep(
                step_type="compaction",
                step_index=len(agent_steps) + 1,
                title="Contextual Token Budget Compaction",
                detail=(
                    f"Compacted {comp_context.total_original_tokens} -> {comp_context.total_compressed_tokens} "
                    f"tokens (ratio {comp_context.overall_compression_ratio:.2f})"
                ),
                data={
                    "original_tokens": comp_context.total_original_tokens,
                    "compressed_tokens": comp_context.total_compressed_tokens,
                },
            )
            agent_steps.append(c_step)
            yield f"event: agent_step\ndata: {c_step.model_dump_json()}\n\n"

        graph_md = graph_res.subgraph_text if graph_res else ""
        context_body = comp_context.formatted_prompt_context or "\n\n".join(
            [f"[{c.id}] {c.text}" for c in search_res.candidates]
        )
        evidence_block = f"{graph_md}\n\n{context_body}" if graph_md else context_body
        prompt = (
            f"{f'System Persona & Directives:\n{system_prompt}\n\n' if system_prompt else ''}"
            f"Relational & Document Context:\n{evidence_block}\n\n"
            f"{f'Previous Conversation:\n{history_context}\n\n' if history_context else ''}"
            f"Question: {query_text}\n"
            f"Synthesize an accurate answer using the verified graph relations and retrieved passages:"
        )
        top_score = search_res.top_score
        final_citations = search_res.citations

    else:
        # Standard Single-Hop Fast Path
        t_ret_start = time.perf_counter()
        search_res = retrieval.retrieve(
            SearchQuery(
                query_text=retrieval_query,
                top_k=top_k,
                top_rerank=top_rerank,
                min_rerank_score=min_score_threshold,
                doc_ids=doc_ids,
            )
        )
        retrieval_ms = (time.perf_counter() - t_ret_start) * 1000

        if search_res.refused:
            total_ms = (time.perf_counter() - t_start) * 1000
            refusal_msg = (
                "I could not locate sufficiently relevant information in the indexed documents "
                f"to answer your question with confidence (relevance cutoff threshold: {min_score_threshold:.2f})."
            )
            telemetry = QueryTelemetry(
                session_id=session_id,
                query_text=query_text,
                rerank_ms=round(retrieval_ms, 2),
                total_ms=round(total_ms, 2),
                refused=True,
                top_score=search_res.top_score,
                citations_count=0,
            )
            telemetry_tracker.record_query(telemetry)

            session_manager.append_message(
                session_id,
                ChatMessage(role="assistant", content=refusal_msg, latency_ms=round(total_ms, 2)),
            )

            yield f"event: token\ndata: {json.dumps({'token': refusal_msg})}\n\n"
            yield f"event: telemetry\ndata: {telemetry.model_dump_json()}\n\n"
            yield f"event: done\ndata: {json.dumps({'citations': [], 'refused': True, 'top_score': search_res.top_score, 'is_agentic': False})}\n\n"
            return

        comp_context = retrieval.compact_results(
            query=retrieval_query,
            candidates=search_res.candidates,
            budget_tokens=compactor_budget,
        )
        context = comp_context.formatted_prompt_context or "\n\n".join(
            [f"[{c.id}] {c.text}" for c in search_res.candidates]
        )
        if history_context:
            prompt = (
                f"{f'System Persona & Directives:\n{system_prompt}\n\n' if system_prompt else ''}"
                f"Previous Conversation:\n{history_context}\n\n"
                f"Retrieved Document Excerpts:\n{context}\n\n"
                f"User Question: {query_text}\n"
                f"Answer truthfully based on the retrieved documents and conversation context:"
            )
        else:
            prompt = (
                f"{f'System Persona & Directives:\n{system_prompt}\n\n' if system_prompt else ''}"
                f"Context:\n{context}\n\n"
                f"Question: {query_text}\n"
                f"Answer truthfully based strictly on the provided context:"
            )
        top_score = search_res.top_score
        final_citations = search_res.citations

    # Calculate safe num_ctx tailored for the active hardware profile & model
    # On RTX 3050 6GB VRAM, clamp num_ctx for 7B/8B/14B models to 4096 to prevent "context size too large"
    is_large_model = any(tag in model_name.lower() for tag in ("8b", "7b", "14b", "13b", "70b"))
    max_hardware_ctx = 4096 if is_large_model else 8192
    safe_num_ctx = min(max(compactor_budget + 512, 2048), max_hardware_ctx)

    # Prompt length safety guard to guarantee prompt never overflows Ollama context
    max_prompt_chars = int((safe_num_ctx - 350) * 3.5)
    if len(prompt) > max_prompt_chars:
        prompt = prompt[:max_prompt_chars] + "\n\n[Context truncated to fit model context window]\n"

    # 3. Stream from Local Ollama & Measure TTFT
    full_answer_parts: list[str] = []
    t_llm_start = time.perf_counter()
    ttft_ms = 0.0
    token_count = 0

    try:
        resp = requests.post(
            f"{settings.hardware.ollama_base_url}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "num_predict": 256,
                    "temperature": temperature,
                    "num_ctx": safe_num_ctx,
                },
            },
            stream=True,
            timeout=120,
        )
        if resp.status_code != 200:
            logger.warning(
                f"Ollama stream returned {resp.status_code}, retrying with safe num_ctx=2048: {resp.text}"
            )
            resp = requests.post(
                f"{settings.hardware.ollama_base_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt[:4000],
                    "stream": True,
                    "options": {
                        "num_predict": 256,
                        "temperature": temperature,
                        "num_ctx": 2048,
                    },
                },
                stream=True,
                timeout=120,
            )

        for line in resp.iter_lines():
            if line:
                chunk = json.loads(line)
                tok = chunk.get("response", "")
                if tok:
                    if token_count == 0:
                        ttft_ms = (time.perf_counter() - t_llm_start) * 1000
                    token_count += 1
                    full_answer_parts.append(tok)
                    yield f"event: token\ndata: {json.dumps({'token': tok})}\n\n"
                if chunk.get("done", False):
                    break
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    llm_gen_ms = (time.perf_counter() - t_llm_start) * 1000
    total_ms = (time.perf_counter() - t_start) * 1000
    tokens_per_sec = round(token_count / (llm_gen_ms / 1000), 1) if llm_gen_ms > 0 else 0.0

    telemetry = QueryTelemetry(
        session_id=session_id,
        query_text=query_text,
        rerank_ms=round(retrieval_ms, 2),
        llm_ttft_ms=round(ttft_ms, 2),
        llm_gen_ms=round(llm_gen_ms, 2),
        total_ms=round(total_ms, 2),
        tokens_generated=token_count,
        tokens_per_sec=tokens_per_sec,
        refused=False,
        top_score=top_score,
        citations_count=len(final_citations),
    )
    telemetry_tracker.record_query(
        telemetry,
        redis_host=settings.storage.redis_host,
        redis_port=settings.storage.redis_port,
    )

    # 4. Save Assistant Turn to Session History
    full_answer = "".join(full_answer_parts)
    session_manager.append_message(
        session_id,
        ChatMessage(
            role="assistant",
            content=full_answer,
            citations=final_citations,
            latency_ms=round(total_ms, 2),
        ),
    )

    # 5. Emit Live Telemetry, Citations, and Agentic Trace
    citations_data = [c.model_dump() for c in final_citations]
    yield f"event: telemetry\ndata: {telemetry.model_dump_json()}\n\n"
    yield f"event: done\ndata: {json.dumps({'citations': citations_data, 'top_score': top_score, 'is_agentic': is_agentic, 'agent_steps': [s.model_dump() for s in agent_steps], 'sub_queries': sub_queries_list})}\n\n"


@app.post("/api/v1/chat")
def chat(req: ChatRequest):
    """Conversational RAG endpoint supporting both SSE streaming tokens and synchronous response."""
    # Ensure active session exists or auto-create one
    session: ChatSession | None = None
    active_session_id = req.session_id
    if active_session_id:
        session, _ = session_manager.get_session(active_session_id)
    if not session:
        session = session_manager.create_session()
        active_session_id = session.id

    effective_model = (
        session.parameters.model
        if (req.model == "llama3.2:3b" and session.parameters.model)
        else req.model
    )
    effective_mode = (
        session.parameters.retrieval_mode
        if (req.mode == "auto" and session.parameters.retrieval_mode)
        else req.mode
    )
    effective_top_k = (
        session.parameters.top_k
        if (req.top_k == 20 and session.parameters.top_k)
        else req.top_k
    )
    effective_top_rerank = (
        session.parameters.top_rerank
        if (req.top_rerank == 6 and hasattr(session.parameters, "top_rerank") and session.parameters.top_rerank)
        else req.top_rerank
    )
    effective_stream = (
        session.parameters.stream
        if hasattr(session.parameters, "stream") and not session.parameters.stream
        else req.stream
    )
    temperature = session.parameters.temperature
    compactor_budget = session.parameters.compactor_budget
    min_score_threshold = session.parameters.min_score_threshold
    doc_ids = session.files if session.files else None
    system_prompt = session.system_prompt

    if effective_stream:
        return StreamingResponse(
            sse_chat_generator(
                query_text=req.query,
                top_k=effective_top_k,
                top_rerank=effective_top_rerank,
                model_name=effective_model,
                session_id=active_session_id,
                mode=effective_mode,
                system_prompt=system_prompt,
                temperature=temperature,
                doc_ids=doc_ids,
                compactor_budget=compactor_budget,
                min_score_threshold=min_score_threshold,
            ),
            media_type="text/event-stream",
        )

    t_start = time.perf_counter()
    _, _, retrieval = get_services()
    coordinator = get_agentic_coordinator()

    # 1. Session Memory & Context Window
    retrieval_query = session_manager.reformulate_query(req.query, active_session_id)
    history_context = session_manager.build_conversation_context(active_session_id, max_turns=3)
    user_msg = ChatMessage(role="user", content=req.query)
    session_manager.append_message(active_session_id, user_msg)

    # 2. Determine Agentic vs Standard Execution
    is_agentic = (effective_mode == "agentic") or (
        effective_mode == "auto" and coordinator.decomposer.is_multi_hop_candidate(retrieval_query)
    )

    agent_steps: list[AgentStep] = []
    sub_queries_list: list[str] = []

    if is_agentic:
        t_ret_start = time.perf_counter()
        candidates, citations, agent_steps, decomp_plan, crag_res, refused = coordinator.run_plan(
            query=retrieval_query,
            top_k=effective_top_k,
            top_rerank=effective_top_rerank,
            force_multi_hop=(effective_mode == "agentic"),
            context_budget=compactor_budget,
            doc_ids=doc_ids,
        )
        retrieval_ms = (time.perf_counter() - t_ret_start) * 1000
        sub_queries_list = [sq.query_text for sq in decomp_plan.sub_queries]

        if refused:
            total_ms = (time.perf_counter() - t_start) * 1000
            refusal_msg = "I could not locate sufficiently relevant information in the indexed documents."
            telemetry = QueryTelemetry(
                session_id=active_session_id,
                query_text=req.query,
                rerank_ms=round(retrieval_ms, 2),
                total_ms=round(total_ms, 2),
                refused=True,
                top_score=crag_res.top_score,
                citations_count=0,
            )
            telemetry_tracker.record_query(telemetry)
            session_manager.append_message(
                active_session_id,
                ChatMessage(role="assistant", content=refusal_msg, latency_ms=round(total_ms, 2)),
            )
            return {
                "answer": refusal_msg,
                "citations": [],
                "refused": True,
                "telemetry": telemetry.model_dump(),
                "is_agentic": True,
                "agent_steps": [s.model_dump() for s in agent_steps],
                "session_id": active_session_id,
            }

        prompt = coordinator.build_agentic_prompt(
            query=req.query,
            candidates=candidates,
            decomp_plan=decomp_plan,
            history_context=history_context,
            graph_context=(
                coordinator.last_graph_response.subgraph_text
                if coordinator.last_graph_response
                else ""
            ),
            compacted_context=coordinator.last_compacted_context,
        )
        if system_prompt:
            prompt = f"System Persona & Directives:\n{system_prompt}\n\n{prompt}"
        top_score = candidates[0].rerank_score if candidates else 0.0
        final_citations = citations

    elif effective_mode == "graph":
        t_ret_start = time.perf_counter()
        search_res, graph_res = retrieval.retrieve_with_graph(
            SearchQuery(
                query_text=retrieval_query,
                top_k=effective_top_k,
                top_rerank=effective_top_rerank,
                min_rerank_score=min_score_threshold,
                doc_ids=doc_ids,
            )
        )
        retrieval_ms = (time.perf_counter() - t_ret_start) * 1000

        if graph_res and graph_res.relations:
            agent_steps.append(
                AgentStep(
                    step_type="graph_traversal",
                    step_index=1,
                    title="GraphRAG Relational Traversal",
                    detail=(
                        f"Discovered {len(graph_res.relations)} relational facts and "
                        f"{len(graph_res.connected_chunk_ids)} connected chunks"
                    ),
                    data={
                        "entities": [e.name for e in graph_res.matched_entities],
                        "relations_count": len(graph_res.relations),
                        "subgraph_text": graph_res.subgraph_text,
                    },
                )
            )

        if search_res.refused and not (graph_res and graph_res.relations):
            total_ms = (time.perf_counter() - t_start) * 1000
            refusal_msg = "I could not locate sufficiently relevant information in the indexed documents or knowledge graph."
            telemetry = QueryTelemetry(
                session_id=active_session_id,
                query_text=req.query,
                rerank_ms=round(retrieval_ms, 2),
                total_ms=round(total_ms, 2),
                refused=True,
                top_score=search_res.top_score,
                citations_count=0,
            )
            telemetry_tracker.record_query(telemetry)
            session_manager.append_message(
                active_session_id,
                ChatMessage(role="assistant", content=refusal_msg, latency_ms=round(total_ms, 2)),
            )
            return {
                "answer": refusal_msg,
                "citations": [],
                "refused": True,
                "telemetry": telemetry.model_dump(),
                "is_agentic": False,
                "mode": "graph",
                "session_id": active_session_id,
            }

        comp_context = retrieval.compact_results(
            query=retrieval_query,
            candidates=search_res.candidates,
            budget_tokens=compactor_budget,
        )
        if comp_context.dropped_chunks_count > 0 or comp_context.deduplicated_sentences_count > 0:
            agent_steps.append(
                AgentStep(
                    step_type="compaction",
                    step_index=len(agent_steps) + 1,
                    title="Contextual Token Budget Compaction",
                    detail=(
                        f"Compacted {comp_context.total_original_tokens} -> {comp_context.total_compressed_tokens} "
                        f"tokens (ratio {comp_context.overall_compression_ratio:.2f})"
                    ),
                    data={
                        "original_tokens": comp_context.total_original_tokens,
                        "compressed_tokens": comp_context.total_compressed_tokens,
                    },
                )
            )

        graph_md = graph_res.subgraph_text if graph_res else ""
        context_body = comp_context.formatted_prompt_context or "\n\n".join(
            [f"[{c.id}] {c.text}" for c in search_res.candidates]
        )
        evidence_block = f"{graph_md}\n\n{context_body}" if graph_md else context_body
        prompt = (
            f"{f'System Persona & Directives:\n{system_prompt}\n\n' if system_prompt else ''}"
            f"Relational & Document Context:\n{evidence_block}\n\n"
            f"{f'Previous Conversation:\n{history_context}\n\n' if history_context else ''}"
            f"Question: {req.query}\n"
            f"Synthesize an accurate answer using the verified graph relations and retrieved passages:"
        )
        top_score = search_res.top_score
        final_citations = search_res.citations

    else:
        # Standard Single-Hop Path
        t_ret_start = time.perf_counter()
        ret_res = retrieval.retrieve(
            SearchQuery(
                query_text=retrieval_query,
                top_k=effective_top_k,
                top_rerank=effective_top_rerank,
                min_rerank_score=min_score_threshold,
                doc_ids=doc_ids,
            )
        )
        retrieval_ms = (time.perf_counter() - t_ret_start) * 1000

        if ret_res.refused:
            total_ms = (time.perf_counter() - t_start) * 1000
            refusal_msg = "I could not locate sufficiently relevant information in the indexed documents."
            telemetry = QueryTelemetry(
                session_id=active_session_id,
                query_text=req.query,
                rerank_ms=round(retrieval_ms, 2),
                total_ms=round(total_ms, 2),
                refused=True,
                top_score=ret_res.top_score,
                citations_count=0,
            )
            telemetry_tracker.record_query(telemetry)
            session_manager.append_message(
                active_session_id,
                ChatMessage(role="assistant", content=refusal_msg, latency_ms=round(total_ms, 2)),
            )
            return {
                "answer": refusal_msg,
                "citations": [],
                "refused": True,
                "telemetry": telemetry.model_dump(),
                "is_agentic": False,
                "session_id": active_session_id,
            }

        comp_context = retrieval.compact_results(
            query=retrieval_query,
            candidates=ret_res.candidates,
            budget_tokens=compactor_budget,
        )
        context = comp_context.formatted_prompt_context or "\n\n".join(
            [f"[{c.id}] {c.text}" for c in ret_res.candidates]
        )
        if history_context:
            prompt = (
                f"{f'System Persona & Directives:\n{system_prompt}\n\n' if system_prompt else ''}"
                f"Previous Conversation:\n{history_context}\n\n"
                f"Context:\n{context}\n\n"
                f"Question: {req.query}\n"
                f"Answer truthfully based on the retrieved documents and conversation context:"
            )
        else:
            prompt = (
                f"{f'System Persona & Directives:\n{system_prompt}\n\n' if system_prompt else ''}"
                f"Context:\n{context}\n\n"
                f"Question: {req.query}\n"
                f"Answer truthfully based strictly on the provided context:"
            )
        top_score = ret_res.top_score
        final_citations = ret_res.citations

    # Calculate safe num_ctx tailored for the active hardware profile & model
    # On RTX 3050 6GB VRAM, clamp num_ctx for 7B/8B/14B models to 4096 to prevent "context size too large"
    is_large_model = any(tag in effective_model.lower() for tag in ("8b", "7b", "14b", "13b", "70b"))
    max_hardware_ctx = 4096 if is_large_model else 8192
    safe_num_ctx = min(max(compactor_budget + 512, 2048), max_hardware_ctx)

    # Prompt length safety guard to guarantee prompt never overflows Ollama context
    max_prompt_chars = int((safe_num_ctx - 350) * 3.5)
    if len(prompt) > max_prompt_chars:
        prompt = prompt[:max_prompt_chars] + "\n\n[Context truncated to fit model context window]\n"

    t_llm_start = time.perf_counter()
    try:
        resp = requests.post(
            f"{settings.hardware.ollama_base_url}/api/generate",
            json={
                "model": effective_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 256,
                    "temperature": temperature,
                    "num_ctx": safe_num_ctx,
                },
            },
            timeout=120,
        )
        if resp.status_code != 200:
            logger.warning(
                f"Ollama generation returned {resp.status_code}, retrying with safe num_ctx=2048: {resp.text}"
            )
            resp = requests.post(
                f"{settings.hardware.ollama_base_url}/api/generate",
                json={
                    "model": effective_model,
                    "prompt": prompt[:4000],
                    "stream": False,
                    "options": {
                        "num_predict": 256,
                        "temperature": temperature,
                        "num_ctx": 2048,
                    },
                },
                timeout=120,
            )
        llm_answer = resp.json().get("response", "")
    except Exception as e:
        llm_answer = f"Error generating answer: {e}"

    llm_gen_ms = (time.perf_counter() - t_llm_start) * 1000
    total_ms = (time.perf_counter() - t_start) * 1000
    token_count = len(llm_answer.split()) * 1.3
    tokens_per_sec = round(token_count / (llm_gen_ms / 1000), 1) if llm_gen_ms > 0 else 0.0

    formatter = CitationFormatterComponent()
    final_output = formatter.format_response(llm_answer, [c.model_dump() for c in final_citations])

    telemetry = QueryTelemetry(
        session_id=active_session_id,
        query_text=req.query,
        rerank_ms=round(retrieval_ms, 2),
        llm_gen_ms=round(llm_gen_ms, 2),
        total_ms=round(total_ms, 2),
        tokens_generated=int(token_count),
        tokens_per_sec=tokens_per_sec,
        refused=False,
        top_score=top_score,
        citations_count=len(final_citations),
    )
    telemetry_tracker.record_query(
        telemetry,
        redis_host=settings.storage.redis_host,
        redis_port=settings.storage.redis_port,
    )

    session_manager.append_message(
        active_session_id,
        ChatMessage(
            role="assistant",
            content=final_output,
            citations=final_citations,
            latency_ms=round(total_ms, 2),
        ),
    )

    return {
        "answer": final_output,
        "raw_answer": llm_answer,
        "citations": [c.model_dump() for c in final_citations],
        "top_score": top_score,
        "refused": False,
        "duration_ms": round(total_ms, 2),
        "telemetry": telemetry.model_dump(),
        "is_agentic": is_agentic,
        "agent_steps": [s.model_dump() for s in agent_steps],
        "sub_queries": sub_queries_list,
        "session_id": active_session_id,
    }


# --- RAGOps & Feedback Endpoints (Phase 15) ---


@app.post("/api/v1/feedback", response_model=FeedbackRecord)
def submit_feedback(req: FeedbackRequest) -> FeedbackRecord:
    """Submits user satisfaction feedback and automatically mines hard-negatives on thumbs down."""
    return ragops_store.record_feedback(req)


@app.get("/api/v1/feedback/summary", response_model=RAGOpsSummary)
def get_feedback_summary(session_id: str | None = None) -> RAGOpsSummary:
    """Returns aggregated continuous evaluation metrics and active learning counts, optionally scoped to a session."""
    return ragops_store.get_summary(session_id=session_id)


@app.get("/api/v1/ragops/dataset")
def export_ragops_dataset(session_id: str | None = None) -> list[dict[str, Any]]:
    """Exports mined contrastive hard-negative triplets, optionally scoped to a session."""
    return ragops_store.export_training_dataset(session_id=session_id)


# --- GraphRAG Endpoints (Phase 13) ---


@app.post("/api/v1/graph/extract", response_model=GraphExtractionResult)
def extract_graph_elements(req: GraphExtractRequest) -> GraphExtractionResult:
    """Extracts entities and relational predicates from text preserving document coordinates."""
    extractor = EntityRelationshipExtractor()
    entities = extractor.extract_entities(req.text, doc_id=req.doc_id, chunk_id=req.chunk_id)
    relations = extractor.extract_relations(
        req.text, entities=entities, doc_id=req.doc_id, chunk_id=req.chunk_id
    )
    return GraphExtractionResult(
        entities=entities,
        relations=relations,
        doc_id=req.doc_id,
        chunk_id=req.chunk_id,
    )


@app.post("/api/v1/graph/query", response_model=GraphRAGResponse)
def query_knowledge_graph(req: GraphSearchQuery) -> GraphRAGResponse:
    """Executes multi-hop traversal, associative pathfinding, and community detection."""
    _, _, retrieval = get_services()
    if not retrieval.traverser:
        raise HTTPException(status_code=503, detail="Graph traversal engine is not available")
    return retrieval.traverser.query_graph(
        query_text=req.query_text,
        max_hops=req.max_hops,
        max_entities=req.max_entities,
        min_edge_weight=req.min_edge_weight,
    )


@app.get("/api/v1/graph/stats")
def get_graph_stats(session_id: str | None = None, doc_ids: str | None = None) -> dict[str, Any]:
    """Returns knowledge graph topology metrics, node categories, and predicate distributions, optionally scoped to session or documents."""
    _, indexing, _ = get_services()
    filter_doc_ids: list[str] | None = None
    if session_id:
        sess, _ = session_manager.get_session(session_id)
        if sess and sess.files:
            filter_doc_ids = sess.files
        else:
            filter_doc_ids = []
    elif doc_ids:
        filter_doc_ids = [d.strip() for d in doc_ids.split(",") if d.strip()]

    return indexing.graph.get_stats(doc_ids=filter_doc_ids)


# --- Contextual Compression Endpoints (Phase 14) ---


@app.post("/api/v1/compact", response_model=CompactedContext)
def compact_context(req: CompactorRequest) -> CompactedContext:
    """Contextual compression & token budget compaction for multi-hop evidence passages."""
    compactor = ContextCompactor(
        default_budget_tokens=req.budget_tokens,
        min_sentence_score=req.min_sentence_score,
    )
    return compactor.compress_candidates(
        query=req.query,
        candidates=req.candidates,
        budget_tokens=req.budget_tokens,
        deduplicate=req.deduplicate,
        prune_tables=req.prune_tables,
    )


@app.get("/", response_class=HTMLResponse)
def index_page() -> str:
    """Serves the interactive single-page RAG client."""
    ui_path = Path("ui/index.html")
    if ui_path.exists():
        return ui_path.read_text(encoding="utf-8")
    return """
    <html>
      <head><title>Hybrid RAG SOA Gateway</title></head>
      <body style="font-family: sans-serif; padding: 2rem;">
        <h2>Hybrid RAG Platform API Gateway</h2>
        <p>Endpoints available:</p>
        <ul>
          <li><a href="/docs">Swagger API Documentation (/docs)</a></li>
          <li><a href="/api/v1/health">System Health (/api/v1/health)</a></li>
        </ul>
      </body>
    </html>
    """
