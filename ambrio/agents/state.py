"""LangGraph state schemas for the Ambrio agent graph."""
# ambrio/agents/state.py
from typing import Any, Literal, Optional, TypedDict


class SubTask(TypedDict):
    description: str
    tool:        Optional[str]
    args:        Optional[dict[str, Any]]
    status:      Literal["pending", "done", "failed"]
    result:      Optional[Any]


class AgentState(TypedDict):
    session_id:      str
    user_input:      str
    messages:        list[dict[str, Any]]      # {"role": str, "content": str}
    subtasks:        list[SubTask]
    current_subtask: Optional[int]
    tool_results:    list[dict[str, Any]]
    critic_verdict:  Optional[Literal["pass", "fail", "partial"]]
    critic_feedback: Optional[str]
    attempt_count:   int
    final_answer:    Optional[str]
    model_alias:     Optional[str]             # e.g. "groq/llama-3.3-70b"
    elapsed:         Optional[float]           # seconds
