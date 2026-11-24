"""Authenticate completed current-main verification before acquiring release credentials."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from deployment_profile import load
from operator_checks import require

VERIFY_JOBS = {
    "verify / quality",
    "verify / unit",
    "verify / browser-build",
    "verify / backend-checks",
    "verify / infrastructure",
    "verify / frontend",
    "verify / backend",
    "verify / api-browser",
    *(f"verify / browser-profile ({name})" for name in ("desktop-chromium", "phone", "tablet")),
    *(
        f"verify / backend-group ({name})"
        for name in ("identity-clients", "scheduling-packages", "records-platform")
    ),
    "verify / api-browser-shard (1)",
    "verify / api-browser-shard (2)",
}
CODEQL_JOBS = {"CodeQL (javascript-typescript)", "CodeQL (python)"}


def api(path):
    """Read GitHub metadata without downloading or executing artifact contents."""
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", path], capture_output=True, text=True, timeout=60
    )
    require(result.returncode == 0, "Verification metadata unavailable")
    return json.loads(result.stdout)


def check_run(run, workflow, source, repository):
    """Require completed canonical main verification for the exact repository and source."""
    require(
        run.get("path") == f".github/workflows/{workflow}.yml"
        and run.get("event")
        in (
            {"push", "workflow_dispatch", "schedule"}
            if workflow == "codeql"
            else {"push", "workflow_dispatch"}
        )
        and run.get("head_branch") == "main"
        and run.get("head_repository", {}).get("full_name") == repository
        and run.get("repository", {}).get("full_name") == repository
        and run.get("head_sha") == source
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and type(run.get("id")) is int
        and run["id"] > 0
        and type(run.get("run_attempt")) is int
        and run["run_attempt"] > 0,
        "Successful exact-source canonical main verification required",
    )


def check_jobs(payload, expected, run, source):
    """Reject incomplete, duplicate, skipped or foreign-attempt verification jobs."""
    rows = payload.get("jobs", [])
    names = [row.get("name") for row in rows]
    require(
        payload.get("total_count") == len(rows)
        and all(isinstance(name, str) and name for name in names)
        and len(set(names)) == len(names),
        "Complete unique verification job inventory required",
    )
    required = [row for row in rows if row.get("name") in expected]
    require(
        set(names) >= expected
        and all(
            row.get("run_id") == run["id"]
            and row.get("run_attempt") == run["run_attempt"]
            and row.get("head_sha") == source
            and row.get("status") == "completed"
            and row.get("conclusion") == "success"
            for row in required
        ),
        "Every required verification job must pass on the exact attempt",
    )
    require(
        not ({name for name in names if name.startswith("verify /")} - expected)
        if expected == VERIFY_JOBS
        else set(names) == expected,
        "Unexpected verification job requires gate review",
    )


def verify(run_id, source, profile, read=api):
    """Reuse full CI evidence without extending operational review or catalog expiry."""
    require(
        isinstance(run_id, str) and re.fullmatch(r"[1-9][0-9]*", run_id),
        "Exact verification run ID required",
    )
    require(re.fullmatch(r"[a-f0-9]{40}", source or ""), "Exact source required")
    repository = profile["github_repository"]
    root = f"repos/{repository}"
    run = read(f"{root}/actions/runs/{run_id}")
    check_run(run, "pages", source, repository)
    require(str(run["id"]) == run_id, "Verification run identity differs")
    check_jobs(
        read(f"{root}/actions/runs/{run_id}/attempts/{run['run_attempt']}/jobs?per_page=100"),
        VERIFY_JOBS,
        run,
        source,
    )
    scans = read(
        f"{root}/actions/workflows/codeql.yml/runs?head_sha={source}&branch=main&per_page=100"
    )
    rows = scans.get("workflow_runs", [])
    require(
        scans.get("total_count") == len(rows) and rows, "Complete CodeQL run inventory required"
    )
    candidates = [
        row
        for row in rows
        if row.get("event") in {"push", "workflow_dispatch", "schedule"}
        and type(row.get("id")) is int
    ]
    require(candidates, "Canonical main CodeQL run required")
    scan = max(candidates, key=lambda row: row["id"])
    check_run(scan, "codeql", source, repository)
    check_jobs(
        read(f"{root}/actions/runs/{scan['id']}/attempts/{scan['run_attempt']}/jobs?per_page=100"),
        CODEQL_JOBS,
        scan,
        source,
    )
    results = read(
        f"{root}/commits/{source}/check-runs?check_name=CodeQL&filter=latest&per_page=100"
    )
    # GitHub emits the result check for PRs; main still requires both analysis jobs.
    checks = results.get("check_runs", [])
    require(
        results.get("total_count") == len(checks)
        and all(
            row.get("name") == "CodeQL"
            and row.get("head_sha") == source
            and row.get("status") == "completed"
            and row.get("conclusion") == "success"
            and row.get("app", {}).get("slug") == "github-advanced-security"
            and row.get("app", {}).get("id") == 57789
            for row in checks
        ),
        "Successful GitHub CodeQL result required",
    )
    return {
        "source_sha": source,
        "repository": repository,
        "verification_run": run["id"],
        "verification_attempt": run["run_attempt"],
        "codeql_run": scan["id"],
        "codeql_attempt": scan["run_attempt"],
        "codeql_result": "success" if checks else "not_emitted_for_main",
        "state": "source_verified",
    }


def main():
    """Validate protected workflow context and retain a metadata-only verification receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    profile = load(args.profile)
    require(
        os.environ.get("GITHUB_REPOSITORY") == profile["github_repository"]
        and os.environ.get("GITHUB_REF") == "refs/heads/main"
        and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and os.environ.get("GITHUB_WORKFLOW_REF")
        == profile["github_repository"] + "/.github/workflows/aws-rollout.yml@refs/heads/main",
        "Protected manual main rollout required",
    )
    receipt = verify(os.environ["VERIFICATION_RUN"], os.environ["GITHUB_SHA"], profile)
    (Path(os.environ["RUNNER_TEMP"]) / "rollout-verification.json").write_text(
        json.dumps(receipt) + "\n"
    )
    print("Exact-source full verification and CodeQL passed; operational reviews still apply.")


if __name__ == "__main__":
    main()
