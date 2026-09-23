"""Orchestrator: the message-passing loop driving Planner -> Worker -> Critic.

Flow:
  1. Orchestrator broadcasts ``run_started``; the planner posts its plan.
  2. For each subtask, in plan order:
       orchestrator -> worker:  ``work_assigned``
       worker     -> critic:   ``artifact_submitted``
       critic     -> worker | orchestrator: ``review_posted``
     If the verdict is ``rework`` and the subtask's iteration count is still
     within ``max_rework``, the orchestrator sends ``revision_requested`` and
     the worker revises using the critic's feedback. Otherwise the subtask is
     marked ``failed``. The loop is bounded: attempts per subtask never exceed
     ``max_rework + 1``.
  3. Orchestrator broadcasts ``run_finished`` and returns the transcript with
     per-subtask statuses attached.
"""

from __future__ import annotations

from typing import Any

from src.blackboard import Blackboard
from src.roles import CriticAgent, PlannerAgent, WorkerAgent


class Orchestrator:
    def __init__(
        self,
        planner: PlannerAgent | None = None,
        worker: WorkerAgent | None = None,
        critic: CriticAgent | None = None,
        max_rework: int = 2,
    ):
        self.planner = planner or PlannerAgent()
        self.worker = worker or WorkerAgent()
        self.critic = critic or CriticAgent()
        if max_rework < 0:
            raise ValueError("max_rework must be >= 0")
        self.max_rework = max_rework

    def run(self, task: str) -> dict[str, Any]:
        blackboard = Blackboard(task)
        blackboard.post_message(
            sender="orchestrator",
            recipient="planner",
            type="run_started",
            payload={"task": task, "max_rework": self.max_rework},
        )

        self.planner.act(blackboard)

        statuses: dict[str, str] = {}
        for subtask in blackboard.plan:
            subtask_id = subtask["id"]
            blackboard.post_message(
                sender="orchestrator",
                recipient="worker",
                type="work_assigned",
                payload={"subtask_id": subtask_id},
            )
            statuses[subtask_id] = self._run_subtask(blackboard, subtask_id)

        blackboard.post_message(
            sender="orchestrator",
            recipient="all",
            type="run_finished",
            payload={"statuses": dict(statuses)},
        )

        transcript = blackboard.transcript()
        transcript["statuses"] = statuses
        return transcript

    def _run_subtask(self, blackboard: Blackboard, subtask_id: str) -> str:
        """Drive one subtask through worker/critic cycles. Returns final status."""
        while True:
            self.worker.act(blackboard, subtask_id)
            review = self.critic.act(blackboard, subtask_id)
            if review["verdict"] == "accept":
                blackboard.post_message(
                    sender="orchestrator",
                    recipient="all",
                    type="subtask_accepted",
                    payload={"subtask_id": subtask_id, "iteration": review["iteration"]},
                )
                return "accepted"
            iterations = blackboard.iterations[subtask_id]
            if iterations > self.max_rework:
                blackboard.post_message(
                    sender="orchestrator",
                    recipient="all",
                    type="subtask_failed",
                    payload={
                        "subtask_id": subtask_id,
                        "reason": f"rework budget exhausted after {iterations} attempt(s)",
                    },
                )
                return "failed"
            blackboard.post_message(
                sender="orchestrator",
                recipient="worker",
                type="revision_requested",
                payload={
                    "subtask_id": subtask_id,
                    "feedback": review["feedback"],
                    "next_iteration": iterations + 1,
                },
            )
