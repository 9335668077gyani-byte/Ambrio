# tests/unit/test_executor_node.py
import pytest
from unittest.mock import AsyncMock, patch
from ambrio.agents.state import AgentState, SubTask
from ambrio.agents.nodes.executor import executor_node


def _base_state(**overrides) -> AgentState:
    base = AgentState(
        session_id="s1", user_input="test",
        messages=[], subtasks=[], current_subtask=0,
        tool_results=[], critic_verdict=None, critic_feedback=None,
        attempt_count=0, final_answer=None, model_alias=None, elapsed=None,
    )
    return {**base, **overrides}


@pytest.mark.asyncio
async def test_executor_runs_tool_subtask():
    """Executor calls the tool and stores result in tool_results."""
    subtask: SubTask = {"description": "search Python", "tool": "web_search",
                        "args": {"query": "Python"}, "status": "pending", "result": None}
    state = _base_state(subtasks=[subtask], current_subtask=0)

    with patch("ambrio.agents.nodes.executor._dispatch_tool",
               new_callable=AsyncMock) as mock_tool:
        mock_tool.return_value = {"results": ["Python is great"]}
        result = await executor_node(state)

    assert result["subtasks"][0]["status"] == "done"
    assert result["subtasks"][0]["result"] == {"results": ["Python is great"]}
    assert len(result["tool_results"]) == 1
    assert result["tool_results"][0]["tool"] == "web_search"


@pytest.mark.asyncio
async def test_executor_skips_tool_for_no_tool_subtask():
    """Subtask with tool=None skips dispatch; result stays None, status done."""
    subtask: SubTask = {"description": "summarize", "tool": None,
                        "args": None, "status": "pending", "result": None}
    state = _base_state(subtasks=[subtask], current_subtask=0)

    with patch("ambrio.agents.nodes.executor._dispatch_tool",
               new_callable=AsyncMock) as mock_tool:
        result = await executor_node(state)

    mock_tool.assert_not_called()
    assert result["subtasks"][0]["status"] == "done"
    assert result["subtasks"][0]["result"] is None


@pytest.mark.asyncio
async def test_executor_marks_failed_on_tool_error():
    """If tool raises, subtask status = 'failed', error stored in result."""
    subtask: SubTask = {"description": "search", "tool": "web_search",
                        "args": {"query": "test"}, "status": "pending", "result": None}
    state = _base_state(subtasks=[subtask], current_subtask=0)

    with patch("ambrio.agents.nodes.executor._dispatch_tool",
               new_callable=AsyncMock) as mock_tool:
        mock_tool.side_effect = RuntimeError("network error")
        result = await executor_node(state)

    assert result["subtasks"][0]["status"] == "failed"
    assert "network error" in str(result["subtasks"][0]["result"])
    # tool_results must record the failure too
    assert result["tool_results"][0]["error"] is not None


@pytest.mark.asyncio
async def test_executor_advances_current_subtask():
    """current_subtask increments after execution."""
    subtasks: list[SubTask] = [
        {"description": "step 1", "tool": None, "args": None, "status": "pending", "result": None},
        {"description": "step 2", "tool": None, "args": None, "status": "pending", "result": None},
    ]
    state = _base_state(subtasks=subtasks, current_subtask=0)

    with patch("ambrio.agents.nodes.executor._dispatch_tool", new_callable=AsyncMock):
        result = await executor_node(state)

    assert result["current_subtask"] == 1
