# tests/unit/test_planner_node.py
import pytest
from unittest.mock import AsyncMock, patch
from ambrio.agents.state import AgentState
from ambrio.agents.nodes.planner import planner_node, _parse_subtasks

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


# ── _parse_subtasks unit tests ──────────────────────────────────────────────

def test_parse_subtasks_markdown_fences():
    raw = '```json\n[{"description": "do thing", "tool": null, "args": null, "status": "pending", "result": null}]\n```'
    result = _parse_subtasks(raw)
    assert len(result) == 1
    assert result[0]["tool"] is None


def test_parse_subtasks_nested_args_array():
    raw = '[{"description": "read files", "tool": "file_read", "args": {"files": ["a.pdf", "b.pdf"]}, "status": "pending", "result": null}]'
    result = _parse_subtasks(raw)
    assert len(result) == 1
    assert result[0]["args"] == {"files": ["a.pdf", "b.pdf"]}


def test_parse_subtasks_over_cap_truncates():
    tasks = [
        {"description": f"task {i}", "tool": None, "args": None,
         "status": "pending", "result": None}
        for i in range(6)
    ]
    import json
    result = _parse_subtasks(json.dumps(tasks))
    assert len(result) == 4  # _MAX_SUBTASKS


def test_parse_subtasks_empty_string():
    assert _parse_subtasks("") == []


@pytest.mark.asyncio
async def test_planner_preserves_other_state_fields():
    """State spread must not drop fields."""
    state = AgentState(
        session_id="preserve-me", user_input="hello",
        messages=[{"role": "user", "content": "hello"}],
        subtasks=[], current_subtask=None, tool_results=[],
        critic_verdict=None, critic_feedback=None, attempt_count=2,
        final_answer=None, model_alias="groq/llama-3.3-70b", elapsed=1.5,
    )
    with patch("ambrio.agents.nodes.planner._call_planner_llm",
               new_callable=AsyncMock) as mock:
        mock.return_value = [
            {"description": "t", "tool": None, "args": None,
             "status": "pending", "result": None}
        ]
        result = await planner_node(state)
    assert result["session_id"] == "preserve-me"
    assert result["attempt_count"] == 2
    assert result["model_alias"] == "groq/llama-3.3-70b"
    assert result["current_subtask"] == 0
