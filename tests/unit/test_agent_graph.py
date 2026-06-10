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
