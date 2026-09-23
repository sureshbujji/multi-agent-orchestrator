"""Shared blackboard: the single source of truth for the multi-agent run.

All agents communicate by reading from and writing to this object. It holds
the task, the plan, produced artifacts, critic reviews, an append-only
message log (the event trace of every handoff), and per-subtask iteration
counters used to bound rework.

Determinism: messages are numbered with a monotonic sequence counter (no
wall-clock timestamps), so re-running a scenario yields a byte-identical
transcript.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class Blackboard:
    """Central shared state for a Planner -> Worker -> Critic run."""

    def __init__(self, task: str):
        self.task: str = task
        # plan: list of {"id", "description", "acceptance_criteria"}
        self.plan: list[dict[str, Any]] = []
        # artifacts: subtask_id -> {"content", "iteration"}
        self.artifacts: dict[str, dict[str, Any]] = {}
        # reviews: list of {"subtask_id", "verdict", "feedback", "iteration"}
        self.reviews: list[dict[str, Any]] = []
        # messages: append-only event log of dicts
        self.messages: list[dict[str, Any]] = []
        # iteration counters: subtask_id -> number of worker attempts so far
        self.iterations: dict[str, int] = {}
        self._seq: int = 0

    # ------------------------------------------------------------------ #
    # Message passing
    # ------------------------------------------------------------------ #
    def post_message(
        self,
        sender: str,
        recipient: str,
        type: str,  # noqa: A002 - 'type' is the blackboard message field name
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Append an event to the message log and return it."""
        self._seq += 1
        message = {
            "seq": self._seq,
            "sender": sender,
            "recipient": recipient,
            "type": type,
            "payload": deepcopy(payload),
        }
        self.messages.append(message)
        return message

    # ------------------------------------------------------------------ #
    # Plan / artifacts / reviews
    # ------------------------------------------------------------------ #
    def set_plan(self, subtasks: list[dict[str, Any]]) -> None:
        """Register the plan produced by the planner."""
        self.plan = deepcopy(subtasks)
        for subtask in self.plan:
            self.iterations.setdefault(subtask["id"], 0)

    def submit_artifact(
        self, subtask_id: str, content: str, iteration: int
    ) -> dict[str, Any]:
        """Store the worker's output for a subtask."""
        artifact = {"subtask_id": subtask_id, "content": content, "iteration": iteration}
        self.artifacts[subtask_id] = artifact
        return artifact

    def record_review(
        self, subtask_id: str, verdict: str, feedback: str, iteration: int
    ) -> dict[str, Any]:
        """Store the critic's verdict for an artifact. verdict in {"accept", "rework"}."""
        if verdict not in ("accept", "rework"):
            raise ValueError(f"verdict must be 'accept' or 'rework', got {verdict!r}")
        review = {
            "subtask_id": subtask_id,
            "verdict": verdict,
            "feedback": feedback,
            "iteration": iteration,
        }
        self.reviews.append(review)
        return review

    def bump_iteration(self, subtask_id: str) -> int:
        """Increment and return the attempt counter for a subtask."""
        self.iterations[subtask_id] = self.iterations.get(subtask_id, 0) + 1
        return self.iterations[subtask_id]

    def subtask(self, subtask_id: str) -> dict[str, Any]:
        """Return the plan entry for a subtask id (raises KeyError if unknown)."""
        for entry in self.plan:
            if entry["id"] == subtask_id:
                return entry
        raise KeyError(f"unknown subtask id: {subtask_id!r}")

    # ------------------------------------------------------------------ #
    # Read-side helpers
    # ------------------------------------------------------------------ #
    def get_context(self, subtask_id: str | None = None) -> dict[str, Any]:
        """Snapshot of everything an agent needs to act.

        With a subtask_id, returns the focused view: the task, that subtask's
        plan entry, its latest artifact, its review history, and the full
        message log. Without one, returns the global view.
        """
        context: dict[str, Any] = {
            "task": self.task,
            "plan": deepcopy(self.plan),
            "messages": deepcopy(self.messages),
        }
        if subtask_id is not None:
            context["subtask"] = deepcopy(self.subtask(subtask_id))
            context["artifact"] = deepcopy(self.artifacts.get(subtask_id))
            context["reviews"] = deepcopy(
                [r for r in self.reviews if r["subtask_id"] == subtask_id]
            )
            context["iteration"] = self.iterations.get(subtask_id, 0)
        return context

    def transcript(self) -> dict[str, Any]:
        """Full run transcript: deterministic, JSON-serializable."""
        return {
            "task": self.task,
            "plan": deepcopy(self.plan),
            "messages": deepcopy(self.messages),
            "artifacts": deepcopy(self.artifacts),
            "reviews": deepcopy(self.reviews),
            "iterations": deepcopy(self.iterations),
        }
