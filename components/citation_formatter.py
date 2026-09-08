"""Langflow custom component for formatting citations and provenance badges."""

from __future__ import annotations

from typing import Any

from services.common.logger import get_logger

logger = get_logger("components.citations")

try:
    from langflow.custom import Component
    from langflow.io import DataInput, Output, StrInput
    _HAS_LANGFLOW = True
except ImportError:
    _HAS_LANGFLOW = False
    Component = object  # type: ignore


class CitationFormatterComponent(Component):
    display_name = "Provenance Citation Formatter"
    description = "Formats LLM response with verified [Doc: Page: BBox] provenance citations."
    icon = "badge-check"
    beta = True

    if _HAS_LANGFLOW:
        inputs = [
            StrInput(name="answer_text", display_name="Generated Answer", required=True),
            DataInput(name="citations", display_name="Citations List", required=False),
        ]
        outputs = [
            Output(name="final_response", display_name="Response with Citations", method="format_response"),
        ]

    def format_response(self, answer_text: str = "", citations: list[dict[str, Any]] | None = None) -> str:
        if not citations:
            return answer_text

        citation_lines = []
        for idx, cite in enumerate(citations):
            badge = cite.get("formatted_badge", "")
            snippet = cite.get("snippet", "")
            is_table = cite.get("is_table", False)
            is_figure = cite.get("is_figure", False)
            img_path = cite.get("image_path")

            icon = "📑"
            type_label = ""
            if is_figure:
                icon = "🖼️"
                type_label = " [Visual Figure]"
            elif is_table:
                icon = "📊"
                type_label = " [Structured Table]"

            line = f"{idx+1}. {icon} **{badge}**{type_label}\n   > _{snippet}_"
            if is_figure and img_path:
                line += f"\n   \n   ![{badge}](/{img_path})"
            citation_lines.append(line)

        citations_section = "\n\n---\n### 📑 Verified Sources & Provenance:\n" + "\n".join(citation_lines)
        return f"{answer_text.strip()}\n{citations_section}"
