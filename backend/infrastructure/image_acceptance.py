"""Read-only security acceptance of a trusted published TEST image; never a release."""

import io
import json
import os
import re
import subprocess
import zipfile
from datetime import UTC, datetime

from operator_checks import require
from release_image import (
    ACCOUNT,
    REGION,
    REPOSITORY,
    URI,
    ImageCandidate,
    scan_evidence,
    sha,
    strict_scan_passed,
    timestamp,
)

GITHUB_REPO = "LimYouSheng/FitfinityReact"
POLICY = "backend/infrastructure/image-test-approvals.json"
READS = {
    ("sts", "get-caller-identity"),
    ("ecr", "describe-repositories"),
    ("ecr", "list-tags-for-resource"),
    ("ecr", "get-registry-scanning-configuration"),
    ("ecr", "batch-get-image"),
    ("ecr", "describe-image-scan-findings"),
}


def finding_identity(row):
    attributes = row.get("attributes", [])
    require(isinstance(attributes, list), "Malformed finding attributes")
    values = {}
    for item in attributes:
        require(isinstance(item, dict), "Malformed finding attribute")
        key = item.get("key")
        if key in {"package_name", "package_version"}:
            require(
                key not in values and isinstance(item.get("value"), str) and item["value"],
                "Missing or ambiguous package identity",
            )
            values[key] = item["value"]
    require(
        re.fullmatch(r"CVE-[0-9]{4}-[0-9]+", row.get("name", "")) and len(values) == 2,
        "Missing exact CVE/package/version identity",
    )
    return {
        "cve": row["name"],
        "package": values["package_name"],
        "version": values["package_version"],
        "severity": row["severity"],
    }


def acceptance(pages, digest, provenance, approval, now):
    counts, findings = scan_evidence(pages, digest, now)
    require(
        not counts.get("CRITICAL", 0) and not counts.get("UNDEFINED", 0),
        "Critical or unclassified findings cannot receive a TEST exception",
    )
    if approval is None:
        require(strict_scan_passed(counts), "High findings require an exact reviewed TEST approval")
        return "strict_policy_passed", counts
    require(
        isinstance(approval, dict) and approval.get("status") == "approved",
        "Approval missing or revoked",
    )
    for key in ("id", "approval_reference", "approver", "reason", "approved_at", "expires_at"):
        require(
            isinstance(approval.get(key), str) and approval[key].strip(),
            "Malformed approval metadata",
        )
    require(
        approval["approver"] == "LimYouSheng"
        and timestamp(approval["approved_at"]) <= now < timestamp(approval["expires_at"]),
        "Approval expired or future dated",
    )
    require(
        all(
            approval.get(key) == value
            for key, value in {
                "account": ACCOUNT,
                "region": REGION,
                "repository": REPOSITORY,
                "environment": "test",
                "image_digest": digest,
                "provenance": provenance,
            }.items()
        ),
        "Approval scope/provenance differs",
    )
    approved = approval.get("findings")
    actual = [finding_identity(row) for row in findings if row["severity"] == "HIGH"]
    require(
        isinstance(approved, list)
        and bool(approved)
        and all(
            isinstance(row, dict)
            and set(row) == {"cve", "package", "version", "severity"}
            and row.get("severity") == "HIGH"
            for row in approved
        ),
        "Malformed exact finding approval",
    )

    def canonical(rows):
        return sorted(json.dumps(row, sort_keys=True) for row in rows)

    require(
        len(set(canonical(approved))) == len(approved) and canonical(approved) == canonical(actual),
        "Finding set changed; obtain a new exact review (do not infer a fix)",
    )
    return "accepted_with_test_exception", counts


class ExistingImage(ImageCandidate):
    def aws(self, service, operation, *args, **kwargs):
        require((service, operation) in READS, "Existing image evaluation is read-only")
        return super().aws(service, operation, *args, **kwargs)

    def github(self, path, *, binary=False):
        require(path.startswith(f"repos/{GITHUB_REPO}/"), "Unexpected GitHub repository")
        result = subprocess.run(
            ["gh", "api", "--method", "GET", "--hostname", "github.com", path],
            cwd=self.root,
            capture_output=True,
            timeout=120,
        )
        require(result.returncode == 0, "Cannot read trusted GitHub evidence")
        return result.stdout if binary else json.loads(result.stdout)

    def trusted_candidate(self, run_id, attempt, artifact_id, digest):
        prefix = f"repos/{GITHUB_REPO}"
        run = self.github(f"{prefix}/actions/runs/{run_id}/attempts/{attempt}")
        revision = run.get("head_sha", "")
        require(
            run.get("id") == run_id
            and run.get("run_attempt") == attempt
            and run.get("repository", {}).get("full_name") == GITHUB_REPO
            and run.get("head_repository", {}).get("full_name") == GITHUB_REPO
            and run.get("head_branch") == "main"
            and run.get("event") in {"push", "workflow_dispatch"}
            and run.get("path") == ".github/workflows/pages.yml"
            and run.get("status") == "completed"
            and re.fullmatch(r"[0-9a-f]{40}", revision),
            "Untrusted candidate workflow provenance",
        )
        self.command(["git", "merge-base", "--is-ancestor", revision, "HEAD"])
        jobs = []
        for page in range(1, 101):
            result = self.github(
                f"{prefix}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}"
            )
            jobs.extend(result["jobs"])
            if len(jobs) == result["total_count"]:
                break
            require(
                result["jobs"] and len(jobs) < result["total_count"], "Incomplete job pagination"
            )
        else:
            raise RuntimeError("Excessive job pagination")
        for name in ("verify / frontend", "verify / backend"):
            matches = [job for job in jobs if job.get("name") == name]
            require(
                len(matches) == 1 and matches[0].get("conclusion") == "success",
                "Candidate source lacks complete required CI",
            )
        images = [job for job in jobs if job.get("name") == "image / image"]
        require(
            len(images) == 1 and images[0].get("conclusion") in {"success", "failure"},
            "Missing canonical image job",
        )
        artifact = self.github(f"{prefix}/actions/artifacts/{artifact_id}")
        require(
            artifact.get("id") == artifact_id
            and artifact.get("expired") is False
            and artifact.get("name") == f"fitfinity-image-candidate-{run_id}-{attempt}"
            and artifact.get("workflow_run", {}).get("id") == run_id
            and artifact["workflow_run"].get("head_sha") == revision,
            "Candidate artifact provenance differs",
        )
        data = self.github(f"{prefix}/actions/artifacts/{artifact_id}/zip", binary=True)
        require(artifact.get("digest") == "sha256:" + sha(data), "Artifact checksum differs")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            require(
                archive.namelist().count("fitfinity-image-candidate.json") == 1
                and archive.getinfo("fitfinity-image-candidate.json").file_size <= 5000000,
                "Invalid candidate receipt archive",
            )
            candidate = json.loads(archive.read("fitfinity-image-candidate.json"))
        require(
            candidate.get("account") == ACCOUNT
            and candidate.get("region") == REGION
            and candidate.get("revision") == revision
            and candidate.get("image_digest") == digest
            and candidate.get("image_uri") == URI + "@" + digest
            and candidate.get("image_tag") == f"{URI}:commit-{revision}-{run_id}-{attempt}"
            and candidate.get("runtime_build_complete") is True
            and candidate.get("image_published") is True
            and re.fullmatch(r"sha256:[0-9a-f]{64}", candidate.get("config_digest", "")),
            "Candidate receipt does not bind the published build",
        )
        # Recompute the original source manifest from Git objects, never today's policy checkout.
        manifest = {}
        for entry in filter(
            None,
            self.command(["git", "ls-tree", "-r", "-z", revision, "--", "backend"]).split("\0"),
        ):
            metadata, name = entry.split("\t", 1)
            mode, kind, _ = metadata.split()
            require(mode in {"100644", "100755"} and kind == "blob", "Redirected candidate source")
            # Backend build inputs are text files; preserve bytes using git through subprocess.
            raw = subprocess.run(
                ["git", "show", f"{revision}:{name}"],
                cwd=self.root,
                capture_output=True,
                check=True,
                timeout=30,
            ).stdout
            manifest[name] = sha(raw)
        fingerprint = sha(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
        require(
            "backend/Dockerfile" in manifest
            and candidate.get("source_files") == manifest
            and candidate.get("source_sha256") == fingerprint,
            "Candidate source manifest differs",
        )
        provenance = {
            "source_revision": revision,
            "source_sha256": fingerprint,
            "run_id": run_id,
            "run_attempt": attempt,
            "artifact_id": artifact_id,
            "artifact_sha256": sha(data),
        }
        return candidate, provenance

    def reviewed_approval(self, approval_id):
        policy = json.loads((self.root / POLICY).read_text())
        require(
            policy.get("version") == 1 and isinstance(policy.get("approvals"), list),
            "Invalid approval policy",
        )
        matches = [item for item in policy["approvals"] if item.get("id") == approval_id]
        require(len(matches) == 1, "Approval missing or ambiguous")
        approval = matches[0]
        match = re.fullmatch(
            r"https://github.com/LimYouSheng/FitfinityReact/pull/([1-9][0-9]*)",
            approval.get("approval_reference", ""),
        )
        require(match is not None, "Approval requires an authoritative merged review reference")
        pr = self.github(f"repos/{GITHUB_REPO}/pulls/{match[1]}")
        merge = pr.get("merge_commit_sha", "")
        require(
            pr.get("merged") is True
            and pr.get("merged_by", {}).get("login") == "LimYouSheng"
            and pr.get("base", {}).get("ref") == "main"
            and pr.get("base", {}).get("repo", {}).get("full_name") == GITHUB_REPO
            and re.fullmatch(r"[0-9a-f]{40}", merge),
            "Approval was not merged by the authorized reviewer",
        )
        self.command(["git", "merge-base", "--is-ancestor", merge, "HEAD"])
        reviewed = json.loads(self.command(["git", "show", f"{merge}:{POLICY}"]))
        require(
            [item for item in reviewed.get("approvals", []) if item.get("id") == approval_id]
            == [approval],
            "Approval differs from the user-merged review",
        )
        return approval

    def evaluate(self, digest, run_id, attempt, artifact_id, approval_id):
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", digest), "Exact immutable digest required")
        require(
            all(type(value) is int and value > 0 for value in (run_id, attempt, artifact_id)),
            "Invalid build identity",
        )
        # Exact clean main Actions checkout: policy revision, not the original build.
        self.source()
        self.report["policy_revision"] = self.report.pop("revision")
        candidate, provenance = self.trusted_candidate(run_id, attempt, artifact_id, digest)
        self.report.update(
            candidate_provenance=provenance, image_digest=digest, image_uri=URI + "@" + digest
        )
        approval = self.reviewed_approval(approval_id) if approval_id else None
        self.identity()
        response = self.aws(
            "ecr",
            "batch-get-image",
            "--registry-id",
            ACCOUNT,
            "--repository-name",
            REPOSITORY,
            "--image-ids",
            "imageDigest=" + digest,
        )
        require(
            not response.get("failures") and len(response.get("images", [])) == 1,
            "Published image missing",
        )
        row = response["images"][0]
        raw = row.get("imageManifest", "")
        manifest = json.loads(raw)
        require(
            row.get("registryId") == ACCOUNT
            and row.get("repositoryName") == REPOSITORY
            and row.get("imageId", {}).get("imageDigest") == digest
            and "sha256:" + sha(raw.encode()) == digest
            and manifest.get("schemaVersion") == 2
            and manifest.get("mediaType")
            in {
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.v2+json",
            }
            and manifest.get("config", {}).get("digest") == candidate["config_digest"],
            "ECR manifest differs from trusted candidate",
        )
        pages = self.scan(digest, read_only=True)
        result, counts = acceptance(pages, digest, provenance, approval, datetime.now(UTC))
        self.report.update(
            result=result,
            severity_counts=counts,
            scan_policy_passed=result == "strict_policy_passed",
            image_security_accepted=True,
            approval=approval,
        )


def accept_existing(receipt, digest, run_id, attempt, artifact_id, approval_id=None):
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "account": ACCOUNT,
        "region": REGION,
        "result": "blocked",
        "scan_policy_passed": False,
        "image_security_accepted": False,
        "application_deployed": False,
        "live_authentication_accepted": False,
        "cloud_write_attempts": [],
    }
    with os.fdopen(os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
        try:
            ExistingImage(report).evaluate(digest, run_id, attempt, artifact_id, approval_id)
        except Exception as error:
            report["failure_type"] = type(error).__name__
            report["blocked_reason"] = (
                str(error) if isinstance(error, RuntimeError) else type(error).__name__
            )
            raise
        finally:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    print(f"PASS — {report['result']}; image security only, no deployment or runtime acceptance.")
