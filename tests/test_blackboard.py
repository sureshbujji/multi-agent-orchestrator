"""Blackboard tests: state round-trips and message log ordering."""

import pytest

from src.blackboard import Blackboard


def make_board() -> Blackboard:
    board = Blackboard("Design a test plan for a login API.")
    board.set_plan(
        [
            {
                "id": "s1",
                "title": "Subtask 1",
                "description": "First subtask.",
                "acceptance_criteria": {"min_test_cases": 1},
            }
        ]
    )
    return board


def test_post_submit_review_round_trip():
    board = make_board()

    msg = board.post_message("planner", "orchestrator", "plan_proposed", {"n": 1})
    assert msg["seq"] == 1
    assert msg["sender"] == "planner"

    artifact = board.submit_artifact("s1", "# Artifact", iteration=1)
    assert artifact["content"] == "# Artifact"
    assert board.artifacts["s1"]["iteration"] == 1

    review = board.record_review("s1", "accept", "Looks good.", iteration=1)
    assert review["verdict"] == "accept"
    assert board.reviews[-1]["feedback"] == "Looks good."

    ctx = board.get_context("s1")
    assert ctx["task"].startswith("Design a test plan")
    assert ctx["subtask"]["id"] == "s1"
    assert ctx["artifact"]["content"] == "# Artifact"
    assert ctx["reviews"][0]["verdict"] == "accept"
    assert ctx["iteration"] == 0  # bump_iteration not called yet


def test_message_log_is_append_only_and_ordered():
    board = make_board()
    for i in range(5):
        board.post_message("a", "b", f"type-{i}", {"i": i})
    seqs = [m["seq"] for m in board.messages]
    assert seqs == [1, 2, 3, 4, 5]
    assert [m["type"] for m in board.messages] == [f"type-{i}" for i in range(5)]
    # payloads are deep-copied: mutating the original must not affect the log
    payload = {"items": [1]}
    board.post_message("a", "b", "x", payload)
    payload["items"].append(999)
    assert board.messages[-1]["payload"] == {"items": [1]}


def test_record_review_rejects_bad_verdict():
    board = make_board()
    with pytest.raises(ValueError):
        board.record_review("s1", "maybe", "bad verdict", iteration=1)


def test_subtask_unknown_id_raises():
    board = make_board()
    with pytest.raises(KeyError):
        board.subtask("nope")


def test_bump_iteration_counts_attempts():
    board = make_board()
    assert board.bump_iteration("s1") == 1
    assert board.bump_iteration("s1") == 2
    assert board.iterations["s1"] == 2
