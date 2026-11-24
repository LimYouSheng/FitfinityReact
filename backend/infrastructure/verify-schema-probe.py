"""Private probe planning rejects drift and keeps operator authority separate."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from schema_probe_plan import prepare, prepare_review, write_review


class ProbePlanTests(unittest.TestCase):
    def setUp(self):
        self.binding = dict(
            account="418638389566",
            region="ap-southeast-1",
            source_sha="a" * 40,
            image_digest="sha256:" + "b" * 64,
            sql_sha256="c" * 64,
            db_host="fitfinity-test-db.example.ap-southeast-1.rds.amazonaws.com",
            db_name="fitfinity",
            migration_secret_arn="arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fitfinity/test/database/migration-abcdef",
            subnet_ids=["subnet-00000001", "subnet-00000002"],
            security_group_id="sg-00000001",
            expires_at=2000,
        )

    def test_plan_is_private_and_immutable_and_does_not_mutate_input(self):
        before = copy.deepcopy(self.binding)
        result = prepare(self.binding, now=1000)
        self.assertEqual(self.binding, before)
        self.assertEqual(result["decision"], "HOLD")
        resources = result["template"]["Resources"]
        self.assertEqual(set(resources), {"Probe", "ProbeRole", "ProbeLogs"})
        props = resources["Probe"]["Properties"]
        self.assertTrue(props["Code"]["ImageUri"].endswith("@sha256:" + "b" * 64))
        self.assertEqual(props["ReservedConcurrentExecutions"], 1)
        self.assertEqual(props["Timeout"], 60)
        self.assertIn("app.schema_probe:create_app", props["ImageConfig"]["Command"])
        self.assertEqual(props["Environment"]["Variables"]["FITFINITY_PROBE_SQL_SHA256"], "c" * 64)
        self.assertNotIn("FITFINITY_AUTH_SECRET_ARN", props["Environment"]["Variables"])
        self.assertEqual(result["invoke_payload"], {"operation": "observe-schema"})

    def test_only_exact_migration_secret_is_readable(self):
        resources = prepare(self.binding, now=1000)["template"]["Resources"]
        statements = resources["ProbeRole"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ]
        secret = statements[0]
        self.assertEqual(secret["Action"], "secretsmanager:GetSecretValue")
        self.assertEqual(secret["Resource"], self.binding["migration_secret_arn"])
        self.assertEqual(
            secret["Condition"]["StringEquals"]["secretsmanager:VersionStage"], "AWSCURRENT"
        )
        self.assertEqual(statements[-1]["Effect"], "Deny")
        self.assertIn("lambda:SourceFunctionArn", statements[-1]["Condition"]["ArnEquals"])

    def test_foreign_account_or_region_refused(self):
        for key, value in [("account", "123456789012"), ("region", "us-east-1")]:
            with self.assertRaises(RuntimeError):
                prepare({**self.binding, key: value}, now=1000)

    def test_mutable_or_missing_artifact_binding_refused(self):
        for key, value in [("image_digest", "latest"), ("source_sha", "main"), ("sql_sha256", "")]:
            with self.assertRaises(RuntimeError):
                prepare({**self.binding, key: value}, now=1000)

    def test_network_and_secret_overrides_refused(self):
        for key, value in [
            ("db_host", "example.com"),
            ("migration_secret_arn", "*"),
            (
                "migration_secret_arn",
                self.binding["migration_secret_arn"].replace("/migration-", "/app-"),
            ),
            ("security_group_id", "*"),
            ("subnet_ids", ["subnet-00000001"]),
            ("subnet_ids", ["subnet-00000001", "subnet-00000001"]),
        ]:
            with self.assertRaises(RuntimeError):
                prepare({**self.binding, key: value}, now=1000)

    def test_unreviewed_fields_refused(self):
        with self.assertRaises(RuntimeError):
            prepare({**self.binding, "sql": "DELETE FROM staff_users"}, now=1000)

    def test_expired_or_unbounded_lifetime_refused(self):
        for value in [999, 1000, 4601, "2000", True]:
            with self.assertRaises(RuntimeError):
                prepare({**self.binding, "expires_at": value}, now=1000)

    def test_plan_explicitly_requires_authority_and_cleanup(self):
        evidence = " ".join(prepare(self.binding, now=1000)["required_evidence"])
        self.assertIn("Account-plan eligibility", evidence)
        self.assertIn("create/invoke/delete authority", evidence)
        self.assertIn("expiry is not cleanup", evidence)

    def test_review_binds_source_sql_and_exact_template_bytes(self):
        sql = b"SELECT current_database();"
        binding = {**self.binding, "sql_sha256": hashlib.sha256(sql).hexdigest()}
        result = prepare_review(binding, "a" * 40, sql, now=1000)
        encoded = json.dumps(result["template"], sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(result["template_sha256"], hashlib.sha256(encoded).hexdigest())
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("Not verified", result["image_attestation"])
        self.assertEqual(result["expires_at"], 2000)

    def test_review_rejects_wrong_checkout_source(self):
        with self.assertRaisesRegex(RuntimeError, "source differs"):
            prepare_review(self.binding, "b" * 40, b"sql", now=1000)

    def test_review_rejects_changed_packaged_sql(self):
        with self.assertRaisesRegex(RuntimeError, "SQL differs"):
            prepare_review(self.binding, "a" * 40, b"changed sql", now=1000)

    def test_package_writes_exact_protocol_bytes_and_refuses_overwrite(self):
        review = prepare(self.binding, now=1000)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "review"
            write_review(review, output)
            self.assertEqual(
                (output / "invoke.json").read_bytes(), b'{"operation":"observe-schema"}'
            )
            self.assertEqual(json.loads((output / "template.json").read_text()), review["template"])
            with self.assertRaises(FileExistsError):
                write_review(review, output)
