"""Offline read-boundary and redaction probes for current release collection."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import release_observation as observation


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.identity = {
            "Account": "418638389566",
            "Arn": "arn:aws:sts::418638389566:assumed-role/fitfinity-test-github-hosting/probe",
        }
        self.status = "UPDATE_COMPLETE"
        self.function_arn = (
            "arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-staff-api"
        )

    def call(self, service, operation, *args):
        self.calls.append((service, operation, args))
        if operation == "get-caller-identity":
            return self.identity
        if operation == "describe-stacks":
            return {
                "Stacks": [
                    {
                        "StackName": "fitfinity-test-login",
                        "StackStatus": self.status,
                        "StackId": "synthetic-stack",
                        "Parameters": "sensitive-marker",
                    }
                ]
            }
        if operation == "get-template":
            return {"TemplateBody": {"Resources": {}, "Secret": "sensitive-marker"}}
        if operation == "get-function":
            return {
                "Configuration": {
                    "FunctionArn": self.function_arn,
                    "RevisionId": "revision",
                    "Environment": {
                        "Variables": {
                            "SECRET": "sensitive-marker",
                            "FITFINITY_MEDIA_ENABLED": "sensitive-marker",
                            "FITFINITY_AUTH_ENABLED": "true",
                        }
                    },
                },
                "Code": {
                    "ResolvedImageUri": "image@sha256:synthetic",
                    "Location": "https://example.test/sensitive-marker",
                },
            }
        if operation == "get-alias":
            return {"FunctionVersion": "2", "RevisionId": "alias-revision"}
        if operation == "describe-db-instances":
            return {
                "DBInstances": [
                    {
                        "DBInstanceIdentifier": "fitfinity-test-db",
                        "MasterUsername": "sensitive-marker",
                    }
                ]
            }
        raise AssertionError("Unexpected call")

    def test_safe_projection_retains_no_secrets_or_presigned_urls(self):
        result = observation.observe(self.call)
        self.assertNotIn("sensitive-marker", json.dumps(result))
        self.assertNotIn("https://", json.dumps(result))
        self.assertEqual(result["deployment_decision"], "HOLD")
        self.assertEqual(
            result["runtime"]["latest_configuration"]["feature_flags"]["FITFINITY_AUTH_ENABLED"],
            "true",
        )
        self.assertEqual(
            result["runtime"]["latest_configuration"]["feature_flags"]["FITFINITY_MEDIA_ENABLED"],
            "unset-or-invalid",
        )
        self.assertTrue(all((s, o) in observation.READS for s, o, _ in self.calls))

    def test_serving_flags_are_not_inferred_from_latest(self):
        def call(service, operation, *args):
            result = self.call(service, operation, *args)
            if operation == "get-function":
                variables = result["Configuration"]["Environment"]["Variables"]
                variables["FITFINITY_MEDIA_ENABLED"] = "true" if "--qualifier" in args else "false"
                if "--qualifier" in args:
                    variables["SERVING_ONLY_SECRET"] = "sensitive-marker"
            return result

        result = observation.observe(call)["runtime"]
        self.assertEqual(
            result["latest_configuration"]["feature_flags"]["FITFINITY_MEDIA_ENABLED"], "false"
        )
        self.assertEqual(
            result["serving_configuration"]["feature_flags"]["FITFINITY_MEDIA_ENABLED"], "true"
        )
        self.assertNotIn("SERVING_ONLY_SECRET", result["latest_configuration"]["environment_keys"])
        self.assertIn("SERVING_ONLY_SECRET", result["serving_configuration"]["environment_keys"])
        self.assertNotIn("sensitive-marker", json.dumps(result))

    def test_wrong_account_stops_before_resource_access(self):
        self.identity["Account"] = "000000000000"
        with self.assertRaisesRegex(RuntimeError, "Wrong AWS"):
            observation.observe(self.call)
        self.assertEqual(len(self.calls), 1)

    def test_broader_role_refused(self):
        self.identity["Arn"] = "arn:aws:sts::418638389566:assumed-role/Administrator/probe"
        with self.assertRaisesRegex(RuntimeError, "Wrong AWS"):
            observation.observe(self.call)
        self.assertEqual(len(self.calls), 1)

    def test_unstable_stack_refused(self):
        self.status = "UPDATE_IN_PROGRESS"
        with self.assertRaisesRegex(RuntimeError, "not stable"):
            observation.observe(self.call)
        self.assertEqual(len(self.calls), 2)

    def test_wrong_function_refused(self):
        self.function_arn += "-other"
        with self.assertRaisesRegex(RuntimeError, "Runtime identity"):
            observation.observe(self.call)

    def test_mutations_and_endpoint_override_never_start_process(self):
        with patch.object(observation.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "not allowed"):
                observation.aws("lambda", "update-function-code")
            with self.assertRaisesRegex(RuntimeError, "override"):
                observation.aws("sts", "get-caller-identity", "--endpoint-url", "https://wrong")
            run.assert_not_called()

    def test_cli_failure_does_not_echo_raw_sensitive_output(self):
        with patch.object(
            observation.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=1, stdout="sensitive-marker", stderr="sensitive-marker"
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Read failed") as caught:
                observation.aws("sts", "get-caller-identity")
            self.assertNotIn("sensitive-marker", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
