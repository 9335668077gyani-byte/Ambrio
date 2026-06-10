# tests/unit/test_chroma_store.py
"""Unit tests for ChromaStore — semantic recall, session isolation, score range, edge cases."""
import pytest
from ambrio.memory.chroma_store import ChromaStore


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
async def mem_store():
    """Fresh ephemeral ChromaStore per test — no shared state."""
    store = ChromaStore(persist_dir=":memory:")
    await store.init()
    yield store


# ── Core behaviour ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_semantic_recall_finds_similar(mem_store):
    """Inserting brake-related messages and querying 'brakes' should surface them."""
    await mem_store.insert("s1", "user",      "brake pad replacement discussed", "m1")
    await mem_store.insert("s1", "assistant", "brake pads available in rack A3",  "m2")
    results = await mem_store.search("s1", "brakes", limit=5)
    assert len(results) > 0
    assert any("brake" in r["content"].lower() for r in results)


@pytest.mark.asyncio
async def test_no_cross_session_leak(mem_store):
    """Documents inserted into session-A must NOT appear when querying session-B."""
    await mem_store.insert("session-A", "user", "confidential data", "a1")
    # session-B has no documents — where-filter restricts to session-B → 0 results.
    results = await mem_store.search("session-B", "confidential data", limit=5)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_returns_scores(mem_store):
    """Every result dict must contain a 'score' key with a value in [0.0, 1.0]."""
    await mem_store.insert("s1", "user", "Python programming language", "p1")
    results = await mem_store.search("s1", "Python", limit=3)
    assert len(results) > 0, "Expected at least one result"
    assert all("score" in r for r in results)
    assert all(0.0 <= r["score"] <= 1.0 for r in results)


# ── Isolation guarantee ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_instances_are_isolated():
    """Two separate ChromaStore(':memory:') instances must NOT share state."""
    store_a = ChromaStore(persist_dir=":memory:")
    store_b = ChromaStore(persist_dir=":memory:")
    await store_a.init()
    await store_b.init()

    await store_a.insert("s1", "user", "secret data in instance A", "x1")

    # Instance B — same session id "s1" — should see nothing from instance A.
    results = await store_b.search("s1", "secret data", limit=5)
    assert len(results) == 0, (
        "Instance B returned results from instance A — EphemeralClient is sharing state!"
    )


# ── Edge cases ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_store_returns_empty_list(mem_store):
    """Searching a freshly-initialised store must return [] not raise."""
    results = await mem_store.search("s1", "anything", limit=5)
    assert results == []


@pytest.mark.asyncio
async def test_result_contains_role_field(mem_store):
    """Each result dict must have a 'role' key matching what was inserted."""
    await mem_store.insert("s1", "user", "spare part inquiry about filters", "r1")
    results = await mem_store.search("s1", "filters", limit=3)
    assert len(results) > 0
    assert all("role" in r for r in results)
    assert all(r["role"] == "user" for r in results)
