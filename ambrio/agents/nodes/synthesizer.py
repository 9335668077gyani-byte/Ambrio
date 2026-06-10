# ambrio/agents/nodes/synthesizer.py
"""Synthesizer node — generates the final answer from subtask results via LLM."""
import logging
import time
from typing import Any

from ambrio.agents.state import AgentState

log = logging.getLogger(__name__)

_SYNTHESIZER_SYSTEM = """You are a helpful assistant. The user asked a question.
You have been given research results from tools. Synthesize them into a clear,
concise, and accurate final answer. Use markdown formatting where helpful.
Never fabricate information not present in the tool results."""

_FALLBACK_ANSWER = "I encountered an error generating a response. Please try again."


def _build_synthesis_prompt(user_input: str, tool_results: list[dict[str, Any]]) -> str:
    """Build the synthesis prompt from user question and tool outputs."""
    if not tool_results:
        return user_input
    parts = [f"User question: {user_input}", "", "Tool results:"]
    for i, r in enumerate(tool_results, 1):
        tool = r.get("tool", "unknown")
        result = r.get("result")
        error  = r.get("error")
        if error:
            parts.append(f"{i}. [{tool}] ERROR: {error}")
        else:
            parts.append(f"{i}. [{tool}] {result}")
    return "\n".join(parts)


async def _call_synthesizer_llm(user_input: str, tool_results: list[dict[str, Any]]) -> str:
    """Call the chat LLM and stream a final answer."""
    from ambrio.config import PROVIDER_KEYS
    from ambrio.router.model_router import ModelRouter

    router = ModelRouter(provider_keys=PROVIDER_KEYS)
    prompt = _build_synthesis_prompt(user_input, tool_results)
    messages = [
        {"role": "system", "content": _SYNTHESIZER_SYSTEM},
        {"role": "user",   "content": prompt},
    ]
    full_text = ""
    async for chunk in router.stream(messages, task_type="chat"):
        if chunk.get("done"):
            break
        full_text += chunk.get("message", {}).get("content", "")
    return full_text.strip() or _FALLBACK_ANSWER


async def synthesizer_node(state: AgentState) -> AgentState:
    """LangGraph node: synthesize final_answer from tool_results via LLM."""
    log.info("[Synthesizer] synthesizing answer for: %r", state["user_input"][:60])
    t0 = time.monotonic()
    try:
        answer = await _call_synthesizer_llm(
            state["user_input"], state["tool_results"]
        )
    except Exception as e:
        log.error("[Synthesizer] LLM failed: %s", e, exc_info=True)
        answer = _FALLBACK_ANSWER
    elapsed = round(time.monotonic() - t0, 3)
    log.info("[Synthesizer] done in %.2fs", elapsed)
    return {
        **state,
        "final_answer": answer,
        "elapsed":      elapsed,
    }
