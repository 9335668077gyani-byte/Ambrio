# Ambrio Desktop Phase 3 — Architecture Design Spec
**Date:** 2026-06-06  
**Status:** Approved  
**Stack:** Python 3.10+, PyQt6, Ollama, SQLite/FTS5, Docker/gVisor, ZeroMQ

---

## System Overview

Three-tier decoupled architecture:

```
┌─────────────────────────────────────────────────────┐
│  TIER 1: UI LAYER                                   │
│  PyQt6 (Neumorphic) → ZeroMQ DEALER socket          │
└─────────────────────┬───────────────────────────────┘
                      │ IPC (tcp://127.0.0.1:5555)
┌─────────────────────▼───────────────────────────────┐
│  TIER 2: COGNITIVE ROUTER (headless microservice)   │
│  Asyncio event loop + ZeroMQ ROUTER socket          │
│  Memory: SQLite FTS5 | Tool RPC registry            │
└──────────┬──────────────────────────┬───────────────┘
           │ Ollama REST              │ subprocess / docker exec
┌──────────▼──────────┐  ┌───────────▼───────────────┐
│  CodeGemma (Ollama) │  │  TIER 3: SANDBOX           │
│  localhost:11434    │  │  Docker + gVisor (runsc)   │
└─────────────────────┘  │  Maker-Checker subagents   │
                         └───────────────────────────┘
```

---

## Modular Directory Tree

```
Ambrio/
├── ambrio/                         # Core Python package
│   ├── __init__.py
│   │
│   ├── ui/                         # TIER 1 — PyQt6 Frontend
│   │   ├── __init__.py
│   │   ├── main_window.py          # QMainWindow shell, no logic
│   │   ├── chat_widget.py          # Message list, streaming token handler
│   │   ├── input_bar.py            # Multiline input, slash-command autocomplete
│   │   ├── sidebar.py              # Session list, memory browser, settings
│   │   ├── theme/
│   │   │   ├── neumorphic.qss      # Base QSS tokens
│   │   │   └── palette.py          # HSL color constants → QColor
│   │   └── ipc/
│   │       ├── qt_zmq_bridge.py    # QThread wrapping zmq.asyncio.Context
│   │       └── message_protocol.py # Pydantic schemas for IPC frames
│   │
│   ├── router/                     # TIER 2 — Cognitive Router (headless)
│   │   ├── __init__.py
│   │   ├── service.py              # Entry: asyncio.run(), ZMQ ROUTER loop
│   │   ├── session_manager.py      # Session lifecycle, context window mgmt
│   │   ├── context_pruner.py       # FTS5 retrieval + sliding window logic
│   │   ├── ollama_client.py        # Async streaming client for /api/chat
│   │   ├── tool_registry.py        # @tool decorator, RPC dispatch table
│   │   ├── tools/                  # Native Python tool implementations
│   │   │   ├── __init__.py
│   │   │   ├── memory_tool.py      # FTS5 search/store
│   │   │   ├── sparepartspro_tool.py # DB bridge to SparePartsPro SQLite
│   │   │   └── sandbox_tool.py     # Dispatch to Tier 3 sandbox
│   │   └── memory/
│   │       ├── db.py               # SQLite connection pool, migrations
│   │       ├── fts5_store.py       # INSERT/SEARCH over fts5 virtual table
│   │       └── schema.sql          # FTS5 table + metadata schema
│   │
│   └── sandbox/                    # TIER 3 — Execution Sandbox
│       ├── __init__.py
│       ├── orchestrator.py         # Maker-Checker coordinator
│       ├── maker.py                # Worker agent: code exec, DB query, codegen
│       ├── checker.py              # Grader agent: safety + correctness verify
│       ├── docker_runner.py        # docker run / gVisor (runsc) subprocess mgmt
│       └── policies/
│           ├── allowlist.py        # Syscall/network egress allowlist
│           └── resource_limits.py  # CPU/mem/time cgroup constraints
│
├── router_service.py               # __main__ entry for Cognitive Router process
├── app.py                          # __main__ entry for PyQt6 UI process
├── ambrio.ps1 / ambrio.sh          # Launch both processes, manage PIDs
├── docker/
│   ├── sandbox.Dockerfile          # Minimal Python image for sandbox containers
│   └── runsc-config.toml           # gVisor runtime config
├── db/
│   └── schema.sql                  # Authoritative schema (router runs migrations)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── sandbox/                    # Isolated container tests
├── docs/specs/
│   └── 2026-06-06-ambrio-desktop-phase3-design.md
└── requirements.txt                # pyzmq, pyqt6, aiohttp, pydantic, aiosqlite
```

---

## IPC Message Protocol (ZeroMQ DEALER ↔ ROUTER)

All frames are msgpack-encoded Pydantic models.

```python
# ambrio/ui/ipc/message_protocol.py
from enum import StrEnum
from pydantic import BaseModel, Field
import uuid, time

class MsgType(StrEnum):
    CHAT_REQUEST   = "chat.request"
    CHAT_TOKEN     = "chat.token"       # streaming SSE-style
    CHAT_DONE      = "chat.done"
    TOOL_CALL      = "tool.call"        # router→ui for approval gating
    TOOL_RESULT    = "tool.result"
    SANDBOX_SUBMIT = "sandbox.submit"
    SANDBOX_RESULT = "sandbox.result"
    ERROR          = "error"
    SESSION_SYNC   = "session.sync"     # sidebar state push

class Frame(BaseModel):
    id:         str      = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    type:       MsgType
    payload:    dict
    ts:         float    = Field(default_factory=time.monotonic)
```

---

## Tier 1 — UI/UX Layer

### `qt_zmq_bridge.py` — Non-blocking IPC on QThread

```python
# ambrio/ui/ipc/qt_zmq_bridge.py
import zmq, zmq.asyncio, asyncio, msgpack
from PyQt6.QtCore import QThread, pyqtSignal
from .message_protocol import Frame, MsgType

class ZmqBridge(QThread):
    """Runs asyncio event loop on a QThread. Emits Qt signals → UI stays on main thread."""
    token_received   = pyqtSignal(str, str)   # session_id, token
    done_received    = pyqtSignal(str)         # session_id
    tool_call_gate   = pyqtSignal(str, dict)   # session_id, tool_payload (approval gate)
    sandbox_result   = pyqtSignal(str, dict)
    error_received   = pyqtSignal(str, str)

    ROUTER_ADDR = "tcp://127.0.0.1:5555"

    def __init__(self):
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._socket: zmq.asyncio.Socket | None = None
        self._send_queue: asyncio.Queue[Frame] = asyncio.Queue()

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._io_loop())

    async def _io_loop(self):
        ctx = zmq.asyncio.Context()
        self._socket = ctx.socket(zmq.DEALER)
        self._socket.connect(self.ROUTER_ADDR)
        await asyncio.gather(self._recv_loop(), self._send_loop())

    async def _recv_loop(self):
        while True:
            raw = await self._socket.recv()
            frame = Frame.model_validate(msgpack.unpackb(raw))
            self._dispatch(frame)

    async def _send_loop(self):
        while True:
            frame = await self._send_queue.get()
            await self._socket.send(msgpack.packb(frame.model_dump()))

    def _dispatch(self, frame: Frame):
        match frame.type:
            case MsgType.CHAT_TOKEN:
                self.token_received.emit(frame.session_id, frame.payload["token"])
            case MsgType.CHAT_DONE:
                self.done_received.emit(frame.session_id)
            case MsgType.TOOL_CALL:
                self.tool_call_gate.emit(frame.session_id, frame.payload)
            case MsgType.SANDBOX_RESULT:
                self.sandbox_result.emit(frame.session_id, frame.payload)
            case MsgType.ERROR:
                self.error_received.emit(frame.session_id, frame.payload["msg"])

    def send(self, frame: Frame):
        """Thread-safe enqueue from main Qt thread."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._send_queue.put_nowait, frame)
```

---

## Tier 2 — Cognitive Router

### `service.py` — Asyncio ROUTER event loop

```python
# ambrio/router/service.py
import asyncio, zmq, zmq.asyncio, msgpack
from .session_manager import SessionManager
from .tool_registry import ToolRegistry
from .message_protocol import Frame, MsgType

class RouterService:
    BIND_ADDR = "tcp://127.0.0.1:5555"

    def __init__(self):
        self.sessions   = SessionManager()
        self.tools      = ToolRegistry()
        self._socket: zmq.asyncio.Socket | None = None
        self._peers: dict[bytes, bytes] = {}  # identity → session_id

    async def run(self):
        ctx = zmq.asyncio.Context()
        self._socket = ctx.socket(zmq.ROUTER)
        self._socket.bind(self.BIND_ADDR)
        await self._recv_loop()

    async def _recv_loop(self):
        while True:
            identity, _, raw = await self._socket.recv_multipart()
            frame = Frame.model_validate(msgpack.unpackb(raw))
            self._peers[identity] = frame.session_id.encode()
            asyncio.create_task(self._handle(identity, frame))

    async def _handle(self, identity: bytes, frame: Frame):
        match frame.type:
            case MsgType.CHAT_REQUEST:
                await self._stream_chat(identity, frame)
            case MsgType.TOOL_RESULT:
                await self._resume_tool(identity, frame)
            case MsgType.SESSION_SYNC:
                await self._sync_session(identity, frame)

    async def _stream_chat(self, identity: bytes, frame: Frame):
        session = await self.sessions.get_or_create(frame.session_id)
        messages = await session.build_context(frame.payload["content"])

        async for chunk in session.ollama.stream(messages):
            if chunk.get("tool_call"):
                await self._gate_tool(identity, frame.session_id, chunk)
                return  # suspend until TOOL_RESULT arrives
            token = chunk["message"]["content"]
            await self._send(identity, Frame(
                session_id=frame.session_id,
                type=MsgType.CHAT_TOKEN,
                payload={"token": token}
            ))

        await session.persist_turn(frame.payload["content"])
        await self._send(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_DONE,
            payload={}
        ))

    async def _gate_tool(self, identity: bytes, session_id: str, chunk: dict):
        """Forward tool call to UI for human-in-the-loop approval."""
        await self._send(identity, Frame(
            session_id=session_id,
            type=MsgType.TOOL_CALL,
            payload=chunk["tool_call"]
        ))

    async def _resume_tool(self, identity: bytes, frame: Frame):
        result = await self.tools.dispatch(
            frame.payload["tool_name"],
            frame.payload["tool_args"]
        )
        session = await self.sessions.get_or_create(frame.session_id)
        session.inject_tool_result(result)
        await self._stream_chat(identity, frame)

    async def _send(self, identity: bytes, frame: Frame):
        await self._socket.send_multipart(
            [identity, b"", msgpack.packb(frame.model_dump())]
        )
```

### `context_pruner.py` — FTS5 Retrieval + Sliding Window

```python
# ambrio/router/context_pruner.py
import tiktoken
from .memory.fts5_store import FTS5Store

CONTEXT_BUDGET   = 7000   # tokens — leave 1192 for response
RECENT_MSGS_KEEP = 6      # always keep last N verbatim
SUMMARY_TRIGGER  = 20     # summarize when history > N messages

enc = tiktoken.get_encoding("cl100k_base")

class ContextPruner:
    def __init__(self, store: FTS5Store, session_id: str):
        self.store      = store
        self.session_id = session_id

    async def build(self, new_content: str, full_history: list[dict]) -> list[dict]:
        """
        Returns a token-bounded message list:
          [system_prompt] + [fts5_recalled] + [recent_tail] + [new_user_msg]
        """
        system    = [{"role": "system", "content": await self._system_prompt()}]
        recent    = full_history[-RECENT_MSGS_KEEP:]
        recalled  = await self._recall(new_content, exclude=recent)

        budget    = CONTEXT_BUDGET - self._tokens(system)
        context   = self._fit(recalled + recent, budget)
        context   = system + context + [{"role": "user", "content": new_content}]
        return context

    async def _recall(self, query: str, exclude: list[dict]) -> list[dict]:
        exclude_contents = {m["content"] for m in exclude}
        rows = await self.store.search(self.session_id, query, limit=10)
        return [
            {"role": r["role"], "content": r["content"]}
            for r in rows
            if r["content"] not in exclude_contents
        ]

    def _fit(self, messages: list[dict], budget: int) -> list[dict]:
        """Greedy-drop oldest until within budget."""
        while messages and self._tokens(messages) > budget:
            messages.pop(0)
        return messages

    def _tokens(self, messages: list[dict]) -> int:
        return sum(len(enc.encode(m["content"])) for m in messages)

    async def _system_prompt(self) -> str:
        return (
            "You are Ambrio, a private autonomous AI assistant running 100% locally. "
            "You have access to tools: memory_search, sparepartspro_query, run_sandboxed_code. "
            "Always reason step-by-step before invoking tools. "
            "Never expose internal tool names or raw JSON to the user."
        )
```

### `tool_registry.py` — RPC Dispatch

```python
# ambrio/router/tool_registry.py
import functools, inspect
from typing import Callable, Any

_REGISTRY: dict[str, Callable] = {}

def tool(name: str | None = None):
    """Decorator to register a coroutine as an RPC-callable tool."""
    def decorator(fn: Callable):
        key = name or fn.__name__
        assert inspect.iscoroutinefunction(fn), f"{key} must be async"
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
            raise KeyError(f"Unknown tool: {tool_name}")
        return await fn(**args)

    def schema(self) -> list[dict]:
        """Returns Ollama-compatible tool schema for all registered tools."""
        schemas = []
        for name, fn in _REGISTRY.items():
            sig = inspect.signature(fn)
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": fn.__doc__ or "",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            p: {"type": "string"} for p in sig.parameters
                        },
                        "required": list(sig.parameters.keys())
                    }
                }
            })
        return schemas
```

---

## Tier 3 — Execution Sandbox (Maker-Checker)

### `orchestrator.py` — Maker-Checker Coordinator

```python
# ambrio/sandbox/orchestrator.py
import asyncio
from dataclasses import dataclass
from enum import StrEnum
from .maker  import MakerAgent
from .checker import CheckerAgent

class Verdict(StrEnum):
    PASS    = "pass"
    FAIL    = "fail"
    UNSAFE  = "unsafe"

@dataclass
class SandboxResult:
    verdict:  Verdict
    stdout:   str
    stderr:   str
    artifact: dict   # structured output from maker

class SandboxOrchestrator:
    MAX_RETRIES = 2

    def __init__(self):
        self.maker   = MakerAgent()
        self.checker = CheckerAgent()

    async def execute(self, task: dict) -> SandboxResult:
        """
        task = {
          "type": "code_exec" | "db_query" | "codegen",
          "payload": {...},
          "constraints": {"timeout_s": 30, "network": false}
        }
        """
        for attempt in range(self.MAX_RETRIES + 1):
            maker_out  = await self.maker.run(task)
            verdict    = await self.checker.grade(task, maker_out)

            if verdict == Verdict.UNSAFE:
                return SandboxResult(
                    verdict=Verdict.UNSAFE,
                    stdout="", stderr="",
                    artifact={"reason": "checker: unsafe operation detected"}
                )
            if verdict == Verdict.PASS:
                return SandboxResult(
                    verdict=Verdict.PASS,
                    stdout=maker_out.stdout,
                    stderr=maker_out.stderr,
                    artifact=maker_out.artifact
                )
            # FAIL → retry with checker feedback injected into next task
            task["_checker_feedback"] = maker_out.stderr

        return SandboxResult(verdict=Verdict.FAIL, stdout="", stderr="max retries", artifact={})
```

### `docker_runner.py` — gVisor Container Execution

```python
# ambrio/sandbox/docker_runner.py
import asyncio, json, tempfile, os
from pathlib import Path
from .policies.resource_limits import LIMITS

SANDBOX_IMAGE  = "ambrio-sandbox:latest"
GVISOR_RUNTIME = "runsc"              # must be registered in /etc/docker/daemon.json

class DockerRunner:
    async def run(
        self,
        code: str,
        lang: str = "python",
        network_enabled: bool = False,
        timeout: int = 30
    ) -> tuple[str, str, int]:
        """Returns (stdout, stderr, exit_code)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "main.py"
            src.write_text(code)

            cmd = self._build_cmd(tmpdir, lang, network_enabled)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return "", "TIMEOUT", 124

        return stdout.decode(), stderr.decode(), proc.returncode

    def _build_cmd(self, workdir: str, lang: str, network: bool) -> list[str]:
        net_flag  = "" if network else "--network none"
        entry     = "python /work/main.py" if lang == "python" else f"bash /work/main.sh"
        return [
            "docker", "run", "--rm",
            "--runtime", GVISOR_RUNTIME,
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            *([net_flag] if net_flag else ["--network", "none"]),
            "--cpus",   str(LIMITS["cpus"]),
            "--memory", LIMITS["memory"],
            "--pids-limit", str(LIMITS["pids"]),
            "-v", f"{workdir}:/work:ro",
            SANDBOX_IMAGE,
            *entry.split()
        ]
```

### `checker.py` — Grader Agent

```python
# ambrio/sandbox/checker.py
from dataclasses import dataclass
from .orchestrator import Verdict

UNSAFE_PATTERNS = [
    "import os", "subprocess", "__import__",
    "eval(", "exec(", "open(/etc", "open(/proc",
    "socket.connect", "requests.get",
]

@dataclass
class MakerOutput:
    stdout:   str
    stderr:   str
    artifact: dict
    exit_code: int

class CheckerAgent:
    async def grade(self, task: dict, output: MakerOutput) -> Verdict:
        # 1. Static safety scan on artifact/stdout
        combined = output.stdout + str(output.artifact)
        for pattern in UNSAFE_PATTERNS:
            if pattern in combined:
                return Verdict.UNSAFE

        # 2. Exit code check
        if output.exit_code != 0:
            return Verdict.FAIL

        # 3. Task-type specific validation
        match task.get("type"):
            case "db_query":
                if not isinstance(output.artifact.get("rows"), list):
                    return Verdict.FAIL
            case "codegen":
                if not output.artifact.get("code"):
                    return Verdict.FAIL

        return Verdict.PASS
```

---

## Memory Schema — SQLite FTS5

```sql
-- db/schema.sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    meta        TEXT DEFAULT '{}'  -- JSON blob
);

CREATE TABLE messages (
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

-- FTS5 virtual table for cross-session semantic search
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    role UNINDEXED,
    session_id UNINDEXED,
    message_id UNINDEXED,
    tokenize = 'porter ascii'
);

-- Sync trigger: messages → messages_fts
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, role, session_id, message_id)
    VALUES (new.rowid, new.content, new.role, new.session_id, new.id);
END;

CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE message_id = old.id;
END;

CREATE INDEX idx_messages_session ON messages(session_id, ts DESC);
CREATE INDEX idx_messages_ts ON messages(ts DESC);
```

---

## State Flow Diagram

```
USER INPUT (Qt main thread)
    │
    ▼
input_bar.py → ZmqBridge.send(CHAT_REQUEST)
    │
    │ [QThread — non-blocking]
    ▼
ZMQ DEALER → tcp://127.0.0.1:5555
    │
    ▼
RouterService._handle(CHAT_REQUEST)
    │
    ├── SessionManager.get_or_create()
    ├── ContextPruner.build()          ← FTS5 recall + sliding window
    ├── OllamaClient.stream()          ← async generator
    │       │
    │       ├── [no tool_call] → emit CHAT_TOKEN × N → emit CHAT_DONE
    │       │                       ↓ (Qt main thread via signal)
    │       │                   ChatWidget.append_token()
    │       │
    │       └── [tool_call detected]
    │               │
    │               ├── emit TOOL_CALL → UI shows approval dialog
    │               │
    │               └── [user approves] → send TOOL_RESULT back to router
    │                       │
    │                       ├── ToolRegistry.dispatch(tool_name, args)
    │                       │       │
    │                       │       └── sandbox_tool → SandboxOrchestrator.execute()
    │                       │               │
    │                       │               ├── MakerAgent.run() → DockerRunner (gVisor)
    │                       │               └── CheckerAgent.grade() → Verdict
    │                       │
    │                       └── inject result → resume stream
    │
    └── SessionManager.persist_turn() → SQLite + FTS5 index
```

---

## Launch Architecture

```powershell
# ambrio.ps1 — launches both processes
Start-Process python -ArgumentList "router_service.py" -NoNewWindow
Start-Sleep 1   # wait for ZMQ bind
python app.py   # Qt main process (blocks until window closed)
```

Two separate OS processes. Router survives UI crash. UI reconnects on restart (DEALER auto-reconnects).
