# tests/unit/test_planner_node.py
import pytest
from unittest.mock import AsyncMock, patch
from ambrio.agents.state import AgentState
from ambrio.agents.nodes.planner import planner_node

MOCK_SUBTASKS = [
    {"description": "search for Python", "tool": "web_search",
     "args": {"query": "Python"}, "status": "pending", "result": None},
    {"description": "summarize results", "tool": None,
     "args": None, "status": "pending", "result": None},
]

@pytest.mark.asyncio
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
    assert result["subtasks"][1]["tool"] is None

@pytest.mark.asyncio
async def test_planner_fallback_on_bad_llm_output():
    """If LLM returns garbage, planner must produce a single no-tool subtask."""
    state = AgentState(
        session_id="s1", user_input="hello world",
        messages=[], subtasks=[], current_subtask=None, tool_results=[],
        critic_verdict=None, critic_feedback=None, attempt_count=0,
        final_answer=None, model_alias=None, elapsed=None,
    )
    with patch("ambrio.agents.nodes.planner._call_planner_llm",
               new_callable=AsyncMock) as mock:
        mock.side_effect = Exception("LLM timeout")
        result = await planner_node(state)
    # Must not crash — fall back to single no-tool subtask
    assert len(result["subtasks"]) == 1
    assert result["subtasks"][0]["tool"] is None
    assert result["current_subtask"] == 0
