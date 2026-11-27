"""Verify the automatic entry point cannot elevate untrusted or obsolete CI runs."""

import unittest
from copy import deepcopy
from unittest.mock import Mock

from deployment_profile import DEVELOPER
from orchestration_gate import assess


class GateTests(unittest.TestCase):
    def setUp(self):
        self.source = "a" * 40
        repo = {"full_name": DEVELOPER["github_repository"]}
        self.event = {
            "repository": repo,
            "workflow_run": {
                "head_repository": repo,
                "head_sha": self.source,
                "head_branch": "main",
                "event": "push",
                "path": ".github/workflows/pages.yml",
                "status": "completed",
                "conclusion": "success",
            },
        }
        self.select = Mock(return_value={"state": "source_verified", "source_sha": self.source})

    def test_main_success_checks_all_gates_and_remains_non_mutating(self):
        result = assess("workflow_run", self.event, self.source, DEVELOPER, select=self.select)
        self.assertEqual(result["state"], "source_verified")
        self.assertEqual(result["deployment_decision"], "HOLD")
        self.select.assert_called_once_with(self.source, DEVELOPER)

    def test_foreign_pr_failed_and_obsolete_triggers_are_rejected(self):
        for key, value in (
            ("head_repository", {"full_name": "foreign/repo"}),
            ("head_sha", "b" * 40),
            ("event", "pull_request"),
            ("conclusion", "failure"),
            ("path", ".github/workflows/foreign.yml"),
        ):
            event = deepcopy(self.event)
            event["workflow_run"][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                assess("workflow_run", event, self.source, DEVELOPER, select=self.select)
        self.select.assert_not_called()

    def test_other_verification_still_pending_never_starts_deployment(self):
        self.select.side_effect = RuntimeError("CodeQL pending")
        result = assess("workflow_run", self.event, self.source, DEVELOPER, select=self.select)
        self.assertEqual(result["state"], "waiting_for_verification")
        self.assertEqual(result["reason"], "CodeQL pending")
        self.assertEqual(result["deployment_decision"], "HOLD")


if __name__ == "__main__":
    unittest.main()
