---
version: alpha
name: Enterprise-Multimodal-RAG-Console
description: |
  An enterprise-grade, high-density AI cockpit designed for multimodal retrieval-augmented generation.
  Built on an obsidian slate canvas (`#0b0f19`) with elevated card surfaces (`#111827`) and hairline slate
  borders (`#1f293d`), punctuated by a single restrained electric cobalt accent (`#3b82f6`) and semantic
  telemetry indicators (emerald `#10b981` for healthy service nodes, amber `#f59e0b` for ambiguous CRAG hops,
  crimson `#ef4444` for retrieval refusals). Typography pairs crisp sans-serif ('Inter', system-ui) for maximum
  scanning density with 'JetBrains Mono' for low-level vector telemetry, citations, bounding-box coordinates,
  and latency breakdowns. Rejects generic SaaS tropes, purple AI glows, and floaty glassmorphism in favor of
  software-craft precision, high contrast, and deep provenance transparency.

colors:
  primary: "#3b82f6"
  primary-hover: "#60a5fa"
  primary-focus: "#2563eb"
  on-primary: "#ffffff"
  canvas: "#0b0f19"
  surface-card: "#111827"
  surface-hover: "#162032"
  surface-elevated: "#1f2937"
  surface-code: "#1e293b"
  surface-accent-glow: "rgba(59, 130, 246, 0.15)"
  hairline: "#1f293d"
  hairline-strong: "#374151"
  hairline-subtle: "rgba(255, 255, 255, 0.05)"
  ink: "#f3f4f6"
  ink-secondary: "#d1d5db"
  ink-muted: "#9ca3af"
  ink-tertiary: "#6b7280"
  semantic-success: "#10b981"
  semantic-success-glow: "rgba(16, 185, 129, 0.20)"
  semantic-warning: "#f59e0b"
  semantic-warning-glow: "rgba(245, 158, 11, 0.20)"
  semantic-danger: "#ef4444"
  semantic-danger-glow: "rgba(239, 68, 68, 0.20)"
  semantic-info: "#38bdf8"
  citation-badge: "#1e293b"
  citation-badge-text: "#93c5fd"

typography:
  display-lg:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: -0.5px
  headline:
    fontFamily: "'Inter', sans-serif"
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: -0.2px
  section-header:
    fontFamily: "'Inter', sans-serif"
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: 0.6px
    textTransform: uppercase
  card-title:
    fontFamily: "'Inter', sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: 0
  body-md:
    fontFamily: "'Inter', sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0
  body-sm:
    fontFamily: "'Inter', sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  caption:
    fontFamily: "'Inter', sans-serif"
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0
  button:
    fontFamily: "'Inter', sans-serif"
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.0
    letterSpacing: 0
  code:
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: 0
  badge-mono:
    fontFamily: "'JetBrains Mono', monospace"
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0

rounded:
  none: 0px
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  xl: 16px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  base: 16px
  lg: 20px
  xl: 24px
  xxl: 32px
  section: 48px

components:
  top-nav:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    typography: "{typography.headline}"
    height: 54px
    borderBottom: "1px solid {colors.hairline}"
  sidebar:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    borderRight: "1px solid {colors.hairline}"
    width: 380px
  service-pill:
    backgroundColor: "rgba(255, 255, 255, 0.03)"
    textColor: "{colors.ink-muted}"
    typography: "{typography.caption}"
    rounded: "{rounded.md}"
    border: "1px solid {colors.hairline}"
    padding: 8px
  service-pill-active:
    backgroundColor: "rgba(16, 185, 129, 0.08)"
    textColor: "{colors.ink}"
    border: "1px solid rgba(16, 185, 129, 0.3)"
  session-item:
    backgroundColor: "rgba(255, 255, 255, 0.02)"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    border: "1px solid {colors.hairline}"
    padding: 8px 12px
  session-item-active:
    backgroundColor: "{colors.surface-accent-glow}"
    textColor: "#60a5fa"
    border: "1px solid {colors.primary}"
  chat-message-user:
    backgroundColor: "{colors.surface-hover}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.lg}"
    border: "1px solid {colors.hairline}"
    padding: 14px 18px
  chat-message-assistant:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.lg}"
    border: "1px solid {colors.hairline}"
    padding: 18px 22px
  agent-reasoning-accordion:
    backgroundColor: "rgba(0, 0, 0, 0.25)"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    border: "1px solid {colors.hairline}"
    padding: 10px 14px
  crag-badge-confident:
    backgroundColor: "rgba(16, 185, 129, 0.15)"
    textColor: "{colors.semantic-success}"
    typography: "{typography.badge-mono}"
    rounded: "{rounded.pill}"
    padding: 2px 8px
  crag-badge-ambiguous:
    backgroundColor: "rgba(245, 158, 11, 0.15)"
    textColor: "{colors.semantic-warning}"
    typography: "{typography.badge-mono}"
    rounded: "{rounded.pill}"
    padding: 2px 8px
  crag-badge-refuse:
    backgroundColor: "rgba(239, 68, 68, 0.15)"
    textColor: "{colors.semantic-danger}"
    typography: "{typography.badge-mono}"
    rounded: "{rounded.pill}"
    padding: 2px 8px
  citation-badge:
    backgroundColor: "{colors.surface-code}"
    textColor: "{colors.citation-badge-text}"
    typography: "{typography.badge-mono}"
    rounded: "{rounded.xs}"
    border: "1px solid rgba(59, 130, 246, 0.3)"
    padding: 2px 6px
  multimodal-card:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.lg}"
    border: "1px solid {colors.hairline}"
    padding: 12px 16px
  provenance-modal:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    border: "1px solid {colors.hairline-strong}"
    padding: 24px
  telemetry-hud:
    backgroundColor: "rgba(11, 15, 25, 0.95)"
    textColor: "{colors.ink-muted}"
    typography: "{typography.badge-mono}"
    rounded: "{rounded.md}"
    border: "1px solid {colors.hairline}"
    padding: 10px 14px
  feedback-button:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    typography: "{typography.caption}"
    rounded: "{rounded.md}"
    border: "1px solid {colors.hairline}"
    padding: 4px 10px
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 8px 16px
    height: 38px
  input-text:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    border: "1px solid {colors.hairline}"
    padding: 10px 14px
---

# DESIGN.md — Enterprise Multimodal RAG Console

Specification following the **[getdesign.md](https://getdesign.md)** and **Google Stitch** standards.
This document serves as the single source of visual truth for AI coding agents and human engineers building and maintaining the Enterprise Multimodal RAG platform frontend.

---

## 1. Overview & Visual Identity

The Enterprise Multimodal RAG Console is built for deep technical exploration, visual PDF document provenance, multi-hop agentic reasoning transparency, and active learning evaluation.

Unlike consumer chatbots that favor friendly rounded bubbles and pastel gradients, this console embraces an **engineering-first, cockpit aesthetic**:
- **Canvas**: Dark obsidian slate (`#0b0f19`) provides deep immersion and high visual comfort during extended analysis sessions.
- **Surfaces**: A 3-step surface elevation ladder (`#111827` $\to$ `#162032` $\to$ `#1f2937`) delineates document management, live chat streams, and modal inspectors.
- **Restraint**: A single chromatic voltage — **Electric Cobalt** (`#3b82f6`) — is strictly reserved for primary actions, active session pills, and verified citation badges.
- **Precision**: Monospace typography (`JetBrains Mono`) anchors all low-level telemetry, bounding-box geometry, execution latencies, and CRAG reflection scores.

---

## 2. Core Design Directives & Anti-Patterns

### Anti-Patterns (STRICTLY FORBIDDEN)
1. **NO Purple "AI" Gradients**: Avoid indigo-purple-violet gradients, rainbow neon glows, or holographic backdrops. AI features are communicated through data density and transparent reasoning steps, not cosmetic gradient fills.
2. **NO Glassmorphism**: Avoid `backdrop-filter: blur(20px)` with semi-transparent frosted cards. Surface hierarchy must rely on distinct contrastive hex values and subtle hairlines (`#1f293d`).
3. **NO Excessive Border Radii**: Do not use bubbly 24px–32px radii for chat cards. Standard radius is strictly 8px (`{rounded.md}`) for inputs/buttons and 12px (`{rounded.lg}`) for cards.
4. **NO Decorative Floating Blobs**: Do not inject SVG animated background orbs or decorative mesh gradients.
5. **NO Unanchored Metrics**: Never display a percentage or score without units, confidence intervals, or sample sizes.

### Preferred Patterns
1. **Dense Information Architecture**: Prioritize compact layouts, clear column grids, and immediate data scannability over vast empty whitespace.
2. **Collapsible Transparency**: Multi-step agent traces and CRAG evaluations live inside collapsible `<details class="agent-reasoning">` accordions to keep primary answers readable while maintaining full auditability.
3. **Interactive Visual Provenance**: Citations are clickable badge pills (`[p. 3 #3]`) that trigger a modal PDF viewer highlighting the exact bounding box (`[x0, y0, x1, y1]`).
4. **Active Learning Telemetry**: Every assistant turn includes explicit evaluation controls (`👍 Helpful` / `👎 Inaccurate`) that pipe hard negatives directly into continuous evaluation pipelines.

---

## 3. Color Architecture & Semantic Tokens

```
[#0b0f19] Canvas (Deep Obsidian)
   ├── [#111827] Surface Card / Sidebar / Modals
   │      ├── [#162032] Surface Hover / Active List Items
   │      └── [#1e293b] Code Wells / Citation Wells / JSON Inspect
   └── [#1f293d] Hairline Borders (Subtle, 1px solid)
```

### Color Mapping Table
| Token | Hex / Value | Usage Description |
|---|---|---|
| `{colors.canvas}` | `#0b0f19` | Root page background, deep obsidian tone |
| `{colors.surface-card}` | `#111827` | Sidebar container, assistant message cards, modal dialogs |
| `{colors.surface-hover}` | `#162032` | User chat bubbles, list hover states, table header cells |
| `{colors.surface-code}` | `#1e293b` | Code blocks, citation badge backgrounds, raw JSON viewports |
| `{colors.hairline}` | `#1f293d` | 1px border on cards, dividers, and sidebar boundary |
| `{colors.primary}` | `#3b82f6` | Send button, active navigation items, citation badges |
| `{colors.semantic-success}` | `#10b981` | Qdrant/Redis healthy pulse dots, CRAG `CONFIDENT` status |
| `{colors.semantic-warning}` | `#f59e0b` | CRAG `AMBIGUOUS` corrective hop, low token warning |
| `{colors.semantic-danger}` | `#ef4444` | CRAG `REFUSE` fallback, service disconnection, error toast |
| `{colors.ink}` | `#f3f4f6` | Primary reading text (contrast ratio > 12:1 against canvas) |
| `{colors.ink-muted}` | `#9ca3af` | Secondary labels, timestamps, metadata, section headers |

---

## 4. Typography Scale & Fonts

- **Primary UI Sans**: `'Inter', system-ui, -apple-system, sans-serif`
- **Technical & Code Mono**: `'JetBrains Mono', 'Fira Code', monospace`

| Scale Token | Font Family | Size | Weight | Line Height | Usage |
|---|---|---|---|---|---|
| `display-lg` | Inter | 28px | 700 | 1.2 | Hero modal title, welcome headline |
| `headline` | Inter | 18px | 700 | 1.3 | Console header, modal headers |
| `section-header`| Inter | 12px | 600 | 1.4 | Sidebar category titles (`uppercase`, tracking 0.6px) |
| `card-title` | Inter | 14px | 600 | 1.4 | Document names, modal section titles |
| `body-md` | Inter | 14px | 400 | 1.55 | Assistant answers, user query bubbles |
| `body-sm` | Inter | 13px | 400 | 1.5 | Agent reasoning text, descriptions |
| `caption` | Inter | 11px | 400 | 1.4 | Timestamp, hard negative indicators, status labels |
| `button` | Inter | 13px | 500 | 1.0 | Action buttons, tabs, mode selectors |
| `code` | JetBrains Mono | 12px | 400 | 1.6 | Ingested table markdown, JSON payloads, Python snippets |
| `badge-mono` | JetBrains Mono | 11px | 500 | 1.2 | Citation badges (`[p.2]`), CRAG scores (`0.884`), latencies |

---

## 5. Layout & Spatial Architecture

The platform follows a responsive 2-column cockpit with modal drawers:
1. **Left Sidebar (`width: 380px`, sticky)**:
   - Platform branding with pulsing health indicators for Gateway, Qdrant, and Redis.
   - Conversation history list with active session highlights and delete controls.
   - Document Ingestion Dropzone (drag-and-drop PDF/multimodal upload, chunking telemetry).
   - Ingested Documents Registry with status badges (`Ready`, `Vectorized`, `Chunks: N`).
2. **Main Cockpit (`flex: 1`, scrollable chat viewport)**:
   - Header bar with retrieval mode selector (`Auto`, `Agentic Multi-Hop`, `Direct`), clear chat, and RAGOps observability modal trigger.
   - Message Stream:
     - User messages aligned right/compact in `{colors.surface-hover}`.
     - Assistant messages full-width in `{colors.surface-card}` with markdown rendering, syntax highlighting, and citation badges.
     - Collapsible Agent Reasoning Traces (`<details class="agent-reasoning">`) displaying sub-queries, CRAG evaluation chips, and multi-hop plans.
     - Multimodal cards for tabular and figure evidence.
     - Feedback toolbar (`👍 Helpful` / `👎 Inaccurate`).
   - Sticky Bottom Composer:
     - Multi-line autosizing textarea.
     - Primary send button (`{colors.primary}`).
     - Real-time token and chunk estimate preview.
3. **Inspector & Observability Modals**:
   - **Provenance Modal**: PDF page visualizer with highlighted bounding box coordinates.
   - **RAGOps Observability Modal**: Live rolling satisfaction %, hard-negative counts, and dataset export triggers.

---

## 6. Component Specifications

### 6.1 Service Status Heartbeat Pill
```html
<div class="pill active">
  <span class="dot"></span>
  <span class="name">Qdrant Vector DB</span>
  <span class="label">:6333</span>
</div>
```
- Active dot has `6px` diameter, `{colors.semantic-success}` background with `box-shadow: 0 0 6px var(--success)`.

### 6.2 Agent Reasoning & CRAG Reflection Badge
```html
<details class="agent-reasoning" open>
  <summary>
    <span>Agent Multi-Hop Execution (2 hops)</span>
    <span class="crag-badge-confident">CONFIDENT · 0.82</span>
  </summary>
  <div class="step-stream">
    <div class="step-item"><b>Sub-query 1:</b> Extract Q4 GPU server benchmarks</div>
    <div class="step-item"><b>Sub-query 2:</b> Compare candidate specs against baseline</div>
  </div>
</details>
```

### 6.3 Citation Badges & Visual Provenance
- Badges render as inline pills: `[p.2 #1]`.
- Clicking opens the Provenance Modal displaying the PDF page canvas with a highlighted red/cobalt rectangle overlay mapped from `bbox: [x0, y0, x1, y1]`.

### 6.4 Multimodal Evidence Cards
- **Tables**: Formatted as dark-mode ASCII/HTML tables with alternating row shading (`#111827` and `#162032`) and monospace font for tabular numbers.
- **Figures/Charts**: Rendered with thumbnail preview, caption, OCR extracted text, and a "View in Context" trigger.

### 6.5 RAGOps Feedback Toolbar
- Sits at the bottom right of every assistant answer:
```html
<div class="feedback-bar">
  <button class="feedback-btn thumbs-up" title="Helpful answer">👍 Helpful</button>
  <button class="feedback-btn thumbs-down" title="Report inaccurate or hallucinated answer">👎 Inaccurate</button>
</div>
```
- Submitting `👎 Inaccurate` immediately logs the query and retrieved context chunks as a hard-negative triplet (`triplet: (query, positive, negative)`) for contrastive re-ranking fine-tuning.

---

## 7. Motion & Transitions

- **Standard Ease**: `cubic-bezier(0.16, 1, 0.3, 1)` (snappy ease-out, no bouncing).
- **Duration**: `150ms` for hover and button clicks; `200ms` for modal fade-ins.
- **Streaming Pulse**: A subtle 1.5s infinite breathing animation on active retrieval indicators (`opacity: 0.4` $\to$ `1.0`).
- **Zero Decorative Motion**: No parallax scrolling, no animated 3D cards, no distracting page transitions.

---

## 8. Directives for AI Coding Agents

When adding or refactoring frontend code in this repository:
1. **Read `DESIGN.md` First**: Ensure all hex codes, font tokens, and component classes align with this specification.
2. **Match Existing CSS**: Update `ui/index.html` inline `:root` variables or dedicated stylesheets without introducing competing CSS frameworks.
3. **Check Contrast**: Body copy must always meet WCAG AAA (contrast ratio $\ge 7:1$) against `{colors.surface-card}` and `{colors.canvas}`.
4. **Preserve Monospace Data**: Latency figures (`124ms`), confidence scores (`0.88`), page numbers (`p. 3`), and coordinates must always be styled with `{typography.code}` or `{typography.badge-mono}`.
5. **Keep Components Self-Contained**: Do not install heavy third-party UI widget libraries when native semantic HTML (`<details>`, `<dialog>`, `<canvas>`) provides superior performance and transparency.
