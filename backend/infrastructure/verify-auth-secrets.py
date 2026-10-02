"Offline tests for secret initialization, startup, fail-closed reruns and IAM scope."

import ast
import asyncio
import base64
import copy
import hashlib
import importlib.util
import json
import os
import sys
import types
import unittest
from contextlib import ExitStack, closing
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from image_test_fixture import image_fixture

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
ARN = "arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fitfinity/test/auth-AbCd12"


def load(test):
    spec = importlib.util.spec_from_file_location("auth_operator", ROOT / "test-auth-secrets.py")
    op = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(op)
    op = op.create_operator() if hasattr(op, "create_operator") else op
    image_root, contract = test.enterContext(image_fixture(ROOT.parent, op.MIGRATION))
    test.enterContext(patch.object(op, "MIGRATION", contract))
    runtime = types.ModuleType("auth_runtime")
    exec(compile(op.source_bundle(), "auth_runtime", "exec"), runtime.__dict__)
    runtime.ROOT = image_root
    runtime.shared.CA = image_root / "app/certificates/ap-southeast-1-bundle.pem"
    return op, runtime


class AuthChecks(unittest.TestCase):
    def setUp(self):
        self.pinned_contract = (ROOT / "test-db-migration-contract.json").read_bytes()
        self.op, self.rt = load(self)
        self.auth = {
            "cognito_pool_id": self.op.CONTRACT["pool_id"],
            "cognito_client_id": self.op.CONTRACT["client_id"],
            "cognito_client_secret": "C" * 48,
            "auth_encryption_keys": [base64.urlsafe_b64encode(b"K" * 32).decode()],
        }
        self.versions = {}
        self.stored = None
        self.sm = Mock()
        self.sm.describe_secret.side_effect = lambda **kw: self.meta()
        self.sm.get_secret_value.side_effect = self.read
        self.sm.put_secret_value.side_effect = self.put
        self.cog = Mock()
        self.cog.describe_user_pool_client.return_value = {
            "UserPoolClient": {
                "ClientId": self.op.CONTRACT["client_id"],
                "UserPoolId": self.op.CONTRACT["pool_id"],
                "ClientSecret": "C" * 48,
                "ExplicitAuthFlows": ["ALLOW_USER_PASSWORD_AUTH"],
                "EnableTokenRevocation": True,
                "RefreshTokenRotation": {"Feature": "ENABLED", "RetryGracePeriodSeconds": 0},
                "AccessTokenValidity": 5,
                "TokenValidityUnits": {"AccessToken": "minutes", "RefreshToken": "hours"},
                "RefreshTokenValidity": 8,
                "AuthSessionValidity": 5,
                "PreventUserExistenceErrors": "ENABLED",
                "WriteAttributes": ["email", "name"],
            }
        }
        self.cog.describe_user_pool.return_value = {
            "UserPool": {
                "Policies": {
                    "PasswordPolicy": {
                        "MinimumLength": 15,
                        "RequireUppercase": False,
                        "RequireLowercase": False,
                        "RequireNumbers": False,
                        "RequireSymbols": False,
                    }
                },
                "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
                "UsernameAttributes": ["email"],
                "UsernameConfiguration": {"CaseSensitive": False},
                "AccountRecoverySetting": {
                    "RecoveryMechanisms": [{"Name": "verified_email", "Priority": 1}]
                },
                "UserAttributeUpdateSettings": {
                    "AttributesRequireVerificationBeforeUpdate": ["email"]
                },
                "UserPoolTier": "ESSENTIALS",
            }
        }
        self.cog.get_user_pool_mfa_config.return_value = {
            "MfaConfiguration": "ON",
            "SoftwareTokenMfaConfiguration": {"Enabled": True},
        }
        self.clients = patch.object(
            self.rt,
            "client",
            side_effect=lambda service: closing(
                self.sm if service == "secretsmanager" else self.cog
            ),
        )
        self.clients.start()
        self.addCleanup(self.clients.stop)

    def meta(self):
        return {
            "ARN": ARN,
            "Name": "fitfinity/test/auth",
            "Tags": [{"Key": k, "Value": v} for k, v in self.op.TAGS.items()],
            "VersionIdsToStages": copy.deepcopy(self.versions),
        }

    def put(self, **kw):
        self.stored = json.loads(kw["SecretString"])
        self.versions = {kw["ClientRequestToken"]: ["AWSCURRENT"]}
        return {"ARN": ARN, "VersionId": kw["ClientRequestToken"], "VersionStages": ["AWSCURRENT"]}

    def read(self, **kw):
        if kw["SecretId"] == self.op.MIGRATION["secret_arns"]["app"]:
            return {
                "ARN": kw["SecretId"],
                "VersionStages": ["AWSCURRENT"],
                "SecretString": json.dumps({"username": "fitfinity_app", "password": "p" * 48}),
            }
        return {
            "ARN": ARN,
            "VersionId": self.rt.version_token(ARN),
            "VersionStages": ["AWSCURRENT"],
            "SecretString": json.dumps(self.stored),
        }

    def seed(self):
        self.stored = copy.deepcopy(self.auth)
        self.versions = {self.rt.version_token(ARN): ["AWSCURRENT"]}

    def event(self, action="preflight", mode="auth-initialize", **fields):
        class Request:
            async def body(inner):
                return json.dumps({"action": action, "nonce": "a" * 32, **fields}).encode()

        with ExitStack() as stack:
            stack.enter_context(
                patch.dict(
                    os.environ,
                    {
                        "FITFINITY_DB_ACCESS_MODE": mode,
                        "FITFINITY_AUTH_SECRET_ARN": ARN,
                        "FITFINITY_DATABASE_SECRET_ARN": self.op.MIGRATION["secret_arns"]["app"],
                    },
                )
            )
            for name, value in zip(
                ["getuid", "geteuid", "getgid", "getegid"], [993, 993, 990, 990], strict=True
            ):
                stack.enter_context(patch.object(os, name, return_value=value))
            return asyncio.run(self.rt.run(Request()))

    def test_native_id_preflight_checks_real_image_without_secret_calls(self):
        for mode in self.op.MODES.values():
            self.assertTrue(self.event(mode=mode)["ok"])
        self.sm.describe_secret.assert_not_called()
        self.sm.get_secret_value.assert_not_called()
        self.sm.put_secret_value.assert_not_called()
        self.assertEqual(
            (ROOT / "test-db-migration-contract.json").read_bytes(), self.pinned_contract
        )

    def test_preflight_rejects_missing_or_changed_image(self):
        for relative in ["app/config.py", "app/persistence.py"]:
            path = self.rt.ROOT / relative
            original = path.read_bytes()
            for change in ["modified", "missing"]:
                with self.subTest(file=relative, change=change):
                    try:
                        if change == "modified":
                            path.write_bytes(original + b"\n# changed after manifest capture\n")
                        else:
                            path.unlink()
                        result = self.event()
                        self.assertEqual(result["stage"], "image_files")
                        self.assertFalse(result["ok"])
                        self.sm.describe_secret.assert_not_called()
                        self.sm.get_secret_value.assert_not_called()
                        self.sm.put_secret_value.assert_not_called()
                    finally:
                        path.write_bytes(original)
        self.rt.CONTRACT["files"]["app/config.py"] = "0" * 64
        self.assertEqual(self.event()["stage"], "image_files")

    def test_preflight_rejects_changed_ca(self):
        self.rt.shared.CA_SHA256 = "0" * 64
        self.assertEqual(self.event()["stage"], "tls_bundle")

    def test_request_rejects_unknown_action_and_extra_field(self):
        for args in [{"action": "delete"}, {"extra": True}, {"nonce": "bad"}]:
            self.assertFalse(self.event(**args)["ok"])
        self.sm.describe_secret.assert_not_called()

    def test_expiry_refuses_secret_access(self):
        with patch.object(self.rt, "datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 29, 15, 59, tzinfo=UTC)
            clock.side_effect = lambda *a, **k: datetime(*a, **k)
            self.assertEqual(self.event()["stage"], "exception_window")
        self.sm.describe_secret.assert_not_called()

    def test_root_refused(self):
        class Request:
            async def body(inner):
                return json.dumps({"action": "preflight", "nonce": "a" * 32}).encode()

        with (
            patch.dict(os.environ, {"FITFINITY_DB_ACCESS_MODE": "auth-initialize"}),
            patch.object(os, "geteuid", return_value=0),
        ):
            self.assertEqual(asyncio.run(self.rt.run(Request()))["stage"], "runtime_identity")

    def test_initialize_uses_actual_settings_crypto_and_config_validator(self):
        proof = self.rt.initialize(ARN)
        self.assertTrue(proof["newly_initialized"])
        self.assertEqual(proof["cognito_checks"], 18)
        self.op.validate_proof(proof, ARN, application=False)
        self.assertEqual(len(base64.urlsafe_b64decode(self.stored["auth_encryption_keys"][0])), 32)
        self.sm.put_secret_value.assert_called_once()
        self.assertNotIn("C" * 48, json.dumps(proof))
        self.sm.close.assert_called_once()
        self.cog.close.assert_called_once()

    def test_completed_rerun_does_not_write_or_generate_key(self):
        self.seed()
        original = self.rt.secrets.token_bytes

        def nonce_only(size):
            self.assertEqual(size, 12, "Rerun must only generate an encryption-test nonce")
            return original(size)

        with patch.object(self.rt.secrets, "token_bytes", side_effect=nonce_only):
            self.assertFalse(self.rt.initialize(ARN)["newly_initialized"])
        self.sm.put_secret_value.assert_not_called()

    def test_unknown_current_or_extra_version_refused(self):
        for value in [
            {"x" * 64: ["AWSCURRENT"]},
            {self.rt.version_token(ARN): ["AWSCURRENT"], "x" * 64: []},
        ]:
            self.versions = value
            with self.assertRaises(RuntimeError):
                self.rt.initialize(ARN)
        self.sm.put_secret_value.assert_not_called()

    def test_secret_metadata_drift_refused_before_write(self):
        for changed in [
            {"ARN": ARN + "x"},
            {"RotationEnabled": True},
            {"DeletedDate": datetime.now(UTC)},
            {"KmsKeyId": "other"},
            {"Tags": []},
            {"ReplicationStatus": [{}]},
            {"OwningService": "rds"},
        ]:
            row = {**self.meta(), **changed}
            self.sm.describe_secret.side_effect = None
            self.sm.describe_secret.return_value = row
            with self.assertRaises(RuntimeError):
                self.rt.initialize(ARN)
        self.sm.put_secret_value.assert_not_called()

    def test_changed_cognito_policy_refused_before_write(self):
        self.cog.get_user_pool_mfa_config.return_value["MfaConfiguration"] = "OFF"
        with self.assertRaises(ValueError):
            self.rt.initialize(ARN)
        self.sm.put_secret_value.assert_not_called()
        self.sm.close.assert_called_once()

    def test_changed_cognito_client_refused_before_write(self):
        self.cog.describe_user_pool_client.return_value["UserPoolClient"]["ClientId"] = "wrong"
        with self.assertRaises(RuntimeError):
            self.rt.initialize(ARN)
        self.sm.put_secret_value.assert_not_called()

    def test_existing_invalid_key_and_extra_secret_fields_refused(self):
        for changed in [
            {"auth_encryption_keys": ["bad"]},
            {"extra": "bad"},
            {"cognito_pool_id": "other"},
            {"cognito_client_secret": "bad"},
            {"auth_encryption_keys": []},
        ]:
            self.seed()
            self.stored.update(changed)
            with self.assertRaises((ValueError, RuntimeError)):
                self.rt.initialize(ARN)
        self.sm.put_secret_value.assert_not_called()

    def test_existing_credential_mismatch_refused_without_repair(self):
        self.seed()
        self.stored["cognito_client_secret"] = "D" * 48
        with self.assertRaises(ValueError):
            self.rt.initialize(ARN)
        self.sm.put_secret_value.assert_not_called()

    def test_duplicate_json_field_rejected(self):
        self.seed()
        row = self.read(SecretId=ARN)
        row["SecretString"] = row["SecretString"][:-1] + ',"cognito_pool_id":"bad"}'
        self.sm.get_secret_value.side_effect = None
        self.sm.get_secret_value.return_value = row
        with self.assertRaises(ValueError):
            self.rt.initialize(ARN)

    def test_wrong_version_response_rejected(self):
        self.seed()
        row = self.read(SecretId=ARN)
        row["VersionId"] = "a" * 64
        self.sm.get_secret_value.side_effect = None
        self.sm.get_secret_value.return_value = row
        with self.assertRaises(RuntimeError):
            self.rt.initialize(ARN)

    def test_interrupted_write_rerun_verifies_committed_version(self):
        def interrupted(**kw):
            self.put(**kw)
            raise TimeoutError("simulated response loss")

        self.sm.put_secret_value.side_effect = interrupted
        with self.assertRaises(TimeoutError):
            self.rt.initialize(ARN)
        key = self.stored["auth_encryption_keys"][:]
        self.assertFalse(self.rt.initialize(ARN)["newly_initialized"])
        self.assertEqual(self.stored["auth_encryption_keys"], key)
        self.assertEqual(self.sm.put_secret_value.call_count, 1)

    def test_put_uses_fixed_version_token_and_only_current_stage(self):
        self.rt.initialize(ARN)
        kw = self.sm.put_secret_value.call_args.kwargs
        self.assertEqual(kw["ClientRequestToken"], self.rt.version_token(ARN))
        self.assertEqual(kw["VersionStages"], ["AWSCURRENT"])
        self.assertEqual(kw["SecretId"], ARN)

    def test_failure_output_does_not_echo_secret(self):
        self.sm.describe_secret.side_effect = ValueError("C" * 48)
        result = self.event(action="auth-initialize")
        self.assertEqual(result["stage"], "secret_state")
        self.assertNotIn("C" * 48, json.dumps(result))

    def test_real_sdk_clients_support_explicit_closing(self):
        import boto3
        from botocore.stub import Stubber

        real = boto3.client(
            "secretsmanager",
            region_name="ap-southeast-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
        with Stubber(real) as stub:
            stub.add_response("describe_secret", self.meta(), {"SecretId": ARN})
            with (
                patch.object(real, "close", wraps=real.close) as close,
                patch.object(self.rt.boto3, "client", return_value=real),
            ):
                self.clients.stop()
                try:
                    with self.rt.client("secretsmanager") as got:
                        self.assertFalse(self.rt.metadata(got, ARN))
                    close.assert_called_once()
                finally:
                    self.clients.start()

    def test_independent_application_uses_actual_managed_loader_and_readonly_sql(self):
        self.seed()
        t = self.op.probe_template(ARN, self.op.source_bundle())
        env = t["Resources"]["ApplicationFunction"]["Properties"]["Environment"]["Variables"]
        from app import managed_secrets

        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        transaction = Mock()
        transaction.__enter__ = Mock(return_value=None)
        transaction.__exit__ = Mock(return_value=False)
        connection.transaction.return_value = transaction

        def execute(statement, *args):
            cursor = Mock()
            if statement == "SHOW transaction_read_only":
                cursor.fetchone.return_value = ("on",)
            elif "pg_stat_ssl" in statement:
                cursor.fetchone.return_value = (
                    "fitfinity",
                    "fitfinity_app",
                    170011,
                    True,
                    "TLSv1.3",
                )
            elif "has_database_privilege" in statement:
                cursor.fetchone.return_value = (True, False, False, True, False)
            elif "SELECT version_num" in statement:
                cursor.fetchall.return_value = [("20260924_0006",)]
            elif "obj_description" in statement:
                cursor.fetchone.return_value = (
                    "fitfinity-test-schema-v1:"
                    + self.rt.CONTRACT["migration_contract_sha256"]
                    + ":"
                    + self.rt.CONTRACT["accepted_schema_sha256"],
                )
            elif statement != "SET TRANSACTION READ ONLY":
                raise AssertionError("unexpected SQL " + statement)
            return cursor

        connection.execute.side_effect = execute
        with (
            patch.dict(os.environ, env),
            patch.object(managed_secrets.boto3, "client", return_value=self.sm),
            patch.object(self.rt.shared, "connect", return_value=connection),
        ):
            result = self.rt.application_proof(ARN)
        self.op.validate_proof(result, ARN, application=True)
        connection.transaction.assert_called_once_with(force_rollback=True)
        self.sm.put_secret_value.assert_not_called()

    def test_retained_secret_starts_empty_and_has_no_values(self):
        resource = self.op.secret_template()["Resources"]["AuthenticationSecret"]
        self.assertEqual(resource["DeletionPolicy"], "Retain")
        self.assertEqual(resource["UpdateReplacePolicy"], "Retain")
        self.assertNotIn("SecretString", resource["Properties"])
        self.assertNotIn("GenerateSecretString", resource["Properties"])

    def test_initializer_and_application_iam_scopes_are_distinct(self):
        t = self.op.probe_template(ARN, self.op.source_bundle())
        for prefix in self.op.MODES:
            statements = t["Resources"][prefix + "Role"]["Properties"]["Policies"][0][
                "PolicyDocument"
            ]["Statement"]
            put = [s for s in statements if "secretsmanager:PutSecretValue" in s["Action"]]
            self.assertEqual(len(put), 1 if prefix == "Setup" else 0)
            if put:
                self.assertEqual(put[0]["Resource"], [ARN])
            read = statements[0]["Resource"]
            self.assertEqual(
                read,
                [ARN]
                + ([self.op.MIGRATION["secret_arns"]["app"]] if prefix == "Application" else []),
            )
            self.assertNotIn("cognito-idp:AdminCreateUser", json.dumps(statements))
        self.assertNotIn(self.op.db.ADMIN_ARN, json.dumps(t))
        self.assertNotIn(self.op.MIGRATION["secret_arns"]["migration"], json.dumps(t))

    def test_configuration_transport_stays_below_all_budgets(self):
        t = self.op.probe_template(ARN, self.op.source_bundle())
        self.assertEqual(len(t["Resources"]), 6)
        self.assertLess(len(self.op.source_bundle().encode()), 32768)
        for prefix in self.op.MODES:
            size = self.op.db.configuration_sizes(t["Resources"][prefix + "Function"]["Properties"])
            self.assertLess(size["modeled_update_request"] + size["provider_allowance"], 5120)

    def test_template_environment_contains_no_secret_values(self):
        t = self.op.probe_template(ARN, self.op.source_bundle())
        text = json.dumps(t)
        for forbidden in [
            "FITFINITY_COGNITO_CLIENT_SECRET",
            "FITFINITY_AUTH_ENCRYPTION_KEYS",
            "C" * 48,
        ]:
            self.assertNotIn(forbidden, text)
        self.assertEqual(
            t["Resources"]["SetupFunction"]["Properties"]["VpcConfig"]["SubnetIds"],
            [self.op.db.SUBNET_A],
        )

    def test_operator_cannot_read_or_write_secret_values(self):
        self.assertNotIn(("secretsmanager", "get-secret-value"), self.op.db.context.reads)
        self.assertNotIn(("secretsmanager", "put-secret-value"), self.op.db.context.writes)
        self.assertNotIn(("cognito-idp", "admin-create-user"), self.op.db.context.writes)

    def test_fixed_proof_refuses_false_checks_or_other_version(self):
        proof = self.rt.initialize(ARN)
        for key, value in [
            ("secret_version_id", "changed"),
            ("auth_secret_verified", False),
            ("encryption_verified", False),
            ("cognito_checks", 17),
        ]:
            with self.assertRaises(RuntimeError):
                self.op.validate_proof({**proof, key: value}, ARN, application=False)

    def test_auth_cost_includes_fourth_secret_without_changing_legacy(self):
        prices = iter(["0.025", "0.138", "0.0106", "0.096", "0.005", "0.4"])
        with (
            patch.object(self.op.db, "price", side_effect=lambda *a: {"usd": next(prices)}),
            patch.object(self.op.db, "note"),
        ):
            self.op.db.costs(20, 8, authentication=True)
        self.assertEqual(self.op.context.report["monthly_base_usd"]["after_this_step"], "34.7660")
        self.assertNotIn("later_auth_secret", self.op.context.report["monthly_base_usd"])

    def test_secret_stack_termination_protection_added_to_creation(self):
        row = {"StackId": "id", "StackStatus": "CREATE_COMPLETE"}

        def aws(service, operation, *args, **kw):
            if operation == "create-stack":
                self.assertIn("--enable-termination-protection", args)
                return {"StackId": "id"}
            return {}

        import tempfile

        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(self.op.db, "owned_stack", side_effect=[None, row]),
            patch.object(self.op.db, "stack_template", return_value={}),
            patch.object(self.op.db, "aws", side_effect=aws),
            patch.object(self.op.db, "note"),
        ):
            self.op.db.provision("auth", {}, Path(temp), protect=True)

    def test_shared_crypto_check_count_matches_source(self):
        tree = ast.parse((ROOT.parent / "app/auth/admin.py").read_text())
        check = next(
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "checks" for t in n.targets)
        )
        self.assertEqual(len(check.keys), 18)

    def test_actual_loader_runs_both_preflights_without_sdk_calls(self):
        from fastapi.testclient import TestClient

        spec = importlib.util.spec_from_file_location("auth_loader", ROOT / "test-db-loader.py")
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        source = self.op.source_bundle()
        loader.SOURCE_SHA256 = hashlib.sha256(source.encode()).hexdigest()
        original = Path.read_bytes

        def image_bytes(path):
            relative = str(path)
            if relative.startswith("/app/"):
                return original(self.rt.ROOT / relative[5:])
            return original(path)

        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, "read_bytes", image_bytes))
            sdk = stack.enter_context(
                patch.object(
                    self.rt.boto3, "client", side_effect=AssertionError("SDK in preflight")
                )
            )
            for name, value in zip(
                ["getuid", "geteuid", "getgid", "getegid"], [993, 993, 990, 990], strict=True
            ):
                stack.enter_context(patch.object(os, name, return_value=value))
            with TestClient(loader.app) as http:
                for mode in self.op.MODES.values():
                    with patch.dict(
                        os.environ,
                        {
                            "FITFINITY_DB_ACCESS_MODE": mode,
                            "FITFINITY_AUTH_SECRET_ARN": ARN,
                            "FITFINITY_DATABASE_SECRET_ARN": self.op.MIGRATION["secret_arns"][
                                "app"
                            ],
                        },
                    ):
                        result = http.post(
                            "/events",
                            json={
                                "action": "preflight",
                                "nonce": "a" * 32,
                                "bootstrap_source": source,
                            },
                        ).json()
                        self.assertTrue(result["ok"], result)
                tampered = http.post(
                    "/events",
                    json={
                        "action": "preflight",
                        "nonce": "a" * 32,
                        "bootstrap_source": source + "#change",
                    },
                ).json()
                self.assertEqual(tampered["stage"], "bootstrap_transport")
            sdk.assert_not_called()

    def flow(self, fail=None):
        op = self.op
        proof = {
            "secret_version_id": self.rt.version_token(ARN),
            "auth_secret_verified": True,
            "encryption_verified": True,
            "cognito_checks": 18,
            "newly_initialized": True,
        }
        app = {
            **proof,
            "managed_settings_verified": True,
            "database_read_only": True,
            "target_revision": "20260924_0006",
            "database": "fitfinity",
            "user": "fitfinity_app",
            "sslmode": "verify-full",
            "tls": "TLSv1.3",
            "server_version_num": 170011,
        }

        def invoke(name, mode, directory, *, preflight=False, source=None):
            if preflight:
                return {
                    "ok": True,
                    "image_files_sha256": op.db.canonical_hash(op.MIGRATION["files"]),
                }
            if fail == mode:
                raise RuntimeError("controlled failure")
            return {"proof": app if mode == "auth-app-probe" else proof}

        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["operator"]))
            for name in ["environment", "scan", "costs", "note", "verify_functions"]:
                stack.enter_context(patch.object(op.db, name))
            stack.enter_context(patch.object(op.db, "network", return_value=(20, 8)))
            for name in ["cognito_review", "credentials_review", "confirmation", "before_probe"]:
                stack.enter_context(patch.object(op, name))
            stack.enter_context(patch.object(op, "before_secret", return_value=None))
            stack.enter_context(patch.object(op, "secret_state", return_value=ARN))
            provision = stack.enter_context(
                patch.object(
                    op.db, "provision", side_effect=[{"StackId": "secret"}, {"StackId": "probe"}]
                )
            )
            stack.enter_context(
                patch.object(op.db, "owned_stack", return_value={"StackId": "secret"})
            )
            stack.enter_context(patch.object(op.db, "invoke", side_effect=invoke))
            cleanup = stack.enter_context(patch.object(op.db, "cleanup"))
            if fail:
                with self.assertRaises(RuntimeError):
                    op.main()
                cleanup.assert_not_called()
            else:
                op.main()
                cleanup.assert_called_once()
                self.assertEqual(cleanup.call_args.kwargs["name"], op.PROBE_STACK)
                self.assertEqual(cleanup.call_args.args[0], {"StackId": "probe"})
            self.assertTrue(provision.call_args_list[0].kwargs["protect"])
            self.assertEqual(provision.call_args_list[0].args[0], op.SECRET_STACK)
            return op.context.report

    def test_complete_flow_protects_secret_and_only_cleans_temporary_stack(self):
        report = self.flow()
        self.assertTrue(report["auth_secret_verified"])
        self.assertTrue(report["managed_runtime_verified"])
        self.assertFalse(report["owner_created"])
        self.assertFalse(report["app_deployed"])

    def test_initialization_failure_preserves_resources_and_uncertain_outcome(self):
        report = self.flow(fail="auth-initialize")
        self.assertFalse(report["auth_secret_verified"])
        self.assertEqual(report["initialization_status"], "unknown_until_verified")

    def test_application_failure_preserves_successful_secret_and_resources(self):
        report = self.flow(fail="auth-app-probe")
        self.assertTrue(report["auth_secret_verified"])
        self.assertFalse(report["managed_runtime_verified"])
        self.assertEqual(report["initialization_status"], "verified")

    def test_confirmation_refusal_prevents_any_write(self):
        import io

        def terminal(*args):
            return io.StringIO("wrong")

        with patch("builtins.open", side_effect=terminal):
            with self.assertRaisesRegex(RuntimeError, "Confirmation differs"):
                self.op.confirmation()
        self.assertFalse(self.op.db.context.write_allowed)
        self.assertEqual(self.op.context.report["cloud_writes"], [])

    def test_no_automatic_recovery_of_failed_probe(self):
        with patch.object(self.op.db, "owned_stack", return_value={"StackStatus": "CREATE_FAILED"}):
            with self.assertRaisesRegex(RuntimeError, "requires review"):
                self.op.before_probe({})

    def test_orphan_secret_prevents_creation(self):
        with (
            patch.object(self.op.db, "owned_stack", return_value=None),
            patch.object(self.op.db, "aws", return_value={"ARN": ARN}),
        ):
            with self.assertRaisesRegex(RuntimeError, "outside"):
                self.op.before_secret()


if __name__ == "__main__":
    unittest.main(verbosity=2)
