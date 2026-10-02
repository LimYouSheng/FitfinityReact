"Regression coverage for command routing, read-only audit and CI identity boundaries."

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from operator_support import load_operator

ROOT = Path(__file__).resolve().parent


class DeploymentChecks(unittest.TestCase):
    def setUp(self):
        self.op = load_operator("deploy.py")
        self.local = f"arn:aws:iam::{self.op.CONFIG['account']}:user/fitfinity-deployer"
        self.actions = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "LimYouSheng/FitfinityReact",
            "GITHUB_REF": "refs/heads/main",
            "AWS_ACCESS_KEY_ID": "offline-access",
            "AWS_SECRET_ACCESS_KEY": "offline-secret",
            "AWS_SESSION_TOKEN": "offline-session",
        }
        self.role = "arn:aws:sts::418638389566:assumed-role/fitfinity-test-github-verify/run-1"

    def identity(self, actions=False, arn=None, account="418638389566", overrides=None):
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"Account": account, "Arn": arn or (self.role if actions else self.local)}
            ),
        )
        with (
            patch.dict(
                os.environ, {**(self.actions if actions else {}), **(overrides or {})}, clear=True
            ),
            patch.object(self.op.subprocess, "run", return_value=result) as command,
        ):
            self.op.ReadOnlyAWS(actions).environment()
            return command.call_args

    def test_local_identity_uses_exact_profile_and_account(self):
        call = self.identity()
        self.assertIn("fitfinity-test", call.args[0])
        self.assertTrue(call.kwargs["env"]["AWS_IGNORE_CONFIGURED_ENDPOINT_URLS"])

    def test_wrong_account_and_local_principal_refused(self):
        for values in [
            {"account": "000000000000"},
            {"arn": "arn:aws:iam::418638389566:root"},
            {"arn": self.role},
        ]:
            with self.subTest(values=values), self.assertRaises(RuntimeError):
                self.identity(**values)

    def test_local_environment_overrides_refused_before_aws(self):
        for key in [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_CONFIG_FILE",
            "AWS_ENDPOINT_URL",
            "AWS_CA_BUNDLE",
        ]:
            with (
                self.subTest(key=key),
                patch.dict(os.environ, {key: "untrusted"}, clear=True),
                patch.object(self.op.subprocess, "run") as command,
            ):
                with self.assertRaises(RuntimeError):
                    self.op.ReadOnlyAWS().environment()
                command.assert_not_called()

    def test_actions_uses_temporary_credentials_without_local_profile(self):
        call = self.identity(actions=True)
        self.assertNotIn("--profile", call.args[0])
        self.assertEqual(call.kwargs["env"]["AWS_SESSION_TOKEN"], "offline-session")

    def test_actions_refuses_other_repository_branch_and_missing_session(self):
        for overrides in [
            {"GITHUB_ACTIONS": "false"},
            {"GITHUB_REPOSITORY": "other/repo"},
            {"GITHUB_REF": "refs/pull/4/merge"},
            {"AWS_SESSION_TOKEN": ""},
        ]:
            with self.subTest(overrides=overrides), self.assertRaises(RuntimeError):
                self.identity(actions=True, overrides=overrides)

    def test_actions_refuses_wrong_role_or_local_user(self):
        for arn in [
            self.local,
            self.role.replace("github-verify", "github-deploy"),
            self.role.replace("/run-1", "/"),
        ]:
            with self.subTest(arn=arn), self.assertRaises(RuntimeError):
                self.identity(actions=True, arn=arn)

    def test_actions_still_refuses_endpoint_config_and_role_overrides(self):
        for key in [
            "AWS_ENDPOINT_URL_STS",
            "AWS_SHARED_CREDENTIALS_FILE",
            "AWS_ROLE_ARN",
            "AWS_WEB_IDENTITY_TOKEN_FILE",
        ]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.identity(actions=True, overrides={key: "untrusted"})

    def test_mutations_secret_values_invocation_and_host_commands_refused(self):
        with patch.object(self.op.subprocess, "run") as command:
            for service, action in [
                ("cloudformation", "create-stack"),
                ("cloudformation", "update-stack"),
                ("cloudformation", "delete-stack"),
                ("secretsmanager", "get-secret-value"),
                ("secretsmanager", "put-secret-value"),
                ("lambda", "invoke"),
                ("ssm", "send-command"),
                ("ecr", "start-image-scan"),
            ]:
                with self.subTest(action=action), self.assertRaises(RuntimeError):
                    self.op.ReadOnlyAWS()(service, action)
            command.assert_not_called()

    def test_unfiltered_cognito_client_refused(self):
        with patch.object(self.op.subprocess, "run") as command:
            for args in [
                (),
                ("--query", "UserPoolClient"),
                ("--query", "UserPoolClient.ClientSecret"),
            ]:
                with self.subTest(args=args), self.assertRaises(RuntimeError):
                    self.op.ReadOnlyAWS()("cognito-idp", "describe-user-pool-client", *args)
            command.assert_not_called()

    def test_cognito_projection_never_returns_secret_field(self):
        query = self.op.client_projection()
        self.assertNotRegex(query, r"(?:\{|,)ClientSecret:")
        self.assertIn("HasClientSecret:", query)
        result = SimpleNamespace(returncode=0, stdout='{"HasClientSecret":true}')
        with patch.object(self.op.subprocess, "run", return_value=result):
            self.assertEqual(
                self.op.ReadOnlyAWS()("cognito-idp", "describe-user-pool-client", "--query", query),
                {"HasClientSecret": True},
            )

    def test_wrong_region_refused(self):
        with patch.object(self.op.subprocess, "run") as command:
            with self.assertRaises(RuntimeError):
                self.op.ReadOnlyAWS()("rds", "describe-db-instances", region="us-east-1")
            command.assert_not_called()

    def test_provider_error_redacted_not_treated_as_missing(self):
        result = SimpleNamespace(
            returncode=1, stderr="AccessDenied password=DO_NOT_PRINT", stdout=""
        )
        with patch.object(self.op.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "response suppressed") as caught:
                self.op.ReadOnlyAWS()(
                    "cloudformation", "describe-stacks", "--stack-name", "expected", missing=True
                )
            self.assertNotIn("DO_NOT_PRINT", str(caught.exception))

    def test_only_exact_missing_stack_is_accepted(self):
        result = SimpleNamespace(
            returncode=1,
            stderr="An error occurred (ValidationError): Stack with id expected does not exist",
            stdout="",
        )
        with patch.object(self.op.subprocess, "run", return_value=result):
            self.assertIsNone(
                self.op.ReadOnlyAWS()(
                    "cloudformation", "describe-stacks", "--stack-name", "expected", missing=True
                )
            )
            with self.assertRaises(RuntimeError):
                self.op.ReadOnlyAWS()(
                    "cloudformation", "describe-stacks", "--stack-name", "other", missing=True
                )

    def test_status_discloses_historical_acceptance_and_release_blockers(self):
        with patch.object(self.op.subprocess, "run") as command:
            value = self.op.status()
            self.assertFalse(value["automatic_release_ready"])
            self.assertEqual(len(value["release_blockers"]), 5)
            self.assertIn("not a live", value["source"])
            command.assert_not_called()

    def test_full_deploy_fails_before_any_cloud_action(self):
        with patch.object(self.op.subprocess, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "Full release is not ready"):
                self.op.main(["deploy"])
            command.assert_not_called()

    def test_accepted_bootstrap_stages_never_recreate_resources(self):
        with (
            patch.object(self.op.subprocess, "run") as command,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            for name, value in self.op.CONFIG["stages"].items():
                if value["kind"] == "bootstrap":
                    self.op.run_stage("bootstrap", name)
            command.assert_not_called()

    def test_recovery_cannot_run_through_release_or_unknown_stage(self):
        with patch.object(self.op.subprocess, "run") as command:
            for kind, name in [
                ("release", "database-recovery"),
                ("bootstrap", "../deploy.py"),
                ("release", None),
            ]:
                with self.subTest(name=name), self.assertRaises(RuntimeError):
                    self.op.run_stage(kind, name)
            command.assert_not_called()

    def test_explicit_recovery_routes_only_to_canonical_guarded_operator(self):
        with patch.object(self.op.subprocess, "run") as command:
            self.op.run_stage("recovery", "database-recovery")
            self.assertEqual(
                command.call_args.args[0][1:], [str(ROOT / "test-db-access.py"), "--recover"]
            )
            self.assertTrue(command.call_args.kwargs["check"])

    def test_actions_cannot_invoke_bootstrap_release_or_recovery(self):
        with patch.object(self.op.subprocess, "run") as command:
            for kind in ["bootstrap", "release", "recovery", "deploy"]:
                with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                    self.op.main([kind, "--actions"])
            command.assert_not_called()

    def test_failure_receipt_is_private_and_never_claims_runtime_success(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(self.op, "verify", side_effect=RuntimeError("metadata drift")),
        ):
            path = Path(folder) / "receipt.json"
            with self.assertRaisesRegex(RuntimeError, "metadata drift"):
                self.op.main(["verify", "--receipt", str(path)])
            value = json.loads(path.read_text())
            self.assertFalse(value["metadata_verified"])
            self.assertFalse(value["runtime_smoke_executed"])
            self.assertEqual(value["cloud_writes"], [])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_receipt_refuses_overwrite_or_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "receipt.json"
            target.write_text("original")
            link = Path(folder) / "link.json"
            link.symlink_to(target)
            for path in [target, link]:
                with self.subTest(path=path), self.assertRaises(FileExistsError):
                    self.op.save_receipt(path, {"new": True})
            self.assertEqual(target.read_text(), "original")

    def test_iam_role_has_exact_oidc_subject_and_no_mutation_or_secret_value_actions(self):
        template = json.loads((ROOT / "test-github-verification-role.json").read_text())
        properties = template["Resources"]["VerificationRole"]["Properties"]
        trust = properties["AssumeRolePolicyDocument"]["Statement"][0]
        conditions = trust["Condition"]["StringEquals"]
        self.assertEqual(conditions["token.actions.githubusercontent.com:aud"], "sts.amazonaws.com")
        self.assertEqual(
            conditions["token.actions.githubusercontent.com:sub"], {"Ref": "GitHubSubject"}
        )
        pattern = template["Parameters"]["GitHubSubject"]["AllowedPattern"]
        for subject in [
            "repo:LimYouSheng/FitfinityReact:environment:aws-test",
            "repo:LimYouSheng@123/FitfinityReact@456:environment:aws-test",
        ]:
            self.assertIsNotNone(re.fullmatch(pattern, subject))
        self.assertIsNone(re.fullmatch(pattern, "repo:LimYouSheng/FitfinityReact:*"))
        for statement in properties["Policies"][0]["PolicyDocument"]["Statement"]:
            for action in statement["Action"]:
                self.assertRegex(action.split(":")[1], r"^(Describe|Get|List)")
                self.assertNotIn(action, ["secretsmanager:GetSecretValue", "ssm:GetParameter"])

    def test_ci_and_mac_share_the_canonical_suite_without_credentials(self):
        backend = (ROOT.parent / "scripts/verify.py").read_text()
        self.assertIn("verify-infrastructure.py", backend)
        compose = (ROOT.parent / "compose.yaml").read_text().split("  infrastructure-tests:", 1)[1]
        self.assertIn("network_mode: none", compose)
        self.assertNotIn("AWS_ACCESS_KEY_ID", compose)
        for stage in self.op.CONFIG["stages"].values():
            self.assertTrue((ROOT / stage["script"]).is_file())

    def test_audit_does_not_mark_success_after_failed_prerequisite(self):
        aws = Mock()
        aws.environment.return_value = self.local
        aws.return_value = {"accountPlanType": "PAID", "accountPlanStatus": "ACTIVE"}
        report = {}
        with patch.object(self.op, "AuthenticationSecretOperator") as load:
            with self.assertRaisesRegex(RuntimeError, "account plan differs"):
                self.op.verify(report, aws)
            load.assert_not_called()
        self.assertNotIn("metadata_verified", report)

    def audit_fixture(self, scan_error=None, policy_patch=None):
        auth = load_operator("test-auth-secrets.py")
        egress = load_operator("test-egress-execute.py")
        db = auth.db
        foundation = {"StackId": db.FOUNDATION}
        egress_row = {"StackId": egress.FAILED_ARN, "StackStatus": "UPDATE_COMPLETE"}
        templates = {
            db.FOUNDATION: json.loads((ROOT / "test-foundation.json").read_text()),
            egress.FAILED_ARN: egress.TEMPLATE,
        }
        report = {"metadata_verified": False, "runtime_smoke_executed": False, "cloud_writes": []}

        def before_secret():
            report.update(
                auth_secret_has_value=True,
                auth_secret_arn=self.op.CONFIG["auth_secret"],
                auth_secret_version_id=self.op.CONFIG["auth_version"],
            )
            return {"StackId": self.op.CONFIG["auth_stack"]}

        aws = Mock()
        aws.environment.return_value = self.local
        aws.side_effect = [
            {"accountPlanType": "FREE", "accountPlanStatus": "ACTIVE"},
            {"Stacks": [foundation]},
            {
                "StackPolicyBody": json.dumps(
                    {
                        "Statement": [
                            {
                                "Effect": "Deny",
                                "Principal": "*",
                                "Resource": "LogicalResourceId/Database",
                                "Action": ["Update:Replace", "Update:Delete"],
                                **(policy_patch or {}),
                            }
                        ]
                    }
                )
            },
            {"Stacks": [egress_row]},
        ]
        with (
            patch.object(self.op, "AuthenticationSecretOperator", return_value=auth),
            patch.object(self.op, "EgressOperator", return_value=egress),
            patch.object(db, "network") as network,
            patch.object(db, "stack_template", side_effect=lambda row: templates[row["StackId"]]),
            patch.object(egress, "verify") as egress_check,
            patch.object(auth, "cognito_review") as cognito,
            patch.object(auth, "credentials_review") as credentials,
            patch.object(auth, "before_secret", side_effect=before_secret),
            patch.object(db, "scan", side_effect=scan_error) as scan,
        ):
            if policy_patch:
                with self.assertRaisesRegex(RuntimeError, "protection differs"):
                    self.op.verify(report, aws)
                network.assert_called_once()
                for check in [cognito, credentials, scan, egress_check]:
                    check.assert_not_called()
                return report
            if scan_error:
                with self.assertRaisesRegex(RuntimeError, "expired"):
                    self.op.verify(report, aws)
            else:
                self.op.verify(report, aws)
            for check in [network, cognito, credentials, scan]:
                check.assert_called_once()
            egress_check.assert_called_once_with(egress_row, check_host=False)
        return report

    def test_audit_success_requires_every_shared_check_and_claims_metadata_only(self):
        report = self.audit_fixture()
        self.assertTrue(report["metadata_verified"])
        self.assertFalse(report["runtime_smoke_executed"])
        self.assertEqual(report["cloud_writes"], [])

    def test_failed_protection_or_scan_prevents_audit_success_without_repair(self):
        report = self.audit_fixture(RuntimeError("Image exception expired"))
        self.assertFalse(report["metadata_verified"])
        self.assertEqual(report["cloud_writes"], [])
        for policy_override in [
            {"Principal": None},
            {"Condition": {}},
            {"Action": ["Update:Delete"]},
        ]:
            with self.subTest(policy_patch=policy_override):
                report = self.audit_fixture(policy_patch=policy_override)
                self.assertFalse(report["metadata_verified"])
                self.assertEqual(report["cloud_writes"], [])

    def test_operator_invocations_do_not_share_receipts_permissions_or_write_confirmation(self):
        from authentication_secrets import AuthenticationSecretOperator
        from database_access import DatabaseAccessOperator
        from database_migrations import DatabaseMigrationOperator

        first = AuthenticationSecretOperator()
        second = AuthenticationSecretOperator()
        database = DatabaseAccessOperator()
        migration = DatabaseMigrationOperator()
        first.context.report["cloud_writes"].append({"fixture": True})
        first.context.write_allowed = True
        self.assertIs(first.context, first.db.context)
        self.assertEqual(second.context.report["cloud_writes"], [])
        self.assertFalse(second.context.write_allowed)
        self.assertFalse(database.context.write_allowed)
        self.assertNotIn(("cognito-idp", "describe-user-pool"), database.context.reads)
        self.assertNotIn(("cognito-idp", "describe-user-pool"), migration.context.reads)
        self.assertNotIn(("cloudformation", "update-stack"), migration.context.writes)

    def test_injected_transport_retains_scope_confirmation_and_recovery_guards(self):
        from database_access import DatabaseAccessOperator
        from egress_preflight import EgressPreflightOperator

        transport = Mock()
        database = DatabaseAccessOperator(aws_call=transport)
        with self.assertRaisesRegex(RuntimeError, "before execution confirmation"):
            database.aws("cloudformation", "create-stack")
        with self.assertRaisesRegex(RuntimeError, "outside this operator"):
            database.aws("secretsmanager", "get-secret-value")
        database.context.write_allowed = True
        database.context.report["recovery_only"] = True
        with self.assertRaisesRegex(RuntimeError, "restricted to the reviewed"):
            database.aws("cloudformation", "rollback-stack", "--stack-name", "unrelated")
        preflight = EgressPreflightOperator(aws_call=transport)
        with self.assertRaisesRegex(RuntimeError, "Only the public"):
            preflight.aws("ssm", "get-parameter", "--name", "private-secret")
        transport.assert_not_called()
        self.assertEqual(database.context.report["cloud_writes"], [])

    def test_nested_operators_keep_receipt_defaults_and_share_only_the_transport(self):
        from private_egress import PrivateEgressOperator

        calls = []

        def transport(service, operation, *args, region=None, missing=False):
            calls.append((service, operation, region, missing))
            return {}

        private = PrivateEgressOperator(aws_call=transport)
        self.assertFalse(private.context.report["cleanup_complete"])
        self.assertFalse(private.e.context.report["egress_configuration_verified"])
        self.assertTrue(private.e.pf.context.report["read_only"])
        self.assertIsNot(private.context.report, private.e.context.report)
        self.assertIsNot(private.e.context.report, private.e.pf.context.report)
        private.e.aws("cloudformation", "describe-stacks", missing_stack=True)
        private.e.pf.aws("sts", "get-caller-identity")
        self.assertEqual(
            calls,
            [
                ("cloudformation", "describe-stacks", private.REGION, True),
                ("sts", "get-caller-identity", private.REGION, False),
            ],
        )

    def test_audit_receipt_is_owned_by_caller_and_injected_client_reaches_database(self):
        from authentication_secrets import AuthenticationSecretOperator
        from operator_context import OperatorContext

        report = {"cloud_writes": [], "metadata_verified": False}
        transport = Mock(return_value={"Account": self.op.CONFIG["account"]})
        auth = AuthenticationSecretOperator(
            context=OperatorContext(report=report, aws_call=transport)
        )
        self.assertIs(auth.context.report, report)
        self.assertIs(auth.db.context.report, report)
        self.assertEqual(set(report), {"cloud_writes", "metadata_verified"})
        self.assertEqual(auth.db.aws("sts", "get-caller-identity"), transport.return_value)
        transport.assert_called_once_with(
            "sts", "get-caller-identity", region=auth.db.REGION, missing=False
        )
        self.assertFalse(report["metadata_verified"])
