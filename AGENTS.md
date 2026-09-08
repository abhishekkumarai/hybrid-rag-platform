# Agent Directives & UI Design Standards

## UI / UX Design Standards (Enforced for all Frontend & Web Work)

You must never generate generic, outdated "AI slop" interfaces (e.g., standard Bootstrap cards, garish saturated purple/blue gradients, fuzzy drop shadows, oversized rounded pills, or unstyled default layouts). Always adhere to the modern "Craft" aesthetic inspired by getdesign.md, Linear, Vercel, and Raycast.

### 1. Visual Hierarchy & Theme
- **Aesthetic**: Modern Craft / Technical Elegance. Default to obsidian/zinc dark mode unless light mode is explicitly requested.
- **Surfaces**: Layered depth using tone-on-tone neutrals (e.g., `zinc-950` base, `zinc-900` card, `zinc-800` borders/hover states).
- **Hairline Dividers**: Replace heavy drop shadows with 1px translucent borders (`border border-white/[0.08]` or `border-zinc-800`). Add subtle top-edge hairline highlights (`h-px bg-gradient-to-r from-transparent via-white/15 to-transparent`).
- **Glassmorphism**: Use translucent card backgrounds with blur (`bg-zinc-900/60 backdrop-blur-md`).

### 2. Typography & Lettering
- **Primary Sans**: Geist Sans or Inter. Headings must use tight letter-spacing (`tracking-tight` / `-0.025em`) and balanced text wrapping (`text-balance`).
- **Secondary Monospace**: Geist Mono or JetBrains Mono for all metadata, status badges, timestamps, numerical values, and category tags (`font-mono text-[11px] uppercase tracking-wider`).
- **High Contrast Ratios**: Crisp foreground text (`text-zinc-100` / `#f4f4f5`) paired with intentional muted secondary text (`text-zinc-400` / `text-zinc-500`).

### 3. Components & Geometry
- **Corners & Radii**: Disciplined radii. Buttons and inputs use `rounded-md` (6px); cards use `rounded-lg` (8px) or `rounded-xl` (12px). Always ensure nested elements follow $R_{inner} = R_{outer} - Padding$.
- **Buttons**:
  - Primary: High-contrast solid (crisp white background with dark text `bg-white text-zinc-950 hover:bg-zinc-200 font-medium`) or single focused accent (e.g., cobalt `#3b82f6` or amber `#f5a623`).
  - Secondary / Ghost: Subtly bordered translucent buttons (`bg-zinc-900 border border-white/10 hover:bg-zinc-800 text-zinc-300`).
- **Badges & Indicators**: Small status indicator pills with glowing pulsing dots (`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono`).
- **Icons**: Clean geometric iconography (Lucide or Phosphor) with consistent thin stroke widths (`strokeWidth={1.5}` or `1.75`).

### 4. Interactive Polish & Transitions
- Micro-transitions must be snappy and subtle (`duration-150 ease-out`).
- Include hover elevation: subtle border brightens (`hover:border-white/20`) or slight scale transforms.
- Keyboard hints: Include styled `<kbd>` chips (`border border-zinc-700 bg-zinc-800 font-mono text-[10px] px-1.5 py-0.5 rounded text-zinc-400`).

### 5. Project Foundation & System Alignment
- Every frontend project in this workspace must maintain and strictly follow [`DESIGN.md`](file:///C:/Users/abhi3/Documents/work/rag/DESIGN.md) in the project root to enforce design tokens, palette variables, and component guidelines across subsequent edits.
- Consult [`claude.md`](file:///C:/Users/abhi3/Documents/work/rag/claude.md) for behavioral rules and component reuse hierarchy.

---

## Technical & Architectural Guidelines (RAG Codebase)

1. **Contracts First**:
   - All data exchange between retrieval services, ingestion workers, and API gateways must strictly adhere to Pydantic models in `contracts/` (`contracts/agent.py`, `contracts/feedback.py`, `contracts/retrieval.py`, `contracts/ingestion.py`).
2. **Deterministic Citations & Bounding Boxes**:
   - Every candidate and citation chunk must preserve document ID, page number, and bounding box coordinates `[x0, y0, x1, y1]` for visual PDF provenance.
3. **Corrective RAG (CRAG) Guardrails**:
   - Every agentic multi-hop retrieval step must run through `CRAGEvaluator`, classifying candidate sets into `CONFIDENT`, `AMBIGUOUS`, or `REFUSE`.
4. **Active Learning (RAGOps)**:
   - User feedback logs (`👍 Helpful` / `👎 Inaccurate`) are persisted to `/data/ragops/` and Redis, automatically mining hard-negatives on thumbs down for contrastive re-ranking fine-tuning.
5. **Testing & Code Quality**:
   - Always verify changes with `python -m ruff check .` and `python -m pytest tests/ -q`. Ensure 100% passing tests and zero lint errors.
