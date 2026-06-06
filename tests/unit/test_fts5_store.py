import pytest, tempfile, os, uuid
from ambrio.router.memory.db import Database
from ambrio.router.memory.fts5_store import FTS5Store

@pytest.fixture
async def store_and_session():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    db = Database(path)
    await db.init()
    store = FTS5Store(db)
    session_id = str(uuid.uuid4())
    async with db.conn() as c:
        await c.execute('INSERT INTO sessions(id, title) VALUES (?,?)', (session_id, 'test'))
        await c.commit()
    yield store, session_id
    os.unlink(path)

@pytest.mark.asyncio
async def test_store_and_search(store_and_session):
    store, session_id = store_and_session
    await store.insert(session_id, 'user', 'invoice query for March', str(uuid.uuid4()))
    await store.insert(session_id, 'assistant', 'here is the invoice data', str(uuid.uuid4()))
    results = await store.search(session_id, 'invoice', limit=5)
    assert len(results) == 2
    assert any('invoice' in r['content'] for r in results)

@pytest.mark.asyncio
async def test_search_returns_empty_on_no_match(store_and_session):
    store, session_id = store_and_session
    results = await store.search(session_id, 'zzznomatchzzz', limit=5)
    assert results == []
