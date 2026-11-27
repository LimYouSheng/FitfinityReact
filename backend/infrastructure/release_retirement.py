"""Retire only a proven unsubmitted pre-backup release without erasing its history."""

import hashlib
import re
from copy import deepcopy

from operator_checks import require
from release_record import STAGES, encode, identity, validate


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def bindings(record):
    """Require the exact pre-backup boundary and preserve all original completed evidence."""
    require(not record.get("retirement"), "Release already retired; inspect its successor")
    require(set(record["stages"]) == set(STAGES[:5]), "Only pre-backup retirement is supported")
    require(
        all(row["outcome"] == "complete" for row in record["stages"].values()),
        "Original completed stages required",
    )
    pending = record["pending"]
    require(
        pending is not None
        and pending["stage"] == "backup"
        and pending["state"] == "dispatch_intent",
        "Original backup dispatch intent required",
    )
    dispatch = pending["inputs"]
    require(
        dispatch.get("workflow") == "aws-maintenance.yml"
        and dispatch.get("inputs", {}).get("mode") == "backup"
        and "review_sha256" not in dispatch["inputs"],
        "Retirement requires the original missing-required-input failure",
    )
    docs = record["stages"]["prepare"]["evidence"]["documents"]
    maintenance = docs["maintenance-review/review.json"]
    probe = record["stages"]["probe_create"]["evidence"]["documents"]["schema-probe-receipt.json"]
    review = docs["schema-probe-review/review.json"]
    owner = record["identity"]
    require(
        maintenance["source_sha"] == probe["source_sha"] == owner["source_sha"]
        and maintenance["profile_sha256"] == probe["profile_sha256"] == owner["profile_sha256"]
        and probe["operation_id"] == review["bindings"]["operation_id"]
        and review["bindings"]["source_sha"] == owner["source_sha"]
        and probe["state"] == "create_submitted",
        "Original review identities differ",
    )
    require(
        isinstance(probe.get("stack_id"), str) and probe["stack_id"],
        "Original probe stack receipt required",
    )
    require(
        type(maintenance.get("previous_concurrency")) is int
        and maintenance["previous_concurrency"] > 0,
        "Original running capacity required",
    )
    return maintenance, probe, review


def check_evidence(record, successor, evidence):
    """Reject incomplete deletion, possible maintenance execution and changed live bindings."""
    maintenance, probe, review = bindings(record)
    require(
        re.fullmatch(r"[a-f0-9]{40}", successor or "")
        and successor != record["identity"]["source_sha"],
        "Distinct exact successor required",
    )
    require(
        evidence.get("main_source") == successor
        and evidence.get("ancestor") is True
        and type(evidence.get("maintenance_runs")) is int
        and evidence["maintenance_runs"] == 0
        and type(evidence.get("maintenance_runs_since_intent")) is int
        and evidence["maintenance_runs_since_intent"] == 0
        and type(evidence.get("active_original_runs")) is int
        and evidence["active_original_runs"] == 0
        and evidence.get("original_coordinator_finished") is True
        and evidence.get("required_input_absent") is True
        and re.fullmatch(r"[a-f0-9]{64}", evidence.get("workflow_sha256", "")),
        "Original dispatch rejection and successor evidence required",
    )
    require(
        evidence.get("runtime_state") == "Active"
        and evidence.get("runtime_update") == "Successful"
        and evidence.get("runtime_revision") == maintenance["function_revision"]
        and type(evidence.get("capacity")) is int
        and evidence["capacity"] == maintenance["previous_concurrency"]
        and evidence.get("maintenance_markers") == {}
        and evidence.get("hosting_stack_id") == maintenance["hosting_stack_arn"]
        and evidence.get("hosting_status") == "UPDATE_COMPLETE"
        and evidence.get("hosting_template_sha256") == maintenance["hosting_template_sha256"]
        and evidence.get("database_resource_id") == maintenance["database_resource_id"]
        and evidence.get("database_status") == "available",
        "Live application or database changed",
    )
    require(
        evidence.get("probe_stack_id") == probe["stack_id"]
        and evidence.get("probe_status") == "DELETE_COMPLETE"
        and evidence.get("probe_template_sha256") == review["template_sha256"]
        and evidence.get("probe_tags")
        == {
            "FitfinityOperation": probe["operation_id"],
            "FitfinitySource": record["identity"]["source_sha"],
            "FitfinityProfile": record["identity"]["profile_sha256"],
            "FitfinityTemplate": review["template_sha256"],
        },
        "Exact owned probe deletion must be verified first",
    )


def prepare(record, profile, successor, evidence, claim_etag, record_etag, now):
    """Build a short-lived review; preparation never writes the journal."""
    validate(record, identity(profile, record["identity"]["source_sha"]))
    check_evidence(record, successor, evidence)
    require(bindings(record)[0]["expires_at"] < now, "Original review must be expired")
    require(
        all(isinstance(value, str) and value for value in (claim_etag, record_etag)),
        "Both conditional-write versions required",
    )
    return {
        "schema_version": 1,
        "kind": "retire_unsubmitted_backup",
        "identity": deepcopy(record["identity"]),
        "successor_source": successor,
        "record_sha256": digest(record),
        "claim_etag": claim_etag,
        "record_etag": record_etag,
        "prepared_at": now,
        "expires_at": now + 600,
        "evidence": deepcopy(evidence),
    }


def terminal(record):
    """Validate a sealed retirement independently before allowing target transfer."""
    proof = record.get("retirement")
    require(
        isinstance(proof, dict)
        and set(proof) == {"plan", "plan_sha256", "previous_updated_at", "completed_at"},
        "Invalid retirement proof",
    )
    plan = proof["plan"]
    require(
        plan.get("schema_version") == 1
        and plan.get("kind") == "retire_unsubmitted_backup"
        and plan.get("identity") == record["identity"]
        and proof["plan_sha256"] == digest(plan)
        and plan["prepared_at"] <= proof["completed_at"] <= plan["expires_at"]
        and plan["expires_at"] - plan["prepared_at"] == 600
        and record["updated_at"] == proof["completed_at"],
        "Retirement review differs",
    )
    original = deepcopy(record)
    del original["retirement"]
    original["generation"] -= 1
    original["updated_at"] = proof["previous_updated_at"]
    require(digest(original) == plan["record_sha256"], "Retired history was modified")
    require(
        bindings(original)[0]["expires_at"] < plan["prepared_at"],
        "Retirement predates original review expiry",
    )
    check_evidence(original, plan["successor_source"], plan["evidence"])
    return plan["successor_source"]


def apply(record, profile, plan, expected_digest, read_claim, observe, now, *, clock=None):
    """Recheck providers and both pointers, then CAS one retirement without changing the claim."""
    require(digest(plan) == expected_digest, "Reviewed retirement plan changed")
    record.refresh()
    if record.value.get("retirement"):
        require(
            terminal(record.value) == plan["successor_source"]
            and record.value["retirement"]["plan_sha256"] == expected_digest,
            "Different retirement already recorded",
        )
        return {"state": "already_retired", "successor_source": plan["successor_source"]}
    require(plan["prepared_at"] <= now <= plan["expires_at"], "Retirement review expired")
    require(
        record.etag == plan["record_etag"] and digest(record.value) == plan["record_sha256"],
        "Release changed since retirement preparation",
    )
    evidence = observe(record.value, plan["successor_source"])
    require(evidence == plan["evidence"], "Recovery observations changed; prepare a fresh review")
    fresh = prepare(
        record.value,
        profile,
        plan["successor_source"],
        evidence,
        plan["claim_etag"],
        record.etag,
        now,
    )
    require(fresh["identity"] == plan["identity"], "Retirement target differs")
    claim, etag = read_claim()
    require(
        etag == plan["claim_etag"]
        and claim.get("schema_version") == 1
        and claim.get("identity") == record.identity,
        "Target claim changed",
    )
    now = clock() if clock is not None else now
    require(
        plan["prepared_at"] <= now <= plan["expires_at"],
        "Retirement review expired during inspection",
    )
    value = deepcopy(record.value)
    value.update(generation=value["generation"] + 1, updated_at=now)
    value["retirement"] = {
        "plan": deepcopy(plan),
        "plan_sha256": expected_digest,
        "previous_updated_at": record.value["updated_at"],
        "completed_at": now,
    }
    terminal(value)
    record.commit(value)
    return {"state": "retired", "successor_source": plan["successor_source"]}
