"""Bind rollout artifacts to one source, target, frontend inventory and observed schema."""

import hashlib
import json
import re
from datetime import UTC, datetime

from deployment_profile import identities
from hosting_frontend import inventory, manifest_hash
from operator_checks import require
from release_image_validation import validate_scan_acceptance
from release_readiness import migration_chain


def file_hash(path):
    """Hash an ordinary reviewed file without following redirected paths."""
    require(path.is_file() and not path.is_symlink(), "Missing or redirected release file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observed_catalog(probe, *, source, profile_sha256, sql_path):
    """Bind the private observation to its release target, source and packaged SQL."""
    payload = probe.get("receipt")
    require(
        probe.get("state") == "observed"
        and probe.get("source_sha") == source
        and probe.get("profile_sha256") == profile_sha256
        and isinstance(payload, dict)
        and payload.get("source_sha") == source
        and payload.get("sql_sha256") == file_hash(sql_path)
        and isinstance(payload.get("catalog"), dict),
        "Current-source private catalog receipt required",
    )
    return payload["catalog"]


def catalog_matches(catalog, grants, *, database, now):
    """Require fresh schema and exact current-table runtime access from the private observer."""
    observed = datetime.fromisoformat(catalog.get("observed_at", ""))
    require(
        observed.tzinfo is not None
        and 0 <= now - observed.timestamp() <= 3600
        and catalog.get("database") == database
        and catalog.get("database_user") == "fitfinity_migrator"
        and catalog.get("transaction_read_only") == "on"
        and catalog.get("alembic_revisions") == [grants["schema_revision"]],
        "Fresh target schema observation required",
    )
    tables = catalog.get("tables", [])
    require(isinstance(tables, list), "Complete catalog table inventory required")
    actual = {row.get("name"): row for row in tables}
    require(
        len(actual) == len(tables) and set(actual) == set(grants["tables"]),
        "Catalog table inventory differs from the release grant contract",
    )
    permissions = {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
    for name, actions in grants["tables"].items():
        row = actual[name]
        privileges = row.get("runtime_privileges", {})
        require(
            row.get("owner") == "fitfinity_migrator"
            and row.get("row_security") is False
            and row.get("force_row_security") is False
            and set(privileges) == permissions
            and all(
                type(privileges[action]) is bool and privileges[action] == (action in actions)
                for action in permissions
            ),
            "Observed runtime table permissions differ",
        )
    roles = catalog.get("roles", [])
    require(
        len(roles) == 2
        and {row.get("name") for row in roles} == {"fitfinity_app", "fitfinity_migrator"}
        and all(
            row.get(key) is False
            for row in roles
            for key in ("superuser", "create_role", "create_database", "bypass_row_security")
        ),
        "Observed database roles have unexpected authority",
    )
    runtime = next(row for row in roles if row["name"] == "fitfinity_app")
    require(
        all(runtime.get(key) is True for key in ("login", "database_connect", "schema_usage")),
        "Observed runtime login, database CONNECT and public schema USAGE are required",
    )
    return observed.isoformat()


def validate(
    frontend,
    folder,
    image,
    upgrade,
    probe,
    *,
    repo,
    source_inventory,
    profile,
    database,
    schema_action,
    now,
):
    """Validate trusted-workflow artifact contents without cloud calls or deployment authority."""
    target = identities(profile)
    source = source_inventory.get("revision", "")
    require(
        re.fullmatch(r"[a-f0-9]{40}", source) and source_inventory.get("git_tree_verified") is True,
        "Verified local source inventory required",
    )
    require(
        frontend.get("source_sha") == source
        and frontend.get("profile_sha256") == target["profile_sha256"]
        and frontend.get("frontend_source") == source_inventory
        and frontend.get("frontend_source_after_build") == source_inventory,
        "Frontend producer source or target differs",
    )
    files = inventory(folder)
    require(files == frontend.get("frontend_manifest"), "Frontend bytes differ from their manifest")
    manifest = manifest_hash(files)
    build = frontend.get("frontend_build", {})
    require(
        build
        == {
            "mode": "api",
            "base_path": "/",
            "api_base_url": "",
            "pwa_verified": True,
            "files": len(files),
            "manifest_sha256": manifest,
        },
        "Frontend API mode, PWA or manifest binding differs",
    )
    dependencies = frontend.get("frontend_dependencies", {})
    require(
        dependencies.get("npm_ls_passed") is True
        and dependencies.get("package_lock_sha256") == file_hash(repo / "package-lock.json"),
        "Frontend dependency binding differs",
    )
    required = {}
    for name in source_inventory.get("files", {}):
        require(
            isinstance(name, str) and not name.startswith("/") and ".." not in name.split("/"),
            "Unsafe source inventory path",
        )
        if name.startswith("backend/"):
            required[name] = file_hash(repo / name)
    require(
        "backend/Dockerfile" in required and image.get("source_files") == required,
        "Published backend file inventory differs from the verified checkout",
    )
    image_digest = image.get("image_digest", "")
    require(
        re.fullmatch(r"sha256:[a-f0-9]{64}", image_digest)
        and image.get("revision") == source
        and image.get("profile_sha256") == target["profile_sha256"]
        and image.get("account") == target["account"]
        and image.get("region") == target["region"]
        and image.get("image_uri")
        == target["registry"] + "/" + target["image_repository"] + "@" + image_digest
        and all(
            image.get(key) is True
            for key in ("candidate_ready", "image_published", "scan_policy_passed")
        ),
        "Exact target image publication receipt required",
    )
    if image.get("scan_acceptance", {}).get("kind") == "developer_exception":
        validate_scan_acceptance(
            image, image.get("scan_pages", []), datetime.fromtimestamp(now, UTC), profile=profile
        )
    chain = migration_chain(repo / "backend/migrations/versions")
    grants = json.loads((repo / "backend/app/runtime-grants.json").read_text())
    require(grants["schema_revision"] == chain[-1]["revision"], "Runtime grant schema differs")
    require(schema_action in {"unchanged", "upgrade"}, "Explicit schema action required")
    if schema_action == "unchanged":
        require(upgrade is None, "Do not discard or reinterpret an upgrade receipt")
    else:
        require(isinstance(upgrade, dict), "Completed upgrade receipt required")
        identity, result = upgrade.get("identity", {}), upgrade.get("result", {})
        require(
            upgrade.get("state") in {"upgraded", "already_at_target"}
            and result.get("outcome") == upgrade["state"]
            and result.get("source_sha") == source
            and result.get("schema") == chain[-1]["revision"]
            and result.get("from_revision") in {row["revision"] for row in chain[:-1]}
            and re.fullmatch(r"[a-f0-9]{32}", result.get("operation_id", ""))
            and identity.get("FitfinityOperation") == result["operation_id"]
            and identity.get("FitfinitySource") == source
            and identity.get("FitfinityProfile") == target["profile_sha256"]
            and re.fullmatch(r"[a-f0-9]{64}", identity.get("FitfinityTemplate", "")),
            "Completed same-source upgrade and grant receipt required",
        )
    catalog = observed_catalog(
        probe,
        source=source,
        profile_sha256=target["profile_sha256"],
        sql_path=repo / "backend/infrastructure/read-schema.sql",
    )
    observed = catalog_matches(catalog, grants, database=database, now=now)
    return {
        "decision": "HOLD",
        "source_sha": source,
        "profile_sha256": target["profile_sha256"],
        "image_digest": image_digest,
        "frontend_sha256": manifest,
        "frontend_prefix": f"releases/{source}/{manifest}",
        "schema": grants["schema_revision"],
        "catalog_observed_at": observed,
        "schema_action": schema_action,
        "required_image_files": required,
        "remaining": (
            "Fresh live image scan, owned resources, uploaded frontend, "
            "maintenance and exact change-set review"
        ),
    }
