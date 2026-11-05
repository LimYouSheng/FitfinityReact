"""Credential-free source inventory. A successful report is never deployment approval."""

import ast
import hashlib
import json
import re
from pathlib import Path


def migration_chain(directory):
    records = {}
    for path in sorted(directory.glob("*.py")):
        if path.name == "__init__.py":
            continue
        values = {}
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                        if target.id in values:
                            raise ValueError("Duplicate migration declaration")
                        values[target.id] = ast.literal_eval(node.value)
        revision = values.get("revision")
        parent = values.get("down_revision")
        if (
            not isinstance(revision, str)
            or not re.fullmatch(r"[A-Za-z0-9_]+", revision)
            or "down_revision" not in values
            or (parent is not None and not isinstance(parent, str))
            or revision in records
        ):
            raise ValueError("Invalid or duplicate migration revision")
        records[revision] = {
            "revision": revision,
            "down_revision": parent,
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    ordered = []
    parent = None
    while len(ordered) < len(records):
        children = [record for record in records.values() if record["down_revision"] == parent]
        if len(children) != 1 or children[0] in ordered:
            raise ValueError("Migration chain must be connected, linear and acyclic")
        ordered.append(children[0])
        parent = children[0]["revision"]
    if not ordered:
        raise ValueError("No migrations found")
    return ordered


def report(repo, revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected exact source SHA")
    backend = repo / "backend"
    chain = migration_chain(backend / "migrations/versions")
    historical = json.loads(
        (backend / "infrastructure/test-db-migration-contract.json").read_text()
    )
    runtime = json.loads((backend / "infrastructure/private-runtime-contract.json").read_text())
    return {
        "source_sha": revision,
        "scope": "source inventory only; no AWS or database access",
        "deployment_decision": "HOLD",
        "current_schema_head": chain[-1]["revision"],
        "migrations": chain,
        "historical_bootstrap_head": historical["revisions"][-1],
        "historical_runtime_source": runtime["revision"],
        "aws_observation": "not performed",
        "required_before_rollout": [
            "Successful exact-source application CI and fresh-main verification",
            "Current account/resource/schema/image/configuration read-only evidence",
            "Recoverable backup and tested populated upgrade from the observed schema",
            "Reviewed current-source migration and runtime/hosting rollout operators",
            "Exact published image scan acceptance and immutable frontend binding",
            "Separately authorized rollout, health checks and rollback boundaries",
        ],
        "not_established": [
            "Image vulnerability scan or ECR publication",
            "Deployed schema compatibility or backup/restore acceptance",
            "Live Cognito, provider delivery, physical-device or M6 acceptance",
        ],
    }


def main():
    import argparse

    from hosting_frontend import build, source_check

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frontend", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    source_check(repo, args.revision)
    result = report(repo, args.revision)
    if args.frontend:
        _, manifest = build(repo, args.frontend, result, args.revision)
        result["frontend_manifest"] = manifest
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Source inventory prepared: {len(result['migrations'])} migrations; deployment HOLD")


if __name__ == "__main__":
    main()
