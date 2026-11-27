"""Inspect every release milestone without replaying writes or changing target ownership."""

import hashlib

from operator_checks import require
from release_dispatch import WORKFLOWS, reconcile
from release_record import STAGES, encode, identity, validate

# These are existing child recovery modes, not permission to invoke a mutation.
RECOVERY = {
    "image": ("Inspect the exact ECR digest and original image receipt", None),
    "observation": ("Prepare a fresh read-only observation", None),
    "prepare": ("Inspect preparation artifacts and review expiry", None),
    "probe_create": ("Inspect the original probe stack and creation receipt", None),
    "catalog": ("Inspect probe invocation status and catalog receipt", None),
    "backup": (
        "Read the retained milestone_phase: inspect pause, "
        "record-pause-inspect/verify for its change set, snapshot-check for backup",
        None,
    ),
    "upgrade_prepare": ("Inspect upgrade review and source/schema bindings", None),
    "upgrade_create": ("Inspect the original upgrade worker stack", "inspect"),
    "upgrade_inspect": ("Inspect worker readiness without invoking migration", "inspect"),
    "upgrade": (
        "Inspect migration receipt and database catalog; "
        "worker inspect alone cannot prove migration outcome",
        "inspect",
    ),
    "post_upgrade_catalog": ("Inspect the original catalog request; require current grants", None),
    "rollout": (
        "Read the retained milestone_phase: upload-inspect for upload, "
        "inspect for change set, verify for installed template",
        None,
    ),
    "resume": (
        "Read the retained milestone_phase: resume-inspect/verify, resume-health, "
        "or resume-finalize-inspect; do not repeat finalization",
        None,
    ),
    "cleanup_upgrade": ("Inspect deletion of the exact retained upgrade stack", "cleanup-check"),
    "cleanup_upgrade_check": ("Continue read-only deletion verification", "cleanup-check"),
    "cleanup_probe": ("Inspect deletion of the exact retained probe stack", "cleanup-check"),
    "cleanup_probe_check": ("Continue read-only deletion verification", "cleanup-check"),
}


def claim_key(profile):
    """Return the target-owned pointer, never a caller-selected storage location."""
    return (
        "releases/targets/"
        + "/".join(profile[key] for key in ("account", "region", "resource_prefix"))
        + "/current.json"
    )


def inventory(repository, workflow, source, read):
    """Read all bounded pages; an incomplete inventory cannot establish absence."""
    result, total = [], None
    for page in range(1, 11):
        payload = read(
            f"repos/{repository}/actions/workflows/{workflow}/runs"
            f"?head_sha={source}&per_page=100&page={page}"
        )
        rows = payload.get("workflow_runs")
        count = payload.get("total_count")
        require(isinstance(rows, list) and type(count) is int, "Invalid recovery run inventory")
        require(total is None or count == total, "Run inventory changed during inspection")
        total = count
        result.extend(rows)
        if len(result) >= total:
            require(len(result) == total, "Recovery run inventory is incomplete")
            require(len({row["id"] for row in result}) == total, "Duplicate recovery run inventory")
            return {"total_count": total, "workflow_runs": result}
    raise RuntimeError("Recovery run inventory exceeds bounded inspection limit")


def inspect_record(record, profile, current_source, read):
    """Classify a retained intent for all milestones; absence is never dispatch rejection proof."""
    owner = record["identity"]
    require(owner == identity(profile, owner.get("source_sha")), "Recovery identity differs")
    validate(record, owner)
    pending = record["pending"]
    result = {
        "source_sha": owner["source_sha"],
        "current_source_sha": current_source,
        "source_changed": owner["source_sha"] != current_source,
        "generation": record["generation"],
        "completed_stages": [stage for stage in STAGES if stage in record["stages"]],
        "journal_sha256": hashlib.sha256(encode(record)).hexdigest(),
        "mutation_authorized": False,
        "resource_state_checked": False,
        "receipt_authenticated": False,
    }
    if pending is None:
        stage = next((name for name in STAGES if name not in record["stages"]), None)
        return {
            **result,
            "stage": stage,
            "action": "complete"
            if stage is None
            else "hold"
            if result["source_changed"]
            else "continue_verified_source",
            "next": "Reauthenticate source and review freshness before preparing the next stage",
        }
    stage = pending["stage"]
    payload = inventory(owner["repository"], WORKFLOWS[stage], owner["source_sha"], read)
    holder = type("Retained", (), {"value": record, "identity": owner})()
    observed = reconcile(holder, payload)
    action = observed["action"]
    note, mode = RECOVERY[stage]
    if observed.get("reason") == "dispatch_not_observed":
        note = (
            "No correlated child observed; retain intent and prove rejection before a replacement"
        )
    elif action == "wait":
        note = "Wait for the existing child; do not submit another operation"
    elif action == "authenticate_receipt":
        note = "Authenticate the original child receipt before advancing; never repeat the child"
    return {
        **result,
        "stage": stage,
        "operation_id": pending["operation_id"],
        "action": action,
        "reason": observed.get("reason"),
        "run_id": observed.get("run_id"),
        "recovery_mode": mode,
        "next": note,
        "source_transition_required": result["source_changed"],
    }


def inspect_target(profile, source, read_object, read_api):
    """Read the owning release even when a newer main commit cannot claim its target."""
    claim, _ = read_object(claim_key(profile))
    require(claim.get("schema_version") == 1, "Recovery claim schema differs")
    owner = claim["identity"]
    require(owner == identity(profile, owner.get("source_sha")), "Recovery claim identity differs")
    record, _ = read_object(
        f"releases/{owner['profile_sha256']}/{owner['source_sha']}/current.json"
    )
    require(record.get("identity") == owner, "Claim and release record differ")
    return inspect_record(record, profile, source, read_api)
