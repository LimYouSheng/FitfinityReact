"""Prepare, retrieve and execute source-bound maintenance through protected Actions."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from deployment_profile import identities, load
from operation_journal import Journal
from operator_checks import require
from portable_services import maintenance_access
from release_maintenance import execute, validate_review
from schema_probe_artifacts import fetch, run_binding

OPERATIONS = {
    ("sts", "get-caller-identity"),
    ("lambda", "get-function"),
    ("lambda", "get-function-concurrency"),
    ("lambda", "put-function-concurrency"),
    ("lambda", "tag-resource"),
    ("rds", "describe-db-instances"),
    ("rds", "create-db-snapshot"),
    ("rds", "describe-db-snapshots"),
    ("rds", "list-tags-for-resource"),
}


def digest(value):
    """Bind review approval to its canonical metadata bytes."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def aws(service, operation, values, *, profile):
    """Call only fixed maintenance operations without retries or provider-output logging."""
    require((service, operation) in OPERATIONS, "Maintenance operation is not allowed")
    result = subprocess.run(
        [
            "aws",
            service,
            operation,
            "--cli-input-json",
            json.dumps(values),
            "--region",
            identities(profile)["region"],
            "--output",
            "json",
            "--no-cli-pager",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "AWS_MAX_ATTEMPTS": "1", "AWS_EC2_METADATA_DISABLED": "true"},
    )
    require(result.returncode == 0, "Maintenance call failed; inspect retained intent")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def fetch_prior(run_id, destination, profile):
    """Retrieve original intent even after a failed or cancelled maintenance invocation."""
    require(re.fullmatch(r"[1-9][0-9]*", run_id or ""), "Exact prior run ID required")
    repository = profile["github_repository"]
    run = json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repository}/actions/runs/{run_id}"], text=True
        )
    )
    require(
        run.get("conclusion") in {"success", "failure", "cancelled"},
        "Prior maintenance must have finished",
    )
    _, attempt = run_binding({**run, "conclusion": "success"}, "aws-maintenance", profile=profile)
    subprocess.run(
        [
            "gh",
            "run",
            "download",
            run_id,
            "--repo",
            repository,
            "--name",
            f"fitfinity-maintenance-{run_id}-{attempt}",
            "--dir",
            str(destination),
        ],
        check=True,
    )


def reviewed_input(root, profile, source, recovery):
    """Validate the reviewed payload before AWS authentication and again before execution."""
    review = json.loads((root / "maintenance-review/maintenance-review/review.json").read_text())
    require(digest(review) == os.environ["REVIEW_SHA256"], "Reviewed maintenance digest differs")
    validate_review(review, profile, review["expires_at"] - 1 if recovery else time.time())
    if recovery:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", review["source_sha"], "HEAD"], check=True
        )
    else:
        require(review["source_sha"] == source, "Maintenance source differs")
    return review


def main():
    """Keep evidence retrieval before credentials and provider writes behind exact review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "fetch", "execute"])
    parser.add_argument("--profile", required=True)
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    profile = load(args.profile)
    source = os.environ["GITHUB_SHA"]
    require(
        os.environ["GITHUB_REPOSITORY"] == profile["github_repository"]
        and os.environ["GITHUB_REF"] == "refs/heads/main"
        and os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch",
        "Manual main maintenance workflow required",
    )
    if args.phase == "prepare":
        review = json.loads(args.bindings.read_text())
        validate_review(review, profile, time.time())
        require(review["source_sha"] == source, "Maintenance source differs")
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "review.json").write_text(json.dumps(review, indent=2) + "\n")
        (args.output / "review.sha256").write_text(digest(review) + "\n")
        (args.output / "access-template.json").write_text(
            json.dumps(maintenance_access(profile), indent=2) + "\n"
        )
        print("Maintenance metadata and separate IAM template prepared; no cloud action")
        return
    require(
        os.environ.get("GITHUB_WORKFLOW_REF")
        == profile["github_repository"] + "/.github/workflows/aws-maintenance.yml@refs/heads/main",
        "Dedicated protected maintenance workflow required",
    )
    root = Path(os.environ["RUNNER_TEMP"])
    mode = os.environ["MAINTENANCE_MODE"]
    require(mode in {"pause", "inspect", "snapshot", "snapshot-check"}, "Unknown maintenance mode")
    recovery = mode in {"inspect", "snapshot-check"}
    if args.phase == "fetch":
        fetch(
            "review",
            os.environ["REVIEW_RUN"],
            root / "maintenance-review",
            None if recovery else source,
            profile=profile,
        )
        reviewed_input(root, profile, source, recovery)
        if mode != "pause":
            fetch_prior(os.environ.get("PRIOR_RUN"), root / "maintenance-prior", profile)
        return
    require(
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == source,
        "Maintenance checkout differs",
    )
    review = reviewed_input(root, profile, source, recovery)
    prior = (
        None
        if mode == "pause"
        else json.loads((root / "maintenance-prior/maintenance-receipt.json").read_text())
    )
    journal = Journal(root / "maintenance-receipt.json")
    try:
        execute(
            mode,
            review,
            lambda service, operation, values: aws(service, operation, values, profile=profile),
            journal.save,
            profile=profile,
            prior=prior,
        )
    except Exception:
        journal.save(
            {
                **journal.value,
                "error": "Maintenance failed; inspect original operation before recovery",
            }
        )
        raise RuntimeError("Maintenance failed; inspect its retained receipt") from None
    print("Maintenance receipt retained; migration, rollout and traffic resumption are separate")


if __name__ == "__main__":
    main()
