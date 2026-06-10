# ambrio/agents/nodes/planner.py
"""Planner node — decomposes user input into ordered SubTask list via LLM."""
import json
import logging
import re
from typing import Any

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
- Simple single request → ONE subtask (tool=null, answer from memory/LLM)
- Complex/multi-step → 2-4 subtasks maximum
- Never invent tool names outside the list above"""

_FALLBACK_SUBTASK: SubTask = {
    "description": "answer",
    "tool": None,
    "args": None,
    "status": "pending",
    "result": None,
}


def _build_fallback(user_input: str) -> list[SubTask]:
    return [{**_FALLBACK_SUBTASK, "description": user_input}]


def _parse_subtasks(raw: str) -> list[SubTask]:
    """Extract JSON array from LLM output. Returns fallback list on any parse error."""
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if not match:
        return []
    try:
        tasks: list[dict[str, Any]] = json.loads(match.group())
        result: list[SubTask] = []
        for t in tasks:
            result.append(SubTask(
                description=str(t.get("description", "task")),
                tool=t.get("tool") or None,
                args=t.get("args") or None,
                status="pending",
                result=None,
            ))
        return result[:4]  # hard cap at 4 subtasks
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


async def _call_planner_llm(user_input: str) -> list[SubTask]:
    """Call the configured reasoning LLM and parse subtasks from response."""
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

    subtasks = _parse_subtasks(full_text)
    if not subtasks:
        log.warning("[Planner] LLM returned unparseable output — using fallback")
        return _build_fallback(user_input)
    return subtasks


async def planner_node(state: AgentState) -> AgentState:
    """LangGraph node: decompose user_input into subtasks list."""
    log.info(f"[Planner] Planning: {state['user_input'][:80]}")
    try:
        subtasks = await _call_planner_llm(state["user_input"])
    except Exception as e:
        log.error(f"[Planner] LLM call failed ({e}) — using fallback")
        subtasks = _build_fallback(state["user_input"])
    log.info(f"[Planner] → {len(subtasks)} subtask(s)")
    return {**state, "subtasks": subtasks, "current_subtask": 0}
