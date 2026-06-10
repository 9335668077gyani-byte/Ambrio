# tests/unit/test_critic_node.py
"""Tests for the Critic node (Maker-Checker verdict logic)."""
import pytest
from ambrio.agents.state import AgentState, SubTask
from ambrio.agents.nodes.critic import critic_node


def _state(**overrides) -> AgentState:
    base = AgentState(
        session_id="s1", user_input="find Python docs",
        messages=[], subtasks=[], current_subtask=0,
        tool_results=[], critic_verdict=None, critic_feedback=None,
        attempt_count=0, final_answer=None, model_alias=None, elapsed=None,
    )
    return {**base, **overrides}


@pytest.mark.asyncio
async def test_all_subtasks_done_gives_pass():
    subtasks = [
        {"description": "t1", "tool": None, "args": None, "status": "done", "result": "ok"},
        {"description": "t2", "tool": "web_search", "args": {}, "status": "done", "result": {"r": 1}},
    ]
    state = _state(subtasks=subtasks, current_subtask=2)
    result = await critic_node(state)
    assert result["critic_verdict"] == "pass"
    assert result["critic_feedback"] is None


@pytest.mark.asyncio
async def test_any_failed_subtask_gives_fail():
    subtasks = [
        {"description": "t1", "tool": "web_search", "args": {}, "status": "failed", "result": "timeout"},
        {"description": "t2", "tool": None, "args": None, "status": "done", "result": None},
    ]
    state = _state(subtasks=subtasks, current_subtask=2)
    result = await critic_node(state)
    assert result["critic_verdict"] == "fail"
    assert "t1" in result["critic_feedback"]


@pytest.mark.asyncio
async def test_pending_subtasks_give_partial():
    subtasks = [
        {"description": "t1", "tool": None, "args": None, "status": "done", "result": None},
        {"description": "t2", "tool": None, "args": None, "status": "pending", "result": None},
    ]
    state = _state(subtasks=subtasks, current_subtask=1)
    result = await critic_node(state)
    assert result["critic_verdict"] == "partial"


@pytest.mark.asyncio
async def test_max_attempts_forces_pass():
    """After MAX_CRITIC_ATTEMPTS retries, critic must pass to prevent infinite loop."""
    subtasks = [
        {"description": "t1", "tool": "web_search", "args": {}, "status": "failed", "result": "err"},
    ]
    state = _state(subtasks=subtasks, current_subtask=1, attempt_count=3)
    result = await critic_node(state)
    assert result["critic_verdict"] == "pass"
    assert "max attempts" in result["critic_feedback"].lower()


@pytest.mark.asyncio
async def test_attempt_count_increments_on_fail():
    subtasks = [
        {"description": "t1", "tool": "web_search", "args": {}, "status": "failed", "result": "err"},
    ]
    state = _state(subtasks=subtasks, current_subtask=1, attempt_count=1)
    result = await critic_node(state)
    assert result["attempt_count"] == 2


@pytest.mark.asyncio
async def test_empty_subtasks_gives_pass():
    """No subtasks = nothing to fail = pass."""
    state = _state(subtasks=[], current_subtask=0)
    result = await critic_node(state)
    assert result["critic_verdict"] == "pass"


# ── New tests added after quality review ─────────────────────────────────────

@pytest.mark.asyncio
async def test_failed_beats_pending():
    """fail has higher priority than partial \u2014 fail wins when both present."""
    subtasks = [
        {"description": "t1", "tool": "web_search", "args": {}, "status": "failed", "result": "timeout"},
        {"description": "t2", "tool": None, "args": None, "status": "pending", "result": None},
    ]
    result = await critic_node(_state(subtasks=subtasks))
    assert result["critic_verdict"] == "fail"


@pytest.mark.asyncio
async def test_pass_does_not_increment_attempt_count():
    subtasks = [
        {"description": "t1", "tool": None, "args": None, "status": "done", "result": "ok"},
    ]
    state = _state(subtasks=subtasks, attempt_count=2)
    result = await critic_node(state)
    assert result["critic_verdict"] == "pass"
    assert result["attempt_count"] == 2          # unchanged


@pytest.mark.asyncio
async def test_partial_increments_attempt_count():
    """partial also counts as a retry \u2014 must increment to prevent infinite loop."""
    subtasks = [
        {"description": "t1", "tool": None, "args": None, "status": "done", "result": None},
        {"description": "t2", "tool": None, "args": None, "status": "pending", "result": None},
    ]
    state = _state(subtasks=subtasks, attempt_count=0)
    result = await critic_node(state)
    assert result["critic_verdict"] == "partial"
    assert result["attempt_count"] == 1          # incremented


@pytest.mark.asyncio
async def test_max_attempts_minus_one_still_retries():
    """One attempt before limit \u2014 should still get a real verdict (fail), not forced pass."""
    subtasks = [
        {"description": "t1", "tool": "web_search", "args": {}, "status": "failed", "result": "err"},
    ]
    state = _state(subtasks=subtasks, attempt_count=2)   # MAX_CRITIC_ATTEMPTS - 1
    result = await critic_node(state)
    assert result["critic_verdict"] == "fail"             # NOT forced pass yet
    assert result["attempt_count"] == 3


@pytest.mark.asyncio
async def test_feedback_includes_description_and_error():
    """Fail feedback maps each failure to 'description: error_detail' format."""
    subtasks = [
        {"description": "search Python", "tool": "web_search", "args": {},
         "status": "failed", "result": "connection refused"},
    ]
    result = await critic_node(_state(subtasks=subtasks))
    assert result["critic_verdict"] == "fail"
    assert "search Python" in result["critic_feedback"]
    assert "connection refused" in result["critic_feedback"]

