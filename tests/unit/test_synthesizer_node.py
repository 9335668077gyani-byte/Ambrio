# tests/unit/test_synthesizer_node.py
"""Tests for the Synthesizer node — final answer generation."""
import pytest
from unittest.mock import AsyncMock, patch
from ambrio.agents.state import AgentState, SubTask
from ambrio.agents.nodes.synthesizer import synthesizer_node


def _state(**overrides) -> AgentState:
    base = AgentState(
        session_id="s1", user_input="what is Python?",
        messages=[], subtasks=[], current_subtask=0,
        tool_results=[], critic_verdict=None, critic_feedback=None,
        attempt_count=0, final_answer=None, model_alias=None, elapsed=None,
    )
    return {**base, **overrides}


@pytest.mark.asyncio
async def test_synthesizer_produces_final_answer():
    """Synthesizer calls LLM and sets final_answer."""
    state = _state(
        user_input="explain Python",
        tool_results=[{"tool": "web_search", "result": {"text": "Python is a language"}, "error": None}],
    )
    with patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock:
        mock.return_value = "Python is a high-level programming language."
        result = await synthesizer_node(state)
    assert result["final_answer"] == "Python is a high-level programming language."
    assert result["elapsed"] is not None
    assert isinstance(result["elapsed"], float)


@pytest.mark.asyncio
async def test_synthesizer_works_with_no_tool_results():
    """No-tool subtasks: synthesizer answers from user_input alone."""
    state = _state(user_input="hello", tool_results=[])
    with patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock:
        mock.return_value = "Hello! How can I help?"
        result = await synthesizer_node(state)
    assert result["final_answer"] == "Hello! How can I help?"


@pytest.mark.asyncio
async def test_synthesizer_fallback_on_llm_error():
    """If LLM fails, final_answer is a safe error string (not a crash)."""
    state = _state(user_input="explain Python", tool_results=[])
    with patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock:
        mock.side_effect = Exception("LLM unavailable")
        result = await synthesizer_node(state)
    assert result["final_answer"] is not None
    assert "error" in result["final_answer"].lower() or "unable" in result["final_answer"].lower()


@pytest.mark.asyncio
async def test_synthesizer_preserves_state_fields():
    """State spread must not drop fields like session_id, messages, subtasks."""
    subtasks: list[SubTask] = [
        {"description": "t1", "tool": None, "args": None, "status": "done", "result": None}
    ]
    state = _state(
        session_id="preserve-me", subtasks=subtasks,
        messages=[{"role": "user", "content": "hi"}], attempt_count=1,
    )
    with patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock:
        mock.return_value = "answer"
        result = await synthesizer_node(state)
    assert result["session_id"] == "preserve-me"
    assert result["attempt_count"] == 1
    assert result["subtasks"] == subtasks
    assert result["messages"] == [{"role": "user", "content": "hi"}]
