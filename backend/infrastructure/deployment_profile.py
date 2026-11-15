"""Validate deployment identities without credentials or implicit environment overrides."""

import hashlib
import json
import os
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
    "runtime_alias",
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
        "runtime_alias": r"[a-z][a-z0-9-]{0,49}",
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


def unique_json(text):
    """Reject duplicate JSON keys at every configuration level."""

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate deployment profile key")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=pairs)


def configured_target(name, text):
    """Resolve one explicitly named target from repository configuration."""
    require(
        isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name),
        "Invalid deployment target name",
    )
    targets = unique_json(text)
    require(isinstance(targets, dict) and name in targets, "Deployment target is not configured")
    return validate(targets[name])


def load(path):
    """Load a file or explicitly selected GitHub-variable target without credential values."""
    if str(path).startswith("env:"):
        profile = configured_target(
            str(path)[4:], os.environ.get("FITFINITY_DEPLOYMENT_TARGETS_JSON", "{}")
        )
        require(
            profile["github_repository"] == os.environ.get("GITHUB_REPOSITORY"),
            "Wrong deployment repository",
        )
        return profile
    return validate(unique_json(Path(path).read_text()))


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
        "runtime_function": prefix + "-staff-api",
        "upgrade_name": prefix + "-schema-upgrade",
        "upgrade_operator_role": prefix + "-github-schema-upgrade",
        "upgrade_setup_stack": prefix + "-schema-upgrade-access",
        "upgrade_runtime_role": prefix + "-schema-upgrade-runtime",
        "upgrade_boundary": (
            f"arn:aws:iam::{account}:policy/{prefix}-schema-upgrade-runtime-boundary"
        ),
        "hosting_stack": prefix + "-login",
        "hosting_role": prefix + "-github-hosting",
        "image_repository": prefix + "-api",
        "image_role": prefix + "-github-image",
        "environment_tag": target["secret_prefix"].split("/")[1],
        "registry": f"{account}.dkr.ecr.{region}.amazonaws.com",
        "oidc_subject": "repo:"
        + target["github_repository"]
        + ":environment:"
        + quote(target["github_environment"], safe="-_."),
    }


DEVELOPER = load(Path(__file__).with_name("targets") / "developer.json")


def template_rules(profile, *, edge=False):
    """Refuse deploying a rendered template in a different account or region."""
    target = identities(profile)
    return {
        "SelectedTarget": {
            "Assertions": [
                {
                    "Assert": {"Fn::Equals": [{"Ref": key}, value]},
                    "AssertDescription": "Use the reviewed deployment account and region",
                }
                for key, value in (
                    ("AWS::AccountId", target["account"]),
                    ("AWS::Region", "us-east-1" if edge else target["region"]),
                )
            ]
        }
    }


def observation_policy(profile):
    """Scope the observation session to the selected stack, runtime and database."""
    target = identities(profile)
    account, region = target["account"], target["region"]
    function = f"arn:aws:lambda:{region}:{account}:function:{target['runtime_function']}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "sts:GetCallerIdentity", "Resource": "*"},
            {
                "Effect": "Allow",
                "Action": ["cloudformation:DescribeStacks", "cloudformation:GetTemplate"],
                "Resource": (
                    f"arn:aws:cloudformation:{region}:{account}:stack/{target['hosting_stack']}/*"
                ),
            },
            {
                "Effect": "Allow",
                "Action": ["lambda:GetFunction", "lambda:GetAlias"],
                "Resource": [function, function + ":*"],
            },
            {
                "Effect": "Allow",
                "Action": "rds:DescribeDBInstances",
                "Resource": f"arn:aws:rds:{region}:{account}:db:{target['database']}",
            },
        ],
    }


def workflow_target(name, repository, root=None, *, configuration=None):
    """Resolve a checked-in target and refuse foreign repositories or path traversal."""
    require(
        isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name),
        "Invalid deployment target name",
    )
    root = Path(__file__).with_name("targets") if root is None else Path(root)
    path = root / (name + ".json")
    require(
        not path.is_symlink() and path.resolve().parent == root.resolve(),
        "Target must be a direct regular profile file",
    )
    profile = configured_target(name, configuration) if configuration else load(path)
    require(profile["github_repository"] == repository, "Wrong deployment repository")
    target = identities(profile)
    return {
        "profile": "env:" + name
        if configuration
        else "backend/infrastructure/targets/" + name + ".json",
        "profile_sha256": target["profile_sha256"],
        "environment": target["github_environment"],
        "account": target["account"],
        "region": target["region"],
        "role": f"arn:aws:iam::{target['account']}:role/{target['operator_role']}",
        "image_role": f"arn:aws:iam::{target['account']}:role/{target['image_role']}",
        "hosting_role": f"arn:aws:iam::{target['account']}:role/{target['hosting_role']}",
        "observation_policy": json.dumps(observation_policy(profile), separators=(",", ":")),
    }


if __name__ == "__main__":
    result = workflow_target(
        os.environ["DEPLOYMENT_TARGET"],
        os.environ["GITHUB_REPOSITORY"],
        configuration=os.environ.get("FITFINITY_DEPLOYMENT_TARGETS_JSON"),
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        for key, value in result.items():
            output.write(f"{key}={value}\n")
