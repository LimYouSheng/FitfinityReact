"""Read fresh provider evidence for the narrow pre-backup retirement protocol."""

import base64
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from deployment_profile import identities
from operator_checks import require
from release_recovery import inventory
from release_retirement import bindings, digest


def observe(record, profile, successor, github, aws, contract):
    """Prove rejection, unchanged runtime and exact worker deletion from fresh reads."""
    maintenance, probe, review = bindings(record)
    target = identities(profile)
    repository, source = profile["github_repository"], record["identity"]["source_sha"]
    require(
        aws("sts", "get_caller_identity", {})["Account"] == target["account"],
        "Wrong recovery account",
    )
    main = github(f"repos/{repository}/git/ref/heads/main")["object"]["sha"]
    require(main == successor and main != source, "Reviewed successor is not current main")
    comparison = github(f"repos/{repository}/compare/{source}...{successor}")
    require(
        comparison.get("status") == "ahead"
        and comparison.get("merge_base_commit", {}).get("sha") == source,
        "Original source must be an ancestor of successor",
    )
    runs = inventory(repository, "aws-maintenance.yml", source, github)
    require(runs["total_count"] == 0, "Maintenance run exists; use receipt-based recovery")
    since = datetime.fromtimestamp(int(record["updated_at"]), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def recent(path):
        page = path.rsplit("page=", 1)[1]
        query = urlencode({"created": ">=" + since, "per_page": 100, "page": page})
        return github(f"repos/{repository}/actions/workflows/aws-maintenance.yml/runs?{query}")

    require(
        inventory(repository, "aws-maintenance.yml", source, recent)["total_count"] == 0,
        "Maintenance ran after intent, possibly on another source; inspect it",
    )
    # The original dispatcher must have finished; no late child can still be submitted.
    original = all_runs(repository, source, github)
    require(
        any(row.get("path") == ".github/workflows/aws-release.yml" for row in original)
        and all(
            row.get("status") == "completed" and row.get("head_sha") == source for row in original
        ),
        "An original-source run is still active",
    )
    archived = github(
        f"repos/{repository}/contents/.github/workflows/aws-maintenance.yml?ref={source}"
    )
    require(archived.get("encoding") == "base64", "Archived workflow encoding differs")
    content = base64.b64decode(archived["content"], validate=False)
    require(
        hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        == archived.get("sha"),
        "Archived workflow blob differs",
    )
    workflow_hash = contract(content)
    function = aws("lambda", "get_function", {"FunctionName": target["runtime_function"]})
    cfg = function["Configuration"]
    function_arn = (
        f"arn:aws:lambda:{target['region']}:{target['account']}:function:"
        + target["runtime_function"]
    )
    require(
        cfg.get("FunctionArn") == function_arn
        and isinstance(function.get("Tags"), dict)
        and not function.get("TagsError"),
        "Runtime identity or tag read failed",
    )
    capacity = aws(
        "lambda", "get_function_concurrency", {"FunctionName": target["runtime_function"]}
    ).get("ReservedConcurrentExecutions")
    prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
    require(
        re.fullmatch(
            re.escape(prefix + target["hosting_stack"] + "/") + r"[\w-]+",
            maintenance["hosting_stack_arn"],
        ),
        "Hosting stack target differs",
    )
    hosting = stack(aws, maintenance["hosting_stack_arn"])
    hosting_template = template(aws, hosting["StackId"])
    databases = aws("rds", "describe_db_instances", {"DBInstanceIdentifier": target["database"]})[
        "DBInstances"
    ]
    require(len(databases) == 1, "Exact database observation required")
    db = databases[0]
    require(
        db.get("DBInstanceArn")
        == f"arn:aws:rds:{target['region']}:{target['account']}:db:{target['database']}"
        and db.get("StorageEncrypted") is True
        and db.get("PubliclyAccessible") is False
        and db.get("Engine") == "postgres",
        "Database target or protection differs",
    )
    require(
        re.fullmatch(re.escape(prefix + target["probe_name"] + "/") + r"[\w-]+", probe["stack_id"]),
        "Probe stack target differs",
    )
    worker = stack(aws, probe["stack_id"])
    tags = {row["Key"]: row["Value"] for row in worker.get("Tags", [])}
    require(
        github(f"repos/{repository}/git/ref/heads/main")["object"]["sha"] == successor,
        "Main changed during recovery inspection",
    )
    return {
        "main_source": main,
        "ancestor": True,
        "maintenance_runs": 0,
        "maintenance_runs_since_intent": 0,
        "active_original_runs": 0,
        "original_coordinator_finished": True,
        "required_input_absent": True,
        "workflow_sha256": workflow_hash,
        "runtime_state": cfg.get("State"),
        "runtime_update": cfg.get("LastUpdateStatus"),
        "runtime_revision": cfg.get("RevisionId"),
        "capacity": capacity,
        "maintenance_markers": {
            k: v
            for k, v in function["Tags"].items()
            if k in {"FitfinityMaintenance", "FitfinitySnapshot"}
        },
        "hosting_stack_id": hosting["StackId"],
        "hosting_status": hosting["StackStatus"],
        "hosting_template_sha256": hashlib.sha256(
            json.dumps(hosting_template, sort_keys=True).encode()
        ).hexdigest(),
        "database_resource_id": db["DbiResourceId"],
        "database_status": db["DBInstanceStatus"],
        "probe_stack_id": worker["StackId"],
        "probe_status": worker["StackStatus"],
        "probe_template_sha256": digest(template(aws, worker["StackId"])),
        "probe_tags": {
            k: tags[k]
            for k in (
                "FitfinityOperation",
                "FitfinitySource",
                "FitfinityProfile",
                "FitfinityTemplate",
            )
            if k in tags
        },
    }


def stack(aws, arn):
    rows = aws("cloudformation", "describe_stacks", {"StackName": arn})["Stacks"]
    require(len(rows) == 1 and rows[0]["StackId"] == arn, "Exact original stack required")
    return rows[0]


def template(aws, arn):
    value = aws("cloudformation", "get_template", {"StackName": arn, "TemplateStage": "Original"})[
        "TemplateBody"
    ]
    return json.loads(value) if isinstance(value, str) else value


def all_runs(repository, source, github):
    """Reuse complete pagination for the source-wide run inventory, not just the pending child."""

    def read(path):
        suffix = path.split("/runs?", 1)[1]
        return github(f"repos/{repository}/actions/runs?{suffix}")

    return inventory(repository, "unused", source, read)["workflow_runs"]


def archived_contract(content):
    """Use the locked YAML parser rather than guessing contract semantics with text matching."""
    result = subprocess.run(
        ["node", str(Path(__file__).with_name("retirement_contract.mjs"))],
        input=content,
        capture_output=True,
        timeout=30,
    )
    require(
        result.returncode == 0,
        "Archived contract validation failed; install locked Node dependencies",
    )
    value = json.loads(result.stdout)
    require(
        value.get("workflow_sha256") == hashlib.sha256(content).hexdigest(),
        "Archived contract digest differs",
    )
    return value["workflow_sha256"]
