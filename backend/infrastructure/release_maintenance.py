"""Pause one reviewed staff runtime and prepare an owned pre-upgrade snapshot."""

import re
import time
from copy import deepcopy
from math import isfinite

from deployment_profile import identities
from operator_checks import require
from release_execution import execute as release_step
from release_execution import template as read_template
from release_observation import digest
from release_pause import require_recorded_pause

RECORD_MODES = {
    "record-pause-create",
    "record-pause-inspect",
    "record-pause-execute",
    "record-pause-verify",
}
MODES = {"pause", "inspect", "snapshot", "snapshot-check"} | RECORD_MODES
RECOVERY_MODES = {"inspect", "snapshot-check", "record-pause-inspect", "record-pause-verify"}


def snapshot_identity(target, operation, source):
    """Derive the runtime marker and snapshot ownership for one drained maintenance operation."""
    name = target["resource_prefix"] + "-release-" + operation
    return {
        "marker": operation + ":" + source + ":" + target["profile_sha256"],
        "name": name,
        "arn": f"arn:aws:rds:{target['region']}:{target['account']}:snapshot:{name}",
        "tags": {
            "Application": "Fitfinity",
            "FitfinityOperation": operation,
            "FitfinityProfile": target["profile_sha256"],
            "FitfinitySource": source,
        },
    }


def check_snapshot_tags(rows, expected):
    """Require the maintenance-owned snapshot tags while preserving unrelated resource tags."""
    require(
        isinstance(rows, list)
        and all(isinstance(row, dict) and isinstance(row.get("Key"), str) for row in rows),
        "Snapshot ownership tags unavailable",
    )
    actual = {row["Key"]: row.get("Value") for row in rows}
    require(
        len(actual) == len(rows) and all(actual.get(k) == v for k, v in expected.items()),
        "Snapshot ownership differs",
    )


def verified_snapshot(receipt, arn, target, source):
    """Bind an available backup to its protected maintenance receipt and drain deadline."""
    require(isinstance(receipt, dict), "Verified maintenance snapshot receipt required")
    identity = receipt.get("identity")
    require(
        isinstance(identity, dict)
        and identity.get("profile_sha256") == target["profile_sha256"]
        and identity.get("source_sha") == source
        and isinstance(identity.get("operation_id"), str)
        and re.fullmatch(r"[a-f0-9]{32}", identity["operation_id"]),
        "Maintenance snapshot receipt belongs to another source, target or operation",
    )
    snapshot = snapshot_identity(target, identity["operation_id"], source)
    drained_after = receipt.get("drained_after")
    require(
        receipt.get("state") == "snapshot_ready"
        and receipt.get("snapshot_requested") is True
        and receipt.get("snapshot_arn") == arn == snapshot["arn"]
        and type(drained_after) in (int, float)
        and isfinite(drained_after)
        and drained_after > 0,
        "Ready maintenance receipt for the selected snapshot and drain deadline required",
    )
    return snapshot


def validate_review(review, profile, now):
    """Reject incomplete, foreign or expired maintenance metadata."""
    target = identities(profile)
    required = {
        "profile_sha256",
        "source_sha",
        "operation_id",
        "expires_at",
        "function_revision",
        "database_resource_id",
        "previous_concurrency",
    }
    extra = {"hosting_stack_arn", "hosting_template_sha256"}
    require(
        set(review) in (required, required | extra)
        and review["profile_sha256"] == target["profile_sha256"]
        and re.fullmatch(r"[a-f0-9]{40}", review["source_sha"])
        and re.fullmatch(r"[a-f0-9]{32}", review["operation_id"])
        and re.fullmatch(r"[A-Za-z0-9-]{1,128}", review["function_revision"])
        and re.fullmatch(r"db-[A-Za-z0-9]{1,64}", review["database_resource_id"])
        and type(review["expires_at"]) is int
        and 0 < review["expires_at"] - now <= 3600
        and type(review["previous_concurrency"]) is int
        and review["previous_concurrency"] > 0,
        "Exact unexpired maintenance review required",
    )
    if extra <= set(review):
        prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
        require(
            re.fullmatch(
                re.escape(prefix + target["hosting_stack"] + "/") + r"[a-f0-9-]+",
                review["hosting_stack_arn"],
            )
            and re.fullmatch(r"[a-f0-9]{64}", review["hosting_template_sha256"]),
            "Exact hosting stack observation required",
        )
    return target


def runtime_fingerprint(function):
    """Bind execution configuration without provider revision or lifecycle metadata."""
    config = deepcopy(function["Configuration"])
    for key in (
        "RevisionId",
        "LastModified",
        "State",
        "StateReason",
        "StateReasonCode",
        "LastUpdateStatus",
        "LastUpdateStatusReason",
        "LastUpdateStatusReasonCode",
    ):
        config.pop(key, None)
    return digest(config)


def inspect(review, call, profile, now, prior=None):
    """Recheck exact cloud identities and reject stale maintenance authority."""
    target = validate_review(review, profile, now)
    account, region = target["account"], target["region"]
    identity = call("sts", "get-caller-identity", {})
    require(
        identity.get("Account") == account
        and re.fullmatch(
            rf"arn:aws:sts::{account}:assumed-role/{re.escape(target['maintenance_role'])}/[\w+=,.@-]+",
            identity.get("Arn", ""),
        ),
        "Wrong maintenance account or role",
    )
    function = call("lambda", "get-function", {"FunctionName": target["runtime_function"]})
    config = function.get("Configuration", {})
    require(
        config.get("FunctionArn")
        == f"arn:aws:lambda:{region}:{account}:function:" + target["runtime_function"]
        and config.get("LastUpdateStatus") == "Successful"
        and type(config.get("Timeout")) is int
        and 1 <= config["Timeout"] <= 900
        and isinstance(function.get("Tags"), dict)
        and not function.get("TagsError"),
        "Staff runtime configuration or tag observation differs",
    )
    if prior is None or "runtime_sha256" not in prior:
        require(
            config.get("RevisionId") == review["function_revision"],
            "Runtime revision changed without a retained configuration baseline",
        )
    else:
        require(
            prior["runtime_sha256"] == runtime_fingerprint(function),
            "Runtime configuration changed during maintenance",
        )
    rows = call("rds", "describe-db-instances", {"DBInstanceIdentifier": target["database"]})[
        "DBInstances"
    ]
    require(
        len(rows) == 1
        and rows[0].get("DBInstanceArn")
        == f"arn:aws:rds:{region}:{account}:db:{target['database']}"
        and rows[0].get("DbiResourceId") == review["database_resource_id"]
        and rows[0].get("DBInstanceStatus") == "available"
        and rows[0].get("Engine") == "postgres"
        and rows[0].get("StorageEncrypted") is True
        and rows[0].get("PubliclyAccessible") is False,
        "Private database identity or readiness differs",
    )
    concurrency = call(
        "lambda", "get-function-concurrency", {"FunctionName": target["runtime_function"]}
    ).get("ReservedConcurrentExecutions")
    require(type(concurrency) is int, "Explicit staff concurrency required")
    return target, function, concurrency


def execute(mode, review, call, persist, *, profile, prior=None, now=None):
    """Persist intent before each write; inspect uncertain outcomes without replay."""
    require(mode in MODES, "Unknown maintenance operation")
    require(callable(persist), "Durable maintenance receipt writer required")
    live_clock = now is None
    now = time.time() if live_clock else now
    target, function, concurrency = inspect(
        review,
        call,
        profile,
        review["expires_at"] - 1 if mode in RECOVERY_MODES else now,
        prior=prior,
    )
    operation = review["operation_id"]
    snapshot = snapshot_identity(target, operation, review["source_sha"])
    ownership, snapshot_arn = snapshot["marker"], snapshot["arn"]
    snapshot_marker = function["Tags"].get("FitfinitySnapshot")
    marker = function["Tags"].get("FitfinityMaintenance")
    identity = {key: review[key] for key in ("profile_sha256", "source_sha", "operation_id")}
    identity["review_sha256"] = digest(review)
    receipt = {
        "identity": identity,
        "state": "checked",
        "previous_concurrency": review["previous_concurrency"],
        "runtime_sha256": runtime_fingerprint(function),
    }
    if prior is not None:
        require(
            prior.get("identity") == identity
            and prior.get("previous_concurrency") == review["previous_concurrency"],
            "Prior maintenance identity differs",
        )
    if prior is not None:
        for key in ("pause_record", "drained_after", "snapshot_requested", "snapshot_arn"):
            if key in prior:
                receipt[key] = deepcopy(prior[key])
    if mode in RECORD_MODES:
        require(prior is not None and marker == ownership, "Owned maintenance marker required")
        return record_pause(
            mode,
            review,
            prior,
            receipt,
            call,
            persist,
            profile=profile,
            now=None if live_clock else now,
        )
    if mode == "pause":
        require(
            prior is None and marker is None and concurrency == review["previous_concurrency"],
            "Inspect existing maintenance; do not replay pause",
        )
        receipt["state"] = "pause_submitted"
        persist(dict(receipt))
        call(
            "lambda",
            "tag-resource",
            {
                "Resource": function["Configuration"]["FunctionArn"],
                "Tags": {"FitfinityMaintenance": ownership},
            },
        )
        call(
            "lambda",
            "put-function-concurrency",
            {"FunctionName": target["runtime_function"], "ReservedConcurrentExecutions": 0},
        )
    else:
        require(prior is not None and marker == ownership, "Owned maintenance marker required")
        if mode == "inspect":
            receipt["state"] = "paused" if concurrency == 0 else "pause_not_observed"
            if concurrency == 0:
                receipt["drained_after"] = prior.get(
                    "drained_after", now + function["Configuration"]["Timeout"]
                )
            if prior.get("snapshot_arn"):
                receipt["snapshot_arn"] = prior["snapshot_arn"]
            if prior.get("snapshot_requested") or snapshot_marker == ownership:
                receipt["snapshot_requested"] = True
                receipt["snapshot_arn"] = snapshot_arn
        else:
            require(concurrency == 0, "Staff invocation must remain disabled")
            name, arn = snapshot["name"], snapshot_arn
            receipt["snapshot_arn"] = arn
            receipt["snapshot_requested"] = True
            if mode == "snapshot":
                require_recorded_pause(call, profile)
                require(
                    prior.get("state") == "paused"
                    and not prior.get("snapshot_requested")
                    and snapshot_marker is None,
                    "Inspect the original snapshot request; do not replay",
                )
                require(
                    type(prior.get("drained_after")) in (int, float)
                    and now >= prior["drained_after"],
                    "Wait for the runtime's maximum in-flight invocation lifetime",
                )
                receipt["state"] = "snapshot_submitted"
                persist(dict(receipt))
                call(
                    "lambda",
                    "tag-resource",
                    {
                        "Resource": function["Configuration"]["FunctionArn"],
                        "Tags": {"FitfinitySnapshot": ownership},
                    },
                )
                call(
                    "rds",
                    "create-db-snapshot",
                    {
                        "DBInstanceIdentifier": target["database"],
                        "DBSnapshotIdentifier": name,
                        "Tags": [
                            {"Key": key, "Value": value} for key, value in snapshot["tags"].items()
                        ],
                    },
                )
            else:
                require(
                    prior.get("snapshot_requested") is True and prior.get("snapshot_arn") == arn,
                    "Original snapshot intent required",
                )
                rows = call("rds", "describe-db-snapshots", {"DBSnapshotIdentifier": arn})[
                    "DBSnapshots"
                ]
                require(
                    len(rows) == 1
                    and rows[0].get("DBSnapshotArn") == arn
                    and rows[0].get("DbiResourceId") == review["database_resource_id"]
                    and rows[0].get("DBInstanceIdentifier") == target["database"]
                    and rows[0].get("SnapshotType") == "manual"
                    and rows[0].get("Encrypted") is True,
                    "Snapshot identity or encryption differs",
                )
                tags = call("rds", "list-tags-for-resource", {"ResourceName": arn})["TagList"]
                check_snapshot_tags(tags, snapshot["tags"])
                receipt["state"] = (
                    "snapshot_ready" if rows[0].get("Status") == "available" else "snapshot_pending"
                )
    persist(dict(receipt))
    return receipt


def record_pause(mode, review, prior, receipt, call, persist, *, profile, now):
    """Persist only the reviewed concurrency pause without retaining raw templates in receipts."""
    require(
        {"hosting_stack_arn", "hosting_template_sha256"} <= set(review),
        "Prepare maintenance with the exact hosting observation before recording its pause",
    )
    action = mode.removeprefix("record-pause-")
    name = "release-" + review["operation_id"]
    previous = prior.get("pause_record")
    require(
        action != "create"
        or (
            previous is None
            and prior.get("state") == "paused"
            and not prior.get("snapshot_requested")
        ),
        "Inspect the original pause record; do not recreate",
    )
    require(action == "create" or previous is not None, "Original pause-record intent required")
    original = read_template(
        call, review["hosting_stack_arn"], None if action == "create" else name
    )
    original = deepcopy(original)
    if action != "create":
        original["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = review[
            "previous_concurrency"
        ]
    require(
        digest(original) == review["hosting_template_sha256"], "Reviewed hosting template differs"
    )
    candidate = deepcopy(original)
    candidate["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 0
    plan = {
        key: review[key] for key in ("profile_sha256", "source_sha", "operation_id", "expires_at")
    }
    plan.update(
        stack_arn=review["hosting_stack_arn"],
        original_template=original,
        candidate_template=candidate,
        mode="pause",
        boundary_resource=None,
        maintenance_marker=review["operation_id"]
        + ":"
        + review["source_sha"]
        + ":"
        + review["profile_sha256"],
    )

    def save(value):
        receipt["pause_record"] = deepcopy(value)
        receipt["state"] = (
            "paused" if value["state"] == "template_verified" else "pause_record_" + value["state"]
        )
        persist(deepcopy(receipt))

    release_step(action, plan, call, save, profile=profile, prior=previous, now=now)
    return receipt
