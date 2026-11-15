"""Exercise probe ownership, failure boundaries and cleanup without AWS access."""

import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from schema_probe_artifacts import run_binding
from schema_probe_execution import ACCOUNT, NAME, REGION, ROLE, URI, execute
from schema_probe_operator import aws
from schema_probe_plan import prepare_review


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.sql = b"synthetic catalog"
        self.binding = dict(
            account=ACCOUNT,
            region=REGION,
            source_sha="a" * 40,
            image_digest="sha256:" + "b" * 64,
            sql_sha256=hashlib.sha256(self.sql).hexdigest(),
            db_host="fitfinity-test-db.example.ap-southeast-1.rds.amazonaws.com",
            db_name="fitfinity",
            migration_secret_arn=f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:fitfinity/test/database/migration-abcdef",
            subnet_ids=["subnet-00000001", "subnet-00000002"],
            security_group_id="sg-00000001",
            expires_at=2000,
        )
        self.review = prepare_review(self.binding, "a" * 40, self.sql, now=1000)
        self.operation = "d" * 32
        self.stack = f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{NAME}/synthetic"
        self.tags = {
            "FitfinityOperation": self.operation,
            "FitfinitySource": "a" * 40,
            "FitfinityTemplate": self.review["template_sha256"],
        }
        self.image = dict(
            account=ACCOUNT,
            region=REGION,
            revision="a" * 40,
            image_digest=self.binding["image_digest"],
            image_uri=URI + "@" + self.binding["image_digest"],
            candidate_ready=True,
            image_published=True,
            scan_policy_passed=True,
            source_files={"backend/infrastructure/read-schema.sql": self.binding["sql_sha256"]},
        )
        self.calls = []
        self.overrides = {}
        self.status = "CREATE_COMPLETE"

    def call(self, service, operation, parameters):
        self.calls.append((service, operation, copy.deepcopy(parameters)))
        if operation in self.overrides:
            value = self.overrides[operation]
            if isinstance(value, Exception):
                raise value
            return value
        props = self.review["template"]["Resources"]["Probe"]["Properties"]
        if operation == "get-account-settings":
            return {"AccountLimit": {"UnreservedConcurrentExecutions": 1000}}
        if operation == "get-caller-identity":
            return {"Account": ACCOUNT, "Arn": ROLE + "test"}
        if operation == "describe-db-instances":
            return {
                "DBInstances": [
                    {
                        "DBInstanceArn": f"arn:aws:rds:{REGION}:{ACCOUNT}:db:fitfinity-test-db",
                        "DBInstanceStatus": "available",
                        "Endpoint": {"Address": self.binding["db_host"]},
                        "DBName": "fitfinity",
                        "StorageEncrypted": True,
                        "PubliclyAccessible": False,
                        "DBSubnetGroup": {"VpcId": "vpc-test"},
                    }
                ]
            }
        if operation == "describe-subnets":
            return {
                "Subnets": [
                    {
                        "SubnetId": subnet,
                        "VpcId": "vpc-test",
                        "OwnerId": ACCOUNT,
                        "State": "available",
                        "MapPublicIpOnLaunch": False,
                    }
                    for subnet in self.binding["subnet_ids"]
                ]
            }
        if operation == "describe-security-groups":
            return {"SecurityGroups": [{"VpcId": "vpc-test", "OwnerId": ACCOUNT}]}
        if operation == "describe-secret":
            return {"ARN": self.binding["migration_secret_arn"]}
        if operation == "describe-image-scan-findings":
            return {
                "registryId": ACCOUNT,
                "repositoryName": "fitfinity-test-api",
                "imageId": {"imageDigest": self.binding["image_digest"]},
                "imageScanStatus": {"status": "COMPLETE"},
                "imageScanFindings": {
                    "findingSeverityCounts": {},
                    "findings": [],
                    "imageScanCompletedAt": datetime.fromtimestamp(999, UTC).isoformat(),
                },
            }
        if operation == "create-stack":
            return {"StackId": self.stack}
        if operation == "describe-stacks":
            return {
                "Stacks": [
                    {
                        "StackId": self.stack,
                        "StackStatus": self.status,
                        "Tags": [{"Key": k, "Value": v} for k, v in self.tags.items()],
                    }
                ]
            }
        if operation == "get-template":
            return {"TemplateBody": self.review["template"]}
        if operation == "delete-stack":
            return {}
        if operation == "get-role":
            role = self.review["template"]["Resources"]["ProbeRole"]["Properties"]
            return {
                "Role": {
                    "Arn": f"arn:aws:iam::{ACCOUNT}:role/synthetic-probe-role",
                    "PermissionsBoundary": {"PermissionsBoundaryArn": role["PermissionsBoundary"]},
                    "AssumeRolePolicyDocument": role["AssumeRolePolicyDocument"],
                }
            }
        if operation == "get-function-concurrency":
            return {"ReservedConcurrentExecutions": 1}
        if operation == "describe-stack-resource":
            return {
                "StackResourceDetail": {
                    "ResourceType": "AWS::IAM::Role",
                    "PhysicalResourceId": "synthetic-probe-role",
                }
            }
        if operation == "get-function":
            return {
                "Code": {"ResolvedImageUri": URI + "@" + self.binding["image_digest"]},
                "Configuration": {
                    "FunctionArn": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{NAME}",
                    "State": "Active",
                    "LastUpdateStatus": "Successful",
                    "Role": f"arn:aws:iam::{ACCOUNT}:role/synthetic-probe-role",
                    "Environment": props["Environment"],
                    "VpcConfig": props["VpcConfig"],
                    "Timeout": 60,
                    "MemorySize": 512,
                    "Architectures": ["x86_64"],
                    "ImageConfigResponse": {"ImageConfig": props["ImageConfig"]},
                },
            }
        if operation == "list-function-url-configs":
            return {"FunctionUrlConfigs": []}
        if operation == "get-policy":
            return {"absent": True}
        if operation == "list-event-source-mappings":
            return {"EventSourceMappings": []}
        if operation == "invoke":
            body = {
                "source_sha": "a" * 40,
                "sql_sha256": self.binding["sql_sha256"],
                "catalog": {
                    "database": "fitfinity",
                    "database_user": "fitfinity_migrator",
                    "transaction_read_only": "on",
                },
            }
            return {"StatusCode": 200, "Payload": {"statusCode": 200, "body": json.dumps(body)}}
        raise AssertionError(f"Unexpected operation {service}/{operation}")

    def run_mode(self, mode, **kwargs):
        return execute(
            mode,
            self.review,
            self.review["template_sha256"],
            "a" * 40,
            self.sql,
            self.operation,
            self.image,
            self.call,
            now=kwargs.pop("now", 1000),
            **kwargs,
        )

    def assert_no_write(self):
        self.assertFalse(
            any(op in {"create-stack", "delete-stack", "invoke"} for _, op, _ in self.calls)
        )

    def test_create_only_submits_owned_private_template(self):
        result = self.run_mode("create")
        self.assertEqual(result["state"], "create_submitted")
        args = self.calls[-1][2]
        self.assertEqual(args["ClientRequestToken"], self.operation)
        self.assertEqual(args["StackName"], NAME)
        self.assertEqual(json.loads(args["TemplateBody"]), self.review["template"])
        self.assertEqual(args["OnFailure"], "DO_NOTHING")
        self.assertEqual([op for _, op, _ in self.calls].count("create-stack"), 1)

    def test_review_drift_and_expiry_refuse_before_aws(self):
        original = copy.deepcopy(self.review)
        for change in ("template", "bindings", "expires"):
            self.review = copy.deepcopy(original)
            if change == "template":
                self.review["template"]["Description"] = "changed"
            if change == "bindings":
                self.review["bindings"]["source_sha"] = "c" * 40
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.run_mode("create", now=3000 if change == "expires" else 1000)
            self.assertEqual(self.calls, [])

    def test_wrong_account_role_refused(self):
        for identity in (
            {"Account": "000000000000", "Arn": ROLE + "x"},
            {"Account": ACCOUNT, "Arn": "owner"},
        ):
            self.overrides["get-caller-identity"] = identity
            with self.assertRaises(RuntimeError):
                self.run_mode("create")
            self.assert_no_write()

    def test_network_database_secret_failures_precede_creation(self):
        for operation in (
            "describe-db-instances",
            "describe-subnets",
            "describe-security-groups",
            "describe-secret",
        ):
            self.overrides = {operation: RuntimeError("unavailable")}
            with self.subTest(operation=operation), self.assertRaises(RuntimeError):
                self.run_mode("create")
            self.assert_no_write()

    def test_foreign_network_or_custom_kms_requires_review(self):
        for operation, value in (
            ("describe-subnets", {"Subnets": []}),
            (
                "describe-security-groups",
                {"SecurityGroups": [{"VpcId": "foreign", "OwnerId": ACCOUNT}]},
            ),
            (
                "describe-secret",
                {"ARN": self.binding["migration_secret_arn"], "KmsKeyId": "custom-key"},
            ),
        ):
            self.overrides = {operation: value}
            with self.assertRaises(RuntimeError):
                self.run_mode("create")
            self.assert_no_write()

    def test_unaccepted_image_or_scan_refuses_create_and_collect(self):
        for mode in ("create", "collect"):
            self.image["candidate_ready"] = False
            with self.assertRaises(RuntimeError):
                self.run_mode(mode)
            self.assert_no_write()
        self.image["candidate_ready"] = True
        self.overrides["describe-image-scan-findings"] = {
            "imageScanStatus": {"status": "IN_PROGRESS"}
        }
        with self.assertRaises(RuntimeError):
            self.run_mode("create")
        self.assert_no_write()

    def test_lost_create_response_does_not_retry_or_delete(self):
        self.overrides["create-stack"] = RuntimeError("lost response")
        with self.assertRaises(RuntimeError):
            self.run_mode("create")
        self.assertEqual([op for _, op, _ in self.calls].count("create-stack"), 1)
        self.assertNotIn("delete-stack", [op for _, op, _ in self.calls])

    def test_collect_invokes_exact_compact_intent_once(self):
        result = self.run_mode("collect")
        self.assertEqual(result["state"], "observed")
        self.assertEqual(result["receipt"]["catalog"]["transaction_read_only"], "on")
        self.assertEqual(self.calls[-1][2]["Payload"], '{"operation":"observe-schema"}')
        self.assertEqual([op for _, op, _ in self.calls].count("invoke"), 1)

    def test_foreign_operation_never_invoked_or_deleted(self):
        self.tags["FitfinityOperation"] = "e" * 32
        for mode in ("collect", "cleanup"):
            with self.assertRaises(RuntimeError):
                self.run_mode(mode)
            self.assert_no_write()

    def test_incomplete_stack_and_public_triggers_refuse_invocation(self):
        self.status = "CREATE_IN_PROGRESS"
        with self.assertRaises(RuntimeError):
            self.run_mode("collect")
        self.status = "CREATE_COMPLETE"
        for operation, value in (
            ("list-function-url-configs", {"FunctionUrlConfigs": [{}]}),
            ("get-policy", {"Policy": "{}"}),
            ("list-event-source-mappings", {"EventSourceMappings": [{}]}),
        ):
            self.overrides = {operation: value}
            with self.assertRaises(RuntimeError):
                self.run_mode("collect")
            self.assert_no_write()

    def test_modified_live_image_or_command_is_not_invoked(self):
        original = self.call("lambda", "get-function", {})
        for kind in ("image", "command"):
            changed = copy.deepcopy(original)
            if kind == "image":
                changed["Code"]["ResolvedImageUri"] = "foreign"
            else:
                changed["Configuration"]["ImageConfigResponse"]["ImageConfig"]["Command"] = [
                    "arbitrary"
                ]
            self.overrides["get-function"] = changed
            with self.assertRaises(RuntimeError):
                self.run_mode("collect")
            self.assert_no_write()

    def test_failed_or_misbound_result_is_not_observation(self):
        for response in (
            {"StatusCode": 200, "FunctionError": "Unhandled"},
            {"StatusCode": 200, "Payload": {"statusCode": 503}},
            {"StatusCode": 200, "Payload": {"statusCode": 200, "body": '{"source_sha":"wrong"}'}},
        ):
            self.overrides["invoke"] = response
            with self.assertRaises(RuntimeError):
                self.run_mode("collect")

    def test_cleanup_works_after_expiry_and_targets_owned_arn(self):
        self.assertEqual(self.run_mode("cleanup", now=3000)["state"], "cleanup_submitted")
        self.assertEqual(self.calls[-1][2]["StackName"], self.stack)
        self.assertNotIn("invoke", [op for _, op, _ in self.calls])

    def test_cleanup_verification_is_separate_and_uses_retained_arn(self):
        self.status = "DELETE_IN_PROGRESS"
        self.assertEqual(
            self.run_mode("cleanup-check", now=3000, stack_id=self.stack)["state"],
            "cleanup_pending",
        )
        self.status = "DELETE_COMPLETE"
        self.assertEqual(
            self.run_mode("cleanup-check", now=3000, stack_id=self.stack)["state"],
            "cleanup_verified",
        )
        self.assert_no_write()

    def test_cli_refuses_unknown_operation_and_suppresses_error_content(self):
        with self.assertRaises(RuntimeError):
            aws("secretsmanager", "get-secret-value", {})
        with patch(
            "schema_probe_operator.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stderr="sensitive-marker", stdout=""),
        ):
            with self.assertRaisesRegex(RuntimeError, "inspect owned resource") as error:
                aws("cloudformation", "create-stack", {})
            self.assertNotIn("sensitive-marker", str(error.exception))

    def test_only_exact_policy_not_found_is_absence(self):
        with patch(
            "schema_probe_operator.subprocess.run",
            return_value=SimpleNamespace(
                returncode=1,
                stderr=(
                    "An error occurred (ResourceNotFoundException) "
                    "when calling the GetPolicy operation"
                ),
                stdout="",
            ),
        ):
            self.assertEqual(aws("lambda", "get-policy", {}), {"absent": True})
        with patch(
            "schema_probe_operator.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stderr="AccessDeniedException", stdout=""),
        ):
            with self.assertRaises(RuntimeError):
                aws("lambda", "get-policy", {})

    def test_artifact_producers_require_successful_manual_main_and_exact_source(self):
        run = {
            "path": ".github/workflows/aws-image.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": "LimYouSheng/FitfinityReact"},
            "status": "completed",
            "conclusion": "success",
            "head_sha": "a" * 40,
            "run_attempt": 1,
        }
        self.assertEqual(run_binding(run, "aws-image", "a" * 40), ("a" * 40, 1))
        for key, value in (
            ("path", "other.yml"),
            ("event", "pull_request"),
            ("head_branch", "feature"),
            ("head_repository", {"full_name": "foreign/repo"}),
            ("conclusion", "failure"),
            ("status", "in_progress"),
            ("head_sha", "b" * 40),
            ("run_attempt", 0),
        ):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                run_binding({**run, key: value}, "aws-image", "a" * 40)

    def test_live_role_concurrency_and_hidden_trigger_pages_are_refused(self):
        for operation, value in (
            ("get-function-concurrency", {"ReservedConcurrentExecutions": 2}),
            ("get-role", {"Role": {"PermissionsBoundary": {}}}),
            (
                "describe-stack-resource",
                {
                    "StackResourceDetail": {
                        "ResourceType": "AWS::IAM::Role",
                        "PhysicalResourceId": "foreign",
                    }
                },
            ),
            ("list-function-url-configs", {"FunctionUrlConfigs": [], "NextMarker": "more"}),
            ("list-event-source-mappings", {"EventSourceMappings": [], "NextMarker": "more"}),
        ):
            self.overrides = {operation: value}
            with self.assertRaises(RuntimeError):
                self.run_mode("collect")
            self.assert_no_write()

    def test_account_concurrency_rejection_happens_before_creation(self):
        self.overrides["get-account-settings"] = {
            "AccountLimit": {"UnreservedConcurrentExecutions": 100}
        }
        with self.assertRaisesRegex(RuntimeError, "Account concurrency"):
            self.run_mode("create")
        self.assert_no_write()
