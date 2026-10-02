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

from operator_checks import require

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "418638389566"
REGION = "ap-southeast-1"
REPOSITORY = "fitfinity-test-api"
REGISTRY = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"
URI = f"{REGISTRY}/{REPOSITORY}"
ARN = f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{REPOSITORY}"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/fitfinity-test-github-image"
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


class AWSFailure(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__("AWS image operation failed; private response suppressed")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None, "Scan timestamp must include its timezone")
        return result
    except (TypeError, AttributeError, ValueError):
        raise RuntimeError("Invalid scan timestamp") from None


def scan_policy(pages, digest, now):
    """Check complete current basic-scan evidence, including every findings page."""
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
            page.get("registryId") == ACCOUNT
            and page.get("repositoryName") == REPOSITORY
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
    require(
        not any(counts.get(level, 0) for level in ("CRITICAL", "HIGH", "UNDEFINED")),
        "Image blocked: critical, high or unclassified findings; no automatic exception",
    )
    return counts


class ImageCandidate:
    def __init__(self, report, root=ROOT):
        self.report = report
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
            raise AWSFailure(match[1] if match else "Unknown")
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
                REGION,
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
            and os.getenv("GITHUB_REPOSITORY") == "LimYouSheng/FitfinityReact"
            and os.getenv("GITHUB_REF") == "refs/heads/main"
            and os.getenv("GITHUB_EVENT_NAME") in {"push", "workflow_dispatch"},
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
            identity.get("Account") == ACCOUNT
            and re.fullmatch(
                rf"arn:aws:sts::{ACCOUNT}:assumed-role/"
                r"fitfinity-test-github-image/[A-Za-z0-9+=,.@_-]+",
                identity.get("Arn", ""),
            ),
            "Unexpected image publication principal",
        )
        self.report["identity"] = identity["Arn"]
        response = self.aws("ecr", "describe-repositories", "--repository-names", REPOSITORY)
        rows = response.get("repositories", [])
        require(len(rows) == 1, "Expected one existing image repository")
        row = rows[0]
        require(
            row.get("registryId") == ACCOUNT
            and row.get("repositoryName") == REPOSITORY
            and row.get("repositoryArn") == ARN
            and row.get("repositoryUri") == URI
            and row.get("imageTagMutability") == "IMMUTABLE"
            and row.get("encryptionConfiguration", {}).get("encryptionType") == "AES256",
            "Image repository configuration differs",
        )
        tags = {
            item["Key"]: item["Value"]
            for item in self.aws("ecr", "list-tags-for-resource", "--resource-arn", ARN).get(
                "tags", []
            )
        }
        require(
            all(
                tags.get(key) == value
                for key, value in {
                    "Application": "Fitfinity",
                    "Environment": "test",
                    "ManagedBy": "fitfinity-test-image-uploader",
                }.items()
            ),
            "Image repository ownership differs",
        )
        scan = self.aws("ecr", "get-registry-scanning-configuration")
        require(
            scan.get("registryId") == ACCOUNT
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
        rows = json.loads(self.command(["docker", "image", "inspect", tag], private=True))
        require(len(rows) == 1, "Expected one built runtime image")
        row = rows[0]
        labels = row.get("Config", {}).get("Labels", {})
        require(
            row.get("Os") == "linux"
            and row.get("Architecture") == "amd64"
            and row.get("Config", {}).get("User") == "10001:10001"
            and labels.get("org.opencontainers.image.revision") == self.report["revision"]
            and labels.get("ai.app404.fitfinity.source-sha256") == self.report["source_sha256"]
            and re.fullmatch(r"sha256:[0-9a-f]{64}", row.get("Id", "")),
            "Built image architecture, user or source identity differs",
        )
        self.report["config_digest"] = row["Id"]
        self.report["runtime_build_complete"] = True

    def publish(self, folder, tag):
        tag_name = tag.split(":")[-1]
        existing = self.aws(
            "ecr",
            "batch-get-image",
            "--repository-name",
            REPOSITORY,
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
                REGISTRY,
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
            REPOSITORY,
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
            image.get("registryId") == ACCOUNT
            and image.get("repositoryName") == REPOSITORY
            and image.get("imageId", {}).get("imageTag") == tag_name
            and image.get("imageId", {}).get("imageDigest") == digest
            and manifest.get("schemaVersion") == 2
            and manifest.get("mediaType")
            in {
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.v2+json",
            }
            and manifest.get("config", {}).get("digest") == self.report["config_digest"],
            "Published manifest does not match the built image",
        )
        self.report.update(image_uri=URI + "@" + digest, image_digest=digest, image_published=True)
        return digest

    def scan(self, digest):
        args = [
            "--registry-id",
            ACCOUNT,
            "--repository-name",
            REPOSITORY,
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
        self.report["severity_counts"] = scan_policy(pages, digest, datetime.now(UTC))
        self.report["scan_policy_passed"] = True

    def run(self):
        files = self.source()
        self.identity()
        name = f"commit-{self.report['revision']}-{os.environ['GITHUB_RUN_ID']}"
        tag = f"{URI}:{name}-{os.environ['GITHUB_RUN_ATTEMPT']}"
        self.report["image_tag"] = tag
        with tempfile.TemporaryDirectory(prefix="fitfinity-image-") as directory:
            folder = Path(directory)
            self.build(files, folder, tag)
            # Verify the source again before the first publication attempt.
            require(files == self.source(), "Source changed during runtime build")
            digest = self.publish(folder, tag)
            self.scan(digest)
        self.report["candidate_ready"] = True


def create_candidate(receipt):
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "account": ACCOUNT,
        "region": REGION,
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
            ImageCandidate(report).run()
        except Exception as error:
            report["failure_type"] = type(error).__name__
            raise
        finally:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    print("PASS — image candidate built, published and scanned. Live deployment remains pending.")
