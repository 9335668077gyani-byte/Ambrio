import re

_FTS5_SPECIAL = re.compile(r'[!"\*\(\)\-\:\^~]')

def _sanitize_fts(query: str) -> str:
    """Strip FTS5 special characters to prevent syntax errors."""
    cleaned = _FTS5_SPECIAL.sub(' ', query)
    # Collapse whitespace, take first 10 words max
    words = cleaned.split()[:10]
    return ' '.join(w for w in words if len(w) > 1) or '*'


class FTS5Store:
    def __init__(self, db: Database):
        self.db = db

    async def insert(self, session_id: str, role: str, content: str, message_id: str) -> None:
        async with self.db.conn() as c:
            await c.execute(
                'INSERT INTO messages(id, session_id, role, content) VALUES (?,?,?,?)',
                (message_id, session_id, role, content)
            )
            await c.commit()

    async def search(self, session_id: str, query: str, limit: int = 10) -> list[dict]:
        safe_query = _sanitize_fts(query)
        try:
            async with self.db.conn() as c:
                cur = await c.execute(
                    '''
                    SELECT m.content, m.role, m.session_id, m.id AS message_id
                    FROM messages m
                    WHERE m.session_id = ?
                      AND m.rowid IN (
                          SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?
                      )
                    ORDER BY m.ts DESC
                    LIMIT ?
                    ''',
                    (session_id, safe_query, limit)
                )
                rows = await cur.fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []   # FTS error → return empty, don't crash

    async def search_cross_session(self, query: str, limit: int = 10) -> list[dict]:
        safe_query = _sanitize_fts(query)
        try:
            async with self.db.conn() as c:
                cur = await c.execute(
                    '''
                    SELECT m.content, m.role, m.session_id, m.id AS message_id
                    FROM messages m
                    WHERE m.rowid IN (
                        SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?
                    )
                    ORDER BY m.ts DESC
                    LIMIT ?
                    ''',
                    (safe_query, limit)
                )
                rows = await cur.fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []   # FTS error → return empty, don't crash
