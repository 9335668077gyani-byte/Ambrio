PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
    meta       TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
    content     TEXT NOT NULL,
    tokens      INTEGER,
    ts          INTEGER NOT NULL DEFAULT (unixepoch()),
    tool_name   TEXT,
    tool_args   TEXT,
    tool_result TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    role       UNINDEXED,
    session_id UNINDEXED,
    message_id UNINDEXED,
    tokenize = 'porter ascii'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, role, session_id, message_id)
    VALUES (new.rowid, new.content, new.role, new.session_id, new.id);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE message_id = old.id;
END;

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts DESC);
