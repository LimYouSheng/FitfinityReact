"""Exercise probe ownership, failure boundaries and cleanup without AWS access."""

import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deployment_profile import DEVELOPER, identities
from schema_probe_artifacts import run_binding
from schema_probe_execution import execute
from schema_probe_operator import aws
from schema_probe_plan import prepare_review

TARGET = identities(DEVELOPER)
ACCOUNT, REGION, NAME = TARGET["account"], TARGET["region"], TARGET["probe_name"]
URI = TARGET["registry"] + "/" + TARGET["image_repository"]
ROLE = f"arn:aws:sts::{ACCOUNT}:assumed-role/{TARGET['operator_role']}/"


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.profile = DEVELOPER
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
            "FitfinityProfile": self.review["profile_sha256"],
        }
        self.image = dict(
            profile_sha256=self.review["profile_sha256"],
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
        target = identities(self.profile)
        account, region, name = target["account"], target["region"], target["probe_name"]
        uri = target["registry"] + "/" + target["image_repository"]
        role_prefix = f"arn:aws:sts::{account}:assumed-role/{target['operator_role']}/"
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
            return {"Account": account, "Arn": role_prefix + "test"}
        if operation == "describe-db-instances":
            return {
                "DBInstances": [
                    {
                        "DBInstanceArn": f"arn:aws:rds:{region}:{account}:db:{target['database']}",
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
                        "OwnerId": account,
                        "State": "available",
                        "MapPublicIpOnLaunch": False,
                    }
                    for subnet in self.binding["subnet_ids"]
                ]
            }
        if operation == "describe-security-groups":
            return {"SecurityGroups": [{"VpcId": "vpc-test", "OwnerId": account}]}
        if operation == "describe-secret":
            return {"ARN": self.binding["migration_secret_arn"]}
        if operation == "describe-image-scan-findings":
            return {
                "registryId": account,
                "repositoryName": target["image_repository"],
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
                    "Arn": f"arn:aws:iam::{account}:role/synthetic-probe-role",
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
                "Code": {"ResolvedImageUri": uri + "@" + self.binding["image_digest"]},
                "Configuration": {
                    "FunctionArn": f"arn:aws:lambda:{region}:{account}:function:{name}",
                    "State": "Active",
                    "LastUpdateStatus": "Successful",
                    "Role": f"arn:aws:iam::{account}:role/synthetic-probe-role",
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
            return {"StatusCode": 200, "Payload": body}
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
            profile=self.profile,
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

    def test_cli_collect_reads_generic_event_response_body_from_lambda_output_file(self):
        payload = {
            "source_sha": "a" * 40,
            "sql_sha256": hashlib.sha256(b"synthetic catalog").hexdigest(),
            "catalog": {
                "database": "fitfinity",
                "database_user": "fitfinity_migrator",
                "transaction_read_only": "on",
                "alembic_revisions": ["20260924_0006"],
            },
        }
        provider = self.call

        def cli(command, **_kwargs):
            self.assertEqual(command[1:3], ["lambda", "invoke"])
            self.assertEqual(command[-3:-1], ["--cli-binary-format", "raw-in-base64-out"])
            Path(command[-1]).write_text(json.dumps(payload))
            return SimpleNamespace(returncode=0, stdout='{"StatusCode":200}', stderr="")

        def call(service, action, args):
            if action == "invoke":
                return aws(service, action, args, profile=self.profile)
            return provider(service, action, args)

        with (
            patch.object(self, "call", call),
            patch("schema_probe_operator.subprocess.run", side_effect=cli) as run,
        ):
            result = self.run_mode("collect")
        run.assert_called_once()
        self.assertEqual(result["state"], "observed")
        self.assertEqual(result["receipt"], payload)

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
        valid = {
            "source_sha": self.binding["source_sha"],
            "sql_sha256": self.binding["sql_sha256"],
            "catalog": {
                "database": "fitfinity",
                "database_user": "fitfinity_migrator",
                "transaction_read_only": "on",
            },
        }

        def refused(response, reason):
            with self.subTest(response=response):
                self.calls.clear()
                self.overrides["invoke"] = response
                with self.assertRaisesRegex(RuntimeError, reason):
                    self.run_mode("collect")
                self.assertEqual([op for _, op, _ in self.calls].count("invoke"), 1)

        for response in (
            {"StatusCode": 202, "Payload": valid},
            {"StatusCode": 200, "FunctionError": "Unhandled", "Payload": valid},
        ):
            refused(response, "Probe invocation failed")
        for payload in (
            None,
            {"error": "catalog_observation_failed"},
            {**valid, "source_sha": "b" * 40},
            {**valid, "sql_sha256": "b" * 64},
            {**valid, "error": "unexpected"},
            {"statusCode": 200, "body": json.dumps(valid)},
        ):
            refused({"StatusCode": 200, "Payload": payload}, "Probe result binding differs")
        for catalog in (
            [],
            {**valid["catalog"], "database": "other"},
            {**valid["catalog"], "database_user": "fitfinity_app"},
            {**valid["catalog"], "transaction_read_only": "off"},
        ):
            refused(
                {"StatusCode": 200, "Payload": {**valid, "catalog": catalog}},
                "Probe catalog identity differs",
            )

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

    def test_successful_empty_cli_writes_do_not_interrupt_upgrade_or_cleanup(self):
        for service, operation, purpose in (
            ("lambda", "tag-resource", "upgrade"),
            ("cloudformation", "delete-stack", "probe"),
            ("cloudformation", "delete-stack", "upgrade"),
        ):
            with self.subTest(operation=operation, purpose=purpose):
                for body in ("", " \n"):
                    with patch(
                        "schema_probe_operator.subprocess.run",
                        return_value=SimpleNamespace(returncode=0, stdout=body, stderr=""),
                    ) as run:
                        self.assertEqual(aws(service, operation, {}, purpose=purpose), {})
                        self.assertEqual(run.call_count, 1)
                        self.assertEqual(run.call_args.kwargs["env"]["AWS_MAX_ATTEMPTS"], "1")
                with patch(
                    "schema_probe_operator.subprocess.run",
                    return_value=SimpleNamespace(returncode=1, stdout="", stderr="private-detail"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "inspect owned resource"):
                        aws(service, operation, {}, purpose=purpose)
                with patch(
                    "schema_probe_operator.subprocess.run",
                    return_value=SimpleNamespace(returncode=0, stdout="not-json", stderr=""),
                ):
                    with self.assertRaises(json.JSONDecodeError):
                        aws(service, operation, {}, purpose=purpose)

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

    def configure_client(self):
        """Supply independent client metadata to the simulated provider."""
        self.profile = {
            "schema_version": 1,
            "account": "123456789012",
            "region": "eu-west-1",
            "github_repository": "client-example/portal",
            "github_environment": "production",
            "resource_prefix": "client-prod",
            "secret_prefix": "client/production",
            "runtime_alias": "live",
        }
        self.binding.update(
            account="123456789012",
            region="eu-west-1",
            db_host="client-prod-db.abcdef.eu-west-1.rds.amazonaws.com",
            migration_secret_arn="arn:aws:secretsmanager:eu-west-1:123456789012:secret:client/production/database/migration-abcdef",
        )
        self.review = prepare_review(
            self.binding, "a" * 40, self.sql, now=1000, profile=self.profile
        )
        self.stack = (
            "arn:aws:cloudformation:eu-west-1:123456789012:stack/"
            "client-prod-schema-observe/synthetic"
        )
        self.tags.update(
            FitfinityTemplate=self.review["template_sha256"],
            FitfinityProfile=self.review["profile_sha256"],
        )
        self.image.update(
            profile_sha256=self.review["profile_sha256"],
            account="123456789012",
            region="eu-west-1",
            image_uri="123456789012.dkr.ecr.eu-west-1.amazonaws.com/client-prod-api@"
            + self.binding["image_digest"],
        )

    def test_client_full_lifecycle_never_targets_developer_resources(self):
        self.configure_client()
        self.assertEqual(self.run_mode("create")["state"], "create_submitted")
        self.assertEqual(self.run_mode("collect")["state"], "observed")
        self.assertEqual(self.run_mode("cleanup", now=3000)["state"], "cleanup_submitted")
        self.status = "DELETE_COMPLETE"
        self.assertEqual(
            self.run_mode("cleanup-check", now=3000, stack_id=self.stack)["state"],
            "cleanup_verified",
        )
        sent = json.dumps(self.calls)
        for forbidden in ("418638389566", "ap-southeast-1", "fitfinity-test", "LimYouSheng"):
            self.assertNotIn(forbidden, sent)
        writes = [op for _, op, _ in self.calls if op in {"create-stack", "invoke", "delete-stack"}]
        self.assertEqual(writes, ["create-stack", "invoke", "delete-stack"])

    def test_review_cannot_select_its_own_account_or_repository(self):
        self.configure_client()
        self.profile = DEVELOPER
        with self.assertRaises(RuntimeError):
            self.run_mode("create")
        self.assertEqual(self.calls, [])
        self.configure_client()
        self.tags["FitfinityProfile"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "another operation"):
            self.run_mode("cleanup", now=3000)
        self.assert_no_write()

    def test_client_artifacts_reject_successful_developer_producer(self):
        self.configure_client()
        run = {
            "path": ".github/workflows/aws-image.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": "client-example/portal"},
            "status": "completed",
            "conclusion": "success",
            "head_sha": "a" * 40,
            "run_attempt": 1,
        }
        self.assertEqual(
            run_binding(run, "aws-image", "a" * 40, profile=self.profile), ("a" * 40, 1)
        )
        run["head_repository"]["full_name"] = "LimYouSheng/FitfinityReact"
        with self.assertRaises(RuntimeError):
            run_binding(run, "aws-image", "a" * 40, profile=self.profile)
