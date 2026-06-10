# ambrio/agents/nodes/critic.py
"""Critic node — Maker-Checker verdict: pass | fail | partial.

Verdict logic:
  pass    → all subtasks done (or attempt_count >= MAX_CRITIC_ATTEMPTS)
  fail    → any subtask status == "failed" (triggers re-execution loop)
  partial → any subtask still "pending" — also treated as a retry trigger

MAX_CRITIC_ATTEMPTS prevents infinite retry loops for BOTH fail and partial.
"""
import logging
from typing import Literal

from ambrio.agents.state import AgentState, SubTask

log = logging.getLogger(__name__)

MAX_CRITIC_ATTEMPTS: int = 3   # after this many retries, force pass to break loop

_KNOWN_STATUSES = {"done", "failed", "pending"}


def _evaluate(subtasks: list[SubTask]) -> tuple[Literal["pass", "fail", "partial"], str | None]:
    """Pure function: inspect subtask statuses and return (verdict, feedback).

    Priority: fail > partial > pass
    Unknown status values are logged as warnings (caller is responsible for logging).
    """
    if not subtasks:
        return "pass", None

    # Warn about unknown statuses — caller logs since this is a pure function
    unknown = [t for t in subtasks if t.get("status") not in _KNOWN_STATUSES]

    failed  = [t for t in subtasks if t.get("status") == "failed"]
    pending = [t for t in subtasks if t.get("status") == "pending"]

    if failed:
        # Map each failure to "description: error_detail" for debuggability
        parts = []
        for t in failed:
            err = t.get("result")
            err_str = str(err) if err is not None else "(no error detail)"
            parts.append(f'"{t.get("description", "unknown")}": {err_str}')
        feedback = "Failed subtask(s): " + "; ".join(parts)
        return "fail", feedback

    if pending:
        return "partial", f"{len(pending)} subtask(s) still pending"

    if unknown:
        return "partial", f"{len(unknown)} subtask(s) have unknown status"

    return "pass", None


def _first_retry_idx(subtasks: list[SubTask]) -> int:
    """Return index of the first failed subtask, or first pending, or 0.

    Used by critic_node to reset current_subtask so executor re-executes
    the failed task instead of advancing past it.
    """
    for i, t in enumerate(subtasks):
        if t.get("status") == "failed":
            return i
    for i, t in enumerate(subtasks):
        if t.get("status") == "pending":
            return i
    return 0


async def critic_node(state: AgentState) -> AgentState:
    """LangGraph node: evaluate subtask results and set critic_verdict."""
    attempt  = state["attempt_count"]
    subtasks = state["subtasks"]

    # Warn about unknown statuses
    unknown = [t for t in subtasks if t.get("status") not in _KNOWN_STATUSES]
    if unknown:
        log.warning(
            "[Critic] %d subtask(s) have unknown status: %s",
            len(unknown),
            [t.get("status") for t in unknown],
        )

    # Safety valve: prevent infinite Maker-Checker loop (covers both fail and partial)
    if attempt >= MAX_CRITIC_ATTEMPTS:
        _, pending_feedback = _evaluate(subtasks)
        forced_msg = (
            f"Forced pass after max attempts ({MAX_CRITIC_ATTEMPTS}). "
            + (f"Last state: {pending_feedback}" if pending_feedback else "All subtasks done.")
        )
        log.warning("[Critic] max attempts (%d) reached — forcing pass", MAX_CRITIC_ATTEMPTS)
        return {
            **state,
            "critic_verdict":  "pass",
            "critic_feedback": forced_msg,
            "attempt_count":   attempt,
        }

    verdict, feedback = _evaluate(subtasks)

    # Both fail and partial count as retry triggers
    new_attempt = attempt + 1 if verdict in ("fail", "partial") else attempt

    # C1 fix: on retry, reset current_subtask to the first failed/pending task
    # so executor re-runs it instead of advancing past it.
    if verdict in ("fail", "partial"):
        new_current = _first_retry_idx(subtasks)
        log.warning(
            "[Critic] verdict=%s attempt=%d/%d — reset current_subtask=%d → re-queuing executor",
            verdict, attempt, MAX_CRITIC_ATTEMPTS, new_current,
        )
    else:
        new_current = state["current_subtask"]
        log.info("[Critic] verdict=%s attempt=%d/%d subtasks=%d",
                 verdict, attempt, MAX_CRITIC_ATTEMPTS, len(subtasks))

    return {
        **state,
        "critic_verdict":   verdict,
        "critic_feedback":  feedback,
        "attempt_count":    new_attempt,
        "current_subtask": new_current,
    }
