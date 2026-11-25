"""Update a separately owned runtime boundary using its existing authorized operator."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from deployment_profile import identities, load
from hosting_frontend import source_check
from operation_journal import Journal
from operator_checks import require
from release_execution import execute, live_target, template, validate_authority
from release_features import external_identity, prepare, verify_effective
from release_observation import digest
from rollout_provider import aws


def advance(action, review, hosting, owner, call, persist, *, profile, prior=None, now=None):
    """Rebuild the single-resource change from the original private files at each step."""
    require(action in {"create", "inspect", "execute", "verify"}, "Unknown owner action")
    authority_fields = {
        "operator_role_arn",
        "operator_user_arn",
        "operator_user_id",
        "service_role_arn",
    }
    authority = {key: review[key] for key in authority_fields if key in review}
    require(
        set(review) - authority.keys()
        == {
            "profile_sha256",
            "source_sha",
            "operation_id",
            "expires_at",
            "maintenance_marker",
            "hosting_stack_arn",
            "hosting_template_sha256",
            "feature_values",
            "external_boundary",
            "owner_original_sha256",
        },
        "Exact external owner review required",
    )
    target = identities(profile)
    validate_authority(authority, profile)
    external = external_identity(review["external_boundary"], profile)
    prefix = (
        f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
        + target["hosting_stack"]
        + "/"
    )
    require(
        re.fullmatch(re.escape(prefix) + r"[a-f0-9-]+", review["hosting_stack_arn"])
        and review["profile_sha256"] == target["profile_sha256"]
        and re.fullmatch(
            r"[a-f0-9]{32}:" + re.escape(review["source_sha"]) + ":" + target["profile_sha256"],
            review["maintenance_marker"],
        )
        and digest(hosting) == review["hosting_template_sha256"]
        and digest(owner) == review["owner_original_sha256"],
        "Original owner, paused hosting source and matching maintenance marker required",
    )
    change = prepare(
        hosting,
        review["feature_values"],
        profile=profile,
        boundary_template=owner,
        boundary_template_sha256=review["owner_original_sha256"],
    )
    logical = external["logical_id"]
    candidate = change["boundary_candidate_template"]
    require(
        change["boundary_update_required"]
        and change["boundary_resource"] == logical
        and digest(candidate) == external["template_sha256"],
        "Single required external boundary change and exact destination required",
    )
    expanded = {
        **{
            key: review[key]
            for key in (
                "profile_sha256",
                "source_sha",
                "operation_id",
                "expires_at",
                "maintenance_marker",
            )
        },
        "mode": "boundary",
        "stack_arn": external["stack_arn"],
        "boundary_resource": logical,
        "original_template": owner,
        "candidate_template": candidate,
    }
    if prior is not None:
        require(
            prior.get("owner_review_sha256") == digest(review), "Original owner receipt differs"
        )
    if action in {"create", "execute"}:
        live_target(
            {
                **expanded,
                "mode": "rollout",
                "stack_arn": review["hosting_stack_arn"],
                "boundary_resource": None,
            },
            call,
            profile,
        )
        require(
            template(call, review["hosting_stack_arn"]) == hosting, "Paused hosting base changed"
        )
    if action != "inspect":
        active = candidate if action == "verify" else owner
        verify_effective(
            call,
            profile,
            hosting["Resources"]["ApiRole"]["Properties"],
            active["Resources"][logical]["Properties"]["PolicyDocument"],
        )

    def save(receipt):
        persist({**receipt, "owner_review_sha256": digest(review)})

    receipt = execute(
        action,
        expanded,
        call,
        save,
        profile=profile,
        prior=prior,
        now=now,
        boundary_authority=authority,
    )
    return {**receipt, "owner_review_sha256": digest(review)}


def main():
    """Keep each write's exclusive journal alongside the private reviewed input files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "inspect", "execute", "verify"])
    for field in ("profile", "review", "hosting-template", "owner-template", "journal"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--review-sha256", required=True)
    args = parser.parse_args()
    review = json.loads(args.review.read_text())
    require(digest(review) == args.review_sha256, "Reviewed owner operation digest differs")
    profile = load(args.profile)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    source_check(Path.cwd(), source)
    read_only = args.action in {"inspect", "verify"}
    require(re.fullmatch(r"[a-f0-9]{40}", review["source_sha"]), "Reviewed source required")
    if read_only:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", review["source_sha"], source], check=True
        )
    else:
        require(source == review["source_sha"], "Owner writes require the exact reviewed checkout")
    operation = review["operation_id"]
    require(re.fullmatch(r"[a-f0-9]{32}", operation), "Exact owner operation ID required")
    args.journal.mkdir(mode=0o700, parents=True, exist_ok=True)
    prefix = args.journal / operation
    created = prefix.with_suffix(".create.json")
    submitted = prefix.with_suffix(".execute.json")
    prior = None
    if args.action == "create":
        require(
            not created.exists() and not submitted.exists(), "Inspect the original owner creation"
        )
    else:
        require(created.is_file(), "Original owner creation journal required")
        require(
            args.action != "execute" or not submitted.exists(),
            "Inspect the original owner execution",
        )
        prior = json.loads((submitted if submitted.exists() else created).read_text())
    suffix = args.action + ("-" + uuid4().hex if read_only else "")
    journal = None

    def persist(receipt):
        nonlocal journal
        if journal is None:
            journal = Journal(prefix.with_suffix("." + suffix + ".json"))
        journal.save(receipt)

    result = advance(
        args.action,
        review,
        json.loads(args.hosting_template.read_text()),
        json.loads(args.owner_template.read_text()),
        lambda service, op, values: aws(service, op, values, profile=profile, read_only=read_only),
        persist,
        profile=profile,
        prior=prior,
    )
    print(result["state"])


if __name__ == "__main__":
    main()
