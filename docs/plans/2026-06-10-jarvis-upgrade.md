# Ambrio → Autonomous Multi-Agent System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Ambrio from a linear ZMQ/Ollama/FTS5 assistant into a self-correcting multi-agent Jarvis system with semantic memory, structured tool calling, multi-modal ingestion, and a Vue.js PWA.

**Architecture:** Five independent phases that layer on top of each other — each phase produces working software before the next begins. Phase 1–4 keep PyQt6 alive; Phase 5 migrates to Vue.js. No hard cutovers.

**Tech Stack:** LangGraph 0.2+, ChromaDB 0.5+ (embedded), sentence-transformers (all-MiniLM-L6-v2), MarkItDown, FastAPI + uvicorn, Vue 3 + Vite, Groq llama-3.3-70b (Planner/Critic), Gemini 2.5-flash (Vision), Ollama phi3-mini (local structured outputs).

---

## Architectural Decisions (No Compromises)

| Question | Decision | Why |
|---|---|---|
| Agent framework | **LangGraph** | Industry standard for cyclic state graphs. Manual asyncio = reinventing it poorly. |
| Vector DB | **ChromaDB embedded** | PersistentClient = one config line to switch to server. No extra process. |
| Planner LLM | **Groq llama-3.3-70b** | Free tier, 128K, best free planner. Local small models = poor decomposition. |
| Structured output model | **phi3-mini minimum** | llama3.2:1b structured output quality is unacceptable for production. |
| Vue migration | **Included — Phase 5** | Full Jarvis vision. No half measures. |

---

## New File Structure

```
ambrio/
├── agents/                         # NEW — Phase 1
│   ├── __init__.py
│   ├── graph.py                    # LangGraph state graph definition
│   ├── state.py                    # AgentState TypedDict
│   ├── nodes/
│   │   ├── planner.py              # Task decomposition node
│   │   ├── executor.py             # Tool execution node
│   │   ├── critic.py               # Output validation node
│   │   └── synthesizer.py          # Final answer assembly node
│   └── runner.py                   # Graph runner (replaces _stream_chat)
│
├── ingestion/                      # NEW — Phase 3
│   ├── __init__.py
│   ├── mime_guard.py               # MIME-type validator + video blocker
│   ├── doc_parser.py               # MarkItDown + PyMuPDF4LLM → Markdown
│   └── image_encoder.py            # Base64 pipeline for Gemini Vision
│
├── memory/                         # MODIFIED — Phase 4
│   ├── chroma_store.py             # NEW — ChromaDB vector store (replaces fts5_store primary)
│   ├── fts5_store.py               # KEEP — keyword fallback
│   ├── brain_store.py              # MODIFIED — vector-aware BrainStore
│   └── post_turn_worker.py         # NEW — async lesson extraction + commit
│
├── api/                            # NEW — Phase 5
│   ├── __init__.py
│   ├── server.py                   # FastAPI app + WebSocket endpoint
│   └── models.py                   # Pydantic request/response models
│
├── router/
│   ├── service.py                  # MODIFIED — delegates to agents.runner, regex DELETED
│   ├── context_pruner.py           # MODIFIED — ChromaDB primary recall
│   ├── session_manager.py          # MODIFIED — init chroma + post_turn_worker
│   └── ollama_client.py            # MODIFIED — response_format param added
│
└── ui/                             # DEPRECATED Phase 5 — kept working until then

frontend/                           # NEW — Phase 5
├── src/
│   ├── App.vue
│   ├── components/ChatWindow.vue
│   └── composables/useWebSocket.js
└── vite.config.js
```

---

## Phase 1 — LangGraph Multi-Agent Orchestration

> **Replaces:** `service.py → _stream_chat()` + entire `_TOOL_PATTERNS` + `_extract_text_tool_call()` (lines 20–163)
> **New dependency:** `pip install langgraph langchain-core`

---

### Task 1.1 — Install LangGraph & Define AgentState

**Files:**
- Create: `ambrio/agents/__init__.py`, `ambrio/agents/state.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependencies**

```
# requirements.txt — add these lines:
langgraph>=0.2.0
langchain-core>=0.2.0
```

```powershell
cd "C:\MY PROJECTS\Ambrio"
.venv\Scripts\pip install langgraph langchain-core
```
Expected: `Successfully installed langgraph-0.2.x`

- [ ] **Step 2: Write failing test**

```python
# tests/unit/test_agent_state.py
from ambrio.agents.state import AgentState

def test_state_has_required_fields():
    state = AgentState(
        session_id="test-session",
        user_input="hello",
        messages=[],
        subtasks=[],
        current_subtask=None,
        tool_results=[],
        critic_verdict=None,
        critic_feedback=None,
        attempt_count=0,
        final_answer=None,
        model_alias=None,
        elapsed=None,
    )
    assert state["session_id"] == "test-session"
    assert state["attempt_count"] == 0
    assert state["critic_verdict"] is None
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_agent_state.py -v
```
Expected: `FAIL — ModuleNotFoundError: ambrio.agents.state`

- [ ] **Step 3: Create `ambrio/agents/__init__.py`** (empty)

- [ ] **Step 4: Create `ambrio/agents/nodes/__init__.py`** (empty)

- [ ] **Step 5: Implement AgentState**

```python
# ambrio/agents/state.py
from typing import TypedDict, Optional, Any

class SubTask(TypedDict):
    description: str
    tool:        Optional[str]
    args:        Optional[dict]
    status:      str               # "pending" | "done" | "failed"
    result:      Optional[Any]

class AgentState(TypedDict):
    session_id:      str
    user_input:      str
    messages:        list[dict]
    subtasks:        list[SubTask]
    current_subtask: Optional[int]
    tool_results:    list[dict]
    critic_verdict:  Optional[str]   # "pass" | "fail" | "partial"
    critic_feedback: Optional[str]
    attempt_count:   int
    final_answer:    Optional[str]
    model_alias:     Optional[str]
    elapsed:         Optional[float]
```

- [ ] **Step 6: Run test — must PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_agent_state.py -v
```
Expected: `1 passed`

- [ ] **Step 7: Commit**

```bash
git add ambrio/agents/ tests/unit/test_agent_state.py requirements.txt
git commit -m "feat(agents): AgentState TypedDict + LangGraph dependency"
```

---

### Task 1.2 — Planner Node

**Files:**
- Create: `ambrio/agents/nodes/planner.py`
- Test: `tests/unit/test_planner_node.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_planner_node.py
import asyncio
from unittest.mock import AsyncMock, patch
from ambrio.agents.state import AgentState
from ambrio.agents.nodes.planner import planner_node

MOCK_SUBTASKS = [
    {"description": "search for Python", "tool": "web_search",
     "args": {"query": "Python"}, "status": "pending", "result": None},
    {"description": "summarize results", "tool": None,
     "args": None, "status": "pending", "result": None},
]

async def test_planner_produces_subtasks():
    state = AgentState(
        session_id="s1", user_input="search and summarize Python",
        messages=[], subtasks=[], current_subtask=None, tool_results=[],
        critic_verdict=None, critic_feedback=None, attempt_count=0,
        final_answer=None, model_alias=None, elapsed=None,
    )
    with patch("ambrio.agents.nodes.planner._call_planner_llm",
               new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_SUBTASKS
        result = await planner_node(state)
    assert len(result["subtasks"]) == 2
    assert result["current_subtask"] == 0
    assert result["subtasks"][0]["tool"] == "web_search"

asyncio.run(test_planner_produces_subtasks())  # local smoke
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_planner_node.py -v
```
Expected: `FAIL — ModuleNotFoundError`

- [ ] **Step 2: Implement Planner Node**

```python
# ambrio/agents/nodes/planner.py
import json, logging, re
from ambrio.agents.state import AgentState, SubTask

log = logging.getLogger(__name__)

_PLANNER_SYSTEM = """You are a task planner. Break the user request into ordered subtasks.
Return ONLY valid JSON — a list of subtask objects. No prose, no explanation.

Format: [{"description": str, "tool": str|null, "args": object|null, "status": "pending", "result": null}, ...]

Available tools: web_search, web_read, file_read, file_write, file_list, file_search,
doc_read, doc_save, doc_convert, doc_combine, img_ocr, img_passport, img_resize,
img_remove_bg, img_upscale, img_scan_doc, img_color_grade, img_background, img_rotate,
img_enhance, sparepartspro_query, sparepartspro_sql, memory_search.

Rules:
- Simple single request → ONE subtask (tool=null, answer from memory)
- Complex/multi-step → 2-4 subtasks maximum
- Never invent tool names outside the list above"""

async def _call_planner_llm(user_input: str) -> list[SubTask]:
    from ambrio.config import PROVIDER_KEYS
    from ambrio.router.model_router import ModelRouter
    router = ModelRouter(provider_keys=PROVIDER_KEYS)
    messages = [
        {"role": "system", "content": _PLANNER_SYSTEM},
        {"role": "user",   "content": user_input},
    ]
    full_text = ""
    async for chunk in router.stream(messages, task_type="reasoning"):
        if chunk.get("done"):
            break
        full_text += chunk.get("message", {}).get("content", "")

    json_match = re.search(r'\[.*?\]', full_text, re.DOTALL)
    if not json_match:
        # Fallback: single no-tool task
        return [{"description": user_input, "tool": None, "args": None,
                 "status": "pending", "result": None}]
    try:
        tasks = json.loads(json_match.group())
        for t in tasks:
            t.setdefault("status", "pending")
            t.setdefault("result", None)
        return tasks[:4]   # hard cap
    except json.JSONDecodeError:
        return [{"description": user_input, "tool": None, "args": None,
                 "status": "pending", "result": None}]

async def planner_node(state: AgentState) -> AgentState:
    log.info(f"[Planner] Planning: {state['user_input'][:80]}")
    subtasks = await _call_planner_llm(state["user_input"])
    log.info(f"[Planner] → {len(subtasks)} subtask(s)")
    return {**state, "subtasks": subtasks, "current_subtask": 0}
```

- [ ] **Step 3: Run test — must PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_planner_node.py -v
```
Expected: `1 passed`

- [ ] **Step 4: Commit**

```bash
git add ambrio/agents/nodes/planner.py tests/unit/test_planner_node.py
git commit -m "feat(agents): Planner node — Groq-powered task decomposition"
```

---

### Task 1.3 — Executor Node

**Files:**
- Create: `ambrio/agents/nodes/executor.py`
- Test: `tests/unit/test_executor_node.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_executor_node.py
import asyncio
from unittest.mock import AsyncMock, patch
from ambrio.agents.state import AgentState
from ambrio.agents.nodes.executor import executor_node

async def test_executor_calls_tool_marks_done():
    state = AgentState(
        session_id="s1", user_input="search X", messages=[],
        critic_verdict=None, critic_feedback=None, attempt_count=0,
        final_answer=None, model_alias=None, elapsed=None,
        subtasks=[{"description": "search X", "tool": "web_search",
                   "args": {"query": "X"}, "status": "pending", "result": None}],
        current_subtask=0,
        tool_results=[],
    )
    with patch("ambrio.agents.nodes.executor._dispatch_tool",
               new_callable=AsyncMock) as mock:
        mock.return_value = {"answer": "X is a framework"}
        result = await executor_node(state)
    assert result["subtasks"][0]["status"] == "done"
    assert result["subtasks"][0]["result"] == {"answer": "X is a framework"}
    assert len(result["tool_results"]) == 1

async def test_executor_marks_failed_on_exception():
    state = AgentState(
        session_id="s1", user_input="search X", messages=[],
        critic_verdict=None, critic_feedback=None, attempt_count=0,
        final_answer=None, model_alias=None, elapsed=None,
        subtasks=[{"description": "search X", "tool": "web_search",
                   "args": {"query": "X"}, "status": "pending", "result": None}],
        current_subtask=0,
        tool_results=[],
    )
    with patch("ambrio.agents.nodes.executor._dispatch_tool",
               new_callable=AsyncMock) as mock:
        mock.side_effect = TimeoutError("network timeout")
        result = await executor_node(state)
    assert result["subtasks"][0]["status"] == "failed"
    assert "timeout" in result["subtasks"][0]["result"]["error"]
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_executor_node.py -v
```
Expected: `FAIL — ModuleNotFoundError`

- [ ] **Step 2: Implement Executor Node**

```python
# ambrio/agents/nodes/executor.py
import asyncio, logging, time
from ambrio.agents.state import AgentState
from ambrio.router.tool_registry import ToolRegistry

log     = logging.getLogger(__name__)
_tools  = ToolRegistry()

async def _dispatch_tool(tool_name: str, tool_args: dict) -> dict:
    return await _tools.dispatch(tool_name, tool_args)

async def executor_node(state: AgentState) -> AgentState:
    idx      = state["current_subtask"]
    subtasks = list(state["subtasks"])
    results  = list(state["tool_results"])

    if idx is None or idx >= len(subtasks):
        return state

    task = dict(subtasks[idx])
    log.info(f"[Executor] [{idx}] {task['description']} | tool={task['tool']}")

    if task["tool"] is None:
        task["status"] = "done"
        task["result"] = {"answer": None}
    else:
        try:
            t0  = time.monotonic()
            res = await _dispatch_tool(task["tool"], task["args"] or {})
            task["status"] = "done"
            task["result"] = res
            results.append({"tool": task["tool"], "args": task["args"],
                             "result": res, "elapsed": round(time.monotonic()-t0, 2)})
        except Exception as e:
            log.error(f"[Executor] Tool {task['tool']} failed: {e}")
            task["status"] = "failed"
            task["result"] = {"error": str(e)}
            results.append({"tool": task["tool"], "error": str(e)})

    subtasks[idx] = task
    next_idx = next(
        (i for i, t in enumerate(subtasks) if t["status"] == "pending"), None)
    return {**state, "subtasks": subtasks,
            "current_subtask": next_idx, "tool_results": results}
```

- [ ] **Step 3: Run tests — must PASS (2 passed)**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_executor_node.py -v
```

- [ ] **Step 4: Commit**

```bash
git add ambrio/agents/nodes/executor.py tests/unit/test_executor_node.py
git commit -m "feat(agents): Executor node with tool dispatch + error marking"
```

---

### Task 1.4 — Critic Node (Maker-Checker Loop)

**Files:**
- Create: `ambrio/agents/nodes/critic.py`
- Test: `tests/unit/test_critic_node.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_critic_node.py
import asyncio
from unittest.mock import AsyncMock, patch
from ambrio.agents.state import AgentState
from ambrio.agents.nodes.critic import critic_node

def _make_state(tool_results, attempt=0):
    return AgentState(
        session_id="s1", user_input="search X", messages=[],
        current_subtask=None, final_answer=None, model_alias=None, elapsed=None,
        critic_feedback=None, attempt_count=attempt, critic_verdict=None,
        subtasks=[{"description": "search X", "tool": "web_search",
                   "args": {}, "status": "done" if not any(r.get("error") for r in tool_results) else "failed",
                   "result": tool_results[0] if tool_results else {}}],
        tool_results=tool_results,
    )

async def test_critic_passes_good_result():
    state = _make_state([{"tool": "web_search", "result": {"answer": "X is a framework"}}])
    with patch("ambrio.agents.nodes.critic._call_critic_llm", new_callable=AsyncMock) as m:
        m.return_value = ("pass", "")
        result = await critic_node(state)
    assert result["critic_verdict"] == "pass"
    assert result["attempt_count"] == 0   # unchanged on pass

async def test_critic_fails_and_increments_attempt():
    state = _make_state([{"tool": "web_search", "error": "timeout"}])
    with patch("ambrio.agents.nodes.critic._call_critic_llm", new_callable=AsyncMock) as m:
        m.return_value = ("fail", "retry with different query terms")
        result = await critic_node(state)
    assert result["critic_verdict"] == "fail"
    assert result["attempt_count"] == 1

async def test_critic_forces_pass_at_max_attempts():
    state = _make_state([{"tool": "web_search", "error": "timeout"}], attempt=3)
    with patch("ambrio.agents.nodes.critic._call_critic_llm", new_callable=AsyncMock) as m:
        result = await critic_node(state)
    assert result["critic_verdict"] == "pass"   # forced
    m.assert_not_called()                        # LLM not called when max reached
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_critic_node.py -v
```
Expected: `FAIL — ModuleNotFoundError`

- [ ] **Step 2: Implement Critic Node**

```python
# ambrio/agents/nodes/critic.py
import logging, re
from ambrio.agents.state import AgentState

log          = logging.getLogger(__name__)
MAX_ATTEMPTS = 3

_CRITIC_SYSTEM = """You are a strict QA critic for an AI agent.
Evaluate if the tool results sufficiently answer the user's request.
Respond EXACTLY in this format (no extra text):
VERDICT: pass
FEEDBACK:

Or if failed:
VERDICT: fail
FEEDBACK: specific retry instruction

Rules:
- "pass" = results contain useful data that answers the request
- "fail" = errors, empty results, or missed intent
- "partial" = some data but incomplete — treat as "fail"
- Be strict. Partial answers should be retried."""

async def _call_critic_llm(user_input: str, tool_results: list) -> tuple[str, str]:
    from ambrio.config import PROVIDER_KEYS
    from ambrio.router.model_router import ModelRouter
    router  = ModelRouter(provider_keys=PROVIDER_KEYS)
    summary = "\n".join(
        f"- {r.get('tool','?')}: {str(r.get('result', r.get('error','no result')))[:200]}"
        for r in tool_results
    )
    messages = [
        {"role": "system", "content": _CRITIC_SYSTEM},
        {"role": "user",   "content": f"Request: {user_input}\n\nTool Results:\n{summary}"},
    ]
    full = ""
    async for chunk in router.stream(messages, task_type="reasoning"):
        if chunk.get("done"): break
        full += chunk.get("message", {}).get("content", "")
    v = re.search(r'VERDICT:\s*(pass|fail|partial)', full, re.IGNORECASE)
    f = re.search(r'FEEDBACK:\s*(.*)',               full, re.IGNORECASE)
    return (v.group(1).lower() if v else "pass"), (f.group(1).strip() if f else "")

async def critic_node(state: AgentState) -> AgentState:
    if state["attempt_count"] >= MAX_ATTEMPTS:
        log.warning("[Critic] Max retries reached — forcing pass")
        return {**state, "critic_verdict": "pass", "critic_feedback": ""}

    verdict, feedback = await _call_critic_llm(state["user_input"], state["tool_results"])
    log.info(f"[Critic] verdict={verdict} attempt={state['attempt_count']+1}/{MAX_ATTEMPTS}")

    if verdict in ("fail", "partial"):
        # Reset failed subtasks to pending for retry
        subtasks = [
            {**t, "status": "pending", "result": None} if t["status"] == "failed" else t
            for t in state["subtasks"]
        ]
        retry_idx = next(
            (i for i, t in enumerate(subtasks) if t["status"] == "pending"), 0)
        return {**state, "critic_verdict": "fail", "critic_feedback": feedback,
                "subtasks": subtasks, "current_subtask": retry_idx,
                "attempt_count": state["attempt_count"] + 1}

    return {**state, "critic_verdict": "pass", "critic_feedback": ""}
```

- [ ] **Step 3: Run tests — must PASS (3 passed)**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_critic_node.py -v
```

- [ ] **Step 4: Commit**

```bash
git add ambrio/agents/nodes/critic.py tests/unit/test_critic_node.py
git commit -m "feat(agents): Critic node — Maker-Checker loop, max 3 retries"
```

---

### Task 1.5 — Synthesizer Node

**Files:**
- Create: `ambrio/agents/nodes/synthesizer.py`
- Test: `tests/unit/test_synthesizer_node.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_synthesizer_node.py
import asyncio
from unittest.mock import AsyncMock, patch
from ambrio.agents.state import AgentState
from ambrio.agents.nodes.synthesizer import synthesizer_node

async def test_synthesizer_builds_final_answer():
    state = AgentState(
        session_id="s1", user_input="search and summarize Python",
        messages=[], current_subtask=None, critic_verdict="pass",
        critic_feedback=None, attempt_count=0, model_alias=None, elapsed=None,
        subtasks=[{"description": "search", "tool": "web_search", "status": "done",
                   "args": {}, "result": {"answer": "Python is a language"}}],
        tool_results=[{"tool": "web_search", "result": {"answer": "Python is a language"}}],
        final_answer=None,
    )
    with patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock:
        mock.return_value = "Python is a high-level programming language."
        result = await synthesizer_node(state)
    assert result["final_answer"] == "Python is a high-level programming language."
    assert result["final_answer"] != ""
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_synthesizer_node.py -v
```
Expected: `FAIL`

- [ ] **Step 2: Implement Synthesizer Node**

```python
# ambrio/agents/nodes/synthesizer.py
import logging
from ambrio.agents.state import AgentState

log = logging.getLogger(__name__)

_SYNTH_SYSTEM = """Synthesize a clear, direct answer from the provided tool results.
- Bullet points for lists
- No filler phrases ("Great question!", "Certainly!", "Of course!")
- If tool results failed, explain what couldn't be done and why
- Match the language of the user's request"""

async def _call_synthesizer_llm(user_input: str, tool_results: list,
                                  messages: list) -> str:
    from ambrio.config import PROVIDER_KEYS
    from ambrio.router.model_router import ModelRouter
    router  = ModelRouter(provider_keys=PROVIDER_KEYS)
    context = "\n".join(
        f"[{r.get('tool','no-tool')}]: "
        f"{str(r.get('result', r.get('error', 'no result')))[:400]}"
        for r in tool_results
    )
    synth_messages = [
        {"role": "system", "content": _SYNTH_SYSTEM},
        *messages[-4:],
        {"role": "user",
         "content": f"Original request: {user_input}\n\nTool Results:\n{context}\n\nWrite final answer:"}
    ]
    answer = ""
    async for chunk in router.stream(synth_messages, task_type="chat"):
        if chunk.get("done"): break
        answer += chunk.get("message", {}).get("content", "")
    return answer.strip() or "I was unable to find a result for your request."

async def synthesizer_node(state: AgentState) -> AgentState:
    log.info("[Synthesizer] Building final answer")
    answer = await _call_synthesizer_llm(
        state["user_input"], state["tool_results"], state["messages"])
    return {**state, "final_answer": answer}
```

- [ ] **Step 3: Run test — must PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_synthesizer_node.py -v
```

- [ ] **Step 4: Commit**

```bash
git add ambrio/agents/nodes/synthesizer.py tests/unit/test_synthesizer_node.py
git commit -m "feat(agents): Synthesizer node — final answer assembly"
```

---

### Task 1.6 — Wire LangGraph + Delete Regex Block

**Files:**
- Create: `ambrio/agents/graph.py`, `ambrio/agents/runner.py`
- Modify: `ambrio/router/service.py`
- Test: `tests/unit/test_agent_graph.py`

- [ ] **Step 1: Write integration test**

```python
# tests/unit/test_agent_graph.py
import asyncio
from unittest.mock import AsyncMock, patch
from ambrio.agents.runner import run_agent

async def test_full_graph_simple_query():
    with patch("ambrio.agents.nodes.planner._call_planner_llm", new_callable=AsyncMock) as p, \
         patch("ambrio.agents.nodes.critic._call_critic_llm",  new_callable=AsyncMock) as c, \
         patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm", new_callable=AsyncMock) as s:
        p.return_value = [{"description": "answer",  "tool": None, "args": None,
                            "status": "pending", "result": None}]
        c.return_value = ("pass", "")
        s.return_value = "The answer is 42."
        tokens = []
        async for token in run_agent("test-s", "what is 6*7", [], None):
            tokens.append(token)
    full = "".join(tokens)
    assert "42" in full
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_agent_graph.py -v
```
Expected: `FAIL`

- [ ] **Step 2: Implement graph.py**

```python
# ambrio/agents/graph.py
from langgraph.graph import StateGraph, END
from ambrio.agents.state       import AgentState
from ambrio.agents.nodes.planner     import planner_node
from ambrio.agents.nodes.executor    import executor_node
from ambrio.agents.nodes.critic      import critic_node
from ambrio.agents.nodes.synthesizer import synthesizer_node

def _route_after_executor(state: AgentState) -> str:
    return "executor" if any(t["status"] == "pending" for t in state["subtasks"]) \
           else "critic"

def _route_after_critic(state: AgentState) -> str:
    return "synthesizer" if state["critic_verdict"] == "pass" else "executor"

def build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("planner",     planner_node)
    g.add_node("executor",    executor_node)
    g.add_node("critic",      critic_node)
    g.add_node("synthesizer", synthesizer_node)
    g.set_entry_point("planner")
    g.add_edge("planner", "executor")
    g.add_conditional_edges("executor", _route_after_executor,
                             {"executor": "executor", "critic": "critic"})
    g.add_conditional_edges("critic",   _route_after_critic,
                             {"synthesizer": "synthesizer", "executor": "executor"})
    g.add_edge("synthesizer", END)
    return g.compile()

GRAPH = build_graph()
```

- [ ] **Step 3: Implement runner.py**

```python
# ambrio/agents/runner.py
import asyncio
from typing import AsyncIterator
from ambrio.agents.graph import GRAPH
from ambrio.agents.state import AgentState

async def run_agent(session_id: str, user_input: str,
                    messages: list[dict],
                    tool_registry=None) -> AsyncIterator[str]:
    initial: AgentState = AgentState(
        session_id=session_id, user_input=user_input, messages=messages,
        subtasks=[], current_subtask=None, tool_results=[],
        critic_verdict=None, critic_feedback=None, attempt_count=0,
        final_answer=None, model_alias=None, elapsed=None,
    )
    final: AgentState = await GRAPH.ainvoke(initial)
    answer = final.get("final_answer") or ""
    words  = answer.split()
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        await asyncio.sleep(0.015)
```

- [ ] **Step 4: Replace `_stream_chat` in `service.py` — DELETE lines 20–163**

Open `ambrio/router/service.py`. Delete:
- The entire `_TOOL_PATTERNS` list (lines 20–135)
- The entire `_extract_text_tool_call` function (lines 138–163)
- The old `_stream_chat` body

Replace `_stream_chat` with:

```python
async def _stream_chat(self, identity: bytes, frame: Frame) -> None:
    import time
    session      = await self.sessions.get_or_create(frame.session_id)
    user_content = frame.payload.get("content", "")
    messages     = await session.build_context(user_content)
    t_start      = time.monotonic()
    full_answer  = ""
    token_count  = 0

    from ambrio.agents.runner import run_agent
    async for token in run_agent(frame.session_id, user_content, messages):
        token_count += 1
        full_answer += token
        await self._send(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_TOKEN,
            payload={"token": token}
        ))

    elapsed = round(time.monotonic() - t_start, 1)
    await session.persist_turn(user_content, full_answer)
    await self.sessions.post_turn_tick(
        frame.session_id, user_content, full_answer)
    await self._send(identity, Frame(
        session_id=frame.session_id,
        type=MsgType.CHAT_DONE,
        payload={"model": "multi-agent", "tokens": token_count, "elapsed": elapsed}
    ))
```

Also delete `_execute_tool_and_reply` and `_resume_after_tool` — they are no longer needed.

- [ ] **Step 5: Run full test suite + smoke test**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/ -v
.venv\Scripts\python.exe smoke_test_router.py
```
Expected: All passing; smoke test produces streamed response

- [ ] **Step 6: Commit**

```bash
git add ambrio/agents/graph.py ambrio/agents/runner.py ambrio/router/service.py
git commit -m "feat(agents): wire LangGraph cyclic graph, delete 143 lines of regex — Phase 1 DONE"
```

---

## Phase 2 — Native Structured Outputs

### Task 2.1 — Ollama JSON Schema Enforcement

**Files:**
- Modify: `ambrio/router/ollama_client.py`

- [ ] **Step 1: Update `stream()` to accept `response_format`**

Find the `payload` dict construction in `OllamaClient.stream()` and add:

```python
async def stream(self, messages: list[dict], tools=None,
                  response_format: dict | None = None):
    payload = {
        "model":    self.model,
        "messages": messages,
        "stream":   True,
        "options":  {"temperature": 0.1 if response_format else 0.7},
    }
    if tools:            payload["tools"]  = tools
    if response_format:  payload["format"] = response_format  # Ollama native JSON
    # rest of method unchanged
```

- [ ] **Step 2: Update ModelRouter.stream() to forward response_format**

In `model_router.py`, update `stream()` signature and `_stream_ollama()` call:

```python
async def stream(self, messages, tools=None, task_type=None,
                  response_format: dict | None = None) -> AsyncIterator[dict]:
    # ... existing routing logic ...
    async for chunk in self._dispatch(alias, model, messages, tools,
                                       response_format=response_format):
        yield chunk

async def _stream_ollama(self, messages, tools=None, response_format=None):
    from .ollama_client import OllamaClient
    async for chunk in OllamaClient().stream(messages, tools=tools,
                                              response_format=response_format):
        yield chunk

async def _dispatch(self, alias, model, messages, tools,
                     response_format=None):
    if model.provider == "ollama":
        async for c in self._stream_ollama(messages, tools, response_format):
            yield c
    # ... other providers unchanged
```

- [ ] **Step 3: Commit**

```bash
git add ambrio/router/ollama_client.py ambrio/router/model_router.py
git commit -m "feat(llm): response_format param through OllamaClient — JSON schema enforcement"
```

---

### Task 2.2 — Gemini Native Function Declarations

**Files:**
- Modify: `ambrio/router/model_router.py` → `_stream_gemini()`

- [ ] **Step 1: Add function declarations to Gemini body**

In `_stream_gemini()`, before `url` construction:

```python
if tools:
    body["tools"] = [{"function_declarations": [
        {
            "name":        t["function"]["name"],
            "description": t["function"].get("description", ""),
            "parameters":  t["function"].get("parameters", {}),
        }
        for t in tools
    ]}]
    body["tool_config"] = {"function_calling_config": {"mode": "AUTO"}}
```

In the response parsing loop, add functionCall detection before text parsing:

```python
for part in candidate.get("content", {}).get("parts", []):
    if "functionCall" in part:
        yield {"done": False, "message": {"tool_calls": [{
            "function": {
                "name":      part["functionCall"]["name"],
                "arguments": part["functionCall"].get("args", {}),
            }
        }]}}
        yield {"done": True}
        return
    if "text" in part and part["text"]:
        yield {"done": False, "message": {"content": part["text"]}}
```

- [ ] **Step 2: Commit**

```bash
git add ambrio/router/model_router.py
git commit -m "feat(llm): Gemini native function calling — structured tool dispatch"
```

---

## Phase 3 — Multi-Modal Ingestion Pipeline

### Task 3.1 — MIME Guard (Video Blocker)

**Files:**
- Create: `ambrio/ingestion/__init__.py` (empty), `ambrio/ingestion/mime_guard.py`
- Test: `tests/unit/test_mime_guard.py`

- [ ] **Step 1: Install dependency**

```powershell
.venv\Scripts\pip install python-magic-bin
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_mime_guard.py
import pytest
from ambrio.ingestion.mime_guard import validate_file, VideoFileError, FileTooLargeError

def test_blocks_mp4_by_extension(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"fake video data")
    with pytest.raises(VideoFileError):
        validate_file(str(f))

def test_blocks_mkv_by_extension(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"fake")
    with pytest.raises(VideoFileError):
        validate_file(str(f))

def test_allows_pdf(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4 fake content")
    # Should not raise
    result = validate_file(str(f))
    assert result is not None

def test_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        validate_file("C:/does/not/exist.pdf")
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_mime_guard.py -v
```
Expected: `FAIL`

- [ ] **Step 3: Implement mime_guard.py**

```python
# ambrio/ingestion/mime_guard.py
import os
from pathlib import Path

BLOCKED_EXTENSIONS  = {".mp4",".avi",".mkv",".mov",".wmv",".flv",
                        ".webm",".m4v",".3gp",".mpeg",".mpg",".ts",".vob"}
BLOCKED_MIME_PREFIX = "video/"
MAX_SIZE_MB         = 50

class VideoFileError(ValueError):  pass
class FileTooLargeError(ValueError): pass

def validate_file(path: str) -> str:
    """Validate file for processing. Returns MIME type string. Raises on blocked files."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    size_mb = os.path.getsize(path) / 1_048_576
    if size_mb > MAX_SIZE_MB:
        raise FileTooLargeError(f"File is {size_mb:.1f}MB — max is {MAX_SIZE_MB}MB")
    ext = Path(path).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        raise VideoFileError(f"Video files not supported: {ext}")
    try:
        import magic
        mime = magic.from_file(path, mime=True)
        if mime.startswith(BLOCKED_MIME_PREFIX):
            raise VideoFileError(f"Video MIME type blocked: {mime}")
        return mime
    except ImportError:
        # python-magic not available — extension check above was sufficient
        return "application/octet-stream"
```

- [ ] **Step 4: Run tests — must PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_mime_guard.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add ambrio/ingestion/ tests/unit/test_mime_guard.py
git commit -m "feat(ingestion): MIME guard — video blocking at entry point"
```

---

### Task 3.2 — Document Parser (MarkItDown → Markdown)

**Files:**
- Create: `ambrio/ingestion/doc_parser.py`
- Test: `tests/unit/test_doc_parser.py`

- [ ] **Step 1: Install**

```powershell
.venv\Scripts\pip install "markitdown[all]" PyMuPDF
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_doc_parser.py
import pytest
from ambrio.ingestion.doc_parser import parse_to_markdown

def test_parses_txt_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello World\nLine 2\nLine 3")
    result = parse_to_markdown(str(f))
    assert "Hello World" in result
    assert "Line 2" in result

def test_parses_csv_to_table(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("name,age,city\nAlice,30,Mumbai\nBob,25,Delhi")
    result = parse_to_markdown(str(f))
    assert "Alice" in result

def test_rejects_video_extension(tmp_path):
    f = tmp_path / "file.mp4"
    f.write_bytes(b"not a video")
    with pytest.raises(ValueError, match="Unsupported"):
        parse_to_markdown(str(f))

def test_respects_max_chars(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("A" * 100_000)
    result = parse_to_markdown(str(f), max_chars=1000)
    assert len(result) <= 1000
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_doc_parser.py -v
```
Expected: `FAIL`

- [ ] **Step 3: Implement doc_parser.py**

```python
# ambrio/ingestion/doc_parser.py
from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".pdf",".docx",".doc",".xlsx",".xls",
    ".csv",".txt",".md",".html",".htm",".pptx"
}

def parse_to_markdown(path: str, max_chars: int = 40_000) -> str:
    """Parse any supported document to clean Markdown string."""
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {ext}")

    # Primary: MarkItDown (handles docx, xlsx, pptx, csv, txt, html, md)
    try:
        from markitdown import MarkItDown
        result = MarkItDown().convert(path)
        if result.text_content.strip():
            return result.text_content.strip()[:max_chars]
    except Exception as e:
        if ext != ".pdf":
            raise RuntimeError(f"MarkItDown failed on {ext}: {e}") from e

    # PDF fallback: PyMuPDF (handles scanned + native PDFs)
    try:
        import fitz
        doc  = fitz.open(path)
        text = "\n\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text.strip()[:max_chars]
    except Exception as e2:
        raise RuntimeError(f"All PDF parsers exhausted: {e2}") from e2

    raise RuntimeError(f"Could not extract text from {path}")
```

- [ ] **Step 4: Run tests — must PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_doc_parser.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add ambrio/ingestion/doc_parser.py tests/unit/test_doc_parser.py
git commit -m "feat(ingestion): MarkItDown + PyMuPDF4LLM doc parser — Markdown output"
```

---

### Task 3.3 — Gemini Vision Base64 Encoder

**Files:**
- Create: `ambrio/ingestion/image_encoder.py`
- Test: `tests/unit/test_image_encoder.py`

- [ ] **Step 1: Install Pillow (if not present)**

```powershell
.venv\Scripts\pip install Pillow
```

- [ ] **Step 2: Write failing test**

```python
# tests/unit/test_image_encoder.py
import os, struct, zlib, pytest
from ambrio.ingestion.image_encoder import encode_image_for_gemini, build_vision_message

def _make_valid_png(path):
    """Write a 1x1 white PNG."""
    def chunk(name, data):
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    sig  = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff'))
    iend = chunk(b'IEND', b'')
    path.write_bytes(sig + ihdr + idat + iend)

def test_encode_returns_b64_and_mime(tmp_path):
    f = tmp_path / "img.png"
    _make_valid_png(f)
    b64, mime = encode_image_for_gemini(str(f))
    import base64
    assert base64.b64decode(b64) == f.read_bytes()
    assert mime == "image/png"

def test_rejects_unsupported_format(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"random bytes")
    with pytest.raises(ValueError, match="Unsupported image"):
        encode_image_for_gemini(str(f))

def test_build_vision_message_structure(tmp_path):
    f = tmp_path / "photo.png"
    _make_valid_png(f)
    msg = build_vision_message("Describe this image", str(f))
    assert msg["role"] == "user"
    part_types = [list(p.keys())[0] for p in msg["parts"]]
    assert "text" in part_types
    assert "inline_data" in part_types
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_image_encoder.py -v
```
Expected: `FAIL`

- [ ] **Step 3: Implement image_encoder.py**

```python
# ambrio/ingestion/image_encoder.py
import base64, mimetypes, os
from pathlib import Path

SUPPORTED_IMAGE_EXTENSIONS = {".jpg",".jpeg",".png",".gif",".webp",".bmp"}
MAX_IMAGE_BYTES = 4 * 1024 * 1024   # 4MB — Gemini inline limit

def encode_image_for_gemini(path: str) -> tuple[str, str]:
    """Returns (base64_string, mime_type). Resizes if over 4MB."""
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {ext}")
    if os.path.getsize(path) > MAX_IMAGE_BYTES:
        _resize_to_fit(path, path, MAX_IMAGE_BYTES)
    with open(path, "rb") as f:
        raw = f.read()
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    return base64.b64encode(raw).decode("utf-8"), mime

def _resize_to_fit(src: str, dst: str, max_bytes: int) -> None:
    try:
        from PIL import Image
        img = Image.open(src)
        img.thumbnail((1568, 1568), Image.LANCZOS)
        img.save(dst, optimize=True)
    except ImportError:
        pass  # Pillow not installed — skip resize, Gemini will reject if too large

def build_vision_message(text: str, image_path: str) -> dict:
    """Build a Gemini-compatible multipart message with text + image."""
    b64, mime = encode_image_for_gemini(image_path)
    return {
        "role":  "user",
        "parts": [
            {"text": text},
            {"inline_data": {"mime_type": mime, "data": b64}}
        ]
    }
```

- [ ] **Step 4: Run tests — must PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_image_encoder.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add ambrio/ingestion/image_encoder.py tests/unit/test_image_encoder.py
git commit -m "feat(ingestion): Gemini Vision base64 encoder — Phase 3 DONE"
```

---

## Phase 4 — Vector Memory (ChromaDB + all-MiniLM-L6-v2)

### Task 4.1 — ChromaDB Vector Store

**Files:**
- Create: `ambrio/memory/chroma_store.py`
- Test: `tests/unit/test_chroma_store.py`

- [ ] **Step 1: Install**

```powershell
.venv\Scripts\pip install chromadb "sentence-transformers>=2.7"
# First run downloads all-MiniLM-L6-v2 (~22MB) — takes ~30s
.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); print('OK')"
```
Expected: `OK`

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_chroma_store.py
import asyncio, pytest
from ambrio.memory.chroma_store import ChromaStore

async def test_semantic_recall_finds_similar():
    store = ChromaStore(persist_dir=":memory:")
    await store.init()
    await store.insert("s1", "user",      "brake pad replacement discussed", "m1")
    await store.insert("s1", "assistant", "brake pads available in rack A3",  "m2")
    results = await store.search("s1", "brakes", limit=5)
    assert len(results) > 0
    assert any("brake" in r["content"].lower() for r in results)

async def test_no_cross_session_leak():
    store = ChromaStore(persist_dir=":memory:")
    await store.init()
    await store.insert("session-A", "user", "confidential data", "a1")
    results = await store.search("session-B", "confidential data", limit=5)
    assert len(results) == 0

async def test_search_returns_scores():
    store = ChromaStore(persist_dir=":memory:")
    await store.init()
    await store.insert("s1", "user", "Python programming language", "p1")
    results = await store.search("s1", "Python", limit=3)
    assert all("score" in r for r in results)
    assert all(0.0 <= r["score"] <= 1.0 for r in results)
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_chroma_store.py -v
```
Expected: `FAIL — ModuleNotFoundError`

- [ ] **Step 3: Implement ChromaStore**

```python
# ambrio/memory/chroma_store.py
import asyncio, logging
log = logging.getLogger(__name__)

class ChromaStore:
    """
    ChromaDB-backed semantic memory store.
    Uses all-MiniLM-L6-v2 for local embeddings (22MB, CPU-friendly).
    persist_dir=":memory:" → ephemeral (tests).
    persist_dir="./ambrio_chroma" → persistent on disk.
    """
    def __init__(self, persist_dir: str = "./ambrio_chroma"):
        self.persist_dir  = persist_dir
        self._collection  = None
        self._embedder    = None

    async def init(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_init)
        log.info(f"ChromaStore initialized at '{self.persist_dir}'")

    def _sync_init(self):
        import chromadb
        from sentence_transformers import SentenceTransformer
        if self.persist_dir == ":memory:":
            client = chromadb.EphemeralClient()
        else:
            client = chromadb.PersistentClient(path=self.persist_dir)
        self._collection = client.get_or_create_collection(
            name="ambrio_messages",
            metadata={"hnsw:space": "cosine"}
        )
        self._embedder = SentenceTransformer("all-MiniLM-L6-v2")

    def _embed(self, text: str) -> list[float]:
        return self._embedder.encode(
            text, normalize_embeddings=True, show_progress_bar=False
        ).tolist()

    async def insert(self, session_id: str, role: str,
                     content: str, message_id: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._sync_upsert, session_id, role, content, message_id)

    def _sync_upsert(self, session_id, role, content, message_id):
        self._collection.upsert(
            ids=[message_id],
            embeddings=[self._embed(content)],
            documents=[content],
            metadatas=[{"session_id": session_id, "role": role}]
        )

    async def search(self, session_id: str, query: str,
                     limit: int = 10) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._sync_search, session_id, query, limit)

    def _sync_search(self, session_id, query, limit) -> list[dict]:
        results = self._collection.query(
            query_embeddings=[self._embed(query)],
            n_results=limit,
            where={"session_id": session_id},
            include=["documents","metadatas","distances"]
        )
        docs    = results["documents"][0]
        metas   = results["metadatas"][0]
        dists   = results["distances"][0]
        return [
            {"content": doc, "role": meta["role"],
             "score": round(1.0 - dist, 4)}
            for doc, meta, dist in zip(docs, metas, dists)
        ]
```

- [ ] **Step 4: Run tests — must PASS (3 passed)**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_chroma_store.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ambrio/memory/chroma_store.py tests/unit/test_chroma_store.py
git commit -m "feat(memory): ChromaDB semantic vector store — all-MiniLM-L6-v2 local embeddings"
```

---

### Task 4.2 — Post-Turn Async Worker (Lesson Extraction)

**Files:**
- Create: `ambrio/memory/post_turn_worker.py`
- Modify: `ambrio/router/session_manager.py`
- Test: `tests/unit/test_post_turn_worker.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_post_turn_worker.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from ambrio.memory.post_turn_worker import PostTurnWorker

async def test_worker_extracts_and_commits_lessons():
    brain  = MagicMock(); brain.save_lesson  = AsyncMock()
    chroma = MagicMock(); chroma.insert      = AsyncMock()
    worker = PostTurnWorker(brain=brain, chroma=chroma)
    with patch("ambrio.memory.post_turn_worker._extract_lessons",
               new_callable=AsyncMock) as ex:
        ex.return_value = ["user prefers bullet points", "shop name is N.A. MOTORS"]
        await worker.process_turn("s1", "give a list", "• item1\n• item2")
    assert brain.save_lesson.call_count == 2
    assert chroma.insert.call_count == 2

async def test_worker_silent_on_empty_lessons():
    brain  = MagicMock(); brain.save_lesson  = AsyncMock()
    chroma = MagicMock(); chroma.insert      = AsyncMock()
    worker = PostTurnWorker(brain=brain, chroma=chroma)
    with patch("ambrio.memory.post_turn_worker._extract_lessons",
               new_callable=AsyncMock) as ex:
        ex.return_value = []
        await worker.process_turn("s1", "hi", "hello!")
    brain.save_lesson.assert_not_called()
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_post_turn_worker.py -v
```
Expected: `FAIL`

- [ ] **Step 2: Implement PostTurnWorker**

```python
# ambrio/memory/post_turn_worker.py
import asyncio, json, logging, re, uuid
log = logging.getLogger(__name__)

_LESSON_SYSTEM = """Extract durable learnable facts from this conversation turn.
Return ONLY a JSON array of strings. Return [] if nothing worth remembering.
Types to extract:
- User preferences ("user prefers bullet points")
- Persistent facts ("shop name is N.A. MOTORS, Bangalore")
- Tool failures ("doc_save fails on OneDrive paths")
- Learned patterns ("user often asks about brake pads")
Keep each fact under 100 chars. Max 3 facts per turn."""

async def _extract_lessons(user_input: str, assistant_output: str) -> list[str]:
    from ambrio.config import PROVIDER_KEYS
    from ambrio.router.model_router import ModelRouter
    router = ModelRouter(provider_keys=PROVIDER_KEYS)
    messages = [
        {"role": "system", "content": _LESSON_SYSTEM},
        {"role": "user",
         "content": f"User: {user_input[:300]}\nAssistant: {assistant_output[:500]}"},
    ]
    full = ""
    async for chunk in router.stream(messages, task_type="fast"):
        if chunk.get("done"): break
        full += chunk.get("message", {}).get("content", "")
    m = re.search(r'\[.*?\]', full, re.DOTALL)
    if not m: return []
    try:
        lessons = json.loads(m.group())
        return [l for l in lessons if isinstance(l, str) and l.strip()][:3]
    except json.JSONDecodeError:
        return []

class PostTurnWorker:
    def __init__(self, brain, chroma):
        self.brain  = brain
        self.chroma = chroma

    async def process_turn(self, session_id: str,
                             user_input: str, assistant_output: str) -> None:
        try:
            lessons = await _extract_lessons(user_input, assistant_output)
            for lesson in lessons:
                await self.brain.save_lesson(lesson)
                await self.chroma.insert(
                    "__global__", "lesson", lesson, str(uuid.uuid4()))
            if lessons:
                log.info(f"[PostTurn] Committed {len(lessons)} lesson(s)")
        except Exception as e:
            log.error(f"[PostTurn] Worker error (non-fatal): {e}")
```

- [ ] **Step 3: Wire into SessionManager**

In `ambrio/router/session_manager.py`, update `init()` and `post_turn_tick()`:

```python
async def init(self, db_path: str = "ambrio.db") -> None:
    # ... existing code ...
    from ambrio.memory.chroma_store    import ChromaStore
    from ambrio.memory.post_turn_worker import PostTurnWorker
    self._chroma = ChromaStore(persist_dir="./ambrio_chroma")
    await self._chroma.init()
    self._post_turn_worker = PostTurnWorker(brain=self._brain, chroma=self._chroma)
    log.info("ChromaStore + PostTurnWorker initialized")

async def post_turn_tick(self, session_id: str,
                          user_input: str = "",
                          assistant_output: str = "") -> None:
    if self._loop:
        await self._loop.tick(session_id)
    if user_input and hasattr(self, '_post_turn_worker'):
        asyncio.create_task(
            self._post_turn_worker.process_turn(
                session_id, user_input, assistant_output)
        )
```

- [ ] **Step 4: Run tests — must PASS**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_post_turn_worker.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add ambrio/memory/post_turn_worker.py ambrio/router/session_manager.py tests/unit/test_post_turn_worker.py
git commit -m "feat(memory): PostTurnWorker lesson extraction + async BrainStore/Chroma commit"
```

---

### Task 4.3 — Update ContextPruner — ChromaDB Primary Recall

**Files:**
- Modify: `ambrio/router/context_pruner.py`
- Modify: `ambrio/router/session_manager.py` (pass chroma to ContextPruner)

- [ ] **Step 1: Update ContextPruner constructor and `_recall()`**

```python
# ambrio/router/context_pruner.py — update class:
class ContextPruner:
    def __init__(self, chroma, fts5, session_id: str, brain=None):
        self.chroma     = chroma   # PRIMARY — semantic
        self.fts5       = fts5     # SECONDARY — keyword fallback
        self.session_id = session_id
        self.brain      = brain

    async def _recall(self, query: str, exclude: list[dict]) -> list[dict]:
        exclude_set = {m["content"] for m in exclude}

        # Primary: ChromaDB semantic search
        chroma_raw = await self.chroma.search(self.session_id, query, limit=8)
        chroma_msgs = [{"role": r["role"], "content": r["content"]}
                       for r in chroma_raw if r["content"] not in exclude_set]

        # Secondary: FTS5 keyword search (catches exact terms ChromaDB might miss)
        fts5_raw  = await self.fts5.search(self.session_id, query, limit=5)
        seen      = {m["content"] for m in chroma_msgs}
        fts5_msgs = [{"role": r["role"], "content": r["content"]}
                     for r in fts5_raw
                     if r["content"] not in exclude_set and r["content"] not in seen]

        return (chroma_msgs + fts5_msgs)[:10]
```

- [ ] **Step 2: Update Session construction in session_manager.py**

```python
# In SessionManager.get_or_create(), update Session construction:
self._sessions[session_id] = Session(
    session_id, self._db, self._brain,
    self._model_router if self._model_router else self._ollama,
    chroma=self._chroma   # NEW
)
```

```python
# In Session.__init__():
def __init__(self, session_id, db, brain, ollama, chroma=None):
    self.pruner = ContextPruner(
        chroma=chroma,
        fts5=FTS5Store(db),
        session_id=session_id,
        brain=brain
    )
```

- [ ] **Step 3: Commit**

```bash
git add ambrio/router/context_pruner.py ambrio/router/session_manager.py
git commit -m "feat(memory): ChromaDB primary recall in ContextPruner — FTS5 keyword fallback — Phase 4 DONE"
```

---

## Phase 5 — Headless FastAPI + Vue.js PWA

### Task 5.1 — FastAPI WebSocket Server

**Files:**
- Create: `ambrio/api/__init__.py` (empty), `ambrio/api/models.py`, `ambrio/api/server.py`

- [ ] **Step 1: Install**

```powershell
.venv\Scripts\pip install "fastapi>=0.111" "uvicorn[standard]" websockets
```

- [ ] **Step 2: Implement models.py**

```python
# ambrio/api/models.py
from pydantic import BaseModel
from typing  import Optional

class ChatRequest(BaseModel):
    content: str
    session_id: Optional[str] = None

class ChatToken(BaseModel):
    type:  str = "token"
    data:  str

class ChatDone(BaseModel):
    type:    str = "done"
    model:   str
    tokens:  int
    elapsed: float
    tool:    Optional[str] = None

class ErrorMsg(BaseModel):
    type:    str = "error"
    message: str
```

- [ ] **Step 3: Implement server.py**

```python
# ambrio/api/server.py
import asyncio, time, logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from ambrio.api.models import ChatDone, ErrorMsg

log = logging.getLogger(__name__)
app = FastAPI(title="Ambrio", version="4.0.0")

_session_manager = None

@app.on_event("startup")
async def _startup():
    global _session_manager
    from ambrio.router.session_manager import SessionManager
    from ambrio.router.model_router    import ModelRouter
    from ambrio.config                 import PROVIDER_KEYS
    import ambrio.router.tools.memory_tool
    import ambrio.router.tools.sparepartspro_tool
    import ambrio.router.tools.file_tool
    import ambrio.router.tools.doc_tool
    import ambrio.router.tools.web_tool
    import ambrio.router.tools.img_tool
    import ambrio.router.tools.convert_tool
    _session_manager = SessionManager()
    await _session_manager.init("ambrio.db")
    _session_manager.set_model_router(ModelRouter(provider_keys=PROVIDER_KEYS))
    log.info("Ambrio FastAPI online — ws://localhost:8765/chat/{session_id}")

@app.websocket("/chat/{session_id}")
async def chat_ws(ws: WebSocket, session_id: str):
    await ws.accept()
    log.info(f"WS connected: {session_id}")
    try:
        while True:
            data = await ws.receive_json()
            user_content = data.get("content", "").strip()
            if not user_content:
                continue
            session  = await _session_manager.get_or_create(session_id)
            messages = await session.build_context(user_content)
            t_start  = time.monotonic()
            answer   = ""
            tokens   = 0
            from ambrio.agents.runner import run_agent
            async for token in run_agent(session_id, user_content, messages):
                await ws.send_json({"type": "token", "data": token})
                answer += token
                tokens += 1
            elapsed = round(time.monotonic() - t_start, 1)
            await session.persist_turn(user_content, answer)
            await _session_manager.post_turn_tick(session_id, user_content, answer)
            await ws.send_json(
                ChatDone(model="multi-agent", tokens=tokens, elapsed=elapsed).model_dump()
            )
    except WebSocketDisconnect:
        log.info(f"WS disconnected: {session_id}")
    except Exception as e:
        log.exception(f"WS error: {session_id}")
        try:
            await ws.send_json(ErrorMsg(message=str(e)).model_dump())
        except Exception:
            pass

@app.get("/health")
async def health():
    return {"status": "ok", "version": "4.0.0"}

@app.get("/sessions")
async def list_sessions():
    if not _session_manager:
        return []
    return list(_session_manager._sessions.keys())
```

- [ ] **Step 4: Smoke test**

```powershell
# Terminal 1
.venv\Scripts\python.exe -m uvicorn ambrio.api.server:app --port 8765 --reload

# Terminal 2 — WebSocket smoke test
.venv\Scripts\python.exe -c "
import asyncio, websockets, json
async def t():
    async with websockets.connect('ws://localhost:8765/chat/smoke-test') as ws:
        await ws.send(json.dumps({'content': 'what is 2+2?'}))
        while True:
            m = json.loads(await ws.recv())
            print(m.get('data','') if m['type']=='token' else m, end='', flush=True)
            if m['type'] == 'done': print(); break
asyncio.run(t())"
```
Expected: Streamed answer then done metadata

- [ ] **Step 5: Commit**

```bash
git add ambrio/api/ && git commit -m "feat(api): FastAPI WebSocket server on :8765 — headless mode"
```

---

### Task 5.2 — Vue.js PWA Frontend

**Files:**
- Create: `frontend/` (scaffolded via Vite)

- [ ] **Step 1: Scaffold**

```powershell
cd "C:\MY PROJECTS\Ambrio"
npx create-vite@latest frontend -- --template vue
cd frontend
npm install
npm install marked vite-plugin-pwa
```

- [ ] **Step 2: Create WebSocket composable**

```javascript
// frontend/src/composables/useWebSocket.js
import { ref } from 'vue'

export function useWebSocket(sessionId) {
    const messages  = ref([])
    const isLoading = ref(false)
    const statusMsg = ref('')
    let   ws        = null

    function connect() {
        ws = new WebSocket(`ws://localhost:8765/chat/${sessionId}`)
        ws.onopen = () => { statusMsg.value = 'Connected' }
        ws.onclose = () => { statusMsg.value = 'Disconnected'; ws = null }
        ws.onerror = () => { statusMsg.value = 'Connection error' }
        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data)
            if (msg.type === 'token') {
                messages.value.at(-1).content += msg.data
            } else if (msg.type === 'done') {
                messages.value.at(-1).meta = {
                    model: msg.model, tokens: msg.tokens, elapsed: msg.elapsed
                }
                isLoading.value = false
            } else if (msg.type === 'error') {
                messages.value.push({ role: 'error', content: msg.message })
                isLoading.value = false
            }
        }
    }

    function send(content) {
        if (!ws || ws.readyState !== WebSocket.OPEN) connect()
        messages.value.push({ role: 'user',      content })
        messages.value.push({ role: 'assistant', content: '', meta: null })
        isLoading.value = true
        // Wait for connection if just opened
        const _send = () => ws.send(JSON.stringify({ content }))
        if (ws.readyState === WebSocket.OPEN) _send()
        else ws.addEventListener('open', _send, { once: true })
    }

    connect()
    return { messages, isLoading, statusMsg, send }
}
```

- [ ] **Step 3: Update vite.config.js**

```javascript
// frontend/vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
    plugins: [
        vue(),
        VitePWA({
            registerType: 'autoUpdate',
            manifest: {
                name:        'Ambrio',
                short_name:  'Ambrio',
                description: '100% local autonomous AI agent',
                theme_color: '#0a0a0f',
                background_color: '#0a0a0f',
                display:     'standalone',
                icons: [{ src: '/icon-192.png', sizes: '192x192', type: 'image/png' }]
            }
        })
    ],
    server: { port: 5173 }
})
```

- [ ] **Step 4: Verify dev server**

```powershell
cd "C:\MY PROJECTS\Ambrio\frontend"
npm run dev
```
Expected: `VITE ready on http://localhost:5173`

- [ ] **Step 5: Commit**

```bash
cd "C:\MY PROJECTS\Ambrio"
git add frontend/
git commit -m "feat(ui): Vue 3 Vite PWA frontend — WebSocket client — Phase 5 DONE"
```

---

## Database Migration

Run once before Phase 4:

```powershell
# C:\MY PROJECTS\Ambrio
.venv\Scripts\python.exe -c "
import sqlite3, sys
conn = sqlite3.connect('ambrio.db')
conn.executescript('''
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS vector_memories (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    session_id  TEXT NOT NULL,
    content     TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK(kind IN (''turn'',''lesson'',''fact'',''failure'')),
    chroma_id   TEXT,
    ts          INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_vmem_session ON vector_memories(session_id, ts DESC);

CREATE TABLE IF NOT EXISTS brain_lessons (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    content     TEXT UNIQUE NOT NULL,
    confidence  REAL DEFAULT 1.0,
    created_at  INTEGER DEFAULT (unixepoch()),
    last_used   INTEGER DEFAULT (unixepoch()),
    use_count   INTEGER DEFAULT 0
);
''')
conn.commit(); conn.close()
print('Migration complete')
"
```

---

## Full Dependency Install (One Shot)

```powershell
cd "C:\MY PROJECTS\Ambrio"
.venv\Scripts\pip install langgraph langchain-core chromadb "sentence-transformers>=2.7" `
    "markitdown[all]" PyMuPDF python-magic-bin `
    "fastapi>=0.111" "uvicorn[standard]" websockets Pillow

# Pull phi3-mini for local structured outputs (Ollama must be running)
ollama pull phi3:mini
```

---

## Run Commands After All Phases Complete

```powershell
# Option A: Headless + Vue (Phase 5 complete)
# Terminal 1 — Backend
.venv\Scripts\python.exe -m uvicorn ambrio.api.server:app --port 8765

# Terminal 2 — Frontend
cd frontend && npm run dev

# Option B: Legacy ZMQ + PyQt6 (until Phase 5)
.\ambrio.ps1
```
