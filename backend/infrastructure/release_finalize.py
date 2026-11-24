"""Retire only the reviewed maintenance tags after verified release health."""

import re
import time

from deployment_profile import identities
from operator_checks import require
from release_execution import review_identity
from release_observation import digest


def finish(mode, review, evidence, prior, health, call, persist, *, profile, now=None):
    """Record removal intent once and inspect uncertain tag removal without replay."""
    require(mode in {"finalize", "inspect"}, "Unknown maintenance finalization action")
    clock = time.time() if now is None else now
    target = identities(profile)
    identity = review_identity(review, profile, clock, recovery=mode == "inspect")
    require(
        prior is not None
        and prior.get("identity") == identity
        and prior.get("execution_requested") is True
        and prior.get("state")
        in {"template_verified", "finalize_submitted", "maintenance_finalized"},
        "Verified original resumption receipt required",
    )
    require(
        health.get("state") == "health_verified"
        and health.get("review_sha256") == digest(review)
        and health.get("evidence_sha256") == digest(evidence)
        and type(health.get("observed_at")) in {int, float}
        and 0 <= clock - health["observed_at"] <= 300,
        "Fresh exact-release health evidence required",
    )
    caller = call("sts", "get-caller-identity", {})
    require(
        caller.get("Account") == target["account"]
        and re.fullmatch(
            rf"arn:aws:sts::{target['account']}:assumed-role/{re.escape(target['hosting_role'])}/[\w+=,.@-]+",
            caller.get("Arn", ""),
        ),
        "Exact hosting operator required",
    )
    arn = (
        f"arn:aws:lambda:{target['region']}:{target['account']}:"
        f"function:{target['runtime_function']}"
    )
    function = call("lambda", "get-function", {"FunctionName": target["runtime_function"]})
    require(
        function.get("Configuration", {}).get("FunctionArn") == arn
        and isinstance(function.get("Tags"), dict)
        and not function.get("TagsError"),
        "Exact runtime tags required",
    )
    tags = function["Tags"]
    keys = [key for key in ("FitfinityMaintenance", "FitfinitySnapshot") if key in tags]
    require(
        all(tags[key] == review["maintenance_marker"] for key in keys),
        "Foreign maintenance ownership prevents finalization",
    )
    receipt = {**prior, "health": health}
    if mode == "inspect":
        require(
            prior.get("finalization_requested") is True, "Original finalization intent required"
        )
        receipt["state"] = "maintenance_finalized" if not keys else "finalize_submitted"
        persist(receipt)
        return receipt
    require(
        prior.get("state") == "template_verified"
        and not prior.get("finalization_requested")
        and "FitfinityMaintenance" in keys,
        "Inspect original finalization; never replay removal",
    )
    receipt.update(state="finalize_submitted", finalization_requested=True)
    persist(dict(receipt))
    call("lambda", "untag-resource", {"Resource": arn, "TagKeys": keys})
    # A successful response is not a receipt of the subsequent observed tag state.
    return receipt
