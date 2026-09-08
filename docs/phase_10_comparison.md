# Phase 10: Capability Options & Architecture Comparison

This document provides a side-by-side comparison of the candidate capability areas for **Phase 10** of the Hybrid RAG platform.

---

## 1. High-Level Comparison Table

| Dimension | Option 1: Conversational Memory & Session Management | Option 2: Real-Time Observability & Telemetry | Option 3: Full Production Containerization | Option 4: Complete Enterprise Suite (Recommended: 1 + 2) |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Goal** | Enables contextual multi-turn dialogue and conversation persistence. | Tracks system health, query latency breakdown, and token throughput. | Packages every microservice into a single turnkey Docker stack with health checks. | Combines persistent multi-turn chat sessions with real-time observability in the Web UI. |
| **Core Capabilities** | • `session_id` tracking via Redis<br>• Sliding token window context<br>• Pronoun/context resolution (e.g. *"What did he do next?"*)<br>• Session sidebar in Web UI to switch chats | • `/api/v1/metrics` Prometheus/JSON endpoint<br>• Millisecond latency breakdown: Dense vs. Sparse vs. FlashRank vs. Ollama TTFT<br>• Live tokens/sec meter<br>• Hardware VRAM/RAM monitor | • Unified `docker-compose.prod.yml`<br>• Automated healthcheck probes for Qdrant, Redis, Ollama, Langflow, Gateway<br>• Single-command launch (`docker compose up`) | • Both multi-turn chat memory and live telemetry dashboard active in the Web UI<br>• Full end-to-end user experience and operational visibility |
| **User Experience Impact** | **High**: Users can have ongoing, natural back-and-forth conversations with context preserved across questions. | **High for operations**: Visual feedback on search speed, generation latency, and refusal triggers. | **High for deployment**: Simplifies deploying or migrating the stack to any other server or machine. | **Maximum**: Delivers both end-user conversational flow and operational metrics in one cohesive interface. |
| **Hardware Overhead**<br>*(RTX 3050 6GB + 16GB RAM)* | **Minimal**<br>(~5–10 MB in Redis for conversation history). | **Negligible**<br>(in-memory rolling metrics buffer; 0 MB VRAM). | **Moderate**<br>(Docker networking and container daemon overhead). | **Minimal**<br>(< 15 MB RAM, 0 MB VRAM overhead). |
| **Real-World Value** | Resolves follow-up queries without having to repeat context or document names. | Pinpoints bottlenecks immediately (e.g., whether latency was in dense embedding, cross-encoder, or Ollama generation). | Ensures consistent, reproducible runtime environments across different machines. | Production-grade platform ready for both daily interactive use and performance profiling. |

---

## 2. Detailed Breakdown of Each Option

### Option 1: Conversational Memory & Session Management

#### What Gets Added
- **Backend**:
  - Adds session endpoints:
    - `POST /api/v1/chat/sessions`: Create a new session.
    - `GET /api/v1/chat/sessions`: List active sessions.
    - `GET /api/v1/chat/sessions/{session_id}`: Retrieve message history.
    - `DELETE /api/v1/chat/sessions/{session_id}`: Delete a session.
  - Stores conversation turns (user question, assistant answer, citations, timestamps) in Redis.
  - Implements sliding window token budgeting so the context envelope never overflows the LLM context limit.
  - Adds contextual query reformulation: when the user asks a follow-up query with pronouns (e.g., *"What company did he join after that?"*), it uses previous conversation context to retrieve relevant chunks accurately.
- **Frontend ([`ui/index.html`](file:///C:/Users/abhi3/Documents/work/rag/ui/index.html))**:
  - Adds a collapsible left-hand navigation sidebar displaying session history.
  - "New Chat" button to reset context without losing prior conversation logs.
  - Clicking an earlier session reloads the full message timeline and citation badges.

---

### Option 2: Real-Time Observability & Telemetry Dashboard

#### What Gets Added
- **Backend**:
  - Adds `/api/v1/metrics` exposing:
    - **Latency Breakdown**:
      - Dense Embedding + Search Latency (`ms`)
      - BM25 Sparse Search Latency (`ms`)
      - Reciprocal Rank Fusion Latency (`ms`)
      - FlashRank CPU Rerank Latency (`ms`)
      - Ollama Time-to-First-Token (TTFT) (`ms`)
      - Total End-to-End Latency (`ms`)
    - **Throughput Metrics**:
      - Output tokens generated per second (`tok/s`).
    - **Quality & Safety Counters**:
      - Total queries processed.
      - Refusal trigger count (hallucinations prevented by $< 0.15$ cutoff).
    - **Storage Counters**:
      - Points in Qdrant HNSW collection.
      - Documents indexed in BM25s disk store.
      - Pending jobs in Redis Queue / DLQ.
- **Frontend ([`ui/index.html`](file:///C:/Users/abhi3/Documents/work/rag/ui/index.html))**:
  - Adds a sleek **Telemetry HUD Bar** at the top/bottom:
    ```
    [Latency: 317ms (Dense: 13ms | Sparse: 9ms | Rerank: 42ms)] [LLM: 28 tok/s] [Refusals Blocked: 4]
    ```
  - Expandable modal with real-time graphs and index statistics.

---

### Option 3: Full Production Containerization

#### What Gets Added
- **Stack Architecture**:
  - Creates a unified multi-container configuration (`docker-compose.prod.yml`) bundling:
    - `fastapi-gateway`: FastAPI microservice + static UI.
    - `redis-queue`: Redis 7 alpine with persistence and task queues.
    - `qdrant`: Vector database with volume mounts.
    - `langflow`: Visual workflow engine.
    - `worker`: Background asynchronous ingestion daemon.
  - Automated service dependency ordering with health checks.
  - Single-command orchestration: `docker compose -f docker-compose.prod.yml up -d`.

---

### Option 4: Complete Enterprise Suite (Options 1 + 2) *(Recommended)*

#### Why This is the Recommended Path
1. **Interactive Polish**: Transforms the system from a single-query demo into a fully featured conversational workplace tool.
2. **Zero VRAM Footprint**: Both features run strictly in CPU memory and Redis (< 15 MB RAM total), leaving 100% of your 6GB RTX 3050 VRAM dedicated to Ollama generation.
3. **Operational Transparency**: You get visual feedback on why answers take the time they do and how effectively the hybrid retriever is performing.

---

## 3. Decision & Next Steps

When you are ready, please indicate your preference:
- **Proceed with Option 4** (Enterprise Suite: Memory + Telemetry + UI Enhancements)
- **Proceed with Option 1** (Conversational Memory only)
- **Proceed with Option 2** (Telemetry only)
- **Proceed with Option 3** (Docker Containerization only)
