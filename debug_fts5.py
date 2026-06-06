import asyncio, tempfile, uuid, os
from ambrio.router.memory.db import Database
from ambrio.router.memory.fts5_store import FTS5Store

async def debug():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    db = Database(path)
    await db.init()
    store = FTS5Store(db)
    sid = str(uuid.uuid4())
    async with db.conn() as c:
        await c.execute('INSERT INTO sessions(id,title) VALUES(?,?)', (sid,'test'))
        await c.commit()

    mid1 = str(uuid.uuid4())
    mid2 = str(uuid.uuid4())
    await store.insert(sid, 'user', 'invoice query for March', mid1)
    await store.insert(sid, 'assistant', 'here is the invoice data', mid2)

    async with db.conn() as c:
        # Check messages table
        cur = await c.execute('SELECT id, content, rowid FROM messages')
        rows = await cur.fetchall()
        print('messages:', [dict(r) for r in rows])

        # Check FTS table
        cur = await c.execute('SELECT rowid, content, message_id FROM messages_fts')
        rows = await cur.fetchall()
        print('fts rows:', [dict(r) for r in rows])

        # Raw FTS match
        cur = await c.execute('SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?', ('invoice',))
        rows = await cur.fetchall()
        print('fts match rowids:', [r[0] for r in rows])

        # Full search query test
        cur = await c.execute('''
            SELECT m.content, m.role, m.session_id, m.id AS message_id
            FROM messages m
            WHERE m.session_id = ?
              AND m.rowid IN (
                  SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?
              )
            LIMIT 10
        ''', (sid, 'invoice'))
        rows = await cur.fetchall()
        print('search results:', [dict(r) for r in rows])

    os.unlink(path)

asyncio.run(debug())
