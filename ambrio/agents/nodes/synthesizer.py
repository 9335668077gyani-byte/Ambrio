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

_SYNTHESIZER_SYSTEM_NO_TOOLS = """You are a helpful assistant.
Answer the user's question clearly and concisely using your knowledge.
Use markdown formatting where helpful."""

_FALLBACK_ANSWER = (
    "I wasn't able to generate an answer right now. "
    "Please try rephrasing your question."
)

# ── Singleton router (one instance per process) ───────────────────────────────
_router: "Any | None" = None


def _get_router() -> "Any":
    """Lazy-init ModelRouter singleton — never re-constructed across calls."""
    global _router
    if _router is None:
        from ambrio.config import PROVIDER_KEYS
        from ambrio.router.model_router import ModelRouter
        _router = ModelRouter(provider_keys=PROVIDER_KEYS)
    return _router


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_synthesis_prompt(user_input: str, tool_results: list[dict[str, Any]]) -> str:
    """Build the synthesis prompt from user question and tool outputs.

    Returns bare ``user_input`` when there are no tool results, so the LLM
    can still answer from general knowledge without a misleading preamble.
    """
    if not tool_results:
        return user_input

    parts = [f"User question: {user_input}", "", "Tool results:"]
    for i, r in enumerate(tool_results, 1):
        tool   = r.get("tool", "unknown")
        result = r.get("result")
        error  = r.get("error")
        if error:
            parts.append(f"{i}. [{tool}] ERROR: {error}")
        elif result is None:
            parts.append(f"{i}. [{tool}] (no result returned)")
        else:
            parts.append(f"{i}. [{tool}] {result}")
    return "\n".join(parts)


# ── LLM caller ────────────────────────────────────────────────────────────────

async def _call_synthesizer_llm(user_input: str, tool_results: list[dict[str, Any]]) -> str:
    """Call the chat LLM and stream a final answer."""
    router = _get_router()
    prompt = _build_synthesis_prompt(user_input, tool_results)
    system = _SYNTHESIZER_SYSTEM if tool_results else _SYNTHESIZER_SYSTEM_NO_TOOLS
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]
    full_text = ""
    async for chunk in router.stream(messages, task_type="chat"):
        if chunk.get("done"):
            break
        full_text += chunk.get("message", {}).get("content", "")

    if not full_text.strip():
        log.warning("[Synthesizer] LLM returned empty stream — using fallback")
        return _FALLBACK_ANSWER
    return full_text.strip()


# ── LangGraph node ────────────────────────────────────────────────────────────

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
