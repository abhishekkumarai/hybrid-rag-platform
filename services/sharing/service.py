"""Public share links for chats and forking them into a project of one's own (IRA-35).

A share is a snapshot: the messages that existed when it was created, never later ones. Anyone with
the URL can read it. A signed-in user can fork it, which creates a project they own holding a copy of
that history — so `SessionManager.build_conversation_context` continues the conversation from there
with no pipeline change — plus a read-only grant to the shared documents, so follow-ups stay grounded.
Revoking a share kills the URL and the grants; existing forks keep their copied history."""

from __future__ import annotations

from contracts.session import ChatMessage, ChatSession
from contracts.share import Share, SharedMessage, ShareSnapshot, ShareSummary
from services.common.logger import get_logger
from services.identity.access import resolve_scope
from services.identity.auth import hash_token, new_token
from services.identity.store import IdentityStore
from services.session.manager import SessionManager

logger = get_logger("sharing.service")


def summarize(share: Share) -> ShareSummary:
    return ShareSummary(
        id=share.id, session_id=share.session_id, created_at=share.created_at,
        message_count=len(share.snapshot.messages), revoked=share.revoked_at is not None,
    )


class ShareService:
    def __init__(self, store: IdentityStore, sessions: SessionManager) -> None:
        self.store = store
        self.sessions = sessions

    def create(self, session: ChatSession, messages: list[ChatMessage], shareable_doc_ids: set[str]) -> tuple[str, Share]:
        """Snapshots `session`. `shareable_doc_ids` is what the sharer owns plus the public corpus:
        documents they were only *granted* through someone else's share are not re-published, and
        citations pointing at anything outside the snapshot's documents are dropped with them."""
        doc_ids = resolve_scope(session.files, shareable_doc_ids)
        allowed = set(doc_ids)
        snapshot = ShareSnapshot(
            title=session.title,
            system_prompt=session.system_prompt,
            parameters=session.parameters,
            doc_ids=doc_ids,
            messages=[
                SharedMessage(
                    role=m.role, content=m.content, timestamp=m.timestamp,
                    citations=[c for c in m.citations if c.doc_id in allowed],
                )
                for m in messages
                if m.role in ("user", "assistant")
            ],
        )
        token = new_token(24)
        share = Share(token_hash=hash_token(token), session_id=session.id, owner_id=session.owner_id or "", snapshot=snapshot)
        self.store.create_share(share)
        logger.info(f"Shared session '{session.id}' as '{share.id}' ({len(snapshot.messages)} messages, {len(doc_ids)} docs)")
        return token, share

    def get_public(self, token: str) -> Share | None:
        share = self.store.get_share_by_token_hash(hash_token(token))
        if not share or share.revoked_at is not None:
            return None
        return share

    def list_for_session(self, session_id: str) -> list[ShareSummary]:
        return [summarize(s) for s in self.store.list_shares(session_id)]

    def revoke(self, share_id: str, owner_id: str) -> bool:
        share = self.store.get_share(share_id)
        if not share or share.owner_id != owner_id:
            return False
        self.store.revoke_share(share_id)
        logger.info(f"Revoked share '{share_id}'")
        return True

    def fork(self, token: str, user_id: str) -> ChatSession | None:
        share = self.get_public(token)
        if not share:
            return None
        snap = share.snapshot
        session = self.sessions.create_session(
            title=f"{snap.title} (shared)",
            system_prompt=snap.system_prompt,
            parameters=snap.parameters,
            files=snap.doc_ids,
            owner_id=user_id,
            forked_from=share.id,
        )
        for m in snap.messages:
            self.sessions.append_message(
                session.id,
                ChatMessage(
                    role=m.role, content=m.content, citations=m.citations, timestamp=m.timestamp,
                    metadata={"forked_from": share.id},
                ),
            )
        if snap.doc_ids:
            self.store.add_grants(user_id, snap.doc_ids, share.id)
        logger.info(f"Forked share '{share.id}' into session '{session.id}' for user '{user_id}'")
        forked, _ = self.sessions.get_session(session.id)
        return forked or session
