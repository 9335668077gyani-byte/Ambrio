# ambrio/agents/nodes/executor.py
"""Executor node — dispatches the current SubTask's tool and records results."""
import logging
from typing import Any

from ambrio.agents.state import AgentState, SubTask

log = logging.getLogger(__name__)

# ── Tool registry ─────────────────────────────────────────────────────────────
# Maps tool name → async callable(args: dict) -> Any
# Populated lazily to avoid circular imports; tools register themselves.
_TOOL_REGISTRY: dict[str, Any] = {}


def register_tool(name: str):
    """Decorator: register an async function as an executable tool.

    Usage:
        @register_tool("web_search")
        async def web_search(args: dict) -> Any: ...
    """
    def decorator(fn):
        _TOOL_REGISTRY[name] = fn
        return fn
    return decorator


async def _dispatch_tool(tool_name: str, args: dict[str, Any] | None) -> Any:
    """Look up and call a registered tool. Raises KeyError if unknown."""
    if tool_name not in _TOOL_REGISTRY:
        # Lazy import tools package so all @register_tool decorators fire
        import ambrio.tools  # noqa: F401  (side-effect import)
    if tool_name not in _TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: '{tool_name}'")
    return await _TOOL_REGISTRY[tool_name](args or {})


# ── LangGraph node ────────────────────────────────────────────────────────────

async def executor_node(state: AgentState) -> AgentState:
    """LangGraph node: execute current_subtask and record result."""
    idx = state["current_subtask"]
    subtasks = [dict(t) for t in state["subtasks"]]  # mutable copy
    task = subtasks[idx]
    tool_name = task.get("tool")

    log.info("[Executor] task=%d tool=%s desc=%r", idx, tool_name, task["description"][:60])

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
