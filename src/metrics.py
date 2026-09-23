"""Run metrics: pure functions over a run transcript.

Every function takes the transcript dict produced by ``Orchestrator.run()``
and returns a plain number/bool. No I/O, no state, no randomness.
"""

from __future__ import annotations

from typing import Any


def rework_rate(transcript: dict[str, Any]) -> float:
    """Fraction of critic reviews that requested rework (0.0 when no reviews)."""
    reviews = transcript.get("reviews", [])
    if not reviews:
        return 0.0
    reworks = sum(1 for r in reviews if r["verdict"] == "rework")
    return reworks / len(reviews)


def critic_acceptance_rate(transcript: dict[str, Any]) -> float:
    """Fraction of critic reviews that accepted the artifact (0.0 when none)."""
    reviews = transcript.get("reviews", [])
    if not reviews:
        return 0.0
    accepts = sum(1 for r in reviews if r["verdict"] == "accept")
    return accepts / len(reviews)


def end_to_end_success(transcript: dict[str, Any]) -> bool:
    """True when every planned subtask ended with status 'accepted'."""
    plan = transcript.get("plan", [])
    statuses = transcript.get("statuses", {})
    if not plan:
        return False
    return all(statuses.get(s["id"]) == "accepted" for s in plan)


def avg_iterations_per_subtask(transcript: dict[str, Any]) -> float:
    """Mean worker attempts per planned subtask (0.0 when no subtasks)."""
    plan = transcript.get("plan", [])
    iterations = transcript.get("iterations", {})
    if not plan:
        return 0.0
    total = sum(iterations.get(s["id"], 0) for s in plan)
    return total / len(plan)


def all_metrics(transcript: dict[str, Any]) -> dict[str, Any]:
    """Compute every metric at once (convenience for reports)."""
    return {
        "rework_rate": rework_rate(transcript),
        "critic_acceptance_rate": critic_acceptance_rate(transcript),
        "end_to_end_success": end_to_end_success(transcript),
        "avg_iterations_per_subtask": avg_iterations_per_subtask(transcript),
        "total_reviews": len(transcript.get("reviews", [])),
        "total_subtasks": len(transcript.get("plan", [])),
    }
