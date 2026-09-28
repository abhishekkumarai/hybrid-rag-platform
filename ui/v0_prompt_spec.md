# v0 Production Prompt & Wireframe Design Specification

Use the following complete, structured prompt in **[v0.dev](https://v0.dev)** to generate or iterate on the NextGen **Enterprise Multimodal RAG Mission Control** UI.

---

## 1. Quick Copy-Paste Prompt for v0.dev

```markdown
Create a high-density, engineering-grade "Enterprise Multimodal RAG Mission Control" cockpit in Next.js (App Router), React, Tailwind CSS, Lucide React icons, and shadcn/ui primitives.

Aesthetic & Theme:
- "Modern Craft" / "Obsidian Zinc" aesthetic (Linear / Raycast / getdesign.md inspired).
- Background: deep obsidian canvas (#09090b), elevated cards (#121214), zinc-800 interactive elements (#18181b), 1px translucent hairline borders (border-white/[0.08] or border-zinc-800).
- Typography: Geist Sans for UI text/headings, JetBrains Mono for telemetry, latencies, bounding-box coordinates, and token counts.
- Accent colors: Telemetry Emerald (#10b981) for healthy status, live websockets, and verified provenance; Muted Amber (#f59e0b) for ambiguous CRAG hops; Soft Crimson (#ef4444) for hallucination refusals. Strictly NO purple AI gradients.

Architecture (3-Pane Cockpit Layout):
1. Left Navigation & Corpus Rail (260px, fixed height):
   - Project Selector: "Enterprise Financial AI" on cluster "prod-us-west-1" with pulsing green heartbeat dot.
   - Navigation links: Mission Control (Active), Documents & Corpus, Knowledge Graph, Observability & Telemetry, RAGOps & Fine-tuning, Settings.
   - Scoped PDF document inventory with status badges (e.g. "doc_sec_10k_nvda.pdf" · 142 chunks · 100% indexed · OCR v2.4 Active).
   - Drag-and-drop PDF upload zone with dashed hairline border.

2. Center Chat & Reasoning Workspace (Fluid):
   - Header Bar: Workspace title with inline rename, Live Service Connectivity Heartbeats (API Gateway :8000 Connected, Qdrant :6333 [12,480 vectors], Redis Cache :6379 [99.2% hit rate]), Share session button, and Retrieval Mode selector pills (Auto CRAG [Active], Agentic Multi-Hop, GraphRAG, Direct RRF).
   - Chat Stream:
     * User query card in elevated zinc with timestamp.
     * Collapsible Agent Reasoning trace (<details> / Accordion): CRAG multi-hop sub-query decomposition ("NVDA FY24 Datacenter revenue schedule", "Operating cash flow reconciliation"), BM25 + dense vector scores, FlashRank cross-encoder re-ranking (Top-80 -> Top-6), and CRAG Self-Correction Gate ("CONFIDENT 0.94" emerald pill).
     * Assistant Multimodal Synthesis: Grounded text synthesis, financial reconciliation data table with crisp hairline borders, and extracted OCR figure preview card (Figure 4.2 with bounding box [124, 310, 420, 65]).
     * Inline interactive provenance citation pills: "[doc_sec_10k_nvda.pdf p.14 #2]" with glowing emerald hover state.
     * Active Learning RAGOps Feedback Bar: Helpful / Inaccurate buttons, latency telemetry breakdown ("412ms total: 18ms BM25 · 34ms Qdrant · 52ms Rerank · 308ms LLM"), and token count badge.
   - Floating Bottom Input Island: Sleek docked command bar with mode indicator, LLM model switcher dropdown ("Llama-3.2:3b [2.2/6.0 GB VRAM]"), prompt textarea, attachment trigger, and high-contrast emerald submit button.

3. Right Contextual Visual Provenance & Telemetry Inspector (360px):
   - Header: "Visual Ground-Truth Inspector" with close button.
   - Target citation badge: "[doc_sec_10k_nvda.pdf p.14 #2]" (Verified Match, Cosine: 0.892, Cross-Encoder: 0.961).
   - Document Preview Canvas: Rendered PDF document page replica with luminous SVG bounding box rectangle overlay ([0.14, 0.32, 0.85, 0.48]) highlighting the exact cited financial paragraph.
   - Ground-truth chunk text card with highlighted matching keywords.
   - Monospace latency waterfall breakdown: BM25 Sparse (18ms), Qdrant Dense HNSW (34ms), FlashRank Cross-Encoder (52ms), Llama-3.2:3b generation (308ms).
```

---

## 2. Component Hierarchy in v0

| Component | Responsibility | Props / State |
|---|---|---|
| `MissionControlHeader` | Top global status bar, service heartbeats (`:8000`, `:6333`, `:6379`), search command bar (⌘K) | `services`, `activeProject` |
| `CorpusNavigationRail` | Left navigation links, scoped PDF list with chunk count, upload zone | `documents`, `activeTab`, `onUpload` |
| `ChatCockpit` | Main conversational stream, CRAG reasoning accordion, multimodal tables, feedback bar | `messages`, `mode`, `onCitationClick` |
| `ReasoningTraceAccordion` | Multi-hop query decomposition, sub-queries, CRAG confidence badge (`CONFIDENT 0.94`) | `traceSteps`, `cragScore` |
| `MultimodalEvidenceTable` | Financial reconciliation table, zebra hairline dividers, inline citation tags | `tableData`, `citations` |
| `ProvenanceInspector` | Right-side drawer, visual PDF canvas with SVG bounding box `[x0, y0, x1, y1]`, raw chunk | `activeCitation`, `onClose` |
| `TelemetryWaterfall` | Monospace latency breakdown (BM25, Qdrant HNSW, FlashRank, LLM), VRAM monitor | `latencyMetrics`, `vramUsage` |
| `ObservabilityConsole` | Telemetry grid, p50/p95/p99 sparklines, RAGOps active learning hard-negative mining table | `timeWindow`, `hardNegatives` |

---

## 3. Design Tokens (Obsidian Zinc Craft)

```css
:root {
  --canvas: #09090b;               /* Deep Obsidian base */
  --surface-card: #121214;         /* Zinc-900 elevated card */
  --surface-elevated: #18181b;     /* Zinc-800 interactive surface */
  --surface-well: #16161a;         /* Code & citation well */
  --hairline: rgba(255, 255, 255, 0.08); /* 1px translucent boundary */
  
  --ink: #fafafa;                  /* High contrast white */
  --ink-secondary: #a1a1aa;        /* Secondary zinc-400 */
  --ink-muted: #71717a;            /* Muted zinc-500 */
  
  --telemetry-emerald: #10b981;    /* Healthy service / Confident CRAG */
  --telemetry-amber: #f59e0b;      /* Ambiguous CRAG / Fallback */
  --telemetry-crimson: #ef4444;    /* Refusal / Hallucination defense */
  --telemetry-cyan: #14b8a6;       /* Dense vector / Sparse search */
}
```
