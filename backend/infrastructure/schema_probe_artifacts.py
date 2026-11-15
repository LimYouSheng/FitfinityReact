"""Fetch only successful, same-repository manual release evidence for the probe."""

import json
import os
import re
import subprocess
from pathlib import Path

from deployment_profile import DEVELOPER, identities, load
from operator_checks import require

REPOSITORY = DEVELOPER["github_repository"]


def run_binding(run, workflow, source=None, *, profile=DEVELOPER):
    """Reject foreign, failed, non-main or non-manual artifact producers."""
    require(
        run.get("path") == f".github/workflows/{workflow}.yml"
        and run.get("event") == "workflow_dispatch"
        and run.get("head_branch") == "main"
        and run.get("head_repository", {}).get("full_name")
        == identities(profile)["github_repository"]
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", ""))
        and type(run.get("run_attempt")) is int
        and run["run_attempt"] > 0,
        "Artifact producer identity or result differs",
    )
    require(source is None or run["head_sha"] == source, "Artifact source differs")
    return run["head_sha"], run["run_attempt"]


def fetch(kind, run_id, destination, source=None, *, profile=DEVELOPER):
    """Download one named artifact without executing its contents."""
    repository = identities(profile)["github_repository"]
    require(kind in {"review", "image"}, "Unknown artifact kind")
    require(re.fullmatch(r"[1-9][0-9]*", run_id or ""), "Exact artifact run ID required")
    workflow = "aws-release-prepare" if kind == "review" else "aws-image"
    run = json.loads(
        subprocess.check_output(
            [
                "gh",
                "api",
                f"repos/{repository}/actions/runs/{run_id}",
            ],
            text=True,
        )
    )
    revision, attempt = run_binding(run, workflow, source, profile=profile)
    name = (
        f"fitfinity-release-prepare-{revision}-{run_id}-{attempt}"
        if kind == "review"
        else f"fitfinity-image-candidate-{run_id}-{attempt}"
    )
    subprocess.run(
        [
            "gh",
            "run",
            "download",
            run_id,
            "--repo",
            repository,
            "--name",
            name,
            "--dir",
            str(destination),
        ],
        check=True,
    )
    return revision


if __name__ == "__main__":
    profile = load(os.environ["DEPLOYMENT_PROFILE"])
    require(os.environ["GITHUB_REPOSITORY"] == profile["github_repository"], "Wrong repository")
    root = Path(os.environ["RUNNER_TEMP"])
    mode = os.environ["PROBE_MODE"]
    source = fetch(
        "review",
        os.environ["REVIEW_RUN"],
        root / "probe-review",
        None if mode.startswith("cleanup") else os.environ["GITHUB_SHA"],
        profile=profile,
    )
    if not mode.startswith("cleanup"):
        fetch("image", os.environ["IMAGE_RUN"], root / "probe-image", source, profile=profile)
