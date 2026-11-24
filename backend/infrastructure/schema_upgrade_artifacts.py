"""Fetch source-bound upgrade evidence before the workflow receives AWS credentials."""

import json
import os
import re
import subprocess
from pathlib import Path

from deployment_profile import identities, load
from operator_checks import require
from release_evidence import observed_catalog
from release_maintenance import verified_snapshot
from schema_probe_artifacts import fetch, run_binding


def operational(kind, run_id, destination, *, profile, source=None):
    """Retain failed upgrade intents for inspection without accepting failed catalog producers."""
    producers = {
        "prior": ("aws-schema-upgrade", "fitfinity-schema-upgrade", "schema-upgrade-receipt.json"),
        "catalog": ("aws-schema-probe", "fitfinity-schema-probe", "schema-probe-receipt.json"),
        "maintenance": ("aws-maintenance", "fitfinity-maintenance", "maintenance-receipt.json"),
    }
    require(kind in producers, "Unknown operational artifact")
    require(re.fullmatch(r"[1-9][0-9]*", run_id or ""), "Exact operational run ID required")
    repository = profile["github_repository"]
    run = json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repository}/actions/runs/{run_id}"], text=True
        )
    )
    workflow, prefix, filename = producers[kind]
    checked = dict(run)
    if kind == "prior":
        require(
            run.get("conclusion") in {"success", "failure", "cancelled"},
            "Prior operation must have finished; inspect running work",
        )
        checked["conclusion"] = "success"
    producer, attempt = run_binding(checked, workflow, source, profile=profile)
    name = f"{prefix}-{run_id}-{attempt}"
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
    receipt = json.loads((destination / filename).read_text())
    if kind == "catalog":
        return observed_catalog(
            receipt,
            source=producer,
            profile_sha256=identities(profile)["profile_sha256"],
            sql_path=Path(__file__).with_name("read-schema.sql"),
        )
    return receipt


def main():
    """Prepare only metadata inputs from named protected workflow artifacts."""
    profile = load(os.environ["DEPLOYMENT_PROFILE"])
    require(os.environ["GITHUB_REPOSITORY"] == profile["github_repository"], "Wrong repository")
    root = Path(os.environ["RUNNER_TEMP"])
    mode = os.environ["UPGRADE_MODE"]
    require(mode in {"create", "inspect", "invoke", "cleanup", "cleanup-check"}, "Unknown mode")
    recovery = mode in {"inspect", "cleanup", "cleanup-check"}
    source = fetch(
        "review",
        os.environ["REVIEW_RUN"],
        root / "upgrade-review",
        None if recovery else os.environ["GITHUB_SHA"],
        profile=profile,
    )
    if not recovery:
        fetch("image", os.environ["IMAGE_RUN"], root / "upgrade-image", source, profile=profile)
    if mode != "create" and os.getenv("PRIOR_RUN"):
        operational("prior", os.environ["PRIOR_RUN"], root / "upgrade-prior", profile=profile)
    if mode == "invoke":
        catalog = operational(
            "catalog",
            os.environ["CATALOG_RUN"],
            root / "upgrade-catalog",
            profile=profile,
            source=source,
        )
        maintenance = operational(
            "maintenance",
            os.environ["MAINTENANCE_RUN"],
            root / "upgrade-maintenance",
            profile=profile,
            source=source,
        )
        arn = os.environ["SNAPSHOT_ARN"]
        verified_snapshot(maintenance, arn, identities(profile), source)
        evidence = {
            "catalog": catalog,
            "snapshot_arn": arn,
            "maintenance": maintenance,
        }
        (root / "upgrade-evidence.json").write_text(json.dumps(evidence) + "\n")


if __name__ == "__main__":
    main()
