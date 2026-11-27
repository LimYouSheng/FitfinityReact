"""Authenticate stage outcomes before advancing the durable release record."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from deployment_profile import fingerprint, identities
from operator_checks import require
from release_evidence import catalog_matches, observed_catalog
from release_observation import digest
from release_receipts import fetch

STATES = {
    "probe_create": {"create_submitted"},
    "catalog": {"observed"},
    "post_upgrade_catalog": {"observed"},
    "backup": {"snapshot_ready"},
    "upgrade_create": {"create_submitted"},
    "upgrade_inspect": {"worker_verified"},
    "upgrade": {"upgraded", "already_at_target"},
    "rollout": {"template_verified"},
    "resume": {"maintenance_finalized"},
    "cleanup_upgrade": {"cleanup_submitted"},
    "cleanup_upgrade_check": {"cleanup_verified"},
    "cleanup_probe": {"cleanup_submitted"},
    "cleanup_probe_check": {"cleanup_verified"},
}


def prepared(record, stage, name):
    """Read a document retained by an authenticated completed preparation stage."""
    return record["stages"][stage]["evidence"]["documents"][name]


def validate(stage, bundle, record, profile, *, now):
    """Match actual operational success to the original submitted stage inputs."""
    source = record["identity"]["source_sha"]
    target = identities(profile)
    require(
        record["identity"]["profile_sha256"] == fingerprint(profile)
        and bundle["source_sha"] == source,
        "Stage source or profile differs",
    )
    inputs = record["pending"]["inputs"]["inputs"]
    values = bundle["documents"]
    if stage == "image":
        value = values["fitfinity-image-candidate.json"]
        require(
            value.get("revision") == source
            and value.get("profile_sha256") == target["profile_sha256"]
            and value.get("account") == target["account"]
            and value.get("region") == target["region"]
            and all(
                value.get(key) is True
                for key in ("candidate_ready", "image_published", "scan_policy_passed")
            )
            and re.fullmatch(r"sha256:[a-f0-9]{64}", value.get("image_digest", "")),
            "Published image acceptance missing",
        )
        if value.get("scan_acceptance", {}).get("kind") == "developer_exception":
            from release_image_validation import validate_scan_acceptance

            validate_scan_acceptance(
                value,
                value.get("scan_pages", []),
                datetime.fromtimestamp(now, UTC),
                profile=profile,
            )
    elif stage == "observation":
        value = values["release-observation.json"]
        require(
            value.get("source_sha") == source
            and value.get("profile_sha256") == target["profile_sha256"]
            and value.get("account") == target["account"]
            and value.get("region") == target["region"],
            "Observation target differs",
        )
        observed = datetime.fromisoformat(value["observed_at"])
        require(
            observed.tzinfo is not None and 0 <= now - observed.timestamp() <= 3600,
            "Fresh observation required",
        )
    elif stage in {"prepare", "upgrade_prepare"}:
        value = values["release-readiness.json"]
        require(
            value.get("source_sha") == source
            and value.get("profile_sha256") == target["profile_sha256"]
            and value.get("frontend_manifest"),
            "Prepared frontend source/profile missing",
        )
        for key, path, field in (
            ("probe_bindings", "schema-probe-review/review.json", "bindings"),
            ("upgrade_bindings", "schema-upgrade-review/review.json", "binding"),
            ("maintenance_bindings", "maintenance-review/review.json", None),
        ):
            if inputs.get(key):
                document = values.get(path, {})
                require(
                    (document.get(field) if field else document) == json.loads(inputs[key]),
                    "Prepared review differs from dispatched bindings",
                )
    elif stage in {
        "probe_create",
        "catalog",
        "post_upgrade_catalog",
        "cleanup_probe",
        "cleanup_probe_check",
    }:
        value = values["schema-probe-receipt.json"]
        require(
            value.get("source_sha") == source
            and value.get("profile_sha256") == target["profile_sha256"]
            and value.get("operation_id") == inputs["operation_id"],
            "Probe operation differs",
        )
        if stage in {"catalog", "post_upgrade_catalog"}:
            catalog = observed_catalog(
                value,
                source=source,
                profile_sha256=target["profile_sha256"],
                sql_path=Path(__file__).with_name("read-schema.sql"),
            )
            observed = datetime.fromisoformat(catalog["observed_at"])
            require(
                observed.tzinfo is not None and 0 <= now - observed.timestamp() <= 3600,
                "Fresh catalog observation required",
            )
            if stage == "post_upgrade_catalog":
                grants = json.loads(
                    (Path(__file__).parents[1] / "app/runtime-grants.json").read_text()
                )
                database = prepared(record, "prepare", "schema-probe-review/review.json")[
                    "bindings"
                ]["db_name"]
                catalog_matches(catalog, grants, database=database, now=now)
    elif stage == "backup":
        value = values["maintenance-receipt.json"]
        review = prepared(record, "prepare", "maintenance-review/review.json")
        expected = {key: review[key] for key in ("source_sha", "profile_sha256", "operation_id")}
        expected["review_sha256"] = digest(review)
        require(value.get("identity") == expected, "Original backup operation differs")
    elif stage in {
        "upgrade_create",
        "upgrade_inspect",
        "upgrade",
        "cleanup_upgrade",
        "cleanup_upgrade_check",
    }:
        value = values["schema-upgrade-receipt.json"]
        review = prepared(record, "upgrade_prepare", "schema-upgrade-review/review.json")
        require(inputs["template_sha256"] == review["template_sha256"], "Upgrade template differs")
        require(
            value.get("identity")
            == {
                "FitfinityOperation": review["binding"]["operation_id"],
                "FitfinitySource": source,
                "FitfinityProfile": target["profile_sha256"],
                "FitfinityTemplate": inputs["template_sha256"],
            },
            "Upgrade operation differs",
        )
        if stage == "upgrade":
            result = value.get("result", {})
            require(
                result.get("operation_id") == review["binding"]["operation_id"]
                and result.get("source_sha") == source
                and result.get("schema") == review["binding"]["to_revision"]
                and result.get("from_revision") == review["binding"]["from_revision"]
                and result.get("outcome") == value.get("state"),
                "Upgrade result differs",
            )
    elif stage in {"rollout", "resume"}:
        value = values["rollout-receipt.json"]
        review = json.loads(inputs["review_json"])
        require(
            value.get("review_sha256") == digest(review)
            and value.get("evidence", {}).get("source_sha") == source
            and value.get("evidence", {}).get("profile_sha256") == target["profile_sha256"],
            "Rollout review or evidence differs",
        )
    else:
        raise RuntimeError("Unknown release stage")
    if stage in STATES:
        require(
            value.get("state") in STATES[stage] and not value.get("error"),
            "Child completed without the required operational outcome",
        )
    if stage in {"probe_create", "upgrade_create"}:
        name = target["probe_name"] if stage == "probe_create" else target["upgrade_name"]
        prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/{name}/"
        require(
            isinstance(value.get("stack_id"), str)
            and value["stack_id"].startswith(prefix)
            and len(value["stack_id"]) > len(prefix),
            "Retained worker stack identity missing",
        )
    elif inputs.get("stack_id") and value.get("stack_id") is not None:
        require(value["stack_id"] == inputs["stack_id"], "Worker stack changed")
    return {
        "outcome": "complete",
        "evidence": {
            **bundle,
            "stage": stage,
            "profile_sha256": target["profile_sha256"],
            "dispatch_inputs": dict(inputs),
        },
    }


def authenticate(stage, run_id, record, profile, *, now):
    """Fetch authenticated artifact bytes and enforce the stage's operational result."""
    bundle = fetch(stage, run_id, record["identity"]["source_sha"], profile)
    return validate(stage, bundle, record, profile, now=now)
