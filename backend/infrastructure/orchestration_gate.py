"""Bind automatic release eligibility to trusted current-main verification events."""

import json
import os
from pathlib import Path

from deployment_profile import load
from operator_checks import require
from release_verification import discover


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
            and run.get("path") in {".github/workflows/pages.yml", ".github/workflows/codeql.yml"}
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
    result = assess(os.environ["GITHUB_EVENT_NAME"], event, os.environ["GITHUB_SHA"], profile)
    (Path(os.environ["RUNNER_TEMP"]) / "orchestration-eligibility.json").write_text(
        json.dumps(result) + "\n"
    )
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write("state=" + result["state"] + "\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
        output.write("\nRelease eligibility: " + result["state"] + ". AWS execution: HOLD.\n")


if __name__ == "__main__":
    main()
