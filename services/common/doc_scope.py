"""Project (session) document-scope matching shared by every store and retrieval path.

Indexed doc_ids are content-addressed as `{stem}_{sha256[:8]}` (see
`IngestionService._generate_doc_id`), while a project's `files` list may hold that exact id, the raw
filename (`Report 2024.pdf`) or the bare stem. Matching is therefore exact-after-normalization, plus
"bare stem + an 8-hex hash suffix" — never a loose prefix, which would pull `report_final_*` into a
project scoped to `report.pdf`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_HASH_SUFFIX = re.compile(r"_[0-9a-f]{8}$")
_EXTENSION = re.compile(r"\.[a-z0-9]{1,5}$")


def normalize_doc_id(doc_id: str) -> str:
    """Lowercases, strips a file extension, and maps spaces/hyphens to underscores."""
    norm = doc_id.strip().lower()
    norm = _EXTENSION.sub("", norm)
    return norm.replace(" ", "_").replace("-", "_")


def matches_doc_scope(candidate_doc_id: str | None, scope: Iterable[str]) -> bool:
    """True when `candidate_doc_id` is one of the scoped documents."""
    if not candidate_doc_id:
        return False
    cand = normalize_doc_id(candidate_doc_id)
    cand_stem = _HASH_SUFFIX.sub("", cand)
    for target in scope:
        tgt = normalize_doc_id(target)
        if cand == tgt:
            return True
        # Target given as a bare stem/filename (no hash) matches that stem's hashed id.
        if not _HASH_SUFFIX.search(tgt) and cand_stem == tgt and cand_stem != cand:
            return True
    return False
