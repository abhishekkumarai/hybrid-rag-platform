"""Base protocol and common utilities for specialized parsers."""

from __future__ import annotations

from typing import Protocol

from contracts.document import Block


class DocumentParser(Protocol):
    """Protocol that all specialized page parsers must implement."""

    def parse(self, file_path: str, doc_id: str) -> list[Block]:
        """Parses a document file and returns a list of normalized Block objects."""
        ...
