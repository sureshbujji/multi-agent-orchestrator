"""Critic tests: accepts good artifacts, flags thin ones, accepts revisions."""

from src.blackboard import Blackboard
from src.roles import CriticAgent, WorkerAgent


def login_security_plan():
    return [
        {
            "id": "security",
            "title": "Security tests",
            "description": "Security tests for the login API.",
            "acceptance_criteria": {
                "min_test_cases": 4,
                "required_sections": ["Test Cases", "Objective"],
                "required_keywords": ["sql injection", "rate limiting"],
            },
            "hard": True,
        }
    ]


def test_critic_accepts_good_artifact():
    board = Blackboard("Design a test plan for a login API.")
    board.set_plan(
        [
            {
                "id": "auth-flows",
                "title": "Authentication flows",
                "description": "Auth flows.",
                "acceptance_criteria": {
                    "min_test_cases": 4,
                    "required_sections": ["Test Cases", "Objective"],
                    "required_keywords": ["token", "logout"],
                },
            }
        ]
    )
    WorkerAgent().act(board, "auth-flows")  # first attempt: full bank, 4 cases
    review = CriticAgent().act(board, "auth-flows")
    assert review["verdict"] == "accept"
    assert board.reviews[0]["verdict"] == "accept"


def test_critic_requests_rework_on_thin_artifact_then_accepts_revision():
    board = Blackboard("Design a test plan for a login API.")
    board.set_plan(login_security_plan())
    worker, critic = WorkerAgent(), CriticAgent()

    worker.act(board, "security")  # iteration 1: deliberately thin
    first = critic.act(board, "security")
    assert first["verdict"] == "rework"
    assert "sql injection" in first["feedback"]
    assert "rate limiting" in first["feedback"]

    worker.act(board, "security")  # iteration 2: full artifact + revision notes
    revised_artifact = board.artifacts["security"]
    assert "Revision Notes" in revised_artifact["content"]
    second = critic.act(board, "security")
    assert second["verdict"] == "accept"


def test_critic_counts_cases_and_sections_concretely():
    critic = CriticAgent()
    assert critic.count_test_cases("| TC-1 | a | b | c |\n| TC-2 | d | e | f |") == 2
    assert critic.count_test_cases("no table here") == 0
    content = "# Title\n\n## Test Cases\n\nbody"
    assert critic.missing_sections(content, ["Test Cases"]) == []
    assert critic.missing_sections(content, ["Objective"]) == ["Objective"]
    assert critic.missing_keywords("rate limiting is here", ["rate limiting", "sql injection"]) == [
        "sql injection"
    ]


def test_critic_raises_without_artifact():
    board = Blackboard("task")
    board.set_plan(login_security_plan())
    import pytest

    with pytest.raises(ValueError):
        CriticAgent().act(board, "security")
