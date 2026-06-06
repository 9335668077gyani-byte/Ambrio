# ⚡ Ambrio — Local-First Autonomous AI Desktop

> **100% offline. 100% private. Runs on your machine.**

Ambrio is a standalone autonomous AI assistant built on a hybrid microservice architecture. No cloud. No subscriptions. No data leaving your machine.

---

## Architecture — Phase 3

```
┌──────────────────────────────┐
│  PyQt6 UI (Neumorphic)       │  ← Main thread only
│  ZMQ DEALER → bridge thread  │
└──────────────┬───────────────┘
               │ tcp://127.0.0.1:5555 (msgpack frames)
┌──────────────▼───────────────┐
│  Cognitive Router (headless) │  ← Separate OS process
│  asyncio + ZMQ ROUTER        │
│  FTS5 memory · Tool RPC      │
│  Ollama streaming client     │
└──────────────┬───────────────┘
               │
   ┌───────────┴───────────┐
   │  Ollama (CodeGemma)   │   Docker/gVisor Sandbox
   │  localhost:11434       │   Maker-Checker pattern
   └───────────────────────┘
```

## Stack

| Layer | Tech |
|---|---|
| UI | PyQt6, Neumorphic QSS |
| IPC | ZeroMQ (DEALER/ROUTER), msgpack, Pydantic |
| LLM | Ollama (CodeGemma, local) |
| Memory | SQLite FTS5 (Porter stemming, BM25 ranking) |
| Sandbox | Docker + gVisor (runsc), Maker-Checker pattern |
| Async | asyncio, aiosqlite, aiohttp |

## Features

- 🧠 **Persistent cross-session memory** — FTS5 full-text search over all past conversations
- ⚡ **Zero UI freezing** — LLM streaming runs on a ZMQ bridge thread, never touches Qt main thread
- 🔒 **Sandboxed code execution** — AI-generated code runs in Docker/gVisor with a Maker-Checker safety verifier
- 🛠️ **Tool calling** — Human-in-the-loop approval dialog before any tool executes
- 🗄️ **SparePartsPro integration** — Read-only SQL bridge to SparePartsPro ERP database
- 🔄 **Two-process design** — Router survives UI crash; UI reconnects automatically

## Quick Start

### Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com) running with `codegemma` pulled
- Docker Desktop (for sandbox execution)

### Install

```powershell
git clone https://github.com/9335668077gyani-byte/Ambrio.git
cd Ambrio
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Run

```powershell
# Start Ollama in background first
ollama serve

# Launch Ambrio (starts router + UI automatically)
.\ambrio.ps1
```

Or manually:
```powershell
# Terminal 1 — Cognitive Router
.venv\Scripts\python.exe router_service.py

# Terminal 2 — UI
.venv\Scripts\python.exe app.py
```

### Build sandbox image (optional — for code execution)

```powershell
docker build -f docker/sandbox.Dockerfile -t ambrio-sandbox:latest .
```

## Project Structure

```
Ambrio/
├── ambrio/
│   ├── ui/                     # PyQt6 Neumorphic interface
│   │   ├── ipc/                # ZMQ bridge + Pydantic message frames
│   │   ├── theme/              # QSS + color palette
│   │   ├── chat_widget.py      # Streaming token display
│   │   ├── input_bar.py        # Enter-to-send input
│   │   ├── sidebar.py          # Session management
│   │   └── main_window.py      # Root window + signal wiring
│   ├── router/                 # Cognitive Router microservice
│   │   ├── service.py          # ZMQ ROUTER asyncio loop
│   │   ├── ollama_client.py    # Async streaming /api/chat
│   │   ├── context_pruner.py   # FTS5 recall + sliding window
│   │   ├── session_manager.py  # Per-session state + memory
│   │   ├── tool_registry.py    # @tool decorator + RPC dispatch
│   │   └── tools/              # memory, sparepartspro, sandbox
│   └── sandbox/                # Docker/gVisor execution sandbox
│       ├── orchestrator.py     # Maker-Checker coordinator
│       ├── maker.py            # Worker: run code in container
│       ├── checker.py          # Grader: safety + correctness
│       └── policies/           # Resource limits + allowlist
├── db/schema.sql               # SQLite FTS5 schema + triggers
├── docker/sandbox.Dockerfile   # Minimal Python sandbox image
├── router_service.py           # Router process entry point
├── app.py                      # UI process entry point
├── ambrio.ps1                  # Dual-process launcher
└── tests/unit/                 # pytest-asyncio test suite
```

## Roadmap

- [x] Phase 1: Foundation — FTS5 memory, IPC protocol
- [x] Phase 2: Cognitive Router — Ollama streaming, tool RPC, context pruning
- [x] Phase 3: Neumorphic UI — ZMQ bridge, chat widget, session management
- [ ] Phase 4: Session summarization + self-improving memory loop
- [ ] Phase 5: Scheduled autonomous tasks (cron)
- [ ] Phase 6: Telegram/WhatsApp gateway

## License

MIT
