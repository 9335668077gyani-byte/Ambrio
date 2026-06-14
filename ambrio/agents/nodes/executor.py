# ambrio/agents/nodes/executor.py
"""Executor node — dispatches the current SubTask's tool and records results."""
import logging
from typing import Any

from ambrio.agents.state import AgentState, SubTask

log = logging.getLogger(__name__)

# ── Tool registry ─────────────────────────────────────────────────────────────
_registry_instance = None

def _get_registry():
    global _registry_instance
    if _registry_instance is None:
        from ambrio.router.tool_registry import ToolRegistry
        _registry_instance = ToolRegistry()
        # Ensure tools are imported so decorators run
        import ambrio.router.tools.memory_tool        # noqa
        import ambrio.router.tools.sparepartspro_tool  # noqa
        import ambrio.router.tools.sandbox_tool        # noqa
        import ambrio.router.tools.file_tool           # noqa
        import ambrio.router.tools.doc_tool            # noqa
        import ambrio.router.tools.convert_tool        # noqa
        import ambrio.router.tools.web_tool            # noqa
        import ambrio.router.tools.img_tool            # noqa
    return _registry_instance

async def _dispatch_tool(tool_name: str, args: dict[str, Any] | None) -> Any:
    registry = _get_registry()
    try:
        return await registry.dispatch(tool_name, args or {})
    except KeyError:
        raise KeyError(f"Unknown tool: '{tool_name}'")


# ── LangGraph node ────────────────────────────────────────────────────────────

async def executor_node(state: AgentState) -> AgentState:
    """LangGraph node: execute current_subtask and record result."""
    idx = state["current_subtask"]
    subtasks = [dict(t) for t in state["subtasks"]]  # mutable copy
    if idx >= len(subtasks):
        log.warning("[Executor] current_subtask=%d out of range (len=%d), skipping", idx, len(subtasks))
        return state
    task = subtasks[idx]
    tool_name = task.get("tool")

    log.info("[Executor] task=%d tool=%s desc=%r", idx, tool_name, task.get("description", "")[:60])

    tool_results = list(state["tool_results"])

    if tool_name:
        try:
            outcome = await _dispatch_tool(tool_name, task.get("args"))
            task["status"] = "done"
            task["result"] = outcome
            tool_results.append({"tool": tool_name, "result": outcome, "error": None})
            log.info("[Executor] tool=%s → success", tool_name)
        except Exception as e:
            err_msg = str(e)
            task["status"] = "failed"
            task["result"] = err_msg
            tool_results.append({"tool": tool_name, "result": None, "error": err_msg})
            log.error("[Executor] tool=%s failed: %s", tool_name, err_msg, exc_info=True)
    else:
        # No tool — Synthesizer will generate the answer from context
        task["status"] = "done"
        task["result"] = None
        log.info("[Executor] task=%d no-tool, skipping dispatch", idx)

    subtasks[idx] = task
    next_idx = idx + 1

    return {
        **state,
        "subtasks":        subtasks,
        "tool_results":    tool_results,
        "current_subtask": next_idx,
    }
