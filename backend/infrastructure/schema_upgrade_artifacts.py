"""Fetch source-bound upgrade evidence before the workflow receives AWS credentials."""

import json
import os
import re
import subprocess
from pathlib import Path

from backup_transition import prepare_transition
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
    if kind == "maintenance":
        require(
            receipt.get("identity", {}).get("source_sha") == producer,
            "Maintenance receipt differs from its authenticated producer",
        )
    return receipt


def maintenance_run(value, source):
    """Read a run ID or explicit original source for a backed-up release transition."""
    if re.fullmatch(r"[1-9][0-9]*", value):
        return value, source
    selection = json.loads(value)
    require(
        isinstance(selection, dict)
        and set(selection) == {"run", "source_sha"}
        and isinstance(selection["run"], str)
        and re.fullmatch(r"[1-9][0-9]*", selection["run"])
        and isinstance(selection["source_sha"], str)
        and re.fullmatch(r"[a-f0-9]{40}", selection["source_sha"])
        and selection["source_sha"] != source,
        "Exact original maintenance run and distinct source required",
    )
    return selection["run"], selection["source_sha"]


def catalog_runs(value):
    """Read an exact catalog producer or the baseline/current pair for a delayed upgrade."""
    if re.fullmatch(r"[1-9][0-9]*", value):
        return value, None
    ids = json.loads(value)
    require(
        isinstance(ids, dict)
        and set(ids) == {"current", "baseline"}
        and all(
            isinstance(item, str) and re.fullmatch(r"[1-9][0-9]*", item) for item in ids.values()
        ),
        "Exact current and baseline catalog run IDs required",
    )
    return ids["current"], ids["baseline"]


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
        current_run, baseline_run = catalog_runs(os.environ["CATALOG_RUN"])
        catalog = operational(
            "catalog",
            current_run,
            root / "upgrade-catalog",
            profile=profile,
            source=source,
        )
        maintenance_id, backup_source = maintenance_run(os.environ["MAINTENANCE_RUN"], source)
        maintenance = operational(
            "maintenance",
            maintenance_id,
            root / "upgrade-maintenance",
            profile=profile,
            source=backup_source,
        )
        arn = os.environ["SNAPSHOT_ARN"]
        verified_snapshot(maintenance, arn, identities(profile), backup_source)
        evidence = {
            "catalog": catalog,
            "snapshot_arn": arn,
            "maintenance": maintenance,
            "producer_runs": {
                "maintenance": maintenance_id,
                "catalog": current_run,
                "baseline_catalog": baseline_run or current_run,
            },
        }
        if baseline_run:
            evidence["baseline_catalog"] = operational(
                "catalog",
                baseline_run,
                root / "upgrade-baseline-catalog",
                profile=profile,
                source=backup_source,
            )
        if backup_source != source:
            require(baseline_run is not None, "Original pre-backup catalog producer required")
            evidence["backup_transition"] = prepare_transition(
                maintenance, evidence["baseline_catalog"], source
            )
        (root / "upgrade-evidence.json").write_text(json.dumps(evidence) + "\n")


if __name__ == "__main__":
    main()
