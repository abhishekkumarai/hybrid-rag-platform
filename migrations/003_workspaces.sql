-- IRA-46: shared teams of users. A project (ChatSession, stored in Redis) is stamped with the
-- workspace it belongs to; every member of that workspace can see the project, not just its owner.
-- Every user gets a personal workspace (see services/identity/migrate.py's backfill for existing
-- accounts, and the signup/demo/CLI account-creation paths for new ones).

CREATE TABLE IF NOT EXISTS workspaces (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    owner_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
    added_at     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS workspace_members_user_idx ON workspace_members(user_id);

-- Mirrors ChatSession.files (Redis) for whichever project attached the document, so
-- accessible_doc_ids can union in "documents attached to any project in one of my workspaces"
-- without reading every session out of Redis on every request.
CREATE TABLE IF NOT EXISTS workspace_documents (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    doc_id       TEXT NOT NULL,
    added_by     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (workspace_id, doc_id)
);
CREATE INDEX IF NOT EXISTS workspace_documents_doc_idx ON workspace_documents(doc_id);
