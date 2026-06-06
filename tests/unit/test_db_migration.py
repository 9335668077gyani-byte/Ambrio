import pytest, tempfile, os
from ambrio.router.memory.db import Database

@pytest.mark.asyncio
async def test_migration_creates_tables():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    db = Database(path)
    await db.init()
    async with db.conn() as c:
        cur = await c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {r[0] for r in await cur.fetchall()}
    assert 'sessions' in names
    assert 'messages' in names
    os.unlink(path)
