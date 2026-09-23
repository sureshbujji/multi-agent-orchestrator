"""Agent roles: Planner, Worker, Critic.

All brains are deterministic mock implementations (rule/template-based, no
API calls, no randomness). The *architecture* — decomposition, execution,
review, and message passing — is real: agents only interact through the
shared Blackboard.

Common interface: every role exposes ``act(blackboard)``. The planner works
on the whole task; the worker and critic additionally take the ``subtask_id``
they should focus on.
"""

from __future__ import annotations

import re
from typing import Any

from src.blackboard import Blackboard


class PlannerAgent:
    """Decomposes a task into subtasks with acceptance criteria."""

    name = "planner"

    # ------------------------------------------------------------------ #
    # Mock brain: keyword/template-based decomposition
    # ------------------------------------------------------------------ #
    def _decompose_login_api_test_plan(self) -> list[dict[str, Any]]:
        """Domain template: test-plan design for a login API."""
        return [
            {
                "id": "auth-flows",
                "title": "Authentication flows",
                "description": (
                    "Cover the core login API authentication flows: successful login "
                    "with valid credentials, logout invalidating the session token, "
                    "refreshing an expired access token with a refresh token, and the "
                    "password reset flow issuing a time-limited token."
                ),
                "acceptance_criteria": {
                    "min_test_cases": 4,
                    "required_sections": ["Test Cases", "Objective"],
                    "required_keywords": ["token", "logout"],
                },
            },
            {
                "id": "negative-edge",
                "title": "Negative and edge cases",
                "description": (
                    "Cover negative and edge cases for the login API: wrong password "
                    "returns 401 without leaking which field was wrong, locked "
                    "accounts return 403 with an unlock flow, expired session tokens "
                    "return 401 with a clear error code, and empty or missing fields "
                    "return 400 validation errors."
                ),
                "acceptance_criteria": {
                    "min_test_cases": 4,
                    "required_sections": ["Test Cases", "Objective"],
                    "required_keywords": ["401", "400"],
                },
            },
            {
                "id": "security",
                "title": "Security tests",
                "description": (
                    "Cover security tests for the login API: SQL injection in the "
                    "username field must be neutralized, rate limiting must block "
                    "brute-force attempts, repeated failures must trigger account "
                    "lockout, and a fresh session id must be issued after login to "
                    "prevent session fixation."
                ),
                "acceptance_criteria": {
                    "min_test_cases": 4,
                    "required_sections": ["Test Cases", "Objective"],
                    "required_keywords": ["sql injection", "rate limiting"],
                },
                # Flagged hard: the worker's first attempt is deliberately thin
                # so the critic/rework path is exercised end to end.
                "hard": True,
            },
            {
                "id": "performance",
                "title": "Performance tests",
                "description": (
                    "Cover performance tests for the login API: p95 login latency "
                    "under 500ms at 100 concurrent users, sustained throughput of "
                    "1000 logins per minute without errors, token refresh staying "
                    "within the latency budget under load, and graceful degradation "
                    "with 503 plus Retry-After when the service is overloaded."
                ),
                "acceptance_criteria": {
                    "min_test_cases": 4,
                    "required_sections": ["Test Cases", "Objective"],
                    "required_keywords": ["latency", "throughput"],
                },
            },
        ]

    def _decompose_generic(self, task: str) -> list[dict[str, Any]]:
        """Fallback: one subtask per sentence in the task description."""
        sentences = [s.strip() for s in re.split(r"[.!?]+", task) if s.strip()]
        if not sentences:
            sentences = [task.strip() or "Execute the task"]
        subtasks = []
        for i, sentence in enumerate(sentences[:5], start=1):
            subtasks.append(
                {
                    "id": f"subtask-{i}",
                    "title": f"Subtask {i}",
                    "description": sentence,
                    "acceptance_criteria": {
                        "min_test_cases": 2,
                        "required_sections": ["Test Cases", "Objective"],
                        "required_keywords": [],
                    },
                }
            )
        return subtasks

    def _decompose(self, task: str) -> list[dict[str, Any]]:
        lowered = task.lower()
        if "login" in lowered and ("api" in lowered or "test plan" in lowered):
            return self._decompose_login_api_test_plan()
        return self._decompose_generic(task)

    # ------------------------------------------------------------------ #
    # Agent interface
    # ------------------------------------------------------------------ #
    def act(self, blackboard: Blackboard) -> list[dict[str, Any]]:
        subtasks = self._decompose(blackboard.task)
        blackboard.set_plan(subtasks)
        blackboard.post_message(
            sender=self.name,
            recipient="orchestrator",
            type="plan_proposed",
            payload={"subtask_ids": [s["id"] for s in subtasks]},
        )
        return subtasks


class WorkerAgent:
    """Executes one subtask and produces a structured markdown artifact."""

    name = "worker"

    # -- Mock brain: template test-case banks per subtask ---------------- #
    _CASE_BANKS: dict[str, list[dict[str, str]]] = {
        "auth-flows": [
            {"case": "Valid credentials return 200 with access and refresh tokens",
             "steps": "POST /login with a valid username and password",
             "expected": "200 OK; response contains access_token and refresh_token"},
            {"case": "Logout invalidates the session token",
             "steps": "POST /logout with a valid token, then reuse the token on a protected endpoint",
             "expected": "Logout returns 200; reused token returns 401"},
            {"case": "Expired access token can be refreshed",
             "steps": "Wait for access token expiry, then POST /refresh with the refresh token",
             "expected": "200 OK with a new access token; old token stays rejected"},
            {"case": "Password reset issues a time-limited token",
             "steps": "POST /password-reset for a known account, then use the emailed token to set a new password",
             "expected": "Reset token valid for 15 minutes; login succeeds with the new password"},
        ],
        "negative-edge": [
            {"case": "Wrong password returns 401 without leaking which field was wrong",
             "steps": "POST /login with a valid username and wrong password",
             "expected": "401 with a generic 'invalid credentials' error"},
            {"case": "Locked account returns 403 and offers an unlock flow",
             "steps": "Exceed the failed-attempt threshold, then attempt login again",
             "expected": "403 account locked; unlock email/code flow is triggered"},
            {"case": "Expired session token returns 401 with a clear error code",
             "steps": "Call a protected endpoint with an expired token",
             "expected": "401 with error code TOKEN_EXPIRED"},
            {"case": "Empty or missing fields return 400 validation errors",
             "steps": "POST /login with missing username and empty password",
             "expected": "400 listing each missing/invalid field"},
        ],
        "security": [
            {"case": "SQL injection in the username field is neutralized",
             "steps": "POST /login with username `' OR '1'='1` and any password",
             "expected": "401; no error leakage; query uses parameterized statements"},
            {"case": "Rate limiting blocks brute-force attempts",
             "steps": "Send 60 login attempts within one minute from a single IP",
             "expected": "429 Too Many Requests with Retry-After after the threshold"},
            {"case": "Repeated failures trigger account lockout",
             "steps": "Attempt login with wrong passwords 10 times in a row",
             "expected": "Account locked; further attempts return 403 until unlock"},
            {"case": "Fresh session id is issued after login (no session fixation)",
             "steps": "Fix a session id pre-login, then complete login",
             "expected": "Post-login session id differs from the pre-login one"},
        ],
        "performance": [
            {"case": "p95 login latency stays under 500ms at 100 concurrent users",
             "steps": "Drive 100 concurrent login requests for 5 minutes",
             "expected": "p95 latency < 500ms; zero 5xx errors"},
            {"case": "Sustained throughput of 1000 logins per minute without errors",
             "steps": "Ramp to 1000 logins/min and hold for 10 minutes",
             "expected": "Throughput >= 1000/min; error rate < 0.1%"},
            {"case": "Token refresh stays within the latency budget under load",
             "steps": "Mix refresh calls into the load at 20% of traffic",
             "expected": "p95 refresh latency < 300ms"},
            {"case": "Overload degrades gracefully with 503 and Retry-After",
             "steps": "Push traffic to 5x capacity until saturation",
             "expected": "503 with Retry-After header; recovery without restart"},
        ],
    }

    # First attempt at a flagged-hard subtask is deliberately thin so the
    # critic's rework path is exercised end to end.
    _THIN_BANK: dict[str, list[dict[str, str]]] = {
        "security": [
            {"case": "Repeated failures trigger account lockout",
             "steps": "Attempt login with wrong passwords 10 times in a row",
             "expected": "Account locked; further attempts return 403 until unlock"},
            {"case": "Fresh session id is issued after login (no session fixation)",
             "steps": "Fix a session id pre-login, then complete login",
             "expected": "Post-login session id differs from the pre-login one"},
        ],
    }

    # ------------------------------------------------------------------ #
    # Mock brain: template-based artifact generation
    # ------------------------------------------------------------------ #
    def _cases_for(self, subtask: dict[str, Any], iteration: int) -> list[dict[str, str]]:
        sid = subtask["id"]
        if subtask.get("hard") and iteration == 1 and sid in self._THIN_BANK:
            return self._THIN_BANK[sid]
        if sid in self._CASE_BANKS:
            return self._CASE_BANKS[sid]
        # Generic fallback: one test case per sentence of the description.
        sentences = [s.strip() for s in re.split(r"[.!?]+", subtask["description"]) if s.strip()]
        cases = []
        for i, sentence in enumerate(sentences, start=1):
            cases.append(
                {
                    "case": f"Verify: {sentence}",
                    "steps": "Execute the scenario described in the subtask",
                    "expected": "Observed behavior matches the subtask description",
                }
            )
        return cases or [
            {
                "case": f"Verify: {subtask['description']}",
                "steps": "Execute the scenario described in the subtask",
                "expected": "Observed behavior matches the subtask description",
            }
        ]

    def _render_artifact(
        self,
        subtask: dict[str, Any],
        cases: list[dict[str, str]],
        iteration: int,
        feedback: str | None,
    ) -> str:
        lines = [
            f"# {subtask['title']}",
            "",
            "## Objective",
            "",
            subtask["description"],
            "",
            "## Test Cases",
            "",
            "| ID | Test Case | Steps | Expected Result |",
            "|----|-----------|-------|-----------------|",
        ]
        for i, case in enumerate(cases, start=1):
            lines.append(
                f"| TC-{i} | {case['case']} | {case['steps']} | {case['expected']} |"
            )
        lines += [
            "",
            "## Acceptance Criteria",
            "",
        ]
        criteria = subtask["acceptance_criteria"]
        lines.append(f"- At least {criteria['min_test_cases']} test cases")
        for keyword in criteria.get("required_keywords", []):
            lines.append(f"- Covers: {keyword}")
        if iteration > 1 and feedback:
            lines += [
                "",
                "## Revision Notes",
                "",
                f"Addressed critic feedback from the previous review: {feedback}",
            ]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Agent interface
    # ------------------------------------------------------------------ #
    def act(self, blackboard: Blackboard, subtask_id: str) -> dict[str, Any]:
        context = blackboard.get_context(subtask_id)
        iteration = blackboard.bump_iteration(subtask_id)
        feedback = context["reviews"][-1]["feedback"] if context["reviews"] else None
        cases = self._cases_for(context["subtask"], iteration)
        content = self._render_artifact(context["subtask"], cases, iteration, feedback)
        artifact = blackboard.submit_artifact(subtask_id, content, iteration)
        blackboard.post_message(
            sender=self.name,
            recipient="critic",
            type="artifact_submitted",
            payload={"subtask_id": subtask_id, "iteration": iteration},
        )
        return artifact


class CriticAgent:
    """Reviews an artifact against its subtask's acceptance criteria."""

    name = "critic"

    # ------------------------------------------------------------------ #
    # Mock brain: concrete, deterministic checks (never random)
    # ------------------------------------------------------------------ #
    @staticmethod
    def count_test_cases(content: str) -> int:
        """Count markdown table rows of the form `| TC-<n> | ...`."""
        return len(re.findall(r"^\|\s*TC-\d+\b", content, flags=re.MULTILINE | re.IGNORECASE))

    @staticmethod
    def missing_sections(content: str, required: list[str]) -> list[str]:
        lowered = content.lower()
        missing = []
        for section in required:
            if not re.search(r"^#{1,6}\s+" + re.escape(section.lower()) + r"\b", lowered, flags=re.MULTILINE):
                missing.append(section)
        return missing

    @staticmethod
    def missing_keywords(content: str, required: list[str]) -> list[str]:
        lowered = content.lower()
        return [kw for kw in required if kw.lower() not in lowered]

    def _review(self, content: str, criteria: dict[str, Any]) -> dict[str, str]:
        problems: list[str] = []

        n_cases = self.count_test_cases(content)
        min_cases = criteria.get("min_test_cases", 0)
        if n_cases < min_cases:
            problems.append(
                f"only {n_cases} test case(s) found, minimum required is {min_cases}"
            )

        missing_sections = self.missing_sections(content, criteria.get("required_sections", []))
        if missing_sections:
            problems.append(f"missing required section(s): {', '.join(missing_sections)}")

        # Keywords must be covered by the actual test content, not merely
        # echoed in the Acceptance Criteria checklist, so strip that section.
        test_body = re.split(
            r"^#{1,6}\s+acceptance criteria\b",
            content,
            flags=re.MULTILINE | re.IGNORECASE,
        )[0]
        missing_keywords = self.missing_keywords(test_body, criteria.get("required_keywords", []))
        if missing_keywords:
            problems.append(f"missing required keyword(s): {', '.join(missing_keywords)}")

        if problems:
            return {
                "verdict": "rework",
                "feedback": "Rework required: " + "; ".join(problems) + ".",
            }
        return {
            "verdict": "accept",
            "feedback": (
                f"Accepted: {n_cases} test case(s) present, all required sections "
                "and keywords covered."
            ),
        }

    # ------------------------------------------------------------------ #
    # Agent interface
    # ------------------------------------------------------------------ #
    def act(self, blackboard: Blackboard, subtask_id: str) -> dict[str, Any]:
        context = blackboard.get_context(subtask_id)
        artifact = context["artifact"]
        if artifact is None:
            raise ValueError(f"no artifact submitted for subtask {subtask_id!r}")
        result = self._review(artifact["content"], context["subtask"]["acceptance_criteria"])
        review = blackboard.record_review(
            subtask_id, result["verdict"], result["feedback"], artifact["iteration"]
        )
        blackboard.post_message(
            sender=self.name,
            recipient="worker" if result["verdict"] == "rework" else "orchestrator",
            type="review_posted",
            payload={
                "subtask_id": subtask_id,
                "verdict": result["verdict"],
                "feedback": result["feedback"],
                "iteration": artifact["iteration"],
            },
        )
        return review
