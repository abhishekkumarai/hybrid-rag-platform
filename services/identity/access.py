"""Which documents a user may read, and turning a project's `files` list into an exact retrieval
scope (IRA-34).

The indexes are shared by everyone (doc_ids are content-addressed), so isolation happens here: a
scope handed to retrieval is always a list of exact doc_ids the user may read, never a raw filename
or stem. Loose filename/stem matching (`matches_doc_scope`) is still applied, but only against the
user's own accessible set, so `report.pdf` can no longer resolve to someone else's `report_<hash>`."""

from __future__ import annotations

import re
from collections.abc import Iterable

from services.common.doc_scope import matches_doc_scope
from services.identity.store import IdentityStore

_FIGURE_NAME = re.compile(r"^(?P<doc_id>.+)_p\d+_fig_\d+\.png$")


def accessible_doc_ids(store: IdentityStore, user_id: str, public_doc_ids: Iterable[str] = ()) -> set[str]:
    """Owned, plus granted through a live share, plus documents attached to a project in one of the
    user's workspaces (IRA-46), plus the public web corpus."""
    return (
        store.owned_doc_ids(user_id)
        | store.granted_doc_ids(user_id)
        | store.workspace_doc_ids(user_id)
        | set(public_doc_ids)
    )


def resolve_scope(entries: Iterable[str], accessible: set[str]) -> list[str]:
    """Maps a project's `files` entries to the exact accessible doc_ids they name, in order.
    Entries that name nothing the user can read are dropped."""
    resolved: list[str] = []
    for entry in entries:
        if entry in accessible:
            matches = [entry]
        else:
            matches = sorted(a for a in accessible if matches_doc_scope(a, [entry]))
        for m in matches:
            if m not in resolved:
                resolved.append(m)
    return resolved


def figure_doc_id(figure_name: str) -> str | None:
    """Figures are written as `{doc_id}_p{page}_fig_{n}.png` by the multimodal extractor."""
    m = _FIGURE_NAME.match(figure_name)
    return m.group("doc_id") if m else None
