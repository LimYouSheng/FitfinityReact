"""Apply reviewed current-table privileges without granting unknown or future objects."""

import json
from pathlib import Path

from psycopg import sql
from sqlalchemy import text

from app import models  # noqa: F401 -- register the authoritative table inventory
from app.database import Base


class RuntimeGrantsRefused(RuntimeError):
    """Refuse privilege drift without exposing database credentials or row contents."""


def require(value, message):
    if not value:
        raise RuntimeGrantsRefused(message)


def contract():
    """Require explicit privileges for every current model table and the version ledger."""
    value = json.loads(Path(__file__).with_name("runtime-grants.json").read_text())
    require(set(value) == {"schema_revision", "tables"}, "Unexpected grant contract fields")
    require(
        set(value["tables"]) == set(Base.metadata.tables) | {"alembic_version"},
        "Runtime grant inventory differs from current models",
    )
    for actions in value["tables"].values():
        require(
            isinstance(actions, list)
            and actions
            and len(set(actions)) == len(actions)
            and set(actions) <= {"SELECT", "INSERT", "UPDATE", "DELETE"},
            "Unexpected runtime privilege",
        )
    return value


def reconcile(
    connection, *, expected_migrator, target_revision, runtime_role="fitfinity_app", apply=False
):
    """Refuse excessive privileges first, then grant only the reviewed missing table access."""
    specification = contract()
    require(specification["schema_revision"] == target_revision, "Grant schema revision differs")
    require(
        connection.scalar(text("SELECT current_user")) == expected_migrator,
        "Migration grant identity differs",
    )
    role = connection.execute(
        text(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
            "rolbypassrls, rolinherit, rolcanlogin "
            "FROM pg_roles WHERE rolname=:role"
        ),
        {"role": runtime_role},
    ).one_or_none()
    require(
        role is not None and not any(role[:6]) and role[6],
        "Runtime role is absent or has elevated attributes",
    )
    require(
        not connection.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_auth_members WHERE member="
                "(SELECT oid FROM pg_roles WHERE rolname=:role))"
            ),
            {"role": runtime_role},
        ),
        "Runtime role membership requires review",
    )
    require(
        not connection.scalar(
            text(
                "SELECT has_schema_privilege(:role, 'public', 'CREATE') OR "
                "has_database_privilege(:role, current_database(), 'CREATE') OR "
                "has_database_privilege(:role, current_database(), 'TEMP')"
            ),
            {"role": runtime_role},
        ),
        "Runtime schema/database write privileges require review",
    )
    require(
        connection.scalar(
            text(
                "SELECT has_database_privilege(:role,current_database(),'CONNECT') "
                "AND has_schema_privilege(:role,'public','USAGE')"
            ),
            {"role": runtime_role},
        ),
        "Runtime database/schema access is missing",
    )
    require(
        not connection.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_default_acl d, LATERAL aclexplode(d.defaclacl) a "
                "WHERE d.defaclobjtype='r' AND (a.grantee=0 OR "
                "a.grantee=(SELECT oid FROM pg_roles WHERE rolname=:role)))"
            ),
            {"role": runtime_role},
        ),
        "Future-table grants require review",
    )
    rows = connection.execute(
        text(
            "SELECT c.relname, pg_get_userbyid(c.relowner), "
            "EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=c.oid "
            "AND a.attacl IS NOT NULL) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY c.relname"
        )
    ).all()
    require(
        {row[0] for row in rows} == set(specification["tables"])
        and all(owner == expected_migrator and not columns for _, owner, columns in rows),
        "Table inventory, ownership or column grants differ",
    )
    privileges = (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "REFERENCES",
        "TRIGGER",
        "MAINTAIN",
    )
    missing = []
    for table, allowed in specification["tables"].items():
        reference = 'public."' + table.replace('"', '""') + '"'
        actual = connection.execute(
            text(
                "SELECT p, has_table_privilege(:role,:table,p), "
                "has_table_privilege(:role,:table,p || ' WITH GRANT OPTION') "
                "FROM unnest(CAST(:privileges AS text[])) p"
            ),
            {"role": runtime_role, "table": reference, "privileges": list(privileges)},
        ).all()
        require(
            all(
                not option and (not enabled or privilege in allowed)
                for privilege, enabled, option in actual
            ),
            "Excess runtime table privilege",
        )
        require(
            not connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_class c, LATERAL "
                    "aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a "
                    "WHERE c.oid=CAST(:table AS regclass) AND a.grantee<>c.relowner "
                    "AND a.grantee<>(SELECT oid FROM pg_roles WHERE rolname=:role))"
                ),
                {"table": reference, "role": runtime_role},
            ),
            "Unexpected table grantee",
        )
        needed = [
            privilege for privilege, enabled, _ in actual if privilege in allowed and not enabled
        ]
        if needed:
            missing.append((table, needed))
    require(apply or not missing, "Runtime table grants are incomplete")
    if apply:
        with connection.connection.driver_connection.cursor() as cursor:
            for table, needed in missing:
                cursor.execute(
                    sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                        sql.SQL(", ").join(sql.SQL(action) for action in needed),
                        sql.Identifier("public", table),
                        sql.Identifier(runtime_role),
                    )
                )
        reconcile(
            connection,
            expected_migrator=expected_migrator,
            target_revision=target_revision,
            runtime_role=runtime_role,
            apply=False,
        )
