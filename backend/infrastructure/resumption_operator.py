"""Bind Actions resumption to an authenticated completed paused-rollout receipt."""

import json
import re
import time
from copy import deepcopy

from operator_checks import require
from release_execution import template
from release_features import check_rollout_access
from release_observation import digest
from release_rollout import resume, resumption_plan

MODES = {
    "resume-create",
    "resume-inspect",
    "resume-execute",
    "resume-verify",
    "resume-health",
    "resume-finalize",
    "resume-finalize-inspect",
}
RECOVERY = {"resume-inspect", "resume-verify", "resume-health", "resume-finalize-inspect"}


def validate(value, *, recovery=False):
    """Require a distinct reviewed operation and an exact completed-rollout producer."""
    require(
        isinstance(value, dict)
        and set(value) == {"operation_id", "expires_at", "concurrency", "verified_run"},
        "Exact resumption metadata required",
    )
    require(
        re.fullmatch(r"[a-f0-9]{32}", value["operation_id"] or "")
        and type(value["expires_at"]) is int
        and (recovery or 0 < value["expires_at"] - time.time() <= 3600)
        and type(value["concurrency"]) is int
        and value["concurrency"] > 0
        and re.fullmatch(r"[1-9][0-9]*", value["verified_run"] or ""),
        "Reviewed resumption identity, expiry, capacity and producer required",
    )
    return value


def execute_step(
    mode, review, evidence, root, call, persist, *, profile, verified, prior=None, confirmation=None
):
    """Recover hashed templates without persisting runtime secrets in Actions artifacts."""
    from rollout_operator import expanded_rollout, restore_original

    require(mode in MODES, "Unknown resumption step")
    settings = validate(review["resumption"], recovery=mode in RECOVERY)
    original_review = {key: value for key, value in review.items() if key != "resumption"}
    require(
        verified.get("review_sha256") == digest(original_review)
        and verified.get("state") == "template_verified"
        and verified.get("evidence") == evidence
        and "resumption_plan_sha256" not in verified,
        "Verified original paused rollout required",
    )
    require(mode != "resume-create" or prior is None, "Inspect original resumption; never replay")
    require(mode == "resume-create" or prior is not None, "Original resumption receipt required")
    if prior is not None:
        require(
            prior.get("review_sha256") == digest(review)
            and prior.get("verified_rollout_sha256") == digest(verified)
            and prior.get("evidence") == evidence,
            "Original resumption evidence differs",
        )
        require(
            not prior.get("finalization_requested") or mode == "resume-finalize-inspect",
            "Inspect original finalization; never replay removal",
        )
    # A subsequent stack update invalidates earlier change sets. Recover the paused
    # template from its sole reviewed delta and verify both original template hashes below.
    candidate = deepcopy(template(call, review["stack_arn"]))
    runtime = candidate["Resources"]["ApiFunction"]["Properties"]
    capacity = runtime.get("ReservedConcurrentExecutions")
    require(
        type(capacity) is int and capacity in {0, settings["concurrency"]},
        "Current stack capacity differs from the reviewed resumption",
    )
    runtime["ReservedConcurrentExecutions"] = 0
    original = restore_original(
        candidate,
        verified.get("original_release"),
        feature_values=review.get("feature_values"),
        profile=profile,
    )
    require(
        digest(original) == review["original_template_sha256"]
        and digest(candidate) == review["candidate_template_sha256"],
        "Verified paused templates differ",
    )
    if review.get("feature_values") and mode not in {"resume-inspect", "resume-finalize-inspect"}:
        check_rollout_access(original_review, candidate, call, profile)
    expanded = expanded_rollout(original_review, original, candidate)
    plan = resumption_plan(
        expanded,
        evidence,
        verified,
        profile=profile,
        operation_id=settings["operation_id"],
        expires_at=settings["expires_at"],
        concurrency=settings["concurrency"],
        recovery=mode in RECOVERY,
    )

    def save(receipt):
        persist(
            {
                **receipt,
                "review_sha256": digest(review),
                "evidence": evidence,
                "verified_rollout_sha256": digest(verified),
            }
        )

    image = (
        json.loads((root / "image/fitfinity-image-candidate.json").read_text())
        if mode not in RECOVERY
        else {}
    )
    if mode in {"resume-finalize", "resume-finalize-inspect"}:
        require(
            prior.get("resumption_plan_sha256") == digest(plan), "Original resumption plan required"
        )
        from release_finalize import finish
        from release_health import read_url, verify

        inspecting = mode == "resume-finalize-inspect"
        health = (
            prior.get("health")
            if inspecting
            else verify(
                plan["review"],
                evidence,
                call,
                read_url,
                root / "frontend/release-frontend/dist-api-test",
                profile=profile,
            )
        )
        return finish(
            "inspect" if inspecting else "finalize",
            plan["review"],
            evidence,
            prior,
            health,
            call,
            save,
            profile=profile,
        )
    result = resume(
        "verify" if mode == "resume-health" else mode.removeprefix("resume-"),
        plan,
        expanded,
        evidence,
        verified,
        image,
        root / "frontend/release-frontend/dist-api-test",
        call,
        save,
        profile=profile,
        prior=prior,
        confirmation=confirmation,
    )
    if mode == "resume-health":
        from release_health import read_url, verify

        health = verify(
            plan["review"],
            evidence,
            call,
            read_url,
            root / "frontend/release-frontend/dist-api-test",
            profile=profile,
        )
        result = {**result, "health": health}
        save(result)
    return result
