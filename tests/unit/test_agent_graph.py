# tests/unit/test_agent_graph.py
"""Smoke tests for the assembled LangGraph agent graph."""
import pytest
from unittest.mock import AsyncMock, patch
from ambrio.agents.graph import build_graph, run_graph
from ambrio.agents.state import AgentState


@pytest.mark.asyncio
async def test_graph_runs_end_to_end_happy_path():
    """Graph: planner → executor → critic(pass) → synthesizer → final_answer."""
    MOCK_SUBTASKS = [
        {"description": "answer", "tool": None, "args": None,
         "status": "pending", "result": None},
    ]

    with patch("ambrio.agents.nodes.planner._call_planner_llm",
               new_callable=AsyncMock) as mock_planner, \
         patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock_synth:

        mock_planner.return_value = MOCK_SUBTASKS
        mock_synth.return_value = "42 is the answer."

        result = await run_graph(
            session_id="test-session",
            user_input="what is the meaning of life?",
        )

    assert result["final_answer"] == "42 is the answer."
    assert result["critic_verdict"] == "pass"
    assert result["elapsed"] is not None


@pytest.mark.asyncio
async def test_graph_handles_planner_failure_gracefully():
    """Even if planner LLM throws, graph produces a final_answer (not a crash)."""
    with patch("ambrio.agents.nodes.planner._call_planner_llm",
               new_callable=AsyncMock) as mock_planner, \
         patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock_synth:

        mock_planner.side_effect = Exception("LLM down")
        mock_synth.return_value = "Fallback answer."

        result = await run_graph(
            session_id="test-session",
            user_input="hello",
        )

    assert result["final_answer"] is not None
    assert result["critic_verdict"] == "pass"


def test_build_graph_returns_singleton():
    """build_graph() must return the SAME object on repeated calls."""
    g1 = build_graph()
    g2 = build_graph()
    assert g1 is g2


@pytest.mark.asyncio
async def test_graph_retries_on_tool_fail_then_recovers():
    """Executor fails a tool subtask → critic routes back → executor retries → pass."""
    call_count = {"n": 0}

    async def dispatch_side_effect(tool_name, args):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("first attempt fails")
        return {"result": "recovered"}

    MOCK_SUBTASKS = [
        {"description": "search", "tool": "web_search", "args": {"query": "test"},
         "status": "pending", "result": None},
    ]

    with patch("ambrio.agents.nodes.planner._call_planner_llm",
               new_callable=AsyncMock) as mock_planner, \
         patch("ambrio.agents.nodes.executor._dispatch_tool",
               side_effect=dispatch_side_effect), \
         patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock_synth:

        mock_planner.return_value = MOCK_SUBTASKS
        mock_synth.return_value = "Search recovered."

        result = await run_graph(session_id="retry-test", user_input="search test")

    assert result["final_answer"] == "Search recovered."
    assert result["critic_verdict"] == "pass"
    assert call_count["n"] == 2   # first attempt + one retry


@pytest.mark.asyncio
async def test_graph_exhausts_max_attempts_and_still_returns():
    """After MAX_CRITIC_ATTEMPTS, critic forces pass — graph terminates normally."""
    async def always_fail(tool_name, args):
        raise RuntimeError("always fails")

    MOCK_SUBTASKS = [
        {"description": "bad_tool", "tool": "web_search", "args": {},
         "status": "pending", "result": None},
    ]

    with patch("ambrio.agents.nodes.planner._call_planner_llm",
               new_callable=AsyncMock) as mock_planner, \
         patch("ambrio.agents.nodes.executor._dispatch_tool",
               side_effect=always_fail), \
         patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock_synth:

        mock_planner.return_value = MOCK_SUBTASKS
        mock_synth.return_value = "Best effort answer."

        result = await run_graph(session_id="max-attempts", user_input="always fails")

    # Graph must terminate, not loop forever
    assert result["final_answer"] is not None
    assert result["critic_verdict"] == "pass"
    assert "max attempts" in (result.get("critic_feedback") or "").lower()


@pytest.mark.asyncio
async def test_graph_synthesizer_crash_returns_fallback():
    """If synthesizer LLM crashes, final_answer is the FALLBACK_ANSWER (no exception)."""
    from ambrio.agents.nodes.synthesizer import _FALLBACK_ANSWER
    MOCK_SUBTASKS = [
        {"description": "answer", "tool": None, "args": None,
         "status": "pending", "result": None},
    ]
    with patch("ambrio.agents.nodes.planner._call_planner_llm",
               new_callable=AsyncMock) as mock_planner, \
         patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm",
               new_callable=AsyncMock) as mock_synth:

        mock_planner.return_value = MOCK_SUBTASKS
        mock_synth.side_effect = Exception("synthesizer down")

        result = await run_graph(session_id="synth-crash", user_input="test")

    assert result["final_answer"] == _FALLBACK_ANSWER
@pytest.mark.asyncio
async def test_full_graph_simple_query():
    from unittest.mock import AsyncMock, patch
    from ambrio.agents.runner import run_agent
    with patch("ambrio.agents.nodes.planner._call_planner_llm", new_callable=AsyncMock) as p, \
         patch("ambrio.agents.nodes.synthesizer._call_synthesizer_llm", new_callable=AsyncMock) as s:
        p.return_value = [{"description": "answer",  "tool": None, "args": None,
                            "status": "pending", "result": None}]
        s.return_value = "The answer is 42."
        tokens = []
        async for token in run_agent("test-s", "what is 6*7", [], None):
            tokens.append(token)
    full = "".join(tokens)
    assert "42" in full

