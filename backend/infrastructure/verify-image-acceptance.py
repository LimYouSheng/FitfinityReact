"""Existing-image TEST policy, provenance and read-only execution regression checks."""

import io
import json
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import image_acceptance as accept
import release_image as image
from operator_support import load_operator


class AcceptanceChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.revision, self.policy_revision = "a" * 40, "b" * 40
        self.config = "sha256:" + "c" * 64
        self.raw = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {"digest": self.config},
            }
        )
        self.digest = "sha256:" + image.sha(self.raw.encode())
        self.now = datetime.now(UTC)
        self.manifest = {"backend/Dockerfile": image.sha(b"FROM fixture\n")}
        self.fingerprint = image.sha(
            json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode()
        )
        self.candidate = {
            "account": image.ACCOUNT,
            "region": image.REGION,
            "revision": self.revision,
            "image_digest": self.digest,
            "image_uri": image.URI + "@" + self.digest,
            "image_tag": f"{image.URI}:commit-{self.revision}-123-1",
            "config_digest": self.config,
            "runtime_build_complete": True,
            "image_published": True,
            "source_files": self.manifest,
            "source_sha256": self.fingerprint,
        }
        self.archive = io.BytesIO()
        with zipfile.ZipFile(self.archive, "w") as zipped:
            zipped.writestr("fitfinity-image-candidate.json", json.dumps(self.candidate))
        self.archive = self.archive.getvalue()
        self.provenance = {
            "source_revision": self.revision,
            "source_sha256": self.fingerprint,
            "run_id": 123,
            "run_attempt": 1,
            "artifact_id": 456,
            "artifact_sha256": image.sha(self.archive),
        }
        self.run = {
            "id": 123,
            "run_attempt": 1,
            "head_sha": self.revision,
            "head_branch": "main",
            "event": "push",
            "path": ".github/workflows/pages.yml",
            "status": "completed",
            "repository": {"full_name": accept.GITHUB_REPO},
            "head_repository": {"full_name": accept.GITHUB_REPO},
        }
        self.jobs = {
            "total_count": 3,
            "jobs": [
                {"name": "verify / frontend", "conclusion": "success"},
                {"name": "verify / backend", "conclusion": "success"},
                {"name": "image / image", "conclusion": "failure"},
            ],
        }
        self.artifact = {
            "id": 456,
            "expired": False,
            "name": "fitfinity-image-candidate-123-1",
            "workflow_run": {"id": 123, "head_sha": self.revision},
            "digest": "sha256:" + image.sha(self.archive),
        }
        self.finding = {
            "name": "CVE-2026-85091",
            "severity": "HIGH",
            "attributes": [
                {"key": "package_name", "value": "zlib"},
                {"key": "package_version", "value": "1.3"},
            ],
        }
        self.page = {
            "registryId": image.ACCOUNT,
            "repositoryName": image.REPOSITORY,
            "imageId": {"imageDigest": self.digest},
            "imageScanStatus": {"status": "COMPLETE"},
            "imageScanFindings": {
                "imageScanCompletedAt": self.now.isoformat(),
                "findingSeverityCounts": {"HIGH": 1},
                "findings": [self.finding],
            },
        }
        self.approval = {
            "id": "TEST-REVIEW",
            "status": "approved",
            "approval_reference": f"https://github.com/{accept.GITHUB_REPO}/pull/10",
            "approver": "LimYouSheng",
            "reason": "Explicit synthetic test review",
            "approved_at": (self.now - timedelta(hours=1)).isoformat(),
            "expires_at": (self.now + timedelta(hours=1)).isoformat(),
            "account": image.ACCOUNT,
            "region": image.REGION,
            "repository": image.REPOSITORY,
            "environment": "test",
            "image_digest": self.digest,
            "provenance": self.provenance,
            "findings": [accept.finding_identity(self.finding)],
        }
        self.report = {
            "revision": self.policy_revision,
            "cloud_write_attempts": [],
            "scan_policy_passed": False,
            "application_deployed": False,
            "live_authentication_accepted": False,
        }
        self.op = accept.ExistingImage(self.report, self.root)

    def decision(self, approval=True):
        return accept.acceptance(
            [self.page], self.digest, self.provenance, self.approval if approval else None, self.now
        )

    def github(self, path, **kwargs):
        if path.endswith("/zip"):
            return self.archive
        if "/jobs?" in path:
            return self.jobs
        if "/artifacts/" in path:
            return self.artifact
        return self.run

    def command(self, args, **kwargs):
        if args[1] == "ls-tree":
            return "100644 blob fixture\tbackend/Dockerfile\0"
        self.assertEqual(args[:3], ["git", "merge-base", "--is-ancestor"])
        return ""

    def trusted(self):
        with (
            patch.object(self.op, "github", side_effect=self.github),
            patch.object(self.op, "command", side_effect=self.command),
            patch("subprocess.run", return_value=SimpleNamespace(stdout=b"FROM fixture\n")),
        ):
            return self.op.trusted_candidate(123, 1, 456, self.digest)

    def test_clean_strict_acceptance(self):
        self.page["imageScanFindings"].update(findingSeverityCounts={}, findings=[])
        self.assertEqual(self.decision(False)[0], "strict_policy_passed")

    def test_exact_high_exception_is_distinct_from_clean_scan(self):
        self.assertEqual(self.decision()[0], "accepted_with_test_exception")
        with self.assertRaises(RuntimeError):
            image.scan_policy([self.page], self.digest, self.now)

    def test_unapproved_high_stays_blocked(self):
        with self.assertRaises(RuntimeError):
            self.decision(False)

    def test_expired_future_revoked_and_missing_metadata_fail(self):
        for key, value in [
            ("expires_at", self.now.isoformat()),
            ("approved_at", (self.now + timedelta(seconds=1)).isoformat()),
            ("status", "revoked"),
            ("reason", ""),
            ("approval_reference", None),
            ("approver", "other"),
        ]:
            with (
                self.subTest(key=key),
                patch.dict(self.approval, {key: value}),
                self.assertRaises(RuntimeError),
            ):
                self.decision()

    def test_exact_scope_does_not_transfer(self):
        for key in ("account", "region", "repository", "environment", "image_digest", "provenance"):
            with (
                self.subTest(key=key),
                patch.dict(self.approval, {key: "*"}),
                self.assertRaises(RuntimeError),
            ):
                self.decision()

    def test_new_changed_or_disappeared_finding_requires_review(self):
        for findings in (
            [],
            [{**self.approval["findings"][0], "version": "2"}],
            self.approval["findings"] * 2,
        ):
            with (
                self.subTest(findings=findings),
                patch.dict(self.approval, {"findings": findings}),
                self.assertRaises(RuntimeError),
            ):
                self.decision()

    def test_critical_and_unclassified_never_excepted(self):
        for severity in ("CRITICAL", "UNDEFINED", "UNKNOWN"):
            with (
                self.subTest(severity=severity),
                patch.dict(self.finding, {"severity": severity}),
                patch.dict(
                    self.page["imageScanFindings"], {"findingSeverityCounts": {severity: 1}}
                ),
                self.assertRaises(RuntimeError),
            ):
                self.decision()

    def test_stale_and_future_scans_fail(self):
        for hours in (-25, 1):
            with (
                patch.dict(
                    self.page["imageScanFindings"],
                    {"imageScanCompletedAt": (self.now + timedelta(hours=hours)).isoformat()},
                ),
                self.assertRaises(RuntimeError),
            ):
                self.decision()

    def test_incomplete_identity_counts_and_pagination_fail(self):
        for key, value in [
            ("imageScanStatus", {"status": "IN_PROGRESS"}),
            ("registryId", "other"),
            ("nextToken", "missing-page"),
        ]:
            with patch.dict(self.page, {key: value}), self.assertRaises(RuntimeError):
                self.decision()
        with (
            patch.dict(self.page["imageScanFindings"], {"findingSeverityCounts": {"HIGH": 2}}),
            self.assertRaises(RuntimeError),
        ):
            self.decision()

    def test_ambiguous_package_identity_fails(self):
        self.finding["attributes"].append({"key": "package_name", "value": "other"})
        with self.assertRaises(RuntimeError):
            self.decision()

    def test_trusted_github_artifact_recomputes_original_source(self):
        candidate, provenance = self.trusted()
        self.assertEqual(candidate, self.candidate)
        self.assertEqual(provenance, self.provenance)

    def test_arbitrary_receipt_cannot_claim_verified_ci(self):
        self.jobs["jobs"][0]["conclusion"] = "failure"
        with self.assertRaises(RuntimeError):
            self.trusted()

    def test_fork_branch_event_and_workflow_are_not_trusted(self):
        for key, value in [
            ("head_branch", "feature"),
            ("event", "pull_request"),
            ("path", "other.yml"),
            ("head_repository", {"full_name": "other/repo"}),
            ("run_attempt", 2),
        ]:
            with patch.dict(self.run, {key: value}), self.assertRaises(RuntimeError):
                self.trusted()

    def test_artifact_binding_and_digest_cannot_be_forged(self):
        for key, value in [
            ("id", 999),
            ("expired", True),
            ("name", "other"),
            ("digest", "sha256:" + "0" * 64),
            ("workflow_run", {"id": 123, "head_sha": "d" * 40}),
        ]:
            with patch.dict(self.artifact, {key: value}), self.assertRaises(RuntimeError):
                self.trusted()

    def test_source_manifest_mismatch_fails(self):
        with (
            patch.object(self.op, "github", side_effect=self.github),
            patch.object(self.op, "command", side_effect=self.command),
            patch("subprocess.run", return_value=SimpleNamespace(stdout=b"changed")),
        ):
            with self.assertRaises(RuntimeError):
                self.op.trusted_candidate(123, 1, 456, self.digest)

    def test_read_only_aws_allowlist_refuses_every_write_path(self):
        for operation in (
            "start-image-scan",
            "get-login-password",
            "put-image",
            "create-repository",
        ):
            with self.assertRaises(RuntimeError):
                self.op.aws("ecr", operation)

    def test_scan_needed_is_a_prerequisite_not_an_implicit_write(self):
        for response in (
            image.AWSFailure("ScanNotFoundException"),
            {"imageScanStatus": {"status": "IN_PROGRESS"}},
        ):
            with patch.object(
                self.op,
                "aws",
                side_effect=response
                if isinstance(response, Exception)
                else lambda *args, response=response, **kwargs: response,
            ) as aws:
                with self.assertRaises(RuntimeError):
                    self.op.scan(self.digest, read_only=True)
                self.assertEqual(aws.call_count, 1)
                self.assertEqual(self.report["cloud_write_attempts"], [])

    def evaluate(self, approval=True, manifest=None):
        row = {
            "registryId": image.ACCOUNT,
            "repositoryName": image.REPOSITORY,
            "imageId": {"imageDigest": self.digest},
            "imageManifest": manifest or self.raw,
        }

        def aws(service, operation, *args, **kwargs):
            self.assertIn((service, operation), accept.READS)
            return {"images": [row]} if operation == "batch-get-image" else self.page

        with (
            patch.object(self.op, "source"),
            patch.object(self.op, "identity"),
            patch.object(
                self.op, "trusted_candidate", return_value=(self.candidate, self.provenance)
            ),
            patch.object(self.op, "reviewed_approval", return_value=self.approval),
            patch.object(self.op, "aws", side_effect=aws),
            patch.object(self.op, "build", side_effect=AssertionError("build forbidden")),
            patch.object(self.op, "publish", side_effect=AssertionError("publish forbidden")),
        ):
            self.op.evaluate(self.digest, 123, 1, 456, "TEST-REVIEW" if approval else None)

    def test_exception_receipt_retains_full_findings_and_false_strict_policy(self):
        self.evaluate()
        self.assertFalse(self.report["scan_policy_passed"])
        self.assertTrue(self.report["image_security_accepted"])
        self.assertEqual(self.report["scan_pages"], [self.page])
        self.assertEqual(self.report["cloud_write_attempts"], [])
        self.assertFalse(self.report["application_deployed"])
        self.assertFalse(self.report["live_authentication_accepted"])

    def test_policy_only_commit_does_not_rebuild_or_change_candidate(self):
        self.evaluate()
        self.assertEqual(self.report["policy_revision"], self.policy_revision)
        self.assertEqual(self.report["candidate_provenance"]["source_revision"], self.revision)
        self.assertEqual(self.report["image_digest"], self.digest)

    def test_manifest_mismatch_is_blocked(self):
        with self.assertRaises(RuntimeError):
            self.evaluate(manifest="{}")

    def test_clean_evaluation_receipt_is_truthful(self):
        self.page["imageScanFindings"].update(findingSeverityCounts={}, findings=[])
        self.evaluate(False)
        self.assertTrue(self.report["scan_policy_passed"])
        self.assertEqual(self.report["result"], "strict_policy_passed")

    def test_failed_evaluation_retains_blocked_receipt_without_overwrite(self):
        path = self.root / "receipt.json"
        with patch.object(accept.ExistingImage, "evaluate", side_effect=RuntimeError("blocked")):
            with self.assertRaises(RuntimeError):
                accept.accept_existing(path, self.digest, 123, 1, 456)
        report = json.loads(path.read_text())
        self.assertEqual(report["result"], "blocked")
        self.assertFalse(report["image_security_accepted"])
        with self.assertRaises(FileExistsError):
            accept.accept_existing(path, self.digest, 123, 1, 456)

    def test_approval_must_match_user_merged_policy(self):
        path = self.root / accept.POLICY
        path.parent.mkdir(parents=True)
        policy = {"version": 1, "approvals": [self.approval]}
        path.write_text(json.dumps(policy))
        pr = {
            "merged": True,
            "merged_by": {"login": "LimYouSheng"},
            "merge_commit_sha": "c" * 40,
            "base": {"ref": "main", "repo": {"full_name": accept.GITHUB_REPO}},
        }
        with (
            patch.object(self.op, "github", return_value=pr),
            patch.object(self.op, "command", side_effect=["", json.dumps(policy)]),
        ):
            self.assertEqual(self.op.reviewed_approval("TEST-REVIEW"), self.approval)
        for key, value in [("merged", False), ("merged_by", {"login": "other"})]:
            with (
                patch.dict(pr, {key: value}),
                patch.object(self.op, "github", return_value=pr),
                self.assertRaises(RuntimeError),
            ):
                self.op.reviewed_approval("TEST-REVIEW")
        with (
            patch.object(self.op, "github", return_value=pr),
            patch.object(self.op, "command", side_effect=["", '{"approvals":[]}']),
            self.assertRaises(RuntimeError),
        ):
            self.op.reviewed_approval("TEST-REVIEW")

    def test_missing_approval_and_free_text_reference_cannot_self_approve(self):
        path = self.root / accept.POLICY
        path.parent.mkdir(parents=True)
        path.write_text('{"version":1,"approvals":[]}')
        with self.assertRaises(RuntimeError):
            self.op.reviewed_approval("unknown")
        self.approval["approval_reference"] = "I approve myself"
        path.write_text(json.dumps({"version": 1, "approvals": [self.approval]}))
        with self.assertRaises(RuntimeError):
            self.op.reviewed_approval("TEST-REVIEW")

    def test_github_client_uses_only_authenticated_get(self):
        with patch(
            "subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=b"{}")
        ) as run:
            self.op.github(f"repos/{accept.GITHUB_REPO}/actions/runs/123")
            self.assertEqual(run.call_args.args[0][:4], ["gh", "api", "--method", "GET"])
        with self.assertRaises(RuntimeError):
            self.op.github("repos/other/repo/actions/runs/123")

    def test_dispatcher_routes_only_explicit_acceptance_and_still_refuses_deploy(self):
        dispatcher = load_operator("deploy.py")
        with patch.object(accept, "accept_existing") as evaluate:
            dispatcher.main(
                [
                    "image-accept",
                    "--actions",
                    "--digest",
                    self.digest,
                    "--build-run",
                    "123",
                    "--build-attempt",
                    "1",
                    "--artifact-id",
                    "456",
                    "--receipt",
                    "receipt.json",
                ]
            )
            evaluate.assert_called_once_with("receipt.json", self.digest, 123, 1, 456, None)
        with self.assertRaises(RuntimeError):
            dispatcher.main(["image-accept", "--receipt", "receipt.json"])
        with self.assertRaisesRegex(RuntimeError, "Full release is not ready"):
            dispatcher.main(["deploy"])


if __name__ == "__main__":
    unittest.main()
