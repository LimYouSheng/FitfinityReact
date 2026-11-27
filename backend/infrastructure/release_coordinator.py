"""Advance one durable deployment stage using authenticated child results."""

import uuid
from pathlib import Path

from deployment_journal import MissingJournalObject
from operator_checks import require
from release_dispatch import WORKFLOWS, dispatch, reconcile
from release_readiness import migration_chain
from release_record import claim_target, initial, next_stage


def source_evidence(record, verify):
    """Reauthenticate source verification before changing release state."""
    result = verify()
    require(
        result.get("state") == "source_verified"
        and result.get("source_sha") == record.identity["source_sha"]
        and result.get("repository") == record.identity["repository"],
        "Coordinator source verification differs",
    )
    return result


def start(record, profile, verify, now):
    """Create one release record without adopting or replacing an existing release."""
    require(record.value is None, "Release already loaded")
    verification = source_evidence(record, verify)
    record.commit(initial(profile, record.identity["source_sha"], verification, now))
    return {"state": "release_created"}


def load_or_start(record, profile, verify, now):
    """Resume existing evidence or initialize only after an explicit missing-object response."""
    source_evidence(record, verify)
    claim_target(profile, record.identity["source_sha"], record.read, record.write, now)
    try:
        record.refresh()
    except MissingJournalObject:
        require(record.value is None, "Previously loaded release disappeared; reconcile storage")
        return start(record, profile, verify, now)
    source_evidence(record, verify)
    return {"state": "release_loaded"}


def tick(record, *, verify, plan, read_runs, authenticate, read, send, now, operation_id=None):
    """Dispatch or reconcile one stage without holding a child workflow's concurrency lock."""
    record.refresh()
    source_evidence(record, verify)
    selected = next_stage(record.value, record.identity)
    if selected["action"] == "retired":
        return {
            "state": "hold",
            "reason": "release_retired",
            "successor_source": selected["successor_source"],
        }
    if selected["action"] == "complete":
        return {"state": "release_complete"}
    if selected["action"] == "prepare":
        stage = selected["stage"]
        if stage in {
            "upgrade_prepare",
            "upgrade_create",
            "upgrade_inspect",
            "upgrade",
            "cleanup_upgrade",
            "cleanup_upgrade_check",
        }:
            catalog_stage = record.value["stages"].get("catalog", {})
            catalog_evidence = catalog_stage.get("evidence", {})
            catalog = catalog_evidence.get("documents", {}).get("schema-probe-receipt.json", {})
            revisions = catalog.get("receipt", {}).get("catalog", {}).get("alembic_revisions")
            head = migration_chain(Path(__file__).parents[1] / "migrations/versions")[-1][
                "revision"
            ]
            if revisions == [head]:
                record.skip(
                    stage,
                    {
                        "reason": "schema_already_current",
                        "revision": head,
                        "catalog_evidence_sha256": catalog_stage["evidence_sha256"],
                    },
                    now,
                )
                return {"state": "stage_not_required", "stage": stage}
        prepared = plan(selected["stage"], record.value)
        if isinstance(prepared, dict) and set(prepared) == {"wait"}:
            return {"state": "wait", "stage": stage, "reason": prepared["wait"]}
        require(
            isinstance(prepared, dict) and set(prepared) == {"inputs"},
            "An explicit stage input plan is required",
        )
        return dispatch(
            record,
            selected["stage"],
            operation_id or uuid.uuid4().hex,
            prepared["inputs"],
            read=read,
            now=now,
            send=send,
        )
    stage = selected["stage"]
    observed = reconcile(record, read_runs(WORKFLOWS[stage], record.identity["source_sha"]))
    if observed["action"] != "authenticate_receipt":
        return {"state": observed["action"], **observed}
    result = authenticate(stage, observed["run_id"], record.value)
    require(
        isinstance(result, dict) and set(result) == {"outcome", "evidence"},
        "Authenticated stage evidence required",
    )
    proof = result["evidence"]
    require(
        isinstance(proof, dict)
        and proof.get("run_id") == observed["run_id"]
        and proof.get("source_sha") == record.identity["source_sha"]
        and proof.get("profile_sha256") == record.identity["profile_sha256"]
        and proof.get("stage") == stage,
        "Stage receipt authority differs",
    )
    record.complete(selected["operation_id"], proof, outcome=result["outcome"], now=now)
    return {"state": "stage_complete", "stage": stage, "run_id": observed["run_id"]}
