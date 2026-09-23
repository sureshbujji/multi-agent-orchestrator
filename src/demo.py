"""Demo: design a test plan for a login API via Planner -> Worker -> Critic.

Runs fully in mock mode (deterministic rule/template brains, no API calls).
Writes:
  reports/run_report.json  - full transcript: task, plan, messages, artifacts,
                             reviews, iterations, statuses, metrics
  reports/run_summary.md   - human-readable run summary

Run from the project root:  python src/demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python src/demo.py` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.metrics import all_metrics
from src.orchestrator import Orchestrator

DEMO_TASK = "Design a test plan for a login API."


def build_summary(task: str, transcript: dict, metrics: dict) -> str:
    lines = [
        "# Multi-Agent Orchestrator - Run Summary",
        "",
        f"**Task:** {task}",
        "",
        "## Metrics",
        "",
        f"- Rework rate: {metrics['rework_rate']:.2%}",
        f"- Critic acceptance rate: {metrics['critic_acceptance_rate']:.2%}",
        f"- End-to-end success: {metrics['end_to_end_success']}",
        f"- Avg iterations per subtask: {metrics['avg_iterations_per_subtask']:.2f}",
        f"- Total reviews: {metrics['total_reviews']}",
        "",
        "## Subtasks",
        "",
    ]
    statuses = transcript.get("statuses", {})
    for subtask in transcript["plan"]:
        sid = subtask["id"]
        status = statuses.get(sid, "unknown")
        attempts = transcript["iterations"].get(sid, 0)
        verdicts = [r["verdict"] for r in transcript["reviews"] if r["subtask_id"] == sid]
        lines.append(f"### {sid} - {subtask['title']}")
        lines.append("")
        lines.append(f"- Status: **{status}** after {attempts} attempt(s)")
        lines.append(f"- Review verdicts: {' -> '.join(verdicts)}")
        lines.append(f"- Description: {subtask['description']}")
        lines.append("")
    lines += [
        "## Message Flow (first 12 events)",
        "",
    ]
    for msg in transcript["messages"][:12]:
        payload_keys = ", ".join(msg["payload"].keys())
        lines.append(
            f"{msg['seq']}. `{msg['sender']}` -> `{msg['recipient']}` "
            f"**{msg['type']}** ({payload_keys})"
        )
    lines += [
        "",
        f"_Full transcript: {len(transcript['messages'])} messages, "
        f"{len(transcript['artifacts'])} artifacts, "
        f"{len(transcript['reviews'])} reviews._",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    orchestrator = Orchestrator(max_rework=2)
    transcript = orchestrator.run(DEMO_TASK)
    metrics = all_metrics(transcript)

    report = {
        "task": DEMO_TASK,
        "metrics": metrics,
        "transcript": transcript,
    }
    (reports_dir / "run_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (reports_dir / "run_summary.md").write_text(build_summary(DEMO_TASK, transcript, metrics))

    print(f"Task: {DEMO_TASK}")
    print(f"Subtasks: {metrics['total_subtasks']}")
    print(f"Rework rate: {metrics['rework_rate']:.2%}")
    print(f"Critic acceptance rate: {metrics['critic_acceptance_rate']:.2%}")
    print(f"End-to-end success: {metrics['end_to_end_success']}")
    print(f"Avg iterations per subtask: {metrics['avg_iterations_per_subtask']:.2f}")
    print("Wrote reports/run_report.json and reports/run_summary.md")


if __name__ == "__main__":
    main()
