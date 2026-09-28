-- IRA-38: throwaway guest accounts behind "Try demo". Flagged so they can be labeled in the UI and
-- purged later without touching real accounts.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS users_demo_idx ON users(is_demo) WHERE is_demo;
