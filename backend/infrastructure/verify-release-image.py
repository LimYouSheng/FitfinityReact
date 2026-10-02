"""Current image publication boundaries; all Git, Docker and AWS operations are simulated."""

import hashlib
import json
import os
import tempfile
import unittest
from datetime import UTC, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import release_image as image
from operator_support import load_operator

ROOT = Path(__file__).resolve().parent


class ImageReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "backend").mkdir()
        (self.root / "backend/Dockerfile").write_text("FROM fixture\n")
        self.revision = "a" * 40
        self.config = "sha256:" + "b" * 64
        self.manifest = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {"digest": self.config},
                "layers": [],
            }
        )
        self.digest = "sha256:" + image.sha(self.manifest.encode())
        self.now = image.datetime.now(UTC)
        self.report = {"cloud_write_attempts": []}
        self.op = image.ImageCandidate(self.report, self.root)
        self.calls = []
        self.env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "LimYouSheng/FitfinityReact",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": self.revision,
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "AWS_ACCESS_KEY_ID": "fixture",
            "AWS_SECRET_ACCESS_KEY": "fixture",
            "AWS_SESSION_TOKEN": "fixture",
        }
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.patch = patch.object(self.op, "command", side_effect=self.command)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.published = False

    def page(self, counts=None, findings=None):
        return {
            "registryId": image.ACCOUNT,
            "repositoryName": image.REPOSITORY,
            "imageId": {"imageDigest": self.digest},
            "imageScanStatus": {"status": "COMPLETE"},
            "imageScanFindings": {
                "imageScanCompletedAt": self.now.isoformat(),
                "findingSeverityCounts": counts or {},
                "findings": findings or [],
            },
        }

    def command(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return self.revision
        if args[:2] == ["git", "status"]:
            return ""
        if args[:2] == ["git", "ls-tree"]:
            data = b"FROM fixture\n"
            blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            return f"100644 blob {blob}\tbackend/Dockerfile\0"
        if args[:3] == ["docker", "buildx", "build"]:
            self.assertEqual((Path(args[-1]) / "Dockerfile").read_text(), "FROM fixture\n")
            self.assertFalse((Path(args[-1]) / "secret.env").exists())
            return ""
        if args[:3] == ["docker", "image", "inspect"]:
            return json.dumps(
                [
                    {
                        "Id": self.config,
                        "Os": "linux",
                        "Architecture": "amd64",
                        "Config": {
                            "User": "10001:10001",
                            "Labels": {
                                "org.opencontainers.image.revision": self.revision,
                                "ai.app404.fitfinity.source-sha256": self.report["source_sha256"],
                            },
                        },
                    }
                ]
            )
        if args[0] == "docker" and "login" in args:
            self.assertEqual(kwargs["input_data"], "private-token")
            self.assertEqual(Path(args[2]).stat().st_mode & 0o777, 0o700)
            return ""
        if args[0] == "docker" and "push" in args:
            self.published = True
            self.tag = args[-1].split(":")[-1]
            return ""
        self.assertEqual(args[0], "aws")
        self.assertTrue(kwargs["private"])
        self.assertNotIn("--profile", args)
        self.assertEqual(args[args.index("--region") + 1], image.REGION)
        operation = args[2]
        if operation == "get-caller-identity":
            result = {
                "Account": image.ACCOUNT,
                "Arn": f"arn:aws:sts::{image.ACCOUNT}:assumed-role/fitfinity-test-github-image/run",
            }
        elif operation == "describe-repositories":
            result = {
                "repositories": [
                    {
                        "registryId": image.ACCOUNT,
                        "repositoryName": image.REPOSITORY,
                        "repositoryArn": image.ARN,
                        "repositoryUri": image.URI,
                        "imageTagMutability": "IMMUTABLE",
                        "encryptionConfiguration": {"encryptionType": "AES256"},
                    }
                ]
            }
        elif operation == "list-tags-for-resource":
            result = {
                "tags": [
                    {"Key": key, "Value": value}
                    for key, value in {
                        "Application": "Fitfinity",
                        "Environment": "test",
                        "ManagedBy": "fitfinity-test-image-uploader",
                    }.items()
                ]
            }
        elif operation == "get-registry-scanning-configuration":
            result = {"registryId": image.ACCOUNT, "scanningConfiguration": {"scanType": "BASIC"}}
        elif operation == "get-login-password":
            return "private-token"
        elif operation == "batch-get-image":
            result = (
                {
                    "images": [
                        {
                            "registryId": image.ACCOUNT,
                            "repositoryName": image.REPOSITORY,
                            "imageId": {"imageDigest": self.digest, "imageTag": self.tag},
                            "imageManifest": self.manifest,
                        }
                    ],
                    "failures": [],
                }
                if self.published
                else {"images": [], "failures": [{"failureCode": "ImageNotFound"}]}
            )
        elif operation == "describe-image-scan-findings":
            result = self.page()
        else:
            raise AssertionError(args)
        return json.dumps(result)

    def test_complete_candidate_has_exact_source_digest_and_no_deployment_claim(self):
        (self.root / "backend/secret.env").write_text("must not enter build context")
        self.op.run()
        self.assertTrue(self.report["candidate_ready"])
        self.assertEqual(self.report["image_uri"], image.URI + "@" + self.digest)
        self.assertEqual(self.report["cloud_write_attempts"], ["publish-image"])
        self.assertNotIn("application_deployed", self.report)
        builds = [args for args, _ in self.calls if args[:3] == ["docker", "buildx", "build"]]
        self.assertEqual(len(builds), 1)
        for flag in ("--pull", "--no-cache", "--provenance=false", "--sbom=false", "--load"):
            self.assertIn(flag, builds[0])

    def test_source_refuses_pull_requests_forks_other_branches_and_invalid_sha(self):
        for key, value in [
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_REPOSITORY", "other/repo"),
            ("GITHUB_REF", "refs/heads/other"),
            ("GITHUB_SHA", "bad"),
        ]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                with self.assertRaises(RuntimeError):
                    self.op.source()
        self.assertFalse(self.calls)

    def test_source_refuses_dirty_or_different_commit(self):
        for outputs in [["b" * 40], [self.revision, "?? changed"]]:
            with patch.object(self.op, "command", side_effect=outputs):
                with self.assertRaisesRegex(RuntimeError, "exact clean"):
                    self.op.source()

    def test_source_checks_committed_bytes_even_when_git_status_is_clean(self):
        (self.root / "backend/Dockerfile").write_text("uncommitted")
        with self.assertRaisesRegex(RuntimeError, "bytes differ"):
            self.op.source()

    def test_source_refuses_symlinks(self):
        target = self.root / "elsewhere"
        target.write_text("FROM fixture\n")
        (self.root / "backend/Dockerfile").unlink()
        (self.root / "backend/Dockerfile").symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "Redirected"):
            self.op.source()

    def test_identity_refuses_overrides_before_cloud_access(self):
        for key in ["AWS_PROFILE", "AWS_CA_BUNDLE", "AWS_ENDPOINT_URL_ECR", "DOCKER_HOST"]:
            with self.subTest(key=key), patch.dict(os.environ, {key: "unexpected"}):
                with self.assertRaises(RuntimeError):
                    self.op.identity()
        self.assertFalse(self.calls)

    def test_identity_requires_temporary_credentials(self):
        with patch.dict(os.environ, {"AWS_SESSION_TOKEN": ""}):
            with self.assertRaisesRegex(RuntimeError, "Temporary"):
                self.op.identity()
        self.assertFalse(self.calls)

    def test_identity_refuses_other_account_role_and_local_user(self):
        for row in [
            {"Account": "0" * 12, "Arn": "wrong"},
            {"Account": image.ACCOUNT, "Arn": image.ROLE},
            {
                "Account": image.ACCOUNT,
                "Arn": f"arn:aws:sts::{image.ACCOUNT}:"
                "assumed-role/fitfinity-test-github-verify/run",
            },
        ]:
            with self.subTest(row=row), patch.object(self.op, "aws", return_value=row):
                with self.assertRaisesRegex(RuntimeError, "principal"):
                    self.op.identity()

    def test_repository_drift_stops_before_build_and_publication(self):
        original = self.command
        for field, value in [("repositoryUri", "other"), ("imageTagMutability", "MUTABLE")]:

            def changed(args, field=field, value=value, **kwargs):
                result = original(args, **kwargs)
                if args[:3] == ["aws", "ecr", "describe-repositories"]:
                    data = json.loads(result)
                    data["repositories"][0][field] = value
                    return json.dumps(data)
                return result

            with self.subTest(field=field), patch.object(self.op, "command", side_effect=changed):
                with self.assertRaisesRegex(RuntimeError, "configuration differs"):
                    self.op.run()
        self.assertFalse(self.report["cloud_write_attempts"])

    def test_operator_refuses_unrelated_operations(self):
        for pair in [
            ("lambda", "update-function-code"),
            ("secretsmanager", "get-secret-value"),
            ("ecr", "delete-repository"),
            ("iam", "create-role"),
        ]:
            with self.subTest(pair=pair), self.assertRaises(RuntimeError):
                self.op.aws(*pair)
        self.assertFalse(self.calls)

    def test_source_changed_after_build_cannot_be_published(self):
        def changed(*args):
            (self.root / "backend/Dockerfile").write_text("changed")

        with patch.object(self.op, "build", side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, "bytes differ"):
                self.op.run()
        self.assertFalse(self.report["cloud_write_attempts"])

    def test_occupied_tag_is_never_overwritten(self):
        with patch.object(self.op, "aws", return_value={"images": [{}]}):
            with self.assertRaisesRegex(RuntimeError, "occupied"):
                self.op.publish(self.root, image.URI + ":occupied")
        self.assertFalse(self.report["cloud_write_attempts"])

    def test_published_manifest_must_match_built_configuration(self):
        self.config = "sha256:" + "c" * 64
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            self.op.run()
        self.assertNotIn("candidate_ready", self.report)
        self.assertEqual(self.report["cloud_write_attempts"], ["publish-image"])

    def test_paginated_scan_matches_complete_counts(self):
        rows = [{"name": "CVE-fixture", "severity": "MEDIUM"}]
        first = self.page({"MEDIUM": 1}, [])
        first["nextToken"] = "page2"
        second = self.page({"MEDIUM": 1}, rows)
        self.assertEqual(image.scan_policy([first, second], self.digest, self.now), {"MEDIUM": 1})

    def test_scan_blocks_critical_high_and_unclassified_findings(self):
        for level in ["CRITICAL", "HIGH", "UNDEFINED"]:
            with self.subTest(level=level), self.assertRaisesRegex(RuntimeError, "blocked"):
                image.scan_policy(
                    [self.page({level: 1}, [{"severity": level}])], self.digest, self.now
                )

    def test_scan_refuses_stale_future_and_naive_timestamps(self):
        for stamp in [
            (self.now - timedelta(hours=25)).isoformat(),
            (self.now + timedelta(seconds=1)).isoformat(),
            self.now.replace(tzinfo=None).isoformat(),
            None,
        ]:
            page = self.page()
            page["imageScanFindings"]["imageScanCompletedAt"] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(RuntimeError):
                image.scan_policy([page], self.digest, self.now)

    def test_scan_identity_and_status_must_match(self):
        for key, value in [
            ("registryId", "other"),
            ("repositoryName", "other"),
            ("imageId", {"imageDigest": "other"}),
            ("imageScanStatus", {"status": "FAILED"}),
        ]:
            page = self.page()
            page[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                image.scan_policy([page], self.digest, self.now)

    def test_scan_refuses_truncation_repeated_pages_and_count_mismatch(self):
        page = self.page()
        page["nextToken"] = "again"
        for pages in [[page], [page, page, self.page()], [self.page({"MEDIUM": 1}, [])]]:
            with self.subTest(pages=pages), self.assertRaises(RuntimeError):
                image.scan_policy(pages, self.digest, self.now)

    def test_scan_refuses_changed_evidence_between_pages(self):
        page = self.page()
        page["nextToken"] = "next"
        other = self.page()
        other["imageScanFindings"]["imageScanCompletedAt"] = (
            self.now - timedelta(seconds=1)
        ).isoformat()
        with self.assertRaisesRegex(RuntimeError, "changed during"):
            image.scan_policy([page, other], self.digest, self.now)

    def test_scan_rejects_malformed_counts_and_findings(self):
        for field, value in [
            ("findingSeverityCounts", {"OTHER": 1}),
            ("findingSeverityCounts", {"HIGH": True}),
            ("findingSeverityCounts", {"HIGH": -1}),
            ("findings", None),
            ("findings", [{"severity": "OTHER"}]),
        ]:
            page = self.page()
            page["imageScanFindings"][field] = value
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                image.scan_policy([page], self.digest, self.now)

    def test_scan_on_push_is_reused_without_duplicate_scan_request(self):
        with patch.object(self.op, "aws", return_value=self.page()) as aws:
            self.op.scan(self.digest)
        self.assertEqual(aws.call_count, 1)
        self.assertFalse(self.report["cloud_write_attempts"])

    def test_missing_scan_starts_once_and_handles_concurrent_scan_limit(self):
        for started in [{}, image.AWSFailure("LimitExceededException")]:
            with (
                patch.object(
                    self.op,
                    "aws",
                    side_effect=[
                        image.AWSFailure("ScanNotFoundException"),
                        started,
                        self.page(),
                    ],
                ) as aws,
                patch.object(image.time, "sleep"),
            ):
                self.op.scan(self.digest)
            self.assertEqual(
                [call.args[1] for call in aws.call_args_list],
                [
                    "describe-image-scan-findings",
                    "start-image-scan",
                    "describe-image-scan-findings",
                ],
            )

    def test_scan_wait_is_bounded_and_failure_never_becomes_ready(self):
        with (
            patch.object(
                self.op,
                "aws",
                return_value={
                    "imageScanStatus": {"status": "IN_PROGRESS"},
                },
            ) as aws,
            patch.object(image.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "five minutes"):
                self.op.scan(self.digest)
        self.assertEqual(aws.call_count, 31)
        self.assertEqual(sleep.call_count, 30)
        self.assertNotIn("scan_policy_passed", self.report)

    def test_scan_denial_is_not_treated_as_missing(self):
        with patch.object(self.op, "aws", side_effect=image.AWSFailure("AccessDeniedException")):
            with self.assertRaisesRegex(RuntimeError, "Cannot read"):
                self.op.scan(self.digest)
        self.assertFalse(self.report["cloud_write_attempts"])

    def test_scan_pagination_retrieves_each_token_and_keeps_full_evidence(self):
        first = self.page()
        first["nextToken"] = "page2"
        with patch.object(self.op, "aws", side_effect=[first, self.page()]) as aws:
            self.op.scan(self.digest)
        self.assertEqual(aws.call_args.args[-2:], ("--next-token", "page2"))
        self.assertEqual(len(self.report["scan_pages"]), 2)

    def test_private_failures_do_not_echo_provider_tokens(self):
        op = image.ImageCandidate({}, self.root)
        result = SimpleNamespace(
            returncode=1,
            stdout="private-token",
            stderr="An error occurred (AccessDeniedException): private-token",
        )
        with patch.object(image.subprocess, "run", return_value=result):
            with self.assertRaises(image.AWSFailure) as caught:
                op.aws("sts", "get-caller-identity")
        self.assertNotIn("private-token", str(caught.exception))
        self.assertEqual(caught.exception.code, "AccessDeniedException")

    def test_failure_receipt_records_attempts_without_claiming_deployment(self):
        target = self.root / "receipt.json"

        def failed(candidate):
            candidate.report["cloud_write_attempts"].append("publish-image")
            raise RuntimeError("private material must not enter receipt")

        with patch.object(image.ImageCandidate, "run", failed):
            with self.assertRaises(RuntimeError):
                image.create_candidate(target)
        report = json.loads(target.read_text())
        self.assertFalse(report["candidate_ready"])
        self.assertFalse(report["application_deployed"])
        self.assertFalse(report["live_authentication_accepted"])
        self.assertEqual(report["cloud_write_attempts"], ["publish-image"])
        self.assertNotIn("private material", target.read_text())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_receipt_refuses_overwrite_and_symlink_before_operations(self):
        target = self.root / "receipt.json"
        target.write_text("preserve")
        link = self.root / "link.json"
        link.symlink_to(target)
        with patch.object(image.ImageCandidate, "run") as run:
            for path in [target, link]:
                with self.assertRaises(FileExistsError):
                    image.create_candidate(path)
            run.assert_not_called()
        self.assertEqual(target.read_text(), "preserve")

    def test_cli_requires_actions_and_receipt_and_preserves_full_deploy_block(self):
        op = load_operator("deploy.py")
        with patch.object(image, "create_candidate") as candidate:
            for args in [["image-candidate"], ["image-candidate", "--actions"], ["deploy"]]:
                with self.subTest(args=args), self.assertRaises(RuntimeError):
                    op.main(args)
            candidate.assert_not_called()
            op.main(["image-candidate", "--actions", "--receipt", "new.json"])
            candidate.assert_called_once_with("new.json")

    def test_image_role_is_separate_and_cannot_deploy_or_read_application_secrets(self):
        template = json.loads((ROOT / "test-github-image-role.json").read_text())
        properties = template["Resources"]["ImageRole"]["Properties"]
        self.assertEqual(properties["RoleName"], "fitfinity-test-github-image")
        trust = properties["AssumeRolePolicyDocument"]["Statement"][0]
        self.assertEqual(
            trust["Condition"]["StringEquals"],
            {
                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                "token.actions.githubusercontent.com:sub": {"Ref": "GitHubSubject"},
            },
        )
        statements = properties["Policies"][0]["PolicyDocument"]["Statement"]
        for statement in statements:
            for action in statement["Action"]:
                self.assertTrue(action.startswith("ecr:"))
                self.assertNotIn(
                    action,
                    [
                        "ecr:DeleteRepository",
                        "ecr:BatchDeleteImage",
                        "ecr:CreateRepository",
                        "ecr:SetRepositoryPolicy",
                    ],
                )
            self.assertEqual(
                statement["Resource"],
                "*" if "ecr:GetAuthorizationToken" in statement["Action"] else image.ARN,
            )
        historical = json.loads((ROOT / "test-github-verification-role.json").read_text())
        self.assertNotEqual(template, historical)
