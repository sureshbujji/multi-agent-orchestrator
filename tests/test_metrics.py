"""Metrics tests: hand-computed fixture -> expected values."""

import pytest

from src.metrics import (
    all_metrics,
    avg_iterations_per_subtask,
    critic_acceptance_rate,
    end_to_end_success,
    rework_rate,
)


@pytest.fixture
def transcript():
    # Hand-built fixture:
    #   subtask a: rework then accept (2 iterations)
    #   subtask b: accept on first try (1 iteration)
    # reviews: 3 total -> rework_rate 1/3, acceptance 2/3, avg iterations 1.5
    return {
        "plan": [{"id": "a"}, {"id": "b"}],
        "reviews": [
            {"subtask_id": "a", "verdict": "rework", "feedback": "thin", "iteration": 1},
            {"subtask_id": "a", "verdict": "accept", "feedback": "ok", "iteration": 2},
            {"subtask_id": "b", "verdict": "accept", "feedback": "ok", "iteration": 1},
        ],
        "iterations": {"a": 2, "b": 1},
        "statuses": {"a": "accepted", "b": "accepted"},
    }


def test_rework_rate(transcript):
    assert rework_rate(transcript) == pytest.approx(1 / 3)


def test_critic_acceptance_rate(transcript):
    assert critic_acceptance_rate(transcript) == pytest.approx(2 / 3)


def test_end_to_end_success(transcript):
    assert end_to_end_success(transcript) is True
    failed = dict(transcript)
    failed["statuses"] = {"a": "accepted", "b": "failed"}
    assert end_to_end_success(failed) is False


def test_avg_iterations_per_subtask(transcript):
    assert avg_iterations_per_subtask(transcript) == pytest.approx(1.5)


def test_empty_transcript_edge_cases():
    empty = {"plan": [], "reviews": [], "iterations": {}, "statuses": {}}
    assert rework_rate(empty) == 0.0
    assert critic_acceptance_rate(empty) == 0.0
    assert avg_iterations_per_subtask(empty) == 0.0
    assert end_to_end_success(empty) is False


def test_all_metrics_bundle(transcript):
    m = all_metrics(transcript)
    assert m["rework_rate"] == pytest.approx(1 / 3)
    assert m["critic_acceptance_rate"] == pytest.approx(2 / 3)
    assert m["end_to_end_success"] is True
    assert m["avg_iterations_per_subtask"] == pytest.approx(1.5)
    assert m["total_reviews"] == 3
    assert m["total_subtasks"] == 2
