"""Gate existing-stack rollout on bound artifacts and fresh read-only provider evidence."""

import re
import time
from copy import deepcopy
from datetime import datetime

from deployment_profile import identities
from operator_checks import require
from release_execution import execute, review_identity
from release_frontend import transfer
from release_image_validation import validate_image
from release_observation import digest


def binding(review, evidence, profile):
    """Match the reviewed runtime and frontend template to collected artifact identities."""
    target = identities(profile)
    require(
        review.get("mode") == "rollout"
        and evidence.get("decision") == "HOLD"
        and evidence.get("source_sha") == review.get("source_sha")
        and evidence.get("profile_sha256") == target["profile_sha256"]
        and re.fullmatch(r"sha256:[a-f0-9]{64}", evidence.get("image_digest", ""))
        and re.fullmatch(r"[a-f0-9]{64}", evidence.get("frontend_sha256", "")),
        "Exact collected rollout evidence required",
    )
    expected = {"frontend", "image", "catalog"}
    action = evidence.get("schema_action")
    require(action in {"upgrade", "unchanged"}, "Explicit collected schema action required")
    if action == "upgrade":
        expected.add("upgrade")
    runs = evidence.get("producer_runs", {})
    require(
        set(runs) == expected
        and all(
            isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value)
            for value in runs.values()
        ),
        "Authenticated producer inventory required",
    )
    resources = review["candidate_template"]["Resources"]
    require(
        resources["ApiFunction"]["Properties"]["Code"]
        == {
            "ImageUri": target["registry"]
            + "/"
            + target["image_repository"]
            + "@"
            + evidence["image_digest"]
        },
        "Reviewed template image differs from collected evidence",
    )
    origins = resources["Distribution"]["Properties"]["DistributionConfig"]["Origins"]
    frontend = [row for row in origins if row.get("Id") == "frontend"]
    prefix = f"releases/{review['source_sha']}/{evidence['frontend_sha256']}"
    require(
        evidence.get("frontend_prefix") == prefix
        and len(frontend) == 1
        and frontend[0].get("OriginPath") == "/" + prefix,
        "Reviewed frontend origin differs from collected bytes",
    )
    return digest(evidence)


def check_artifacts(review, evidence, image, folder, call, profile, clock):
    """Recheck scan, stored frontend and catalog freshness before release writes."""
    validate_image(
        image,
        evidence,
        call,
        clock(),
        profile=profile,
        required_files=evidence["required_image_files"],
    )
    frontend_review = {
        key: review[key] for key in ("source_sha", "profile_sha256", "stack_arn", "expires_at")
    }
    frontend_review["manifest_sha256"] = evidence["frontend_sha256"]
    transfer(frontend_review, folder, profile, call, lambda _: None, inspect=True, clock=clock)
    observed = datetime.fromisoformat(evidence.get("catalog_observed_at", ""))
    require(
        observed.tzinfo is not None and 0 <= clock() - observed.timestamp() <= 3600,
        "Fresh catalog evidence required before rollout write",
    )


def advance(
    action, review, evidence, image, folder, call, persist, *, profile, prior=None, now=None
):
    """Require current scan and uploaded objects before either change-set write."""
    clock = time.time if now is None else lambda: now
    recovery = action in {"inspect", "verify"}
    review_identity(review, profile, clock(), recovery=recovery)
    evidence_hash = binding(review, evidence, profile)
    if prior is not None:
        require(prior.get("evidence_sha256") == evidence_hash, "Original rollout evidence required")
    if action in {"create", "execute"}:
        check_artifacts(review, evidence, image, folder, call, profile, clock)

    def save(receipt):
        persist({**receipt, "evidence_sha256": evidence_hash})

    result = execute(action, review, call, save, profile=profile, prior=prior, now=now)
    return {**result, "evidence_sha256": evidence_hash}


def resumption_plan(
    rollout_review,
    evidence,
    verified_receipt,
    *,
    profile,
    operation_id,
    expires_at,
    concurrency,
    now=None,
    recovery=False,
):
    """Bind a separate concurrency-only review to a verified paused release."""
    observed = time.time() if now is None else now
    identity = review_identity(rollout_review, profile, observed, recovery=True)
    evidence_hash = binding(rollout_review, evidence, profile)
    require(
        verified_receipt.get("identity") == identity
        and verified_receipt.get("state") == "template_verified"
        and verified_receipt.get("execution_requested") is True
        and verified_receipt.get("evidence_sha256") == evidence_hash,
        "Verified original paused rollout receipt required",
    )
    require(
        operation_id != rollout_review["operation_id"], "Separate resumption operation required"
    )
    require(type(concurrency) is int and concurrency > 0, "Explicit positive concurrency required")
    original = deepcopy(rollout_review["candidate_template"])
    require(
        original["Resources"]["ApiFunction"]["Properties"].get("ReservedConcurrentExecutions") == 0,
        "Verified release must remain paused",
    )
    candidate = deepcopy(original)
    candidate["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = (
        concurrency
    )
    review = {
        **deepcopy(rollout_review),
        "operation_id": operation_id,
        "expires_at": expires_at,
        "original_template": original,
        "candidate_template": candidate,
        "mode": "resume",
        "boundary_resource": None,
    }
    review_identity(review, profile, observed, recovery=recovery)
    return {
        "decision": "HOLD",
        "review": review,
        "rollout_receipt_sha256": digest(verified_receipt),
        "evidence_sha256": evidence_hash,
        "requirements": [
            "Authenticate the original receipt producer before using this plan",
            "Recheck live artifacts, schema, maintenance ownership and capacity before execution",
            "Verify health after resumption; finalize maintenance separately",
        ],
    }


def resume(
    action,
    plan,
    rollout_review,
    evidence,
    verified_receipt,
    image,
    folder,
    call,
    persist,
    *,
    profile,
    prior=None,
    now=None,
):
    """Execute only the bound concurrency review and retain original resumption identity."""
    require(action in {"create", "inspect", "execute", "verify"}, "Unknown resumption action")
    clock = time.time if now is None else lambda: now
    review = plan["review"]
    review_identity(review, profile, clock(), recovery=action in {"inspect", "verify"})
    expected = resumption_plan(
        rollout_review,
        evidence,
        verified_receipt,
        profile=profile,
        operation_id=review["operation_id"],
        expires_at=review["expires_at"],
        concurrency=review["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ],
        now=clock(),
        recovery=action in {"inspect", "verify"},
    )
    require(plan == expected, "Original reviewed resumption plan required")
    plan_hash = digest(plan)
    if prior is not None:
        require(
            prior.get("resumption_plan_sha256") == plan_hash, "Original resumption receipt required"
        )
    if action in {"create", "execute"}:
        check_artifacts(review, evidence, image, folder, call, profile, clock)

    def save(receipt):
        persist({**receipt, "resumption_plan_sha256": plan_hash})

    receipt = execute(action, review, call, save, profile=profile, prior=prior, now=now)
    return {**receipt, "resumption_plan_sha256": plan_hash}
