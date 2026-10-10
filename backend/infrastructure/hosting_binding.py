"""Authenticated hosting inputs; image source and operator source stay distinct."""

import io
import json
import re
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath

import private_runtime_binding as runtime
import private_runtime_preflight as preflight
from image_acceptance import GITHUB_REPO, ExistingImage
from operator_checks import require
from release_image import sha

WORKFLOW = ".github/workflows/aws-test-hosting.yml"
RUNTIME_RUN = 37721383277
RUNTIME_ARTIFACT = 11528371887
RUNTIME_SHA = "5d11866916b82ccfec8e33700465427606394d59e8cfa1d12aac2fc1a58f8296"
RUNTIME_SOURCE = "087f744884f7ed0d3374aa8e4e2ba1e9ddbf3932"

# One reviewed recovery edge, not a general cross-source resume permission.
TRANSITION_RUN = 37889740465
TRANSITION_OPERATION = "769df115e6ea4f478426f75c8a283a32"
TRANSITION_SOURCE = "b63fa5ef16904359a429e9048345b8ad13bea2be"
TRANSITION_ARTIFACT = 11600513161
TRANSITION_ZIP_SHA = "a384b8b2d8989ac269a4023786ad9c307d78a94b7ee890cfb5dad8477431ec90"
TRANSITION_STATE_SHA = "6d1ccd4dad76e9683bd5c4d93cfa12e82c360c7ec3d6684a815c796b7dc46014"
FAILED_REVIEW_PR = 20
FAILED_RUN = 37946314992
FAILED_SOURCE = "a57a54609f4a4b8ca875534636f78e30aa36ac05"
FAILED_ARTIFACT = 11626367274
FAILED_ZIP_SHA = "cf3accdda2f21d8dcf6314a409ad32b993fc99d5afea215755ba9afdd06bacc5"
FAILED_STATE_SHA = "a86308eb6c55ed4571b5cd125d105308148e5dbe467404209b9141043dd03d1a"


class EvidenceAWS(preflight.EvidenceAWS):
    def environment(self):
        runtime.actions_environment()
        value = self("sts", "get-caller-identity")
        require(
            value.get("Account") == "418638389566"
            and re.fullmatch(
                (
                    "arn:aws:sts::418638389566:assumed-role/fitfinity-test-github"
                    "-hosting/[A-Za-z0-9+=,.@_-]+"
                ),
                value.get("Arn", ""),
            ),
            "Separate hosting OIDC identity required",
        )
        return value["Arn"]


def unpack(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(
            len(names) == len(set(names)) and len(names) <= 1000,
            "Duplicate/oversized artifact inventory",
        )
        require(
            sum(x.file_size for x in archive.infolist()) <= 100 * 1024 * 1024,
            "Artifact exceeds size limit",
        )
        files = {}
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            require(
                not path.is_absolute()
                and ".." not in path.parts
                and "\\" not in info.filename
                and (info.external_attr >> 16) & 0o170000 != 0o120000,
                "Unsafe artifact path",
            )
            if not info.is_dir():
                files[info.filename] = archive.read(info)
        return files


def artifact(
    run_id, name, source, *, success=True, workflow=WORKFLOW, artifact_id=None, checksum=None
):
    image = ExistingImage({})
    prefix = f"repos/{GITHUB_REPO}"
    run = image.github(f"{prefix}/actions/runs/{run_id}")
    require(
        run.get("id") == run_id
        and run.get("repository", {}).get("full_name") == GITHUB_REPO
        and run.get("head_repository", {}).get("full_name") == GITHUB_REPO
        and run.get("head_sha") == source
        and run.get("head_branch") == "main"
        and run.get("event") == "workflow_dispatch"
        and run.get("path") == workflow
        and run.get("status") == "completed"
        and (not success or run.get("conclusion") == "success"),
        "Untrusted hosting artifact run/source",
    )
    listing = image.github(f"{prefix}/actions/runs/{run_id}/artifacts?per_page=100")
    rows = listing.get("artifacts", [])
    require(listing.get("total_count") == len(rows), "Incomplete artifact inventory")
    expected = name.format(run=run_id, attempt=run["run_attempt"])
    rows = [x for x in rows if x.get("name") == expected]
    require(len(rows) == 1 and rows[0].get("expired") is False, "Missing/ambiguous artifact")
    row = rows[0]
    require(
        row.get("workflow_run", {}).get("id") == run_id
        and row["workflow_run"].get("head_sha") == source
        and (artifact_id is None or row["id"] == artifact_id),
        "Artifact run binding differs",
    )
    raw = image.github(f"{prefix}/actions/artifacts/{row['id']}/zip", binary=True)
    require(
        row.get("digest") == "sha256:" + sha(raw) and (checksum is None or sha(raw) == checksum),
        "Artifact ZIP checksum differs",
    )
    return unpack(raw), {
        "run_id": run_id,
        "attempt": run["run_attempt"],
        "artifact_id": row["id"],
        "sha256": sha(raw),
    }


def runtime_proof(report):
    files, origin = artifact(
        RUNTIME_RUN,
        "fitfinity-private-runtime-aa2b2e439c3943b3b425de90302833ab-{run}-{attempt}",
        RUNTIME_SOURCE,
        workflow=".github/workflows/aws-private-runtime.yml",
        artifact_id=RUNTIME_ARTIFACT,
        checksum=RUNTIME_SHA,
    )
    receipt = json.loads(files["private-runtime/receipt.json"])
    state = json.loads(files["private-runtime/state.json"])
    require(
        receipt.get("checkpoint") == state
        and receipt.get("accepted") is True
        and receipt.get("aws_runtime_verified") is True
        and receipt.get("temporary_cleanup_complete") is True
        and receipt.get("application_deployed") is False
        and receipt.get("live_authentication_accepted") is False
        and state.get("image_digest") == runtime.DIGEST
        and state.get("operator_commit") == RUNTIME_SOURCE,
        "Current-image runtime acceptance differs",
    )
    report["runtime_proof"] = origin


def compatibility(repo):
    contract = json.loads((Path(__file__).parent / "private-runtime-contract.json").read_text())
    require(contract["revision"] == runtime.SOURCE, "Image source contract differs")
    for name, expected in contract["files"].items():
        path = repo / "backend" / name
        require(
            path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == expected,
            "Backend/image compatibility differs: " + name,
        )
    return {
        "image_digest": runtime.DIGEST,
        "image_source": runtime.SOURCE,
        "contract_sha256": sha(
            (Path(__file__).parent / "private-runtime-contract.json").read_bytes()
        ),
    }


def release(run_id, source, directory):
    import hosting_frontend as frontend

    files, origin = artifact(run_id, "fitfinity-hosting-release-{run}-{attempt}", source)
    require("release.json" in files, "Release manifest missing")
    manifest = json.loads(files.pop("release.json"))
    require(
        manifest.get("operator_source") == source
        and manifest.get("frontend_source", {}).get("revision") == source
        and manifest.get("compatibility") == compatibility(Path(__file__).resolve().parents[2])
        and manifest.get("frontend_build", {}).get("mode") == "api"
        and manifest["frontend_build"].get("base_path") == "/"
        and manifest["frontend_build"].get("api_base_url") == ""
        and manifest["frontend_build"].get("pwa_verified") is True,
        "Release source/configuration/image differs",
    )
    inventory = manifest["manifest"]
    require(
        set(files) == {"frontend/" + n for n in inventory}
        and manifest["frontend_build"]["manifest_sha256"] == frontend.manifest_hash(inventory),
        "Release inventory differs",
    )
    directory.mkdir(mode=0o700)
    for name, raw in files.items():
        relative = name.removeprefix("frontend/")
        require(sha(raw) == inventory[relative]["sha256"], "Release file checksum differs")
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    require(frontend.inventory(directory) == inventory, "Release metadata differs")
    return {
        "directory": str(directory),
        "manifest": inventory,
        "prefix": "releases/" + source + "/" + frontend.manifest_hash(inventory),
        "artifact": origin,
    }


def restore(run_id, operation, source):
    files, origin = artifact(
        run_id, "fitfinity-hosting-" + operation + "-{run}-{attempt}", source, success=False
    )
    state = json.loads(files["hosting/state.json"])
    require(
        state.get("operator_commit") == source
        and state.get("operation_id") == operation
        and state.get("operator_revision") == "2026-10-08-test-hosting-1"
        and state.get("image_digest") == runtime.DIGEST
        and (
            not state.get("failed_edge_recovery")
            or state["failed_edge_recovery"].get("reviewed") is True
        )
        and (
            not state.get("source_transition")
            or state["source_transition"].get("reconciled") is True
        ),
        "Recovery identity differs",
    )
    return state, origin


def restore_transition(run_id, operation, source):
    """Read-only rebind of the pinned, unexecuted operation after owner review."""
    require(
        run_id == TRANSITION_RUN and operation == TRANSITION_OPERATION,
        "Unreviewed source transition operation/run",
    )
    pr = ExistingImage({}).github(f"repos/{GITHUB_REPO}/pulls/19")
    require(
        pr.get("merged") is True
        and pr.get("merged_by", {}).get("login") == "LimYouSheng"
        and pr.get("base", {}).get("ref") == "main"
        and pr.get("base", {}).get("repo", {}).get("full_name") == GITHUB_REPO
        and pr.get("head", {}).get("repo", {}).get("full_name") == GITHUB_REPO
        and pr.get("merge_commit_sha") == source
        and re.fullmatch(r"[0-9a-f]{40}", source)
        and source != TRANSITION_SOURCE,
        "Source transition requires exact owner-merged PR 19 main",
    )
    files, origin = artifact(
        run_id,
        "fitfinity-hosting-" + operation + "-{run}-{attempt}",
        TRANSITION_SOURCE,
        success=False,
        artifact_id=TRANSITION_ARTIFACT,
        checksum=TRANSITION_ZIP_SHA,
    )
    raw = files["hosting/state.json"]
    require(sha(raw) == TRANSITION_STATE_SHA, "Source transition checkpoint differs")
    state = json.loads(raw)
    receipt = json.loads(files["hosting/receipt.json"])
    edge = state.get("stacks", {}).get("edge", {})
    require(
        receipt.get("checkpoint") == state
        and receipt.get("status") == "stopped"
        and receipt.get("error") == "Stack ownership tags differ"
        and state.get("operator_commit") == TRANSITION_SOURCE
        and state.get("operation_id") == operation
        and state.get("image_digest") == runtime.DIGEST
        and set(state.get("stacks", {})) == {"edge"}
        and edge.get("create_response_received") is True
        and edge.get("create_intent")
        and not edge.get("execute_intent")
        and not edge.get("complete")
        and not state.get("frontend_uploaded")
        and not state.get("complete")
        and not state.get("source_transition"),
        "Source transition requires the original unexecuted checkpoint",
    )
    original = deepcopy(state)
    state.update(
        operator_commit=source,
        execution_authorized=False,
        source_transition={
            "review_pr": 19,
            "from_source": TRANSITION_SOURCE,
            "to_source": source,
            "artifact": origin,
            "state_sha256": sha(raw),
            "original_checkpoint": original,
        },
    )
    return state, origin


def restore_failed_edge(run_id, operation, source):
    """One owner-reviewed recovery of the acknowledged failed edge execution."""
    require(
        run_id == FAILED_RUN and operation == TRANSITION_OPERATION,
        "Unreviewed failed-edge operation/run",
    )
    pr = ExistingImage({}).github(f"repos/{GITHUB_REPO}/pulls/{FAILED_REVIEW_PR}")
    require(
        pr.get("merged") is True
        and pr.get("merged_by", {}).get("login") == "LimYouSheng"
        and pr.get("base", {}).get("ref") == "main"
        and pr.get("base", {}).get("repo", {}).get("full_name") == GITHUB_REPO
        and pr.get("head", {}).get("repo", {}).get("full_name") == GITHUB_REPO
        and pr.get("merge_commit_sha") == source
        and re.fullmatch(r"[0-9a-f]{40}", source)
        and source != FAILED_SOURCE,
        "Failed-edge recovery requires exact owner-merged repair main",
    )
    files, origin = artifact(
        run_id,
        "fitfinity-hosting-" + operation + "-{run}-{attempt}",
        FAILED_SOURCE,
        success=False,
        artifact_id=FAILED_ARTIFACT,
        checksum=FAILED_ZIP_SHA,
    )
    raw = files["hosting/state.json"]
    require(sha(raw) == FAILED_STATE_SHA, "Failed-edge checkpoint bytes differ")
    state = json.loads(raw)
    receipt = json.loads(files["hosting/receipt.json"])
    edge = state.get("stacks", {}).get("edge", {})
    require(
        receipt.get("checkpoint") == state
        and receipt.get("status") == "stopped"
        and receipt.get("cloudformation_failure", {}).get("status") == "ROLLBACK_IN_PROGRESS"
        and state.get("operator_commit") == FAILED_SOURCE
        and state.get("operation_id") == operation
        and state.get("image_digest") == runtime.DIGEST
        and set(state.get("stacks", {})) == {"edge"}
        and edge.get("execute_response_received") is True
        and edge.get("execute_intent")
        and state.get("source_transition", {}).get("reconciled") is True
        and not state.get("complete")
        and not state.get("frontend_uploaded")
        and not state.get("failed_edge_recovery"),
        "Failed-edge recovery requires exact acknowledged failed execution",
    )
    original = deepcopy(state)
    state.update(
        operator_commit=source,
        execution_authorized=False,
        failed_edge_recovery={
            "review_pr": FAILED_REVIEW_PR,
            "from_source": FAILED_SOURCE,
            "to_source": source,
            "artifact": origin,
            "original_checkpoint": original,
        },
    )
    return state, origin
