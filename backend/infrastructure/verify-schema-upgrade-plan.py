"""Verify portable private-upgrade scope without provider access or database writes."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

from deployment_profile import DEVELOPER, identities
from private_job_template import render
from schema_probe_iam import runtime_policy
from schema_probe_setup import prepare as prepare_access
from schema_probe_setup import write_bundle
from schema_upgrade_plan import prepare, validate_image

CLIENT = {
    **DEVELOPER,
    "account": "123456789012",
    "region": "eu-west-1",
    "github_repository": "client-example/portal",
    "github_environment": "production",
    "resource_prefix": "client-prod",
    "secret_prefix": "client/production",
    "runtime_alias": "live",
}


def runtime_source_files():
    """Bind synthetic publication evidence to the actual upgrade implementation."""
    root = Path(__file__).resolve().parents[1]
    names = [
        "release_upgrade.py",
        "release_upgrade_service.py",
        "runtime_grants.py",
        "runtime-grants.json",
    ]
    return {
        "backend/app/" + name: hashlib.sha256((root / "app" / name).read_bytes()).hexdigest()
        for name in names
    }


def binding(profile):
    account, region = profile["account"], profile["region"]
    return {
        "account": account,
        "region": region,
        "source_sha": "a" * 40,
        "image_digest": "sha256:" + "b" * 64,
        "operation_id": "c" * 32,
        "from_revision": "20260924_0006",
        "to_revision": "20261101_0052",
        "db_host": f"{profile['resource_prefix']}-db.abcdefghijk.{region}.rds.amazonaws.com",
        "db_name": "fitfinity",
        "migration_secret_arn": f"arn:aws:secretsmanager:{region}:{account}:secret:"
        + profile["secret_prefix"]
        + "/database/migration-aBc123",
        "subnet_ids": ["subnet-" + "1" * 17, "subnet-" + "2" * 17],
        "security_group_id": "sg-" + "3" * 17,
        "expires_at": 1200,
    }


class UpgradePlanTests(unittest.TestCase):
    def test_two_targets_bind_private_fixed_handler_secret_and_forward_chain(self):
        for profile in (DEVELOPER, CLIENT):
            with self.subTest(profile=profile["resource_prefix"]):
                result = prepare(binding(profile), profile=profile, source_sha="a" * 40, now=1000)
                self.assertEqual(result["decision"], "HOLD")
                self.assertEqual(result["profile_sha256"], identities(profile)["profile_sha256"])
                resources = result["template"]["Resources"]
                self.assertEqual(set(resources), {"Upgrade", "UpgradeRole", "UpgradeLogs"})
                self.assertFalse(
                    any(
                        row["Type"] in {"AWS::Lambda::Url", "AWS::Lambda::Permission"}
                        or "ApiGateway" in row["Type"]
                        for row in resources.values()
                    )
                )
                function = resources["Upgrade"]["Properties"]
                self.assertEqual(
                    function["FunctionName"], profile["resource_prefix"] + "-schema-upgrade"
                )
                self.assertIn(
                    "app.release_upgrade_service:create_app", function["ImageConfig"]["Command"]
                )
                self.assertEqual(function["ReservedConcurrentExecutions"], 1)
                env = function["Environment"]["Variables"]
                self.assertEqual(env["FITFINITY_UPGRADE_OPERATION_ID"], "c" * 32)
                self.assertEqual(env["FITFINITY_UPGRADE_FROM"], "20260924_0006")
                self.assertFalse(any(key.startswith("FITFINITY_PROBE_") for key in env))
                role = resources["UpgradeRole"]["Properties"]
                self.assertEqual(
                    role["PermissionsBoundary"], identities(profile)["upgrade_boundary"]
                )
                rules = role["Policies"][0]["PolicyDocument"]["Statement"]
                self.assertEqual(rules[0]["Resource"], binding(profile)["migration_secret_arn"])
                self.assertEqual(
                    rules[-1]["Condition"]["ArnEquals"]["lambda:SourceFunctionArn"],
                    f"arn:aws:lambda:{profile['region']}:{profile['account']}:function:"
                    + profile["resource_prefix"]
                    + "-schema-upgrade",
                )
                self.assertEqual(result["migration_chain"][-1]["revision"], "20261101_0052")
                self.assertTrue(all(len(row["sha256"]) == 64 for row in result["migration_chain"]))
                self.assertEqual(
                    result["invoke_payload"],
                    {"operation": "upgrade-existing", "operation_id": "c" * 32},
                )
        text = json.dumps(prepare(binding(CLIENT), profile=CLIENT, source_sha="a" * 40, now=1000))
        for forbidden in ("418638389566", "ap-southeast-1", "fitfinity-test"):
            self.assertNotIn(forbidden, text)

    def test_unknown_bootstrap_downgrade_and_stale_source_are_refused(self):
        for changes in (
            {"from_revision": "base"},
            {"from_revision": "20261101_0052"},
            {"to_revision": "20261024_0045"},
            {"to_revision": "head"},
            {"from_revision": "20000101_0000"},
            {"source_sha": "d" * 40},
        ):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                prepare(
                    {**binding(CLIENT), **changes}, profile=CLIENT, source_sha="a" * 40, now=1000
                )

    def test_foreign_secret_expired_intent_and_unreviewed_options_fail_closed(self):
        for changes in (
            {"migration_secret_arn": binding(DEVELOPER)["migration_secret_arn"]},
            {"account": DEVELOPER["account"]},
            {"expires_at": 1000},
            {"expires_at": 5000},
            {"expires_at": True},
            {"subnet_ids": ["subnet-" + "1" * 17] * 2},
            {"operation_id": "wrong"},
            {"command": "arbitrary Python"},
        ):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                prepare(
                    {**binding(CLIENT), **changes}, profile=CLIENT, source_sha="a" * 40, now=1000
                )

    def test_private_job_kind_cannot_select_an_arbitrary_handler_or_permission_scope(self):
        for kind in ("shell", "bootstrap", "staff", None):
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                render(binding(CLIENT), profile=CLIENT, kind=kind)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                runtime_policy(
                    binding(CLIENT)["migration_secret_arn"], profile=CLIENT, purpose=kind
                )

    def test_image_requires_every_migration_hash_and_exact_target_before_provider_reads(self):
        review = prepare(binding(CLIENT), profile=CLIENT, source_sha="a" * 40, now=1000)
        target = identities(CLIENT)
        receipt = {
            "profile_sha256": review["profile_sha256"],
            "account": CLIENT["account"],
            "region": CLIENT["region"],
            "revision": "a" * 40,
            "image_digest": binding(CLIENT)["image_digest"],
            "image_uri": target["registry"]
            + "/"
            + target["image_repository"]
            + "@"
            + binding(CLIENT)["image_digest"],
            "candidate_ready": True,
            "image_published": True,
            "scan_policy_passed": True,
            "source_files": {
                **runtime_source_files(),
                **{
                    "backend/migrations/versions/" + row["file"]: row["sha256"]
                    for row in review["migration_chain"]
                },
            },
        }
        calls = []

        def scan(service, operation, arguments):
            calls.append((service, operation, arguments))
            self.assertEqual((service, operation), ("ecr", "describe-image-scan-findings"))
            self.assertEqual(
                arguments,
                {
                    "repositoryName": "client-prod-api",
                    "imageId": {"imageDigest": "sha256:" + "b" * 64},
                },
            )
            return {
                "registryId": "123456789012",
                "repositoryName": "client-prod-api",
                "imageId": {"imageDigest": "sha256:" + "b" * 64},
                "imageScanStatus": {"status": "COMPLETE"},
                "imageScanFindings": {
                    "findingSeverityCounts": {},
                    "findings": [],
                    "imageScanCompletedAt": "1970-01-01T00:16:39+00:00",
                },
            }

        validate_image(review, receipt, scan, profile=CLIENT, source_sha="a" * 40, now=1000)
        self.assertEqual(len(calls), 1)
        for field, value in (
            ("account", DEVELOPER["account"]),
            ("revision", "d" * 40),
            ("profile_sha256", "e" * 64),
            ("image_published", False),
            ("source_files", {}),
        ):
            calls.clear()
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                validate_image(
                    review,
                    {**receipt, field: value},
                    scan,
                    profile=CLIENT,
                    source_sha="a" * 40,
                    now=1000,
                )
            self.assertEqual(calls, [])
        for path in receipt["source_files"]:
            altered = copy.deepcopy(receipt)
            altered["source_files"][path] = "0" * 64
            calls.clear()
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                validate_image(review, altered, scan, profile=CLIENT, source_sha="a" * 40, now=1000)
            self.assertEqual(calls, [])
        changed = copy.deepcopy(review)
        changed["migration_chain"][0]["sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            validate_image(changed, receipt, scan, profile=CLIENT, source_sha="a" * 40, now=1000)
        self.assertEqual(calls, [])

    def test_upgrade_access_is_separate_and_has_no_secret_read_or_staff_write_authority(self):
        for profile in (DEVELOPER, CLIENT):
            target = identities(profile)
            review = prepare_access(
                binding(profile)["migration_secret_arn"],
                vpc_id="vpc-aaaaaaaa",
                profile=profile,
                purpose="upgrade",
            )
            resources = review["template"]["Resources"]
            self.assertEqual(
                set(resources), {"RuntimeBoundary", "OperatorBoundary", "OperatorRole"}
            )
            operator = resources["OperatorRole"]["Properties"]
            self.assertEqual(
                operator["RoleName"], profile["resource_prefix"] + "-github-schema-upgrade"
            )
            self.assertEqual(operator["Policies"][0]["PolicyName"], "UpgradeLifecycle")
            self.assertEqual(
                operator["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"],
                {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    "token.actions.githubusercontent.com:sub": "repo:"
                    + profile["github_repository"]
                    + ":environment:"
                    + profile["github_environment"],
                },
            )
            rows = operator["Policies"][0]["PolicyDocument"]["Statement"]

            def statement(action, rows=rows):
                return next(
                    row
                    for row in rows
                    if action
                    in (row["Action"] if isinstance(row["Action"], list) else [row["Action"]])
                )

            function = (
                f"arn:aws:lambda:{profile['region']}:{profile['account']}:function:"
                + profile["resource_prefix"]
                + "-schema-upgrade"
            )
            self.assertEqual(statement("lambda:InvokeFunction")["Resource"], function)
            self.assertEqual(
                statement("iam:CreateRole")["Condition"],
                {"StringEquals": {"iam:PermissionsBoundary": target["upgrade_boundary"]}},
            )
            self.assertEqual(
                statement("iam:PassRole")["Resource"],
                f"arn:aws:iam::{profile['account']}:role/" + target["upgrade_runtime_role"],
            )
            actions = {
                action
                for row in rows
                for action in (
                    row["Action"] if isinstance(row["Action"], list) else [row["Action"]]
                )
            }
            for action in (
                "secretsmanager:GetSecretValue",
                "iam:AttachRolePolicy",
                "iam:PutRolePermissionsBoundary",
                "lambda:UpdateFunctionCode",
                "lambda:CreateFunctionUrlConfig",
                "cloudformation:UpdateStack",
                "rds:ModifyDBInstance",
                "s3:PutObject",
            ):
                self.assertNotIn(action, actions)
            runtime = resources["RuntimeBoundary"]["Properties"]
            self.assertEqual(
                runtime["ManagedPolicyName"],
                profile["resource_prefix"] + "-schema-upgrade-runtime-boundary",
            )
            self.assertEqual(
                runtime["PolicyDocument"]["Statement"][0]["Resource"],
                binding(profile)["migration_secret_arn"],
            )
            self.assertEqual(
                resources["OperatorBoundary"]["Properties"]["PolicyDocument"],
                operator["Policies"][0]["PolicyDocument"],
            )
            staff_rows = [
                row
                for row in rows
                if row["Resource"]
                == f"arn:aws:lambda:{profile['region']}:{profile['account']}:function:"
                + target["runtime_function"]
            ]
            self.assertEqual(len(staff_rows), 1)
            self.assertEqual(
                staff_rows[0]["Action"],
                ["lambda:GetFunction", "lambda:GetFunctionConcurrency", "lambda:ListTags"],
            )
            text = json.dumps(review["template"])
            for forbidden in (
                target["probe_name"],
                target["operator_role"],
            ):
                self.assertNotIn(forbidden, text)

    def test_upgrade_access_cannot_be_packaged_as_the_verified_probe_installer(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "not-created"
            review = prepare_access(
                binding(CLIENT)["migration_secret_arn"],
                vpc_id="vpc-aaaaaaaa",
                profile=CLIENT,
                purpose="upgrade",
            )
            with self.assertRaisesRegex(RuntimeError, "Template differs"):
                write_bundle(review, destination)
            self.assertFalse(destination.exists())
        for purpose in (None, "staff", "arbitrary"):
            with self.subTest(purpose=purpose), self.assertRaises(RuntimeError):
                prepare_access(
                    binding(CLIENT)["migration_secret_arn"],
                    vpc_id="vpc-aaaaaaaa",
                    profile=CLIENT,
                    purpose=purpose,
                )


class UpgradeExecutionTests(unittest.TestCase):
    def setUp(self):
        from schema_upgrade_execution import execute

        self.execute = execute
        self.profile = CLIENT
        self.target = identities(CLIENT)
        self.binding = binding(CLIENT)
        self.review = prepare(self.binding, profile=CLIENT, source_sha="a" * 40, now=1000)
        self.stack = (
            "arn:aws:cloudformation:eu-west-1:123456789012:stack/"
            "client-prod-schema-upgrade/synthetic"
        )
        self.tags = {
            "FitfinityOperation": "c" * 32,
            "FitfinitySource": "a" * 40,
            "FitfinityTemplate": self.review["template_sha256"],
            "FitfinityProfile": self.review["profile_sha256"],
        }
        self.image = {
            "profile_sha256": self.review["profile_sha256"],
            "account": "123456789012",
            "region": "eu-west-1",
            "revision": "a" * 40,
            "image_digest": "sha256:" + "b" * 64,
            "image_uri": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/client-prod-api@sha256:"
            + "b" * 64,
            "candidate_ready": True,
            "image_published": True,
            "scan_policy_passed": True,
            "source_files": {
                **runtime_source_files(),
                **{
                    "backend/migrations/versions/" + row["file"]: row["sha256"]
                    for row in self.review["migration_chain"]
                },
            },
        }
        self.maintenance_operation = "f" * 32
        self.marker = (
            self.maintenance_operation + ":" + "a" * 40 + ":" + self.target["profile_sha256"]
        )
        self.snapshot_tags = {
            "Application": "Fitfinity",
            "FitfinityOperation": self.maintenance_operation,
            "FitfinityProfile": self.target["profile_sha256"],
            "FitfinitySource": "a" * 40,
        }
        self.evidence = {
            "catalog": {
                "database": "fitfinity",
                "database_user": "fitfinity_migrator",
                "transaction_read_only": "on",
                "alembic_revisions": ["20260924_0006"],
                "observed_at": "1970-01-01T00:15:00+00:00",
            },
            "snapshot_arn": "arn:aws:rds:eu-west-1:123456789012:snapshot:client-prod-release-"
            + self.maintenance_operation,
        }
        self.evidence["maintenance"] = {
            "identity": {
                "profile_sha256": self.target["profile_sha256"],
                "source_sha": self.binding["source_sha"],
                "operation_id": self.maintenance_operation,
            },
            "state": "snapshot_ready",
            "snapshot_requested": True,
            "snapshot_arn": self.evidence["snapshot_arn"],
            "drained_after": 940,
        }
        self.saved, self.calls, self.overrides = [], [], {}
        self.status = "CREATE_COMPLETE"
        self.invocation = {}

    def call(self, service, operation, args):
        self.calls.append((operation, copy.deepcopy(args)))
        if operation in self.overrides:
            value = self.overrides[operation]
            if isinstance(value, Exception):
                raise value
            return copy.deepcopy(value)
        function = self.review["template"]["Resources"]["Upgrade"]["Properties"]
        role = self.review["template"]["Resources"]["UpgradeRole"]["Properties"]
        if operation == "get-caller-identity":
            return {
                "Account": "123456789012",
                "Arn": (
                    "arn:aws:sts::123456789012:assumed-role/client-prod-github-schema-upgrade/run"
                ),
            }
        if operation == "get-account-settings":
            return {"AccountLimit": {"UnreservedConcurrentExecutions": 1000}}
        if operation == "describe-db-instances":
            return {
                "DBInstances": [
                    {
                        "DBInstanceArn": "arn:aws:rds:eu-west-1:123456789012:db:client-prod-db",
                        "DBInstanceStatus": "available",
                        "DbiResourceId": "db-SYNTHETIC-IDENTITY",
                        "Endpoint": {"Address": self.binding["db_host"]},
                        "DBName": "fitfinity",
                        "StorageEncrypted": True,
                        "PubliclyAccessible": False,
                        "DBSubnetGroup": {"VpcId": "vpc-123"},
                    }
                ]
            }
        if operation == "describe-subnets":
            return {
                "Subnets": [
                    {
                        "SubnetId": subnet,
                        "VpcId": "vpc-123",
                        "OwnerId": "123456789012",
                        "State": "available",
                        "MapPublicIpOnLaunch": False,
                    }
                    for subnet in self.binding["subnet_ids"]
                ]
            }
        if operation == "describe-security-groups":
            return {"SecurityGroups": [{"VpcId": "vpc-123", "OwnerId": "123456789012"}]}
        if operation == "describe-secret":
            return {"ARN": self.binding["migration_secret_arn"]}
        if operation == "describe-image-scan-findings":
            return {
                "registryId": "123456789012",
                "repositoryName": "client-prod-api",
                "imageId": {"imageDigest": self.binding["image_digest"]},
                "imageScanStatus": {"status": "COMPLETE"},
                "imageScanFindings": {
                    "findingSeverityCounts": {},
                    "findings": [],
                    "imageScanCompletedAt": "1970-01-01T00:16:39+00:00",
                },
            }
        if operation == "describe-db-snapshots":
            return {
                "DBSnapshots": [
                    {
                        "DBSnapshotArn": self.evidence["snapshot_arn"],
                        "DBSnapshotIdentifier": "client-prod-release-" + self.maintenance_operation,
                        "DBInstanceIdentifier": "client-prod-db",
                        "DbiResourceId": "db-SYNTHETIC-IDENTITY",
                        "Status": "available",
                        "SnapshotType": "manual",
                        "Encrypted": True,
                        "Engine": "postgres",
                        "SnapshotCreateTime": "1970-01-01T00:15:50+00:00",
                        "TagList": [{"Key": k, "Value": v} for k, v in self.snapshot_tags.items()],
                    }
                ]
            }
        if operation == "create-stack":
            self.assertEqual(self.saved[-1]["state"], "create_submitted")
            return {"StackId": self.stack}
        if operation == "describe-stacks" and args.get("StackName") == "client-prod-login":
            return {
                "Stacks": [
                    {
                        "StackName": "client-prod-login",
                        "StackId": (
                            "arn:aws:cloudformation:eu-west-1:123456789012:stack/"
                            "client-prod-login/abcd"
                        ),
                        "StackStatus": "UPDATE_COMPLETE",
                    }
                ]
            }
        if operation == "describe-stacks":
            return {
                "Stacks": [
                    {
                        "StackId": self.stack,
                        "StackStatus": self.status,
                        "Tags": [{"Key": key, "Value": value} for key, value in self.tags.items()],
                    }
                ]
            }
        if operation == "get-template":
            if ":stack/client-prod-login/" in args.get("StackName", ""):
                return {
                    "TemplateBody": {
                        "Resources": {
                            "ApiFunction": {
                                "Type": "AWS::Lambda::Function",
                                "Properties": {
                                    "FunctionName": "client-prod-staff-api",
                                    "ReservedConcurrentExecutions": 0,
                                },
                            }
                        }
                    }
                }
            return {"TemplateBody": self.review["template"]}
        if operation == "get-function":
            if args["FunctionName"] == "client-prod-staff-api":
                return {
                    "Configuration": {
                        "FunctionArn": (
                            "arn:aws:lambda:eu-west-1:123456789012:function:client-prod-staff-api"
                        ),
                        "LastUpdateStatus": "Successful",
                    },
                    "Tags": {"FitfinityMaintenance": self.marker, "FitfinitySnapshot": self.marker},
                }
            config = {
                key: copy.deepcopy(function[key])
                for key in ("MemorySize", "Timeout", "Architectures", "Environment", "VpcConfig")
            }
            config.update(
                FunctionArn="arn:aws:lambda:eu-west-1:123456789012:function:client-prod-schema-upgrade",
                State="Active",
                LastUpdateStatus="Successful",
                ImageConfigResponse={"ImageConfig": function["ImageConfig"]},
                Role="arn:aws:iam::123456789012:role/client-prod-schema-upgrade-runtime",
            )
            return {
                "Configuration": config,
                "Code": {"ResolvedImageUri": self.image["image_uri"]},
                "Tags": dict(self.invocation),
            }
        if operation == "get-function-concurrency":
            return {
                "ReservedConcurrentExecutions": 0
                if args["FunctionName"] == "client-prod-staff-api"
                else 1
            }
        if operation == "describe-stack-resource":
            self.assertEqual(args["LogicalResourceId"], "UpgradeRole")
            return {
                "StackResourceDetail": {
                    "ResourceType": "AWS::IAM::Role",
                    "PhysicalResourceId": "client-prod-schema-upgrade-runtime",
                }
            }
        if operation == "get-role":
            return {
                "Role": {
                    "Arn": "arn:aws:iam::123456789012:role/client-prod-schema-upgrade-runtime",
                    "PermissionsBoundary": {"PermissionsBoundaryArn": role["PermissionsBoundary"]},
                    "AssumeRolePolicyDocument": role["AssumeRolePolicyDocument"],
                }
            }
        if operation == "list-function-url-configs":
            return {"FunctionUrlConfigs": []}
        if operation == "get-policy":
            return {"absent": True}
        if operation == "list-event-source-mappings":
            return {"EventSourceMappings": []}
        if operation == "tag-resource":
            self.assertEqual(self.saved[-1]["state"], "invoke_submitted")
            self.invocation.update(args["Tags"])
            return {}
        if operation == "invoke":
            self.assertEqual(self.saved[-1]["state"], "invoke_submitted")
            self.assertEqual(
                args["Payload"],
                '{"operation":"upgrade-existing","operation_id":"' + "c" * 32 + '"}',
            )
            payload = {
                "operation_id": "c" * 32,
                "source_sha": "a" * 40,
                "from_revision": "20260924_0006",
                "schema": "20261101_0052",
                "outcome": "upgraded",
            }
            return {"StatusCode": 200, "Payload": payload}
        if operation == "delete-stack":
            self.assertEqual(self.saved[-1]["state"], "cleanup_submitted")
            self.assertEqual(args["StackName"], self.stack)
            return {}
        raise AssertionError((service, operation, args))

    def run_mode(self, mode, prior=None, now=1000):
        return self.execute(
            mode,
            self.review,
            self.review["template_sha256"],
            "a" * 40,
            self.image,
            self.call,
            lambda value: self.saved.append(copy.deepcopy(value)),
            profile=CLIENT,
            evidence=self.evidence,
            prior=prior,
            stack_id=None if mode == "create" else self.stack,
            now=now,
        )

    def test_success_writes_intents_before_effects_and_keeps_cleanup_explicit(self):
        created = self.run_mode("create")
        checked = self.run_mode("inspect", created)
        result = self.run_mode("invoke", checked)
        self.assertEqual(result["state"], "upgraded")
        self.assertNotIn("delete-stack", [name for name, _ in self.calls])
        self.assertEqual(self.run_mode("cleanup", result, now=5000)["state"], "cleanup_submitted")
        self.status = "DELETE_COMPLETE"
        self.assertEqual(self.run_mode("cleanup-check", now=5000)["state"], "cleanup_verified")

    def test_cli_already_at_target_receipt_and_empty_tag_and_cleanup_responses(self):
        from subprocess import CompletedProcess
        from unittest.mock import patch

        from schema_probe_operator import aws

        worker_result = {
            "operation_id": "c" * 32,
            "source_sha": "a" * 40,
            "from_revision": "20260924_0006",
            "schema": "20261101_0052",
            "outcome": "already_at_target",
        }
        provider = self.call

        def cli(command, **_kwargs):
            service, action = command[1:3]
            parameters = json.loads(command[command.index("--cli-input-json") + 1])
            provider(service, action, parameters)
            stdout = ""
            if action == "invoke":
                Path(command[-1]).write_text(json.dumps(worker_result))
                stdout = '{"StatusCode":200}'
            return CompletedProcess(command, 0, stdout, "")

        def call(service, action, parameters):
            if action in {"tag-resource", "invoke", "delete-stack"}:
                return aws(service, action, parameters, profile=CLIENT, purpose="upgrade")
            return provider(service, action, parameters)

        created = self.run_mode("create")
        with (
            patch.object(self, "call", call),
            patch("schema_probe_operator.subprocess.run", side_effect=cli) as run,
        ):
            receipt = self.run_mode("invoke", created)
            self.assertEqual(receipt["state"], "already_at_target")
            self.assertEqual(receipt["result"], worker_result)
            cleanup = self.run_mode("cleanup", receipt, now=5000)
            self.assertEqual(cleanup["state"], "cleanup_submitted")
        self.assertEqual(
            [attempt.args[0][1:3] for attempt in run.call_args_list],
            [["lambda", "tag-resource"], ["lambda", "invoke"], ["cloudformation", "delete-stack"]],
        )

    def test_malformed_error_or_foreign_direct_worker_result_preserves_uncertain_intent(self):
        valid = {
            "operation_id": "c" * 32,
            "source_sha": "a" * 40,
            "from_revision": "20260924_0006",
            "schema": "20261101_0052",
            "outcome": "upgraded",
        }
        for response in (
            {"StatusCode": 202, "Payload": valid},
            {"StatusCode": 200, "FunctionError": "Unhandled", "Payload": valid},
            {"StatusCode": 200, "Payload": None},
            {"StatusCode": 200, "Payload": {"error": "migration_failed_or_uncertain"}},
            {"StatusCode": 200, "Payload": {**valid, "operation_id": "d" * 32}},
            {"StatusCode": 200, "Payload": {**valid, "source_sha": "e" * 40}},
            {"StatusCode": 200, "Payload": {**valid, "from_revision": "20260923_0005"}},
            {"StatusCode": 200, "Payload": {**valid, "schema": "20260924_0006"}},
            {"StatusCode": 200, "Payload": {**valid, "outcome": "unknown"}},
            {"StatusCode": 200, "Payload": {**valid, "error": "migration_failed_or_uncertain"}},
            {"StatusCode": 200, "Payload": {"statusCode": 200, "body": json.dumps(valid)}},
        ):
            with self.subTest(response=response):
                self.setUp()
                created = self.run_mode("create")
                self.overrides["invoke"] = response
                with self.assertRaises(RuntimeError):
                    self.run_mode("invoke", created)
                self.assertEqual(self.saved[-1]["state"], "invoke_submitted")
                inspected = self.run_mode("inspect", self.saved[-1])
                self.assertEqual(inspected["database_outcome"], "not_observed")
                with self.assertRaisesRegex(RuntimeError, "do not replay"):
                    self.run_mode("invoke", inspected)
                self.assertEqual(sum(action == "invoke" for action, _ in self.calls), 1)

    def test_lost_response_preserves_intent_and_repeated_inspection_never_allows_replay(self):
        created = self.run_mode("create")
        self.overrides["invoke"] = RuntimeError("connection interrupted")
        with self.assertRaises(RuntimeError):
            self.run_mode("invoke", created)
        uncertain = self.saved[-1]
        self.assertEqual(uncertain["state"], "invoke_submitted")
        for _ in range(2):
            uncertain = self.run_mode("inspect", uncertain)
            self.assertEqual(uncertain["invocation"], "invoke_submitted")
        with self.assertRaisesRegex(RuntimeError, "already marked"):
            self.run_mode("invoke", created)
        count = len(self.calls)
        with self.assertRaisesRegex(RuntimeError, "do not replay"):
            self.run_mode("invoke", uncertain)
        self.assertNotIn("invoke", [name for name, _ in self.calls[count:]])

    def test_wrong_actor_or_changed_review_stops_before_mutation(self):
        self.overrides["get-caller-identity"] = {
            "Account": "123456789012",
            "Arn": "arn:aws:sts::123456789012:assumed-role/client-prod-github-schema-probe/run",
        }
        with self.assertRaisesRegex(RuntimeError, "Wrong upgrade"):
            self.run_mode("create")
        self.assertEqual(self.saved, [])
        self.overrides.clear()
        self.review["template"]["Description"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "review differs"):
            self.run_mode("create")
        self.assertEqual(self.saved, [])

    def test_public_trigger_stale_catalog_or_missing_backup_refuses_invocation(self):
        created = self.run_mode("create")
        for operation, response in (
            (
                "list-function-url-configs",
                {"FunctionUrlConfigs": [{"FunctionUrl": "https://unexpected.example"}]},
            ),
            ("describe-db-snapshots", {"DBSnapshots": []}),
        ):
            self.calls.clear()
            self.overrides[operation] = response
            with self.subTest(operation=operation), self.assertRaises(RuntimeError):
                self.run_mode("invoke", created)
            self.assertNotIn("invoke", [name for name, _ in self.calls])
            self.overrides.clear()
        unreadable = self.call(
            "lambda", "get-function", {"FunctionName": "client-prod-schema-upgrade"}
        )
        unreadable["TagsError"] = {"ErrorCode": "AccessDeniedException"}
        self.overrides["get-function"] = unreadable
        with self.assertRaisesRegex(RuntimeError, "marker cannot be inspected"):
            self.run_mode("invoke", created)
        self.overrides.clear()
        self.evidence["catalog"]["alembic_revisions"] = ["wrong"]
        with self.assertRaisesRegex(RuntimeError, "catalog identity"):
            self.run_mode("invoke", created)

    def test_failed_receipt_persistence_prevents_any_cloud_write(self):
        def refuse(_receipt):
            raise OSError("receipt storage unavailable")

        with self.assertRaises(OSError):
            self.execute(
                "create",
                self.review,
                self.review["template_sha256"],
                "a" * 40,
                self.image,
                self.call,
                refuse,
                profile=CLIENT,
                now=1000,
            )
        self.assertNotIn("create-stack", [name for name, _ in self.calls])

    def test_maintenance_and_backup_metadata_must_be_live_and_exact(self):
        from schema_upgrade_execution import readiness

        original = self.call("rds", "describe-db-snapshots", {})["DBSnapshots"][0]
        for changes in (
            {"Status": "creating"},
            {"DbiResourceId": "db-REPLACED-IDENTITY"},
            {"Encrypted": False},
            {"DBInstanceIdentifier": "foreign"},
            {"DBSnapshotIdentifier": "foreign"},
            {"SourceDBSnapshotIdentifier": "old-copied-backup"},
            {"SnapshotCreateTime": "1970-01-01T00:14:00+00:00"},
            # Matching ownership and physical DB, after the catalog but still before drain.
            {"SnapshotCreateTime": "1970-01-01T00:15:39+00:00"},
            {"SnapshotCreateTime": "1970-01-01T01:00:00+00:00"},
            {"SnapshotType": "shared"},
        ):
            self.overrides["describe-db-snapshots"] = {"DBSnapshots": [{**original, **changes}]}
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                readiness(self.binding, self.evidence, self.call, profile=CLIENT, now=1000)
        self.overrides.clear()
        other_db = self.call("rds", "describe-db-instances", {})["DBInstances"][0]
        other_db["DBInstanceArn"] += "-foreign"
        self.overrides["describe-db-instances"] = {"DBInstances": [other_db]}
        with self.assertRaisesRegex(RuntimeError, "Database resource identity"):
            readiness(self.binding, self.evidence, self.call, profile=CLIENT, now=1000)
        self.overrides.clear()
        for value in (1, False, None):
            self.overrides["get-function-concurrency"] = {"ReservedConcurrentExecutions": value}
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                readiness(self.binding, self.evidence, self.call, profile=CLIENT, now=1000)
        self.overrides.clear()
        for value in (2, False, None):
            self.overrides["get-template"] = {
                "TemplateBody": {
                    "Resources": {
                        "ApiFunction": {
                            "Type": "AWS::Lambda::Function",
                            "Properties": {
                                "FunctionName": "client-prod-staff-api",
                                "ReservedConcurrentExecutions": value,
                            },
                        }
                    }
                }
            }
            with self.subTest(saved_concurrency=value), self.assertRaises(RuntimeError):
                readiness(self.binding, self.evidence, self.call, profile=CLIENT, now=1000)
        self.overrides.clear()
        readiness(self.binding, self.evidence, self.call, profile=CLIENT, now=1000)
        self.assertNotIn("invoke", [name for name, _ in self.calls])

    def test_upgrade_refuses_snapshot_outside_original_drained_maintenance(self):
        # Every candidate is encrypted, current, and belongs to the same physical database.
        # Only the snapshot taken by the active maintenance operation can fence prior writes.
        for defect in (
            "manual",
            "foreign_name",
            "untagged",
            "tag_source",
            "tag_profile",
            "tag_operation",
            "duplicate",
            "no_pause",
            "no_snapshot",
            "foreign_marker",
            "tags_unreadable",
        ):
            with self.subTest(defect=defect):
                self.setUp()
                worker_call = self.call
                if defect == "manual":
                    self.evidence["snapshot_arn"] = (
                        self.evidence["snapshot_arn"].split("-release-")[0] + "-reviewed"
                    )
                elif defect == "foreign_name":
                    self.evidence["snapshot_arn"] = self.evidence["snapshot_arn"].replace(
                        "f" * 32, "e" * 32
                    )

                def provider(service, operation, args, defect=defect, worker_call=worker_call):
                    result = worker_call(service, operation, args)
                    if operation == "describe-db-snapshots":
                        row = result["DBSnapshots"][0]
                        tags = row["TagList"]
                        if defect == "untagged":
                            row.pop("TagList")
                        elif defect == "duplicate":
                            tags.append(tags[0])
                        elif defect.startswith("tag_"):
                            key = "Fitfinity" + defect.removeprefix("tag_").title()
                            next(tag for tag in tags if tag["Key"] == key)["Value"] = "foreign"
                    if (
                        operation == "get-function"
                        and args["FunctionName"] == self.target["runtime_function"]
                    ):
                        if defect == "no_pause":
                            result["Tags"].pop("FitfinityMaintenance")
                        elif defect == "no_snapshot":
                            result["Tags"].pop("FitfinitySnapshot")
                        elif defect == "foreign_marker":
                            result["Tags"]["FitfinitySnapshot"] = "e" * 32 + self.marker[32:]
                        elif defect == "tags_unreadable":
                            result["TagsError"] = {"ErrorCode": "AccessDenied"}
                    return result

                from unittest.mock import patch

                with patch.object(self, "call", provider):
                    created = self.run_mode("create")
                    with self.assertRaises(RuntimeError):
                        self.run_mode("invoke", created)
                self.assertFalse(any(name in {"tag-resource", "invoke"} for name, _ in self.calls))

    def test_durable_journal_preserves_last_intent_and_refuses_existing_file(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from schema_upgrade_operator import Journal

        with TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            journal = Journal(path)
            journal.save({"state": "invoke_submitted", "identity": self.tags})
            self.assertEqual(json.loads(path.read_text()), journal.value)
            with self.assertRaises(FileExistsError):
                Journal(path)
            with patch("schema_upgrade_operator.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    journal.save({"state": "upgraded"})
            self.assertEqual(json.loads(path.read_text())["state"], "invoke_submitted")
            self.assertEqual(journal.value["state"], "invoke_submitted")

    def test_upgrade_installer_requires_explicit_purpose_and_binds_distinct_role(self):
        import runpy
        from pathlib import Path
        from tempfile import TemporaryDirectory

        review = prepare_access(
            self.binding["migration_secret_arn"],
            vpc_id="vpc-aaaaaaaa",
            profile=CLIENT,
            purpose="upgrade",
        )
        with TemporaryDirectory() as directory:
            output = Path(directory) / "upgrade"
            write_bundle(review, output, purpose="upgrade")
            path = output / "fitfinity-install-upgrade-iam.py"
            namespace = runpy.run_path(str(path))
            self.assertEqual(namespace["ROLE"], "client-prod-github-schema-upgrade")
            self.assertEqual(namespace["STACK"], "client-prod-schema-upgrade-access")
            self.assertEqual(namespace["POLICY_NAME"], "UpgradeLifecycle")
            self.assertEqual(namespace["TEMPLATE"], review["template"])
            self.assertFalse((output / "fitfinity-install-probe-iam.py").exists())

    def test_artifact_selection_accepts_failed_prior_intent_but_not_failed_catalog(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from schema_upgrade_artifacts import operational

        run = {
            "path": ".github/workflows/aws-schema-upgrade.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": "client-example/portal"},
            "status": "completed",
            "conclusion": "failure",
            "head_sha": "a" * 40,
            "run_attempt": 1,
        }
        with TemporaryDirectory() as directory:
            destination = Path(directory)
            (destination / "schema-upgrade-receipt.json").write_text(
                json.dumps({"state": "invoke_submitted"})
            )
            with (
                patch(
                    "schema_upgrade_artifacts.subprocess.check_output", return_value=json.dumps(run)
                ),
                patch("schema_upgrade_artifacts.subprocess.run") as download,
            ):
                self.assertEqual(
                    operational("prior", "123", destination, profile=CLIENT)["state"],
                    "invoke_submitted",
                )
                self.assertIn("fitfinity-schema-upgrade-123-1", download.call_args.args[0])
            for changes in (
                {"path": ".github/workflows/foreign.yml"},
                {"head_branch": "feature"},
                {"head_repository": {"full_name": "foreign/repository"}},
                {"status": "in_progress"},
            ):
                with (
                    patch(
                        "schema_upgrade_artifacts.subprocess.check_output",
                        return_value=json.dumps({**run, **changes}),
                    ),
                    patch("schema_upgrade_artifacts.subprocess.run") as download,
                ):
                    with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                        operational("prior", "123", destination, profile=CLIENT)
                    download.assert_not_called()
            run["path"] = ".github/workflows/aws-schema-probe.yml"
            with (
                patch(
                    "schema_upgrade_artifacts.subprocess.check_output", return_value=json.dumps(run)
                ),
                patch("schema_upgrade_artifacts.subprocess.run") as download,
            ):
                with self.assertRaises(RuntimeError):
                    operational("catalog", "123", destination, profile=CLIENT, source="a" * 40)
                download.assert_not_called()

    def test_upgrade_fetch_binds_private_catalog_to_source_target_and_packaged_sql(self):
        import os
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from schema_upgrade_artifacts import main

        source = self.binding["source_sha"]
        sql = Path(__file__).with_name("read-schema.sql").read_bytes()
        target = self.target["profile_sha256"]
        receipt = {
            "state": "observed",
            "profile_sha256": target,
            "source_sha": source,
            "receipt": {
                "source_sha": source,
                "sql_sha256": hashlib.sha256(sql).hexdigest(),
                "catalog": self.evidence["catalog"],
            },
        }
        run = {
            "path": ".github/workflows/aws-schema-probe.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": CLIENT["github_repository"]},
            "status": "completed",
            "conclusion": "success",
            "head_sha": source,
            "run_attempt": 1,
        }
        other_account = {**CLIENT, "account": "234567890123"}
        for defect in (
            None,
            "profile",
            "source",
            "embedded_source",
            "sql",
            "maintenance_workflow",
            "maintenance_failed",
            "maintenance_source",
            "maintenance_profile",
            "maintenance_state",
            "maintenance_operation",
            "maintenance_arn",
            "maintenance_drain",
            "maintenance_intent",
        ):
            with self.subTest(defect=defect), TemporaryDirectory() as directory:
                root = Path(directory)
                profile = root / "client.json"
                profile.write_text(json.dumps(CLIENT))
                catalog = copy.deepcopy(receipt)
                if defect == "profile":
                    catalog["profile_sha256"] = identities(other_account)["profile_sha256"]
                elif defect == "source":
                    catalog["source_sha"] = "e" * 40
                elif defect == "embedded_source":
                    catalog["receipt"]["source_sha"] = "e" * 40
                elif defect == "sql":
                    catalog["receipt"]["sql_sha256"] = "e" * 64
                downloaded = root / "upgrade-catalog"
                downloaded.mkdir()
                (downloaded / "schema-probe-receipt.json").write_text(json.dumps(catalog))
                backup = copy.deepcopy(self.evidence["maintenance"])
                maintenance_run = {**run, "path": ".github/workflows/aws-maintenance.yml"}
                if defect == "maintenance_workflow":
                    maintenance_run["path"] = run["path"]
                elif defect == "maintenance_failed":
                    maintenance_run["conclusion"] = "failure"
                elif defect == "maintenance_source":
                    backup["identity"]["source_sha"] = "e" * 40
                elif defect == "maintenance_profile":
                    backup["identity"]["profile_sha256"] = "e" * 64
                elif defect == "maintenance_state":
                    backup["state"] = "snapshot_submitted"
                elif defect == "maintenance_operation":
                    backup["identity"]["operation_id"] = "e" * 32
                elif defect == "maintenance_arn":
                    backup["snapshot_arn"] += "-old"
                elif defect == "maintenance_drain":
                    del backup["drained_after"]
                elif defect == "maintenance_intent":
                    backup["snapshot_requested"] = False
                backup_directory = root / "upgrade-maintenance"
                backup_directory.mkdir()
                (backup_directory / "maintenance-receipt.json").write_text(json.dumps(backup))
                evidence_path = root / "upgrade-evidence.json"
                with (
                    patch.dict(
                        os.environ,
                        {
                            "RUNNER_TEMP": directory,
                            "UPGRADE_MODE": "invoke",
                            "REVIEW_RUN": "101",
                            "IMAGE_RUN": "102",
                            "CATALOG_RUN": "103",
                            "MAINTENANCE_RUN": "104",
                            "GITHUB_SHA": source,
                            "DEPLOYMENT_PROFILE": str(profile),
                            "GITHUB_REPOSITORY": CLIENT["github_repository"],
                            "SNAPSHOT_ARN": self.evidence["snapshot_arn"],
                            "PRIOR_RUN": "",
                        },
                    ),
                    patch("schema_upgrade_artifacts.fetch", return_value=source),
                    patch(
                        "schema_upgrade_artifacts.subprocess.check_output",
                        side_effect=[json.dumps(run), json.dumps(maintenance_run)],
                    ),
                    patch("schema_upgrade_artifacts.subprocess.run"),
                ):
                    if defect is None:
                        main()
                        self.assertEqual(json.loads(evidence_path.read_text()), self.evidence)
                    else:
                        with self.assertRaises(RuntimeError):
                            main()
                        self.assertFalse(evidence_path.exists())
