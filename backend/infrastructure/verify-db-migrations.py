"Focused offline migration-operator checks. Never contacts AWS or a deployment DB."

import asyncio
import hashlib
import importlib.util
import io
import json
import os
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from image_test_fixture import image_fixture

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))


def load_operator():
    spec = importlib.util.spec_from_file_location(
        "migration_operator", ROOT / "test-db-migrations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module = module.create_operator() if hasattr(module, "create_operator") else module
    return module


def load_runtime(operator, image_root):
    module = types.ModuleType("migration_runtime")
    exec(compile(operator.source_bundle(), "migration_bundle", "exec"), module.__dict__)
    module.ROOT = image_root
    module.shared.CA = image_root / "app/certificates/ap-southeast-1-bundle.pem"
    return module


class Request:
    def __init__(self, value):
        self.value = json.dumps(value).encode()

    async def body(self):
        return self.value


class RuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.op = load_operator()
        self.pinned_contract = self.op.contract()
        self.image_root, contract = self.enterContext(
            image_fixture(ROOT.parent, self.pinned_contract)
        )
        self.enterContext(patch.object(self.op, "contract", return_value=contract))
        self.runtime = load_runtime(self.op, self.image_root)
        self.nonce = "a" * 32
        self.ids = (10001,) * 4
        self.env = {
            "FITFINITY_DB_ACCESS_MODE": "migrate",
            "FITFINITY_MIGRATION_DB_SECRET_ARN": self.op.contract()["secret_arns"]["migration"],
        }

    def run_event(self, action="preflight", **fields):
        request = Request({"action": action, "nonce": self.nonce, **fields})
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, self.env))
            for key, value in zip(
                ["getuid", "geteuid", "getgid", "getegid"], self.ids, strict=True
            ):
                stack.enter_context(patch.object(os, key, return_value=value))
            return asyncio.run(self.runtime.run(request))

    def test_root_mixed_and_unknown_runtime_ids_refused(self):
        for ids in [(0, 0, 0, 0), (10001, 0, 10001, 10001), (993, 993, 10001, 10001), (42,) * 4]:
            with self.subTest(ids=ids):
                self.ids = ids
                self.assertEqual(self.run_event()["stage"], "runtime_identity")

    def test_native_lambda_identity_accepted(self):
        self.ids = (993, 993, 990, 990)
        self.assertTrue(self.run_event()["ok"])

    def test_catalog_like_patterns_are_not_bound_parameters(self):
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = [("public",)]
        statement = "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%'"
        self.assertEqual(self.runtime.read_rows(connection, statement), [("public",)])
        connection.execute.assert_called_once_with(statement)

    def test_bound_catalog_parameters_are_preserved(self):
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = []
        self.runtime.read_rows(connection, "SELECT %s", ("sentinel",))
        connection.execute.assert_called_once_with("SELECT %s", ("sentinel",))

    def test_preflight_checks_real_files_without_sdk_or_sql(self):
        with (
            patch.object(self.runtime.boto3, "client") as sdk,
            patch.object(self.runtime.shared, "connect") as sql,
        ):
            result = self.run_event()
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["migration_files_sha256"], self.op.db.canonical_hash(self.op.contract()["files"])
        )
        sdk.assert_not_called()
        sql.assert_not_called()
        self.assertEqual(load_operator().contract(), self.pinned_contract)

    def test_app_preflight_uses_only_app_reference(self):
        self.env = {
            "FITFINITY_DB_ACCESS_MODE": "migration-app-probe",
            "FITFINITY_APP_DB_SECRET_ARN": self.op.contract()["secret_arns"]["app"],
        }
        self.assertTrue(self.run_event()["ok"])

    def test_changed_migration_file_rejected(self):
        for relative in ["migrations/env.py", "app/persistence.py"]:
            path = self.image_root / relative
            original = path.read_bytes()
            for change in ["modified", "missing"]:
                with self.subTest(file=relative, change=change):
                    try:
                        if change == "modified":
                            path.write_bytes(original + b"\n# changed after manifest capture\n")
                        else:
                            path.unlink()
                        with (
                            patch.object(self.runtime.boto3, "client") as sdk,
                            patch.object(self.runtime.shared, "connect") as sql,
                        ):
                            result = self.run_event()
                        self.assertEqual(result["stage"], "image_migrations")
                        self.assertFalse(result["ok"])
                        sdk.assert_not_called()
                        sql.assert_not_called()
                    finally:
                        path.write_bytes(original)
        self.runtime.CONTRACT["files"]["migrations/env.py"] = "0" * 64
        result = self.run_event()
        self.assertEqual(result["stage"], "image_migrations")
        self.assertFalse(result["ok"])

    def test_unknown_action_rejected_before_sdk(self):
        for action in ["setup", "database-diagnostic", "drop", "migration-app-probe"]:
            with self.subTest(action=action):
                self.assertEqual(self.run_event(action)["stage"], "request_schema")

    def test_extra_request_fields_refused(self):
        self.assertEqual(self.run_event(sql="DROP DATABASE fitfinity")["stage"], "request_schema")

    def test_invalid_nonce_refused(self):
        self.nonce = "bad"
        self.assertEqual(self.run_event()["stage"], "request_schema")

    def test_unknown_mode_refused(self):
        self.env["FITFINITY_DB_ACCESS_MODE"] = "setup"
        self.assertEqual(self.run_event()["stage"], "request_schema")

    def test_wrong_secret_suffix_refused(self):
        self.env["FITFINITY_MIGRATION_DB_SECRET_ARN"] = (
            self.env["FITFINITY_MIGRATION_DB_SECRET_ARN"][:-1] + "X"
        )
        self.assertEqual(self.run_event()["stage"], "secret_reference")

    def test_expired_image_exception_refused(self):
        clock = Mock(wraps=self.runtime.datetime)
        clock.now.return_value = self.runtime.datetime(2026, 9, 30, tzinfo=self.runtime.UTC)
        with patch.object(self.runtime, "datetime", clock):
            self.assertEqual(self.run_event()["stage"], "exception_window")

    def test_ca_drift_refused(self):
        with patch.object(self.runtime.shared, "CA_SHA256", "0" * 64):
            self.assertEqual(self.run_event()["stage"], "tls_bundle")

    def test_secret_client_closes_before_migration(self):
        self.sdk_scope("migrate")

    def test_secret_client_closes_before_app_proof(self):
        self.sdk_scope("migration-app-probe")

    def sdk_scope(self, mode):
        import boto3
        from botocore.stub import Stubber

        key = "migration" if mode == "migrate" else "app"
        username = "fitfinity_migrator" if key == "migration" else "fitfinity_app"
        arn = self.op.contract()["secret_arns"][key]
        self.env = {
            "FITFINITY_DB_ACCESS_MODE": mode,
            "FITFINITY_MIGRATION_DB_SECRET_ARN"
            if key == "migration"
            else "FITFINITY_APP_DB_SECRET_ARN": arn,
        }
        client = boto3.client(
            "secretsmanager",
            region_name="ap-southeast-1",
            aws_access_key_id="offline",
            aws_secret_access_key="offline",
        )
        stubber = Stubber(client)
        password = "offline-test-only-" * 3
        stubber.add_response(
            "get_secret_value",
            {
                "ARN": arn,
                "VersionStages": ["AWSCURRENT"],
                "SecretString": json.dumps({"username": username, "password": password}),
            },
            {"SecretId": arn, "VersionStage": "AWSCURRENT"},
        )
        with (
            stubber,
            patch.object(self.runtime.boto3, "client", return_value=client),
            patch.object(client, "close", wraps=client.close) as close,
        ):

            def proof(value, reference):
                self.assertTrue(close.called)
                self.assertEqual(value, {"username": username, "password": password})
                self.assertEqual(reference, arn)
                return {"verified": True}

            method = "migrate" if key == "migration" else "application_proof"
            with patch.object(self.runtime, method, side_effect=proof):
                result = self.run_event(mode)
            stubber.assert_no_pending_responses()
            self.assertTrue(result["ok"])
            self.assertNotIn(password, json.dumps(result))

    def test_secret_error_redacted_and_client_closed(self):
        client = Mock()
        client.get_secret_value.side_effect = RuntimeError("private-password-sentinel")
        with patch.object(self.runtime.boto3, "client", return_value=client):
            result = self.run_event("migrate")
        self.assertFalse(result["ok"])
        client.close.assert_called_once()
        self.assertNotIn("private-password", json.dumps(result))

    def test_partial_schema_refused(self):
        c = Mock()
        c.execute.return_value.fetchall.return_value = [("20260921_0005",)]
        with patch.object(self.runtime, "relations", return_value=[("public", "alembic_version")]):
            with self.assertRaisesRegex(RuntimeError, "unexpected migration"):
                self.runtime.current_state(c)

    def test_unversioned_schema_refused(self):
        with patch.object(self.runtime, "relations", return_value=[("public", "staff_users")]):
            with self.assertRaisesRegex(RuntimeError, "unversioned"):
                self.runtime.current_state(Mock())

    def test_empty_baseline_runs_existing_guard(self):
        with (
            patch.object(self.runtime, "relations", return_value=[]),
            patch.object(self.runtime.shared, "assert_unmigrated") as guard,
        ):
            self.assertEqual(self.runtime.current_state(Mock()), "empty")
            guard.assert_called_once()

    def test_fingerprint_mismatch_refused_without_repair(self):
        c = Mock()
        c.execute.return_value.fetchone.return_value = ("changed",)
        with patch.object(self.runtime, "fingerprint", return_value="expected"):
            with self.assertRaisesRegex(RuntimeError, "fingerprint"):
                self.runtime.proof_marker(c, create=False)
        self.assertEqual(c.execute.call_count, 1)


class OperatorChecks(unittest.TestCase):
    def setUp(self):
        self.op = load_operator()

    def test_template_has_only_six_private_resources(self):
        t = self.op.template(self.op.contract()["secret_arns"], self.op.source_bundle())
        self.assertEqual(len(t["Resources"]), 6)
        self.assertEqual(
            {r["Type"] for r in t["Resources"].values()},
            {"AWS::Lambda::Function", "AWS::IAM::Role", "AWS::Logs::LogGroup"},
        )

    def test_roles_have_only_their_own_secret(self):
        t = self.op.template(self.op.contract()["secret_arns"], self.op.source_bundle())
        for prefix, suffix in [("Setup", "migration"), ("Application", "app")]:
            policy = t["Resources"][prefix + "Role"]["Properties"]["Policies"][0]["PolicyDocument"]
            self.assertEqual(
                policy["Statement"][0]["Resource"], [self.op.contract()["secret_arns"][suffix]]
            )
            self.assertNotIn(self.op.db.ADMIN_ARN, json.dumps(policy))
            self.assertEqual(policy["Statement"][0]["Action"], ["secretsmanager:GetSecretValue"])

    def test_source_and_config_stay_within_native_limits(self):
        source = self.op.source_bundle()
        self.assertLess(len(source.encode()), 32768)
        self.assertLess(len(json.dumps({"bootstrap_source": source}).encode()), 49152)
        t = self.op.template(self.op.contract()["secret_arns"], source)
        for prefix in self.op.MODES:
            size = self.op.db.configuration_sizes(t["Resources"][prefix + "Function"]["Properties"])
            self.assertLess(size["modeled_update_request"] + 1024, 5120)

    def test_migration_metadata_and_seed_are_read_only(self):
        for name in ["alembic_version", "assessment_form_versions"]:
            self.assertEqual(self.op.contract()["tables"][name], ["SELECT"])

    def test_no_schema_privileges_in_table_contract(self):
        for privileges in self.op.contract()["tables"].values():
            self.assertTrue(set(privileges) <= {"SELECT", "INSERT", "UPDATE", "DELETE"})

    def test_historical_evidence_insert_only(self):
        for name in [
            "acknowledgements",
            "remuneration_approvals",
            "client_assessment_revisions",
            "api_receipts",
        ]:
            self.assertEqual(self.op.contract()["tables"][name], ["SELECT", "INSERT"])

    def test_write_scope_excludes_update_recovery_and_secrets(self):
        self.assertEqual(
            self.op.db.context.writes,
            {
                ("cloudformation", "create-stack"),
                ("cloudformation", "delete-stack"),
                ("lambda", "invoke"),
            },
        )
        self.assertNotIn(("secretsmanager", "get-secret-value"), self.op.db.context.reads)

    def test_no_write_before_confirmation(self):
        with self.assertRaisesRegex(RuntimeError, "before execution confirmation"):
            self.op.db.aws("cloudformation", "create-stack")

    def test_failed_stack_refused(self):
        with patch.object(self.op.db, "owned_stack", return_value={"StackStatus": "CREATE_FAILED"}):
            with self.assertRaisesRegex(RuntimeError, "requires review"):
                self.op.existing_stack({})

    def test_unowned_function_collision_refused(self):
        with (
            patch.object(self.op.db, "owned_stack", return_value=None),
            patch.object(self.op.db, "aws", return_value={"Configuration": {}}),
        ):
            with self.assertRaisesRegex(RuntimeError, "outside this stack"):
                self.op.existing_stack({})

    def test_proof_missing_denial_refused(self):
        for key in [
            "ddl_denied",
            "migration_role_denied",
            "migration_metadata_writes_denied",
            "seed_writes_denied",
            "truncate_denied",
            "dml_and_trigger_rollback_verified",
        ]:
            proof = self.valid_proof(True)
            proof[key] = False
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "proof missing"):
                self.op.validate_proof(proof, application=True)

    def test_proof_wrong_identity_refused(self):
        proof = self.valid_proof(False)
        proof["user"] = "fitfinity_admin"
        with self.assertRaisesRegex(RuntimeError, "identity differs"):
            self.op.validate_proof(proof, application=False)

    def test_proof_wrong_schema_refused(self):
        proof = self.valid_proof(False)
        proof["schema"]["triggers"] -= 1
        with self.assertRaisesRegex(RuntimeError, "Schema proof"):
            self.op.validate_proof(proof, application=False)

    def valid_proof(self, application):
        c = self.op.contract()
        return {
            "database": "fitfinity",
            "user": "fitfinity_app" if application else "fitfinity_migrator",
            "target_revision": "20260924_0006",
            "sslmode": "verify-full",
            "tls": "TLSv1.3",
            "server_version_num": 170011,
            "runtime_grants_verified": True,
            "schema": {
                "tables": len(c["tables"]),
                "functions": len(c["functions"]),
                "triggers": len(c["triggers"]),
                "sequences": 0,
            },
            "assessment_forms": c["assessment_forms"],
            "migrations_applied": True,
            "committed": True,
            "ddl_denied": True,
            "migration_role_denied": True,
            "migration_metadata_writes_denied": True,
            "seed_writes_denied": True,
            "truncate_denied": True,
            "dml_and_trigger_rollback_verified": True,
            "schema_sha256": "b" * 64,
        }

    def pipeline(self, failure=None, confirm=True):
        op = self.op
        order = []

        def invoked(name, mode, directory, *, preflight=False, source=None):
            order.append("preflight" if preflight else mode)
            if failure == ("preflight" if preflight else mode):
                raise RuntimeError("injected stop")
            if preflight:
                return {
                    "ok": True,
                    "target_revision": "20260924_0006",
                    "migration_files_sha256": op.context.report["migration_files_sha256"],
                }
            return {"proof": self.valid_proof(mode == "migration-app-probe")}

        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["operator"]))
            for name, result in [
                ("environment", None),
                ("network", (20, 8)),
                ("scan", None),
                ("costs", None),
                ("verify_functions", None),
                ("note", None),
            ]:
                stack.enter_context(patch.object(op.db, name, return_value=result))
            stack.enter_context(
                patch.object(op, "retained_credentials", return_value=op.contract()["secret_arns"])
            )
            stack.enter_context(patch.object(op, "existing_stack", return_value=None))

            def tty(path, mode="r"):
                self.assertEqual(path, "/dev/tty")
                return io.StringIO(op.db.ACCOUNT if confirm else "no")

            stack.enter_context(patch("builtins.open", side_effect=tty))
            provision = stack.enter_context(
                patch.object(op.db, "provision", return_value={"StackId": "exact"})
            )
            stack.enter_context(patch.object(op.db, "invoke", side_effect=invoked))
            cleanup = stack.enter_context(patch.object(op.db, "cleanup"))
            if failure or not confirm:
                with self.assertRaises(RuntimeError):
                    op.main()
                cleanup.assert_not_called()
                if not confirm:
                    provision.assert_not_called()
            else:
                op.main()
                cleanup.assert_called_once()
                self.assertEqual(cleanup.call_args.kwargs["name"], op.STACK)
        return order

    def test_confirmation_refusal_has_no_writes(self):
        self.assertEqual(self.pipeline(confirm=False), [])

    def test_cleanup_only_after_both_independent_proofs(self):
        self.assertEqual(
            self.pipeline(), ["preflight", "preflight", "migrate", "migration-app-probe"]
        )
        self.assertTrue(self.op.context.report["migrations_applied"])
        self.assertTrue(self.op.context.report["runtime_access_verified"])

    def test_preflight_failure_preserves_resources(self):
        self.pipeline(failure="preflight")
        self.assertFalse(self.op.context.report["migrations_applied"])

    def test_unknown_migration_outcome_is_recorded(self):
        self.pipeline(failure="migrate")
        self.assertEqual(
            self.op.context.report["migration_commit_status"], "unknown_until_verified"
        )
        self.assertFalse(self.op.context.report["migrations_applied"])

    def test_app_failure_preserves_committed_migration_status(self):
        self.pipeline(failure="migration-app-probe")
        self.assertTrue(self.op.context.report["migrations_applied"])
        self.assertFalse(self.op.context.report["runtime_access_verified"])

    def test_payload_is_checked_by_actual_loader(self):
        from fastapi.testclient import TestClient

        spec = importlib.util.spec_from_file_location("loader", ROOT / "test-db-loader.py")
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        source = self.op.source_bundle()
        loader.SOURCE_SHA256 = hashlib.sha256(source.encode()).hexdigest()
        with TestClient(loader.app) as client:
            result = client.post(
                "/events",
                json={
                    "action": "preflight",
                    "nonce": "a" * 32,
                    "bootstrap_source": source + "#tampered",
                },
            ).json()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "bootstrap_transport")

    def test_actual_loader_runs_the_valid_migration_preflight(self):
        from fastapi.testclient import TestClient

        pinned_contract = self.op.contract()
        image_root, contract = self.enterContext(image_fixture(ROOT.parent, pinned_contract))
        self.enterContext(patch.object(self.op, "contract", return_value=contract))
        spec = importlib.util.spec_from_file_location("loader", ROOT / "test-db-loader.py")
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        source = self.op.source_bundle()
        loader.SOURCE_SHA256 = hashlib.sha256(source.encode()).hexdigest()
        original_read = Path.read_bytes

        def image_read(path):
            if str(path).startswith("/app/"):
                path = image_root / path.relative_to("/app")
            return original_read(path)

        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, "read_bytes", image_read))
            stack.enter_context(
                patch.dict(
                    os.environ,
                    {
                        "FITFINITY_DB_ACCESS_MODE": "migrate",
                        "FITFINITY_MIGRATION_DB_SECRET_ARN": self.op.contract()["secret_arns"][
                            "migration"
                        ],
                    },
                )
            )
            for name in ["getuid", "geteuid", "getgid", "getegid"]:
                stack.enter_context(patch.object(os, name, return_value=10001))
            with TestClient(loader.app) as client:
                result = client.post(
                    "/events",
                    json={
                        "action": "preflight",
                        "nonce": "a" * 32,
                        "bootstrap_source": source,
                    },
                ).json()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["preflight_only"])
        self.assertEqual(result["target_revision"], "20260924_0006")
        self.assertEqual(load_operator().contract(), pinned_contract)


if __name__ == "__main__":
    unittest.main(verbosity=2)
