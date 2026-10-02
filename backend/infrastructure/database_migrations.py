"""DatabaseMigrationOperator: explicit per-run dependencies and receipt state."""

import base64
import hashlib
import json
import os
import sys
import tempfile
import time
import zlib
from pathlib import Path

from database_access import DatabaseAccessOperator
from operator_context import OperatorContext


class DatabaseMigrationOperator:
    def __init__(self, *, context=None, aws_call=None):
        self.context = context if context is not None else OperatorContext(aws_call=aws_call)
        self.ROOT = Path(__file__).resolve().parent
        self.db = DatabaseAccessOperator(context=self.context)
        self.STACK = "fitfinity-test-schema-migrations"
        self.SECRET_STACK_ID = (
            "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-db-access/"
            "3ec5d530-b890-11f1-b0be-0ab91b93bd7d"
        )
        self.TAGS = {
            "Application": "Fitfinity",
            "Environment": "test",
            "Purpose": "schema-migrations-v1",
        }
        self.MODES = {"Setup": "migrate", "Application": "migration-app-probe"}
        self.NAMES = {
            "Setup": "fitfinity-test-schema-migrate",
            "Application": "fitfinity-test-schema-app-probe",
        }
        if context is None:
            self.context.report.update(
                {
                    "operator_revision": "2026-09-25-initial-schema",
                    "account": self.db.ACCOUNT,
                    "region": self.db.REGION,
                    "image_digest": self.db.DIGEST,
                    "target_revision": "20260924_0006",
                    "migrations_applied": False,
                    "runtime_access_verified": False,
                    "temporary_cleanup_complete": False,
                    "owner_created": False,
                    "auth_secret_created": False,
                    "app_deployed": False,
                    "cloud_writes": [],
                }
            )
        self.db.context.writes = {
            ("cloudformation", "create-stack"),
            ("cloudformation", "delete-stack"),
            ("lambda", "invoke"),
        }
        self.require = self.db.require

    def contract(self):
        return json.loads((self.ROOT / "test-db-migration-contract.json").read_text())

    def source_bundle(self):
        """Compressed, hash-pinned source fits the existing small Invoke loader.

        Bundle the canonical shared helper module rather than copying its TLS,
        secret and SQL-permission implementations into another runtime.
        """

        def packed(name):
            return base64.b64encode(zlib.compress((self.ROOT / name).read_bytes(), 9)).decode()

        shared_source = packed("test-db-bootstrap.py")
        migration_source = packed("test-db-migration-runtime.py")
        manifest = base64.b64encode(
            zlib.compress(
                json.dumps(self.contract(), sort_keys=True, separators=(",", ":")).encode(), 9
            )
        ).decode()
        source = (
            "import base64, sys, types, zlib\n"
            "shared_module = types.ModuleType('fitfinity_db_shared')\n"
            f"exec(compile(zlib.decompress(base64.b64decode({shared_source!r}, validate=True)), "
            "'fitfinity_db_shared', 'exec'), shared_module.__dict__)\n"
            "sys.modules['fitfinity_db_shared'] = shared_module\n"
            f"FITFINITY_MIGRATION_CONTRACT = zlib.decompress(base64.b64decode({manifest!r}, "
            "validate=True)).decode()\n"
            f"exec(compile(zlib.decompress(base64.b64decode({migration_source!r}, validate=True)), "
            "'fitfinity_db_migrations', 'exec'), globals())\n"
        )
        self.require(len(source.encode()) <= 32768, "Migration source exceeds pinned loader limit")
        return source

    def template(self, arns, source):
        # Reuse the canonical private two-function topology, then narrow each role
        # to its one restricted credential. The administrator secret is excluded.
        result = self.db.probe_template(arns, source=source.encode())
        result["Description"] = (
            "Temporary private initial Alembic migration and runtime permission proof."
        )
        for prefix, mode in self.MODES.items():
            name = self.NAMES[prefix]
            resources = result["Resources"]
            properties = resources[prefix + "Function"]["Properties"]
            properties["FunctionName"] = name
            variables = properties["Environment"]["Variables"]
            variables["FITFINITY_DB_ACCESS_MODE"] = mode
            if prefix == "Setup":
                del variables["FITFINITY_APP_DB_SECRET_ARN"]
            log_name = "/aws/lambda/" + name
            resources[prefix + "Logs"]["Properties"]["LogGroupName"] = log_name
            statements = resources[prefix + "Role"]["Properties"]["Policies"][0]["PolicyDocument"][
                "Statement"
            ]
            statements[0]["Resource"] = [arns["migration" if prefix == "Setup" else "app"]]
            statements[1]["Resource"] = (
                f"arn:aws:logs:{self.db.REGION}:{self.db.ACCOUNT}:log-group:{log_name}:*"
            )
            statements[3]["Condition"]["ArnEquals"]["lambda:SourceFunctionArn"] = (
                f"arn:aws:lambda:{self.db.REGION}:{self.db.ACCOUNT}:function:{name}"
            )
            self.db.configuration_sizes(properties)
        self.require(
            self.db.ADMIN_ARN not in json.dumps(result),
            "Administrator permission in migration template",
        )
        return result

    def retained_credentials(self):
        expected = json.loads((self.ROOT / "test-db-access.json").read_text())
        row = self.db.owned_stack(self.db.SECRETS_STACK, expected)
        self.require(
            row
            and row["StackId"] == self.SECRET_STACK_ID
            and row["StackStatus"] == "CREATE_COMPLETE"
            and row.get("EnableTerminationProtection") is True,
            "Accepted secret stack differs",
        )
        physical = self.db.stack_inventory(row, expected, successful=True)
        arns = self.db.credentials(row)
        self.require(
            arns == self.contract()["secret_arns"], "Accepted credential identities differ"
        )
        self.require(
            physical
            == {
                "ApplicationDatabaseSecret": arns["app"],
                "MigrationDatabaseSecret": arns["migration"],
            },
            "Secret resources differ",
        )
        return arns

    def existing_stack(self, expected):
        row = self.db.owned_stack(self.STACK, expected, tags=self.TAGS)
        if row:
            self.require(
                row["StackStatus"] in {"CREATE_IN_PROGRESS", "CREATE_COMPLETE"},
                "Migration stack requires review; no automatic recovery",
            )
        else:
            for name in self.NAMES.values():
                self.require(
                    self.db.aws("lambda", "get-function", "--function-name", name, missing=True)
                    is None,
                    "Proposed function already exists outside this stack",
                )
                logs = self.db.aws(
                    "logs", "describe-log-groups", "--log-group-name-prefix", "/aws/lambda/" + name
                )
                self.require(
                    not any(
                        item["logGroupName"] == "/aws/lambda/" + name
                        for item in logs.get("logGroups", [])
                    ),
                    "Proposed log group already exists",
                )
        return row

    def validate_proof(self, proof, *, application):
        self.require(
            proof.get("database") == "fitfinity"
            and proof.get("user") == ("fitfinity_app" if application else "fitfinity_migrator")
            and proof.get("target_revision") == self.context.report["target_revision"]
            and proof.get("sslmode") == "verify-full"
            and proof.get("tls") in {"TLSv1.2", "TLSv1.3"}
            and isinstance(proof.get("server_version_num"), int)
            and 170000 <= proof["server_version_num"] < 180000
            and proof.get("runtime_grants_verified") is True,
            "Migration proof identity differs",
        )
        expected = self.contract()
        self.require(
            proof.get("schema")
            == {
                "tables": len(expected["tables"]),
                "functions": len(expected["functions"]),
                "triggers": len(expected["triggers"]),
                "sequences": 0,
            }
            and proof.get("assessment_forms") == expected["assessment_forms"],
            "Schema proof differs",
        )
        required = (
            [
                "ddl_denied",
                "migration_role_denied",
                "migration_metadata_writes_denied",
                "seed_writes_denied",
                "truncate_denied",
                "dml_and_trigger_rollback_verified",
            ]
            if application
            else ["migrations_applied", "committed"]
        )
        self.require(
            all(proof.get(key) is True for key in required), "Permission/commit proof missing"
        )

    def main(self):
        self.require(not sys.argv[1:], "Usage: this script takes no arguments")
        self.db.note("Fitfinity AWS — initial Alembic schema and restricted runtime permissions")
        source = self.source_bundle()
        self.db.environment()
        storage = self.db.network()
        self.db.scan()
        self.db.costs(*storage)
        arns = self.retained_credentials()
        expected = self.template(arns, source)
        before = self.existing_stack(expected)
        self.context.report["migration_source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
        self.context.report["contract_sha256"] = self.db.canonical_hash(self.contract())
        self.context.report["migration_files_sha256"] = self.db.canonical_hash(
            self.contract()["files"]
        )
        self.context.report["bootstrap_configuration_bytes"] = {
            prefix: self.db.configuration_sizes(
                expected["Resources"][prefix + "Function"]["Properties"]
            )
            for prefix in self.MODES
        }
        self.db.note(
            "Base resources/secrets already exist. This step adds no permanent AWS resources."
        )
        self.db.note(
            "Creates/reuses 6 temporary resources: 2 private Lambdas, "
            "2 execution roles, 2 one-day log groups."
        )
        self.db.note(
            "Runs six reviewed Alembic revisions through 20260924_0006 "
            "and explicit runtime grants in one transaction."
        )
        self.db.note(
            "Accepts only the empty database or the verified completed initial schema. "
            "Includes frozen assessment form definitions."
        )
        self.db.note(
            "Migration function reads only the migration "
            "secret; app proof reads only the app secret. "
            "Passwords stay in AWS."
        )
        self.db.note(
            "On both proofs passing, removes only this exact temporary stack and test logs. "
            "Failures preserve resources."
        )
        self.db.note(
            "No Owner/staff creation, invitations, authentication secret, public API, "
            "source installation or Git push."
        )
        reviewed = time.monotonic()
        with open("/dev/tty", "w") as terminal:
            terminal.write(
                "To apply this initial schema, permissions and successful-test cleanup, "
                f"type {self.db.ACCOUNT}: "
            )
            terminal.flush()
        with open("/dev/tty") as terminal:
            self.require(
                terminal.readline().strip() == self.db.ACCOUNT, "Confirmation differs; no writes"
            )
        self.require(time.monotonic() - reviewed < 600, "Preview expired; rerun for current checks")
        self.db.environment()
        self.require(self.db.network() == storage, "Storage changed after quote")
        self.db.scan()
        self.require(self.retained_credentials() == arns, "Credentials changed after preview")
        after = self.existing_stack(expected)
        self.require(
            (before is None and after is None)
            or (before and after and before["StackId"] == after["StackId"]),
            "Stack changed after preview",
        )
        self.db.context.write_allowed = True
        with tempfile.TemporaryDirectory(prefix="fitfinity-schema-") as temporary:
            directory = Path(temporary)
            row = self.db.provision(self.STACK, expected, directory, tags=self.TAGS)
            self.db.verify_functions(row, expected)
            for prefix, mode in self.MODES.items():
                proof = self.db.invoke(
                    self.NAMES[prefix], mode, directory, preflight=True, source=source
                )
                self.context.report.setdefault("runtime_preflight", {})[mode] = proof
                self.require(
                    proof.get("ok") is True
                    and proof.get("target_revision") == self.context.report["target_revision"]
                    and proof.get("migration_files_sha256")
                    == self.context.report["migration_files_sha256"],
                    "Migration image/runtime preflight failed; see receipt",
                )
            self.context.report["runtime_preflight_verified"] = True
            self.db.note(
                "Both runtime/image preflights passed. Applying initial schema and permissions..."
            )
            self.context.report["migration_invocation_attempted"] = True
            self.context.report["migration_commit_status"] = "unknown_until_verified"
            result = self.db.invoke(
                self.NAMES["Setup"], self.MODES["Setup"], directory, source=source
            )["proof"]
            self.context.report["migration_proof"] = result
            self.validate_proof(result, application=False)
            self.context.report["migrations_applied"] = True
            self.context.report["migration_commit_status"] = "verified"
            self.db.note(
                "Alembic target and committed runtime "
                "grants passed. Checking independent app access..."
            )
            self.db.verify_functions(row, expected)
            result = self.db.invoke(
                self.NAMES["Application"], self.MODES["Application"], directory, source=source
            )["proof"]
            self.context.report["application_proof"] = result
            self.validate_proof(result, application=True)
            self.require(
                result.get("schema_sha256")
                == self.context.report["migration_proof"].get("schema_sha256"),
                "Independent schema fingerprint differs",
            )
            self.context.report["runtime_access_verified"] = True
            self.db.cleanup(row, expected, name=self.STACK, tags=self.TAGS)
        self.db.note(
            "SCHEMA MIGRATIONS PASSED — runtime permissions verified; temporary stack removed."
        )
        self.db.note("Owner creation, authentication secret and app deployment remain pending.")

    def save(self):
        self.context.report["checked_at"] = self.db.dt.datetime.now(self.db.dt.UTC).isoformat()
        folder = Path.home() / "Downloads"
        folder.mkdir(exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix="Fitfinity_AWS_Database_Migrations_", suffix=".json", dir=folder
        )
        with os.fdopen(descriptor, "w") as stream:
            json.dump(self.context.report, stream, indent=2)
        self.db.note("Receipt: " + name)

    def run(self):
        try:
            self.main()
        except (Exception, KeyboardInterrupt) as error:
            self.context.report["error"] = (
                str(error) if isinstance(error, RuntimeError) else type(error).__name__
            )
            self.db.note("STOPPED: " + self.context.report["error"])
            self.db.note(
                "Resources are preserved. If invocation "
                "started, commit status may need verification; "
                "do not manually rerun SQL."
            )
            self.save()
            raise SystemExit(1) from None
        self.save()
