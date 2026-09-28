# Antigravity Agent Directives & UI Design Protocol

## UI / UX Design Directives (Priority 1: Figma MCP)

### 1. Mandatory Priority 1: Figma MCP for All UI Work
- **Primary Source of Truth**: For ANY UI/UX design, visual implementation, component creation, screen generation, or frontend refactoring, the **Figma MCP** (`figma-developer-mcp`) is the **Priority 1** authority.
- **Workflow Execution**:
  1. **Query & Inspect**: Before writing or modifying any frontend code or component markup, always query the target Figma file/nodes using Figma MCP tools (extract node trees, styles, layout dimensions, padding/gap tokens, and component properties).
  2. **Zero Guesswork / Hallucination**: Do not approximate or guess CSS styles, padding, component hierarchies, or color values when Figma design specs are available. Extract exact node attributes, flex/grid properties, and token bindings directly.
  3. **Visual & Asset Provenance**: Download and link SVG icons, illustrations, and images directly from Figma via the MCP server into the asset pipeline.
  4. **Design System & Token Parity**: Map extracted Figma styles and component variants directly to the design tokens defined in [`DESIGN.md`](DESIGN.md).

### 2. Secondary & Complementary Design Tooling
- **Multi-Screen Exploration**: If initial wireframes or multi-screen flows need exploration before finalized Figma canvas specs exist, leverage **Google Stitch MCP** (`stitch`) adhering to [`DESIGN.md`](DESIGN.md).
- **Component Implementation**: Use **shadcn/ui MCP** (`shadcn`) to install headless/Tailwind primitives that match the Figma design structure.
- **Rapid Prototyping**: Use **v0 MCP** for complex component generation, always conditioned on Figma node schemas and constraints.

---

## UI / UX Craft Standards (Visual & Interaction Guidelines)

Adhere strictly to the modern "Craft" aesthetic inspired by getdesign.md, Linear, Vercel, and Raycast:

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
- Every frontend project in this workspace must maintain and strictly follow [`DESIGN.md`](DESIGN.md) in the project root to enforce design tokens, palette variables, and component guidelines across subsequent edits.
- Consult [`docs/frontend-guidelines.md`](docs/frontend-guidelines.md) for behavioral rules and component reuse hierarchy.

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
