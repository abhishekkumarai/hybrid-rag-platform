# Architecture Plan — Modern 100% Open-Source Hybrid RAG Platform (SOA + Langflow)

## Goal Description

Build a production-grade, 100% open-source, evaluation-driven hybrid RAG platform designed on **Service-Oriented Architecture (SOA)** principles and powered by **Langflow** and Python.

The system runs completely local-first on the user's hardware (**NVIDIA RTX 3050 6GB VRAM + 16GB System RAM**), utilizing local Ollama models (`bge-m3`, `llama3.1:8b`, `llama3.2:3b`) with zero proprietary cloud API lock-in. It combines layout-aware document probing, asynchronous Redis task queuing with fault-tolerant reconciliation, hybrid HNSW + BM25 retrieval with custom Reciprocal Rank Fusion (RRF), cross-encoder reranking, and an interactive Langflow user interface (Visual Node Canvas + Chat Playground with native drag-and-drop file upload support).

Comprehensive, structured logging is built into every service layer, writing to rotating log files in `logs/` and emitting structured console output.

---

## Resolved Architectural Decisions

> [!NOTE]
> 1. **Service-Oriented Architecture (SOA)**:
>    - Decoupled into 5 autonomous services with strict Pydantic contracts (`contracts/`):
>      - **Service 1: Ingestion & Layout Probing** (`services/ingestion`)
>      - **Service 2: Chunking & Indexing** (`services/indexing`)
>      - **Service 3: Hybrid Retrieval & Cross-Encoder Rerank** (`services/retrieval`)
>      - **Service 4: Task Scheduling & Directory Reconciler** (`services/scheduler`)
>      - **Service 5: Orchestrator & UI via Langflow** (`services/orchestrator` / `components/`)
> 2. **UI & Orchestration: Langflow**:
>    - Langflow (port `7860`) serves as the visual orchestration engine, API gateway, and interactive user interface.
>    - Native document upload is supported directly in the Chat Playground via attachment/drag-and-drop.
>    - Langflow connects directly to PostgreSQL (`localhost:5432`) via `LANGFLOW_DATABASE_URL` for robust flow, session, and chat history persistence.
> 3. **Structured Logging Across All Services**:
>    - Centralized logging engine in `services/common/logger.py`.
>    - Dual destination: Colored console output + daily rotating log files in `logs/` (`rag_system.log`, `ingestion.log`, `retrieval.log`).
>    - Emits structured context: Document ID, routing decision, chunk counts, RRF scores, reranking scores, and execution latencies.
> 4. **100% Open-Source & Local-First (No Cloud APIs)**:
>    - Local Ollama models:
>      - **`quality` Profile (Default)**: `llama3.1:8b` (~28 layers offloaded to RTX 3050).
>      - **`fast` Profile**: `llama3.2:3b` (100% in VRAM).
>    - Embeddings: `bge-m3` via Ollama or local FastEmbed.
>    - Reranker: FlashRank on CPU (0 MB VRAM footprint).

---

## Runtime Inference Token Budget (Ollama 8K Envelope)

To ensure the RTX 3050 operates smoothly without spilling into slow CPU swap, the RAG generation pipeline enforces strict token boundaries:

| Pipeline Component | Token Allocation | Description |
| :--- | :--- | :--- |
| **System Prompt & Citations** | ~400 tokens | Strict grounding instructions and provenance formatting rules. |
| **Retrieved Context Passages** | ~3,072 tokens | Top-6 context passages $\times$ 512 tokens max per chunk. |
| **User Query & Chat History** | ~500 tokens | Current query plus immediate previous turn summary. |
| **Output Completion Budget** | ~1,000 tokens | Synthesis, explanation, and inline `[Doc: Page: BBox]` citations. |
| **Total Generation Envelope** | **~4,972 tokens** | **Fits safely inside the 8,192 Ollama context window** (~3,200 token safety margin). |

---

## System Architecture Diagram (SOA)

```mermaid
flowchart TD
    subgraph Client ["Client Interface (Langflow :7860)"]
        Playground["Interactive Chat Playground<br>• Drag-and-Drop File Upload<br>• SSE Token Streaming<br>• Citations [Doc: Page: BBox]"]
        Canvas["Visual Node Canvas<br>• Service Composition & Inspection"]
        LF_API["Langflow Gateway (/api/v1/run, /api/v1/webhook)"]
    end

    subgraph Service1 ["Service 1: Ingestion & Layout Probe"]
        S1_API["IngestionService.parse(file_path)"]
        Probe["8-Page Heuristic Probe (PyMuPDF)"]
        Router{"Route Selection"}
        P_Fast["PyMuPDF (fast_text)"]
        P_Layout["Docling (layout/tables)"]
        P_OCR["RapidOCR (scans)"]
        S1_API --> Probe --> Router
        Router -->|coverage >= 0.6 & clean| P_Fast
        Router -->|tables / multi-col| P_Layout
        Router -->|scanned images| P_OCR
    end

    subgraph Service2 ["Service 2: Chunking & Indexing"]
        S2_API["IndexingService.index(blocks)"]
        Chunker["Content-Aware Chunker (512 tokens cap)"]
        QdrantStore["Qdrant Client (Port 6333)"]
        BM25Store["BM25s Disk Index"]
        S2_API --> Chunker
        Chunker --> QdrantStore
        Chunker --> BM25Store
    end

    subgraph Service3 ["Service 3: Hybrid Retrieval & Rerank"]
        S3_API["RetrievalService.retrieve(query)"]
        RRF["Reciprocal Rank Fusion (k=60)"]
        CrossEncoder["FlashRank CPU Reranker"]
        Cutoff{"Score >= 0.15?"}
        S3_API --> RRF
        QdrantStore -.->|Dense Top-20| RRF
        BM25Store -.->|Sparse Top-20| RRF
        RRF --> CrossEncoder --> Cutoff
    end

    subgraph Service4 ["Service 4: Task Scheduling & Reconciler"]
        Watcher["Folder Watcher (data/documents/)"]
        Hasher["SHA-256 Deduplication"]
        RedisQ["Redis Queue & DLQ (Port 6379)"]
        Watcher --> Hasher --> RedisQ
        RedisQ -->|POST /api/v1/webhook/{flow_id}| LF_API
    end

    subgraph Infrastructure ["Local Microservices & Storage"]
        Postgres[("PostgreSQL (Port 5432)<br>Flows, Chat History, Metadata")]
        Ollama[("Ollama (Port 11434)<br>llama3.1:8b / llama3.2:3b")]
        Logger["Central Structured Logger (logs/)"]
    end

    Playground <--> LF_API
    Canvas <--> LF_API
    LF_API --> S1_API
    P_Fast --> S2_API
    P_Layout --> S2_API
    P_OCR --> S2_API
    LF_API --> S3_API
    Cutoff -->|Pass Top-6| Ollama
    Cutoff -->|Fail| Refusal["Confident Refusal"]
    LF_API <--> Postgres
    S1_API -.-> Logger
    S2_API -.-> Logger
    S3_API -.-> Logger
    S4_API -.-> Logger
```

---

## Service Contracts & Interfaces

### 1. Document & Ingestion Contracts (`contracts/document.py`)
- `Block(id, doc_id, page, bbox, type, text, html, level, order, meta)`
- `DocumentProfile(route, page_count, text_coverage, chars_per_page, image_ratio, columns, table_score)`
- `IngestRequest(file_path, profile_override)`
- `IngestResponse(doc_id, profile, blocks, duration_ms)`

### 2. Chunking & Indexing Contracts (`contracts/chunk.py`)
- `Chunk(id, doc_id, page, bbox, text, token_count, headings, is_table, meta)`
- `IndexRequest(blocks, collection_name)`
- `IndexResponse(indexed_chunks, duration_ms)`

### 3. Retrieval & Reranking Contracts (`contracts/retrieval.py`)
- `SearchQuery(query_text, top_k=20, min_rerank_score=0.15)`
- `Candidate(id, doc_id, page, bbox, text, dense_rank, sparse_rank, rrf_score, rerank_score)`
- `RetrieveResponse(candidates, citations, refused)`

---

## Hardware Budget Alignment (RTX 3050 + 16GB RAM)

- **Langflow UI & Gateway**: ~450 MB RAM (lean single-worker mode).
- **PostgreSQL**: ~80 MB RAM (already running on `localhost:5432`).
- **Qdrant Vector DB**: ~120 MB RAM (`docker-compose.yml`).
- **Redis Queue**: ~40 MB RAM (`docker-compose.yml`).
- **Ingestion & FlashRank**: CPU only (0 MB VRAM, ~150 MB RAM).
- **Total System RAM**: **~840 MB** (fits cleanly within ~1.1 GB free RAM).
- **VRAM**: Reserved exclusively for Ollama (`llama3.1:8b` or `llama3.2:3b`).
