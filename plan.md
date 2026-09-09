# UI Modernization & Architecture Implementation Plan

## Goal Description
Redesign and upgrade the Hybrid RAG Platform single-page web interface (`ui/index.html`) into a state-of-the-art, high-usability "Mission Control" workstation. The new interface will incorporate modern CSS/icon libraries (Tailwind CSS, Lucide Icons, Geist Sans, and JetBrains Mono), fix missing controls (dynamic Ollama model selector dropdown, retrieval mode segmented pills, `top_k` and `top_rerank` tuning sliders, and streaming SSE toggle), and align with the `Obsidian Zinc Craft` design system generated via Stitch.

---

## Stitch Connection & Master Prompt

### Stitch Project Details
- **Stitch Project URL**: [https://stitch.google.com/projects/2131036001734639932](https://stitch.google.com/projects/2131036001734639932)
- **Generated Screen**: `28c9d70c505547c6bba5ed530ba024d5` ("RAG Mission Control")
- **Design System Asset**: `assets/f63a2590042b40fe8ae5ad572eefd00a` (`Obsidian Zinc Craft`)

### Master Prompt for stitch.google.com
```markdown
High-precision Enterprise Multimodal RAG Mission Control desktop dashboard in an Obsidian/Zinc dark craft aesthetic (Linear/Vercel/Raycast inspired) with Geist Sans and JetBrains Mono monospace telemetry.

Header Bar:
- Brand mark badge: 'HYBRID RAG // MISSION CONTROL' with glowing green indicator dot.
- Active Model Selector dropdown button displaying 'Llama 3.1 8B (Quality / 8K Context)' with dropdown items: 'Llama 3.2 3B (Fast / VRAM)', 'Llama 3.1 8B (Quality / 8K Context)', 'Qwen 2.5 7B', 'DeepSeek-R1 8B', and '+ Custom Model'.
- Segmented retrieval mode selector pills: 'Auto CRAG' (active), 'Agentic Multi-Hop', 'GraphRAG', 'Direct'.
- Inline compact micro-sliders: Top-K (value: 20, range 5-100) and FlashRank Rerank depth (value: 6, range 1-20).
- Streaming SSE toggle switch with active glow.
- Hardware health pill badge with pulsing emerald beacon: 'RTX 4090 - Quality Profile' with micro stats (21.4 / 24 GB VRAM, 44°C).

Left Sidebar:
- Sessions Section: Search bar with shortcut '⌘K', 'Active Sessions' with list items like 'Financial 10-K Cross-Audit' (Active, 14.2k tokens, 2m ago), 'Q3 Vector Cluster Anomaly' (8.9k tokens, 1h ago), 'Biomedical Protocol Graph' (22.1k tokens, 4h ago).
- Ingested Documents Section: 'INGESTED CORPUS (12 files)':
  - 'SEC-10K-2024-NVDA.pdf' (142 chunks, 99.4% indexed, PDF badge)
  - 'Transformer-Arxiv-v3.pdf' (48 chunks, 100% indexed)
  - 'Enterprise-Arch-Blueprint.pdf' (85 chunks, 100% indexed)
- Upload dropzone: Compact dotted border area with 'Drop PDF/DOCX or browse' + upload action button.

Center Stage (Conversation & Agentic Reasoning Stream):
- Multi-turn stream: User query: 'Synthesize NVIDIA's FY24 Datacenter gross margin trajectory and verify against the raw 10-K cash flow table.'
- Expandable step-by-step CRAG Agent Reasoning accordion with status pill 'CRAG: Corrective Retrieval Verified (0.94 Confidence)':
  - Sub-queries: '1. NVDA FY24 Datacenter revenue & GM margins', '2. Cash flow statement capex vs gross profit cross-check'
  - Monospace trace log showing Vector Search (Top-20 retrieved in 14ms), FlashRank Cross-Encoder rerank score (Top-6 filtered, max score 0.982), Hallucination Detector check (0.02 risk score).
- Synthesis response card formatted with pristine markdown, inline numeric highlights, and comparison table.
- Rich Interactive Citation Badges & Cards:
  - '[Doc 1: SEC-10K-2024-NVDA.pdf - Page 42, Bounding Box: [x:124, y:310, w:420, h:65]]' with interactive view provenance button.
  - '[Doc 2: SEC-10K-2024-NVDA.pdf - Page 48, Table 4.1]'.
- RAGOps interactive feedback row: Thumbs Up / Down buttons, 'Report Hallucination', 'Copy Context JSON', 'Export Trace'.
- Polished Bottom Chat Command Bar: Floating dark input box with placeholder 'Ask questions across multi-hop corpus or type / for commands...', action buttons for 'Attach Document', 'Web-Augment Toggle', 'Prompt Presets', 'Send (↵)' button, and keyboard legend badge '↵ Send · ⇧↵ Newline · ⌘/ Inspector'.

Right Collapsible Inspector Drawer:
- Header with tabs: 'Visual PDF Provenance' (Active), 'Knowledge Graph', 'Telemetry'.
- Visual PDF Provenance view: Realistic rendered preview of an enterprise financial PDF report page with highlighted paragraph covered by a semi-transparent emerald glowing bounding box [BBox: p.42: 124,310,420,65], zoom controls (+/- / fit), snippet text OCR extraction panel, and confidence rating 98.7%.
- Knowledge Graph preview card: Associative entity traversal snippet ('NVIDIA' -> 'Datacenter Segment' -> 'Hopper GPU Arch' -> 'FY24 Revenue $47.5B').
- Real-time Telemetry gauge stats:
  - TTFT (Time-to-first-token): 142ms
  - Total Latency: 1.18s
  - Generation Speed: 86.4 tok/sec
  - Retrieval P95: 38ms
  - Context Precision: 96.2%

Visual craft: Obsidian zinc background (#09090b / #121214), crisp micro-borders (#27272a), subtle radial glows, high-density data presentation with impeccable craftsmanship.
```

---

## Phased Implementation Roadmap

### Phase 1: Backend Model Discovery & Parameter Propagation
- **Objective**: Allow the frontend to discover available Ollama models dynamically and pass all tuning parameters down to the retrieval and generation pipeline.
- **Changes**:
  1. Add `GET /api/v1/models` in [`services/gateway/api.py`](file:///C:/Users/abhi3/Documents/work/rag/services/gateway/api.py):
     - Queries `${OLLAMA_BASE_URL}/api/tags`.
     - Returns list of model tags (e.g. `["llama3.2:3b", "llama3.1:8b", "qwen2.5:7b"]`), current default model, and profile metadata.
     - Gracefully falls back to default profile models if Ollama is starting up or offline.
  2. Ensure [`ChatRequest`](file:///C:/Users/abhi3/Documents/work/rag/services/gateway/api.py#L121-L129) fields (`model`, `top_k`, `top_rerank`, `stream`, `mode`) are fully respected and logged in query telemetry.
  3. Add unit test in `tests/unit/test_models_api.py` validating the endpoint and fallback behavior.

### Phase 2: Modern Design System Foundation & Component Library
- **Objective**: Elevate the UI with modern CSS and component standards without introducing a heavy build step.
- **Design Tokens & Libraries**:
  - **CSS**: Modern Tailwind CSS utility layer loaded via CDN (`@tailwindcss/browser` or standard Tailwind script) combined with CSS custom properties for the `Obsidian Zinc Craft` palette.
  - **Typography**: `Geist Sans` for clean, tight geometric headings and body text; `JetBrains Mono` for tabular metrics, bounding box coordinates, and latency badges.
  - **Iconography**: `Lucide Icons` (consistent 1.5px/1.75px optical stroke width).
  - **Hairline Dividers & Surfaces**: Tone-on-tone Zinc/Obsidian surfaces (`#09090b` canvas, `#121214` card, `#18181b` elevated), 1px translucent borders (`border-white/[0.08]`), and top-edge specular hairline highlights.

### Phase 3: Header Controls & Missing Model Selection Flags
- **Objective**: Implement the missing controls and selectors requested by the user.
- **Components to Add in Cockpit Header**:
  1. **Dynamic Model Selector Dropdown**:
     - Displays active model badge with icon and architecture tag (e.g. `Llama 3.2 3B · Fast`).
     - Dropdown menu lists all installed Ollama models with parameters (size, quantization, modified time).
     - "+ Custom Model..." option to specify an arbitrary Ollama model tag.
  2. **Retrieval Mode Segmented Switch**:
     - `Auto (CRAG)`: Evaluator-driven retrieval with automatic reformulation.
     - `Agentic`: Multi-hop query decomposition with full reasoning trace.
     - `GraphRAG`: Associative graph traversal and entity neighborhood.
     - `Direct`: Standard hybrid retrieval without multi-hop overhead.
  3. **Retrieval & Rerank Tuning Popover**:
     - Sliders for `top_k` (5 to 100, default 20) and `top_rerank` (1 to 20, default 6) with real-time numeric display badges.
     - Toggle switch for `stream` (SSE streaming vs JSON response).
  4. **Hardware Health Indicator**:
     - Pulsing beacon pill indicating Ollama status, Qdrant connectivity, and active profile (`Quality` / `Fast`).

### Phase 4: Chat Stream & Agentic Reasoning Stream Refinement
- **Objective**: Modernize the multi-turn chat experience, reasoning transparency, and citation interaction.
- **Key Enhancements**:
  1. **Expandable Step-by-Step CRAG Reasoning Accordion**:
     - Clear breakdown of Sub-queries, Hybrid Retrieval scores, FlashRank rerank rankings, and CRAG confidence classification (`CONFIDENT`, `AMBIGUOUS`, `REFUSE`).
  2. **Rich Citation Badges**:
     - Document title, page number, confidence pill, and bounding box chip (`[x0, y0, x1, y1]`).
     - Clicking any citation automatically opens the right inspector drawer and focuses the visual provenance preview.
  3. **Continuous RAGOps Feedback Bar**:
     - Clean `👍 Helpful` / `👎 Inaccurate` buttons attached to each assistant response.
     - Active notification on thumbs down: "Hard negative mined for contrastive reranker fine-tuning".
  4. **Chat Command Bar**:
     - Auto-resizing textarea with keyboard hints (`↵ Send`, `⇧↵ Newline`, `⌘K Search`).
     - Attachment button to trigger document upload modal.

### Phase 5: Visual PDF Provenance & Deep Telemetry Inspector
- **Objective**: Perfect the visual citation inspection experience.
- **Tabs in Collapsible Inspector**:
  1. **Visual PDF Provenance (Default)**:
     - Zoomable, pan-able high-resolution page canvas rendered from `/api/v1/preview`.
     - SVG glowing bounding box overlay highlighting the exact citation coordinates.
     - OCR text snippet card with copy button.
  2. **GraphRAG Explorer**:
     - Interactive SVG/Canvas node-link visualization of extracted entities and predicates.
  3. **Telemetry & System Observability**:
     - Gauges for TTFT, total latency, tok/sec, Qdrant search time, and Redis task queue metrics.

### Phase 6: Verification, Testing & Documentation
- **Objective**: Complete end-to-end verification and maintain 100% test pass rate.
- **Steps**:
  1. Run `python -m ruff check .` to verify clean linting.
  2. Run `python -m pytest tests/unit -v` to ensure zero regressions in backend contracts and services.
  3. Test the modernized UI on `http://localhost:8001/` across multiple viewports (Desktop, Tablet, Mobile).
  4. Update [`docs/frontend-guidelines.md`](file:///C:/Users/abhi3/Documents/work/rag/docs/frontend-guidelines.md) and [`README.md`](file:///C:/Users/abhi3/Documents/work/rag/README.md) with the new UI capabilities.

---

## Verification Plan

### Automated Tests
```bash
# Verify linting
python -m ruff check .

# Run full unit test suite
python -m pytest tests/unit -v

# Run models API endpoint tests
python -m pytest tests/unit/test_models_api.py -v
```

### Manual Verification
1. Open [http://localhost:8001/](http://localhost:8001/) in a browser.
2. Verify that the Model Selector dropdown populates models from Ollama (or fallback defaults) and allows selecting different models.
3. Switch retrieval modes (`Auto CRAG`, `Agentic`, `GraphRAG`, `Direct`) and verify the active indicator updates.
4. Adjust `top_k` and `top_rerank` sliders and verify the numbers update reactively and are included in `/api/v1/chat` requests.
5. Send a multi-hop question (e.g. "Synthesize the main architecture advantages of hybrid retrieval").
6. Verify streaming SSE tokens, expandable Agent Reasoning steps, citation cards with bounding boxes, and RAGOps feedback logging.
7. Click a citation to verify the PDF page preview loads with the highlighted bounding box overlay.

---
---

# ADDENDUM (2026-09-09): "Retrieval Intelligence Workbench" — Light Theme Redesign

## Status of the plan above
Everything above this addendum describes an **earlier, separate Stitch project** — the dark "Obsidian Zinc
Craft" Mission Control design (Stitch project `2131036001734639932`). Per `wip.md` Phase 16, that design's
backend prerequisites (model discovery endpoint, tuning parameters) shipped and are marked complete. This
addendum documents a **second, distinct** UI direction started fresh in a later session: a light-theme
redesign the user explicitly asked to look nothing like the dark cockpit above, generated as a brand new
Stitch project rather than an iteration on the old one.

## Goal Description (this initiative)
Design a light, off-white, low-cognitive-load, multi-page "Retrieval Intelligence Workbench" covering every
functionality in this codebase: session-scoped chat workspaces, per-session document scoping (NotebookLM-
style Sources panel + a context-aware global Library), model/hyperparameter tuning, observability, RAGOps
feedback, and GraphRAG exploration. Explicit constraints from the user: light theme, off-white background,
Material Design 3 + fluid motion, left nav rail with a right panel hidden by default, fully responsive
(including mobile), built via stitch.google.com, and deliberately avoiding generic "AI slop" chat-UI
conventions (no dark mode, no purple/blue AI gradients, no glassmorphism, no chat-bubble ovals).

## Stitch Connection
- **Stitch Project**: `10226929593327386385` —
  [https://stitch.withgoogle.com/project/10226929593327386385](https://stitch.withgoogle.com/project/10226929593327386385)
- **Design System Asset**: `assets/16587086430143241056` ("Warm Ink & Ember")
- **Palette**: paper `#FAF9F5`, ink `#1C1A15`, Ember accent `#C2410C`, Moss `#4B6B4F`, Clay `#B08947`
- **Type**: Inter (UI text) + JetBrains Mono (every numeric/doc_id/model name), `ROUND_EIGHT` corner radius

The full master design-system brief and all 8 per-screen prompts (verbatim, as sent to
`generate_screen_from_text`) live in this session's conversation transcript — not duplicated here to avoid
drift between two copies; treat the conversation log as source of truth for prompt wording if any screen
needs regenerating.

## Completed — all 8 screens generated and content-verified (2026-09-09)
1. **Project + design system created and applied** — confirmed via `get_project`: all Material 3 tonal
   color tokens resolved correctly from the custom palette.
2. **Workspace Gallery** — landing page, grid of session/workspace cards, new-workspace modal with presets,
   search/filter.
3. **Chat** — 4-zone layout (nav rail / persistent NotebookLM-style Sources sub-panel / message thread /
   hidden-by-default right inspector), citation badges, latency readouts, calm Clay-toned low-confidence
   refusal callout, per-message feedback.
4. **Library** — context-aware "This workspace (N) / All documents (N)" scope switcher, upload dropzone
   with live Probe→Route→Parse→Chunk→Index stepper, monospace document data table.
5. **Knowledge Graph** — force-directed entity/relation canvas, query bar that traces relation paths, stat
   tiles, entity inspector.
6. **Observability** — stat tiles with sparklines, per-query latency waterfall (dense/sparse/fusion/rerank/
   TTFT/generation), service health grid, Redis queue + DLQ panel with replay action.
7. **RAGOps** — satisfaction gauge, feedback table, hard-negative mining panel, "Export training dataset
   (JSONL)" CTA.
8. **Models & Tuning** — embedding/reranker/generation model slot cards with a 6GB VRAM budget meter,
   retrieval-mode selector, hyperparameter sliders (temperature, top-k, confidence threshold, token budget),
   presets.
9. **Settings** — appearance, API & security, notifications, account, danger zone.

Each of screens 4–9 was verified by downloading its actual rendered HTML (not just trusting the title
metadata, after an earlier duplicate turned out to be mislabeled) and grepping for screen-specific content —
e.g. Library's HTML contains "doc_id" / "Drop PDFs" / parser-route language, Knowledge Graph's contains
"entities" / "relations" / "traversal", Models & Tuning's contains "VRAM" / "Embedding Model" / "Reranker",
etc. All checked out correctly.

See `todo.md` Phase 17 for the itemized checklist tracking these same items.

## Pending follow-up work
- **Cleanup: stray duplicate screens** — the unstable generation window (see resolved blocker below)
  produced extra duplicate renders: 2× "Workspace Gallery", ~3× "Chat"/"Workspace Chat", 2× "Library". No
  `delete_screen` MCP tool exists, so remove the unwanted duplicates by hand in the Stitch UI.
- **Wire the approved designs into `ui/index.html`** — Phase 18 (see `todo.md`), started and mostly shipped
  2026-09-09. **6 of 8 pages are live and verified in a real browser against the running stack**: Workspace
  Gallery, Chat (incl. live SSE streaming), Library, Observability, RAGOps, Models & Tuning. Knowledge Graph
  and Settings remain styled placeholders (Phase 18.5 / 18.9).

## Deployed to the main checkout (2026-09-09) — superseded the other session's WIP
`ui/index.html` now serves the new light-theme build live at `http://localhost:8001/`. Getting here required
resolving a real conflict: the main checkout's `ui/index.html` had 984 uncommitted lines from another active
session implementing the original dark "Obsidian Zinc Craft" plan (model selector, retrieval-mode switch,
tuning popover, tabbed inspector, hardware pill, telemetry gauges) — genuine working functionality. Per
explicit user decision (shown the diff first, then chose to proceed with the light theme), that work was
superseded rather than merged line-by-line:
1. Preserved in full as `ui/dark_theme_wip_reference.html` before any overwrite — nothing lost.
2. Its *functionality* (not visual style) was ported into the new Observability, RAGOps, and Models & Tuning
   pages — same endpoints (`/api/v1/models`, `/api/v1/metrics`, `/api/v1/queue/*`, `/api/v1/feedback/summary`),
   restyled to match Warm Ink & Ember.
3. This branch's `ui/index.html` was then copied over the main checkout's and the Docker stack restarted
   (`docker-compose.yml` bind-mounts `./ui:/app/ui`, so the change is live immediately on copy).
4. **Caught a real bug via actual browser testing, not just syntax-checking**: the router toggled the HTML
   `hidden` attribute, but pages also shipped with Tailwind's `hidden` *class* in their markup — every page
   but Gallery rendered blank. Fixed (`classList.toggle` instead), redeployed, re-verified: Chat renders its
   Sources panel + history and successfully sends/receives a live streamed message; Library/Observability/
   RAGOps/Models & Tuning all show real backend data (verified against actual figures — e.g. RAGOps showed
   45 feedback records, 48.9% satisfaction, 21 hard negatives).

Known follow-up items: Knowledge Graph and Settings pages, a mobile/responsive pass, removing now-dead old
dark-theme CSS/JS, and the Models & Tuning sliders/checkbox rendering with default browser accent color
instead of Ember (Tailwind's `accent-primary` utility didn't visibly apply — needs a follow-up look).

## Blocker hit 2026-09-09 (resolved)
`generate_screen_from_text` became unreliable partway through this batch: repeated client-side timeouts, one
explicit `"The service is currently unavailable"` error (which also briefly hit `list_screens` itself), and
no new screens landing even after ~15+ cumulative minutes of polling across both serial retries and a
5-request batch fired back-to-back. Lesson learned the hard way: a client-side timeout on this tool does
**not** mean the job failed — the Chat and Workspace Gallery screens both eventually completed successfully
after a long wait following an identical timeout, and on the next resume all 6 remaining screens eventually
appeared together after a further wait. What worked:
- Resubmit pending screens **one at a time**, not batched — batching multiple requests back-to-back is what
  produced the stray duplicate screens (a job's result appears to sometimes land against the wrong in-flight
  request).
- After each submission, poll `list_screens` patiently (multiple minutes, sometimes 10+) before concluding
  it failed and resubmitting.
- A `"service currently unavailable"` error on `list_screens` itself (not just the generate call) is a sign
  of a genuine transient outage — pause and retry the *read*, don't resubmit a *generation* in response to it.

## Verification performed
1. `get_project` / `list_screens` returns all 8 target screens present (plus known duplicates, see cleanup
   item above).
2. Each of the 6 screens generated in the second batch was downloaded and grepped for screen-specific
   content to confirm it matches its intended prompt, not just its title label.
3. Final project URL: [https://stitch.withgoogle.com/project/10226929593327386385](https://stitch.withgoogle.com/project/10226929593327386385)
