import builtins
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_support import partial

ROOT = Path(__file__).resolve().parent

SCRIPT = ROOT / "test-image-publish.py"
SOURCE = SCRIPT.read_text()
ACCOUNT = "418638389566"
DIGEST = "sha256:efa53edd08c54786bb7e04cc2509b6ace31ff903d1a2c473f203548b2e4d6d12"


def case(
    name,
    *,
    uploaded=False,
    fault=None,
    scans=("COMPLETE",),
    error=None,
    expected_writes=None,
    expected_prompts=None,
    start_fault=None,
    overrides=None,
):
    ns = {"__file__": str(SCRIPT), "__name__": "operator"}
    exec(compile(SOURCE, str(SCRIPT), "exec"), ns)
    ns["SCAN_ATTEMPTS"] = 3
    assert ns["ACCOUNT"] == ACCOUNT and ns["EXPECTED"] == DIGEST
    calls, writes, sleeps, prompts = [], [], [], []
    state = {"uploaded": uploaded, "scan_reads": 0}
    uri = f"{ACCOUNT}.dkr.ecr.ap-southeast-1.amazonaws.com/fitfinity-test-api"
    repository = {
        "registryId": ACCOUNT,
        "repositoryName": "fitfinity-test-api",
        "repositoryUri": uri,
        "repositoryArn": f"arn:aws:ecr:ap-southeast-1:{ACCOUNT}:repository/fitfinity-test-api",
        "imageTagMutability": "IMMUTABLE",
        "encryptionConfiguration": {"encryptionType": "AES256"},
    }
    if fault == "repository":
        repository["repositoryUri"] = "wrong"
    if fault == "mutable":
        repository["imageTagMutability"] = "MUTABLE"
    if fault == "encryption":
        repository["encryptionConfiguration"]["encryptionType"] = "KMS"

    def scan_response(status):
        return {
            "registryId": "000000000000" if fault == "scan_account" else ACCOUNT,
            "repositoryName": "other" if fault == "scan_repository" else "fitfinity-test-api",
            "imageId": {"imageDigest": "sha256:" + "a" * 64 if fault == "scan_digest" else DIGEST},
            "imageScanStatus": {"status": status},
            "imageScanFindings": {
                "findingSeverityCounts": {"HIGH": 1},
                "findings": [{"name": "test-finding", "severity": "HIGH"}],
            },
        }

    def command(args, capture=True, input_data=None, env=None):
        calls.append(args)
        out, err, code = "", "", 0
        if args[0] == "aws":
            assert "--profile" in args and args[args.index("--profile") + 1] == "fitfinity-test"
            assert "--region" in args and args[args.index("--region") + 1] == "ap-southeast-1"
            assert "--no-verify-ssl" not in args and "--endpoint-url" not in args
            op = args[2]
            if op == "get-caller-identity":
                account = "123456789012" if fault == "account" else ACCOUNT
                out = {
                    "Account": account,
                    "Arn": f"arn:aws:iam::{account}:"
                    + ("root" if fault == "root" else "user/fitfinity-deployer"),
                }
            elif op == "describe-repositories":
                if fault in ("missing_repository", "denied"):
                    code = 1
                    err = (
                        "(RepositoryNotFoundException)"
                        if fault == "missing_repository"
                        else "(AccessDeniedException)"
                    )
                else:
                    out = {"repositories": [repository]}
            elif op == "list-tags-for-resource":
                tags = {"Application": "Fitfinity", "Environment": "test", "ManagedBy": ns["OWNER"]}
                if fault == "owner":
                    tags["ManagedBy"] = "other"
                out = {"tags": [{"Key": key, "Value": value} for key, value in tags.items()]}
            elif op == "get-registry-scanning-configuration":
                out = {
                    "registryId": ACCOUNT,
                    "scanningConfiguration": {
                        "scanType": "ENHANCED" if fault == "scan_mode" else "BASIC"
                    },
                }
            elif op == "describe-images":
                if state["uploaded"]:
                    out = {"imageDetails": [{"imageDigest": DIGEST}]}
                else:
                    code, err = 1, "(ImageNotFoundException)"
            elif op == "batch-get-image":
                out = {
                    "images": [
                        {
                            "imageId": {
                                "imageDigest": "sha256:" + "a" * 64
                                if fault == "remote_digest"
                                else DIGEST
                            },
                            "imageManifest": json.dumps(
                                {"config": {"digest": "sha256:" + "b" * 64}}
                            ),
                        }
                    ]
                }
            elif op == "get-login-password":
                out = "FAKE_EPHEMERAL_PASSWORD\n"
            elif op == "describe-image-scan-findings":
                assert args[args.index("--image-id") + 1] == "imageDigest=" + DIGEST
                assert "--no-paginate" not in args and "--max-items" not in args
                status = scans[min(state["scan_reads"], len(scans) - 1)]
                state["scan_reads"] += 1
                if status in ("MISSING", "DENIED"):
                    code, err = (
                        1,
                        "(ScanNotFoundException)"
                        if status == "MISSING"
                        else "(AccessDeniedException)",
                    )
                else:
                    out = scan_response(status)
                    if fault == "truncated":
                        out["nextToken"] = "more"
            elif op == "start-image-scan":
                assert args[args.index("--image-id") + 1] == "imageDigest=" + DIGEST
                writes.append("start_scan")
                if start_fault in ("limit", "denied"):
                    code, err = (
                        1,
                        "(LimitExceededException)"
                        if start_fault == "limit"
                        else "(AccessDeniedException)",
                    )
                else:
                    out = scan_response("IN_PROGRESS")
                    if start_fault == "digest":
                        out["imageId"]["imageDigest"] = "sha256:" + "c" * 64
            else:
                raise AssertionError("Unexpected AWS operation: " + op)
        else:
            assert args[0] == "docker"
            if args[1:3] == ["image", "inspect"]:
                assert args[-1] == "fitfinity-api:admin-access"
                out = [
                    {
                        "Id": "wrong" if fault == "image" else DIGEST,
                        "Created": "wrong" if fault == "created" else ns["EXPECTED_CREATED"],
                        "Os": "windows" if fault == "os" else "linux",
                        "Architecture": "arm64" if fault == "architecture" else "amd64",
                    }
                ]
            elif args[1:3] == ["context", "show"]:
                out = "desktop-linux"
            elif args[1:3] == ["context", "inspect"]:
                out = "tcp://remote" if fault == "remote_engine" else "unix:///tmp/docker.sock"
            elif "login" in args:
                assert input_data == "FAKE_EPHEMERAL_PASSWORD\n"
                assert Path(args[2]).is_dir() and env["DOCKER_CONFIG"] == args[2]
                out = "Login Succeeded"
            elif args[1] == "tag":
                assert args[2] == DIGEST and args[3] == uri + ":manifest-" + DIGEST[7:]
                writes.append("local_tag")
            elif "push" in args:
                assert (
                    "--host" in args and args[args.index("--host") + 1] == "unix:///tmp/docker.sock"
                )
                assert Path(env["DOCKER_CONFIG"]).is_dir()
                writes.append("push")
                if fault == "push":
                    code = 1
                else:
                    state["uploaded"] = True
            else:
                raise AssertionError(args)
        return subprocess.CompletedProcess(
            args, code, out if isinstance(out, str) else json.dumps(out), err
        )

    original_open = builtins.open

    def opened(path, mode="r", *args, **kwargs):
        if path == "/dev/tty":
            if mode == "w":
                prompts.append(True)
            return io.StringIO(("incorrect" if fault == "confirmation" else ACCOUNT) + "\n")
        return original_open(path, mode, *args, **kwargs)

    ns["command"] = command
    stdout, stderr = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory(prefix="fitfinity-ecr-check-") as work:
        with (
            patch.dict(os.environ, overrides or {}, clear=True),
            patch.object(sys, "argv", ["operator"]),
            patch("shutil.which", return_value="/mock/tool"),
            patch("builtins.open", side_effect=opened),
            patch("os.path.expanduser", return_value=work),
            patch("time.sleep", side_effect=sleeps.append),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                ns["main"]()
            except RuntimeError as exc:
                assert error and error in str(exc), (name, str(exc), error)
            else:
                assert error is None, (name, error)
        reports = list((Path(work) / "Downloads").glob("*.json"))
        for report in reports:
            assert stat.S_IMODE(report.stat().st_mode) == 0o600
            data = json.loads(report.read_text())
            assert data["imageId"]["imageDigest"] == DIGEST
            assert data["registryId"] == ACCOUNT
            assert data["imageScanFindings"]["findings"][0]["name"] == "test-finding"
            assert "FAKE_EPHEMERAL_PASSWORD" not in report.read_text()
        if (
            error is None
            or scans[-1] in ("IN_PROGRESS", "FAILED", "UNSUPPORTED_IMAGE")
            and fault is None
        ):
            assert len(reports) == 1, name
    assert writes == (expected_writes or []), (name, writes, expected_writes)
    if expected_prompts is not None:
        assert len(prompts) == expected_prompts, (name, prompts)
    assert "FAKE_EPHEMERAL_PASSWORD" not in stdout.getvalue() + stderr.getvalue()
    assert all(
        not Path(args[args.index("--config") + 1]).exists() for args in calls if "--config" in args
    )
    assert writes.count("start_scan") <= 1
    assert len(sleeps) <= 2
    if (
        state["uploaded"]
        and any(args[:3] == ["aws", "ecr", "batch-get-image"] for args in calls)
        and fault != "remote_digest"
    ):
        assert ns["UPLOAD_VERIFIED"]
    print("PASS — " + name)


SCENARIOS = []
run_case = case


def case(name, **kwargs):
    SCENARIOS.append((name, partial(run_case, name, **kwargs)))


case(
    "new Admin upload, automatic complete scan",
    expected_writes=["local_tag", "push"],
    expected_prompts=1,
)
case("verified rerun performs no cloud writes or confirmation", uploaded=True, expected_prompts=0)
case(
    "absent scan starts once after upload then completes",
    scans=("MISSING", "IN_PROGRESS", "COMPLETE"),
    expected_writes=["local_tag", "push", "start_scan"],
    expected_prompts=1,
)
case(
    "already uploaded image starts missing scan without re-upload",
    uploaded=True,
    scans=("MISSING", "COMPLETE"),
    expected_writes=["start_scan"],
    expected_prompts=1,
)
case(
    "scan-on-push limit race resolves through reads only",
    uploaded=True,
    scans=("MISSING", "COMPLETE"),
    start_fault="limit",
    expected_writes=["start_scan"],
)
case(
    "scan limit with no report stops without claiming acceptance",
    uploaded=True,
    scans=("MISSING",),
    start_fault="limit",
    error="no scan report",
    expected_writes=["start_scan"],
)
case(
    "scan permission denial preserves verified image",
    uploaded=True,
    scans=("DENIED",),
    error="AccessDeniedException",
)
case(
    "scan start denial preserves verified image",
    uploaded=True,
    scans=("MISSING",),
    start_fault="denied",
    error="AccessDeniedException",
    expected_writes=["start_scan"],
)
case(
    "scan start response must match digest",
    uploaded=True,
    scans=("MISSING",),
    start_fault="digest",
    error="Scan response",
    expected_writes=["start_scan"],
)
case(
    "pending scan saves evidence and stops after bounded reads",
    uploaded=True,
    scans=("IN_PROGRESS",),
    error="Scan status is IN_PROGRESS",
)
case(
    "unsupported image saves report and does not pass",
    uploaded=True,
    scans=("UNSUPPORTED_IMAGE",),
    error="Scan status is UNSUPPORTED_IMAGE",
)
case(
    "failed scan saves report and does not pass",
    uploaded=True,
    scans=("FAILED",),
    error="Scan status is FAILED",
)
for fault, message in [
    ("account", "Expected AWS test account"),
    ("root", "Expected the fitfinity-deployer"),
    ("image", "Local image differs"),
    ("created", "creation time differs"),
    ("os", "linux/amd64"),
    ("architecture", "linux/amd64"),
    ("remote_engine", "local Docker Desktop"),
    ("missing_repository", "repository is missing"),
    ("denied", "AccessDeniedException"),
    ("repository", "repository configuration differs"),
    ("mutable", "repository configuration differs"),
    ("encryption", "repository configuration differs"),
    ("owner", "ownership tags differ"),
    ("scan_mode", "Expected basic ECR scanning"),
    ("confirmation", "confirmation did not match"),
]:
    case("pre-write refusal: " + fault, fault=fault, error=message)
case(
    "conflicting remote digest refuses overwrite",
    uploaded=True,
    fault="remote_digest",
    error="Remote tag does not reference",
)
for fault in ("scan_account", "scan_repository", "scan_digest"):
    case("scan identity refusal: " + fault, uploaded=True, fault=fault, error="Scan response")
case("truncated findings refused", uploaded=True, fault="truncated", error="findings are truncated")
case(
    "push failure cleans temporary Docker credentials",
    fault="push",
    error="Command failed",
    expected_writes=["local_tag", "push"],
)
case(
    "credential override blocked before AWS calls",
    overrides={"AWS_ACCESS_KEY_ID": "fake"},
    error="Unset AWS_ACCESS_KEY_ID",
)
case(
    "endpoint override blocked before AWS calls",
    overrides={"AWS_ENDPOINT_URL_ECR": "https://wrong.invalid"},
    error="Unset AWS_ENDPOINT_URL_ECR",
)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(fn, description=name) for name, fn in SCENARIOS
    )
