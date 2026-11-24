"""Run reviewed frontend upload and paused rollout steps from protected Actions."""

import argparse
import json
import os
import re
import subprocess
import time
from copy import deepcopy
from pathlib import Path

import resumption_operator
from deployment_profile import identities, load
from hosting_frontend import source_check
from operation_journal import Journal
from operator_checks import require
from release_artifacts import collect
from release_execution import template
from release_frontend import transfer
from release_observation import digest
from release_plan import prepare
from release_rollout import advance
from rollout_provider import aws
from schema_probe_artifacts import fetch, run_binding

MODES = {"upload", "upload-inspect", "create", "inspect", "execute", "verify"}
MODES |= resumption_operator.MODES
RECOVERY = {"upload-inspect", "inspect", "verify"} | resumption_operator.RECOVERY


def metadata(value, source, profile, *, recovery=False):
    """Validate source-bound metadata without retaining raw runtime templates."""
    target = identities(profile)
    require(
        set(value)
        == {
            "source_sha",
            "profile_sha256",
            "operation_id",
            "expires_at",
            "stack_arn",
            "original_template_sha256",
            "candidate_template_sha256",
            "maintenance_marker",
        },
        "Exact rollout metadata required",
    )
    require(
        value["source_sha"] == source
        and re.fullmatch(r"[a-f0-9]{40}", source)
        and value["profile_sha256"] == target["profile_sha256"]
        and re.fullmatch(r"[a-f0-9]{32}", value["operation_id"])
        and type(value["expires_at"]) is int
        and (recovery or 0 < value["expires_at"] - time.time() <= 3600),
        "Source, target or review expiry differs",
    )
    for field in ("original_template_sha256", "candidate_template_sha256"):
        require(re.fullmatch(r"[a-f0-9]{64}", value[field]), "Exact template hash required")
    prefix = (
        f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
        + target["hosting_stack"]
        + "/"
    )
    require(
        re.fullmatch(re.escape(prefix) + r"[a-f0-9-]+", value["stack_arn"]), "Wrong rollout stack"
    )
    require(
        re.fullmatch(
            r"[a-f0-9]{32}:" + source + ":" + target["profile_sha256"], value["maintenance_marker"]
        ),
        "Matching maintenance ownership required",
    )
    return value


def fetch_prior(run_id, destination, source, profile, *, recovery=False):
    """Retrieve original intent from a verified manual-main source lineage."""
    require(re.fullmatch(r"[1-9][0-9]*", run_id or ""), "Original rollout run required")
    repository = profile["github_repository"]
    run = json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repository}/actions/runs/{run_id}"], text=True
        )
    )
    require(
        run.get("conclusion") in {"success", "failure", "cancelled"},
        "Original run must have finished",
    )
    producer, attempt = run_binding(
        {**run, "conclusion": "success"},
        "aws-rollout",
        None if recovery else source,
        profile=profile,
    )
    if recovery:
        subprocess.run(["git", "merge-base", "--is-ancestor", source, producer], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", producer, "HEAD"], check=True)
    subprocess.run(
        [
            "gh",
            "run",
            "download",
            run_id,
            "--repo",
            repository,
            "--name",
            f"fitfinity-rollout-{run_id}-{attempt}",
            "--dir",
            str(destination),
        ],
        check=True,
    )


def original_metadata(template_value):
    """Retain only the three public artifact/version pointers needed for recovery."""
    resources = template_value["Resources"]
    version = resources["ApiAlias"]["Properties"]["FunctionVersion"]
    output = template_value.get("Outputs", {}).get("FunctionVersion")
    require(output is None or output.get("Value") == version, "Version output differs from alias")
    origins = resources["Distribution"]["Properties"]["DistributionConfig"]["Origins"]
    frontend = [row for row in origins if row.get("Id") == "frontend"]
    require(len(frontend) == 1, "Exact frontend origin required")
    return {
        "image": resources["ApiFunction"]["Properties"]["Code"]["ImageUri"],
        "version": deepcopy(version),
        "frontend": frontend[0]["OriginPath"],
    }


def restore_original(candidate, pointers):
    """Reconstruct the hashed base without storing environment variables in receipts."""
    require(
        isinstance(pointers, dict) and set(pointers) == {"image", "version", "frontend"},
        "Original release pointers required",
    )
    original = deepcopy(candidate)
    resources = original["Resources"]
    added = resources["ApiAlias"]["Properties"]["FunctionVersion"]["Fn::GetAtt"][0]
    require(re.fullmatch(r"ReleaseVersion[a-f0-9]{56}", added), "Reviewed new version required")
    del resources[added]
    resources["ApiFunction"]["Properties"]["Code"] = {"ImageUri": pointers["image"]}
    resources["ApiAlias"]["Properties"]["FunctionVersion"] = deepcopy(pointers["version"])
    origins = resources["Distribution"]["Properties"]["DistributionConfig"]["Origins"]
    for row in origins:
        if row.get("Id") == "frontend":
            row["OriginPath"] = pointers["frontend"]
    if "FunctionVersion" in original.get("Outputs", {}):
        original["Outputs"]["FunctionVersion"]["Value"] = deepcopy(pointers["version"])
    return original


def execute_step(mode, review, evidence, root, call, persist, *, profile, prior=None):
    """Reconstruct only the reviewed template and preserve metadata-only recovery receipts."""
    require(mode in MODES, "Unknown rollout mode")
    require(mode != "create" or prior is None, "Inspect original creation; never replay")
    if prior is not None:
        require(prior.get("review_sha256") == digest(review), "Original review receipt required")
        require(prior.get("evidence") == evidence, "Original evidence receipt required")
    original_release = prior.get("original_release") if prior else None

    def save(value):
        persist(
            {
                **value,
                "review_sha256": digest(review),
                "evidence": evidence,
                "original_release": original_release,
            }
        )

    folder = root / "frontend/release-frontend/dist-api-test"
    if mode in {"upload", "upload-inspect"}:
        frontend_review = {
            key: review[key] for key in ("source_sha", "profile_sha256", "stack_arn", "expires_at")
        }
        frontend_review["manifest_sha256"] = evidence["frontend_sha256"]
        return transfer(
            frontend_review,
            folder,
            profile,
            call,
            save,
            prior=prior,
            inspect=mode == "upload-inspect",
        )
    require(mode == "create" or prior is not None, "Original change-set receipt required")
    if mode in {"inspect", "verify"}:
        candidate = template(call, review["stack_arn"], "release-" + review["operation_id"])
        original = restore_original(candidate, original_release)
    else:
        original = template(call, review["stack_arn"])
        require(
            digest(original) == review["original_template_sha256"],
            "Observed stack template changed",
        )
        original_release = original_metadata(original)
        candidate = prepare(
            original,
            observed_template_sha256=digest(original),
            source_sha=review["source_sha"],
            image_digest=evidence["image_digest"],
            frontend_sha256=evidence["frontend_sha256"],
            profile=profile,
        )["candidate_template"]
    require(
        digest(original) == review["original_template_sha256"], "Original template recovery differs"
    )
    require(
        digest(candidate) == review["candidate_template_sha256"],
        "Candidate template review differs",
    )
    expanded = {key: value for key, value in review.items() if not key.endswith("template_sha256")}
    expanded.update(
        original_template=original,
        candidate_template=candidate,
        mode="rollout",
        boundary_resource=None,
    )
    image = (
        json.loads((root / "image/fitfinity-image-candidate.json").read_text())
        if mode in {"create", "execute"}
        else {}
    )
    return advance(
        mode,
        expanded,
        evidence,
        image,
        folder,
        call,
        save,
        profile=profile,
        prior=None if mode == "create" else prior,
    )


def reviewed_source(review, current, mode):
    """Permit ancestor-source recovery while refusing writes from superseded reviews."""
    require(re.fullmatch(r"[a-f0-9]{40}", current or ""), "Exact checkout source required")
    source = review.get("source_sha", "")
    require(re.fullmatch(r"[a-f0-9]{40}", source), "Exact reviewed source required")
    if mode in RECOVERY:
        subprocess.run(["git", "merge-base", "--is-ancestor", source, current], check=True)
    else:
        require(source == current, "New writes require the current reviewed main source")
    return source


def main():
    """Fetch before credentials, then execute one explicit step with a durable journal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["fetch", "execute"])
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    profile = load(args.profile)
    current_source = os.environ["GITHUB_SHA"]
    require(
        os.environ.get("GITHUB_REPOSITORY") == profile["github_repository"]
        and os.environ.get("GITHUB_REF") == "refs/heads/main"
        and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and os.environ.get("GITHUB_WORKFLOW_REF")
        == profile["github_repository"] + "/.github/workflows/aws-rollout.yml@refs/heads/main",
        "Protected manual main rollout required",
    )
    mode = os.environ["ROLLOUT_MODE"]
    require(mode in MODES, "Unknown rollout mode")
    review_input = json.loads(os.environ["ROLLOUT_REVIEW"])
    source = reviewed_source(review_input, current_source, mode)
    source_check(Path.cwd(), current_source)
    is_resume = mode in resumption_operator.MODES
    resumption = review_input.get("resumption") if is_resume else None
    original_input = (
        {key: value for key, value in review_input.items() if key != "resumption"}
        if is_resume
        else review_input
    )
    review = metadata(original_input, source, profile, recovery=mode in RECOVERY or is_resume)
    if is_resume:
        review = {
            **review,
            "resumption": resumption_operator.validate(resumption, recovery=mode in RECOVERY),
        }
    require(
        digest(review) == os.environ["ROLLOUT_REVIEW_SHA256"], "Reviewed metadata digest differs"
    )
    root = Path(os.environ["RUNNER_TEMP"])
    artifacts = root / "rollout-artifacts"
    prior = root / "rollout-prior/rollout-receipt.json"
    verified_path = root / "rollout-verified/rollout-receipt.json"
    if args.phase == "fetch":
        if is_resume:
            fetch_prior(
                resumption["verified_run"],
                verified_path.parent,
                source,
                profile,
                recovery=mode in RECOVERY,
            )
        if mode in RECOVERY:
            fetch_prior(
                os.environ.get("ROLLOUT_PRIOR_RUN"), prior.parent, source, profile, recovery=True
            )
            retained = json.loads(prior.read_text())
            require(retained.get("review_sha256") == digest(review), "Original review differs")
            evidence = retained["evidence"]
            if mode in {"upload-inspect", "resume-health", "resume-finalize-inspect"}:
                fetch(
                    "review",
                    evidence["producer_runs"]["frontend"],
                    artifacts / "frontend",
                    source,
                    profile=profile,
                )
        else:
            runs = json.loads(os.environ["ROLLOUT_RUNS"])
            evidence = collect(
                Path.cwd(),
                artifacts,
                runs,
                source=source,
                profile=profile,
                database="fitfinity",
                schema_action="upgrade" if "upgrade" in runs else "unchanged",
            )
            if os.environ.get("ROLLOUT_PRIOR_RUN"):
                fetch_prior(os.environ["ROLLOUT_PRIOR_RUN"], prior.parent, source, profile)
        if is_resume:
            verified = json.loads(verified_path.read_text())
            require(
                verified.get("state") == "template_verified"
                and verified.get("review_sha256") == digest(original_input)
                and verified.get("evidence") == evidence
                and "resumption_plan_sha256" not in verified,
                "Verified rollout evidence differs",
            )
        (root / "rollout-evidence.json").write_text(json.dumps(evidence) + "\n")
        return
    source_check(Path.cwd(), current_source)
    evidence = json.loads((root / "rollout-evidence.json").read_text())
    journal = Journal(root / "rollout-receipt.json")
    try:
        step = resumption_operator.execute_step if is_resume else execute_step
        extra = {"verified": json.loads(verified_path.read_text())} if is_resume else {}
        step(
            mode,
            review,
            evidence,
            artifacts,
            lambda service, operation, values: aws(
                service, operation, values, profile=profile, read_only=mode in RECOVERY
            ),
            journal.save,
            profile=profile,
            prior=json.loads(prior.read_text()) if prior.exists() else None,
            **extra,
        )
    except Exception:
        journal.save(
            {**journal.value, "error": "Rollout failed; inspect retained intent before recovery"}
        )
        raise RuntimeError("Rollout failed; inspect retained intent") from None


if __name__ == "__main__":
    main()
