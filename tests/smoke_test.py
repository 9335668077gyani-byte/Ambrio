# tests/smoke_test.py
"""
Ambrio Phase 4 -- End-to-End Smoke Test
Tests: Ollama connectivity, FTS5 memory, ZMQ IPC, streaming, session persist.

Run with:
    .venv\\Scripts\\python.exe tests/smoke_test.py

Prerequisites:
    - Ollama running (ollama serve)
    - At least one model installed (ollama list)
"""
import asyncio, sys, tempfile, os, uuid, time
# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore

PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"
INFO = "\033[94mℹ \033[0m"

results: list[tuple[str, bool, str]] = []

def report(name: str, ok: bool, detail: str = ""):
    icon = PASS if ok else FAIL
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok, detail))


# ── Test 1: Ollama connectivity ────────────────────────────────────────────────
async def test_ollama_connectivity():
    print("\n[1] Ollama Connectivity")
    from ambrio.router.ollama_client import OllamaClient
    client = OllamaClient()
    try:
        models = await client.list_models()
        report("Ollama API reachable", True, f"models: {models}")
        model = await client._resolve_model()
        report("Model auto-detected", True, f"selected: {model}")
        return True
    except Exception as e:
        report("Ollama API reachable", False, str(e))
        print(f"\n  {INFO} Start Ollama with: ollama serve")
        return False


# ── Test 2: FTS5 Memory ────────────────────────────────────────────────────────
async def test_fts5_memory():
    print("\n[2] FTS5 Memory Store")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        dbpath = f.name
    try:
        from ambrio.router.memory.db import Database
        from ambrio.router.memory.fts5_store import FTS5Store
        db    = Database(dbpath)
        await db.init()
        store = FTS5Store(db)
        sid   = str(uuid.uuid4())
        async with db.conn() as c:
            await c.execute("INSERT INTO sessions(id,title) VALUES(?,?)", (sid, "smoke"))
            await c.commit()

        await store.insert(sid, "user",      "invoice for spare parts March 2026", str(uuid.uuid4()))
        await store.insert(sid, "assistant", "here are the March invoices", str(uuid.uuid4()))

        results_fts = await store.search(sid, "invoice", limit=5)
        report("Insert + FTS5 search", len(results_fts) == 2, f"{len(results_fts)} rows found")

        cross = await store.search_cross_session("March", limit=5)
        report("Cross-session search", len(cross) >= 1, f"{len(cross)} rows found")
    except Exception as e:
        report("FTS5 memory", False, str(e))
    finally:
        os.unlink(dbpath)


# ── Test 3: Context Pruner ─────────────────────────────────────────────────────
async def test_context_pruner():
    print("\n[3] Context Pruner")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        dbpath = f.name
    try:
        from ambrio.router.memory.db import Database
        from ambrio.router.memory.fts5_store import FTS5Store
        from ambrio.router.context_pruner import ContextPruner, CONTEXT_BUDGET

        db    = Database(dbpath)
        await db.init()
        store = FTS5Store(db)
        sid   = str(uuid.uuid4())
        async with db.conn() as c:
            await c.execute("INSERT INTO sessions(id,title) VALUES(?,?)", (sid, "smoke"))
            await c.commit()

        pruner  = ContextPruner(store, sid)
        history = [{"role": "user", "content": f"msg {i} " * 80} for i in range(30)]
        context = await pruner.build("new question", history)

        has_system  = context[0]["role"] == "system"
        has_user    = context[-1]["content"] == "new question"
        total_chars = sum(len(m["content"]) for m in context)
        within_budget = total_chars < CONTEXT_BUDGET * 8  # ~8 chars/token rough

        report("System prompt present",    has_system)
        report("New user message at end",  has_user)
        report("Context within budget",    within_budget, f"~{total_chars // 4} tokens est.")
    except Exception as e:
        report("Context pruner", False, str(e))
    finally:
        os.unlink(dbpath)


# ── Test 4: Tool Registry ──────────────────────────────────────────────────────
async def test_tool_registry():
    print("\n[4] Tool Registry + Dispatch")
    try:
        from ambrio.router.tool_registry import tool, ToolRegistry, _REGISTRY

        @tool()
        async def _smoke_add(a: str, b: str) -> dict:
            """Add two numbers (smoke test tool)."""
            return {"result": int(a) + int(b)}

        reg    = ToolRegistry()
        result = await reg.dispatch("_smoke_add", {"a": "10", "b": "32"})
        report("Tool dispatch", result["result"] == 42, f"result={result['result']}")

        schema = reg.schema()
        names  = [s["function"]["name"] for s in schema]
        report("Schema export", "_smoke_add" in names, f"{len(schema)} tools registered")

        try:
            await reg.dispatch("nonexistent", {})
            report("Unknown tool raises", False, "should have raised")
        except KeyError:
            report("Unknown tool raises KeyError", True)
    except Exception as e:
        report("Tool registry", False, str(e))


# ── Test 5: Ollama streaming (real LLM call) ────────────────────────────────────
async def test_ollama_streaming():
    print("\n[5] Ollama Live Streaming")
    from ambrio.router.ollama_client import OllamaClient
    client = OllamaClient()
    try:
        model  = await client._resolve_model()
        tokens = []
        t0     = time.monotonic()
        async for chunk in client.stream([
            {"role": "system",  "content": "You are Ambrio. Respond very briefly."},
            {"role": "user",    "content": "Say exactly: AMBRIO_OK"}
        ]):
            if chunk.get("done"):
                break
            token = chunk.get("message", {}).get("content", "")
            if token:
                tokens.append(token)
                sys.stdout.write(token)
                sys.stdout.flush()

        elapsed = time.monotonic() - t0
        full    = "".join(tokens).strip()
        print()  # newline after streaming

        report("Streaming produces tokens", len(tokens) > 0, f"{len(tokens)} tokens in {elapsed:.1f}s")
        report("Response contains expected text", "AMBRIO" in full.upper(), repr(full[:60]))
    except Exception as e:
        report("Ollama streaming", False, str(e))


# ── Test 6: SessionManager + persist ─────────────────────────────────────────
async def test_session_manager():
    print("\n[6] Session Manager + Persistence")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        dbpath = f.name
    try:
        from ambrio.router.session_manager import SessionManager
        mgr = SessionManager()
        await mgr.init(dbpath)

        sid     = str(uuid.uuid4())
        session = await mgr.get_or_create(sid)
        report("Session created", session is not None)

        await session.persist_turn("hello ambrio", "hello user, I am ambrio")
        report("Turn persisted", len(session._history) == 2)

        # Reload from same DB
        mgr2 = SessionManager()
        await mgr2.init(dbpath)
        session2 = await mgr2.get_or_create(sid)
        report("Session re-created from existing DB", session2 is not None)
    except Exception as e:
        report("Session manager", False, str(e))
    finally:
        os.unlink(dbpath)


# ── Test 7: Checker safety scan ───────────────────────────────────────────────
async def test_checker():
    print("\n[7] Checker — Safety + Verdict")
    try:
        from ambrio.sandbox.checker import CheckerAgent, MakerOutput, Verdict

        checker = CheckerAgent()

        # Safe output
        safe = MakerOutput(stdout='{"rows": []}', stderr="", artifact={"rows": []}, exit_code=0)
        v = await checker.grade({"type": "db_query"}, safe)
        report("PASS verdict on safe output", v == Verdict.PASS, f"verdict={v}")

        # Unsafe output
        unsafe_out = MakerOutput(stdout="import os; eval(evil)", stderr="", artifact={}, exit_code=0)
        v = await checker.grade({"type": "code_exec"}, unsafe_out)
        report("UNSAFE verdict on dangerous output", v == Verdict.UNSAFE, f"verdict={v}")

        # Fail on non-zero exit
        fail_out = MakerOutput(stdout="", stderr="SyntaxError", artifact={}, exit_code=1)
        v = await checker.grade({"type": "code_exec"}, fail_out)
        report("FAIL verdict on non-zero exit", v == Verdict.FAIL, f"verdict={v}")
    except Exception as e:
        report("Checker", False, str(e))


# ── Main ───────────────────────────────────────────────────────────────────────
async def main():
    print("\n" + "="*60)
    print("  [AMBRIO DESKTOP] -- PHASE 4 SMOKE TEST")
    print("="*60)

    ollama_ok = await test_ollama_connectivity()
    await test_fts5_memory()
    await test_context_pruner()
    await test_tool_registry()
    if ollama_ok:
        await test_ollama_streaming()
    else:
        print("\n[5] Ollama Live Streaming — SKIPPED (Ollama not running)")
    await test_session_manager()
    await test_checker()

    # ── Summary ───────────────────────────────────────────────────────────────
    total   = len(results)
    passed  = sum(1 for _, ok, _ in results if ok)
    failed  = total - passed

    print("\n" + "="*60)
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  ({failed} failed)")
        print("\n  Failed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"    {FAIL} {name}: {detail}")
    else:
        print("  — ALL PASS 🎉")
    print("="*60 + "\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
