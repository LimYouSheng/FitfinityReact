import copy
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def load(name, file):
    s = importlib.util.spec_from_file_location(name, ROOT / file)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    m = m.create_operator() if hasattr(m, "create_operator") else m
    return m


op = load("db_operator", "test-db-access.py")
boot = load("db_bootstrap", "test-db-bootstrap.py")
ARNS = {
    "app": f"arn:aws:secretsmanager:{op.REGION}:{op.ACCOUNT}:secret:"
    "fitfinity/test/database/app-ABC123",
    "migration": f"arn:aws:secretsmanager:{op.REGION}:{op.ACCOUNT}:secret:"
    "fitfinity/test/database/migration-DEF456",
}
VALUES = {
    "fitfinity_app": {"username": "fitfinity_app", "password": "A1b2" * 12},
    "fitfinity_migrator": {"username": "fitfinity_migrator", "password": "C3d4" * 12},
}
ROW = {
    "StackId": f"arn:aws:cloudformation:{op.REGION}:{op.ACCOUNT}:stack/{op.PROBE_STACK}/fixture",
    "StackStatus": "CREATE_COMPLETE",
    "EnableTerminationProtection": True,
}


@contextmanager
def mock_runtime(uid=10001, gid=10001, identity=None):
    identity = identity or {"uid": uid, "euid": uid, "gid": gid, "egid": gid}
    with ExitStack() as stack:
        for field in ("uid", "euid", "gid", "egid"):
            stack.enter_context(patch.object(boot.os, "get" + field, return_value=identity[field]))
        yield


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, answers=None, error=None):
        self.answers = iter(answers or [])
        self.commands = []
        self.error = error
        self.rollbacks = []
        self.pgconn = Mock()
        self.pgconn.encrypt_password.return_value = b"SCRAM-SHA-256$4096:test$stored:server"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, q, params=None):
        s = q if isinstance(q, str) else q.as_string(None)
        self.commands.append(s)
        if self.error:
            raise self.error
        return Cursor(next(self.answers, None))

    @contextmanager
    def transaction(self, force_rollback=False):
        self.rollbacks.append(force_rollback)
        yield


class DiagnosticConnection(Connection):
    def __init__(self, missing_setting=True, read_only=True, catalog_failure=False):
        super().__init__()
        self.missing_setting = missing_setting
        self.read_only = read_only
        self.catalog_failure = catalog_failure

    def execute(self, q, params=None):
        self.commands.append(q)
        if q == "SET TRANSACTION READ ONLY":
            return Cursor(None)
        if q == "SHOW transaction_read_only":
            return Cursor(("on" if self.read_only else "off",))
        if not self.read_only:
            raise AssertionError("Query before read-only verification")
        if not q.startswith("SELECT "):
            raise AssertionError("Unexpected SQL mutation")
        if q == "SELECT current_setting('rds.force_ssl', true)":
            return Cursor((None if self.missing_setting else "on",))
        if "current_setting('rds.force_ssl')" in q:
            if self.missing_setting:
                raise boot.psycopg.errors.UndefinedObject("NEVER_PRINT_ME missing GUC")
            return Cursor(("fitfinity", "fitfinity_admin", 170011, "on", True, "TLSv1.3"))
        if q.startswith("SELECT current_database()"):
            return Cursor(("fitfinity", "fitfinity_admin", 170011, True, "TLSv1.3"))
        if q.startswith("SELECT count(*)"):
            if self.catalog_failure:
                raise boot.psycopg.errors.UndefinedObject("NEVER_PRINT_ME catalog")
            return Cursor((0,))
        if q.startswith("SELECT pg_get_userbyid"):
            return Cursor(("fitfinity_admin",))
        if q.startswith("SELECT rolsuper"):
            return Cursor(None)
        raise AssertionError("Unexpected diagnostic query")


class Checks(unittest.TestCase):
    def setUp(self):
        op.context.write_allowed = False
        op.context.report = {"cloud_writes": []}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_01_writes_blocked_before_confirmation(self):
        with patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "before execution"):
                op.aws("cloudformation", "create-stack")
            run.assert_not_called()

    def test_02_unscoped_operations_blocked(self):
        for pair in [
            ("secretsmanager", "get-secret-value"),
            ("rds", "delete-db-instance"),
            ("iam", "put-role-policy"),
        ]:
            with self.assertRaisesRegex(RuntimeError, "outside"):
                op.aws(*pair)

    def test_03_wrong_identity_stops(self):
        with patch.object(op, "aws", return_value={"Account": "other", "Arn": "root"}):
            with self.assertRaisesRegex(RuntimeError, "identity"):
                op.environment()

    def test_04_environment_credential_override_stops(self):
        with patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "NEVER_PRINT_ME"}):
            with self.assertRaisesRegex(RuntimeError, "overrides"):
                op.environment()

    def scan_fixture(self):
        p = FIXTURES / "Fitfinity_ECR_Admin_Scan_efa53edd08c5_6w5hegqo.json"
        d = json.loads(p.read_text())
        d["imageScanFindings"]["imageScanCompletedAt"] = datetime.now(UTC).isoformat()
        return d

    def test_05_accepted_scan(self):
        with patch.object(op, "aws", return_value=self.scan_fixture()):
            op.scan()
        self.assertEqual(op.context.report["scan"]["exception"], "FITFINITY-TEST-2026-09-25-ZLIB")

    def test_06_stale_scan_stops(self):
        d = self.scan_fixture()
        d["imageScanFindings"]["imageScanCompletedAt"] = (
            datetime.now(UTC) - timedelta(days=2)
        ).isoformat()
        with patch.object(op, "aws", return_value=d):
            with self.assertRaisesRegex(RuntimeError, "older than"):
                op.scan()

    def test_07_new_cve_stops(self):
        d = self.scan_fixture()
        d["imageScanFindings"]["findings"][0]["name"] = "CVE-NEW"
        with patch.object(op, "aws", return_value=d):
            with self.assertRaisesRegex(RuntimeError, "findings changed"):
                op.scan()

    def test_08_expired_exception_stops(self):
        with (
            patch.object(op, "EXPIRY", datetime.now(UTC) - timedelta(seconds=1)),
            patch.object(op, "aws") as aws,
        ):
            with self.assertRaisesRegex(RuntimeError, "expired"):
                op.scan()
            aws.assert_not_called()

    def test_09_changed_stack_stops(self):
        r = {
            **ROW,
            "StackId": ROW["StackId"].replace(op.PROBE_STACK, "expected"),
            "Tags": [{"Key": k, "Value": v} for k, v in op.TAGS.items()],
        }
        with patch.object(
            op, "aws", side_effect=[{"Stacks": [r]}, {"TemplateBody": {"changed": True}}]
        ):
            with self.assertRaisesRegex(RuntimeError, "template differs"):
                op.owned_stack("expected", {"original": True})

    def test_10_missing_price_no_fallback(self):
        with patch.object(op, "aws", return_value={"PriceList": []}):
            with self.assertRaisesRegex(RuntimeError, "missing/ambiguous"):
                op.price("AWSSecretsManager", {}, "Secrets")

    def test_11_current_price_arithmetic_and_filter(self):
        def rate(service, filters, unit):
            if unit == "Secrets":
                self.assertEqual(filters["usagetype"], "APS1-AWSSecretsManager-Secret")
                v = "0.4"
            elif service == "AmazonRDS":
                v = "0.025" if unit == "Hrs" else "0.138"
            elif service == "AmazonVPC":
                v = "0.005"
            else:
                v = "0.0106" if unit == "Hrs" else "0.096"
            return {"usd": v}

        with patch.object(op, "price", side_effect=rate):
            op.costs(20, 8)
        self.assertEqual(op.context.report["monthly_base_usd"]["after_this_step"], "34.3660")

    def test_12_secret_template_retains_and_generates(self):
        t = json.loads((ROOT / "test-db-access.json").read_text())
        self.assertEqual(len(t["Resources"]), 2)
        for r in t["Resources"].values():
            self.assertEqual(r["DeletionPolicy"], "Retain")
            self.assertEqual(r["Properties"]["GenerateSecretString"]["PasswordLength"], 48)
            self.assertNotIn("SecretString", r["Properties"])

    def test_13_temporary_template_permissions_and_size(self):
        t = op.probe_template(ARNS)
        self.assertEqual(len(t["Resources"]), 6)
        self.assertLess(len(json.dumps(t).encode()), 51200)
        for prefix in ["Setup", "Application"]:
            p = t["Resources"][prefix + "Function"]["Properties"]
            self.assertEqual(p["Code"]["ImageUri"], op.IMAGE)
            self.assertNotIn("ReservedConcurrentExecutions", p)
            self.assertNotIn("FunctionUrlConfig", p)
            policy = t["Resources"][prefix + "Role"]["Properties"]["Policies"][0]["PolicyDocument"][
                "Statement"
            ]
            self.assertEqual(policy[0]["Action"], ["secretsmanager:GetSecretValue"])
            self.assertEqual(
                policy[0]["Resource"],
                [ARNS["app"]]
                if prefix == "Application"
                else [op.ADMIN_ARN, ARNS["app"], ARNS["migration"]],
            )
            self.assertEqual(policy[-1]["Effect"], "Deny")

    def test_14_invocation_nonce_mismatch_stops(self):
        def aws(*args, **kwargs):
            Path(args[-1]).write_text(
                json.dumps({"statusCode": 200, "body": json.dumps({"ok": True, "nonce": "wrong"})})
            )
            return {"StatusCode": 200}

        with patch.object(op, "aws", side_effect=aws):
            with self.assertRaisesRegex(RuntimeError, "nonce"):
                op.invoke("fn", "setup", Path(self.temp.name))

    def test_15_private_http_event_and_success(self):
        def aws(*args, **kwargs):
            event = json.loads(args[args.index("--payload") + 1])
            self.assertEqual(event["version"], "2.0")
            self.assertEqual(event["requestContext"]["http"]["method"], "POST")
            nonce = json.loads(event["body"])["nonce"]
            Path(args[-1]).write_text(
                json.dumps(
                    {
                        "statusCode": 200,
                        "body": json.dumps({"ok": True, "mode": "setup", "nonce": nonce}),
                    }
                )
            )
            return {"StatusCode": 200}

        with patch.object(op, "aws", side_effect=aws):
            self.assertTrue(op.invoke("fn", "setup", Path(self.temp.name))["ok"])

    def test_16_changed_cleanup_target_not_deleted(self):
        with (
            patch.object(op, "owned_stack", return_value={**ROW, "StackId": "other"}),
            patch.object(op, "aws") as aws,
        ):
            with self.assertRaisesRegex(RuntimeError, "Cleanup identity"):
                op.cleanup(ROW, {})
            aws.assert_not_called()

    def test_17_role_drift_and_membership_rejected(self):
        good = (False, False, False, False, False, False, True, 10, boot.MARKER + ARNS["app"])
        self.assertTrue(boot.role_state(Connection([good, (0,)]), "fitfinity_app", ARNS["app"]))
        for rows in [[(True, *good[1:])], [good, (1,)]]:
            with self.assertRaises(RuntimeError):
                boot.role_state(Connection(rows), "fitfinity_app", ARNS["app"])

    def test_18_tls_requires_expected_identity_and_encryption(self):
        row = ("fitfinity", "fitfinity_app", 170011, True, "TLSv1.3")
        self.assertEqual(boot.tls(Connection([row]), "fitfinity_app")["sslmode"], "verify-full")
        for r in [("other", *row[1:]), (*row[:3], False, row[-1]), (*row[:4], "TLSv1")]:
            with self.assertRaises(RuntimeError):
                boot.tls(Connection([r]), "fitfinity_app")

    def test_19_real_connection_uses_verified_tls(self):
        with patch.object(boot.psycopg, "connect") as connect:
            boot.connect(VALUES["fitfinity_app"])
            self.assertEqual(connect.call_args.kwargs["sslmode"], "verify-full")
            self.assertEqual(connect.call_args.kwargs["host"], boot.HOST)
            self.assertEqual(connect.call_args.kwargs["sslrootcert"], str(boot.CA))

    def test_20_app_effective_ddl_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "privileges differ"):
            boot.permissions(Connection([(True, False, False, True, True)]), "fitfinity_app")

    def test_21_forbidden_operation_success_is_rolled_back(self):
        c = Connection()
        with self.assertRaisesRegex(RuntimeError, "succeeded"):
            boot.denied(c, "CREATE TABLE test(id integer)")
        self.assertEqual(c.rollbacks, [True])

    def test_22_expected_permission_denial_is_accepted(self):
        c = Connection(error=boot.psycopg.errors.InsufficientPrivilege("private-error"))
        self.assertTrue(boot.denied(c, "SET ROLE fitfinity_migrator"))
        self.assertEqual(c.rollbacks, [True])

    def test_23_sql_uses_libpq_scram_not_plaintext(self):
        c = Connection()
        hashed = boot.scram(c, "fitfinity_app", "secret-text")
        self.assertTrue(hashed.startswith("SCRAM-SHA-256$"))
        self.assertNotIn("secret-text", hashed)
        c.pgconn.encrypt_password.assert_called_once_with(
            b"secret-text", b"fitfinity_app", b"scram-sha-256"
        )

    def test_24_existing_data_prevents_setup(self):
        with self.assertRaisesRegex(RuntimeError, "already contains"):
            boot.assert_unmigrated(Connection([(1,)]))

    def test_33_existing_routine_prevents_setup(self):
        with self.assertRaisesRegex(RuntimeError, "already contains application routines"):
            boot.assert_unmigrated(Connection([(0,), (1,)]))

    def test_25_bootstrap_no_network_on_health_or_invalid_action(self):
        with patch.object(boot.boto3, "client") as client:
            c = TestClient(boot.app)
            self.assertEqual(c.get("/health/live").status_code, 200)
            with patch.dict(os.environ, {"FITFINITY_DB_ACCESS_MODE": "setup"}):
                r = c.post("/events", json={"action": "destroy", "nonce": "a" * 32}).json()
            self.assertFalse(r["ok"])
            self.assertEqual(r["stage"], "request_schema")
            client.assert_not_called()
            self.assertEqual(c.get("/docs").status_code, 404)

    def test_26_provider_exception_redacted(self):
        env = {"FITFINITY_DB_ACCESS_MODE": "app-probe", "FITFINITY_APP_DB_SECRET_ARN": ARNS["app"]}
        ca = ROOT.parent / "app/certificates/ap-southeast-1-bundle.pem"
        with (
            patch.dict(os.environ, env),
            patch.object(boot, "CA", ca),
            mock_runtime(),
            patch.object(boot.boto3, "client", side_effect=RuntimeError("password=NEVER_PRINT_ME")),
        ):
            response = TestClient(boot.app).post(
                "/events", json={"action": "app-probe", "nonce": "b" * 32}
            )
            self.assertFalse(response.json()["ok"])
            self.assertNotIn("NEVER_PRINT_ME", response.text)
            self.assertEqual(response.json()["stage"], "secret_client")

    def test_27_secret_schema_and_admin_length(self):
        class Client:
            def __init__(self, v):
                self.v = v

            def get_secret_value(self, **kwargs):
                return {
                    "ARN": ARNS["app"],
                    "VersionStages": ["AWSCURRENT"],
                    "SecretString": json.dumps(self.v),
                }

        self.assertEqual(
            boot.secret(Client(VALUES["fitfinity_app"]), ARNS["app"], "fitfinity_app"),
            VALUES["fitfinity_app"],
        )
        with self.assertRaises(RuntimeError):
            boot.secret(
                Client({**VALUES["fitfinity_app"], "password": "short"}),
                ARNS["app"],
                "fitfinity_app",
            )
        self.assertEqual(
            boot.secret(
                Client({"username": "fitfinity_admin", "password": "A" * 28}),
                ARNS["app"],
                "fitfinity_admin",
            )["username"],
            "fitfinity_admin",
        )

    def orchestrate(self, confirmation=None, fail=None):
        import builtins

        original = builtins.open

        def opening(path, mode="r", *args, **kwargs):
            if path == "/dev/tty":
                import io

                return (
                    io.StringIO((confirmation if confirmation is not None else op.ACCOUNT) + "\n")
                    if mode == "r"
                    else io.StringIO()
                )
            return original(path, mode, *args, **kwargs)

        proofs = [
            {"migration": {"ddl_rollback_verified": True}},
            {"application": {"ddl_denied": True, "migration_role_denied": True}},
        ]
        if fail:
            proofs = [RuntimeError("database permission failure")]
        proofs = [
            {"ok": True, "preflight_only": True},
            {"ok": True, "preflight_only": True},
        ] + proofs
        from contextlib import ExitStack

        with ExitStack() as stack:
            for name, value in [
                ("environment", None),
                ("network", (20, 8)),
                ("scan", None),
                ("costs", None),
                ("owned_stack", None),
                ("aws", None),
                ("stack_inventory", {}),
                ("credentials", ARNS),
                ("verify_functions", None),
            ]:
                stack.enter_context(patch.object(op, name, return_value=value))
            create = stack.enter_context(patch.object(op, "provision", return_value=ROW))
            cleanup = stack.enter_context(patch.object(op, "cleanup"))
            invoke = stack.enter_context(patch.object(op, "invoke", side_effect=proofs))
            stack.enter_context(patch("builtins.open", side_effect=opening))
            stack.enter_context(patch.object(op, "note"))
            try:
                op.main()
                error = None
            except RuntimeError as e:
                error = e
            return error, create.call_count, cleanup.call_count, invoke.call_count

    def test_28_main_success_orders_setup_probe_cleanup(self):
        error, creates, cleanups, invokes = self.orchestrate()
        self.assertIsNone(error)
        self.assertEqual((creates, cleanups, invokes), (2, 1, 4))
        self.assertTrue(op.context.report["database_access_verified"])

    def test_29_declined_execution_has_no_writes(self):
        error, creates, cleanups, invokes = self.orchestrate("wrong")
        self.assertIsNotNone(error)
        self.assertEqual((creates, cleanups, invokes), (0, 0, 0))
        self.assertFalse(op.context.write_allowed)

    def test_30_setup_failure_preserves_resources(self):
        error, creates, cleanups, invokes = self.orchestrate(fail=True)
        self.assertIsNotNone(error)
        self.assertEqual((creates, cleanups, invokes), (2, 0, 3))

    def test_31_partial_roles_are_not_reset(self):
        admin = Connection([(True,)])
        arnmap = {"fitfinity_app": ARNS["app"], "fitfinity_migrator": ARNS["migration"]}
        with (
            patch.object(boot, "connect", return_value=admin),
            patch.object(boot, "tls", return_value={}),
            patch.object(boot, "assert_unmigrated"),
            patch.object(boot, "role_state", side_effect=[True, False]),
        ):
            with self.assertRaisesRegex(RuntimeError, "partial"):
                boot.setup({}, VALUES, arnmap)
        self.assertFalse(any("CREATE ROLE" in q or "ALTER ROLE" in q for q in admin.commands))

    def test_32_rerun_verifies_without_password_reset(self):
        admin = Connection([(True,), ("public",)])
        migrator = Connection([None, (True, True)])
        arnmap = {"fitfinity_app": ARNS["app"], "fitfinity_migrator": ARNS["migration"]}
        with (
            patch.object(boot, "connect", side_effect=[admin, migrator]),
            patch.object(boot, "tls", return_value={}),
            patch.object(boot, "assert_unmigrated"),
            patch.object(boot, "role_state", return_value=True),
            patch.object(boot, "probe", return_value={}),
        ):
            self.assertFalse(boot.setup({}, VALUES, arnmap)["created_roles"])
        self.assertFalse(
            any(
                "PASSWORD" in q or "CREATE ROLE" in q or "ALTER ROLE" in q
                for q in admin.commands + migrator.commands
            )
        )

    def test_148_native_diagnostic_identifies_old_failure_and_corrected_tls_passes(self):
        receipt = json.loads((FIXTURES / "Fitfinity_AWS_Database_Access_c86fkuo6.json").read_text())
        native = receipt["database_diagnostic"]["checks"]
        self.assertFalse(native["force_ssl_sql_setting"]["result"]["present_in_sql"])
        self.assertEqual(native["original_tls_query"]["sqlstate"], "42704")
        with self.assertRaises(boot.psycopg.errors.UndefinedObject):
            DiagnosticConnection().execute("SELECT current_setting('rds.force_ssl')")
        connection = DiagnosticConnection()
        proof = boot.tls(connection, "fitfinity_admin")
        self.assertEqual(
            {k: proof[k] for k in ("sslmode", "tls", "server_version_num")},
            native["connection_identity_tls"]["result"],
        )
        self.assertNotIn("rds.force_ssl", connection.commands[0])
        self.assertIn("WHERE pid=pg_backend_pid()", connection.commands[0])

    def test_149_tls_rejects_wrong_identity_version_missing_row_or_plaintext(self):
        row = ("fitfinity", "fitfinity_app", 170011, True, "TLSv1.3")
        for bad in [
            None,
            ("other", *row[1:]),
            (row[0], "other", *row[2:]),
            (*row[:2], 160000, *row[3:]),
            (*row[:3], False, row[4]),
            (*row[:4], "TLSv1.1"),
        ]:
            with self.assertRaises(RuntimeError):
                boot.tls(Connection([bad]), "fitfinity_app")


class NetworkChecks(unittest.TestCase):
    def setUp(self):
        op.context.write_allowed = False
        op.context.report = {"cloud_writes": []}
        outputs = {
            "Vpc": op.VPC,
            "DatabaseEndpoint": op.HOST,
            "DatabasePort": "5432",
            "AdminSecretArn": op.ADMIN_ARN,
            "ApplicationSecurityGroup": op.APP_SG,
            "MigrationSecurityGroup": op.MIGRATION_SG,
            "DatabaseSecurityGroup": op.DB_SG,
            "AppSubnetA": op.SUBNET_A,
            "AppSubnetB": op.SUBNET_B,
        }
        self.database = {
            "DBInstanceIdentifier": "fitfinity-test-db",
            "DBInstanceStatus": "available",
            "Engine": "postgres",
            "EngineVersion": "17.11",
            "DBInstanceClass": "db.t4g.micro",
            "DBName": "fitfinity",
            "MasterUsername": "fitfinity_admin",
            "PubliclyAccessible": False,
            "StorageEncrypted": True,
            "DeletionProtection": True,
            "MultiAZ": False,
            "StorageType": "gp3",
            "DBSubnetGroup": {"VpcId": op.VPC},
            "Endpoint": {"Address": op.HOST, "Port": 5432},
            "MasterUserSecret": {"SecretArn": op.ADMIN_ARN, "SecretStatus": "active"},
            "VpcSecurityGroups": [{"VpcSecurityGroupId": op.DB_SG, "Status": "active"}],
            "AllocatedStorage": 20,
            "MaxAllocatedStorage": 30,
            "BackupRetentionPeriod": 1,
            "DBParameterGroups": [
                {
                    "DBParameterGroupName": "fitfinity-test-postgres",
                    "ParameterApplyStatus": "in-sync",
                }
            ],
        }

        def tcp(port, **destinations):
            return {"IpProtocol": "tcp", "FromPort": port, "ToPort": port, **destinations}

        groups = [
            {
                "GroupId": op.DB_SG,
                "VpcId": op.VPC,
                "OwnerId": op.ACCOUNT,
                "IpPermissions": [
                    tcp(
                        5432,
                        UserIdGroupPairs=[{"GroupId": op.APP_SG}, {"GroupId": op.MIGRATION_SG}],
                    )
                ],
            }
        ]
        for group in (op.APP_SG, op.MIGRATION_SG):
            groups.append(
                {
                    "GroupId": group,
                    "VpcId": op.VPC,
                    "OwnerId": op.ACCOUNT,
                    "IpPermissions": [],
                    "IpPermissionsEgress": [
                        tcp(443, IpRanges=[{"CidrIp": "0.0.0.0/0"}]),
                        tcp(5432, UserIdGroupPairs=[{"GroupId": op.DB_SG}]),
                    ],
                }
            )
        self.responses = {
            ("cloudformation", "describe-stacks"): {
                "Stacks": [
                    {
                        "StackId": op.FOUNDATION,
                        "StackStatus": "CREATE_COMPLETE",
                        "EnableTerminationProtection": True,
                        "Outputs": [{"OutputKey": k, "OutputValue": v} for k, v in outputs.items()],
                    }
                ]
            },
            ("rds", "describe-db-instances"): {"DBInstances": [self.database]},
            ("rds", "describe-db-parameters"): {
                "Parameters": [{"ParameterName": "rds.force_ssl", "ParameterValue": "1"}]
            },
            ("ec2", "describe-security-groups"): {"SecurityGroups": groups},
            ("ec2", "describe-subnets"): {
                "Subnets": [
                    {"SubnetId": s, "VpcId": op.VPC, "MapPublicIpOnLaunch": False}
                    for s in (op.SUBNET_A, op.SUBNET_B)
                ]
            },
            ("ec2", "describe-route-tables"): {
                "RouteTables": [
                    {
                        "Routes": [
                            {
                                "DestinationCidrBlock": "0.0.0.0/0",
                                "NetworkInterfaceId": "eni-0189d693bfad0c7fa",
                                "State": "active",
                            }
                        ]
                    }
                ]
            },
            ("ec2", "describe-instances"): {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-0fc0373d803ed17ec",
                                "State": {"Name": "running"},
                                "InstanceType": "t4g.micro",
                                "VpcId": op.VPC,
                                "PublicIpAddress": "52.77.93.192",
                                "BlockDeviceMappings": [
                                    {"Ebs": {"VolumeId": "vol-0123456789abcdef0"}}
                                ],
                            }
                        ]
                    }
                ]
            },
            ("ec2", "describe-volumes"): {
                "Volumes": [{"VolumeType": "gp3", "Encrypted": True, "Size": 8}]
            },
        }

    def response(self, service, operation, *args, **kwargs):
        self.assertIn((service, operation), op.context.reads)
        return copy.deepcopy(self.responses[(service, operation)])

    def reject_groups(self):
        with patch.object(op, "aws", side_effect=self.response) as aws:
            with self.assertRaisesRegex(RuntimeError, "RDS security groups differ"):
                op.network()
        self.assertEqual(aws.call_count, 2)
        self.assertFalse(op.context.write_allowed)
        self.assertEqual(op.context.report["cloud_writes"], [])
        self.assertNotIn("database_configuration", op.context.report)

    def test_34_network_accepts_aws_response_shape(self):
        with patch.object(op, "aws", side_effect=self.response) as aws:
            self.assertEqual(op.network(), (20, 8))
        self.assertEqual(aws.call_count, 9)
        routes = [c.args[-1] for c in aws.call_args_list if c.args[1] == "describe-route-tables"]
        self.assertEqual(
            routes, ["Name=association.subnet-id,Values=" + s for s in (op.SUBNET_A, op.SUBNET_B)]
        )
        self.assertEqual(op.context.report["database_configuration"]["EngineVersion"], "17.11")
        self.assertFalse(op.context.write_allowed)
        self.assertEqual(op.context.report["cloud_writes"], [])

    def test_35_rds_fixture_matches_sdk_output_model(self):
        import botocore.session
        from botocore.validate import validate_parameters

        model = botocore.session.get_session().get_service_model("rds")
        self.assertIn("VpcSecurityGroups", model.shape_for("DBInstance").members)
        self.assertNotIn("VPCSecurityGroups", model.shape_for("DBInstance").members)
        validate_parameters(
            self.responses[("rds", "describe-db-instances")],
            model.operation_model("DescribeDBInstances").output_shape,
        )

    def test_36_missing_rds_groups_stops(self):
        del self.database["VpcSecurityGroups"]
        self.reject_groups()

    def test_37_wrong_rds_group_stops(self):
        self.database["VpcSecurityGroups"][0]["VpcSecurityGroupId"] = op.APP_SG
        self.reject_groups()

    def test_38_additional_rds_group_stops(self):
        self.database["VpcSecurityGroups"].append(
            {"VpcSecurityGroupId": op.APP_SG, "Status": "active"}
        )
        self.reject_groups()

    def test_39_inactive_rds_group_stops(self):
        self.database["VpcSecurityGroups"][0]["Status"] = "inactive"
        self.reject_groups()

    def test_40_empty_rds_groups_stops(self):
        self.database["VpcSecurityGroups"] = []
        self.reject_groups()

    def test_41_non_aws_field_spelling_stops(self):
        self.database["VPCSecurityGroups"] = self.database.pop("VpcSecurityGroups")
        self.reject_groups()

    def test_146_rds_force_ssl_api_proof_is_explicit(self):
        with patch.object(op, "aws", side_effect=self.response):
            op.network()
        self.assertEqual(
            op.context.report["database_tls_policy"],
            {
                "source": "rds_parameter_group",
                "parameter_group": "fitfinity-test-postgres",
                "apply_status": "in-sync",
                "rds_force_ssl": "1",
            },
        )

    def test_147_disabled_missing_or_pending_rds_tls_policy_is_rejected(self):
        for parameters in [[], [{"ParameterName": "rds.force_ssl", "ParameterValue": "0"}]]:
            op.context.report = {"cloud_writes": []}
            self.responses[("rds", "describe-db-parameters")] = {"Parameters": parameters}
            with patch.object(op, "aws", side_effect=self.response):
                with self.assertRaisesRegex(RuntimeError, "forced TLS differs"):
                    op.network()
            self.assertNotIn("database_tls_policy", op.context.report)
            self.assertEqual(op.context.report["cloud_writes"], [])
        self.responses[("rds", "describe-db-parameters")] = {
            "Parameters": [{"ParameterName": "rds.force_ssl", "ParameterValue": "1"}]
        }
        self.database["DBParameterGroups"][0]["ParameterApplyStatus"] = "pending-reboot"
        with patch.object(op, "aws", side_effect=self.response):
            with self.assertRaisesRegex(RuntimeError, "parameters not applied"):
                op.network()
        self.assertNotIn("database_tls_policy", op.context.report)


class DiagnosticChecks(unittest.TestCase):
    def setUp(self):
        op.context.write_allowed = False
        op.context.report = {"cloud_writes": []}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.receipt = json.loads(
            (FIXTURES / "Fitfinity_AWS_Database_Access_8vwpef2z.json").read_text()
        )
        self.old = json.loads((FIXTURES / "working-probe-template.json").read_text())
        self.new = op.probe_template(self.receipt["database_secret_arns"])
        self.current = self.old
        self.row = {
            "StackId": op.REVIEWED_PROBE_ID,
            "StackStatus": "UPDATE_COMPLETE",
            "DisableRollback": True,
            "Tags": [{"Key": k, "Value": v} for k, v in op.TAGS.items()],
        }
        self.persistent = json.loads((ROOT / "test-db-access.json").read_text())
        self.secret_row = {
            "StackId": self.receipt["stacks"][op.SECRETS_STACK],
            "StackStatus": "CREATE_COMPLETE",
            "EnableTerminationProtection": True,
            "Tags": self.row["Tags"],
        }
        self.uid = 10001
        self.gid = 10001
        self.identity = None
        self.drift = False
        self.missing_probe = False
        self.writes = []
        self.failed = False
        self.live = None
        self.failure_text = op.REQUEST_SIZE_ERROR
        self.rollback_fails = True
        self.skip_fails = False
        self.stable_event = True
        self.fail_ids = {"SetupFunction", "ApplicationFunction"}
        self.rollback_identity_drift = False
        self.live_update_failed = False
        self.native_inventory = False
        self.resource_overrides = {}
        self.expect_rollback_enabled = False
        self.update_fails = False
        self.post_update_retains_failures = False
        self.update_args = None
        self.db_diagnostic = False
        self.diagnostic_connection = None
        self.native_rows = json.loads((FIXTURES / "retained-resource-inventory.json").read_text())
        self.ca = ROOT.parent / "app/certificates/ap-southeast-1-bundle.pem"

    def physical(self, key):
        if self.native_inventory:
            return next(
                r["PhysicalResourceId"] for r in self.native_rows if r["LogicalResourceId"] == key
            )
        p = self.current["Resources"][key]["Properties"]
        return p.get("FunctionName", p.get("LogGroupName", key + "Fixture"))

    def rows(self):
        if self.native_inventory:
            rows = copy.deepcopy(self.native_rows)
            for r in rows:
                k = r["LogicalResourceId"]
                if not self.failed or k not in self.fail_ids:
                    r["ResourceStatus"] = "CREATE_COMPLETE"
                elif k in self.fail_ids:
                    r["ResourceStatus"] = "UPDATE_ROLLBACK_FAILED"
                if self.failure_text != op.REQUEST_SIZE_ERROR:
                    r["ResourceStatusReason"] = self.failure_text
                r.update(self.resource_overrides.get(k, {}))
            return rows
        return [
            {
                "LogicalResourceId": k,
                "ResourceType": v["Type"],
                "ResourceStatus": (
                    "UPDATE_ROLLBACK_FAILED"
                    if self.failed and k in self.fail_ids
                    else "CREATE_COMPLETE"
                ),
                "PhysicalResourceId": self.physical(k),
                "LastUpdatedTimestamp": op.RETAINED_FAILURE_TIMES.get(k),
                "ResourceStatusReason": self.failure_text,
                **self.resource_overrides.get(k, {}),
            }
            for k, v in self.current["Resources"].items()
        ]

    def provider(self, service, operation, *args, **kwargs):
        pair = (service, operation)
        if pair in op.context.writes:
            self.assertTrue(op.context.write_allowed)
            self.writes.append(pair)
        if service == "cloudformation":
            if operation == "rollback-stack":
                self.assertEqual(args[args.index("--stack-name") + 1], op.REVIEWED_PROBE_ID)
                self.assertNotIn("--resources-to-skip", args)
                self.row["StackStatus"] = (
                    "UPDATE_ROLLBACK_FAILED" if self.rollback_fails else "UPDATE_ROLLBACK_COMPLETE"
                )
                if not self.rollback_fails:
                    self.current = self.old
                    self.live = None
                    self.failed = False
                return {"StackId": op.REVIEWED_PROBE_ID}
            if operation == "continue-update-rollback":
                selected = args[args.index("--resources-to-skip") + 1 :]
                self.assertEqual(set(selected), self.fail_ids)
                if self.skip_fails:
                    raise RuntimeError("known continue failure")
                self.row["StackStatus"] = "UPDATE_ROLLBACK_COMPLETE"
                self.current = self.old
                self.live = None
                self.failed = False
                if self.rollback_identity_drift:
                    self.row["StackId"] = "other"
                return {}
            if operation == "update-stack":
                self.assertEqual(args[args.index("--stack-name") + 1], op.REVIEWED_PROBE_ID)
                self.update_args = args
                self.assertIn(
                    "--no-disable-rollback"
                    if self.expect_rollback_enabled
                    else "--disable-rollback",
                    args,
                )
                path = args[args.index("--template-body") + 1].removeprefix("file://")
                self.assertEqual(json.loads(Path(path).read_text()), self.new)
                if self.update_fails:
                    self.current = self.old
                    self.row["StackStatus"] = "UPDATE_ROLLBACK_COMPLETE"
                    return {"StackId": op.REVIEWED_PROBE_ID}
                self.current = self.new
                self.live = None
                self.failed = self.post_update_retains_failures
                self.live_update_failed = False
                self.row["StackStatus"] = "UPDATE_COMPLETE"
                return {"StackId": op.REVIEWED_PROBE_ID}
            if operation == "validate-template":
                return {}
            if operation == "describe-stack-events":
                return {
                    "StackEvents": [
                        {
                            "LogicalResourceId": logical,
                            "ResourceType": "AWS::Lambda::Function",
                            "ResourceStatus": "UPDATE_ROLLBACK_FAILED",
                            "ResourceStatusReason": self.failure_text,
                        }
                        for logical in self.fail_ids
                    ]
                    + [
                        {
                            "ResourceType": "AWS::CloudFormation::Stack",
                            "ResourceStatus": "UPDATE_ROLLBACK_IN_PROGRESS"
                            if self.row["StackStatus"] == "UPDATE_ROLLBACK_FAILED"
                            else "UPDATE_IN_PROGRESS",
                        }
                    ]
                    + (
                        [
                            {
                                "ResourceType": "AWS::CloudFormation::Stack",
                                "PhysicalResourceId": op.REVIEWED_PROBE_ID,
                                "ResourceStatus": "UPDATE_COMPLETE",
                            }
                        ]
                        if self.stable_event
                        else []
                    )
                }
            name = args[args.index("--stack-name") + 1]
            persistent = name in (op.SECRETS_STACK, self.secret_row["StackId"])
            if operation == "describe-stacks":
                if not persistent and self.missing_probe:
                    return None
                return {"Stacks": [copy.deepcopy(self.secret_row if persistent else self.row)]}
            if operation == "get-template":
                return {"TemplateBody": self.persistent if persistent else self.current}
            if operation == "list-stack-resources":
                rows = (
                    [
                        {"LogicalResourceId": k, "ResourceType": v["Type"], "PhysicalResourceId": k}
                        for k, v in self.persistent["Resources"].items()
                    ]
                    if persistent
                    else self.rows()
                )
                return {"StackResourceSummaries": rows}
        if service == "lambda":
            name = args[args.index("--function-name") + 1]
            prefix = "Setup" if name.endswith("-setup") else "Application"
            p = (self.live or self.current)["Resources"][prefix + "Function"]["Properties"]
            if operation == "invoke":
                event = json.loads(args[args.index("--payload") + 1])
                body = json.loads(event["body"])
                if body["action"] == "database-diagnostic":
                    return self.database_response(p, body, args[-1])
                self.assertEqual(body["action"], "preflight")
                with (
                    self.transport(p) as client,
                    patch.object(boot.boto3, "client") as secrets,
                    patch.object(boot.psycopg, "connect") as connect,
                ):
                    response = client.post("/events", json=body)
                    secrets.assert_not_called()
                    connect.assert_not_called()
                Path(args[-1]).write_text(
                    json.dumps({"statusCode": response.status_code, "body": response.text})
                )
                return {"StatusCode": 200}
            if operation == "get-function":
                environment = copy.deepcopy(p["Environment"])
                if self.drift:
                    environment["Variables"]["FITFINITY_DB_BOOTSTRAP_TAIL"] = "tampered"
                return {
                    "Configuration": {
                        "FunctionArn": f"arn:aws:lambda:{op.REGION}:{op.ACCOUNT}:function:{name}",
                        "State": "Active",
                        "LastUpdateStatus": "Failed" if self.live_update_failed else "Successful",
                        "LastUpdateStatusReason": self.failure_text,
                        "PackageType": "Image",
                        "Architectures": ["x86_64"],
                        "Timeout": 120,
                        "MemorySize": 256,
                        "Environment": environment,
                        "ImageConfigResponse": {"ImageConfig": p["ImageConfig"]},
                        "VpcConfig": {"VpcId": op.VPC, **p["VpcConfig"]},
                        "Role": f"arn:aws:iam::{op.ACCOUNT}:role/{self.physical(prefix + 'Role')}",
                    },
                    "Code": {"ResolvedImageUri": op.IMAGE},
                }
            if operation in ("get-policy", "get-function-url-config"):
                return None
            if operation == "list-event-source-mappings":
                return {"EventSourceMappings": []}
        if service == "iam":
            role = args[args.index("--role-name") + 1]
            prefix = "Setup" if role.startswith("Setup") or "-SetupRole-" in role else "Application"
            p = self.current["Resources"][prefix + "Role"]["Properties"]
            if operation == "get-role":
                return {
                    "Role": {
                        "Arn": f"arn:aws:iam::{op.ACCOUNT}:role/{role}",
                        "AssumeRolePolicyDocument": p["AssumeRolePolicyDocument"],
                    }
                }
            if operation == "list-role-policies":
                return {"PolicyNames": ["FitfinityDatabaseBootstrap"]}
            if operation == "list-attached-role-policies":
                return {"AttachedPolicies": []}
            if operation == "get-role-policy":
                return {"PolicyDocument": p["Policies"][0]["PolicyDocument"]}
        if pair == ("logs", "describe-log-groups"):
            return {"logGroups": [{"logGroupName": args[-1], "retentionInDays": 1}]}
        raise AssertionError("Unexpected operation: " + str(pair))

    def main(self, diagnose=True, confirmation=None, recover=False):
        import builtins
        import io
        from contextlib import ExitStack

        original = builtins.open

        def opening(path, mode="r", *args, **kwargs):
            if path == "/dev/tty":
                return (
                    io.StringIO((confirmation if confirmation is not None else op.ACCOUNT) + "\n")
                    if mode == "r"
                    else io.StringIO()
                )
            return original(path, mode, *args, **kwargs)

        with ExitStack() as stack:
            for name, value in [
                ("environment", None),
                ("network", (20, 8)),
                ("scan", None),
                ("costs", None),
                ("credentials", self.receipt["database_secret_arns"]),
                ("note", None),
            ]:
                stack.enter_context(patch.object(op, name, return_value=value))
            stack.enter_context(patch.object(op, "aws", side_effect=self.provider))
            stack.enter_context(patch("builtins.open", side_effect=opening))
            cleanup = stack.enter_context(patch.object(op, "cleanup"))
            try:
                op.main(
                    diagnose=diagnose if not (recover or self.db_diagnostic) else False,
                    recover=recover,
                    database_diagnostic=self.db_diagnostic,
                )
                error = None
            except RuntimeError as exc:
                error = exc
            cleanup.assert_not_called()
        return error

    def preflight(self, mode="setup", action="preflight", nonce="a" * 32):
        p = self.new["Resources"][("Setup" if mode == "setup" else "Application") + "Function"][
            "Properties"
        ]
        with (
            patch.dict(os.environ, p["Environment"]["Variables"]),
            mock_runtime(self.uid, self.gid, self.identity),
            patch.object(boot, "CA", self.ca),
            patch.object(boot.boto3, "client") as client,
            patch.object(boot.psycopg, "connect") as connect,
        ):
            proof = (
                TestClient(boot.app).post("/events", json={"action": action, "nonce": nonce}).json()
            )
            client.assert_not_called()
            connect.assert_not_called()
        return proof

    def test_42_both_configuration_budgets(self):
        for prefix in ("Setup", "Application"):
            p = self.new["Resources"][prefix + "Function"]["Properties"]
            self.assertLessEqual(len(json.dumps(p["ImageConfig"]).encode()), 4096)
            self.assertLessEqual(len(json.dumps(p["Environment"]["Variables"]).encode()), 4096)
            budget = op.configuration_sizes(p)
            self.assertLess(budget["modeled_update_request"] + budget["provider_allowance"], 5120)

    @contextmanager
    def transport(self, properties=None):
        import sys

        import uvicorn

        p = properties or self.new["Resources"]["SetupFunction"]["Properties"]
        cmd = p["ImageConfig"]["Command"]
        namespace = {"__name__": "__main__"}
        original = Path.read_bytes
        ca_bytes = self.ca.read_bytes()

        def reading(path):
            return ca_bytes if str(path) == str(boot.CA) else original(path)

        with (
            patch.dict(os.environ, p["Environment"]["Variables"]),
            patch.object(sys, "argv", ["-c", cmd[3]]),
            patch.object(uvicorn, "run") as serve,
            mock_runtime(self.uid, self.gid, self.identity),
            patch.object(Path, "read_bytes", reading),
        ):
            exec(compile(cmd[2], "generated-command", "exec"), namespace)
            yield TestClient(serve.call_args.args[0])

    def payload(self, action="preflight"):
        return {
            "action": action,
            "nonce": "a" * 32,
            "bootstrap_source": (ROOT / "test-db-bootstrap.py").read_text(),
        }

    def test_43_loader_health_and_verified_source_preflight(self):
        with (
            self.transport() as c,
            patch.object(boot.boto3, "client") as secrets,
            patch.object(boot.psycopg, "connect") as connect,
        ):
            self.assertEqual(c.get("/health/live").json(), {"status": "ok"})
            self.assertEqual(c.get("/docs").status_code, 404)
            proof = c.post("/events", json=self.payload()).json()
            self.assertTrue(proof["ok"])
            self.assertTrue(proof["preflight_only"])
            secrets.assert_not_called()
            connect.assert_not_called()

    def test_44_tampered_source_never_executes(self):
        payload = self.payload()
        payload["bootstrap_source"] = 'raise RuntimeError("ATTACK_EXECUTED")'
        with self.transport() as c, patch("builtins.exec") as execute:
            proof = c.post("/events", json=payload).json()
            execute.assert_not_called()
            self.assertFalse(proof["ok"])
            self.assertEqual(proof["stage"], "bootstrap_transport")
            self.assertNotIn("ATTACK_EXECUTED", json.dumps(proof))

    def test_45_oversized_source_stops_before_aws(self):
        original = Path.read_bytes

        def reading(path):
            return b"x" * 32769 if path.name == "test-db-bootstrap.py" else original(path)

        with patch.object(Path, "read_bytes", reading), patch.object(op, "environment") as env:
            with self.assertRaisesRegex(RuntimeError, "source exceeds invocation"):
                op.main(diagnose=True)
            env.assert_not_called()

    def test_46_non_tls_sql_implementation_unchanged(self):
        import ast
        import base64
        import zlib

        p = self.old["Resources"]["SetupFunction"]["Properties"]
        cmd = p["ImageConfig"]["Command"]
        old = zlib.decompress(
            base64.b64decode(cmd[3] + p["Environment"]["Variables"]["FITFINITY_DB_BOOTSTRAP_TAIL"])
        )

        def functions(source):
            return {
                n.name: ast.dump(n, include_attributes=False)
                for n in ast.parse(source).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name not in {"run", "diagnose_database", "tls"}
            }

        self.assertEqual(functions(old), functions((ROOT / "test-db-bootstrap.py").read_bytes()))

    def test_47_preflight_cannot_call_secrets_or_sql(self):
        for mode in ("setup", "app-probe"):
            proof = self.preflight(mode)
            self.assertTrue(proof["ok"])
            self.assertTrue(proof["preflight_only"])
            self.assertEqual(proof["mode"], mode)

    def test_48_unreviewed_uid_gid_pair_is_reported_not_accepted(self):
        self.uid = 993
        proof = self.preflight()
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["stage"], "runtime_identity")
        self.assertEqual(proof["runtime_identity"]["euid"], 993)

    def test_49_root_is_rejected(self):
        self.uid = 0
        self.assertEqual(self.preflight()["stage"], "runtime_identity")

    def test_50_certificate_mismatch_is_identified(self):
        self.ca = Path(self.temp.name) / "ca.pem"
        self.ca.write_text("NOT A CERTIFICATE")
        proof = self.preflight()
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["stage"], "tls_bundle")
        self.assertEqual(len(proof["ca_sha256"]), 64)

    def test_51_missing_certificate_does_not_expose_path(self):
        self.ca = Path(self.temp.name) / "PRIVATE_PATH.pem"
        proof = self.preflight()
        self.assertEqual(proof["stage"], "tls_bundle")
        self.assertEqual(proof["error_type"], "FileNotFoundError")
        self.assertNotIn("PRIVATE_PATH", json.dumps(proof))

    def test_52_bad_action_or_nonce_identified(self):
        self.assertEqual(self.preflight(action="destroy")["stage"], "request_schema")
        self.assertEqual(self.preflight(nonce="wrong")["stage"], "request_nonce")

    def test_53_expiry_still_blocks_preflight(self):
        class Expired(datetime):
            @classmethod
            def now(cls, *args):
                return datetime(2026, 9, 30, tzinfo=UTC)

        with patch.object(boot, "datetime", Expired):
            self.assertEqual(self.preflight()["stage"], "exception_window")

    def test_54_update_checks_old_live_functions(self):
        with patch.object(op, "aws", side_effect=self.provider):
            op.review_probe_update(self.row, self.new)
        self.assertEqual(
            op.context.report["reviewed_probe_update"]["stack_id"], op.REVIEWED_PROBE_ID
        )
        self.assertEqual(self.writes, [])

    def test_55_changed_stack_or_state_rejected(self):
        for change in (
            {"StackId": op.FOUNDATION},
            {"StackStatus": "CREATE_FAILED"},
            {"DisableRollback": False},
        ):
            with patch.object(op, "aws", side_effect=self.provider):
                with self.assertRaisesRegex(RuntimeError, "Only the recorded"):
                    op.review_probe_update({**self.row, **change}, self.new)

    def test_56_unknown_previous_template_rejected(self):
        self.current = copy.deepcopy(self.old)
        self.current["Description"] = "unknown"
        with patch.object(op, "aws", side_effect=self.provider):
            with self.assertRaisesRegex(RuntimeError, "Previous stack template differs"):
                op.review_probe_update(self.row, self.new)

    def test_57_expanded_iam_proposal_rejected(self):
        self.new["Resources"]["SetupRole"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ][0]["Resource"] = ["*"]
        with patch.object(op, "aws", side_effect=self.provider):
            with self.assertRaisesRegex(RuntimeError, "beyond bootstrap diagnostics"):
                op.review_probe_update(self.row, self.new)

    def test_58_live_payload_drift_rejected_before_update(self):
        self.drift = True
        error = self.main()
        self.assertIn("Function code/configuration differs", str(error))
        self.assertEqual(self.writes, [])

    def test_59_main_updates_then_collects_both_failed_preflights(self):
        self.uid = 993
        error = self.main()
        self.assertIn("Runtime preflight stopped", str(error))
        self.assertEqual(
            self.writes,
            [("cloudformation", "update-stack"), ("lambda", "invoke"), ("lambda", "invoke")],
        )
        self.assertEqual(set(op.context.report["runtime_preflight"]), {"setup", "app-probe"})
        for proof in op.context.report["runtime_preflight"].values():
            self.assertEqual(proof["runtime_identity"]["euid"], 993)
        self.assertFalse(op.context.report.get("database_access_verified", False))

    def test_60_diagnostic_success_still_does_no_database_work_or_cleanup(self):
        self.assertIsNone(self.main())
        self.assertTrue(op.context.report["runtime_preflight_verified"])
        self.assertFalse(op.context.report.get("database_access_verified", False))
        self.assertEqual(self.writes.count(("lambda", "invoke")), 2)

    def test_61_rerun_reuses_updated_configuration(self):
        self.current = self.new
        self.assertIsNone(self.main())
        self.assertEqual(self.writes, [("lambda", "invoke"), ("lambda", "invoke")])

    def test_62_declined_update_writes_nothing(self):
        self.assertIn("Confirmation did not match", str(self.main(confirmation="no")))
        self.assertEqual(self.writes, [])

    def test_63_missing_diagnostic_stack_is_not_created(self):
        self.missing_probe = True
        self.assertIn("Diagnostics require", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_64_diagnostic_write_allowlist_rejects_setup_and_cleanup(self):
        op.context.write_allowed = True
        op.context.report["diagnostic_only"] = True
        with patch.object(subprocess, "run") as run:
            for operation in ("create-stack", "delete-stack", "update-termination-protection"):
                with self.assertRaisesRegex(RuntimeError, "cannot create or delete"):
                    op.aws("cloudformation", operation)
            with self.assertRaisesRegex(RuntimeError, "only preflight"):
                op.aws(
                    "lambda",
                    "invoke",
                    "--payload",
                    json.dumps({"body": json.dumps({"action": "setup"})}),
                )
            run.assert_not_called()

    def test_65_update_write_allowlist_rejects_other_stack(self):
        op.context.write_allowed = True
        with patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "restricted to the reviewed"):
                op.aws(
                    "cloudformation",
                    "update-stack",
                    "--stack-name",
                    op.FOUNDATION,
                    "--disable-rollback",
                )
            run.assert_not_called()

    def test_66_default_mode_stops_before_sql_on_failed_preflight(self):
        self.uid = 993
        self.assertIn("Runtime preflight stopped", str(self.main(diagnose=False)))
        self.assertEqual(self.writes.count(("lambda", "invoke")), 2)
        self.assertFalse(op.context.report.get("database_access_verified", False))

    def test_67_disappeared_stack_is_not_recreated(self):
        with patch.object(op, "owned_stack", return_value=None), patch.object(op, "aws") as aws:
            with self.assertRaisesRegex(RuntimeError, "disappeared"):
                op.provision(
                    op.PROBE_STACK, self.new, Path(self.temp.name), create_if_missing=False
                )
            aws.assert_not_called()

    def failed_state(self):
        self.current = json.loads((FIXTURES / "request-size-failed-template.json").read_text())
        self.failed = True
        self.live = self.old
        self.row["StackStatus"] = "UPDATE_FAILED"

    def test_68_failed_stack_cannot_repeat_blocked_update(self):
        self.failed_state()
        error = self.main()
        self.assertIn("--recover", str(error))
        self.assertEqual(self.writes, [])

    def test_69_failed_stack_can_report_rolled_back_old_template(self):
        self.failed_state()
        self.current = self.old
        self.assertIsNone(self.main(recover=True))
        self.assertEqual(
            self.writes,
            [("cloudformation", "rollback-stack"), ("cloudformation", "continue-update-rollback")],
        )

    def test_70_unrelated_failure_never_recovers(self):
        self.failed_state()
        self.failure_text = "AccessDenied"
        self.assertIn("unreviewed resource error", str(self.main(recover=True)))
        self.assertEqual(self.writes, [])

    def test_71_unknown_failed_live_configuration_stops(self):
        self.failed_state()
        self.drift = True
        self.assertIn("configuration differs", str(self.main(recover=True)))
        self.assertEqual(self.writes, [])

    def test_72_failed_recovery_cannot_weaken_network_verification(self):
        self.failed_state()
        self.live = copy.deepcopy(self.old)
        self.live["Resources"]["SetupFunction"]["Properties"]["VpcConfig"]["SubnetIds"] = ["other"]
        self.assertIn("networking differs", str(self.main(recover=True)))
        self.assertEqual(self.writes, [])

    def test_73_whole_request_gate_rejects_previous_split_payload(self):
        for name in ("working-probe-template.json", "request-size-failed-template.json"):
            template = json.loads((FIXTURES / name).read_text())
            for prefix in ("Setup", "Application"):
                p = template["Resources"][prefix + "Function"]["Properties"]
                self.assertLess(len(json.dumps(p["ImageConfig"]).encode()), 4096)
                self.assertLess(len(json.dumps(p["Environment"]["Variables"]).encode()), 4096)
                with self.assertRaisesRegex(RuntimeError, "Combined Lambda"):
                    op.configuration_sizes(p)

    def test_74_malformed_envelope_never_executes(self):
        payloads = [
            {},
            [],
            {"nonce": "a" * 32, "bootstrap_source": None},
            self.payload() | {"extra": "x" * 257},
        ]
        with self.transport() as c, patch("builtins.exec") as execute:
            for payload in payloads:
                self.assertEqual(
                    c.post("/events", json=payload).json()["stage"], "bootstrap_transport"
                )
            execute.assert_not_called()

    def test_75_oversized_envelope_never_executes(self):
        with self.transport() as c, patch("builtins.exec") as execute:
            self.assertEqual(
                c.post("/events", content=b"x" * 49153).json()["stage"], "bootstrap_transport"
            )
            execute.assert_not_called()

    def test_76_original_action_and_nonce_guards_survive_transport(self):
        with (
            self.transport() as c,
            patch.object(boot.boto3, "client") as secrets,
            patch.object(boot.psycopg, "connect") as connect,
        ):
            for payload, stage in [
                (self.payload("destroy"), "request_schema"),
                (self.payload() | {"nonce": "bad"}, "request_nonce"),
            ]:
                self.assertEqual(c.post("/events", json=payload).json()["stage"], stage)
            secrets.assert_not_called()
            connect.assert_not_called()

    def test_77_both_prior_payloads_have_pinned_template_and_config_hashes(self):
        for filename, pin in [
            ("working-probe-template.json", op.PREVIOUS_TEMPLATE_SHA256),
            ("request-size-failed-template.json", op.FAILED_TEMPLATE_SHA256),
        ]:
            t = json.loads((FIXTURES / filename).read_text())
            self.assertEqual(op.canonical_hash(t), pin)
            for prefix in ("Setup", "Application"):
                p = t["Resources"][prefix + "Function"]["Properties"]
                self.assertIn(
                    op.canonical_hash({k: p[k] for k in ["ImageConfig", "Environment"]}),
                    op.REVIEWED_CONFIG_HASHES[prefix],
                )

    def test_78_complete_stack_requires_exact_current_configuration(self):
        self.current = self.new
        self.live = self.old
        self.assertIn("code/configuration differs", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_79_recovery_rolls_back_then_verifies_skips_only(self):
        self.failed_state()
        self.assertIsNone(self.main(recover=True))
        self.assertEqual(
            self.writes,
            [("cloudformation", "rollback-stack"), ("cloudformation", "continue-update-rollback")],
        )
        self.assertTrue(op.context.report["stack_recovery_verified"])
        self.assertFalse(op.context.report.get("database_access_verified", False))
        self.assertEqual(set(op.context.report["verified_rollback_skips"]), self.fail_ids)

    def test_80_successful_rollback_needs_no_skips(self):
        self.failed_state()
        self.rollback_fails = False
        self.assertIsNone(self.main(recover=True))
        self.assertEqual(self.writes, [("cloudformation", "rollback-stack")])
        self.assertNotIn("verified_rollback_skips", op.context.report)

    def test_81_no_stable_state_means_no_rollback(self):
        self.failed_state()
        self.stable_event = False
        self.assertIn("Previous successful stack state", str(self.main(recover=True)))
        self.assertEqual(self.writes, [])

    def test_82_recovery_rejects_diagnostic_candidate_as_rollback_target(self):
        self.failed_state()
        self.live = self.current
        self.assertIn("configuration differs", str(self.main(recover=True)))
        self.assertEqual(self.writes, [])

    def test_83_continue_requires_both_known_image_and_configuration(self):
        self.failed_state()
        self.row["StackStatus"] = "UPDATE_ROLLBACK_FAILED"
        self.drift = True
        self.assertIn("configuration differs", str(self.main(recover=True)))
        self.assertEqual(self.writes, [])

    def test_84_resume_failed_rollback_without_reissuing_rollback(self):
        self.failed_state()
        self.row["StackStatus"] = "UPDATE_ROLLBACK_FAILED"
        self.assertIsNone(self.main(recover=True))
        self.assertEqual(self.writes, [("cloudformation", "continue-update-rollback")])

    def test_85_skip_only_one_failed_function_if_other_succeeded(self):
        self.failed_state()
        self.row["StackStatus"] = "UPDATE_ROLLBACK_FAILED"
        self.fail_ids = {"SetupFunction"}
        self.assertIsNone(self.main(recover=True))
        self.assertEqual(op.context.report["verified_rollback_skips"], ["SetupFunction"])

    def test_86_recovered_rerun_performs_no_writes(self):
        self.current = self.old
        self.row["StackStatus"] = "UPDATE_ROLLBACK_COMPLETE"
        self.row["DisableRollback"] = False
        self.assertIsNone(self.main(recover=True))
        self.assertEqual(self.writes, [])
        self.assertTrue(op.context.report["stack_recovery_verified"])

    def test_87_diagnose_can_update_recovered_stack(self):
        self.current = self.old
        self.row["StackStatus"] = "UPDATE_ROLLBACK_COMPLETE"
        self.row["DisableRollback"] = False
        self.assertIsNone(self.main())
        self.assertEqual(
            self.writes,
            [("cloudformation", "update-stack"), ("lambda", "invoke"), ("lambda", "invoke")],
        )

    def test_88_declined_recovery_does_not_write(self):
        self.failed_state()
        self.assertIn("Confirmation did not match", str(self.main(recover=True, confirmation="no")))
        self.assertEqual(self.writes, [])

    def test_89_failed_continue_does_not_invoke_or_delete(self):
        self.failed_state()
        self.skip_fails = True
        self.assertIn("known continue failure", str(self.main(recover=True)))
        self.assertEqual(
            self.writes,
            [("cloudformation", "rollback-stack"), ("cloudformation", "continue-update-rollback")],
        )
        self.assertFalse(op.context.report.get("stack_recovery_verified", False))

    def test_90_recovery_response_identity_mismatch_stops(self):
        self.failed_state()
        self.rollback_identity_drift = True
        self.assertIn("identity differs", str(self.main(recover=True)))
        self.assertFalse(op.context.report.get("stack_recovery_verified", False))

    def test_91_recovery_write_guard_blocks_other_actions(self):
        op.context.write_allowed = True
        op.context.report["recovery_only"] = True
        with patch.object(subprocess, "run") as run:
            for pair in [
                ("cloudformation", "update-stack"),
                ("cloudformation", "delete-stack"),
                ("cloudformation", "create-stack"),
                ("lambda", "invoke"),
            ]:
                with self.assertRaisesRegex(RuntimeError, "Recovery mode cannot"):
                    op.aws(*pair)
            run.assert_not_called()

    def test_92_rollback_write_guard_blocks_other_stack_and_options(self):
        op.context.write_allowed = True
        op.context.report["recovery_only"] = True
        with patch.object(subprocess, "run") as run:
            for args in [
                ("--stack-name", op.FOUNDATION),
                ("--stack-name", op.REVIEWED_PROBE_ID, "--role-arn", "other"),
            ]:
                with self.assertRaises(RuntimeError):
                    op.aws("cloudformation", "rollback-stack", *args)
            for selected in ["SetupRole", "OtherFunction"]:
                with self.assertRaisesRegex(RuntimeError, "two reviewed functions"):
                    op.aws(
                        "cloudformation",
                        "continue-update-rollback",
                        "--stack-name",
                        op.REVIEWED_PROBE_ID,
                        "--resources-to-skip",
                        selected,
                    )
            run.assert_not_called()

    def test_93_rollback_cannot_run_from_diagnostic_mode(self):
        op.context.write_allowed = True
        op.context.report["diagnostic_only"] = True
        with patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "explicit recovery mode"):
                op.aws("cloudformation", "rollback-stack", "--stack-name", op.REVIEWED_PROBE_ID)
            run.assert_not_called()

    def test_94_cloudformation_rejection_preserves_service_reason_only(self):
        op.context.write_allowed = True
        message = (
            "update-stack and create-change-set cannot be performed on st"
            "ack with UPDATE_ROLLBACK_FAILED resource during disable-roll"
            "back."
        )
        result = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=(
                "aws: [ERROR]: An error occurred (ValidationError) when calli"
                "ng the UpdateStack operation: "
            )
            + message
            + "\nDEBUG_DO_NOT_EMIT",
        )
        with patch.object(subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "UPDATE_ROLLBACK_FAILED"):
                op.aws(
                    "cloudformation",
                    "update-stack",
                    "--stack-name",
                    op.REVIEWED_PROBE_ID,
                    "--disable-rollback",
                )
        self.assertEqual(op.context.report["cloudformation_rejection"]["message"], message)
        self.assertNotIn("DEBUG_DO_NOT_EMIT", json.dumps(op.context.report))

    def test_95_failed_lambda_update_status_requires_same_size_reason(self):
        self.failed_state()
        self.live_update_failed = True
        self.assertIsNone(self.main(recover=True))
        self.assertIsNone(self.main())
        self.assertTrue(op.context.report["runtime_preflight_verified"])

    def retained_state(self):
        self.current = self.old
        self.row["StackStatus"] = "UPDATE_ROLLBACK_COMPLETE"
        self.row["DisableRollback"] = False
        self.failed = True
        self.native_inventory = True
        self.expect_rollback_enabled = True

    def test_96_native_retained_failure_recovery_verifies_without_writes(self):
        self.retained_state()
        self.assertIsNone(self.main(recover=True))
        self.assertEqual(self.writes, [])
        self.assertTrue(op.context.report["stack_recovery_verified"])
        self.assertEqual(
            op.context.report["retained_rollback_review"]["resource_ids"],
            ["ApplicationFunction", "SetupFunction"],
        )

    def test_97_native_retained_failure_diagnostic_updates_with_rollback(self):
        self.retained_state()
        self.assertIsNone(self.main())
        self.assertTrue(op.context.report["preview_update_rollback_enabled"])
        self.assertTrue(op.context.report["runtime_preflight_verified"])
        self.assertEqual(
            self.writes,
            [("cloudformation", "update-stack"), ("lambda", "invoke"), ("lambda", "invoke")],
        )
        self.assertIn("--no-disable-rollback", self.update_args)
        self.assertNotIn("--disable-rollback", self.update_args)

    def test_98_new_or_missing_failure_timestamp_stops(self):
        self.retained_state()
        for stamp in [None, "bad", "2026-09-25T07:20:00+00:00"]:
            self.resource_overrides = {"SetupFunction": {"LastUpdatedTimestamp": stamp}}
            self.assertIn("timestamp/reason", str(self.main()))
            self.assertEqual(self.writes, [])

    def test_99_other_retained_failure_reason_stops(self):
        self.retained_state()
        self.failure_text = "AccessDenied"
        self.assertIn("timestamp/reason", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_100_retained_resource_replacement_stops(self):
        self.retained_state()
        self.resource_overrides = {"SetupRole": {"PhysicalResourceId": "replaced-role"}}
        self.assertIn("identities differ", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_101_retained_live_configuration_drift_stops(self):
        self.retained_state()
        self.drift = True
        self.assertIn("configuration differs", str(self.main()))
        self.assertEqual(self.writes, [])
        self.assertNotIn("retained_rollback_review", op.context.report)

    def test_102_retained_role_failure_is_not_permitted(self):
        self.retained_state()
        self.fail_ids.add("SetupRole")
        self.assertIn("type/state differs: SetupRole", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_103_retained_type_drift_is_not_permitted(self):
        self.retained_state()
        self.resource_overrides = {"SetupFunction": {"ResourceType": "AWS::Other::Resource"}}
        self.assertIn("type/state differs: SetupFunction", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_104_other_function_failure_status_is_not_permitted(self):
        self.retained_state()
        self.resource_overrides = {"SetupFunction": {"ResourceStatus": "UPDATE_FAILED"}}
        self.assertIn("type/state differs: SetupFunction", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_105_declining_retained_update_performs_no_writes(self):
        self.retained_state()
        self.assertIn("Confirmation did not match", str(self.main(confirmation="no")))
        self.assertEqual(self.writes, [])

    def test_106_failed_update_captures_rollback_before_template_mismatch(self):
        self.retained_state()
        self.update_fails = True
        self.assertIn("Stack did not complete", str(self.main()))
        self.assertEqual(self.writes, [("cloudformation", "update-stack")])
        self.assertEqual(op.context.report["provisioning_stack_status"], "UPDATE_ROLLBACK_COMPLETE")
        self.assertTrue(op.context.report["failed_resources"])

    def test_107_new_update_must_clear_resource_failures_before_invocation(self):
        self.retained_state()
        self.post_update_retains_failures = True
        self.assertIn("Resource completion", str(self.main()))
        self.assertEqual(self.writes, [("cloudformation", "update-stack")])

    def test_108_enabled_rollback_write_guard_requires_review_and_preview(self):
        op.context.write_allowed = True
        args = ("--stack-name", op.REVIEWED_PROBE_ID, "--no-disable-rollback")
        with patch.object(subprocess, "run") as run:
            for proof in [
                {},
                {
                    "stack_id": op.FOUNDATION,
                    "state": "UPDATE_ROLLBACK_COMPLETE",
                    "live_template_sha256": op.PREVIOUS_TEMPLATE_SHA256,
                },
            ]:
                op.context.report["retained_rollback_review"] = proof
                op.context.report["preview_update_rollback_enabled"] = True
                with self.assertRaisesRegex(RuntimeError, "Enabled rollback requires"):
                    op.aws("cloudformation", "update-stack", *args)
            op.context.report["retained_rollback_review"] = {
                "stack_id": op.REVIEWED_PROBE_ID,
                "state": "UPDATE_ROLLBACK_COMPLETE",
                "live_template_sha256": op.PREVIOUS_TEMPLATE_SHA256,
            }
            op.context.report["preview_update_rollback_enabled"] = False
            with self.assertRaisesRegex(RuntimeError, "Enabled rollback requires"):
                op.aws("cloudformation", "update-stack", *args)
            run.assert_not_called()

    def test_109_write_guard_accepts_verified_rollback_option_only(self):
        op.context.write_allowed = True
        op.context.report["preview_update_rollback_enabled"] = True
        op.context.report["retained_rollback_review"] = {
            "stack_id": op.REVIEWED_PROBE_ID,
            "state": "UPDATE_ROLLBACK_COMPLETE",
            "live_template_sha256": op.PREVIOUS_TEMPLATE_SHA256,
        }
        with patch.object(
            subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="{}")
        ) as run:
            op.aws(
                "cloudformation",
                "update-stack",
                "--stack-name",
                op.REVIEWED_PROBE_ID,
                "--no-disable-rollback",
            )
            self.assertIn("--no-disable-rollback", run.call_args.args[0])
            with self.assertRaises(RuntimeError):
                op.aws(
                    "cloudformation",
                    "update-stack",
                    "--stack-name",
                    op.REVIEWED_PROBE_ID,
                    "--no-disable-rollback",
                    "--disable-rollback",
                )
            self.assertEqual(run.call_count, 1)

    def test_110_preview_change_stops_before_update(self):
        self.retained_state()
        with patch.object(op, "aws", side_effect=self.provider):
            with self.assertRaisesRegex(RuntimeError, "behavior changed"):
                op.update_probe_stack(self.row, self.new, Path(self.temp.name))
        self.assertEqual(self.writes, [])

    def test_111_retained_network_drift_stops(self):
        self.retained_state()
        self.live = copy.deepcopy(self.old)
        self.live["Resources"]["SetupFunction"]["Properties"]["VpcConfig"]["SubnetIds"] = ["other"]
        self.assertIn("networking differs", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_112_resource_failure_receipt_contains_exact_resource_evidence(self):
        self.retained_state()
        self.resource_overrides = {"SetupFunction": {"ResourceStatus": "DELETE_FAILED"}}
        self.assertIn("type/state differs", str(self.main()))
        row = next(
            r
            for r in op.context.report["probe_resource_review"]
            if r["LogicalResourceId"] == "SetupFunction"
        )
        self.assertEqual(row["ResourceStatus"], "DELETE_FAILED")
        self.assertEqual(row["PhysicalResourceId"], "fitfinity-test-db-setup")
        self.assertNotIn("Environment", json.dumps(op.context.report["probe_resource_review"]))

    def transport_state(self):
        self.current = json.loads((FIXTURES / "working-transport-template.json").read_text())
        self.row["StackStatus"] = "UPDATE_COMPLETE"
        self.row["DisableRollback"] = False
        self.native_inventory = True
        self.identity = json.loads(
            (FIXTURES / "Fitfinity_AWS_Database_Access_09yifpg8.json").read_text()
        )["runtime_preflight"]["setup"]["runtime_identity"]

    def test_113_observed_lambda_identity_reaches_ca_and_secret_reference_checks(self):
        self.transport_state()
        for mode in ("setup", "app-probe"):
            proof = self.preflight(mode)
            self.assertTrue(proof["ok"])
            self.assertEqual(proof["runtime_identity"], self.identity)
            self.assertEqual(proof["ca_sha256"], boot.CA_SHA256)

    def test_114_any_root_user_or_group_field_is_rejected(self):
        self.transport_state()
        base = self.identity.copy()
        for field in base:
            self.identity = base | {field: 0}
            self.assertEqual(self.preflight()["stage"], "runtime_identity")

    def test_115_unreviewed_and_mixed_identities_are_rejected(self):
        for identity in [
            dict(uid=994, euid=994, gid=990, egid=990),
            dict(uid=993, euid=10001, gid=990, egid=990),
            dict(uid=993, euid=993, gid=990, egid=10001),
        ]:
            self.identity = identity
            self.assertEqual(self.preflight()["stage"], "runtime_identity")

    def test_116_native_transport_updates_only_pins_and_runs_both_preflights(self):
        self.transport_state()
        self.assertIsNone(self.main())
        self.assertEqual(
            self.writes,
            [("cloudformation", "update-stack"), ("lambda", "invoke"), ("lambda", "invoke")],
        )
        self.assertTrue(op.context.report["runtime_preflight_verified"])
        self.assertFalse(op.context.report["preview_update_rollback_enabled"])
        self.assertEqual(
            op.context.report["reviewed_probe_update"]["previous_template_sha256"],
            "ae592c424ff6cb6d8e090a2974e6295722cd87c652d3de37d5de6f39932c79f2",
        )

    def test_117_native_transport_rejects_changed_loader(self):
        self.transport_state()
        self.new["Resources"]["SetupFunction"]["Properties"]["ImageConfig"]["Command"][2] += (
            "\n# changed"
        )
        with patch.object(op, "aws", side_effect=self.provider):
            with self.assertRaisesRegex(RuntimeError, "changes the verified loader"):
                op.review_probe_update(self.row, self.new)
        self.assertEqual(self.writes, [])

    def test_118_native_transport_rejects_broader_template_changes(self):
        self.transport_state()
        self.new["Resources"]["SetupRole"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ][0]["Resource"] = ["*"]
        with patch.object(op, "aws", side_effect=self.provider):
            with self.assertRaisesRegex(RuntimeError, "beyond the bootstrap source pins"):
                op.review_probe_update(self.row, self.new)
        self.assertEqual(self.writes, [])

    def test_119_native_transport_rejects_live_configuration_drift(self):
        self.transport_state()
        self.drift = True
        self.assertIn("code/configuration differs", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_120_native_transport_rejects_resource_replacement(self):
        self.transport_state()
        self.resource_overrides = {"ApplicationRole": {"PhysicalResourceId": "replaced"}}
        self.assertIn("resource identities differ", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_121_native_transport_must_have_successful_resource_states(self):
        self.transport_state()
        self.failed = True
        self.assertIn("Resource completion", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_122_corrected_rerun_needs_only_preflight_invocations(self):
        self.transport_state()
        self.current = self.new
        self.assertIsNone(self.main())
        self.assertEqual(self.writes, [("lambda", "invoke"), ("lambda", "invoke")])

    def test_123_native_transport_configuration_matches_independent_receipt_fixture(self):
        self.transport_state()
        self.assertEqual(op.canonical_hash(self.current), op.TRANSPORT_TEMPLATE_SHA256)
        for prefix, pin in [
            ("Setup", "d2449cffebf820f238d054520bee38ab6395aade3121f5a47a00c7e72da56169"),
            ("Application", "808d80768558eae99648d3739e3879aa95b9ce02cfeabb25aff8ec89bf842f78"),
        ]:
            p = self.current["Resources"][prefix + "Function"]["Properties"]
            self.assertEqual(
                op.canonical_hash({k: p[k] for k in ("ImageConfig", "Environment")}), pin
            )

    def test_124_lambda_identity_does_not_bypass_certificate_verification(self):
        self.transport_state()
        self.ca = Path(self.temp.name) / "ca"
        self.ca.write_text("wrong")
        self.assertEqual(self.preflight()["stage"], "tls_bundle")

    def test_125_expired_exception_still_blocks_lambda_identity(self):
        self.transport_state()

        class Expired(datetime):
            @classmethod
            def now(cls, *args):
                return datetime(2026, 9, 30, tzinfo=UTC)

        with patch.object(boot, "datetime", Expired):
            self.assertEqual(self.preflight()["stage"], "exception_window")

    def identity_state(self):
        self.transport_state()
        self.current = json.loads((FIXTURES / "working-identity-template.json").read_text())

    def test_126_native_identity_baseline_updates_only_pins(self):
        self.identity_state()
        self.assertIsNone(self.main())
        self.assertEqual(
            self.writes,
            [("cloudformation", "update-stack"), ("lambda", "invoke"), ("lambda", "invoke")],
        )
        self.assertEqual(
            op.context.report["reviewed_probe_update"]["previous_template_sha256"],
            op.IDENTITY_TEMPLATE_SHA256,
        )
        self.assertTrue(op.context.report["runtime_preflight_verified"])

    def test_127_identity_baseline_rejects_live_and_resource_drift(self):
        self.identity_state()
        self.drift = True
        self.assertIn("code/configuration differs", str(self.main()))
        self.assertEqual(self.writes, [])
        self.drift = False
        self.resource_overrides = {"ApplicationRole": {"PhysicalResourceId": "replaced"}}
        self.assertIn("resource identities differ", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_128_identity_baseline_matches_delivered_source_and_native_receipt(self):
        self.identity_state()
        self.assertEqual(op.canonical_hash(self.current), op.IDENTITY_TEMPLATE_SHA256)
        receipt = json.loads((FIXTURES / "Fitfinity_AWS_Database_Access_adsb1l34.json").read_text())
        for prefix in ("Setup", "Application"):
            self.assertEqual(
                self.current["Resources"][prefix + "Function"]["Properties"]["ImageConfig"][
                    "Command"
                ][3],
                receipt["bootstrap_source_sha256"],
            )
        self.assertEqual(
            self.current["Resources"]["SetupFunction"]["Properties"]["Environment"]["Variables"][
                "FITFINITY_APP_DB_SECRET_ARN"
            ],
            receipt["database_secret_arns"]["app"],
        )

    def test_129_identity_baseline_rejects_unknown_template_and_loader(self):
        self.identity_state()
        self.current["Resources"]["SetupFunction"]["Properties"]["MemorySize"] = 512
        self.assertIn("Only the recorded temporary stack", str(self.main()))
        self.assertEqual(self.writes, [])
        self.identity_state()
        self.new["Resources"]["SetupFunction"]["Properties"]["ImageConfig"]["Command"][2] += (
            "\n# modified"
        )
        with patch.object(op, "aws", side_effect=self.provider):
            with self.assertRaisesRegex(RuntimeError, "changes the verified loader"):
                op.review_probe_update(self.row, self.new)
        self.assertEqual(self.writes, [])

    def client_state(self):
        self.identity_state()
        self.current = json.loads((FIXTURES / "working-client-template.json").read_text())

    def database_response(self, p, body, target):
        from botocore.stub import Stubber

        self.assertTrue(self.db_diagnostic)
        self.assertEqual(p["Environment"]["Variables"]["FITFINITY_DB_ACCESS_MODE"], "setup")
        sdk = boot.boto3.client(
            "secretsmanager",
            region_name=boot.REGION,
            aws_access_key_id="offline-test",
            aws_secret_access_key="offline-test",
        )
        try:
            with Stubber(sdk) as stub:
                stub.add_response(
                    "get_secret_value",
                    {
                        "ARN": boot.ADMIN_ARN,
                        "VersionStages": ["AWSCURRENT"],
                        "SecretString": json.dumps(
                            {"username": "fitfinity_admin", "password": "offline-admin-password"}
                        ),
                    },
                    {"SecretId": boot.ADMIN_ARN, "VersionStage": "AWSCURRENT"},
                )
                self.diagnostic_connection = self.diagnostic_connection or DiagnosticConnection()
                with (
                    self.transport(p) as client,
                    patch.object(boot.boto3, "client", return_value=sdk),
                    patch.object(sdk, "close", wraps=sdk.close) as close,
                    patch.object(
                        boot.psycopg, "connect", return_value=self.diagnostic_connection
                    ) as connect,
                ):
                    response = client.post("/events", json=body)
                    close.assert_called_once_with()
                    connect.assert_called_once()
                    self.assertEqual(connect.call_args.kwargs["sslmode"], "verify-full")
                    stub.assert_no_pending_responses()
                self.assertNotIn("offline-admin-password", response.text)
                Path(target).write_text(
                    json.dumps({"statusCode": response.status_code, "body": response.text})
                )
                return {"StatusCode": 200}
        finally:
            sdk.close()

    def test_136_read_only_diagnostic_handles_missing_managed_sql_setting(self):
        self.client_state()
        self.db_diagnostic = True
        self.assertEqual(op.canonical_hash(self.current), op.CLIENT_TEMPLATE_SHA256)
        self.assertIsNone(self.main())
        self.assertEqual(
            self.writes,
            [
                ("cloudformation", "update-stack"),
                ("lambda", "invoke"),
                ("lambda", "invoke"),
                ("lambda", "invoke"),
            ],
        )
        proof = op.context.report["database_diagnostic"]
        self.assertTrue(proof["read_only"])
        self.assertTrue(proof["rolled_back"])
        self.assertTrue(proof["all_checks_passed"])
        self.assertTrue(proof["checks"]["tls_query"]["ok"])
        self.assertEqual(
            proof["checks"]["force_ssl_sql_setting"]["result"],
            {"present_in_sql": False, "enabled": None},
        )
        self.assertTrue(proof["checks"]["connection_identity_tls"]["ok"])
        self.assertTrue(proof["checks"]["unmigrated_schema"]["ok"])
        self.assertNotIn("setup_proof", op.context.report)
        self.assertNotIn("application_proof", op.context.report)
        self.assertFalse(op.context.report.get("database_access_verified", False))
        self.assertTrue(all(self.diagnostic_connection.rollbacks))
        self.assertEqual(len(self.diagnostic_connection.rollbacks), 7)

    def test_137_database_diagnostic_rerun_reuses_and_never_sets_up(self):
        self.client_state()
        self.current = self.new
        self.db_diagnostic = True
        self.diagnostic_connection = DiagnosticConnection(missing_setting=False)
        self.assertIsNone(self.main())
        self.assertTrue(op.context.report["database_diagnostic"]["all_checks_passed"])
        self.assertEqual(self.writes, [("lambda", "invoke")] * 3)
        self.assertNotIn("setup_proof", op.context.report)
        self.assertFalse(op.context.report.get("database_access_verified", False))

    def test_138_database_diagnostic_requires_existing_stack_and_confirmation(self):
        self.client_state()
        self.db_diagnostic = True
        self.missing_probe = True
        self.assertIn("Diagnostics require", str(self.main()))
        self.assertEqual(self.writes, [])
        self.missing_probe = False
        self.assertIn("Confirmation", str(self.main(confirmation="wrong")))
        self.assertEqual(self.writes, [])

    def test_139_database_diagnostic_runtime_failure_stops_before_secret_or_sql(self):
        self.client_state()
        self.db_diagnostic = True
        self.identity = dict(uid=0, euid=0, gid=0, egid=0)
        self.assertIn("Runtime preflight stopped", str(self.main()))
        self.assertIsNone(self.diagnostic_connection)
        self.assertEqual(
            self.writes,
            [("cloudformation", "update-stack"), ("lambda", "invoke"), ("lambda", "invoke")],
        )

    def test_140_database_diagnostic_modes_are_exclusive(self):
        with patch.object(op, "environment") as environment:
            for kwargs in [
                dict(diagnose=True, database_diagnostic=True),
                dict(recover=True, database_diagnostic=True),
            ]:
                with self.assertRaisesRegex(RuntimeError, "only one mode"):
                    op.main(**kwargs)
            environment.assert_not_called()

    def test_141_database_diagnostic_action_rejected_by_application_function(self):
        p = self.new["Resources"]["ApplicationFunction"]["Properties"]
        with (
            self.transport(p) as client,
            patch.object(boot.boto3, "client") as sdk,
            patch.object(boot.psycopg, "connect") as connect,
        ):
            proof = client.post("/events", json=self.payload("database-diagnostic")).json()
            self.assertFalse(proof["ok"])
            self.assertEqual(proof["stage"], "request_schema")
            sdk.assert_not_called()
            connect.assert_not_called()

    def test_142_read_only_mode_must_be_verified_before_select_checks(self):
        self.client_state()
        self.db_diagnostic = True
        self.diagnostic_connection = DiagnosticConnection(read_only=False)
        self.assertIn("diagnostic_read_only", str(self.main()))
        self.assertEqual(
            self.diagnostic_connection.commands,
            ["SET TRANSACTION READ ONLY", "SHOW transaction_read_only"],
        )

    def test_143_diagnostic_reports_catalog_failure_without_error_text(self):
        self.client_state()
        self.db_diagnostic = True
        self.diagnostic_connection = DiagnosticConnection(catalog_failure=True)
        self.assertIsNone(self.main())
        checks = op.context.report["database_diagnostic"]["checks"]
        self.assertFalse(checks["unmigrated_schema"]["ok"])
        self.assertEqual(checks["unmigrated_schema"]["sqlstate"], "42704")
        self.assertTrue(checks["fitfinity_migrator_role"]["ok"])
        self.assertNotIn("NEVER_PRINT_ME", json.dumps(checks))

    def test_144_new_native_client_baseline_requires_exact_template_and_resources(self):
        self.client_state()
        self.db_diagnostic = True
        self.resource_overrides = {"ApplicationRole": {"PhysicalResourceId": "replacement"}}
        self.assertIn("resource identities differ", str(self.main()))
        self.assertEqual(self.writes, [])

    def test_145_database_diagnostic_cannot_be_called_as_application_or_preflight(self):
        with patch.object(op, "aws") as aws:
            for mode, preflight in [("app-probe", False), ("setup", True)]:
                with self.assertRaisesRegex(RuntimeError, "only the setup function"):
                    op.invoke(
                        "fn",
                        mode,
                        Path(self.temp.name),
                        preflight=preflight,
                        database_diagnostic=True,
                    )
            aws.assert_not_called()

    def diagnostic_state(self):
        self.client_state()
        self.current = json.loads((FIXTURES / "working-diagnostic-template.json").read_text())

    def test_150_native_diagnostic_baseline_allows_only_reviewed_tls_source_pins(self):
        self.diagnostic_state()
        self.assertEqual(op.canonical_hash(self.current), op.DIAGNOSTIC_TEMPLATE_SHA256)
        receipt = json.loads((FIXTURES / "Fitfinity_AWS_Database_Access_c86fkuo6.json").read_text())
        for prefix in ("Setup", "Application"):
            self.assertEqual(
                self.current["Resources"][prefix + "Function"]["Properties"]["ImageConfig"][
                    "Command"
                ][3],
                receipt["bootstrap_source_sha256"],
            )
        self.assertIsNone(self.main())
        self.assertEqual(
            self.writes,
            [("cloudformation", "update-stack"), ("lambda", "invoke"), ("lambda", "invoke")],
        )
        self.assertEqual(
            op.context.report["reviewed_probe_update"]["previous_template_sha256"],
            op.DIAGNOSTIC_TEMPLATE_SHA256,
        )

    def test_151_native_diagnostic_baseline_refuses_live_or_proposed_drift(self):
        self.diagnostic_state()
        self.drift = True
        self.assertIn("code/configuration differs", str(self.main()))
        self.assertEqual(self.writes, [])
        self.drift = False
        self.new["Resources"]["SetupRole"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ][0]["Resource"] = ["*"]
        with patch.object(op, "aws", side_effect=self.provider):
            with self.assertRaisesRegex(RuntimeError, "beyond the bootstrap source pins"):
                op.review_probe_update(self.row, self.new)
        self.assertEqual(self.writes, [])


class SecretClientChecks(unittest.TestCase):
    def setUp(self):
        from botocore.config import Config
        from botocore.stub import Stubber

        self.client = boot.boto3.client(
            "secretsmanager",
            region_name=boot.REGION,
            endpoint_url=f"https://secretsmanager.{boot.REGION}.amazonaws.com",
            verify=True,
            aws_access_key_id="offline-test",
            aws_secret_access_key="offline-test",
            config=Config(connect_timeout=3, read_timeout=4, retries={"total_max_attempts": 2}),
        )
        self.addCleanup(self.client.close)
        self.stub = Stubber(self.client)
        self.stub.activate()
        self.addCleanup(self.stub.deactivate)
        self.ca = ROOT.parent / "app/certificates/ap-southeast-1-bundle.pem"
        self.admin = {"username": "fitfinity_admin", "password": "offline-admin-" + ("x" * 32)}

    def enqueue(self, mode="setup"):
        pairs = [(ARNS["app"], VALUES["fitfinity_app"])]
        if mode == "setup":
            pairs.extend(
                [(ARNS["migration"], VALUES["fitfinity_migrator"]), (boot.ADMIN_ARN, self.admin)]
            )
        for arn, value in pairs:
            self.stub.add_response(
                "get_secret_value",
                {"ARN": arn, "VersionStages": ["AWSCURRENT"], "SecretString": json.dumps(value)},
                {"SecretId": arn, "VersionStage": "AWSCURRENT"},
            )

    def env(self, mode):
        return {
            "FITFINITY_DB_ACCESS_MODE": mode,
            "FITFINITY_APP_DB_SECRET_ARN": ARNS["app"],
            "FITFINITY_MIGRATION_DB_SECRET_ARN": ARNS["migration"],
        }

    @contextmanager
    def runtime(self, mode="setup"):
        with (
            patch.dict(os.environ, self.env(mode)),
            mock_runtime(993, 990),
            patch.object(boot, "CA", self.ca),
            patch.object(boot.boto3, "client", return_value=self.client) as factory,
            patch.object(self.client, "close", wraps=self.client.close) as close,
            patch.object(
                self.client._endpoint,
                "make_request",
                side_effect=AssertionError("Network forbidden"),
            ),
        ):
            yield factory, close

    def request(self, mode):
        return TestClient(boot.app).post("/events", json={"action": mode, "nonce": "b" * 32})

    def test_130_delivered_code_reproduces_native_failure_before_secret_api(self):
        self.assertFalse(hasattr(self.client, "__enter__"))
        self.assertTrue(callable(self.client.close))
        with (
            self.runtime(),
            patch.object(self.client, "get_secret_value") as get,
            patch.object(boot.psycopg, "connect") as connect,
        ):
            with self.assertRaises(TypeError), self.client:
                self.client.get_secret_value(SecretId=ARNS["app"])
            get.assert_not_called()
            connect.assert_not_called()

    def test_131_setup_reads_exact_three_secrets_then_closes_before_sql(self):
        self.enqueue()
        with self.runtime() as (factory, close):

            def setup(admin, values, arns):
                close.assert_called_once_with()
                self.assertEqual(admin, self.admin)
                self.assertEqual(values, VALUES)
                self.assertEqual(
                    arns, {"fitfinity_app": ARNS["app"], "fitfinity_migrator": ARNS["migration"]}
                )
                return {"migration": {"ddl_rollback_verified": True}}

            with patch.object(boot, "setup", side_effect=setup) as setup_call:
                response = self.request("setup")
                self.assertTrue(response.json()["ok"])
                setup_call.assert_called_once()
            close.assert_called_once_with()
            self.stub.assert_no_pending_responses()
            self.assertTrue(factory.call_args.kwargs["verify"])
            self.assertEqual(factory.call_args.kwargs["region_name"], boot.REGION)
            self.assertEqual(
                factory.call_args.kwargs["endpoint_url"],
                f"https://secretsmanager.{boot.REGION}.amazonaws.com",
            )
            config = factory.call_args.kwargs["config"]
            self.assertEqual(
                (config.connect_timeout, config.read_timeout, config.retries),
                (3, 4, {"total_max_attempts": 2}),
            )
            for value in [self.admin, *VALUES.values()]:
                self.assertNotIn(value["password"], response.text)

    def test_132_application_reads_only_its_secret_and_closes(self):
        self.enqueue("app-probe")
        with self.runtime("app-probe") as (_, close):

            def probe(value, arn):
                close.assert_called_once_with()
                self.assertEqual((value, arn), (VALUES["fitfinity_app"], ARNS["app"]))
                return {"ddl_denied": True, "migration_role_denied": True}

            with (
                patch.object(boot, "probe", side_effect=probe),
                patch.object(boot, "setup") as setup,
            ):
                self.assertTrue(self.request("app-probe").json()["ok"])
                setup.assert_not_called()
            self.stub.assert_no_pending_responses()
            close.assert_called_once_with()

    def test_133_provider_error_closes_and_redacts_before_sql(self):
        self.stub.add_client_error(
            "get_secret_value",
            service_error_code="AccessDeniedException",
            service_message="password=NEVER_PRINT_ME",
            http_status_code=400,
            expected_params={"SecretId": ARNS["app"], "VersionStage": "AWSCURRENT"},
        )
        with self.runtime() as (_, close), patch.object(boot.psycopg, "connect") as connect:
            response = self.request("setup")
            proof = response.json()
            self.assertFalse(proof["ok"])
            self.assertEqual(proof["stage"], "secret_retrieval")
            self.assertNotIn("NEVER_PRINT_ME", response.text)
            close.assert_called_once_with()
            connect.assert_not_called()
            self.stub.assert_no_pending_responses()

    def test_134_invalid_secret_closes_and_stops_before_sql(self):
        for arn, stages, value in [
            (ARNS["migration"], ["AWSCURRENT"], VALUES["fitfinity_app"]),
            (ARNS["app"], ["AWSPREVIOUS"], VALUES["fitfinity_app"]),
            (ARNS["app"], ["AWSCURRENT"], {"username": "fitfinity_app", "password": "short"}),
        ]:
            self.stub.add_response(
                "get_secret_value",
                {"ARN": arn, "VersionStages": stages, "SecretString": json.dumps(value)},
                {"SecretId": ARNS["app"], "VersionStage": "AWSCURRENT"},
            )
            with self.runtime() as (_, close), patch.object(boot.psycopg, "connect") as connect:
                response = self.request("setup")
                self.assertEqual(response.json()["stage"], "secret_retrieval")
                self.assertFalse(response.json()["ok"])
                close.assert_called_once_with()
                connect.assert_not_called()
                self.stub.assert_no_pending_responses()

    def test_135_actual_loader_and_sdk_reach_both_database_entrypoints(self):
        import sys

        import uvicorn

        for mode, prefix, stage in [
            ("setup", "Setup", "administrator_login"),
            ("app-probe", "Application", "application_login"),
        ]:
            self.enqueue(mode)
            template = op.probe_template(ARNS)
            p = template["Resources"][prefix + "Function"]["Properties"]
            cmd = p["ImageConfig"]["Command"]
            namespace = {"__name__": "__main__"}
            original = Path.read_bytes
            ca_bytes = self.ca.read_bytes()

            def reading(path, ca_bytes=ca_bytes, original=original):
                return (
                    ca_bytes
                    if str(path) == "/app/app/certificates/ap-southeast-1-bundle.pem"
                    else original(path)
                )

            with (
                self.runtime(mode) as (_, close),
                patch.object(sys, "argv", ["-c", cmd[3]]),
                patch.object(uvicorn, "run") as serve,
                patch.object(Path, "read_bytes", reading),
            ):
                exec(compile(cmd[2], "loader", "exec"), namespace)

                def connect(mode=mode, **kwargs):
                    close.assert_called_once_with()
                    self.assertEqual(kwargs["sslmode"], "verify-full")
                    self.assertEqual(kwargs["host"], boot.HOST)
                    self.assertEqual(
                        kwargs["user"], "fitfinity_admin" if mode == "setup" else "fitfinity_app"
                    )
                    raise RuntimeError("offline database stop; password=NEVER_PRINT_ME")

                with patch.object(boot.psycopg, "connect", side_effect=connect) as sql:
                    response = TestClient(serve.call_args.args[0]).post(
                        "/events",
                        json={
                            "action": mode,
                            "nonce": "b" * 32,
                            "bootstrap_source": (ROOT / "test-db-bootstrap.py").read_text(),
                        },
                    )
                    self.assertEqual(response.json()["stage"], stage)
                    self.assertNotIn("NEVER_PRINT_ME", response.text)
                    sql.assert_called_once()
                close.assert_called_once_with()
                self.stub.assert_no_pending_responses()


if __name__ == "__main__":
    unittest.main(verbosity=2)
