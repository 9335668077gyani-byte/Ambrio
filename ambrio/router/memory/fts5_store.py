from .db import Database

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
                (session_id, query, limit)
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def search_cross_session(self, query: str, limit: int = 10) -> list[dict]:
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
                (query, limit)
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
