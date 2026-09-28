# Evergreen Document RAG — design spec (IRA-41)

Source of truth for the wireframes in this folder. Mirrors the Stitch design system
"Evergreen Document RAG" (`assets/ac7b5eb0e02947568bd5677b5e4cb3c1`, project `2453091003018601102`),
with the parts it lacked taken from "IRA Evergreen" (`assets/9837043451042814826`).

**Palette pin:** canvas is exactly `#FBFBF9`, primary exactly `#1F6B52`. Never `#FFF8F5`, `#00523C`,
`#733430` (Stitch's auto-generated tones). No purple, gradients, glows, glassmorphism or emoji.

## Colours

| Token | Hex | Use |
|---|---|---|
| canvas | `#FBFBF9` | page background |
| surface | `#FFFFFF` | sidebar, cards, panels |
| fill | `#F5F5F2` | subtle fill, hover |
| border | `#E7E5E0` | all 1px borders |
| ink | `#1C1917` | primary text |
| ink-secondary | `#57534E` | secondary text |
| metadata | `#78716C` | metadata, placeholders |
| caption | `#8A8580` | captions |
| primary | `#1F6B52` | primary actions, active tab/nav |
| primary-hover | `#175340` | |
| primary-tint | `#E9F2EE` | selected rows, pills, citation chips |
| primary-tint-border | `#D1E3DA` | citation chip border |

**Answer states** (text on tint): confident `#1F8A5B` / `#EAF6EF` · ambiguous `#B7791F` / `#FBF3E4` ·
refused `#B4534F` / `#F9ECEC`.

**Project folder tints** (square / icon): sage `#E9F2EE` / `#1F6B52` · sky `#E8F0F8` / `#3F7CAC` ·
sand `#FBF3E4` / `#B7791F` · rose `#F9ECEC` / `#B4534F`.

## Type
- DM Sans for UI and prose — headings 36 / 24 / 20 / 16, body 14/22, small 13/18.
- JetBrains Mono only for doc ids, page refs, scores, latencies, model names, chunk text; tabular figures.
- Icons: Material Symbols Outlined.

## Shape and depth
- Radius: cards/panels/modals 12px · buttons, inputs, citation tags, code 8px · small chips 4px · avatars full.
- Surfaces: white + 1px `#E7E5E0`, no shadow.
- Hover: `0 1px 3px rgba(28,25,23,.05)` + border `#1F6B52` at 30%.
- Popovers/modals: `0 8px 24px rgba(28,25,23,.08), 0 2px 6px rgba(28,25,23,.04)`.

## Structure: Workspace › Project › Chat session
- **Sidebar:** IRA logo → workspace switcher (initials square · workspace name · "Workspace · admin") →
  nav Overview · Library · Evaluation · Observability → PROJECTS (+) with folder-tint rows
  (active = tint row + evergreen text + dot) → footer Settings, services health (Qdrant · Redis · Ollama),
  user card.
- **Project pages:** breadcrumb `Workspace › Projects › Project`, title, actions
  (Share · New chat · Add source), tabs Overview · Sources · Chat sessions · Evaluation · Settings.
- **Chat sessions tab:** sessions list · conversation · citation inspector · docked composer
  (Auto · Agentic · Graph · Direct + model). Tablet: inspector becomes a right-edge drawer; mobile stacks.

## Components
- **Buttons:**
  - Primary: `#1F6B52` with white text, 8px, 40px tall, 14/500, hover `#175340`.
  - Secondary: white with a 1px `#E7E5E0` border; on hover, `#E9F2EE` fill and a `#1F6B52` border.
  - Ghost: `#78716C` text.
- **Citation chip:** mono 11/500, `[Doc 2, p. 14]` or `file.pdf · p. 14`, on `#E9F2EE`, border `#D1E3DA`,
  text `#1F6B52`, 4px. On hover/active it fills `#1F6B52` with white text and highlights the bbox in the
  inspector.
- **Answer-state chip:** dot + label on its tint. A refused turn is a card on `#F9ECEC` with `#B4534F`
  text.
- **Tabs:** active tab has `#1F6B52` text and a 2px underline; counts in grey pills.
- **Stat card:** 40px tinted icon square, 24px number, caption, tinted delta pill.
- **Inputs:** white, 8px, 1px `#E7E5E0`; focus shows a `#1F6B52` border and a 2px `#E9F2EE` outline.
- **Document chunk:** `#FBFBF9`, 1px `#E7E5E0`, 8px, mono 12/20, with a metadata bar above (file, page,
  score).
