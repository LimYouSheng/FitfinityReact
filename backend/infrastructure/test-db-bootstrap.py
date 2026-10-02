"""One-purpose private setup/probe service; never imports or starts the staff API."""

import hashlib
import json
import os
import re
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import boto3
import psycopg
import uvicorn
from botocore.config import Config
from fastapi import FastAPI, Request
from psycopg import sql

ACCOUNT = "418638389566"
REGION = "ap-southeast-1"
HOST = "fitfinity-test-db.c1ak66620gza.ap-southeast-1.rds.amazonaws.com"
ADMIN_ARN = (
    "arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:rds!db-"
    "06e1ffee-8cb6-422d-96d2-f941519d6a9d-f2CW3j"
)
CA = Path("/app/app/certificates/ap-southeast-1-bundle.pem")
CA_SHA256 = "3c696020a3b7c6721085d182211c28024ab01873ade35dcc7eeebb89c20ee979"
MARKER = "fitfinity-test-db-access-v1:"
ROLES = {"fitfinity_app": 10, "fitfinity_migrator": 3}
STAGE = "initialization"
app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def secret(client, arn, username):
    response = client.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
    require(
        response.get("ARN") == arn and "AWSCURRENT" in response.get("VersionStages", []),
        "secret identity",
    )
    value = json.loads(response["SecretString"])
    require(value.get("username") == username, "secret username")
    password = value.get("password")
    minimum = 1 if username == "fitfinity_admin" else 32
    require(isinstance(password, str) and minimum <= len(password) <= 128, "secret password")
    if username != "fitfinity_admin":
        require(set(value) == {"username", "password"}, "secret fields")
    return value


def connect(value):
    return psycopg.connect(
        host=HOST,
        port=5432,
        dbname="fitfinity",
        user=value["username"],
        password=value["password"],
        sslmode="verify-full",
        sslrootcert=str(CA),
        connect_timeout=5,
        autocommit=True,
        options="-c statement_timeout=10000 -c lock_timeout=2000 -c idle_in_transa"
        "ction_session_timeout=15000",
    )


def tls(connection, username):
    # rds.force_ssl is verified by the operator through RDS parameter-group APIs.
    # This instance does not expose that managed setting as a SQL GUC. Verify
    # this connection's actual encryption after libpq's verify-full handshake.
    row = connection.execute(
        "SELECT current_database(), current_user, current_setting('server_version_num')::int, "
        "ssl, version FROM pg_stat_ssl WHERE pid=pg_backend_pid()"
    ).fetchone()
    require(
        row and row[0:2] == ("fitfinity", username) and 170000 <= row[2] < 180000,
        "database identity",
    )
    require(
        row[3] is True and row[4] in {"TLSv1.2", "TLSv1.3"},
        "TLS verification",
    )
    return {
        "database": row[0],
        "user": row[1],
        "sslmode": "verify-full",
        "tls": row[4],
        "server_version_num": row[2],
    }


def role_state(connection, username, arn):
    row = connection.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, "
        "rolinherit, rolcanlogin, rolconnlimit, shobj_description(oid, 'pg_authid') "
        "FROM pg_roles WHERE rolname=%s",
        (username,),
    ).fetchone()
    if row is None:
        return False
    require(
        row == (False, False, False, False, False, False, True, ROLES[username], MARKER + arn),
        "role drift",
    )
    memberships = connection.execute(
        "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FRO"
        "M pg_roles WHERE rolname=%s)",
        (username,),
    ).fetchone()[0]
    require(memberships == 0, "unexpected inherited role")
    return True


def assert_unmigrated(connection):
    # Stop before touching permissions when application relations already exist.
    row = connection.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' "
        "AND c.relkind IN ('r','p','v','m','S','f') "
        "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass "
        "AND d.objid=c.oid AND d.deptype='e')"
    ).fetchone()
    require(row[0] == 0, "database already contains application relations")
    routines = connection.execute(
        "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='public' AND NOT EXISTS (SELECT 1 FROM pg_depend d "
        "WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')"
    ).fetchone()
    require(routines[0] == 0, "database already contains application routines")
    owner = connection.execute(
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='fitfinity'"
    ).fetchone()
    require(owner == ("fitfinity_admin",), "database owner differs")


def scram(connection, username, password):
    # libpq prepares a SCRAM verifier; plaintext never becomes part of SQL text.
    return connection.pgconn.encrypt_password(
        password.encode("ascii"), username.encode("ascii"), b"scram-sha-256"
    ).decode("ascii")


def permissions(connection, username):
    row = connection.execute(
        "SELECT has_database_privilege(current_user,'fitfinity','CONNECT'), "
        "has_database_privilege(current_user,'fitfinity','CREATE'), "
        "has_database_privilege(current_user,'fitfinity','TEMP'), "
        "has_schema_privilege(current_user,'public','USAGE'), "
        "has_schema_privilege(current_user,'public','CREATE')"
    ).fetchone()
    expected = (True, False, False, True, username == "fitfinity_migrator")
    require(row == expected, "effective database privileges differ")
    return dict(
        zip(
            ["connect", "create_schema", "temporary_objects", "schema_usage", "schema_create"],
            row,
            strict=True,
        )
    )


def denied(connection, statement):
    # Rollback even if the forbidden operation unexpectedly succeeds.
    try:
        with connection.transaction(force_rollback=True):
            connection.execute(statement)
    except psycopg.errors.InsufficientPrivilege:
        return True
    raise RuntimeError("forbidden operation succeeded")


def probe(value, arn):
    username = value["username"]
    with connect(value) as connection:
        proof = tls(connection, username)
        require(role_state(connection, username, arn), "role absent")
        proof["privileges"] = permissions(connection, username)
        if username == "fitfinity_app":
            denied(connection, "CREATE TABLE public.fitfinity_permission_probe (id integer)")
            denied(connection, "SET ROLE fitfinity_migrator")
            proof.update(ddl_denied=True, migration_role_denied=True)
        else:
            connection.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
            with connection.transaction(force_rollback=True):
                connection.execute("CREATE TABLE public.fitfinity_permission_probe (id integer)")
                connection.execute("INSERT INTO public.fitfinity_permission_probe VALUES (1)")
                require(
                    connection.execute(
                        "SELECT count(*) FROM public.fitfinity_permission_probe"
                    ).fetchone()
                    == (1,),
                    "migration DDL test",
                )
            require(
                connection.execute(
                    "SELECT to_regclass('public.fitfinity_permission_probe')"
                ).fetchone()
                == (None,),
                "probe rollback",
            )
            proof["ddl_rollback_verified"] = True
        return proof


def setup(admin, values, arns):
    global STAGE
    with connect(admin) as connection:
        admin_proof = tls(connection, "fitfinity_admin")
        # Transaction-scoped lock also serializes simultaneous operator invocations.
        with connection.transaction():
            require(
                connection.execute("SELECT pg_try_advisory_xact_lock(418638389566)").fetchone()[0],
                "setup already running",
            )
            assert_unmigrated(connection)
            existing = [role_state(connection, name, arns[name]) for name in ROLES]
            require(len(set(existing)) == 1, "partial or unrelated roles")
            created = not all(existing)
            if created:
                STAGE = "role_creation"
                # SQL audit/error logging must not capture credential verifiers.
                connection.execute("SET LOCAL log_statement='none'")
                connection.execute("SET LOCAL log_min_error_statement='panic'")
                for name, limit in ROLES.items():
                    connection.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLIC"
                            "ATION "
                            "NOBYPASSRLS NOINHERIT CONNECTION LIMIT {} PASSWORD {}"
                        ).format(
                            sql.Identifier(name),
                            sql.Literal(limit),
                            sql.Literal(scram(connection, name, values[name]["password"])),
                        )
                    )
                    connection.execute(
                        sql.SQL("COMMENT ON ROLE {} IS {}").format(
                            sql.Identifier(name), sql.Literal(MARKER + arns[name])
                        )
                    )
                    connection.execute(
                        sql.SQL(
                            "ALTER ROLE {} IN DATABASE fitfinity SET search_path=public,pg_temp"
                        ).format(sql.Identifier(name))
                    )
                STAGE = "database_permissions"
                connection.execute("REVOKE ALL ON DATABASE fitfinity FROM PUBLIC")
                connection.execute(
                    "GRANT CONNECT ON DATABASE fitfinity TO fitfinity_app,fitfinity_migrator"
                )
                connection.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
                connection.execute(
                    "GRANT USAGE ON SCHEMA public TO fitfinity_app,fitfinity_migrator"
                )
                connection.execute("GRANT CREATE ON SCHEMA public TO fitfinity_migrator")
                # Master installs this trusted extension so the migrator needs no database CREATE.
                connection.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public")
            else:
                STAGE = "existing_role_verification"
                require(
                    connection.execute(
                        "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid"
                        "=e.extnamespace WHERE e.extname='btree_gist'"
                    ).fetchone()
                    == ("public",),
                    "extension differs",
                )
        # New connections use the real role passwords after the atomic setup commits.
        # A failed postcheck preserves state; a rerun verifies without resetting passwords.
        STAGE = "migration_login"
        with connect(values["fitfinity_migrator"]) as migrator:
            tls(migrator, "fitfinity_migrator")
            # Safe to finish this hardening after a prior post-commit interruption.
            migrator.execute("ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
            default = migrator.execute(
                "SELECT NOT EXISTS (SELECT 1 FROM pg_default_acl d, LATERAL aclexp"
                "lode(d.defaclacl) a "
                "WHERE d.defaclrole=(SELECT oid FROM pg_roles WHERE rolname=current_user) "
                "AND d.defaclnamespace=0 AND d.defaclobjtype='f' AND a.grantee=0 A"
                "ND a.privilege_type='EXECUTE'), "
                "EXISTS (SELECT 1 FROM pg_default_acl WHERE defaclrole=(SELECT oid"
                " FROM pg_roles WHERE rolname=current_user) "
                "AND defaclnamespace=0 AND defaclobjtype='f')"
            ).fetchone()
            require(default == (True, True), "function defaults need review")
        return {
            "created_roles": created,
            "admin_tls": admin_proof,
            "migration": probe(values["fitfinity_migrator"], arns["fitfinity_migrator"]),
        }


def diagnose_database(admin, arns):
    """Inspect fixed prerequisites under read-only transactions; never run setup."""
    global STAGE
    checks = {}
    STAGE = "diagnostic_administrator_connection"
    with connect(admin) as connection:
        with connection.transaction(force_rollback=True):
            STAGE = "diagnostic_read_only"
            connection.execute("SET TRANSACTION READ ONLY")
            require(
                connection.execute("SHOW transaction_read_only").fetchone() == ("on",),
                "read-only transaction not verified",
            )

            def check(label, operation):
                global STAGE
                STAGE = "diagnostic_" + label
                try:
                    with connection.transaction(force_rollback=True):
                        result = operation()
                    checks[label] = {"ok": True, "result": result}
                except Exception as error:
                    code = getattr(error, "sqlstate", None)
                    checks[label] = {
                        "ok": False,
                        "error_type": type(error).__name__,
                        "sqlstate": code
                        if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code)
                        else None,
                    }

            def connection_identity():
                row = connection.execute(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version_num')::int, ssl, version "
                    "FROM pg_stat_ssl WHERE pid=pg_backend_pid()"
                ).fetchone()
                require(
                    row
                    and row[:2] == ("fitfinity", "fitfinity_admin")
                    and 170000 <= row[2] < 180000
                    and row[3] is True
                    and row[4] in {"TLSv1.2", "TLSv1.3"},
                    "diagnostic database identity/TLS differs",
                )
                return {"sslmode": "verify-full", "tls": row[4], "server_version_num": row[2]}

            def force_ssl_setting():
                value = connection.execute(
                    "SELECT current_setting('rds.force_ssl', true)"
                ).fetchone()[0]
                return {
                    "present_in_sql": value is not None,
                    "enabled": None if value is None else value in {"1", "on"},
                }

            check("connection_identity_tls", connection_identity)
            check("force_ssl_sql_setting", force_ssl_setting)
            check("tls_query", lambda: tls(connection, "fitfinity_admin"))
            check("unmigrated_schema", lambda: assert_unmigrated(connection))
            for name in ROLES:
                check(name + "_role", lambda name=name: role_state(connection, name, arns[name]))
    return {
        "database_diagnostic_only": True,
        "read_only": True,
        "rolled_back": True,
        "all_checks_passed": all(item["ok"] for item in checks.values()),
        "checks": checks,
    }


@app.get("/health/live")
def health():
    return {"status": "ok"}


@app.post("/events")
async def run(request: Request):
    global STAGE
    nonce = None
    runtime_identity = None
    ca_sha256 = None
    try:
        STAGE = "request_size"
        raw = await request.body()
        require(len(raw) <= 256, "request too large")
        event = json.loads(raw)
        nonce = event.get("nonce")
        STAGE = "request_schema"
        mode = os.environ["FITFINITY_DB_ACCESS_MODE"]
        action = event.get("action")
        require(
            mode in {"setup", "app-probe"}
            and (
                action in {mode, "preflight"}
                or (mode == "setup" and action == "database-diagnostic")
            )
            and event == {"action": action, "nonce": nonce},
            "request differs",
        )
        STAGE = "request_nonce"
        require(isinstance(nonce, str) and re.fullmatch(r"[a-f0-9]{32}", nonce), "nonce differs")
        STAGE = "exception_window"
        require(
            datetime.now(UTC) < datetime(2026, 9, 29, 15, 59, tzinfo=UTC), "test exception expired"
        )
        STAGE = "runtime_identity"
        runtime_identity = {
            "uid": os.getuid(),
            "euid": os.geteuid(),
            "gid": os.getgid(),
            "egid": os.getegid(),
        }
        # Docker's configured user and the exact non-root Lambda identity observed
        # in both private preflights. AWS does not promise a permanent numeric UID.
        require(
            tuple(runtime_identity[key] for key in ("uid", "euid", "gid", "egid"))
            in {(10001, 10001, 10001, 10001), (993, 993, 990, 990)},
            "runtime user changed",
        )
        STAGE = "tls_bundle"
        ca_sha256 = hashlib.sha256(CA.read_bytes()).hexdigest()
        require(ca_sha256 == CA_SHA256, "CA changed")
        STAGE = "secret_reference"
        arns = {"fitfinity_app": os.environ["FITFINITY_APP_DB_SECRET_ARN"]}
        if mode == "setup":
            arns["fitfinity_migrator"] = os.environ["FITFINITY_MIGRATION_DB_SECRET_ARN"]
        for name, arn in arns.items():
            suffix = "app" if name == "fitfinity_app" else "migration"
            require(
                re.fullmatch(
                    rf"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:fitfinity/test/database/{suffix}-[A-Za-z0-9]{{6}}",
                    arn,
                ),
                "secret reference differs",
            )
        if action == "preflight":
            return {
                "ok": True,
                "nonce": nonce,
                "mode": mode,
                "preflight_only": True,
                "runtime_identity": runtime_identity,
                "ca_sha256": ca_sha256,
            }
        STAGE = "secret_client"
        with closing(
            boto3.client(
                "secretsmanager",
                region_name=REGION,
                endpoint_url=f"https://secretsmanager.{REGION}.amazonaws.com",
                verify=True,
                config=Config(connect_timeout=3, read_timeout=4, retries={"total_max_attempts": 2}),
            )
        ) as client:
            STAGE = "secret_retrieval"
            if action != "database-diagnostic":
                values = {name: secret(client, arn, name) for name, arn in arns.items()}
            if mode == "setup":
                admin = secret(client, ADMIN_ARN, "fitfinity_admin")
        if action == "database-diagnostic":
            proof = {"database_diagnostic": diagnose_database(admin, arns)}
        elif mode == "setup":
            STAGE = "administrator_login"
            proof = setup(admin, values, arns)
        else:
            STAGE = "application_login"
            proof = {"application": probe(values["fitfinity_app"], arns["fitfinity_app"])}
        return {"ok": True, "nonce": nonce, "mode": mode, **proof}
    except Exception as error:
        # Never return provider/database exception text, connection URLs or secret values.
        code = getattr(error, "sqlstate", None)
        return {
            "ok": False,
            "nonce": nonce,
            "stage": STAGE,
            "runtime_identity": runtime_identity,
            "ca_sha256": ca_sha256,
            "error_type": type(error).__name__,
            "sqlstate": code
            if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code)
            else None,
        }


if __name__ == "__main__":
    uvicorn.run(
        app, host="0.0.0.0", port=8080, access_log=False, log_level="error", proxy_headers=False
    )
