"""Bind automatic release eligibility to trusted current-main verification events."""

import json
import os
import subprocess
from pathlib import Path

from deployment_profile import load
from operator_checks import require
from release_verification import api, discover


def context(event_name, event, repository, source):
    """Reject foreign, pull-request and obsolete workflow-run origins."""
    require(event_name in {"workflow_dispatch", "workflow_run"}, "Unsupported orchestration event")
    require(event.get("repository", {}).get("full_name") == repository, "Foreign event repository")
    if event_name == "workflow_run":
        run = event.get("workflow_run", {})
        require(
            run.get("head_repository", {}).get("full_name") == repository
            and run.get("head_sha") == source
            and run.get("head_branch") == "main"
            and run.get("event") in {"push", "workflow_dispatch", "schedule"}
            and run.get("path") == ".github/workflows/pages.yml"
            and run.get("status") == "completed"
            and run.get("conclusion") == "success",
            "Successful trusted current-main verification event required",
        )


def assess(event_name, event, source, profile, *, select=discover):
    """Report readiness without dispatching children or acquiring AWS credentials."""
    context(event_name, event, profile["github_repository"], source)
    try:
        verification = select(source, profile)
    except RuntimeError as error:
        return {
            "state": "waiting_for_verification",
            "deployment_decision": "HOLD",
            "reason": str(error),
        }
    return {
        "state": "source_verified",
        "deployment_decision": "HOLD",
        "verification": verification,
        "next": "Coordinate through the installed journal and protected child workflows",
    }


def wait_for_codeql(source, profile, *, read=api, watch=subprocess.run):
    """Wait only for an existing trusted pending scan; never rerun verification."""
    repository = profile["github_repository"]
    payload = read(
        f"repos/{repository}/actions/workflows/codeql.yml/runs"
        f"?head_sha={source}&branch=main&per_page=100"
    )
    rows = payload.get("workflow_runs", [])
    require(payload.get("total_count") == len(rows), "Complete CodeQL inventory required")
    candidates = [
        row
        for row in rows
        if row.get("event") in {"push", "workflow_dispatch", "schedule"}
        and row.get("head_sha") == source
        and row.get("head_branch") == "main"
        and row.get("head_repository", {}).get("full_name") == repository
        and row.get("path") == ".github/workflows/codeql.yml"
        and type(row.get("id")) is int
        and row["id"] > 0
    ]
    require(candidates, "Current-main CodeQL run not found")
    run = max(candidates, key=lambda row: row["id"])
    if run.get("status") != "completed":
        print("Waiting for existing CodeQL run " + str(run["id"]), flush=True)
        try:
            result = watch(
                [
                    "gh",
                    "run",
                    "watch",
                    str(run["id"]),
                    "--repo",
                    repository,
                    "--exit-status",
                    "--interval",
                    "10",
                ],
                capture_output=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("CodeQL still pending after bounded wait; deployment held") from None
        require(result.returncode == 0, "CodeQL did not succeed; deployment held")


def main():
    """Retain an eligibility receipt for the separate orchestration entry point."""
    repository = os.environ["GITHUB_REPOSITORY"]
    require(
        os.environ.get("GITHUB_REF") == "refs/heads/main"
        and os.environ.get("GITHUB_WORKFLOW_REF")
        == repository + "/.github/workflows/aws-release.yml@refs/heads/main",
        "Canonical main orchestration workflow required",
    )
    profile = load(os.environ["DEPLOYMENT_PROFILE"])
    require(profile["github_repository"] == repository, "Profile repository differs")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    context(os.environ["GITHUB_EVENT_NAME"], event, repository, os.environ["GITHUB_SHA"])
    try:
        wait_for_codeql(os.environ["GITHUB_SHA"], profile)
    except RuntimeError as error:
        result = {
            "state": "waiting_for_verification",
            "deployment_decision": "HOLD",
            "reason": str(error),
        }
    else:
        result = assess(os.environ["GITHUB_EVENT_NAME"], event, os.environ["GITHUB_SHA"], profile)
    (Path(os.environ["RUNNER_TEMP"]) / "orchestration-eligibility.json").write_text(
        json.dumps(result) + "\n"
    )
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write("state=" + result["state"] + "\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
        output.write("\nRelease eligibility: " + result["state"] + ". AWS execution: HOLD.\n")
        if result.get("reason"):
            output.write(result["reason"] + "\n")


if __name__ == "__main__":
    main()
