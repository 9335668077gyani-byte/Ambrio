# Ambrio Desktop Phase 3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 100% offline, local-first Autonomous AI Desktop Assistant with PyQt6 Neumorphic UI, decoupled ZeroMQ IPC, FTS5 persistent memory, and Docker/gVisor sandboxed code execution.

**Architecture:** Two OS processes (UI + Router) communicate via ZeroMQ DEALER/ROUTER. The Router owns all LLM/memory/tool logic as an asyncio microservice. The Sandbox runs AI-executed code in gVisor-isolated containers using a Maker-Checker verification pattern.

**Tech Stack:** Python 3.10+, PyQt6, pyzmq, aiosqlite, aiohttp, pydantic, tiktoken, msgpack, Docker + gVisor (runsc)

---

## Phase 1 — Foundation & IPC Protocol

### Task 1.1: Project Scaffold

**Files:**
- Create: `C:\MY PROJECTS\Ambrio\ambrio\__init__.py`
- Create: `C:\MY PROJECTS\Ambrio\ambrio\ui\__init__.py`
- Create: `C:\MY PROJECTS\Ambrio\ambrio\ui\ipc\__init__.py`
- Create: `C:\MY PROJECTS\Ambrio\ambrio\router\__init__.py`
- Create: `C:\MY PROJECTS\Ambrio\ambrio\router\tools\__init__.py`
- Create: `C:\MY PROJECTS\Ambrio\ambrio\router\memory\__init__.py`
- Create: `C:\MY PROJECTS\Ambrio\ambrio\sandbox\__init__.py`
- Create: `C:\MY PROJECTS\Ambrio\ambrio\sandbox\policies\__init__.py`
- Create: `C:\MY PROJECTS\Ambrio\requirements.txt`

- [ ] **Step 1: Create all `__init__.py` stubs and requirements.txt**

```
# requirements.txt
PyQt6>=6.7.0
pyzmq>=26.0.0
aiosqlite>=0.20.0
aiohttp>=3.9.0
pydantic>=2.7.0
tiktoken>=0.7.0
msgpack>=1.0.8
```

- [ ] **Step 2: Create virtualenv and install deps**

```powershell
cd "C:\MY PROJECTS\Ambrio"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 3: Commit**

```bash
git add .
git commit -m "feat: scaffold Ambrio Phase 3 package structure"
```

---

### Task 1.2: IPC Message Protocol

**Files:**
- Create: `ambrio/ui/ipc/message_protocol.py`
- Test: `tests/unit/test_message_protocol.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_message_protocol.py
import msgpack, pytest
from ambrio.ui.ipc.message_protocol import Frame, MsgType

def test_frame_roundtrip():
    frame = Frame(session_id="s1", type=MsgType.CHAT_REQUEST, payload={"content": "hello"})
    packed = msgpack.packb(frame.model_dump())
    unpacked = Frame.model_validate(msgpack.unpackb(packed))
    assert unpacked.session_id == "s1"
    assert unpacked.type == MsgType.CHAT_REQUEST
    assert unpacked.payload["content"] == "hello"

def test_frame_auto_id():
    f1 = Frame(session_id="s", type=MsgType.CHAT_DONE, payload={})
    f2 = Frame(session_id="s", type=MsgType.CHAT_DONE, payload={})
    assert f1.id != f2.id
```

- [ ] **Step 2: Run — confirm FAIL**

```powershell
pytest tests/unit/test_message_protocol.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# ambrio/ui/ipc/message_protocol.py
from enum import StrEnum
from pydantic import BaseModel, Field
import uuid, time

class MsgType(StrEnum):
    CHAT_REQUEST   = "chat.request"
    CHAT_TOKEN     = "chat.token"
    CHAT_DONE      = "chat.done"
    TOOL_CALL      = "tool.call"
    TOOL_RESULT    = "tool.result"
    SANDBOX_SUBMIT = "sandbox.submit"
    SANDBOX_RESULT = "sandbox.result"
    ERROR          = "error"
    SESSION_SYNC   = "session.sync"

class Frame(BaseModel):
    id:         str   = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    type:       MsgType
    payload:    dict
    ts:         float = Field(default_factory=time.monotonic)
```

- [ ] **Step 4: Run — confirm PASS**

```powershell
pytest tests/unit/test_message_protocol.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ambrio/ui/ipc/message_protocol.py tests/unit/test_message_protocol.py
git commit -m "feat: IPC message protocol with Pydantic + msgpack"
```

---

### Task 1.3: SQLite FTS5 Schema + Migration Runner

**Files:**
- Create: `db/schema.sql`
- Create: `ambrio/router/memory/db.py`
- Test: `tests/unit/test_db_migration.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_db_migration.py
import asyncio, pytest, aiosqlite, tempfile, os
from ambrio.router.memory.db import Database

@pytest.mark.asyncio
async def test_migration_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Database(path)
    await db.init()
    async with db.conn() as c:
        tables = await c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        names = {r[0] for r in await tables.fetchall()}
    assert "sessions" in names
    assert "messages" in names
    os.unlink(path)
```

- [ ] **Step 2: Run — confirm FAIL**

```powershell
pytest tests/unit/test_db_migration.py -v
```

- [ ] **Step 3: Create schema.sql**

```sql
-- db/schema.sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
    meta       TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
    content     TEXT NOT NULL,
    tokens      INTEGER,
    ts          INTEGER NOT NULL DEFAULT (unixepoch()),
    tool_name   TEXT,
    tool_args   TEXT,
    tool_result TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    role      UNINDEXED,
    session_id UNINDEXED,
    message_id UNINDEXED,
    tokenize = 'porter ascii'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, role, session_id, message_id)
    VALUES (new.rowid, new.content, new.role, new.session_id, new.id);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE message_id = old.id;
END;

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts DESC);
```

- [ ] **Step 4: Implement db.py**

```python
# ambrio/router/memory/db.py
import aiosqlite, asyncio
from contextlib import asynccontextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parents[4] / "db" / "schema.sql"

class Database:
    def __init__(self, path: str):
        self._path = path
        self._lock = asyncio.Lock()

    async def init(self):
        async with aiosqlite.connect(self._path) as c:
            c.row_factory = aiosqlite.Row
            sql = SCHEMA_PATH.read_text()
            # Execute each statement separately
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    await c.execute(stmt)
            await c.commit()

    @asynccontextmanager
    async def conn(self):
        async with aiosqlite.connect(self._path) as c:
            c.row_factory = aiosqlite.Row
            await c.execute("PRAGMA foreign_keys=ON")
            yield c
```

- [ ] **Step 5: Run — confirm PASS**

```powershell
pytest tests/unit/test_db_migration.py -v
```

- [ ] **Step 6: Commit**

```bash
git add db/schema.sql ambrio/router/memory/db.py tests/unit/test_db_migration.py
git commit -m "feat: SQLite FTS5 schema + async migration runner"
```

---

### Task 1.4: FTS5 Store — INSERT & SEARCH

**Files:**
- Create: `ambrio/router/memory/fts5_store.py`
- Test: `tests/unit/test_fts5_store.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_fts5_store.py
import asyncio, pytest, tempfile, os, uuid
from ambrio.router.memory.db import Database
from ambrio.router.memory.fts5_store import FTS5Store

@pytest.fixture
async def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Database(path)
    await db.init()
    s = FTS5Store(db)
    yield s
    os.unlink(path)

@pytest.mark.asyncio
async def test_store_and_search(store):
    session_id = str(uuid.uuid4())
    async with store.db.conn() as c:
        await c.execute(
            "INSERT INTO sessions(id, title) VALUES (?,?)",
            (session_id, "test")
        )
        await c.commit()

    await store.insert(session_id, "user", "invoice query for March", str(uuid.uuid4()))
    await store.insert(session_id, "assistant", "here is the invoice data", str(uuid.uuid4()))

    results = await store.search(session_id, "invoice", limit=5)
    assert len(results) == 2
    assert any("invoice" in r["content"] for r in results)

@pytest.mark.asyncio
async def test_search_returns_empty_on_no_match(store):
    session_id = str(uuid.uuid4())
    async with store.db.conn() as c:
        await c.execute("INSERT INTO sessions(id,title) VALUES(?,?)", (session_id,"t"))
        await c.commit()
    results = await store.search(session_id, "zzznomatchzzz", limit=5)
    assert results == []
```

- [ ] **Step 2: Run — confirm FAIL**

- [ ] **Step 3: Implement**

```python
# ambrio/router/memory/fts5_store.py
from .db import Database

class FTS5Store:
    def __init__(self, db: Database):
        self.db = db

    async def insert(self, session_id: str, role: str, content: str, message_id: str) -> None:
        async with self.db.conn() as c:
            await c.execute(
                "INSERT INTO messages(id, session_id, role, content) VALUES (?,?,?,?)",
                (message_id, session_id, role, content)
            )
            await c.commit()

    async def search(self, session_id: str, query: str, limit: int = 10) -> list[dict]:
        """BM25-ranked FTS5 search scoped to a session."""
        async with self.db.conn() as c:
            cur = await c.execute(
                """
                SELECT m.content, m.role, m.session_id, m.id AS message_id
                FROM messages_fts f
                JOIN messages m ON m.id = f.message_id
                WHERE messages_fts MATCH ?
                  AND f.session_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, session_id, limit)
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def search_cross_session(self, query: str, limit: int = 10) -> list[dict]:
        """Cross-session search — for global memory recall."""
        async with self.db.conn() as c:
            cur = await c.execute(
                """
                SELECT m.content, m.role, m.session_id, m.id AS message_id
                FROM messages_fts f
                JOIN messages m ON m.id = f.message_id
                WHERE messages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit)
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Run — confirm PASS**

```powershell
pytest tests/unit/test_fts5_store.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ambrio/router/memory/fts5_store.py tests/unit/test_fts5_store.py
git commit -m "feat: FTS5 store with BM25-ranked INSERT/SEARCH"
```

---

## Phase 2 — Cognitive Router

### Task 2.1: Ollama Async Streaming Client

**Files:**
- Create: `ambrio/router/ollama_client.py`
- Test: `tests/unit/test_ollama_client.py`

- [ ] **Step 1: Write failing test (uses mock)**

```python
# tests/unit/test_ollama_client.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from ambrio.router.ollama_client import OllamaClient

@pytest.mark.asyncio
async def test_stream_yields_tokens():
    client = OllamaClient()
    fake_lines = [
        b'{"message":{"content":"Hello"},"done":false}',
        b'{"message":{"content":" World"},"done":false}',
        b'{"done":true}',
    ]

    mock_resp = AsyncMock()
    mock_resp.content.__aiter__ = AsyncMock(return_value=iter(fake_lines))

    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        tokens = []
        async for chunk in client.stream([{"role":"user","content":"hi"}]):
            if not chunk.get("done"):
                tokens.append(chunk["message"]["content"])
        assert tokens == ["Hello", " World"]
```

- [ ] **Step 2: Run — confirm FAIL**

- [ ] **Step 3: Implement**

```python
# ambrio/router/ollama_client.py
import aiohttp, json
from typing import AsyncGenerator

class OllamaClient:
    BASE_URL   = "http://localhost:11434"
    MODEL      = "codegemma"
    TIMEOUT_S  = 120

    def __init__(self, model: str = MODEL):
        self.model = model

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None
    ) -> AsyncGenerator[dict, None]:
        payload = {
            "model":    self.model,
            "messages": messages,
            "stream":   True,
        }
        if tools:
            payload["tools"] = tools

        timeout = aiohttp.ClientTimeout(total=self.TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{self.BASE_URL}/api/chat",
                json=payload
            ) as resp:
                resp.raise_for_status()
                async for raw_line in resp.content:
                    line = raw_line.strip()
                    if not line:
                        continue
                    yield json.loads(line)

    async def list_models(self) -> list[str]:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.BASE_URL}/api/tags") as resp:
                data = await resp.json()
        return [m["name"] for m in data.get("models", [])]
```

- [ ] **Step 4: Run — confirm PASS**

```powershell
pytest tests/unit/test_ollama_client.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ambrio/router/ollama_client.py tests/unit/test_ollama_client.py
git commit -m "feat: async Ollama streaming client with tool support"
```

---

### Task 2.2: Tool Registry

**Files:**
- Create: `ambrio/router/tool_registry.py`
- Test: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_tool_registry.py
import pytest
from ambrio.router.tool_registry import tool, ToolRegistry

@tool()
async def add_numbers(a: str, b: str) -> dict:
    """Add two numbers."""
    return {"result": int(a) + int(b)}

@pytest.mark.asyncio
async def test_dispatch_known_tool():
    reg = ToolRegistry()
    result = await reg.dispatch("add_numbers", {"a": "3", "b": "4"})
    assert result == {"result": 7}

@pytest.mark.asyncio
async def test_dispatch_unknown_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        await reg.dispatch("nonexistent_tool", {})

def test_schema_export():
    reg = ToolRegistry()
    schema = reg.schema()
    names = [s["function"]["name"] for s in schema]
    assert "add_numbers" in names
```

- [ ] **Step 2: Run — confirm FAIL**

- [ ] **Step 3: Implement**

```python
# ambrio/router/tool_registry.py
import functools, inspect
from typing import Callable, Any

_REGISTRY: dict[str, Callable] = {}

def tool(name: str | None = None):
    def decorator(fn: Callable):
        key = name or fn.__name__
        assert inspect.iscoroutinefunction(fn), f"Tool '{key}' must be async"
        _REGISTRY[key] = fn
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)
        return wrapper
    return decorator

class ToolRegistry:
    async def dispatch(self, tool_name: str, args: dict) -> Any:
        fn = _REGISTRY.get(tool_name)
        if not fn:
            raise KeyError(f"Unknown tool: {tool_name!r}")
        return await fn(**args)

    def schema(self) -> list[dict]:
        schemas = []
        for name, fn in _REGISTRY.items():
            sig = inspect.signature(fn)
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": (fn.__doc__ or "").strip(),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            p: {"type": "string"}
                            for p in sig.parameters
                        },
                        "required": list(sig.parameters.keys())
                    }
                }
            })
        return schemas
```

- [ ] **Step 4: Run — confirm PASS**

```powershell
pytest tests/unit/test_tool_registry.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ambrio/router/tool_registry.py tests/unit/test_tool_registry.py
git commit -m "feat: @tool decorator registry with Ollama schema export"
```

---

### Task 2.3: Context Pruner

**Files:**
- Create: `ambrio/router/context_pruner.py`
- Test: `tests/unit/test_context_pruner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_context_pruner.py
import pytest, asyncio, tempfile, os, uuid
from ambrio.router.memory.db import Database
from ambrio.router.memory.fts5_store import FTS5Store
from ambrio.router.context_pruner import ContextPruner

@pytest.mark.asyncio
async def test_context_budget_not_exceeded():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Database(path)
    await db.init()
    store = FTS5Store(db)
    session_id = str(uuid.uuid4())
    async with db.conn() as c:
        await c.execute("INSERT INTO sessions(id,title) VALUES(?,?)", (session_id,"t"))
        await c.commit()

    pruner = ContextPruner(store, session_id)
    # Build huge history to trigger pruning
    history = [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": f"message number {i} " * 100}
        for i in range(50)
    ]
    context = await pruner.build("new question", history)
    # Count tokens roughly
    total_chars = sum(len(m["content"]) for m in context)
    assert total_chars < 7000 * 6  # 6 chars/token rough upper bound
    os.unlink(path)

@pytest.mark.asyncio
async def test_recent_messages_always_kept():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Database(path)
    await db.init()
    store = FTS5Store(db)
    session_id = str(uuid.uuid4())
    async with db.conn() as c:
        await c.execute("INSERT INTO sessions(id,title) VALUES(?,?)", (session_id,"t"))
        await c.commit()
    pruner = ContextPruner(store, session_id)
    history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
    context = await pruner.build("hi", history)
    contents = [m["content"] for m in context]
    # Last 6 messages must be present
    for msg in history[-6:]:
        assert msg["content"] in contents
    os.unlink(path)
```

- [ ] **Step 2: Run — confirm FAIL**

- [ ] **Step 3: Implement**

```python
# ambrio/router/context_pruner.py
import tiktoken
from .memory.fts5_store import FTS5Store

CONTEXT_BUDGET   = 7000
RECENT_MSGS_KEEP = 6
enc = tiktoken.get_encoding("cl100k_base")

SYSTEM_PROMPT = (
    "You are Ambrio, a private autonomous AI assistant running 100% locally. "
    "You have access to tools: memory_search, sparepartspro_query, run_sandboxed_code. "
    "Always reason step-by-step before invoking tools. "
    "Never expose internal tool names or raw JSON to the user."
)

class ContextPruner:
    def __init__(self, store: FTS5Store, session_id: str):
        self.store      = store
        self.session_id = session_id

    async def build(self, new_content: str, full_history: list[dict]) -> list[dict]:
        system   = [{"role": "system", "content": SYSTEM_PROMPT}]
        recent   = full_history[-RECENT_MSGS_KEEP:]
        recalled = await self._recall(new_content, exclude=recent)

        budget  = CONTEXT_BUDGET - self._tokens(system)
        context = self._fit(recalled + recent, budget)
        return system + context + [{"role": "user", "content": new_content}]

    async def _recall(self, query: str, exclude: list[dict]) -> list[dict]:
        exclude_set = {m["content"] for m in exclude}
        rows = await self.store.search(self.session_id, query, limit=10)
        return [
            {"role": r["role"], "content": r["content"]}
            for r in rows
            if r["content"] not in exclude_set
        ]

    def _fit(self, messages: list[dict], budget: int) -> list[dict]:
        msgs = list(messages)
        while msgs and self._tokens(msgs) > budget:
            msgs.pop(0)
        return msgs

    def _tokens(self, messages: list[dict]) -> int:
        return sum(len(enc.encode(m.get("content", ""))) for m in messages)
```

- [ ] **Step 4: Run — confirm PASS**

```powershell
pytest tests/unit/test_context_pruner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ambrio/router/context_pruner.py tests/unit/test_context_pruner.py
git commit -m "feat: context pruner with FTS5 recall + sliding window"
```

---

### Task 2.4: Session Manager

**Files:**
- Create: `ambrio/router/session_manager.py`

- [ ] **Step 1: Implement**

```python
# ambrio/router/session_manager.py
import uuid
from .memory.db import Database
from .memory.fts5_store import FTS5Store
from .context_pruner import ContextPruner
from .ollama_client import OllamaClient

DB_PATH = "ambrio.db"   # resolved at runtime via env/config

class Session:
    def __init__(self, session_id: str, db: Database):
        self.id      = session_id
        self.db      = db
        self.store   = FTS5Store(db)
        self.pruner  = ContextPruner(self.store, session_id)
        self.ollama  = OllamaClient()
        self._history: list[dict] = []
        self._pending_tool: dict | None = None

    async def build_context(self, user_content: str) -> list[dict]:
        return await self.pruner.build(user_content, self._history)

    async def persist_turn(self, user_content: str, assistant_content: str = "") -> None:
        uid = str(uuid.uuid4())
        aid = str(uuid.uuid4())
        await self.store.insert(self.id, "user",      user_content,      uid)
        if assistant_content:
            await self.store.insert(self.id, "assistant", assistant_content, aid)
        self._history.append({"role": "user",      "content": user_content})
        if assistant_content:
            self._history.append({"role": "assistant", "content": assistant_content})

    def inject_tool_result(self, result: dict) -> None:
        self._history.append({
            "role":    "tool",
            "content": str(result)
        })

class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._db: Database | None = None

    async def init(self, db_path: str = DB_PATH):
        self._db = Database(db_path)
        await self._db.init()
        # Upsert sessions table for first run
        async with self._db.conn() as c:
            await c.execute(
                "INSERT OR IGNORE INTO sessions(id,title) VALUES('__global__','Global')"
            )
            await c.commit()

    async def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            async with self._db.conn() as c:
                await c.execute(
                    "INSERT OR IGNORE INTO sessions(id,title) VALUES(?,?)",
                    (session_id, f"Session {session_id[:8]}")
                )
                await c.commit()
            self._sessions[session_id] = Session(session_id, self._db)
        return self._sessions[session_id]
```

- [ ] **Step 2: Commit**

```bash
git add ambrio/router/session_manager.py
git commit -m "feat: session manager with per-session context/memory"
```

---

### Task 2.5: Built-in Tools

**Files:**
- Create: `ambrio/router/tools/memory_tool.py`
- Create: `ambrio/router/tools/sparepartspro_tool.py`
- Create: `ambrio/router/tools/sandbox_tool.py`

- [ ] **Step 1: Implement memory_tool.py**

```python
# ambrio/router/tools/memory_tool.py
from ..tool_registry import tool
from ..memory.fts5_store import FTS5Store

_store: FTS5Store | None = None

def init_memory_tool(store: FTS5Store):
    global _store
    _store = store

@tool()
async def memory_search(query: str, session_id: str) -> dict:
    """Search past conversation history using full-text search."""
    if not _store:
        return {"error": "memory store not initialized"}
    results = await _store.search(session_id, query, limit=5)
    return {"results": results}
```

- [ ] **Step 2: Implement sparepartspro_tool.py**

```python
# ambrio/router/tools/sparepartspro_tool.py
import aiosqlite, os
from ..tool_registry import tool

SPARE_DB = os.path.join(
    os.environ.get("APPDATA", ""), "SparePartsPro", "spare_parts.db"
)

@tool()
async def sparepartspro_query(sql: str) -> dict:
    """Run a READ-ONLY SELECT query against SparePartsPro database. Only SELECT allowed."""
    sql_clean = sql.strip()
    if not sql_clean.upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are permitted"}
    try:
        async with aiosqlite.connect(SPARE_DB) as c:
            c.row_factory = aiosqlite.Row
            cur = await c.execute(sql_clean)
            rows = await cur.fetchall()
        return {"rows": [dict(r) for r in rows[:100]]}  # cap at 100 rows
    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 3: Implement sandbox_tool.py stub (wired in Phase 3)**

```python
# ambrio/router/tools/sandbox_tool.py
from ..tool_registry import tool

_orchestrator = None

def init_sandbox_tool(orchestrator):
    global _orchestrator
    _orchestrator = orchestrator

@tool()
async def run_sandboxed_code(code: str, lang: str) -> dict:
    """Execute code in an isolated Docker/gVisor sandbox. Returns stdout, stderr, exit_code."""
    if not _orchestrator:
        return {"error": "sandbox not initialized"}
    result = await _orchestrator.execute({
        "type": "code_exec",
        "payload": {"code": code, "lang": lang},
        "constraints": {"timeout_s": 30, "network": False}
    })
    return {
        "verdict":   result.verdict,
        "stdout":    result.stdout,
        "stderr":    result.stderr,
        "artifact":  result.artifact
    }
```

- [ ] **Step 4: Commit**

```bash
git add ambrio/router/tools/
git commit -m "feat: built-in tools — memory, SparePartsPro query, sandbox"
```

---

### Task 2.6: Router Service (ZMQ ROUTER Asyncio Loop)

**Files:**
- Create: `ambrio/router/service.py`
- Create: `router_service.py`

- [ ] **Step 1: Implement service.py**

```python
# ambrio/router/service.py
import asyncio, zmq, zmq.asyncio, msgpack, logging
from .session_manager import SessionManager
from .tool_registry import ToolRegistry
from ..ui.ipc.message_protocol import Frame, MsgType

log = logging.getLogger(__name__)

class RouterService:
    BIND_ADDR = "tcp://127.0.0.1:5555"

    def __init__(self):
        self.sessions = SessionManager()
        self.tools    = ToolRegistry()
        self._socket: zmq.asyncio.Socket | None = None
        self._suspended: dict[str, bytes] = {}  # session_id → peer identity

    async def start(self, db_path: str = "ambrio.db"):
        await self.sessions.init(db_path)
        ctx = zmq.asyncio.Context()
        self._socket = ctx.socket(zmq.ROUTER)
        self._socket.bind(self.BIND_ADDR)
        log.info(f"Router bound to {self.BIND_ADDR}")
        await self._recv_loop()

    async def _recv_loop(self):
        while True:
            parts = await self._socket.recv_multipart()
            identity, _, raw = parts[0], parts[1], parts[2]
            frame = Frame.model_validate(msgpack.unpackb(raw, raw=False))
            asyncio.create_task(self._handle(identity, frame))

    async def _handle(self, identity: bytes, frame: Frame):
        try:
            match frame.type:
                case MsgType.CHAT_REQUEST:
                    await self._stream_chat(identity, frame)
                case MsgType.TOOL_RESULT:
                    await self._resume_after_tool(identity, frame)
        except Exception as e:
            await self._send(identity, Frame(
                session_id=frame.session_id,
                type=MsgType.ERROR,
                payload={"msg": str(e)}
            ))

    async def _stream_chat(self, identity: bytes, frame: Frame):
        session   = await self.sessions.get_or_create(frame.session_id)
        messages  = await session.build_context(frame.payload["content"])
        assistant = ""

        async for chunk in session.ollama.stream(messages, tools=self.tools.schema()):
            if chunk.get("done"):
                break
            msg = chunk.get("message", {})
            if msg.get("tool_calls"):
                # Gate tool through UI for human approval
                tool_call = msg["tool_calls"][0]
                self._suspended[frame.session_id] = identity
                await self._send(identity, Frame(
                    session_id=frame.session_id,
                    type=MsgType.TOOL_CALL,
                    payload=tool_call
                ))
                return
            token = msg.get("content", "")
            assistant += token
            await self._send(identity, Frame(
                session_id=frame.session_id,
                type=MsgType.CHAT_TOKEN,
                payload={"token": token}
            ))

        await session.persist_turn(frame.payload["content"], assistant)
        await self._send(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_DONE,
            payload={}
        ))

    async def _resume_after_tool(self, identity: bytes, frame: Frame):
        result = await self.tools.dispatch(
            frame.payload["tool_name"],
            frame.payload["tool_args"]
        )
        session = await self.sessions.get_or_create(frame.session_id)
        session.inject_tool_result(result)
        # Re-enter stream with tool result injected
        await self._stream_chat(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_REQUEST,
            payload={"content": ""}
        ))

    async def _send(self, identity: bytes, frame: Frame):
        await self._socket.send_multipart([
            identity, b"",
            msgpack.packb(frame.model_dump())
        ])
```

- [ ] **Step 2: Implement router_service.py entry point**

```python
# router_service.py
import asyncio, logging
from ambrio.router.service import RouterService

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    asyncio.run(RouterService().start())
```

- [ ] **Step 3: Commit**

```bash
git add ambrio/router/service.py router_service.py
git commit -m "feat: ZMQ ROUTER asyncio event loop — cognitive router"
```

---

## Phase 3 — Execution Sandbox

### Task 3.1: Sandbox Dockerfile + gVisor Config

**Files:**
- Create: `docker/sandbox.Dockerfile`
- Create: `docker/runsc-config.toml`

- [ ] **Step 1: Create sandbox.Dockerfile**

```dockerfile
# docker/sandbox.Dockerfile
FROM python:3.11-slim

# No network, no shell, no package manager access at runtime
RUN useradd -m -u 1000 sandbox
WORKDIR /work
USER sandbox

# Only stdlib — no pip install at runtime
ENTRYPOINT ["python"]
CMD ["main.py"]
```

- [ ] **Step 2: Create runsc-config.toml**

```toml
# docker/runsc-config.toml
[runsc]
platform = "systrap"
network  = "sandbox"

[runsc.strace]
enable = false

[runsc.debug]
log-packets = false
```

- [ ] **Step 3: Build sandbox image**

```powershell
docker build -f docker/sandbox.Dockerfile -t ambrio-sandbox:latest .
```

Expected: `Successfully tagged ambrio-sandbox:latest`

- [ ] **Step 4: Commit**

```bash
git add docker/
git commit -m "feat: sandbox Dockerfile + gVisor config"
```

---

### Task 3.2: Resource Policies

**Files:**
- Create: `ambrio/sandbox/policies/resource_limits.py`
- Create: `ambrio/sandbox/policies/allowlist.py`

- [ ] **Step 1: Implement**

```python
# ambrio/sandbox/policies/resource_limits.py
LIMITS = {
    "cpus":   "0.5",
    "memory": "256m",
    "pids":   50,
    "timeout_s": 30,
}
```

```python
# ambrio/sandbox/policies/allowlist.py
# Patterns that indicate unsafe output from sandbox
UNSAFE_OUTPUT_PATTERNS = [
    "import os",
    "subprocess",
    "__import__",
    "eval(",
    "exec(",
    "open(/etc",
    "open(/proc",
    "socket.connect",
    "requests.get",
    "urllib.request",
]

def is_safe_output(text: str) -> bool:
    lower = text.lower()
    return not any(p.lower() in lower for p in UNSAFE_OUTPUT_PATTERNS)
```

- [ ] **Step 2: Commit**

```bash
git add ambrio/sandbox/policies/
git commit -m "feat: sandbox resource limits + output safety allowlist"
```

---

### Task 3.3: Docker Runner

**Files:**
- Create: `ambrio/sandbox/docker_runner.py`
- Test: `tests/unit/test_docker_runner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_docker_runner.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from ambrio.sandbox.docker_runner import DockerRunner

@pytest.mark.asyncio
async def test_run_simple_code():
    runner = DockerRunner(use_gvisor=False)  # skip gVisor in unit test

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"42\n", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        stdout, stderr, code = await runner.run("print(42)", lang="python")

    assert code == 0
    assert "42" in stdout
```

- [ ] **Step 2: Run — confirm FAIL**

- [ ] **Step 3: Implement**

```python
# ambrio/sandbox/docker_runner.py
import asyncio, tempfile
from pathlib import Path
from .policies.resource_limits import LIMITS

SANDBOX_IMAGE  = "ambrio-sandbox:latest"
GVISOR_RUNTIME = "runsc"

class DockerRunner:
    def __init__(self, use_gvisor: bool = True):
        self.use_gvisor = use_gvisor

    async def run(
        self,
        code: str,
        lang: str = "python",
        network_enabled: bool = False,
        timeout: int = LIMITS["timeout_s"]
    ) -> tuple[str, str, int]:
        with tempfile.TemporaryDirectory() as tmpdir:
            fname = "main.py" if lang == "python" else "main.sh"
            (Path(tmpdir) / fname).write_text(code)
            cmd = self._build_cmd(tmpdir, lang, network_enabled)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=float(timeout)
                )
            except asyncio.TimeoutError:
                proc.kill()
                return "", "TIMEOUT", 124

        return stdout.decode(), stderr.decode(), proc.returncode

    def _build_cmd(self, workdir: str, lang: str, network: bool) -> list[str]:
        cmd = ["docker", "run", "--rm"]
        if self.use_gvisor:
            cmd += ["--runtime", GVISOR_RUNTIME]
        cmd += [
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "--network", "bridge" if network else "none",
            "--cpus",        LIMITS["cpus"],
            "--memory",      LIMITS["memory"],
            "--pids-limit",  str(LIMITS["pids"]),
            "-v", f"{workdir}:/work:ro",
            SANDBOX_IMAGE,
            fname := ("main.py" if lang == "python" else "main.sh")
        ]
        return cmd
```

- [ ] **Step 4: Run — confirm PASS**

```powershell
pytest tests/unit/test_docker_runner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ambrio/sandbox/docker_runner.py tests/unit/test_docker_runner.py
git commit -m "feat: Docker/gVisor runner with timeout + resource limits"
```

---

### Task 3.4: Checker + Maker + Orchestrator

**Files:**
- Create: `ambrio/sandbox/checker.py`
- Create: `ambrio/sandbox/maker.py`
- Create: `ambrio/sandbox/orchestrator.py`
- Test: `tests/unit/test_orchestrator.py`

- [ ] **Step 1: Implement checker.py**

```python
# ambrio/sandbox/checker.py
from dataclasses import dataclass
from .policies.allowlist import is_safe_output

class Verdict:
    PASS   = "pass"
    FAIL   = "fail"
    UNSAFE = "unsafe"

@dataclass
class MakerOutput:
    stdout:    str
    stderr:    str
    artifact:  dict
    exit_code: int

class CheckerAgent:
    async def grade(self, task: dict, output: MakerOutput) -> str:
        # 1. Safety scan
        if not is_safe_output(output.stdout + str(output.artifact)):
            return Verdict.UNSAFE
        # 2. Exit code
        if output.exit_code != 0:
            return Verdict.FAIL
        # 3. Type-specific validation
        match task.get("type"):
            case "db_query":
                if not isinstance(output.artifact.get("rows"), list):
                    return Verdict.FAIL
            case "codegen":
                if not output.artifact.get("code"):
                    return Verdict.FAIL
        return Verdict.PASS
```

- [ ] **Step 2: Implement maker.py**

```python
# ambrio/sandbox/maker.py
from .docker_runner import DockerRunner
from .checker import MakerOutput

class MakerAgent:
    def __init__(self):
        self.runner = DockerRunner()

    async def run(self, task: dict) -> MakerOutput:
        payload = task["payload"]
        code    = payload.get("code", "")
        lang    = payload.get("lang", "python")
        net     = task.get("constraints", {}).get("network", False)
        timeout = task.get("constraints", {}).get("timeout_s", 30)

        stdout, stderr, exit_code = await self.runner.run(
            code, lang=lang, network_enabled=net, timeout=timeout
        )
        # Attempt to parse structured artifact from stdout
        artifact = {}
        try:
            import json
            artifact = json.loads(stdout)
        except Exception:
            artifact = {"raw": stdout}

        return MakerOutput(
            stdout=stdout, stderr=stderr,
            artifact=artifact, exit_code=exit_code
        )
```

- [ ] **Step 3: Implement orchestrator.py**

```python
# ambrio/sandbox/orchestrator.py
from dataclasses import dataclass
from .maker   import MakerAgent
from .checker import CheckerAgent, Verdict

@dataclass
class SandboxResult:
    verdict:  str
    stdout:   str
    stderr:   str
    artifact: dict

class SandboxOrchestrator:
    MAX_RETRIES = 2

    def __init__(self):
        self.maker   = MakerAgent()
        self.checker = CheckerAgent()

    async def execute(self, task: dict) -> SandboxResult:
        for attempt in range(self.MAX_RETRIES + 1):
            maker_out = await self.maker.run(task)
            verdict   = await self.checker.grade(task, maker_out)

            if verdict == Verdict.UNSAFE:
                return SandboxResult(
                    verdict=Verdict.UNSAFE, stdout="", stderr="",
                    artifact={"reason": "checker: unsafe operation detected"}
                )
            if verdict == Verdict.PASS:
                return SandboxResult(
                    verdict=Verdict.PASS,
                    stdout=maker_out.stdout, stderr=maker_out.stderr,
                    artifact=maker_out.artifact
                )
            task["_checker_feedback"] = maker_out.stderr

        return SandboxResult(
            verdict=Verdict.FAIL, stdout="", stderr="max retries exceeded",
            artifact={}
        )
```

- [ ] **Step 4: Write + run orchestrator test**

```python
# tests/unit/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock, patch
from ambrio.sandbox.orchestrator import SandboxOrchestrator
from ambrio.sandbox.checker import MakerOutput, Verdict

@pytest.mark.asyncio
async def test_pass_verdict_returned():
    orch = SandboxOrchestrator()
    good_output = MakerOutput(stdout='{"rows":[]}', stderr="", artifact={"rows":[]}, exit_code=0)
    orch.maker.run   = AsyncMock(return_value=good_output)
    orch.checker.grade = AsyncMock(return_value=Verdict.PASS)

    result = await orch.execute({"type": "db_query", "payload": {}, "constraints": {}})
    assert result.verdict == Verdict.PASS

@pytest.mark.asyncio
async def test_unsafe_short_circuits():
    orch = SandboxOrchestrator()
    bad_output = MakerOutput(stdout="eval(dangerous)", stderr="", artifact={}, exit_code=0)
    orch.maker.run    = AsyncMock(return_value=bad_output)
    orch.checker.grade = AsyncMock(return_value=Verdict.UNSAFE)

    result = await orch.execute({"type": "code_exec", "payload": {}, "constraints": {}})
    assert result.verdict == Verdict.UNSAFE
    assert orch.maker.run.call_count == 1  # no retry on UNSAFE
```

```powershell
pytest tests/unit/test_orchestrator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ambrio/sandbox/ tests/unit/test_orchestrator.py
git commit -m "feat: Maker-Checker sandbox orchestrator"
```

---

## Phase 4 — PyQt6 Neumorphic UI

### Task 4.1: Neumorphic Theme

**Files:**
- Create: `ambrio/ui/theme/palette.py`
- Create: `ambrio/ui/theme/neumorphic.qss`

- [ ] **Step 1: palette.py**

```python
# ambrio/ui/theme/palette.py
from PyQt6.QtGui import QColor

# Neumorphic base: soft dark slate
BG         = QColor("#1e2130")
BG_LIGHT   = QColor("#252839")
BG_SHADOW  = QColor("#181a28")
ACCENT     = QColor("#7c6af7")      # Purple
ACCENT_ALT = QColor("#5de0e6")      # Cyan
TEXT       = QColor("#d4d8f0")
TEXT_DIM   = QColor("#7880a8")
SUCCESS    = QColor("#56cfb2")
ERROR      = QColor("#f06292")
BORDER     = QColor("#2e3248")

SHADOW_LIGHT = "rgba(255,255,255,0.04)"
SHADOW_DARK  = "rgba(0,0,0,0.4)"
```

- [ ] **Step 2: neumorphic.qss**

```css
/* ambrio/ui/theme/neumorphic.qss */
QMainWindow, QWidget {
    background-color: #1e2130;
    color: #d4d8f0;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 14px;
}

/* Neumorphic card — raised */
.NeuCard {
    background-color: #1e2130;
    border-radius: 16px;
    border: none;
    box-shadow: 6px 6px 12px rgba(0,0,0,0.4),
               -4px -4px 10px rgba(255,255,255,0.04);
}

/* Input bar */
QTextEdit, QLineEdit {
    background-color: #181a28;
    color: #d4d8f0;
    border: 1px solid #2e3248;
    border-radius: 12px;
    padding: 10px 14px;
    selection-background-color: #7c6af7;
}

QTextEdit:focus, QLineEdit:focus {
    border: 1px solid #7c6af7;
}

/* Send button */
QPushButton#sendBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #7c6af7, stop:1 #5de0e6);
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 10px 22px;
    font-weight: 600;
}

QPushButton#sendBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #9580ff, stop:1 #72eeff);
}

/* Sidebar */
QListWidget {
    background-color: #181a28;
    border: none;
    border-radius: 10px;
}

QListWidget::item:selected {
    background-color: #2e3248;
    border-left: 3px solid #7c6af7;
    border-radius: 6px;
}

/* Scrollbar */
QScrollBar:vertical {
    width: 6px;
    background: transparent;
}
QScrollBar::handle:vertical {
    background: #2e3248;
    border-radius: 3px;
}
```

- [ ] **Step 3: Commit**

```bash
git add ambrio/ui/theme/
git commit -m "feat: Neumorphic dark theme — palette + QSS"
```

---

### Task 4.2: ZMQ Bridge (QThread + asyncio)

**Files:**
- Create: `ambrio/ui/ipc/qt_zmq_bridge.py`

- [ ] **Step 1: Implement**

```python
# ambrio/ui/ipc/qt_zmq_bridge.py
import zmq, zmq.asyncio, asyncio, msgpack, logging
from PyQt6.QtCore import QThread, pyqtSignal
from .message_protocol import Frame, MsgType

log = logging.getLogger(__name__)

class ZmqBridge(QThread):
    token_received = pyqtSignal(str, str)    # session_id, token
    done_received  = pyqtSignal(str)          # session_id
    tool_call_gate = pyqtSignal(str, dict)    # session_id, tool_payload
    error_received = pyqtSignal(str, str)     # session_id, message

    ROUTER_ADDR = "tcp://127.0.0.1:5555"

    def __init__(self):
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._socket: zmq.asyncio.Socket | None = None
        self._send_queue: asyncio.Queue | None = None

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._send_queue = asyncio.Queue()
        self._loop.run_until_complete(self._io_loop())

    async def _io_loop(self):
        ctx = zmq.asyncio.Context()
        self._socket = ctx.socket(zmq.DEALER)
        self._socket.connect(self.ROUTER_ADDR)
        log.info(f"ZMQ bridge connected to {self.ROUTER_ADDR}")
        await asyncio.gather(self._recv_loop(), self._send_loop())

    async def _recv_loop(self):
        while True:
            raw = await self._socket.recv()
            try:
                frame = Frame.model_validate(msgpack.unpackb(raw, raw=False))
                self._dispatch(frame)
            except Exception as e:
                log.warning(f"Bad frame: {e}")

    async def _send_loop(self):
        while True:
            frame: Frame = await self._send_queue.get()
            await self._socket.send(msgpack.packb(frame.model_dump()))

    def _dispatch(self, frame: Frame):
        match frame.type:
            case MsgType.CHAT_TOKEN:
                self.token_received.emit(frame.session_id, frame.payload["token"])
            case MsgType.CHAT_DONE:
                self.done_received.emit(frame.session_id)
            case MsgType.TOOL_CALL:
                self.tool_call_gate.emit(frame.session_id, frame.payload)
            case MsgType.ERROR:
                self.error_received.emit(frame.session_id, frame.payload.get("msg",""))

    def send(self, frame: Frame):
        """Thread-safe — call from any Qt thread."""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._send_queue.put_nowait, frame)

    def stop(self):
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
```

- [ ] **Step 2: Commit**

```bash
git add ambrio/ui/ipc/qt_zmq_bridge.py
git commit -m "feat: ZMQ DEALER bridge on QThread with asyncio inner loop"
```

---

### Task 4.3: Chat Widget

**Files:**
- Create: `ambrio/ui/chat_widget.py`

- [ ] **Step 1: Implement**

```python
# ambrio/ui/chat_widget.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy, QFrame
from PyQt6.QtCore    import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui     import QColor, QPalette

class MessageBubble(QFrame):
    def __init__(self, text: str, role: str):
        super().__init__()
        self.setObjectName("msgBubble")
        layout = QVBoxLayout(self)
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._label)

        # Neumorphic bubble styles per role
        if role == "user":
            self.setStyleSheet("""
                QFrame { background:#252839; border-radius:14px;
                         border-left:3px solid #7c6af7; padding:10px 14px;
                         margin-left:60px; margin-right:8px; }
            """)
        else:
            self.setStyleSheet("""
                QFrame { background:#1e2130; border-radius:14px;
                         border-left:3px solid #5de0e6; padding:10px 14px;
                         margin-right:60px; margin-left:8px; }
            """)

    def append_token(self, token: str):
        self._label.setText(self._label.text() + token)


class ChatWidget(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.verticalScrollBar().rangeChanged.connect(self._scroll_to_bottom)

        self._container = QWidget()
        self._layout    = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setSpacing(8)
        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        self._active_bubble: MessageBubble | None = None

    def add_user_message(self, text: str):
        bubble = MessageBubble(text, "user")
        self._layout.addWidget(bubble)

    def begin_assistant_message(self) -> MessageBubble:
        bubble = MessageBubble("", "assistant")
        self._layout.addWidget(bubble)
        self._active_bubble = bubble
        return bubble

    def append_token(self, token: str):
        if self._active_bubble:
            self._active_bubble.append_token(token)

    def finalize_assistant_message(self):
        self._active_bubble = None

    def _scroll_to_bottom(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
```

- [ ] **Step 2: Commit**

```bash
git add ambrio/ui/chat_widget.py
git commit -m "feat: streaming chat widget with neumorphic message bubbles"
```

---

### Task 4.4: Input Bar + Main Window + App Entry

**Files:**
- Create: `ambrio/ui/input_bar.py`
- Create: `ambrio/ui/sidebar.py`
- Create: `ambrio/ui/main_window.py`
- Create: `app.py`
- Create: `ambrio.ps1`

- [ ] **Step 1: input_bar.py**

```python
# ambrio/ui/input_bar.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QTextEdit, QPushButton
from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtGui     import QKeyEvent

class InputBar(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._input = _EnterTextEdit()
        self._input.setPlaceholderText("Message Ambrio…  (Shift+Enter for newline)")
        self._input.setMaximumHeight(120)
        self._input.submitted.connect(self._on_submit)

        self._btn = QPushButton("Send ↑")
        self._btn.setObjectName("sendBtn")
        self._btn.setFixedWidth(90)
        self._btn.clicked.connect(self._on_submit)

        layout.addWidget(self._input)
        layout.addWidget(self._btn)

    def _on_submit(self):
        text = self._input.toPlainText().strip()
        if text:
            self._input.clear()
            self.submitted.emit(text)

    def set_enabled(self, enabled: bool):
        self._input.setEnabled(enabled)
        self._btn.setEnabled(enabled)


class _EnterTextEdit(QTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Return and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submitted.emit()
        else:
            super().keyPressEvent(e)
```

- [ ] **Step 2: sidebar.py**

```python
# ambrio/ui/sidebar.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QPushButton, QLabel
from PyQt6.QtCore    import pyqtSignal
import uuid

class Sidebar(QWidget):
    session_selected = pyqtSignal(str)
    new_session      = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)

        title = QLabel("⚡ Ambrio")
        title.setStyleSheet("font-size:18px; font-weight:700; color:#7c6af7;")
        layout.addWidget(title)

        self._new_btn = QPushButton("+ New Session")
        self._new_btn.setObjectName("sendBtn")
        self._new_btn.clicked.connect(self._create_session)
        layout.addWidget(self._new_btn)

        self._list = QListWidget()
        self._list.currentTextChanged.connect(self.session_selected)
        layout.addWidget(self._list)
        layout.addStretch()

    def _create_session(self):
        sid = str(uuid.uuid4())
        self._list.addItem(sid[:8])
        self._list.setCurrentRow(self._list.count() - 1)
        self.new_session.emit(sid)

    def add_session(self, session_id: str):
        self._list.addItem(session_id[:8])
```

- [ ] **Step 3: main_window.py**

```python
# ambrio/ui/main_window.py
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QMessageBox
from .chat_widget   import ChatWidget
from .input_bar     import InputBar
from .sidebar       import Sidebar
from .ipc.qt_zmq_bridge   import ZmqBridge
from .ipc.message_protocol import Frame, MsgType
import uuid

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ambrio — Local AI")
        self.resize(1200, 800)

        self._session_id = str(uuid.uuid4())
        self._bridge     = ZmqBridge()
        self._bridge.token_received.connect(self._on_token)
        self._bridge.done_received.connect(self._on_done)
        self._bridge.tool_call_gate.connect(self._on_tool_call)
        self._bridge.error_received.connect(self._on_error)
        self._bridge.start()

        # Layout
        root    = QWidget(); self.setCentralWidget(root)
        h_lay   = QHBoxLayout(root)

        self._sidebar = Sidebar()
        self._sidebar.new_session.connect(self._set_session)
        h_lay.addWidget(self._sidebar)

        right   = QWidget()
        v_lay   = QVBoxLayout(right)
        self._chat  = ChatWidget()
        self._input = InputBar()
        self._input.submitted.connect(self._on_send)
        v_lay.addWidget(self._chat)
        v_lay.addWidget(self._input)
        h_lay.addWidget(right)

        # Boot session
        self._sidebar.add_session(self._session_id)

    def _set_session(self, sid: str):
        self._session_id = sid

    def _on_send(self, text: str):
        self._chat.add_user_message(text)
        self._chat.begin_assistant_message()
        self._input.set_enabled(False)
        self._bridge.send(Frame(
            session_id=self._session_id,
            type=MsgType.CHAT_REQUEST,
            payload={"content": text}
        ))

    def _on_token(self, session_id: str, token: str):
        if session_id == self._session_id:
            self._chat.append_token(token)

    def _on_done(self, session_id: str):
        if session_id == self._session_id:
            self._chat.finalize_assistant_message()
            self._input.set_enabled(True)

    def _on_tool_call(self, session_id: str, payload: dict):
        """Human-in-the-loop tool approval dialog."""
        box = QMessageBox(self)
        box.setWindowTitle("Tool Approval Required")
        box.setText(f"Ambrio wants to call tool:\n\n{payload.get('function',{}).get('name','?')}\n\nArguments:\n{payload.get('function',{}).get('arguments','{}')}")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self._bridge.send(Frame(
                session_id=session_id,
                type=MsgType.TOOL_RESULT,
                payload={
                    "tool_name": payload.get("function",{}).get("name"),
                    "tool_args": payload.get("function",{}).get("arguments",{})
                }
            ))

    def _on_error(self, session_id: str, msg: str):
        self._chat.finalize_assistant_message()
        self._input.set_enabled(True)
        QMessageBox.warning(self, "Error", msg)

    def closeEvent(self, event):
        self._bridge.stop()
        self._bridge.wait(2000)
        super().closeEvent(event)
```

- [ ] **Step 4: app.py**

```python
# app.py
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui     import QFontDatabase, QFont
from ambrio.ui.main_window import MainWindow

QSS_PATH = Path(__file__).parent / "ambrio/ui/theme/neumorphic.qss"

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_PATH.read_text())
    app.setFont(QFont("Segoe UI", 12))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: ambrio.ps1 launcher**

```powershell
# ambrio.ps1
$root = $PSScriptRoot
$venv = "$root\.venv\Scripts\python.exe"

Write-Host "Starting Ambrio Router..." -ForegroundColor Cyan
$router = Start-Process $venv -ArgumentList "router_service.py" `
    -WorkingDirectory $root -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 1

Write-Host "Launching Ambrio UI..." -ForegroundColor Green
& $venv app.py

Write-Host "Shutting down router..." -ForegroundColor Yellow
Stop-Process -Id $router.Id -ErrorAction SilentlyContinue
```

- [ ] **Step 6: Commit everything**

```bash
git add ambrio/ui/ app.py ambrio.ps1
git commit -m "feat: PyQt6 Neumorphic UI — chat, input, sidebar, main window, launcher"
```

---

## Final Smoke Test

- [ ] Start router: `python router_service.py`
- [ ] Start UI: `python app.py`
- [ ] Type a message → verify streaming tokens appear in UI
- [ ] Open new session → verify isolation
- [ ] Trigger tool call → verify approval dialog appears
- [ ] Close window → verify router process is cleaned up

```powershell
# One-shot launch
.\ambrio.ps1
```

---

## Dependencies Summary

```
PyQt6>=6.7.0        — UI framework
pyzmq>=26.0.0       — IPC (DEALER/ROUTER)
aiosqlite>=0.20.0   — Async SQLite + FTS5
aiohttp>=3.9.0      — Ollama HTTP client
pydantic>=2.7.0     — Frame schema validation
tiktoken>=0.7.0     — Token counting for context pruner
msgpack>=1.0.8      — Fast binary IPC serialization
pytest-asyncio      — Async test runner
```
