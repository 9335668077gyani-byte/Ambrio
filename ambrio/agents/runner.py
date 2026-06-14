# ambrio/agents/runner.py
import asyncio, re
from typing import AsyncIterator
from ambrio.agents.graph import build_graph
from ambrio.agents.state import AgentState

GRAPH = build_graph()

async def run_agent(session_id: str, user_input: str,
                    messages: list[dict],
                    tool_registry=None) -> AsyncIterator[str]:
    """Execute the LangGraph cyclic state machine and yield words as a stream.
    
    Acts as the interface between the stream-based ZMQ router and the batch-based
    LangGraph pipeline. Simulated streaming is used here until the Synthesizer node
    supports true token-level streaming.
    """
    initial: AgentState = AgentState(
        session_id=session_id, user_input=user_input, messages=messages,
        subtasks=[], current_subtask=None, tool_results=[],
        critic_verdict=None, critic_feedback=None, attempt_count=0,
        final_answer=None, model_alias=None, elapsed=None,
    )
    final: AgentState = await GRAPH.ainvoke(initial)
    answer = final.get("final_answer") or ""
    # Preserve all whitespace (newlines, indentation) — split() destroyed markdown
    chunks = re.findall(r'\S+\s*', answer)
    for chunk in chunks:
        yield chunk
        await asyncio.sleep(0.015)
