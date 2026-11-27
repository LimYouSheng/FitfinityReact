"""Coordinate release stages through conditional durable records."""

import hashlib
import json
import re
from copy import deepcopy

from deployment_journal import MissingJournalObject
from deployment_profile import fingerprint
from operator_checks import require

STAGES = (
    "image",
    "observation",
    "prepare",
    "probe_create",
    "catalog",
    "backup",
    "upgrade_prepare",
    "upgrade_create",
    "upgrade_inspect",
    "upgrade",
    "post_upgrade_catalog",
    "rollout",
    "resume",
    "cleanup_upgrade",
    "cleanup_upgrade_check",
    "cleanup_probe",
    "cleanup_probe_check",
)


def encode(value):
    """Serialize a record deterministically for integrity checks."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def identity(profile, source):
    """Bind a release to the exact reviewed target and source."""
    require(
        isinstance(source, str) and re.fullmatch(r"[a-f0-9]{40}", source),
        "Exact release source required",
    )
    return {
        "repository": profile["github_repository"],
        "profile_sha256": fingerprint(profile),
        "source_sha": source,
    }


def initial(profile, source, verification, now):
    """Prepare a release only from authenticated source verification."""
    bound = identity(profile, source)
    require(
        verification.get("state") == "source_verified"
        and verification.get("source_sha") == source
        and verification.get("repository") == bound["repository"],
        "Source verification differs",
    )
    return {
        "schema_version": 1,
        "identity": bound,
        "generation": 0,
        "updated_at": now,
        "verification": deepcopy(verification),
        "stages": {},
        "pending": None,
    }


def validate(record, expected):
    """Reject foreign records and unrecognized state before selecting an action."""
    require(
        record.get("schema_version") == 1 and record.get("identity") == expected,
        "Release record identity differs",
    )
    require(
        type(record.get("generation")) is int and record["generation"] >= 0,
        "Invalid release generation",
    )
    require(
        isinstance(record.get("stages"), dict) and set(record["stages"]) <= set(STAGES),
        "Unknown release stage",
    )
    for stage, result in record["stages"].items():
        require(
            result.get("outcome") in {"complete", "not_required"}
            and re.fullmatch(r"[a-f0-9]{64}", result.get("evidence_sha256", "")),
            f"Unverified stage: {stage}",
        )
        require(
            hashlib.sha256(encode(result.get("evidence"))).hexdigest() == result["evidence_sha256"],
            "Release evidence digest differs",
        )
    require(
        set(record["stages"]) == set(STAGES[: len(record["stages"])]),
        "Release stages are not sequential",
    )
    require("pending" in record, "Pending state missing")
    pending = record.get("pending")
    if pending is not None:
        require(
            len(record["stages"]) < len(STAGES)
            and pending.get("stage") == STAGES[len(record["stages"])]
            and pending.get("state") in {"dispatch_intent", "dispatched", "blocked"}
            and re.fullmatch(r"[a-f0-9]{32}", pending.get("operation_id", "")),
            "Invalid pending operation",
        )
    if "retirement" in record:
        from release_retirement import terminal

        terminal(record)
    return record


def next_stage(record, expected):
    """Select an unfinished stage without replaying a pending dispatch."""
    validate(record, expected)
    if "retirement" in record:
        return {
            "action": "retired",
            "successor_source": record["retirement"]["plan"]["successor_source"],
        }
    if record["pending"] is not None:
        return {"action": "reconcile", **deepcopy(record["pending"])}
    stage = next((stage for stage in STAGES if stage not in record["stages"]), None)
    return {"action": "complete"} if stage is None else {"action": "prepare", "stage": stage}


def claim_target(profile, source, read, write, now):
    """Reserve a target until its prior release completes every stage and cleanup."""
    expected = identity(profile, source)
    target = "/".join(profile[key] for key in ("account", "region", "resource_prefix"))
    prefix = f"releases/targets/{target}/"
    etag = None
    try:
        current, etag = read(prefix + "current.json")
    except MissingJournalObject:
        current = None
    if current is not None:
        require(isinstance(etag, str) and etag, "Target claim ETag missing")
        owner = current.get("identity", {})
        require(
            current.get("schema_version") == 1
            and owner.get("repository") == expected["repository"]
            and owner.get("profile_sha256") == expected["profile_sha256"]
            and re.fullmatch(r"[a-f0-9]{40}", owner.get("source_sha", "")),
            "Target claim identity differs",
        )
        if owner == expected:
            return {"state": "target_claimed", "identity": expected}
        previous, _ = read(
            "releases/" + expected["profile_sha256"] + "/" + owner["source_sha"] + "/current.json"
        )
        state = next_stage(previous, owner)
        require(
            state == {"action": "complete"}
            or state == {"action": "retired", "successor_source": source},
            "Prior release still owns this target; reconcile it before starting another source",
        )
    value = {"schema_version": 1, "identity": expected, "claimed_at": now}
    body = encode(value)
    write(prefix + "events/" + hashlib.sha256(body).hexdigest() + ".json", body, if_none_match="*")
    condition = {"if_match": etag} if etag else {"if_none_match": "*"}
    acknowledgement = write(prefix + "current.json", body, **condition)
    require(
        isinstance(acknowledgement, str) and acknowledgement, "Target claim acknowledgement missing"
    )
    return {"state": "target_claimed", "identity": expected}


class ReleaseRecord:
    """Commit immutable history before a compare-and-swap release pointer."""

    def __init__(self, profile, source, read, write):
        self.identity = identity(profile, source)
        self.prefix = "releases/" + self.identity["profile_sha256"] + "/" + source + "/"
        self.read, self.write = read, write
        self.value, self.etag = None, None
        self.uncertain = False

    def refresh(self):
        """Read the authoritative record and retain its conditional-write token."""
        value, etag = self.read(self.prefix + "current.json")
        require(isinstance(etag, str) and etag, "Release ETag missing")
        self.value = deepcopy(validate(value, self.identity))
        self.etag = etag
        self.uncertain = False
        return deepcopy(self.value)

    def commit(self, value):
        """Persist history and pointer; block further writes after any uncertain result."""
        require(not self.uncertain, "Refresh required after an uncertain journal write")
        validate(value, self.identity)
        require(
            value["generation"] == (self.value["generation"] + 1 if self.value else 0),
            "Release generation differs",
        )
        body = encode(value)
        digest = hashlib.sha256(body).hexdigest()
        self.uncertain = True
        self.write(self.prefix + "events/" + digest + ".json", body, if_none_match="*")
        condition = {"if_match": self.etag} if self.etag else {"if_none_match": "*"}
        etag = self.write(self.prefix + "current.json", body, **condition)
        require(isinstance(etag, str) and etag, "Release write acknowledgement missing")
        self.value, self.etag, self.uncertain = deepcopy(value), etag, False

    def intent(self, stage, operation_id, inputs, now):
        """Persist exact dispatch inputs before requesting a child workflow."""
        require(self.value is not None, "Load or create a release first")
        require(
            next_stage(self.value, self.identity) == {"action": "prepare", "stage": stage},
            "Release has pending work or a different next stage",
        )
        value = deepcopy(self.value)
        value.update(generation=value["generation"] + 1, updated_at=now)
        value["pending"] = {
            "stage": stage,
            "operation_id": operation_id,
            "state": "dispatch_intent",
            "inputs": deepcopy(inputs),
        }
        self.commit(value)

    def complete(self, operation_id, evidence, *, outcome, now):
        """Record an authenticated stage result while retaining its original operation."""
        require(self.value is not None, "Load a release first")
        pending = self.value["pending"]
        require(
            pending is not None and pending["operation_id"] == operation_id,
            "Completion does not belong to the pending operation",
        )
        require(outcome in {"complete", "not_required"}, "Unsuccessful stage cannot advance")
        value = deepcopy(self.value)
        value["stages"][pending["stage"]] = {
            "outcome": outcome,
            "operation_id": operation_id,
            "evidence_sha256": hashlib.sha256(encode(evidence)).hexdigest(),
            "evidence": deepcopy(evidence),
            "completed_at": now,
        }
        value.update(pending=None, generation=value["generation"] + 1, updated_at=now)
        self.commit(value)

    def skip(self, stage, evidence, now):
        """Atomically record a schema-proven unnecessary stage without dispatch intent."""
        require(
            next_stage(self.value, self.identity) == {"action": "prepare", "stage": stage},
            "Only the next undispatched stage can be unnecessary",
        )
        value = deepcopy(self.value)
        value["stages"][stage] = {
            "outcome": "not_required",
            "operation_id": None,
            "evidence_sha256": hashlib.sha256(encode(evidence)).hexdigest(),
            "evidence": deepcopy(evidence),
            "completed_at": now,
        }
        value.update(generation=value["generation"] + 1, updated_at=now)
        self.commit(value)
