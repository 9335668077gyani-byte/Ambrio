# ambrio/agents/graph.py
"""LangGraph state machine: Planner → Executor → Critic → Synthesizer.

Cyclic flow:
  planner → executor → critic ─┬─ pass    → synthesizer → END
                                ├─ partial  → executor (retry)
                                └─ fail    → executor (retry)

The Critic's MAX_CRITIC_ATTEMPTS guard prevents infinite loops.
"""
import logging
from typing import Any

from langgraph.graph import StateGraph, END

from ambrio.agents.state import AgentState
from ambrio.agents.nodes.planner     import planner_node
from ambrio.agents.nodes.executor    import executor_node
from ambrio.agents.nodes.critic      import critic_node
from ambrio.agents.nodes.synthesizer import synthesizer_node

log = logging.getLogger(__name__)

_COMPILED_GRAPH: Any = None


def _should_retry(state: AgentState) -> str:
    """Conditional edge: route based on critic_verdict."""
    verdict = state.get("critic_verdict")
    if verdict == "pass":
        return "synthesizer"
    # fail or partial → retry executor
    log.info("[Graph] critic_verdict=%s → retrying executor", verdict)
    return "executor"


def build_graph():
    """Build and compile the LangGraph state machine. Returns compiled graph."""
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is not None:
        return _COMPILED_GRAPH

    g = StateGraph(AgentState)

    # Register nodes
    g.add_node("planner",     planner_node)
    g.add_node("executor",    executor_node)
    g.add_node("critic",      critic_node)
    g.add_node("synthesizer", synthesizer_node)

    # Entry point
    g.set_entry_point("planner")

    # Fixed edges
    g.add_edge("planner",     "executor")
    g.add_edge("executor",    "critic")
    g.add_edge("synthesizer", END)

    # Conditional: critic routes back to executor or forward to synthesizer
    g.add_conditional_edges(
        "critic",
        _should_retry,
        {"executor": "executor", "synthesizer": "synthesizer"},
    )

    _COMPILED_GRAPH = g.compile()
    return _COMPILED_GRAPH


async def run_graph(
    session_id: str,
    user_input:  str,
    messages:    list[dict] | None = None,
    model_alias: str | None = None,
) -> AgentState:
    """Run the agent graph for a single user turn. Returns final AgentState."""
    graph = build_graph()
    initial_state = AgentState(
        session_id=session_id,
        user_input=user_input,
        messages=messages or [],
        subtasks=[],
        current_subtask=0,
        tool_results=[],
        critic_verdict=None,
        critic_feedback=None,
        attempt_count=0,
        final_answer=None,
        model_alias=model_alias,
        elapsed=None,
    )
    log.info("[Graph] run start session=%s input=%r", session_id, user_input[:60])
    final_state: AgentState = await graph.ainvoke(initial_state)
    log.info(
        "[Graph] run done session=%s verdict=%s elapsed=%s",
        session_id, final_state.get("critic_verdict"), final_state.get("elapsed")
    )
    return final_state
