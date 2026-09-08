# 100% Open-Source Modern RAG Architecture Specification & System Prompt

## 100% Open-Source Python Tech Stack

| Component | Library / Model | License & Rationale |
| :--- | :--- | :--- |
| **Local LLM** | **Ollama** (`langchain-ollama`) running `llama3.1:8b` or `qwen2.5:7b` | Completely local, open-weights, zero API costs, zero proprietary cloud dependencies. |
| **Local Embeddings** | `fastembed` or `langchain-huggingface` (`BAAI/bge-m3` or `bge-small-en-v1.5`) | Open-source SOTA embeddings with high retrieval accuracy running locally on CPU/GPU. |
| **Vector DB (HNSW)** | `qdrant-client` (local embedded / disk storage) | Apache 2.0 open-source engine with native HNSW indexing (`m=16`, `ef_construct=100`), runs embedded without external servers. |
| **Layout-Aware Parsing** | `docling` (IBM) or `pymupdf4llm` | MIT / Apache open-source layout understanding: extracts hierarchy, tables, and reading order from complex PDFs and documents into Markdown. |
| **Lexical Search (BM25)** | `rank-bm25` | MIT-licensed in-memory tokenized BM25 keyword matching for exact lexical coverage. |
| **Local Reranking** | `flashrank` (`ms-marco-MiniLM-L-12-v2` or `bge-reranker-base`) | Apache 2.0 ultra-fast local cross-encoder running on ONNX runtime (no heavy PyTorch or GPU needed). |
| **Task Queue & Recovery** | **Redis** (`redis` / `rq` or `arq`) | High-performance open-source task queue, job state registry, dead-letter queue (DLQ), and missed document reconciliation. |
| **Orchestration** | `langchain`, `langchain-community`, `langgraph` | Open-source framework for composable LCEL retrieval chains and stateful workflows. |
| **Evaluation & Tracing** | `ragas` + `langsmith` (or open-source `phoenix` / `langfuse`) | Automated evaluation with open-source Ragas metrics running on local models, with LangSmith/Langfuse tracing. |
| **CLI & Config** | `typer`, `pydantic-settings` | Clean, interactive, scriptable terminal CLI for easy testing with AI coding agents. |

---

## Master Engineering Prompt for AI Coding Assistants (Claude Code / Gemini CLI)

```markdown
You are an expert Staff AI Engineer specializing in production-grade Retrieval-Augmented Generation (RAG) systems.

Build a complete, modular, and 100% OPEN-SOURCE RAG application in Python.
The entire stack must run completely local-first with ZERO reliance on proprietary closed APIs (e.g., No OpenAI, No Cohere).
Use:
- LangChain + Ollama (Llama 3.1 8B or Qwen 2.5 7B) for generation
- FastEmbed / HuggingFace (BAAI/bge-m3 or bge-small-en-v1.5) for dense embeddings
- Embedded Qdrant with custom HNSW index
- BM25 for sparse keyword search
- Reciprocal Rank Fusion (RRF) for hybrid ranking
- FlashRank (local ONNX Cross-Encoder) for reranking
- IBM Docling for layout-aware document ingestion
- Redis for asynchronous queue-based ingestion, state tracking, and missed document recovery
- Ragas + LangSmith for evaluation and observability
- Typer CLI interface for testing and automation

---

### Core Architectural Requirements

1. **Document Ingestion & Layout Awareness**:
   - Detect document types (.pdf, .docx, .md, .txt).
   - For PDFs and complex documents, use IBM `docling` (or `pymupdf4llm` fallback) to parse layout structures: titles, section headings, multi-column blocks, reading order, and Markdown tables.
   - Preserve structural metadata: file path, page number, section breadcrumbs, and table indicators.

2. **Content-Aware + Recursive Chunking**:
   - **Content-Aware Splitting**: First split by semantic headers (`MarkdownHeaderTextSplitter`) so that chunk boundaries respect document sections and subheadings.
   - **Recursive Chunking**: Sub-chunk large sections with `RecursiveCharacterTextSplitter` (chunk_size=600, chunk_overlap=120).
   - Prepend section hierarchy/breadcrumbs to child chunks to preserve context.
   - Retain complete markdown tables within single chunks whenever possible.

3. **Dual Indexing & Hybrid Retrieval**:
   - **Dense Index**: Embedded Qdrant (`location="./data/qdrant_db"` or in-memory) with explicit HNSW configuration:
     - `m=16`, `ef_construct=100`
     - Distance metric: Cosine
     - Dense embeddings via open-source `FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")` or `bge-m3`.
   - **Sparse Index**: In-memory BM25 index (`rank-bm25`) built over the same chunk corpus with lowercased and stemmed tokenization.
   - Retrieve `top_k=25` from dense and `top_k=25` from sparse.

4. **Reciprocal Rank Fusion (RRF)**:
   - Implement an explicit RRF scoring formula:
     $$\text{RRF}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{k + \text{rank}_m(d)}$$
     where $k=60$ by default.
   - Deduplicate documents across both retrieval lists and sort by combined RRF score.
   - Keep the top 20 candidates.

5. **Local Cross-Encoder Reranking**:
   - Use `FlashRank` (`Ranker(model_name="ms-marco-MiniLM-L-12-v2")` or `bge-reranker-base`) for ultra-fast, local CPU-based cross-encoder scoring.
   - Rerank the top 20 fused candidates down to the final top 4-6 highest-scoring context passages.

6. **Redis Queue-Based Processing & Missed Job Recovery**:
   - **Asynchronous Ingestion Queue**:
     - Decouple file submission from indexing using Redis (`redis-py` / `rq` or reliable Redis Streams / Lists with atomic `RPOPLPUSH` / `BLMOVE`).
     - Producer: Computes SHA-256 hash of file content. Idempotent check: if the file hash is already marked `COMPLETED` in the Redis registry, skip to prevent duplicate indexing.
   - **Job State Registry & Dead-Letter Queue (DLQ)**:
     - Maintain state in Redis: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`.
     - Record metadata: file path, content hash, timestamp, retry count, and error logs.
     - Exponential backoff retry (up to 3 attempts) on failure. Jobs that fail all retries move to the Dead-Letter Queue (`rag:queue:dead_letter`).
   - **Worker Process**:
     - Background worker process that continuously consumes jobs, executes the layout-aware parser, chunks, and writes to Qdrant & BM25.
     - Heartbeat mechanism: If a worker crashes mid-task, tasks stuck in `PROCESSING` longer than timeout (e.g. 10 minutes) are automatically reclaimed.
   - **Reconciliation / "Pick Up Missed Ones" Engine**:
     - A reconciliation scanner (`cli.py recover --dir ./data/`) that:
       1. Scans the local documents directory.
       2. Cross-references all files on disk against the Redis registry.
       3. Detects any unindexed files (missed due to offline periods or missed events), stalled jobs, and DLQ failures.
       4. Automatically re-enqueues missed/failed documents for reprocessing.

7. **Local Generation & Citation Guardrails**:
   - Connect to local Ollama (`ChatOllama(model="llama3.1:8b", temperature=0.1)`).
   - Construct an LCEL chain with strict citation-grounded prompting.
   - Format: Each fact must cite its source (e.g. `[Doc: annual_report.pdf | Page: 4 | Section: Financials]`).
   - If context lacks sufficient information, instruct the LLM to cleanly state insufficient evidence rather than hallucinating.

8. **Evaluation & Tracing**:
   - Integrate **LangSmith** tracing via environment variables (`LANGCHAIN_TRACING_V2=true`).
   - Implement an evaluation pipeline using **Ragas** powered entirely by the local Ollama LLM and local embeddings:
     - Faithfulness
     - Answer Relevance
     - Context Precision
   - Provide an evaluation test set (5 benchmark question/ground-truth pairs) to run automated scoring.

---

### Project File Tree Structure

```text
rag_system/
├── pyproject.toml / requirements.txt
├── .env.example
├── README.md
├── cli.py                     # Typer CLI entrypoint
├── config.py                  # Pydantic Settings (models, Redis URL, paths)
├── queue/
│   ├── connection.py          # Redis connection pool & keys
│   ├── producer.py            # Document enqueuer with SHA-256 deduplication
│   ├── worker.py              # Ingestion worker (parser -> chunker -> indexer)
│   ├── registry.py            # State tracker (PENDING/PROCESSING/COMPLETED/FAILED)
│   └── reconciler.py          # Missed & stalled document recovery scanner
├── ingest/
│   ├── parser.py              # Docling layout-aware document reader
│   └── chunker.py             # Content-aware header + recursive chunker
├── retrieval/
│   ├── vector_store.py        # Qdrant client with local storage & HNSW
│   ├── bm25_search.py         # BM25 lexical retriever
│   ├── rrf.py                 # Reciprocal Rank Fusion implementation
│   └── reranker.py            # FlashRank local cross-encoder
├── pipeline/
│   ├── chain.py               # LangChain LCEL pipeline with ChatOllama
│   └── prompt.py              # System prompt & citation template
└── evaluation/
    ├── eval_dataset.py        # Benchmark test suite (queries + ground truth)
    └── run_eval.py            # Local Ragas & LangSmith evaluator
```

---

### CLI Interface Requirements

Create `cli.py` supporting:
- `python cli.py enqueue --path ./data/` (Enqueues all new/changed files to Redis queue)
- `python cli.py worker` (Starts background Redis ingestion worker)
- `python cli.py recover --dir ./data/` (Reconciles directory, reclaims stalled jobs, and enqueues missed/failed docs)
- `python cli.py status` (Inspects Redis queue size, DLQ count, and document registry stats)
- `python cli.py query "What are the primary findings in the report?"`
- `python cli.py evaluate` (Runs local Ragas evaluation and logs traces)

---

### Implementation Instructions

1. Write clean, type-annotated, modular Python 3.11+ code.
2. Provide a `.env.example` with:
   - `REDIS_URL="redis://localhost:6379/0"`
   - `OLLAMA_BASE_URL="http://localhost:11434"`
   - `OLLAMA_MODEL="llama3.1:8b"`
   - `EMBEDDING_MODEL="BAAI/bge-small-en-v1.5"`
   - `LANGCHAIN_TRACING_V2="true"`
   - `LANGCHAIN_API_KEY=""`
   - `LANGCHAIN_PROJECT="modern-rag-opensource"`
3. Implement atomic queue transitions, heartbeats for crashed workers, and robust SHA-256 hash checks so indexing is fully idempotent.
4. Do not omit logic or leave placeholder `TODO` implementations.
5. Ensure dependencies in `requirements.txt` are fully open-source and compatible.
6. Verify execution by running the CLI commands after building.
```

---

## How to Execute with Claude Code or Gemini CLI

### Claude Code:
```bash
claude "Read prompt.md and implement the complete 100% open-source, Redis queue-backed RAG system according to the specifications."
```

### Gemini CLI:
```bash
gemini "Read prompt.md and implement the complete 100% open-source, Redis queue-backed RAG system according to the specifications."
```
