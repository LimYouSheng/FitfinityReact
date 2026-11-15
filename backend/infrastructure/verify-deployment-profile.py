"""Exercise independent deployment identities and reject cross-target configuration."""

import hashlib
import json
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment_profile import (
    DEVELOPER,
    fingerprint,
    load,
    observation_policy,
    validate,
    workflow_target,
)
from schema_probe_plan import prepare_review
from schema_probe_setup import prepare, write_bundle

CLIENT = {
    "schema_version": 1,
    "account": "123456789012",
    "region": "eu-west-1",
    "github_repository": "client-example/training-portal",
    "github_environment": "production:approved",
    "resource_prefix": "customer-prod",
    "secret_prefix": "customer/production",
    "runtime_alias": "live",
}


def secret(profile):
    """Construct synthetic secret metadata for the selected test target."""
    return (
        f"arn:aws:secretsmanager:{profile['region']}:{profile['account']}:secret:"
        f"{profile['secret_prefix']}/database/migration-Ab123x"
    )


class ProfileTests(unittest.TestCase):
    def test_rejects_unknown_missing_unsafe_and_ambiguous_fields(self):
        cases = [
            {**CLIENT, "password": "never-accepted"},
            {k: v for k, v in CLIENT.items() if k != "account"},
        ]
        for key, value in [
            ("account", "*"),
            ("region", "us-gov-west-1"),
            ("schema_version", True),
            ("github_repository", "owner/*"),
            ("github_environment", "prod\nINJECT=value"),
            ("resource_prefix", "a" * 60),
            ("secret_prefix", "../secret"),
        ]:
            cases.append({**CLIENT, key: value})
        for value in cases:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                validate(value)

    def test_rejects_duplicate_json_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "target.json"
            path.write_text('{"account":"123456789012","account":"418638389566"}')
            with self.assertRaisesRegex(RuntimeError, "Duplicate"):
                load(path)

    def test_fingerprint_is_order_independent_and_binds_every_field(self):
        self.assertEqual(fingerprint(CLIENT), fingerprint(dict(reversed(list(CLIENT.items())))))
        for key, value in DEVELOPER.items():
            if value != CLIENT[key]:
                self.assertNotEqual(fingerprint(CLIENT), fingerprint({**CLIENT, key: value}))
        result = validate(CLIENT)
        result["account"] = "000000000000"
        self.assertEqual(CLIENT["account"], "123456789012")

    def test_two_targets_render_distinct_trust_and_no_developer_leak(self):
        for profile in (DEVELOPER, CLIENT):
            review = prepare(secret(profile), profile=profile)
            props = review["template"]["Resources"]["OperatorRole"]["Properties"]
            self.assertEqual(props["RoleName"], profile["resource_prefix"] + "-github-schema-probe")
            sub = props["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"]
            self.assertEqual(
                sub["token.actions.githubusercontent.com:sub"],
                "repo:"
                + profile["github_repository"]
                + ":environment:"
                + profile["github_environment"].replace(":", "%3A"),
            )
            self.assertEqual(review["profile_sha256"], fingerprint(profile))
        text = json.dumps(prepare(secret(CLIENT), profile=CLIENT))
        for forbidden in (
            "418638389566",
            "ap-southeast-1",
            "LimYouSheng",
            "fitfinity-test",
            "aws-test",
        ):
            self.assertNotIn(forbidden, text)

    def test_mixed_account_region_or_secret_namespace_is_rejected(self):
        for key in ("account", "region", "secret_prefix"):
            foreign = {**CLIENT, key: DEVELOPER[key]}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                prepare(secret(foreign), profile=CLIENT)

    def test_packaged_client_installer_uses_client_identity_only(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "bundle"
            write_bundle(prepare(secret(CLIENT), profile=CLIENT), output)
            installer = output / "fitfinity-install-probe-iam.py"
            module = runpy.run_path(str(installer))
            self.assertEqual(module["ACCOUNT"], "123456789012")
            self.assertEqual(module["REGION"], "eu-west-1")
            self.assertEqual(module["STACK"], "customer-prod-schema-probe-access")
            self.assertEqual(module["TARGET"]["profile_sha256"], fingerprint(CLIENT))
            for forbidden in (
                "418638389566",
                "ap-southeast-1",
                "LimYouSheng",
                "fitfinity-test",
                "aws-test",
            ):
                self.assertNotIn(forbidden, installer.read_text())

    def test_bundle_rejects_changed_profile_fingerprint(self):
        review = prepare(secret(CLIENT), profile=CLIENT)
        review["profile"]["account"] = "999999999999"
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, "fingerprint"):
                write_bundle(review, Path(folder) / "bundle")

    def test_developer_template_matches_verified_installed_template(self):
        # Historical installed template is independently fixed, not regenerated as the expectation.
        data = json.dumps(
            prepare(secret(DEVELOPER))["template"], sort_keys=True, separators=(",", ":")
        )
        # Secret suffix is the only difference between synthetic metadata and the installed receipt.
        data = data.replace("migration-Ab123x", "migration-HRPtjy")
        import hashlib

        self.assertEqual(
            hashlib.sha256(data.encode()).hexdigest(),
            "e8a2e59127edea9506ba27be52761106fe032ed3cf2de2257da6650b906a2ca8",
        )

    def test_client_probe_plan_binds_image_role_secret_and_review_profile(self):
        sql = b"select 1"
        binding = {
            "account": CLIENT["account"],
            "region": CLIENT["region"],
            "source_sha": "a" * 40,
            "image_digest": "sha256:" + "b" * 64,
            "sql_sha256": hashlib.sha256(sql).hexdigest(),
            "db_host": "customer-prod-db.abcdef.eu-west-1.rds.amazonaws.com",
            "db_name": "fitfinity",
            "migration_secret_arn": secret(CLIENT),
            "subnet_ids": ["subnet-11111111", "subnet-22222222"],
            "security_group_id": "sg-33333333",
            "expires_at": 1100,
        }
        result = prepare_review(binding, "a" * 40, sql, now=1000, profile=CLIENT)
        self.assertEqual(result["profile_sha256"], fingerprint(CLIENT))
        props = result["template"]["Resources"]["Probe"]["Properties"]
        self.assertEqual(
            props["Code"]["ImageUri"],
            "123456789012.dkr.ecr.eu-west-1.amazonaws.com/customer-prod-api@sha256:" + "b" * 64,
        )
        self.assertEqual(
            props["Environment"]["Variables"]["FITFINITY_AWS_ACCOUNT_ID"], "123456789012"
        )
        for forbidden in ("418638389566", "ap-southeast-1", "LimYouSheng", "fitfinity-test"):
            self.assertNotIn(forbidden, json.dumps(result))
        with self.assertRaisesRegex(RuntimeError, "target"):
            prepare_review(binding, "a" * 40, sql, now=1000, profile=DEVELOPER)

    def test_client_entry_rejects_developer_caller_before_any_write(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "bundle"
            write_bundle(prepare(secret(CLIENT), profile=CLIENT), output)
            with patch("subprocess.run") as command:
                command.return_value = subprocess.CompletedProcess(
                    [], 0, stdout='{"Account":"418638389566"}', stderr=""
                )
                with self.assertRaisesRegex(SystemExit, "Wrong AWS account"):
                    runpy.run_path(
                        str(output / "fitfinity-install-probe-iam.py"), run_name="__main__"
                    )
                command.assert_called_once()
                self.assertEqual(
                    command.call_args.args[0][:3], ["aws", "sts", "get-caller-identity"]
                )
                self.assertIn("eu-west-1", command.call_args.args[0])

    def test_bundle_rejects_template_from_another_target(self):
        review = prepare(secret(CLIENT), profile=CLIENT)
        review["template"] = prepare(secret(DEVELOPER))["template"]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "bundle"
            with self.assertRaises(RuntimeError):
                write_bundle(review, output)
            self.assertFalse(output.exists())

    def test_workflow_resolves_only_owned_checked_in_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "client.json").write_text(json.dumps(CLIENT))
            result = workflow_target("client", "client-example/training-portal", root)
            self.assertEqual(result["account"], "123456789012")
            self.assertEqual(result["environment"], "production:approved")
            self.assertEqual(result["profile"], "backend/infrastructure/targets/client.json")
            self.assertEqual(
                result["role"], "arn:aws:iam::123456789012:role/customer-prod-github-schema-probe"
            )
            for name in ("../client", "client.json", "client\nINJECT=x"):
                with self.assertRaises(RuntimeError):
                    workflow_target(name, CLIENT["github_repository"], root)
            with self.assertRaises(RuntimeError):
                workflow_target("client", "LimYouSheng/FitfinityReact", root)
            (root / "alias.json").symlink_to(root / "client.json")
            with self.assertRaises(RuntimeError):
                workflow_target("alias", CLIENT["github_repository"], root)

    def test_repository_variables_supply_client_target_without_source_file(self):
        configuration = json.dumps({"client": CLIENT})
        with tempfile.TemporaryDirectory() as folder:
            result = workflow_target(
                "client", CLIENT["github_repository"], folder, configuration=configuration
            )
            self.assertEqual(result["profile"], "env:client")
            self.assertEqual(result["profile_sha256"], fingerprint(CLIENT))
            self.assertEqual(list(Path(folder).iterdir()), [])
        with patch.dict(
            "os.environ",
            {
                "FITFINITY_DEPLOYMENT_TARGETS_JSON": configuration,
                "GITHUB_REPOSITORY": CLIENT["github_repository"],
            },
            clear=True,
        ):
            self.assertEqual(load("env:client"), CLIENT)
            with self.assertRaises(RuntimeError):
                load("env:developer")
        with (
            patch.dict(
                "os.environ",
                {
                    "FITFINITY_DEPLOYMENT_TARGETS_JSON": configuration,
                    "GITHUB_REPOSITORY": DEVELOPER["github_repository"],
                },
                clear=True,
            ),
            self.assertRaises(RuntimeError),
        ):
            load("env:client")

    def test_configured_targets_reject_duplicates_and_never_fall_back(self):
        duplicate = '{"client":' + json.dumps(CLIENT) + ',"client":' + json.dumps(CLIENT) + "}"
        for configuration in (
            duplicate,
            "{}",
            "[]",
            json.dumps({"client": {**CLIENT, "password": "x"}}),
        ):
            with self.subTest(configuration=configuration), self.assertRaises(RuntimeError):
                workflow_target("client", CLIENT["github_repository"], configuration=configuration)
        with self.assertRaises(RuntimeError):
            workflow_target("developer", DEVELOPER["github_repository"], configuration="{}")

    def test_observation_policy_has_exact_read_actions_and_client_resources(self):
        policy = observation_policy(CLIENT)
        statements = policy["Statement"]
        actions = {
            action
            for row in statements
            for action in (row["Action"] if isinstance(row["Action"], list) else [row["Action"]])
        }
        self.assertEqual(
            actions,
            {
                "sts:GetCallerIdentity",
                "cloudformation:DescribeStacks",
                "cloudformation:GetTemplate",
                "lambda:GetFunction",
                "lambda:GetAlias",
                "lambda:GetFunctionConcurrency",
                "rds:DescribeDBInstances",
            },
        )
        self.assertEqual(
            statements[1]["Resource"],
            "arn:aws:cloudformation:eu-west-1:123456789012:stack/customer-prod-login/*",
        )
        self.assertEqual(
            statements[2]["Resource"],
            [
                "arn:aws:lambda:eu-west-1:123456789012:function:customer-prod-staff-api",
                "arn:aws:lambda:eu-west-1:123456789012:function:customer-prod-staff-api:*",
            ],
        )
        self.assertEqual(
            statements[3]["Resource"], "arn:aws:rds:eu-west-1:123456789012:db:customer-prod-db"
        )
        self.assertTrue(all(row["Effect"] == "Allow" for row in statements))
