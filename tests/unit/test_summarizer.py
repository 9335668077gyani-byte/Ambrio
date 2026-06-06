# tests/unit/test_summarizer.py
"""
Tests for the SessionSummarizer.
We mock the Ollama call so no live LLM is needed.
"""
import pytest, tempfile, os, uuid, json
from unittest.mock import AsyncMock, patch, MagicMock

from ambrio.router.memory.db         import Database
from ambrio.router.memory.fts5_store  import FTS5Store
from ambrio.router.memory.summarizer  import SessionSummarizer, SUMMARY_TRIGGER_TURNS


@pytest.fixture
async def db_session():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db  = Database(path)
    await db.init()
    sid = str(uuid.uuid4())
    async with db.conn() as c:
        await c.execute("INSERT INTO sessions(id,title) VALUES(?,?)", (sid, "test"))
        await c.commit()
    yield db, sid
    os.unlink(path)


async def _fill_session(db, sid, n):
    store = FTS5Store(db)
    for i in range(n):
        await store.insert(sid, "user" if i % 2 == 0 else "assistant",
                           f"message {i} about invoices and spare parts", str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_should_summarize_false_when_below_threshold(db_session):
    db, sid = db_session
    summarizer = SessionSummarizer(db)
    await _fill_session(db, sid, 5)
    assert await summarizer.should_summarize(sid) is False


@pytest.mark.asyncio
async def test_should_summarize_true_when_above_threshold(db_session):
    db, sid = db_session
    summarizer = SessionSummarizer(db)
    await _fill_session(db, sid, SUMMARY_TRIGGER_TURNS + 1)
    assert await summarizer.should_summarize(sid) is True


@pytest.mark.asyncio
async def test_summarize_stores_summary(db_session):
    db, sid = db_session
    await _fill_session(db, sid, 10)

    # Mock the Ollama stream to return valid JSON
    fake_summary = {
        "summary":    "User asked about invoices.",
        "facts":      ["User uses SparePartsPro", "Main currency is INR"],
        "open_tasks": ["Send March report"],
        "entities":   {"company": "SparePartsPro"}
    }
    fake_json = json.dumps(fake_summary)

    async def fake_stream(messages, tools=None):
        yield {"done": False, "message": {"content": fake_json}}
        yield {"done": True}

    from ambrio.router.ollama_client import OllamaClient
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.stream = fake_stream

    summarizer = SessionSummarizer(db, mock_client)
    result     = await summarizer.summarize(sid)

    assert result is not None
    assert result["summary"] == "User asked about invoices."
    assert len(result["facts"]) == 2

    # Verify stored in DB
    latest = await summarizer.load_latest_summary(sid)
    assert latest is not None
    assert latest["facts"] == result["facts"]
