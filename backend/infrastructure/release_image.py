"""Build and scan a current image after CI; never deploy it or reuse old exceptions."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from deployment_profile import DEVELOPER, identities
from image_build_identity import build_identity, valid_digest
from operator_checks import require
from operator_errors import PROVIDER_ERRORS, OperatorFailure, safe_reason
from scan_waiver import developer_exception

ROOT = Path(__file__).resolve().parents[2]
_DEVELOPER = identities(DEVELOPER)
ACCOUNT, REGION = _DEVELOPER["account"], _DEVELOPER["region"]
REPOSITORY = _DEVELOPER["image_repository"]
REGISTRY = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"
URI = f"{REGISTRY}/{REPOSITORY}"
ARN = f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{REPOSITORY}"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/{_DEVELOPER['image_role']}"
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL", "UNDEFINED"}
AWS_OPERATIONS = {
    ("sts", "get-caller-identity"),
    ("ecr", "describe-repositories"),
    ("ecr", "list-tags-for-resource"),
    ("ecr", "get-registry-scanning-configuration"),
    ("ecr", "batch-get-image"),
    ("ecr", "get-login-password"),
    ("ecr", "start-image-scan"),
    ("ecr", "describe-image-scan-findings"),
}


class AWSFailure(OperatorFailure):
    def __init__(self, code, operation="image operation"):
        self.code = code
        safe_code = code if code in PROVIDER_ERRORS else "UnknownProviderError"
        super().__init__(f"AWS {operation} failed; code={safe_code}; private response suppressed")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None, "Scan timestamp must include its timezone")
        return result
    except (TypeError, AttributeError, ValueError):
        raise RuntimeError("Invalid scan timestamp") from None


def scan_evidence(pages, digest, now, *, profile=DEVELOPER):
    """Check complete current basic-scan evidence, including every findings page."""
    target = identities(profile)
    require(bool(pages), "Missing scan evidence")
    first = pages[0].get("imageScanFindings", {})
    counts = first.get("findingSeverityCounts")
    require(
        isinstance(counts, dict)
        and set(counts) <= SEVERITIES
        and all(type(value) is int and value >= 0 for value in counts.values()),
        "Invalid scan severity counts",
    )
    completed = timestamp(first.get("imageScanCompletedAt"))
    require(now - timedelta(hours=24) <= completed <= now, "Scan evidence is stale or future dated")
    findings = []
    seen = set()
    for index, page in enumerate(pages):
        require(
            page.get("registryId") == target["account"]
            and page.get("repositoryName") == target["image_repository"]
            and page.get("imageId", {}).get("imageDigest") == digest
            and page.get("imageScanStatus", {}).get("status") == "COMPLETE",
            "Scan identity or completion differs",
        )
        body = page.get("imageScanFindings", {})
        require(
            body.get("findingSeverityCounts") == counts
            and body.get("imageScanCompletedAt") == first.get("imageScanCompletedAt"),
            "Scan changed during pagination",
        )
        token = page.get("nextToken")
        require(
            (isinstance(token, str) and bool(token) and token not in seen)
            if index < len(pages) - 1
            else token is None,
            "Incomplete or repeated scan pagination",
        )
        seen.add(token)
        rows = body.get("findings")
        require(isinstance(rows, list), "Missing scan findings")
        require(
            all(isinstance(row, dict) and row.get("severity") in SEVERITIES for row in rows),
            "Unclassified scan finding",
        )
        findings.extend(rows)
    require(
        Counter(row["severity"] for row in findings)
        == Counter({key: value for key, value in counts.items() if value}),
        "Scan findings do not match the complete counts",
    )
    return counts, findings


def strict_scan_passed(counts):
    return not any(counts.get(level, 0) for level in ("CRITICAL", "HIGH", "UNDEFINED"))


def scan_policy(pages, digest, now, *, profile=DEVELOPER, source_files=None, decision=None):
    """Apply strict policy or the exact time-limited developer exception."""
    counts, findings = scan_evidence(pages, digest, now, profile=profile)
    result = {"kind": "strict"}
    if not strict_scan_passed(counts):
        require(source_files is not None, "Image scan blocked by severity policy")
        result = developer_exception(findings, digest, now, profile, source_files)
    if decision is not None:
        decision.update(result)
    return counts


class ImageCandidate:
    def __init__(self, report, root=ROOT, *, profile=DEVELOPER):
        self.profile = dict(profile)
        self.target = identities(profile)
        self.account, self.region = self.target["account"], self.target["region"]
        self.repository = self.target["image_repository"]
        self.registry = self.target["registry"]
        self.uri = self.registry + "/" + self.repository
        self.arn = f"arn:aws:ecr:{self.region}:{self.account}:repository/{self.repository}"
        self.report = report
        self.report.update(
            account=self.account, region=self.region, profile_sha256=self.target["profile_sha256"]
        )
        self.root = root

    def command(self, args, *, private=False, input_data=None, env=None, timeout=120):
        stream = args[0] == "docker" and "build" in args and not private
        result = subprocess.run(
            args,
            cwd=self.root,
            input=input_data,
            text=True,
            capture_output=not stream,
            timeout=timeout,
            env=env,
        )
        if result.returncode and args[0] == "aws":
            match = re.search(r"An error occurred \(([A-Za-z0-9]+)\)", result.stderr or "")
            raise AWSFailure(match[1] if match else "Unknown", "/".join(args[1:3]))
        require(result.returncode == 0, f"{args[0]} command failed; private response suppressed")
        return result.stdout or ""

    def aws(self, service, operation, *args, raw=False):
        require((service, operation) in AWS_OPERATIONS, "Operation outside image release scope")
        output = self.command(
            [
                "aws",
                service,
                operation,
                *args,
                "--region",
                self.region,
                "--no-cli-pager",
                "--no-cli-auto-prompt",
                "--cli-connect-timeout",
                "10",
                "--cli-read-timeout",
                "30",
                "--output",
                "text" if raw else "json",
            ],
            private=True,
            env={
                **os.environ,
                "AWS_PAGER": "",
                "AWS_CLI_AUTO_PROMPT": "off",
                "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
                "AWS_MAX_ATTEMPTS": "2",
            },
        )
        return output if raw else json.loads(output)

    def source(self):
        require(
            os.getenv("GITHUB_ACTIONS") == "true"
            and os.getenv("GITHUB_REPOSITORY") == self.target["github_repository"]
            and os.getenv("GITHUB_REF") == "refs/heads/main"
            and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and os.getenv("GITHUB_WORKFLOW_REF")
            == self.target["github_repository"]
            + "/.github/workflows/aws-image.yml@refs/heads/main",
            "Image publication requires the verified main Actions workflow",
        )
        revision = os.getenv("GITHUB_SHA", "")
        require(re.fullmatch(r"[0-9a-f]{40}", revision), "Invalid source revision")
        require(
            self.command(["git", "rev-parse", "HEAD"]).strip() == revision
            and not self.command(["git", "status", "--porcelain", "--untracked-files=all"]).strip(),
            "Build requires the exact clean verified commit",
        )
        # Only tracked backend files enter the context. Ignored local credentials cannot leak in.
        files = self.command(["git", "ls-tree", "-r", "-z", "HEAD", "--", "backend"]).split("\0")
        manifest = {}
        for entry in filter(None, files):
            metadata, name = entry.split("\t", 1)
            mode, kind, blob = metadata.split()
            file = self.root / name
            require(
                mode in {"100644", "100755"}
                and kind == "blob"
                and file.is_file()
                and not file.is_symlink(),
                "Redirected backend source refused",
            )
            data = file.read_bytes()
            require(
                hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == blob,
                "Backend bytes differ from the verified commit",
            )
            manifest[name] = sha(data)
        require("backend/Dockerfile" in manifest, "Missing tracked runtime Dockerfile")
        fingerprint = sha(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
        for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
            require(
                re.fullmatch(r"[1-9][0-9]*", os.getenv(name, "")), "Invalid Actions run identity"
            )
        self.report.update(revision=revision, source_sha256=fingerprint, source_files=manifest)
        return manifest

    def identity(self):
        blocked = {
            "AWS_CONFIG_FILE",
            "AWS_SHARED_CREDENTIALS_FILE",
            "AWS_CA_BUNDLE",
            "AWS_WEB_IDENTITY_TOKEN_FILE",
            "AWS_ROLE_ARN",
            "AWS_SECURITY_TOKEN",
            "AWS_PROFILE",
            "AWS_DEFAULT_PROFILE",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
        }
        require(
            not any(
                value and (key in blocked or key.startswith("AWS_ENDPOINT_URL"))
                for key, value in os.environ.items()
            ),
            "Credential, endpoint or Docker override refused",
        )
        require(
            all(
                os.getenv(key)
                for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
            ),
            "Temporary Actions credentials required",
        )
        identity = self.aws("sts", "get-caller-identity")
        require(
            identity.get("Account") == self.account
            and re.fullmatch(
                rf"arn:aws:sts::{self.account}:assumed-role/"
                rf"{re.escape(self.target['image_role'])}/[A-Za-z0-9+=,.@_-]+",
                identity.get("Arn", ""),
            ),
            "Unexpected image publication principal",
        )
        self.report["identity"] = identity["Arn"]
        response = self.aws("ecr", "describe-repositories", "--repository-names", self.repository)
        rows = response.get("repositories", [])
        require(len(rows) == 1, "Expected one existing image repository")
        row = rows[0]
        require(
            row.get("registryId") == self.account
            and row.get("repositoryName") == self.repository
            and row.get("repositoryArn") == self.arn
            and row.get("repositoryUri") == self.uri
            and row.get("imageTagMutability") == "IMMUTABLE"
            and row.get("encryptionConfiguration", {}).get("encryptionType") == "AES256",
            "Image repository configuration differs",
        )
        tags = {
            item["Key"]: item["Value"]
            for item in self.aws("ecr", "list-tags-for-resource", "--resource-arn", self.arn).get(
                "tags", []
            )
        }
        require(
            all(
                tags.get(key) == value
                for key, value in {
                    "Application": "Fitfinity",
                    "Environment": self.target["environment_tag"],
                    "ManagedBy": self.target["resource_prefix"] + "-image-uploader",
                }.items()
            ),
            "Image repository ownership differs",
        )
        scan = self.aws("ecr", "get-registry-scanning-configuration")
        require(
            scan.get("registryId") == self.account
            and scan.get("scanningConfiguration", {}).get("scanType") == "BASIC",
            "Expected basic scanning; registry configuration will not be changed",
        )

    def build(self, files, folder, tag):
        context = folder / "context"
        context.mkdir()
        for name, expected in files.items():
            data = (self.root / name).read_bytes()
            require(sha(data) == expected, "Source changed before build")
            target = context / Path(name).relative_to("backend")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        metadata_path = folder / "build-metadata.json"
        print("Building the verified runtime source for linux/amd64…", flush=True)
        self.command(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                "linux/amd64",
                "--target",
                "runtime",
                "--pull",
                "--no-cache",
                "--provenance=false",
                "--sbom=false",
                "--load",
                "--metadata-file",
                str(metadata_path),
                "--label",
                f"org.opencontainers.image.revision={self.report['revision']}",
                "--label",
                f"ai.app404.fitfinity.source-sha256={self.report['source_sha256']}",
                "--tag",
                tag,
                str(context),
            ],
            timeout=1200,
        )
        metadata = json.loads(metadata_path.read_text())
        rows = json.loads(self.command(["docker", "image", "inspect", tag], private=True))
        require(len(rows) == 1, "Expected one built runtime image")
        row = rows[0]
        identity = build_identity(metadata, row)
        labels = row.get("Config", {}).get("Labels", {})
        require(
            row.get("Os") == "linux"
            and row.get("Architecture") == "amd64"
            and row.get("Config", {}).get("User") == "10001:10001"
            and labels.get("org.opencontainers.image.revision") == self.report["revision"]
            and labels.get("ai.app404.fitfinity.source-sha256") == self.report["source_sha256"],
            "Built image architecture, user or source identity differs",
        )
        self.report.update(identity)
        self.report["runtime_build_complete"] = True

    def publish(self, folder, tag):
        tag_name = tag.split(":")[-1]
        existing = self.aws(
            "ecr",
            "batch-get-image",
            "--repository-name",
            self.repository,
            "--image-ids",
            f"imageTag={tag_name}",
        )
        require(
            existing.get("images") == []
            and len(existing.get("failures", [])) == 1
            and existing["failures"][0].get("failureCode") == "ImageNotFound",
            "Publication tag is occupied or unreadable; use a new Actions attempt",
        )
        docker_config = folder / "docker-auth"
        docker_config.mkdir(mode=0o700)
        password = self.aws("ecr", "get-login-password", raw=True)
        require(bool(password.strip()), "Missing registry login token")
        self.command(
            [
                "docker",
                "--config",
                str(docker_config),
                "login",
                "--username",
                "AWS",
                "--password-stdin",
                self.registry,
            ],
            private=True,
            input_data=password,
        )
        self.report["cloud_write_attempts"].append("publish-image")
        self.command(
            ["docker", "--config", str(docker_config), "push", tag], private=True, timeout=600
        )
        response = self.aws(
            "ecr",
            "batch-get-image",
            "--repository-name",
            self.repository,
            "--image-ids",
            f"imageTag={tag_name}",
        )
        require(
            not response.get("failures") and len(response.get("images", [])) == 1,
            "Published manifest missing",
        )
        image = response["images"][0]
        manifest_text = image.get("imageManifest", "")
        manifest = json.loads(manifest_text)
        digest = "sha256:" + sha(manifest_text.encode())
        require(
            image.get("registryId") == self.account
            and image.get("repositoryName") == self.repository
            and image.get("imageId", {}).get("imageTag") == tag_name
            and image.get("imageId", {}).get("imageDigest") == digest
            and manifest.get("schemaVersion") == 2
            and manifest.get("mediaType")
            in {
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.v2+json",
            }
            and valid_digest(manifest.get("config", {}).get("digest"))
            and (
                "build_manifest_digest" not in self.report
                or digest == self.report["build_manifest_digest"]
            )
            and (
                "config_digest" not in self.report
                or manifest.get("config", {}).get("digest") == self.report["config_digest"]
            )
            and ("config_digest" in self.report or "build_manifest_digest" in self.report),
            "Published manifest does not match the built image",
        )
        self.report.update(
            image_uri=self.uri + "@" + digest,
            image_digest=digest,
            image_published=True,
            config_digest=manifest["config"]["digest"],
        )
        return digest

    def scan(self, digest, *, read_only=False):
        args = [
            "--registry-id",
            self.account,
            "--repository-name",
            self.repository,
            "--image-id",
            "imageDigest=" + digest,
        ]
        pages = []
        started = False
        for attempt in range(31):
            try:
                page = self.aws(
                    "ecr",
                    "describe-image-scan-findings",
                    *args,
                    "--no-paginate",
                    "--max-results",
                    "1000",
                )
            except AWSFailure as error:
                require(
                    not read_only, "A current COMPLETE scan is required; request a scan separately"
                )
                require(error.code == "ScanNotFoundException", "Cannot read image scan")
                page = {"imageScanStatus": {"status": "PENDING"}}
                if not started:
                    self.report["cloud_write_attempts"].append("start-image-scan")
                    started = True
                    try:
                        self.aws("ecr", "start-image-scan", *args)
                    except AWSFailure as start_error:
                        require(
                            start_error.code == "LimitExceededException", "Cannot start image scan"
                        )
            status = page.get("imageScanStatus", {}).get("status")
            if status == "COMPLETE":
                pages.append(page)
                break
            require(not read_only, "A current COMPLETE scan is required; request a scan separately")
            require(status in {"IN_PROGRESS", "PENDING"}, "Image scan failed or unsupported")
            require(attempt < 30, "Image scan did not complete within five minutes")
            print("Waiting for image scan (10 seconds)…", flush=True)
            time.sleep(10)
        tokens = set()
        while pages[-1].get("nextToken"):
            token = pages[-1]["nextToken"]
            require(token not in tokens and len(pages) < 100, "Repeated or excessive scan pages")
            tokens.add(token)
            pages.append(
                self.aws(
                    "ecr",
                    "describe-image-scan-findings",
                    *args,
                    "--no-paginate",
                    "--max-results",
                    "1000",
                    "--next-token",
                    token,
                )
            )
        self.report["scan_pages"] = pages
        if read_only:
            return pages
        decision = {}
        self.report["severity_counts"] = scan_policy(
            pages,
            digest,
            datetime.now(UTC),
            profile=self.profile,
            source_files=self.report.get("source_files"),
            decision=decision,
        )
        self.report["scan_acceptance"] = decision
        self.report["scan_policy_passed"] = True

    def run(self):
        files = self.source()
        self.identity()
        name = f"commit-{self.report['revision']}-{os.environ['GITHUB_RUN_ID']}"
        tag = f"{self.uri}:{name}-{os.environ['GITHUB_RUN_ATTEMPT']}"
        self.report["image_tag"] = tag
        with tempfile.TemporaryDirectory(prefix="fitfinity-image-") as directory:
            folder = Path(directory)
            self.build(files, folder, tag)
            # Verify the source again before the first publication attempt.
            require(files == self.source(), "Source changed during runtime build")
            digest = self.publish(folder, tag)
            self.scan(digest)
        self.report["candidate_ready"] = True


def create_candidate(receipt, *, profile=DEVELOPER):
    target = identities(profile)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "account": target["account"],
        "region": target["region"],
        "profile_sha256": target["profile_sha256"],
        "candidate_ready": False,
        "image_published": False,
        "scan_policy_passed": False,
        "application_deployed": False,
        "live_authentication_accepted": False,
        "cloud_write_attempts": [],
    }
    # Reserve the receipt before any operation; never overwrite another receipt or a symlink.
    with os.fdopen(os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
        try:
            ImageCandidate(report, profile=profile).run()
        except Exception as error:
            report["failure_type"] = type(error).__name__
            report["error"] = safe_reason(error)
            raise
        finally:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    print("PASS — image candidate built, published and scanned. Live deployment remains pending.")
