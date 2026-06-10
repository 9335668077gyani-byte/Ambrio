# tests/unit/test_chroma_store.py
"""Unit tests for ChromaStore — semantic recall, session isolation, score range."""
import pytest
from ambrio.memory.chroma_store import ChromaStore


@pytest.mark.asyncio
async def test_semantic_recall_finds_similar():
    """Inserting brake-related messages and querying 'brakes' should surface them."""
    store = ChromaStore(persist_dir=":memory:")
    await store.init()
    await store.insert("s1", "user",      "brake pad replacement discussed", "m1")
    await store.insert("s1", "assistant", "brake pads available in rack A3",  "m2")
    results = await store.search("s1", "brakes", limit=5)
    assert len(results) > 0
    assert any("brake" in r["content"].lower() for r in results)


@pytest.mark.asyncio
async def test_no_cross_session_leak():
    """Documents inserted into session-A must NOT appear when querying session-B."""
    store = ChromaStore(persist_dir=":memory:")
    await store.init()
    await store.insert("session-A", "user", "confidential data", "a1")
    # session-B has no documents — _sync_search queries n_results=1 (total count=1)
    # but the where-filter restricts to session-B, so 0 docs should be returned.
    results = await store.search("session-B", "confidential data", limit=5)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_returns_scores():
    """Every result dict must contain a 'score' key with a value in [0.0, 1.0]."""
    store = ChromaStore(persist_dir=":memory:")
    await store.init()
    await store.insert("s1", "user", "Python programming language", "p1")
    results = await store.search("s1", "Python", limit=3)
    assert len(results) > 0, "Expected at least one result"
    assert all("score" in r for r in results)
    assert all(0.0 <= r["score"] <= 1.0 for r in results)
