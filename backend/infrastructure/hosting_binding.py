"""Authenticated hosting inputs; image source and operator source stay distinct."""

import io
import json
import re
import zipfile
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
        and state.get("image_digest") == runtime.DIGEST,
        "Recovery identity differs",
    )
    return state, origin
