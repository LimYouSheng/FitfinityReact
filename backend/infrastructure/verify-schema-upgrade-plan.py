"""Verify portable private-upgrade scope without provider access or database writes."""

import copy
import json
import unittest

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
                "backend/migrations/versions/" + row["file"]: row["sha256"]
                for row in review["migration_chain"]
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
                binding(profile)["migration_secret_arn"], profile=profile, purpose="upgrade"
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
            text = json.dumps(review["template"])
            for forbidden in (
                target["runtime_function"],
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
                binding(CLIENT)["migration_secret_arn"], profile=CLIENT, purpose="upgrade"
            )
            with self.assertRaisesRegex(RuntimeError, "Template differs"):
                write_bundle(review, destination)
            self.assertFalse(destination.exists())
        for purpose in (None, "staff", "arbitrary"):
            with self.subTest(purpose=purpose), self.assertRaises(RuntimeError):
                prepare_access(
                    binding(CLIENT)["migration_secret_arn"], profile=CLIENT, purpose=purpose
                )
