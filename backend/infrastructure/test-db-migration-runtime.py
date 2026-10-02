"""Initial test schema only: atomic Alembic/grants, then independent app proof.

The operator bundles this module with the canonical database bootstrap helpers
and a reviewed contract. Credentials never leave the private Lambda runtime.
"""

import hashlib
import json
import os
import re
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

import boto3
import fitfinity_db_shared as shared
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from botocore.config import Config
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401
from app.database import Base
from app.migrations import migration_config

CONTRACT = json.loads(globals()["FITFINITY_MIGRATION_CONTRACT"])  # supplied by the pinned bundle
TARGET = "20260924_0006"
MIGRATOR = "fitfinity_migrator"
APPLICATION = "fitfinity_app"
STAGE = "initialization"
ROOT = Path("/app")
require = shared.require


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def image_files():
    for relative, expected in CONTRACT["files"].items():
        require(
            hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected,
            "image migration file differs",
        )
    config = migration_config()
    scripts = ScriptDirectory.from_config(config)
    require(scripts.get_heads() == [TARGET], "image migration head differs")
    require(
        [r.revision for r in reversed(list(scripts.walk_revisions()))] == CONTRACT["revisions"],
        "image revision chain differs",
    )
    require(
        set(Base.metadata.tables) == set(CONTRACT["tables"]) - {"alembic_version"},
        "image model tables differ",
    )
    return digest(CONTRACT["files"])


def read_rows(connection, statement, parameters=None):
    # Empty bind tuples still enable psycopg's percent-placeholder parser.
    # Catalog SQL contains literal LIKE patterns, so unbound SQL stays unbound.
    cursor = (
        connection.execute(statement)
        if parameters is None
        else connection.execute(statement, parameters)
    )
    return [tuple(row) for row in cursor.fetchall()]


def role_checks(connection, username, arn):
    require(shared.role_state(connection, username, arn), "restricted role absent")
    privileges = shared.permissions(connection, username)
    require(
        connection.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='fitfinity'"
        ).fetchone()
        == ("fitfinity_admin",),
        "database owner differs",
    )
    require(
        connection.execute(
            "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace "
            "WHERE e.extname='btree_gist'"
        ).fetchone()
        == ("public",),
        "required extension absent or moved",
    )
    return privileges


def relations(connection):
    return read_rows(
        connection,
        "SELECT n.nspname, c.relname, c.relkind, pg_get_userbyid(c.relowner), "
        "c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' "
        "AND c.relkind IN ('r','p','v','m','S','f') AND NOT EXISTS "
        "(SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass "
        "AND d.objid=c.oid AND d.deptype='e') ORDER BY n.nspname,c.relname",
    )


def current_state(connection):
    objects = relations(connection)
    if not objects:
        shared.assert_unmigrated(connection)
        return "empty"
    require(
        any(row[:2] == ("public", "alembic_version") for row in objects),
        "unversioned application schema",
    )
    require(
        connection.execute("SELECT version_num FROM public.alembic_version").fetchall()
        == [(TARGET,)],
        "partial or unexpected migration revision",
    )
    return "target"


def table_acl(connection, *, verify):
    """Explicit privileges on known tables. Never grant all/future-table access."""
    for table, allowed in CONTRACT["tables"].items():
        if not verify:
            connection.execute(
                shared.sql.SQL("GRANT {} ON TABLE public.{} TO fitfinity_app").format(
                    shared.sql.SQL(", ".join(allowed)), shared.sql.Identifier(table)
                )
            )
        rows = read_rows(
            connection,
            "SELECT p, has_table_privilege('fitfinity_app',%s,p), "
            "has_table_privilege('fitfinity_app',%s,p || ' WITH GRANT OPTION') "
            "FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE',"
            "'REFERENCES','TRIGGER','MAINTAIN']) p",
            ("public." + table, "public." + table),
        )
        require(
            all(has is (privilege in allowed) and grant is False for privilege, has, grant in rows),
            "runtime table privileges differ",
        )
        # No PUBLIC/unexpected grantee, grant option or per-column bypass.
        acl = read_rows(
            connection,
            "SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END, "
            "a.privilege_type,a.is_grantable FROM pg_class c, LATERAL "
            "aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a "
            "WHERE c.oid=%s::regclass",
            ("public." + table,),
        )
        require(
            all(
                grantee == MIGRATOR
                or (grantee == APPLICATION and privilege in allowed and not grant)
                for grantee, privilege, grant in acl
            ),
            "unexpected table ACL",
        )
        require(
            connection.execute(
                "SELECT count(*) FROM pg_attribute WHERE attrelid=%s::regclass "
                "AND attnum>0 AND NOT attisdropped AND attacl IS NOT NULL",
                ("public." + table,),
            ).fetchone()
            == (0,),
            "unexpected column ACL",
        )


def defaults(connection):
    rows = read_rows(
        connection,
        "SELECT d.defaclnamespace,d.defaclobjtype, "
        "CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END, "
        "a.privilege_type,a.is_grantable FROM pg_default_acl d, "
        "LATERAL aclexplode(d.defaclacl) a WHERE d.defaclrole="
        "(SELECT oid FROM pg_roles WHERE rolname='fitfinity_migrator')",
    )
    require(
        rows and all(row == (0, "f", MIGRATOR, "EXECUTE", False) for row in rows),
        "migration default privileges differ",
    )


def schema_shape(connection):
    objects = relations(connection)
    require(
        objects
        == [("public", name, "r", MIGRATOR, False, False) for name in sorted(CONTRACT["tables"])],
        "schema objects differ",
    )
    routines = read_rows(
        connection,
        "SELECT p.proname,pg_get_function_identity_arguments(p.oid),p.prosrc,"
        "p.prosecdef,pg_get_userbyid(p.proowner),p.prorettype::regtype::text,p.proconfig,"
        "has_function_privilege('fitfinity_app',p.oid,'EXECUTE') FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' "
        "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass "
        "AND d.objid=p.oid AND d.deptype='e') ORDER BY p.proname",
    )
    require(len(routines) == len(CONTRACT["functions"]), "function count differs")
    for name, arguments, source, definer, owner, returns, config, executable in routines:
        require(
            name in CONTRACT["functions"]
            and arguments == ""
            and returns == "trigger"
            and not definer
            and owner == MIGRATOR
            and config is None
            and not executable
            and hashlib.sha256(source.strip().encode()).hexdigest() == CONTRACT["functions"][name],
            "function definition/ownership/access differs",
        )
    require(
        connection.execute(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace, "
            "LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a "
            "WHERE n.nspname='public' AND p.proname LIKE 'ff_%' AND "
            "(a.grantee<>p.proowner OR a.is_grantable)"
        ).fetchone()
        == (0,),
        "unexpected function ACL",
    )
    triggers = read_rows(
        connection,
        "SELECT c.relname,t.tgname,p.proname,t.tgenabled FROM pg_trigger t "
        "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_proc p ON p.oid=t.tgfoid WHERE n.nspname='public' AND NOT t.tgisinternal "
        "ORDER BY c.relname,t.tgname",
    )
    require(triggers == [tuple(row) for row in CONTRACT["triggers"]], "trigger inventory differs")
    require(
        connection.execute(
            "SELECT count(*) FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace "
            "WHERE n.nspname='public' AND NOT k.convalidated"
        ).fetchone()
        == (0,),
        "unvalidated constraints",
    )
    require(
        connection.execute(
            "SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
            "AND (NOT i.indisvalid OR NOT i.indisready)"
        ).fetchone()
        == (0,),
        "invalid indexes",
    )
    return {
        "tables": len(objects),
        "functions": len(routines),
        "triggers": len(triggers),
        "sequences": 0,
    }


def fingerprint(connection):
    """OID-free schema evidence, including checks, keys, indexes and full triggers."""
    queries = {
        "columns": "SELECT c.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),"
        "a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) "
        "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d "
        "ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE n.nspname='public' "
        "AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum",
        "constraints": "SELECT c.relname,k.conname,k.contype,k.convalidated,"
        "pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
        "ORDER BY c.relname,k.conname",
        "indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' "
        "ORDER BY tablename,indexname",
        "triggers": "SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled "
        "FROM pg_trigger t "
        "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname",
        "functions": "SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' "
        "AND p.proname LIKE 'ff_%' ORDER BY p.proname",
    }
    return digest({key: read_rows(connection, query) for key, query in queries.items()})


def seed_and_empty(connection):
    for table in sorted(set(CONTRACT["tables"]) - {"alembic_version", "assessment_form_versions"}):
        require(
            connection.execute(
                shared.sql.SQL("SELECT EXISTS(SELECT 1 FROM public.{})").format(
                    shared.sql.Identifier(table)
                )
            ).fetchone()
            == (False,),
            "initial deployment already contains business data",
        )
    records = read_rows(
        connection,
        "SELECT form_id,version,title,source_filename,source_sha256,layout_release,"
        "layout_sha256,definition FROM public.assessment_form_versions ORDER BY form_id,version",
    )
    keys = [
        "form_id",
        "version",
        "title",
        "source_filename",
        "source_sha256",
        "layout_release",
        "layout_sha256",
        "definition",
    ]
    actual = [dict(zip(keys, row, strict=True)) for row in records]
    require(digest(actual) == CONTRACT["assessment_seed_sha256"], "assessment seed differs")
    return len(records)


def proof_marker(connection, *, create):
    value = "fitfinity-test-schema-v1:" + digest(CONTRACT) + ":" + fingerprint(connection)
    if create:
        connection.execute(
            shared.sql.SQL("COMMENT ON TABLE public.alembic_version IS {}").format(
                shared.sql.Literal(value)
            )
        )
    require(
        connection.execute(
            "SELECT obj_description('public.alembic_version'::regclass,'pg_class')"
        ).fetchone()
        == (value,),
        "schema fingerprint differs",
    )
    return value.rsplit(":", 1)[1]


def migrate(value, arn):
    global STAGE
    started = monotonic()
    engine = create_engine(
        "postgresql+psycopg://",
        creator=lambda: shared.connect(value),
        isolation_level="READ COMMITTED",
        poolclass=NullPool,
        hide_parameters=True,
        echo=False,
    )
    try:
        with engine.begin() as connection:
            raw = connection.connection.driver_connection
            STAGE = "migration_identity"
            proof = shared.tls(raw, MIGRATOR)
            proof["privileges"] = role_checks(raw, MIGRATOR, arn)
            raw.execute("SET LOCAL search_path TO public, pg_catalog")
            raw.execute("SET LOCAL statement_timeout=45000")
            require(
                raw.execute("SELECT pg_try_advisory_xact_lock(418638389566)").fetchone() == (True,),
                "another database operation is active",
            )
            defaults(raw)
            STAGE = "migration_baseline"
            before = current_state(raw)
            if before == "empty":
                STAGE = "alembic_upgrade"
                config = migration_config()
                config.attributes["connection"] = connection
                command.upgrade(config, TARGET)
            STAGE = "schema_validation"
            require(current_state(raw) == "target", "target revision missing")
            proof["schema"] = schema_shape(raw)
            require(
                compare_metadata(
                    MigrationContext.configure(connection, opts={"compare_type": True}),
                    Base.metadata,
                )
                == [],
                "model/schema differs",
            )
            proof["assessment_forms"] = seed_and_empty(raw)
            STAGE = "runtime_grants"
            table_acl(raw, verify=before == "target")
            STAGE = "schema_fingerprint"
            proof["schema_sha256"] = proof_marker(raw, create=before == "empty")
            require(monotonic() - started < 95, "migration budget exhausted before commit")
            STAGE = "migration_commit"
        return {
            **proof,
            "target_revision": TARGET,
            "previous_state": before,
            "migrations_applied": True,
            "committed": True,
            "newly_applied": before == "empty",
            "runtime_grants_verified": True,
            "business_rows_created": False,
        }
    finally:
        engine.dispose()


def application_proof(value, arn):
    global STAGE
    with shared.connect(value) as connection:
        STAGE = "application_identity"
        proof = shared.tls(connection, APPLICATION)
        proof["privileges"] = role_checks(connection, APPLICATION, arn)
        STAGE = "application_schema"
        require(current_state(connection) == "target", "target revision missing")
        proof["schema"] = schema_shape(connection)
        defaults(connection)
        table_acl(connection, verify=True)
        proof["assessment_forms"] = seed_and_empty(connection)
        proof["schema_sha256"] = proof_marker(connection, create=False)
        STAGE = "application_permission_denials"
        for statement in (
            "CREATE TABLE public.fitfinity_schema_forbidden(id integer)",
            "SET ROLE fitfinity_migrator",
            "UPDATE public.alembic_version SET version_num=version_num WHERE false",
            "DELETE FROM public.alembic_version WHERE false",
            "INSERT INTO public.alembic_version(version_num) VALUES ('forbidden')",
            "UPDATE public.assessment_form_versions SET title=title WHERE false",
            "TRUNCATE public.content_entries",
        ):
            shared.denied(connection, statement)
        STAGE = "application_dml_rollback"
        identity = uuid4()
        # Real insert/update exercise the version trigger without creating any staff identity.
        with connection.transaction(force_rollback=True):
            connection.execute(
                "INSERT INTO public.content_entries(id,key,title,body) "
                "VALUES (%s,%s,'Permission probe','Synthetic rollback only')",
                (identity, "migration-probe/" + identity.hex),
            )
            connection.execute(
                "UPDATE public.content_entries SET version=version+1,title='Verified' WHERE id=%s",
                (identity,),
            )
            require(
                connection.execute(
                    "SELECT title,version FROM public.content_entries WHERE id=%s", (identity,)
                ).fetchone()
                == ("Verified", 2),
                "application DML/trigger proof",
            )
        require(
            connection.execute(
                "SELECT count(*) FROM public.content_entries WHERE id=%s", (identity,)
            ).fetchone()
            == (0,),
            "application probe persisted",
        )
        return {
            **proof,
            "target_revision": TARGET,
            "runtime_grants_verified": True,
            "ddl_denied": True,
            "migration_role_denied": True,
            "migration_metadata_writes_denied": True,
            "seed_writes_denied": True,
            "truncate_denied": True,
            "dml_and_trigger_rollback_verified": True,
        }


async def run(request):
    global STAGE
    nonce = None
    runtime_identity = None
    ca_sha256 = None
    try:
        STAGE = "request_schema"
        raw = await request.body()
        require(len(raw) <= 256, "request too large")
        event = json.loads(raw)
        nonce = event.get("nonce")
        mode = os.environ["FITFINITY_DB_ACCESS_MODE"]
        require(
            mode in {"migrate", "migration-app-probe"}
            and event == {"action": event.get("action"), "nonce": nonce}
            and event["action"] in {mode, "preflight"}
            and isinstance(nonce, str)
            and re.fullmatch(r"[a-f0-9]{32}", nonce),
            "unexpected migration request",
        )
        STAGE = "exception_window"
        require(
            datetime.now(UTC) < datetime(2026, 9, 29, 15, 59, tzinfo=UTC),
            "test image exception expired",
        )
        STAGE = "runtime_identity"
        runtime_identity = dict(
            zip(
                ("uid", "euid", "gid", "egid"),
                (os.getuid(), os.geteuid(), os.getgid(), os.getegid()),
                strict=True,
            )
        )
        require(
            tuple(runtime_identity.values()) in {(993, 993, 990, 990), (10001,) * 4},
            "runtime identity differs",
        )
        STAGE = "tls_bundle"
        ca_sha256 = hashlib.sha256(shared.CA.read_bytes()).hexdigest()
        require(ca_sha256 == shared.CA_SHA256, "CA differs")
        STAGE = "image_migrations"
        files_sha = image_files()
        STAGE = "secret_reference"
        key = "migration" if mode == "migrate" else "app"
        username = MIGRATOR if mode == "migrate" else APPLICATION
        variable = (
            "FITFINITY_MIGRATION_DB_SECRET_ARN"
            if mode == "migrate"
            else "FITFINITY_APP_DB_SECRET_ARN"
        )
        arn = os.environ[variable]
        require(arn == CONTRACT["secret_arns"][key], "secret reference differs")
        if event["action"] == "preflight":
            return {
                "ok": True,
                "nonce": nonce,
                "mode": mode,
                "preflight_only": True,
                "runtime_identity": runtime_identity,
                "ca_sha256": ca_sha256,
                "migration_files_sha256": files_sha,
                "target_revision": TARGET,
            }
        STAGE = "secret_retrieval"
        with closing(
            boto3.client(
                "secretsmanager",
                region_name=shared.REGION,
                endpoint_url=f"https://secretsmanager.{shared.REGION}.amazonaws.com",
                verify=True,
                config=Config(connect_timeout=3, read_timeout=4, retries={"total_max_attempts": 2}),
            )
        ) as client:
            value = shared.secret(client, arn, username)
        proof = migrate(value, arn) if mode == "migrate" else application_proof(value, arn)
        return {"ok": True, "nonce": nonce, "mode": mode, "proof": proof}
    except Exception as error:
        original = getattr(error, "orig", error)
        code = getattr(original, "sqlstate", None)
        return {
            "ok": False,
            "nonce": nonce,
            "stage": STAGE,
            "error_type": type(original).__name__,
            "sqlstate": code
            if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code)
            else None,
            "runtime_identity": runtime_identity,
            "ca_sha256": ca_sha256,
        }
