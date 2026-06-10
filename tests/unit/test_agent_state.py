from ambrio.agents.state import AgentState


def test_state_has_required_fields():
    state = AgentState(
        session_id="test-session",
        user_input="hello",
        messages=[],
        subtasks=[],
        current_subtask=None,
        tool_results=[],
        critic_verdict=None,
        critic_feedback=None,
        attempt_count=0,
        final_answer=None,
        model_alias=None,
        elapsed=None,
    )
    assert state["session_id"] == "test-session"
    assert state["attempt_count"] == 0
    assert state["critic_verdict"] is None
