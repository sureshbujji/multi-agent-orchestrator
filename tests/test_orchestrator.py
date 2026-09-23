"""Orchestrator tests: termination, bounded rework, and the happy path."""

from src.orchestrator import Orchestrator
from src.roles import WorkerAgent


class AlwaysFailWorker(WorkerAgent):
    """Worker whose artifacts can never pass review (only 1 thin case)."""

    def _cases_for(self, subtask, iteration):
        return [
            {
                "case": "A single thin case",
                "steps": "Do the thing",
                "expected": "It works",
            }
        ]


def test_run_terminates_and_succeeds_on_demo_task():
    transcript = Orchestrator(max_rework=2).run("Design a test plan for a login API.")
    assert set(transcript["statuses"].values()) == {"accepted"}
    assert len(transcript["plan"]) == 4
    # the flagged-hard security subtask needed exactly one rework cycle
    security_reviews = [r for r in transcript["reviews"] if r["subtask_id"] == "security"]
    assert [r["verdict"] for r in security_reviews] == ["rework", "accept"]
    assert transcript["iterations"]["security"] == 2
    # every handoff is a message; plan + per-subtask traffic + start/finish
    types = [m["type"] for m in transcript["messages"]]
    assert types[0] == "run_started"
    assert types[-1] == "run_finished"
    assert "plan_proposed" in types
    assert "artifact_submitted" in types
    assert "review_posted" in types
    assert "revision_requested" in types
    assert "subtask_accepted" in types


def test_rework_is_bounded_worker_that_always_fails():
    # Generic fallback plan: single sentence -> one subtask, min 2 cases.
    orchestrator = Orchestrator(worker=AlwaysFailWorker(), max_rework=2)
    transcript = orchestrator.run("Do the thing.")
    assert len(transcript["plan"]) == 1
    sid = transcript["plan"][0]["id"]
    assert transcript["statuses"][sid] == "failed"
    # attempts bounded at max_rework + 1; no infinite loop
    assert transcript["iterations"][sid] == 3
    reviews = [r for r in transcript["reviews"] if r["subtask_id"] == sid]
    assert len(reviews) == 3
    assert all(r["verdict"] == "rework" for r in reviews)
    assert any(
        m["type"] == "subtask_failed" and m["payload"]["subtask_id"] == sid
        for m in transcript["messages"]
    )


def test_zero_rework_budget_fails_fast():
    orchestrator = Orchestrator(worker=AlwaysFailWorker(), max_rework=0)
    transcript = orchestrator.run("Do the thing.")
    sid = transcript["plan"][0]["id"]
    assert transcript["statuses"][sid] == "failed"
    assert transcript["iterations"][sid] == 1
    assert len(transcript["reviews"]) == 1


def test_run_is_deterministic():
    first = Orchestrator(max_rework=2).run("Design a test plan for a login API.")
    second = Orchestrator(max_rework=2).run("Design a test plan for a login API.")
    assert first == second
