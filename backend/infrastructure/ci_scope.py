"""Reuse recent full application CI only for identical application inputs."""

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from operator_checks import require

MAX_AGE_SECONDS = 7 * 24 * 60 * 60
# These policy owners must themselves receive full application verification.
POLICY_FILES = {
    "backend/infrastructure/ci_scope.py",
    "backend/infrastructure/release_verification.py",
    "backend/infrastructure/read-schema.sql",
}
APP_JOBS = {
    "unit",
    "browser-build",
    "browser-profile (desktop-chromium)",
    "browser-profile (phone)",
    "browser-profile (tablet)",
    "backend-group (identity-clients)",
    "backend-group (scheduling-packages)",
    "backend-group (records-platform)",
    "api-browser-shard (1)",
    "api-browser-shard (2)",
}


def application_input(path):
    """Default unknown files to full CI; exclude only documented control-plane inputs."""
    if path in POLICY_FILES:
        return True
    return not (
        path.startswith("backend/infrastructure/")
        or path.startswith("docs/")
        or path
        in {
            "backend/scripts/verify-infrastructure.py",
            "scripts/verify-infrastructure.mjs",
            ".github/workflows/infrastructure.yml",
        }
        or (path.startswith(".github/workflows/aws-") and path.endswith(".yml"))
        or path in {"AGENTS.md", "NORTH_STAR.md", "PROGRESS.md"}
    )


def tree_fingerprint(source):
    """Hash tracked paths, modes and blobs, including deletions and symlink changes."""
    require(re.fullmatch(r"[a-f0-9]{40}", source or ""), "Exact Git source required")
    raw = subprocess.check_output(["git", "ls-tree", "-rz", "--full-tree", source])
    rows = []
    for row in raw.split(b"\0"):
        if row:
            _, path = row.split(b"\t", 1)
            if application_input(path.decode()):
                rows.append(row)
    require(rows, "Application tree is empty")
    return hashlib.sha256(b"\0".join(sorted(rows))).hexdigest()


def same_application(baseline, source):
    """Require ancestry and identical application/test/build/dependency inputs."""
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, source],
        capture_output=True,
        check=False,
    )
    return ancestor.returncode == 0 and tree_fingerprint(baseline) == tree_fingerprint(source)


def fresh(run, now):
    """Do not let a rerun refresh the original evidence age."""
    try:
        created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        return created.tzinfo is not None and 0 <= now - created.timestamp() <= MAX_AGE_SECONDS
    except (KeyError, ValueError, TypeError):
        return False


def baseline(repository, source, read, *, now=None, equivalent=same_application):
    """Select a full successful main run; never chain reuse through scoped runs."""
    from release_verification import VERIFY_JOBS, check_jobs, check_run

    now = time.time() if now is None else now
    root = f"repos/{repository}"
    payload = read(f"{root}/actions/workflows/pages.yml/runs?branch=main&per_page=30")
    for run in payload.get("workflow_runs", []):
        head = run.get("head_sha")
        if not fresh(run, now) or not re.fullmatch(r"[a-f0-9]{40}", head or ""):
            continue
        if run.get("status") != "completed":
            continue
        if run.get("conclusion") != "success":
            if equivalent(head, source):
                return None
            continue
        try:
            check_run(run, "pages", head, repository)
            jobs = read(
                f"{root}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100"
            )
            check_jobs(jobs, VERIFY_JOBS, run, head)
            if equivalent(head, source):
                return {
                    "run_id": run["id"],
                    "source_sha": head,
                    "created_at": run["created_at"],
                    "max_age_seconds": MAX_AGE_SECONDS,
                }
        except RuntimeError:
            continue
    return None


def aggregate(needs):
    """Accept deliberate application skips only after successful scope and fresh checks."""
    scope = needs.get("scope", {})
    require(scope.get("result") == "success", "Scope validation did not pass")
    require(scope.get("outputs", {}).get("run_application") == "false", "Reuse not established")
    require(bool(scope.get("outputs", {}).get("baseline_run")), "Baseline run missing")
    for name, job in needs.items():
        if name != "scope":
            expected = (
                "skipped"
                if name
                in {
                    "unit",
                    "browser-build",
                    "browser-profile",
                    "backend-group",
                    "api-browser-shard",
                }
                else "success"
            )
            require(job.get("result") == expected, "Unexpected job state during CI reuse")


def main():
    """Emit auditable scope outputs; missing evidence falls back to full application CI."""
    from release_verification import api

    if os.environ.get("CI_REUSE_AGGREGATE"):
        aggregate(json.loads(os.environ["CI_NEEDS"]))
        return
    result = None
    try:
        result = baseline(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"], api)
    except (RuntimeError, subprocess.CalledProcessError):
        pass
    outputs = {
        "run_application": "false" if result else "true",
        "baseline_run": str(result["run_id"]) if result else "",
    }
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        for key, value in outputs.items():
            stream.write(f"{key}={value}\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
        stream.write(
            "Application CI: "
            + (
                f"reuse full run {result['run_id']} (unchanged inputs, seven-day limit)."
                if result
                else "full verification required."
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
