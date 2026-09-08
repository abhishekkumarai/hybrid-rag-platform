# Modern UI Architecture & Design Standards

This document summarizes the Modern UI design philosophy and frontend implementation guidelines for the **Enterprise Multimodal RAG Platform**, integrating rules from [`claude.md`](file:///C:/Users/abhi3/Documents/work/rag/claude.md) and the formal [`DESIGN.md`](file:///C:/Users/abhi3/Documents/work/rag/DESIGN.md) design system token specification.

---

## 1. Specification References

- **Formal Token & Component Spec**: [`DESIGN.md`](file:///C:/Users/abhi3/Documents/work/rag/DESIGN.md) (follows [getdesign.md](https://getdesign.md) and Google Stitch specifications)
- **Frontend Behavioral Rules**: [`claude.md`](file:///C:/Users/abhi3/Documents/work/rag/claude.md)
- **Live Implementation**: [`ui/index.html`](file:///C:/Users/abhi3/Documents/work/rag/ui/index.html)

---

## 2. Core Visual Principles

### 2.1 Engineering-First Cockpit (No Generic SaaS Slop)
- Avoid generic landing page templates, 3-column feature cards with floating icons, and decorative background blobs.
- Deliver an engineering cockpit optimized for dense information display, visual document provenance, and low-latency auditability.
- Every metric, confidence score, and citation must be interactive and tied directly to its ground-truth source.

### 2.2 Color & Contrast Discipline
- **Canvas**: `#0b0f19` (Obsidian Slate).
- **Elevated Surfaces**: `#111827` (Card), `#162032` (Hover), `#1e293b` (Code/Citations).
- **Single Chromatic Voltage**: `#3b82f6` (Electric Cobalt) — used exclusively for primary CTAs, active states, and verified citation pills.
- **Strictly No Purple "AI" Gradients**: AI capability is demonstrated through transparent reasoning steps, sub-query decomposition traces, and CRAG reflection scores, not cosmetic purple glow.

### 2.3 Typographic Hierarchy
- **Sans-Serif (`Inter`)**: Page titles, section headings, chat messages, and UI labels.
- **Monospace (`JetBrains Mono`)**: Citations (`[p.3 #2]`), bounding-box coordinates (`[0.12, 0.45, 0.88, 0.92]`), latency benchmarks (`142ms`), CRAG confidence scores (`0.884`), and raw JSON telemetry.

---

## 3. Component Hierarchy & UX Flow

1. **Service Connectivity Bar**:
   - Real-time heartbeat indicators for Gateway (`:8000`), Qdrant (`:6333`), and Redis (`:6379`).
2. **Retrieval Mode Selector**:
   - `Auto`: Dynamic intent classification.
   - `Agentic Multi-Hop`: Decomposes complex comparative questions into sub-queries with CRAG reflection.
   - `Direct`: Single-hop hybrid dense + sparse retrieval.
3. **Collapsible Agent Reasoning Traces (`<details class="agent-reasoning">`)**:
   - Displays sub-queries, CRAG evaluation chips (`CONFIDENT`, `AMBIGUOUS`, `REFUSE`), and execution steps.
4. **Interactive Visual Provenance**:
   - Clicking any citation badge opens the PDF provenance viewer highlighting exact bounding box coordinates on the rendered canvas.
5. **Multimodal Evidence Panels**:
   - Markdown-rendered data tables with alternating row zebra-striping.
   - Figure cards with thumbnail previews and extracted OCR descriptions.
6. **Continuous Evaluation & RAGOps Controls**:
   - Instant feedback (`👍 Helpful` / `👎 Inaccurate`).
   - Reporting inaccurate answers automatically logs hard-negative triplets to `/data/ragops/hard_negatives.jsonl` for contrastive reranker fine-tuning.
