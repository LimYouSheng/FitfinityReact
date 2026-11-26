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
        if operation == "get-function-concurrency":
            return {"ReservedConcurrentExecutions": 2}
        if operation == "get-alias":
            return {"FunctionVersion": "2", "RevisionId": "alias-revision"}
        if operation == "describe-db-instances":
            return {
                "DBInstances": [
                    {
                        "DBInstanceIdentifier": "fitfinity-test-db",
                        "DbiResourceId": "db-exact-resource",
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
        self.assertEqual(result["runtime"]["reserved_concurrency"], 2)
        self.assertEqual(result["database"]["DbiResourceId"], "db-exact-resource")
        self.assertEqual(
            result["runtime"]["latest_configuration"]["feature_flags"]["FITFINITY_AUTH_ENABLED"],
            "true",
        )
        self.assertEqual(
            result["runtime"]["latest_configuration"]["feature_flags"]["FITFINITY_MEDIA_ENABLED"],
            "invalid",
        )
        self.assertEqual(
            result["runtime"]["latest_configuration"]["feature_flags"][
                "FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED"
            ],
            "unset",
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

    def test_client_observation_uses_profile_resources_and_alias(self):
        profile = {
            **observation.DEVELOPER,
            "account": "123456789012",
            "region": "eu-west-1",
            "github_repository": "client-example/portal",
            "github_environment": "production",
            "resource_prefix": "client-prod",
            "secret_prefix": "client/production",
            "runtime_alias": "live",
        }
        self.identity = {
            "Account": "123456789012",
            "Arn": "arn:aws:sts::123456789012:assumed-role/client-prod-github-hosting/run",
        }
        self.function_arn = "arn:aws:lambda:eu-west-1:123456789012:function:client-prod-staff-api"

        def call(service, operation, *args):
            result = self.call(service, operation, *args)
            if operation == "describe-stacks":
                result["Stacks"][0]["StackName"] = "client-prod-login"
            if operation == "describe-db-instances":
                result["DBInstances"][0]["DBInstanceIdentifier"] = "client-prod-db"
            return result

        result = observation.observe(call, profile=profile)
        self.assertEqual(result["account"], "123456789012")
        self.assertEqual(
            result["profile_sha256"], observation.identities(profile)["profile_sha256"]
        )
        self.assertIn(
            ("lambda", "get-alias", ("--function-name", "client-prod-staff-api", "--name", "live")),
            self.calls,
        )
        sent = json.dumps(self.calls)
        for forbidden in ("418638389566", "ap-southeast-1", "fitfinity-test"):
            self.assertNotIn(forbidden, sent)
        self.assertNotIn("sensitive-marker", json.dumps(result))


if __name__ == "__main__":
    unittest.main()


class ConfigurationAuditTests(unittest.TestCase):
    def test_report_is_read_only_and_never_retains_runtime_secret_values(self):
        from deployment_config_audit import READS, collect
        from deployment_profile import DEVELOPER

        calls = []

        def read(service, operation, args):
            self.assertIn((service, operation), READS)
            calls.append(operation)
            if operation == "get-caller-identity":
                return {"Account": DEVELOPER["account"]}
            if operation == "get-role":
                return {"unverified": True, "code": "NoSuchEntity"}
            if operation == "get-function-configuration":
                return {
                    "Environment": {
                        "Variables": {
                            "PASSWORD": "must-not-leak",
                            "FITFINITY_MEDIA_ENABLED": "must-not-leak",
                            "FITFINITY_AUTH_ENABLED": "true",
                        }
                    }
                }
            return {}

        report = collect(DEVELOPER, read)
        self.assertNotIn("must-not-leak", json.dumps(report))
        self.assertEqual(report["runtime"]["feature_flags"]["FITFINITY_AUTH_ENABLED"], "true")
        self.assertEqual(report["runtime"]["feature_flags"]["FITFINITY_MEDIA_ENABLED"], "invalid")
        self.assertEqual(len(report["roles"]), 7)
        self.assertFalse(report["aws_changes"])
        self.assertNotIn("get-secret-value", calls)
        with self.assertRaisesRegex(RuntimeError, "Wrong AWS account"):
            collect(DEVELOPER, lambda *_: {"Account": "000000000000"})
