"""Evaluate an expiring developer exception against exact findings and runtime inputs."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from deployment_profile import identities
from operator_checks import require

POLICY = Path(__file__).with_name("developer-scan-waiver.json")
RUNTIME_FILES = {
    "backend/.dockerignore",
    "backend/Dockerfile",
    "backend/requirements.lock",
    "backend/alembic.ini",
    "backend/infrastructure/read-schema.sql",
}


def runtime_fingerprint(files):
    """Bind all application, migration and Docker runtime inputs, including added files."""
    require(isinstance(files, dict) and RUNTIME_FILES <= files.keys(), "Missing runtime inputs")
    selected = {
        name: value
        for name, value in files.items()
        if name in RUNTIME_FILES or name.startswith(("backend/app/", "backend/migrations/"))
    }
    return hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()


def finding_identity(finding):
    """Reject ambiguous package identities before matching the reviewed finding set."""
    attrs = finding.get("attributes", [])
    require(isinstance(attrs, list), "Malformed scan attributes")
    values = {}
    for item in attrs:
        require(isinstance(item, dict), "Malformed scan attribute")
        key = item.get("key")
        if key in {"package_name", "package_version"}:
            require(key not in values and isinstance(item.get("value"), str), "Ambiguous package")
            values[key] = item["value"]
    require(len(values) == 2 and all(values.values()), "Missing package identity")
    return {
        "cve": finding.get("name"),
        "package": values["package_name"],
        "version": values["package_version"],
        "severity": finding.get("severity"),
    }


def developer_exception(findings, digest, now, profile, source_files):
    """Require the approved developer scope, lifetime, runtime and complete finding set."""
    policy_bytes = POLICY.read_bytes()
    policy = json.loads(policy_bytes)
    require(policy.get("status") == "approved", "Developer waiver is not approved")
    require(
        datetime.fromisoformat(policy["approved_at"])
        <= now
        < datetime.fromisoformat(policy["expires_at"]),
        "Developer waiver expired or future dated",
    )
    require(
        identities(profile)["profile_sha256"] == policy["profile_sha256"],
        "Developer waiver does not cover this target",
    )
    require(
        runtime_fingerprint(source_files) == policy["runtime_sha256"],
        "Developer waiver runtime inputs changed",
    )
    actual = [finding_identity(finding) for finding in findings]

    def canonical(rows):
        return sorted(json.dumps(row, sort_keys=True) for row in rows)

    expected = canonical(policy["findings"])
    require(
        len(expected) == len(set(expected)) and canonical(actual) == expected,
        "Developer waiver finding set changed",
    )
    require(all(row["severity"] != "CRITICAL" for row in actual), "Critical findings are blocked")
    return {
        "kind": "developer_exception",
        "id": policy["id"],
        "expires_at": policy["expires_at"],
        "image_digest": digest,
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "runtime_sha256": policy["runtime_sha256"],
    }
