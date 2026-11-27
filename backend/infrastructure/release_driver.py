"""Run the opt-in release draft against a durable journal and existing protected children."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from deployment_journal import bucket_name, release_store
from deployment_profile import fingerprint, identities, load
from operator_checks import require
from operator_errors import safe_reason
from release_coordinator import load_or_start, tick
from release_dispatch import WORKFLOWS, request
from release_record import ReleaseRecord
from release_stage_inputs import plan, worker_readiness
from release_stage_results import authenticate
from release_verification import api, discover


def validate_child_inputs(workflow, inputs):
    """Validate against the checked-out workflow before persisting dispatch intent."""
    result = subprocess.run(
        ["node", str(Path(__file__).with_name("workflow_inputs.mjs")), workflow],
        input=json.dumps(inputs),
        text=True,
        capture_output=True,
        timeout=30,
    )
    reason = result.stderr.strip() if isinstance(result.stderr, str) else ""
    detail = (
        reason
        if re.fullmatch(r"(?:Required input missing|Invalid choice): [a-z][a-z0-9_]*", reason)
        else "Child workflow input contract rejected"
    )
    require(result.returncode == 0, detail + "; validation failed before dispatch intent")


def drive(record, profile, configuration, *, now=time.time, pause=time.sleep, budget=2700):
    """Observe waiting children; never repeat a persisted dispatch or uncertain write."""
    source = record.identity["source_sha"]

    def verify():
        return discover(source, profile)

    load_or_start(record, profile, verify, now())

    def prepare(stage, value):
        pending = worker_readiness(stage, value, profile)
        if pending:
            return {"wait": pending}
        result = plan(stage, value, configuration, profile, now=now())
        validate_child_inputs(WORKFLOWS[stage], result["inputs"])
        return result

    deadline = now() + budget
    while now() < deadline:
        result = tick(
            record,
            verify=verify,
            plan=prepare,
            read_runs=lambda workflow, revision: api(
                f"repos/{profile['github_repository']}/actions/workflows/{workflow}/runs"
                f"?head_sha={revision}&branch=main&per_page=100"
            ),
            authenticate=lambda stage, run, value: authenticate(
                stage, run, value, profile, now=now()
            ),
            read=api,
            send=request,
            now=now(),
        )
        if result.get("reason") == "dispatch_not_observed":
            result = {**result, "state": "wait"}
        if result["state"] in {"release_complete", "hold"}:
            return result
        if result["state"] in {"dispatch_requested", "wait"}:
            pause(min(20, max(0, deadline - now())))
    return {
        "state": "waiting",
        "reason": "observation_window_ended",
        "next": "Continue this source with Coordinate Release; pending writes are not replayed",
    }


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    require(
        os.environ.get("GITHUB_REF") == "refs/heads/main"
        and os.environ.get("GITHUB_WORKFLOW_REF")
        == repository + "/.github/workflows/aws-release.yml@refs/heads/main",
        "Canonical main coordinator required",
    )
    profile = load(os.environ["DEPLOYMENT_PROFILE"])
    require(profile["github_repository"] == repository, "Coordinator repository differs")
    require(
        os.environ.get("FITFINITY_JOURNAL_BUCKET") == bucket_name(profile),
        "Install the reviewed journal and configure FITFINITY_JOURNAL_BUCKET first",
    )
    configuration = json.loads(os.environ["FITFINITY_RELEASE_CONFIG_JSON"])
    require(
        configuration.get("profile_sha256") == fingerprint(profile)
        and isinstance(configuration.get("probe"), dict)
        and isinstance(configuration.get("target"), str),
        "Release configuration needs target, profile_sha256 and reviewed probe bindings",
    )
    require(
        load("env:" + configuration["target"]) == profile,
        "Configured child target must resolve to the same reviewed deployment profile",
    )
    if sys.argv[1:] == ["--preflight"]:
        for flag in (
            "AWS_IMAGE_RELEASE_ENABLED",
            "AWS_SCHEMA_PROBE_ENABLED",
            "AWS_MAINTENANCE_ENABLED",
            "AWS_SCHEMA_UPGRADE_ENABLED",
            "AWS_ROLLOUT_ENABLED",
        ):
            require(
                os.environ.get(flag) == "true",
                f"Enable the reviewed child workflow flag {flag} first",
            )
        target = identities(profile)
        expected_role = (
            f"arn:aws:iam::{target['account']}:role/{target['resource_prefix']}-github-journal"
        )
        require(
            os.environ.get("JOURNAL_ROLE") == expected_role,
            "AWS_JOURNAL_ROLE_ARN must identify this target's journal coordinator role",
        )
        print("Coordinator configuration checked; no AWS writes performed")
        return
    require(not sys.argv[1:], "Unknown coordinator arguments")
    source = os.environ["GITHUB_SHA"]
    read, write = release_store(profile)
    record = ReleaseRecord(profile, source, read, write)
    try:
        result = drive(record, profile, configuration)
    except Exception as error:
        result = {
            "state": "held",
            "reason": safe_reason(error),
            "next": "Inspect original journal and child receipt; do not rerun child mutations",
        }
    destination = Path(os.environ["RUNNER_TEMP"]) / "release-coordination.json"
    destination.write_text(json.dumps(result) + "\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
        stream.write("\nRelease coordination status: " + result["state"] + "\n\n")
        stream.write("```json\n" + json.dumps(result, indent=2) + "\n```\n")
        stream.write(
            "Existing child environment approvals remain required. "
            "A waiting or held release is not deployed acceptance.\n"
        )
    require(
        result["state"] not in {"held", "hold"},
        "Release held; inspect the coordination summary and original receipt",
    )


if __name__ == "__main__":
    main()
