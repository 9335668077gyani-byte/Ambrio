# ambrio/agents/state.py
from typing import TypedDict, Optional, Any


class SubTask(TypedDict):
    description: str
    tool:        Optional[str]
    args:        Optional[dict]
    status:      str               # "pending" | "done" | "failed"
    result:      Optional[Any]


class AgentState(TypedDict):
    session_id:      str
    user_input:      str
    messages:        list[dict]
    subtasks:        list[SubTask]
    current_subtask: Optional[int]
    tool_results:    list[dict]
    critic_verdict:  Optional[str]   # "pass" | "fail" | "partial"
    critic_feedback: Optional[str]
    attempt_count:   int
    final_answer:    Optional[str]
    model_alias:     Optional[str]
    elapsed:         Optional[float]
