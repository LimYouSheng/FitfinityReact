"""Safe diagnostics must survive receipts without leaking arbitrary exception content."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from deployment_profile import DEVELOPER
from operation_journal import Journal
from operator_checks import require
from operator_errors import retain_failure, safe_reason
from release_health import read_url
from rollout_provider import aws


class DiagnosticTests(unittest.TestCase):
    def test_validation_reason_survives_without_destroying_original_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Journal(Path(directory) / "receipt.json")
            journal.save({"state": "execute_submitted", "execution_requested": True})
            try:
                require(False, "Deployed template differs")
            except RuntimeError as error:
                failure = retain_failure(journal, error, "Rollout")
            self.assertIn("Deployed template differs", str(failure))
            self.assertTrue(journal.value["execution_requested"])
            self.assertEqual(journal.value["state"], "execute_submitted")
            self.assertEqual(journal.value["failed_stage"], "Rollout")

    def test_unknown_exceptions_never_copy_private_values(self):
        for error in (
            RuntimeError("secret-marker"),
            KeyError("secret-marker"),
            ValueError("secret-marker"),
            OSError("secret-marker"),
        ):
            with self.subTest(kind=type(error).__name__):
                self.assertNotIn("secret-marker", safe_reason(error))
                self.assertTrue(safe_reason(error))

    def test_aws_denial_names_operation_and_allowlisted_code_only(self):
        for code, expected in (
            ("AccessDenied", "AccessDenied"),
            ("secretmarker", "UnknownProviderError"),
        ):
            result = SimpleNamespace(
                returncode=254,
                stdout="secret-marker",
                stderr=f"An error occurred ({code}) when calling the ExecuteChangeSet operation: "
                "secret-marker",
            )
            with patch("operator_errors.subprocess.run", return_value=result) as run:
                with self.assertRaises(RuntimeError) as caught:
                    aws("cloudformation", "execute-change-set", {}, profile=DEVELOPER)
                self.assertIn("cloudformation/execute-change-set", str(caught.exception))
                self.assertIn("code=" + expected, str(caught.exception))
                self.assertNotIn("secret-marker", str(caught.exception))
                run.assert_called_once()

    def test_timeout_preserves_uncertainty_without_command_or_output(self):
        error = subprocess.TimeoutExpired(["aws", "secret-marker"], 60, output="secret-marker")
        with patch("operator_errors.subprocess.run", side_effect=error) as run:
            with self.assertRaises(RuntimeError) as caught:
                aws("cloudformation", "execute-change-set", {}, profile=DEVELOPER)
            self.assertIn("LocalProcessTimeout", str(caught.exception))
            self.assertIn("may have reached AWS", str(caught.exception))
            self.assertNotIn("secret-marker", str(caught.exception))
            run.assert_called_once()

    def test_invalid_response_is_distinct_from_empty_success(self):
        with patch("operator_errors.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            self.assertEqual(aws("cloudformation", "execute-change-set", {}, profile=DEVELOPER), {})
            run.return_value.stdout = "secret-marker"
            with self.assertRaises(RuntimeError) as caught:
                aws("cloudformation", "execute-change-set", {}, profile=DEVELOPER)
            self.assertIn("InvalidProviderResponse", str(caught.exception))
            self.assertNotIn("secret-marker", str(caught.exception))

    def test_health_names_endpoint_and_status_without_body_or_headers(self):
        url = "https://d123.cloudfront.net/health/ready"
        with patch("release_health.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError(url, 503, "secret-marker", {}, None)
            with self.assertRaises(RuntimeError) as caught:
                read_url(url)
            self.assertIn("health/ready: HTTP 503", str(caught.exception))
            self.assertNotIn("secret-marker", str(caught.exception))
            opener.return_value.open.assert_called_once()
