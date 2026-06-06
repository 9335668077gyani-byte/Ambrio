# tests/unit/test_brain_store.py
import pytest, tempfile, os
from ambrio.router.memory.db         import Database
from ambrio.router.memory.brain_store import BrainStore


@pytest.fixture
async def brain():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Database(path)
    await db.init()
    b  = BrainStore(db)
    await b.init()
    yield b
    os.unlink(path)


@pytest.mark.asyncio
async def test_set_and_get(brain):
    await brain.set("profile.name", "Gyani", namespace="profile")
    val = await brain.get("profile.name")
    assert val == "Gyani"


@pytest.mark.asyncio
async def test_overwrite(brain):
    await brain.set("fact.city", "Hyderabad")
    await brain.set("fact.city", "Mumbai")
    val = await brain.get("fact.city")
    assert val == "Mumbai"


@pytest.mark.asyncio
async def test_get_namespace(brain):
    await brain.set("fact.a", "val1", namespace="fact")
    await brain.set("fact.b", "val2", namespace="fact")
    rows = await brain.get_namespace("fact")
    assert len(rows) >= 2


@pytest.mark.asyncio
async def test_ingest_summary(brain):
    summary = {
        "summary":    "User discussed invoice queries.",
        "facts":      ["User works at SparePartsPro", "Invoices are in INR"],
        "open_tasks": ["Summarize March invoices"],
        "entities":   {"company": "SparePartsPro", "currency": "INR"}
    }
    await brain.ingest_summary("test-session-123", summary)

    facts = await brain.get_namespace("fact")
    tasks = await brain.get_namespace("task")
    prof  = await brain.get_namespace("profile")

    assert len(facts) >= 2
    assert len(tasks) >= 1
    assert any("company" in r["key"].lower() for r in prof)


@pytest.mark.asyncio
async def test_build_memory_block_empty(brain):
    block = await brain.build_memory_block()
    assert block == ""


@pytest.mark.asyncio
async def test_build_memory_block_populated(brain):
    await brain.set("profile.name", "Gyani",       namespace="profile")
    await brain.set("fact.f1",      "INR currency", namespace="fact")
    await brain.set("task.t1",      "Review March", namespace="task")
    block = await brain.build_memory_block()
    assert "<memory-context>" in block
    assert "Gyani" in block
    assert "INR currency" in block
    assert "Review March" in block
    assert "</memory-context>" in block
