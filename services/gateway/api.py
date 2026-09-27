"""FastAPI Gateway exposing the unified SOA microservice endpoints for the RAG platform."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from contracts.chat import ChatTurnRequest
from contracts.chunk import IndexResponse
from contracts.compactor import CompactedContext, CompactorRequest
from contracts.document import Block, IngestRequest, IngestResponse
from contracts.feedback import FeedbackRecord, FeedbackRequest, RAGOpsSummary
from contracts.graph import GraphExtractionResult, GraphRAGResponse, GraphSearchQuery
from contracts.metrics import (
    ProjectEvalRun,
    ProjectEvalSummary,
    SystemMetrics,
)
from contracts.retrieval import RetrieveResponse, SearchQuery
from contracts.session import (
    AttachFilesRequest,
    ChatSession,
    CreateSessionRequest,
    SessionDetailResponse,
    SessionListResponse,
    UpdateSessionRequest,
)
from services.common.config import load_config
from services.common.logger import get_logger
from services.evaluation import project as project_eval
from services.feedback.store import RAGOpsStore
from services.gateway.chat_pipeline import ChatPipeline, fold_to_response, to_sse
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


STORE_RELOAD_INTERVAL_SECONDS = 60


async def _periodic_store_reload() -> None:
    """Keeps this process's in-memory BM25/graph stores in sync with documents indexed by the
    separate scheduler/worker processes, which construct their own `IndexingService` (and thus
    their own BM25Store/GraphStore instances) and have no way to update this process's memory
    directly. Both stores persist to disk on every write, so periodically re-reading that disk
    state is the cross-process sync mechanism. Qdrant needs no equivalent — it's an external
    service, not in-process state."""
    while True:
        await asyncio.sleep(STORE_RELOAD_INTERVAL_SECONDS)
        if _indexing_service is None:
            continue
        try:
            _indexing_service.bm25.reload()
            _indexing_service.graph.load_from_disk()
        except Exception as exc:
            logger.warning(f"Periodic BM25/graph store reload failed: {exc}")


@app.on_event("startup")
async def _start_background_tasks() -> None:
    asyncio.create_task(_periodic_store_reload())


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
    # These default to None (unset), not their eventual runtime default, so the /chat handler can
    # tell "client omitted this field" apart from "client explicitly requested the default value" —
    # only the former should fall back to the session's stored preference.
    top_k: int | None = Field(default=None, ge=1, le=100)
    top_rerank: int | None = Field(default=None, ge=1, le=20)
    stream: bool | None = Field(default=None, description="Whether to stream response tokens via SSE")
    model: str | None = Field(default=None, description="Ollama model name")
    mode: str | None = Field(default=None, description="Retrieval mode: 'auto', 'agentic', 'graph', or 'direct'")


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

    # Neo4j is intentionally excluded from this gate: its absence is a supported, designed-for
    # fallback to the in-memory NetworkX graph (see services/graph/neo4j_store.py), not a failure.
    # Redis is not optional in the same way — SessionManager/RAGOpsStore depend on it for anything
    # beyond a single-process in-memory/disk fallback, so its outage should surface as degraded.
    status = "healthy" if (qdrant_ok and ollama_ok and redis_ok) else "degraded"
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


@app.get("/api/v1/prompts/default")
def default_system_prompt() -> dict[str, str]:
    """The grounding persona applied to projects that have no custom system prompt (IRA-18)."""
    return {"system_prompt": settings.generation.default_system_prompt}


@app.get("/api/v1/models", response_model=ModelListResponse)
def list_available_models() -> ModelListResponse:
    """Lists locally installed Ollama models and indicates the default active model."""
    default_model = settings.hardware.llm_model
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
        # Ollama is unreachable, so we have no way to know what's actually installed. Offering a
        # list of plausible-sounding-but-unverified model names here (as this used to do) causes
        # a client that doesn't check `ollama_alive` to offer models that error out on selection.
        # The one name we do know is honest is the configured default — surface just that,
        # clearly still tied to `ollama_alive=False`.
        models = [ModelInfo(name=default_model, is_default=True)]

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
    gpu_name: str = "Unknown GPU"
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
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 3:
                gpu_name = parts[0]
                used_mb = float(parts[1])
                tot_mb = float(parts[2])
                return GpuStatusResponse(
                    gpu_name=gpu_name,
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
        gpu_name="Unknown GPU",
        total_vram_mb=total_mb,
        used_vram_mb=used_mb,
        free_vram_mb=free_mb,
        vram_percent=pct,
        models=active_models,
        source="ollama_ps",
    )


class HnswStatusResponse(BaseModel):
    collection_name: str
    hnsw_m: int
    hnsw_ef_construct: int
    default_ef_search: int
    status: str
    points_count: int | None = None
    indexed_vectors_count: int | None = None


class HnswRebuildRequest(BaseModel):
    hnsw_m: int = Field(ge=4, le=64, description="Qdrant HNSW graph connectivity (m) — higher improves recall at the cost of index size/build time")
    hnsw_ef_construct: int = Field(ge=16, le=512, description="Qdrant HNSW build-time search depth (ef_construct) — higher improves index quality at the cost of build time")


@app.get("/api/v1/admin/hnsw", response_model=HnswStatusResponse)
def get_hnsw_status() -> HnswStatusResponse:
    """Reports the live Qdrant collection's HNSW index config and rebuild/optimizer progress.

    m and ef_construct are collection-wide (not per-session, unlike ef_search) — see
    QdrantStore.update_hnsw_config for why.
    """
    _, indexing, _ = get_services()
    return HnswStatusResponse(**indexing.qdrant.get_index_status())


@app.post("/api/v1/admin/hnsw/rebuild", response_model=HnswStatusResponse)
def rebuild_hnsw_index(req: HnswRebuildRequest) -> HnswStatusResponse:
    """Applies new HNSW m/ef_construct to the shared Qdrant collection and triggers a background
    re-index of every already-embedded chunk across every workspace. This affects all users/sessions
    and is not instant — poll GET /api/v1/admin/hnsw afterward to watch `status`/`indexed_vectors_count`
    until the rebuild completes.
    """
    _, indexing, _ = get_services()
    indexing.qdrant.update_hnsw_config(req.hnsw_m, req.hnsw_ef_construct)
    return HnswStatusResponse(**indexing.qdrant.get_index_status())


@app.get("/api/v1/queue/stats")
def queue_stats() -> dict[str, int]:
    """Returns real-time task count for pending, processing, and dead-letter queues."""
    queue = RedisTaskQueue()
    return queue.get_stats()


@app.get("/api/v1/queue/dlq")
def list_dlq(limit: int = Query(default=50, ge=1, le=1000)) -> list[dict[str, Any]]:
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


def _safe_join(base: Path, name: str) -> Path:
    """Joins `name` onto `base` and verifies the result stays inside `base`.

    Rejects absolute paths and `..` traversal in `name` — a plain `base / name` join silently
    discards `base` entirely when `name` is itself absolute (`Path('a') / '/etc/passwd' ==
    Path('/etc/passwd')`), which is what makes an unguarded join exploitable.
    """
    resolved_base = base.resolve()
    candidate = (resolved_base / name).resolve()
    if not candidate.is_relative_to(resolved_base):
        raise HTTPException(status_code=400, detail="Invalid path")
    return candidate


@app.get("/api/v1/figures/{figure_name}")
@app.get("/data/figures/{figure_name}")
def get_figure_image(figure_name: str) -> Response:
    """Serves an extracted figure or diagram PNG crop."""
    fig_path = _safe_join(Path("data/figures"), figure_name)
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
    safe_filename = Path(file.filename or "uploaded_document.pdf").name or "uploaded_document.pdf"
    file_path = _safe_join(upload_dir, safe_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ingestion, _, _ = get_services()
    profile_override = route if route in ("fast_text", "layout", "ocr", "paddleocr") else None
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



def _chat_pipeline() -> ChatPipeline:
    _, _, retrieval = get_services()
    return ChatPipeline(
        retrieval=retrieval,
        coordinator=get_agentic_coordinator(),
        session_manager=session_manager,
        telemetry=telemetry_tracker,
        settings=settings,
    )


def sse_chat_generator(turn: ChatTurnRequest) -> Iterator[str]:
    """Streams one chat turn as SSE frames (see `ChatPipeline.run` for the event contract).

    Deliberately a *sync* generator: every step (retrieval, rerank, the Ollama `requests` stream)
    blocks, and StreamingResponse runs sync iterators in its threadpool. As an `async def` it ran
    on the event loop and stalled every other request for the whole answer (IRA-9)."""
    for event in _chat_pipeline().run(turn, stream_llm=True):
        yield to_sse(event)


@app.post("/api/v1/chat")
def chat(req: ChatRequest):
    """Conversational RAG endpoint: SSE token stream, or one JSON response when stream is false.

    Both transports run the same `ChatPipeline` (IRA-16); only the serialization differs."""
    # Ensure active session exists or auto-create one
    session: ChatSession | None = None
    active_session_id = req.session_id
    if active_session_id:
        session, _ = session_manager.get_session(active_session_id)
    if not session:
        session = session_manager.create_session()
        active_session_id = session.id

    # req.X is None means the client omitted the field — fall back to the session's stored
    # preference. A client that explicitly sends the literal default value (e.g. top_k=20) is
    # honored as an explicit request, not silently overridden by the session.
    params = session.parameters
    turn = ChatTurnRequest(
        query=req.query,
        session_id=active_session_id,
        model=req.model if req.model is not None else params.model,
        mode=req.mode if req.mode is not None else params.retrieval_mode,
        top_k=req.top_k if req.top_k is not None else params.top_k,
        top_rerank=req.top_rerank if req.top_rerank is not None else params.top_rerank,
        temperature=params.temperature,
        compactor_budget=params.compactor_budget,
        min_score_threshold=params.min_score_threshold,
        ef_search=params.hnsw_ef_search,
        doc_ids=session.files or None,
        system_prompt=session.system_prompt,
    )
    stream = req.stream if req.stream is not None else params.stream
    if stream:
        return StreamingResponse(sse_chat_generator(turn), media_type="text/event-stream")
    return fold_to_response(_chat_pipeline().run(turn, stream_llm=False))


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
        doc_ids=req.doc_ids,
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

# --- Evaluation Endpoints (Popular RAG Metrics) ---


def _require_project(session_id: str) -> ChatSession:
    session, _ = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Project '{session_id}' not found")
    return session


@app.get("/api/v1/sessions/{session_id}/eval/summary", response_model=ProjectEvalSummary)
def project_eval_summary(session_id: str) -> ProjectEvalSummary:
    """Aggregates this project's per-turn online evaluation scores (trend + weakest turns)."""
    _require_project(session_id)
    records, judge = project_eval.load_session_telemetry(
        session_id,
        telemetry_tracker.get_recent_telemetry(limit=10_000),
        redis_host=settings.storage.redis_host,
        redis_port=settings.storage.redis_port,
    )
    return project_eval.summarize_project(session_id, records, judge)


@app.get("/api/v1/sessions/{session_id}/eval/run", response_model=ProjectEvalRun | None)
def project_eval_last_run(session_id: str) -> ProjectEvalRun | None:
    """Returns this project's most recent golden-set run, or null if it has never been run."""
    _require_project(session_id)
    return project_eval.load_last_run(session_id)


@app.post("/api/v1/sessions/{session_id}/eval/run", response_model=ProjectEvalRun)
def project_eval_run(session_id: str, rebuild: bool = False) -> ProjectEvalRun:
    """Runs the project's golden set (generated from its own documents) with its own settings."""
    session = _require_project(session_id)
    if not session.files:
        raise HTTPException(status_code=400, detail="Attach documents to this project before evaluating it")
    _, indexing, retrieval = get_services()
    golden = project_eval.load_or_build_golden_set(
        session,
        indexing.bm25.corpus_chunks,
        size=settings.evaluation.golden_set_size,
        ollama_url=settings.hardware.ollama_base_url,
        rebuild=rebuild,
    )
    if not golden:
        raise HTTPException(
            status_code=400, detail="This project's documents have no indexed chunks to build questions from"
        )
    run = project_eval.run_golden_set(session, golden, retrieval)
    project_eval.save_run(run)
    return run


@app.get("/api/v1/eval/report")
def get_evaluation_report() -> dict[str, Any]:
    """Returns the latest RAG evaluation report with popular industry metrics (RAGAS, TruLens, TREC IR)."""
    report_file = Path("data/eval_report.json")
    if report_file.exists():
        try:
            return json.loads(report_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not read cached eval report: {e}")

    # If no report exists yet, run evaluation harness
    from tests.eval.eval_harness import run_evaluation
    return run_evaluation(output_report_path=report_file)


@app.post("/api/v1/eval/run")
def trigger_evaluation_run() -> dict[str, Any]:
    """Triggers an on-demand evaluation run computing popular metrics across the benchmark corpus."""
    report_file = Path("data/eval_report.json")
    from tests.eval.eval_harness import run_evaluation
    return run_evaluation(output_report_path=report_file)

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
