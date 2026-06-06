# ambrio/router/tools/memory_tool.py
from ..tool_registry import tool
from ..memory.fts5_store import FTS5Store

_store: FTS5Store | None = None

def init_memory_tool(store: FTS5Store) -> None:
    global _store
    _store = store

@tool()
async def memory_search(query: str, session_id: str) -> dict:
    """Search past conversation history using full-text search. Returns relevant prior messages."""
    if not _store:
        return {"error": "memory store not initialized"}
    results = await _store.search(session_id, query, limit=5)
    return {"results": results}
