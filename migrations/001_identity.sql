-- IRA-33: accounts, login sessions, per-user document ownership, public shares and the read-only
-- document grants a fork of a share receives. Timestamps are epoch seconds (double precision) to
-- match the float timestamps the Pydantic contracts already use.

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    is_admin      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_sessions(user_id);

-- doc_id is content-addressed, so identical uploads by two users share one indexed document and
-- get one ownership row each.
CREATE TABLE IF NOT EXISTS user_documents (
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_id     TEXT NOT NULL,
    filename   TEXT NOT NULL,
    path       TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (user_id, doc_id)
);
CREATE INDEX IF NOT EXISTS user_documents_doc_idx ON user_documents(doc_id);

CREATE TABLE IF NOT EXISTS shares (
    id          TEXT PRIMARY KEY,
    token_hash  TEXT NOT NULL UNIQUE,
    session_id  TEXT NOT NULL,
    owner_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot    JSONB NOT NULL,
    created_at  DOUBLE PRECISION NOT NULL,
    revoked_at  DOUBLE PRECISION,
    view_count  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS shares_session_idx ON shares(session_id);

CREATE TABLE IF NOT EXISTS doc_grants (
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_id     TEXT NOT NULL,
    share_id   TEXT NOT NULL REFERENCES shares(id) ON DELETE CASCADE,
    created_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (user_id, doc_id, share_id)
);
