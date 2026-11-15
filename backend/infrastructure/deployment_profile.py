"""Validate deployment identities without credentials or implicit environment overrides."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

from operator_checks import require

FIELDS = {
    "schema_version",
    "account",
    "region",
    "github_repository",
    "github_environment",
    "resource_prefix",
    "secret_prefix",
}


def validate(value):
    """Return an isolated profile after rejecting ambiguous or unsafe target identities."""
    require(isinstance(value, dict) and set(value) == FIELDS, "Exact deployment profile required")
    require(
        type(value["schema_version"]) is int and value["schema_version"] == 1,
        "Unsupported deployment profile version",
    )
    patterns = {
        "account": r"[0-9]{12}",
        "region": (
            r"(?:af|ap|ca|eu|il|me|mx|sa|us)-"
            r"(?:central|east|west|north|south|northeast|southeast)-[1-9]"
        ),
        "github_repository": r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}",
        "github_environment": r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}",
        "resource_prefix": r"[a-z][a-z0-9-]{1,24}",
        "secret_prefix": r"[a-z][a-z0-9-]{0,24}/[a-z][a-z0-9-]{0,24}",
    }
    for key, pattern in patterns.items():
        require(
            isinstance(value[key], str) and re.fullmatch(pattern, value[key]),
            f"Invalid deployment profile {key}",
        )
    require(not value["github_repository"].endswith(".git"), "Use repository identity without .git")
    return dict(value)


def load(path):
    """Load one explicit JSON profile and reject duplicate keys."""

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate deployment profile key")
            result[key] = value
        return result

    return validate(json.loads(Path(path).read_text(), object_pairs_hook=pairs))


def fingerprint(profile):
    """Bind receipts to all reviewed target fields using canonical JSON."""
    data = json.dumps(validate(profile), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def identities(profile):
    """Derive scoped resource names and GitHub trust from the validated target."""
    target = validate(profile)
    prefix = target["resource_prefix"]
    account, region = target["account"], target["region"]
    name = prefix + "-schema-observe"
    return {
        **target,
        "profile_sha256": fingerprint(target),
        "probe_name": name,
        "runtime_role": name + "-runtime",
        "runtime_boundary": f"arn:aws:iam::{account}:policy/{name}-runtime-boundary",
        "operator_role": prefix + "-github-schema-probe",
        "setup_stack": prefix + "-schema-probe-access",
        "database": prefix + "-db",
        "image_repository": prefix + "-api",
        "registry": f"{account}.dkr.ecr.{region}.amazonaws.com",
        "oidc_subject": "repo:"
        + target["github_repository"]
        + ":environment:"
        + quote(target["github_environment"], safe="-_."),
    }


DEVELOPER = load(Path(__file__).with_name("targets") / "developer.json")
