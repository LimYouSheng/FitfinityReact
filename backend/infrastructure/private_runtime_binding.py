"""Exact accepted-image and merged-review binding for the private runtime owner."""

import io
import json
import os
import re
import zipfile
from pathlib import Path

from image_acceptance import GITHUB_REPO, ExistingImage, acceptance
from operator_checks import require
from release_image import URI as URI
from release_image import sha, timestamp

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a"
SOURCE = "33d124fcd59ffd3f9cb30d645660bdad99a21278"
APPROVAL = "FITFINITY-TEST-2026-10-07-86183723"
ACCEPT_RUN = 37613240855
ACCEPT_ARTIFACT = 11480831590
ACCEPT_SHA = "34133cf9939ed03e4b35f01b05bc698c97308f273fbf0361e8e4f69d0ff35e01"
POLICY_SHA = "054c6f32f5ba8541d4c389da8fdabc85f6e9c0720a8f53924044da7531c42991"


def local_approval():
    raw = (Path(__file__).parent / "image-test-approvals.json").read_bytes()
    require(sha(raw) == POLICY_SHA, "Reviewed approval policy changed")
    rows = [r for r in json.loads(raw)["approvals"] if r["id"] == APPROVAL]
    require(len(rows) == 1, "Missing exact approval")
    return rows[0]


def check_approval(approval, provenance, now):
    require(
        approval == local_approval() and provenance == approval["provenance"],
        "Approval or provenance changed",
    )
    require(
        timestamp(approval["approved_at"]) <= now < timestamp(approval["expires_at"]),
        "Approval expired or future dated",
    )


def actions_environment():
    require(
        os.getenv("GITHUB_ACTIONS") == "true"
        and os.getenv("GITHUB_REPOSITORY") == GITHUB_REPO
        and os.getenv("GITHUB_REF") == "refs/heads/main"
        and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch",
        "Runtime requires manual reviewed-main Actions execution",
    )
    forbidden = {
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_CA_BUNDLE",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_ROLE_ARN",
        "AWS_SECURITY_TOKEN",
        "AWS_PROFILE",
    }
    require(
        not any(
            v and (k in forbidden or k.startswith("AWS_ENDPOINT_URL"))
            for k, v in os.environ.items()
        ),
        "AWS credential/config/endpoint override refused",
    )
    require(
        all(
            os.getenv(k)
            for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
        ),
        "Temporary OIDC credentials required",
    )


def verify_main(report):
    image = ExistingImage({})
    head = image.command(["git", "rev-parse", "HEAD"]).strip()
    require(
        head == os.getenv("GITHUB_SHA")
        and not image.command(["git", "status", "--porcelain", "--untracked-files=all"]).strip(),
        "Exact clean operator checkout required",
    )
    remote = image.github(f"repos/{GITHUB_REPO}/git/ref/heads/main")
    require(remote.get("object", {}).get("sha") == head, "Reviewed main moved")
    report["operator_commit"] = head


def collect_binding(report):
    """All GitHub reads are authenticated; downloaded success flags confer no authority."""
    verify_main(report)
    image = ExistingImage({})
    candidate, provenance = image.trusted_candidate(37584327992, 1, 11467134068, DIGEST)
    approval = image.reviewed_approval(APPROVAL)
    require(
        candidate["revision"] == SOURCE and approval == local_approval(),
        "Image source or merged approval differs",
    )
    prefix = f"repos/{GITHUB_REPO}"
    run = image.github(f"{prefix}/actions/runs/{ACCEPT_RUN}/attempts/1")
    require(
        run.get("id") == ACCEPT_RUN
        and run.get("run_attempt") == 1
        and run.get("repository", {}).get("full_name") == GITHUB_REPO
        and run.get("head_repository", {}).get("full_name") == GITHUB_REPO
        and run.get("head_branch") == "main"
        and run.get("event") == "workflow_dispatch"
        and run.get("path") == ".github/workflows/aws-image-accept.yml"
        and run.get("conclusion") == "success"
        and run.get("status") == "completed",
        "Untrusted acceptance run",
    )
    artifact = image.github(f"{prefix}/actions/artifacts/{ACCEPT_ARTIFACT}")
    require(
        artifact.get("id") == ACCEPT_ARTIFACT
        and artifact.get("expired") is False
        and artifact.get("name") == f"fitfinity-image-acceptance-{ACCEPT_RUN}-1"
        and artifact.get("workflow_run", {}).get("id") == ACCEPT_RUN
        and artifact["workflow_run"].get("head_sha") == run["head_sha"],
        "Untrusted acceptance artifact",
    )
    raw = image.github(f"{prefix}/actions/artifacts/{ACCEPT_ARTIFACT}/zip", binary=True)
    require(
        sha(raw) == ACCEPT_SHA and artifact.get("digest") == "sha256:" + ACCEPT_SHA,
        "Acceptance ZIP checksum differs",
    )
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(
            archive.namelist().count("fitfinity-image-acceptance.json") == 1
            and archive.getinfo("fitfinity-image-acceptance.json").file_size < 5000000,
            "Invalid acceptance ZIP",
        )
        receipt = json.loads(archive.read("fitfinity-image-acceptance.json"))
    require(
        receipt.get("image_digest") == DIGEST
        and receipt.get("candidate_provenance") == provenance
        and receipt.get("approval") == approval
        and receipt.get("policy_revision") == run["head_sha"],
        "Acceptance receipt binding differs",
    )
    contract = json.loads((Path(__file__).parent / "private-runtime-contract.json").read_text())
    expected = {
        n.removeprefix("backend/"): h
        for n, h in candidate["source_files"].items()
        if n.startswith(("backend/app/", "backend/migrations/"))
        or n in {"backend/alembic.ini", "backend/requirements.lock"}
    }
    lock = image.command(["git", "show", SOURCE + ":backend/requirements.lock"])
    dependencies = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", lock, re.M))
    require(
        contract == {"revision": SOURCE, "files": expected, "dependencies": dependencies},
        "Probe inventory differs from authenticated build",
    )
    report.update(
        candidate=candidate,
        candidate_provenance=provenance,
        approval=approval,
        acceptance_artifact_sha256=ACCEPT_SHA,
        acceptance_run=ACCEPT_RUN,
    )


def review_image(report, aws, now):
    candidate = report["candidate"]
    check_approval(report["approval"], report["candidate_provenance"], now)
    value = aws(
        "ecr",
        "batch-get-image",
        "--repository-name",
        "fitfinity-test-api",
        "--image-ids",
        "imageDigest=" + DIGEST,
    )
    require(not value.get("failures") and len(value.get("images", [])) == 1, "Missing image")
    row = value["images"][0]
    raw = row.get("imageManifest", "")
    require(
        row.get("registryId") == "418638389566"
        and row.get("repositoryName") == "fitfinity-test-api"
        and row.get("imageId", {}).get("imageDigest") == DIGEST
        and "sha256:" + sha(raw.encode()) == DIGEST
        and json.loads(raw).get("config", {}).get("digest") == candidate["config_digest"],
        "Exact image manifest differs",
    )
    # Reuse complete scan pagination and the existing freshness/approval policy.
    image = ExistingImage(report)
    image.aws = aws
    pages = image.scan(DIGEST, read_only=True)
    result, counts = acceptance(
        pages, DIGEST, report["candidate_provenance"], report["approval"], now
    )
    report.update(current_scan_pages=pages, image_security_result=result, severity_counts=counts)


def restore_state(run_id, operation_id, operator_commit):
    """Restore only an authenticated artifact of this exact manual workflow revision."""
    require(type(run_id) is int and run_id > 0, "Invalid recovery run")
    image = ExistingImage({})
    prefix = f"repos/{GITHUB_REPO}"
    run = image.github(f"{prefix}/actions/runs/{run_id}")
    require(
        run.get("repository", {}).get("full_name") == GITHUB_REPO
        and run.get("head_repository", {}).get("full_name") == GITHUB_REPO
        and run.get("head_sha") == operator_commit
        and run.get("head_branch") == "main"
        and run.get("event") == "workflow_dispatch"
        and run.get("status") == "completed"
        and run.get("path") == ".github/workflows/aws-private-runtime.yml",
        "Untrusted recovery run",
    )
    artifacts = image.github(f"{prefix}/actions/runs/{run_id}/artifacts?per_page=100")
    require(
        artifacts.get("total_count") == len(artifacts.get("artifacts", [])),
        "Incomplete recovery artifact inventory",
    )
    rows = [
        r
        for r in artifacts["artifacts"]
        if r["name"] == f"fitfinity-private-runtime-{operation_id}-{run_id}-{run['run_attempt']}"
    ]
    require(
        len(rows) == 1 and rows[0].get("expired") is False, "Missing or ambiguous recovery artifact"
    )
    raw = image.github(f"{prefix}/actions/artifacts/{rows[0]['id']}/zip", binary=True)
    require(rows[0].get("digest") == "sha256:" + sha(raw), "Recovery checksum differs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(
            archive.namelist().count("private-runtime/state.json") == 1
            and archive.getinfo("private-runtime/state.json").file_size < 5000000,
            "Invalid recovery state archive",
        )
        state = json.loads(archive.read("private-runtime/state.json"))
    require(
        state.get("operation_id") == operation_id
        and state.get("operator_commit") == operator_commit
        and state.get("operator_revision") == "2026-10-07-private-runtime-1"
        and state.get("image_digest") == DIGEST
        and state.get("approval_id") == APPROVAL,
        "Recovery binding differs",
    )
    return state
