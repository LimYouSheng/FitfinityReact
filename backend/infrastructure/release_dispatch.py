"""Dispatch one journaled child workflow without replaying an uncertain request."""

import json
import subprocess

from operator_checks import require
from release_record import next_stage

WORKFLOWS = {
    "image": "aws-image.yml",
    "observation": "aws-release-observe.yml",
    "prepare": "aws-release-prepare.yml",
    "probe_create": "aws-schema-probe.yml",
    "catalog": "aws-schema-probe.yml",
    "backup": "aws-maintenance.yml",
    "upgrade_prepare": "aws-release-prepare.yml",
    "upgrade_create": "aws-schema-upgrade.yml",
    "upgrade_inspect": "aws-schema-upgrade.yml",
    "upgrade": "aws-schema-upgrade.yml",
    "post_upgrade_catalog": "aws-schema-probe.yml",
    "rollout": "aws-rollout.yml",
    "resume": "aws-rollout.yml",
    "cleanup_upgrade": "aws-schema-upgrade.yml",
    "cleanup_upgrade_check": "aws-schema-upgrade.yml",
    "cleanup_probe": "aws-schema-probe.yml",
    "cleanup_probe_check": "aws-schema-probe.yml",
}


def request(path, payload):
    """Submit one GitHub request without retries or provider error disclosure."""
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", "--method", "POST", path, "--input", "-"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=60,
    )
    require(result.returncode == 0, "Dispatch outcome uncertain; reconcile the retained intent")


def dispatch(record, stage, operation_id, inputs, *, read, now, send=request):
    """Persist exact child inputs before sending one main-bound dispatch request."""
    require(record.value is not None, "Load an authenticated release record first")
    require(
        next_stage(record.value, record.identity) == {"action": "prepare", "stage": stage},
        "Pending or completed stage cannot be dispatched",
    )
    workflow = WORKFLOWS[stage]
    repository = record.identity["repository"]
    source = record.identity["source_sha"]
    require(
        read(f"repos/{repository}/git/ref/heads/main").get("object", {}).get("sha") == source,
        "Main differs from the reviewed release",
    )
    require(
        isinstance(inputs, dict)
        and all(isinstance(key, str) and isinstance(value, str) for key, value in inputs.items()),
        "Workflow inputs must be explicit strings",
    )
    require("orchestration_id" not in inputs, "Correlation identity is owned by the orchestrator")
    bound = {**inputs, "orchestration_id": operation_id}
    record.intent(stage, operation_id, {"workflow": workflow, "inputs": bound}, now)
    send(
        f"repos/{repository}/actions/workflows/{workflow}/dispatches",
        {"ref": "main", "inputs": bound},
    )
    # An accepted dispatch is still pending until an exact child run is observed.
    return {"state": "dispatch_requested", "operation_id": operation_id}


def reconcile(record, payload):
    """Find an exact correlated child without treating a missing run as permission to retry."""
    require(
        record.value is not None and record.value.get("pending") is not None,
        "Pending dispatch required",
    )
    pending = record.value["pending"]
    workflow = WORKFLOWS[pending["stage"]]
    require(pending["inputs"].get("workflow") == workflow, "Journal workflow differs")
    rows = payload.get("workflow_runs", [])
    require(payload.get("total_count") == len(rows), "Incomplete child run inventory")
    expected_title = "Release operation " + pending["operation_id"]
    matches = [row for row in rows if row.get("display_title") == expected_title]
    require(len(matches) <= 1, "Duplicate correlated runs require inspection")
    if not matches:
        return {"action": "hold", "reason": "dispatch_not_observed"}
    run = matches[0]
    require(
        run.get("path") == ".github/workflows/" + workflow
        and run.get("head_sha") == record.identity["source_sha"]
        and run.get("head_branch") == "main"
        and run.get("event") == "workflow_dispatch"
        and run.get("head_repository", {}).get("full_name") == record.identity["repository"]
        and type(run.get("id")) is int
        and run["id"] > 0
        and run.get("run_attempt") == 1,
        "Correlated run identity differs; do not replay",
    )
    if run.get("status") != "completed":
        return {"action": "wait", "run_id": run["id"]}
    if run.get("conclusion") != "success":
        return {"action": "hold", "reason": "child_unsuccessful", "run_id": run["id"]}
    return {"action": "authenticate_receipt", "run_id": run["id"]}
