# ambrio/agents/nodes/critic.py
"""Critic node — Maker-Checker verdict: pass | fail | partial.

Verdict logic:
  pass    → all subtasks done (or attempt_count >= MAX_CRITIC_ATTEMPTS)
  fail    → any subtask status == "failed" (triggers re-execution loop)
  partial → any subtask still "pending" (should not normally occur)

MAX_CRITIC_ATTEMPTS prevents infinite retry loops.
"""
import logging
from typing import Literal

from ambrio.agents.state import AgentState, SubTask

log = logging.getLogger(__name__)

MAX_CRITIC_ATTEMPTS: int = 3   # after this many fails, force pass to break loop


def _evaluate(subtasks: list[SubTask]) -> tuple[Literal["pass", "fail", "partial"], str | None]:
    """Pure function: inspect subtask statuses and return (verdict, feedback)."""
    if not subtasks:
        return "pass", None

    failed = [t for t in subtasks if t["status"] == "failed"]
    pending = [t for t in subtasks if t["status"] == "pending"]

    if failed:
        desc_list = ", ".join(f'"{t["description"]}"' for t in failed)
        feedback = f"Failed subtask(s): {desc_list}. Errors: " + "; ".join(
            str(t.get("result", "")) for t in failed
        )
        return "fail", feedback

    if pending:
        return "partial", f"{len(pending)} subtask(s) still pending"

    return "pass", None


async def critic_node(state: AgentState) -> AgentState:
    """LangGraph node: evaluate subtask results and set critic_verdict."""
    attempt = state["attempt_count"]
    subtasks = state["subtasks"]

    # Safety valve: prevent infinite Maker-Checker loop
    if attempt >= MAX_CRITIC_ATTEMPTS:
        log.warning(
            "[Critic] max attempts (%d) reached — forcing pass to break loop", MAX_CRITIC_ATTEMPTS
        )
        return {
            **state,
            "critic_verdict":  "pass",
            "critic_feedback": f"Forced pass after max attempts ({MAX_CRITIC_ATTEMPTS})",
            "attempt_count":   attempt,
        }

    verdict, feedback = _evaluate(subtasks)
    new_attempt = attempt + 1 if verdict == "fail" else attempt

    log.info(
        "[Critic] verdict=%s attempt=%d/%d subtasks=%d",
        verdict, attempt, MAX_CRITIC_ATTEMPTS, len(subtasks)
    )

    return {
        **state,
        "critic_verdict":  verdict,
        "critic_feedback": feedback,
        "attempt_count":   new_attempt,
    }
