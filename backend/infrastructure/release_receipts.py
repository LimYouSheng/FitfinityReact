"""Retrieve bounded receipts from authenticated child-workflow artifacts."""

import hashlib
import io
import json
import stat
import subprocess
import zipfile
from pathlib import PurePosixPath

from operator_checks import require
from release_dispatch import WORKFLOWS
from release_verification import api
from schema_probe_artifacts import run_binding

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_DOCUMENT = 4 * 1024 * 1024
RECEIPTS = {
    "aws-image.yml": ("image-candidate", ("fitfinity-image-candidate.json",)),
    "aws-release-observe.yml": ("release-observation", ("release-observation.json",)),
    "aws-release-prepare.yml": ("release-prepare", ("release-readiness.json",)),
    "aws-schema-probe.yml": ("schema-probe", ("schema-probe-receipt.json",)),
    "aws-schema-upgrade.yml": ("schema-upgrade", ("schema-upgrade-receipt.json",)),
    "aws-maintenance.yml": ("maintenance", ("maintenance-receipt.json",)),
    "aws-rollout.yml": ("rollout", ("rollout-receipt.json",)),
}
REVIEWS = (
    "schema-probe-review/review.json",
    "schema-upgrade-review/review.json",
    "maintenance-review/review.json",
)


def download(path):
    """Download one GitHub archive without running or extracting its contents."""
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", path], capture_output=True, timeout=120
    )
    require(result.returncode == 0, "Receipt archive unavailable; preserve the original run")
    require(len(result.stdout) <= MAX_ARCHIVE, "Receipt archive exceeds size limit")
    return result.stdout


def documents(body, required, optional=()):
    """Read exact JSON members while rejecting duplicate, redirected and oversized archives."""
    require(isinstance(body, bytes) and len(body) <= MAX_ARCHIVE, "Invalid receipt archive")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        rows = archive.infolist()
        names = [row.filename for row in rows]
        require(len(names) == len(set(names)), "Duplicate archive members")
        require(sum(row.file_size for row in rows) <= 4 * MAX_ARCHIVE, "Expanded archive too large")
        for row in rows:
            path = PurePosixPath(row.filename)
            require(
                not path.is_absolute()
                and ".." not in path.parts
                and "\\" not in row.filename
                and not stat.S_ISLNK(row.external_attr >> 16),
                "Redirected archive member",
            )
        require(set(required) <= set(names), "Required operational receipt missing")
        result = {}
        for name in (*required, *optional):
            if name not in names:
                continue
            require(archive.getinfo(name).file_size <= MAX_DOCUMENT, "Receipt document too large")
            value = json.loads(archive.read(name))
            require(isinstance(value, dict), "Receipt must be an object")
            result[name] = value
        return result


def fetch(stage, run_id, source, profile, *, read=api, fetch_bytes=download):
    """Authenticate the exact child attempt, artifact identity and archive digest before reading."""
    require(
        stage in WORKFLOWS and type(run_id) is int and run_id > 0, "Exact child stage/run required"
    )
    workflow = WORKFLOWS[stage]
    repository = profile["github_repository"]
    root = f"repos/{repository}/actions/runs/{run_id}"
    run = read(root)
    revision, attempt = run_binding(run, workflow.removesuffix(".yml"), source, profile=profile)
    require(run.get("id") == run_id and attempt == 1, "Original child attempt required")
    prefix, required = RECEIPTS[workflow]
    name = f"fitfinity-{prefix}-"
    if workflow in {"aws-release-prepare.yml", "aws-release-observe.yml"}:
        name += revision + "-"
    name += f"{run_id}-{attempt}"
    listing = read(root + "/artifacts?per_page=100")
    rows = listing.get("artifacts", [])
    require(listing.get("total_count") == len(rows), "Incomplete artifact inventory")
    matches = [row for row in rows if row.get("name") == name]
    require(len(matches) == 1, "Exact child artifact missing or ambiguous")
    artifact = matches[0]
    require(
        artifact.get("expired") is False
        and type(artifact.get("id")) is int
        and artifact["id"] > 0
        and type(artifact.get("size_in_bytes")) is int
        and 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE,
        "Artifact expired or invalid",
    )
    body = fetch_bytes(f"repos/{repository}/actions/artifacts/{artifact['id']}/zip")
    require(isinstance(body, bytes) and len(body) <= MAX_ARCHIVE, "Invalid artifact bytes")
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    require(artifact.get("digest") == digest, "Artifact digest differs")
    values = documents(body, required, REVIEWS if workflow == "aws-release-prepare.yml" else ())
    return {
        "run_id": run_id,
        "attempt": attempt,
        "source_sha": source,
        "artifact_id": artifact["id"],
        "artifact_sha256": digest,
        "documents": values,
    }
