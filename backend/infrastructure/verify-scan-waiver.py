"""Verify developer acceptance and downstream rejection without AWS operations."""

import copy
import json
import unittest
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import scan_waiver
from deployment_profile import DEVELOPER as BASE_DEVELOPER
from release_image import scan_policy
from release_image_validation import validate_scan_acceptance

DEVELOPER = {**BASE_DEVELOPER, "github_owner_id": "141623519", "github_repository_id": "1353173586"}


class DeveloperWaiverChecks(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(scan_waiver.POLICY.read_text())
        self.now = datetime(2026, 11, 26, tzinfo=UTC)
        self.digest = "sha256:" + "a" * 64
        self.files = json.loads(
            Path(__file__).with_name("scan-waiver-source-fixture.json").read_text()
        )
        self.findings = [
            {
                "name": row["cve"],
                "severity": row["severity"],
                "attributes": [
                    {"key": "package_name", "value": row["package"]},
                    {"key": "package_version", "value": row["version"]},
                ],
            }
            for row in self.policy["findings"]
        ]

    def page(self):
        return {
            "registryId": DEVELOPER["account"],
            "repositoryName": "fitfinity-test-api",
            "imageId": {"imageDigest": self.digest},
            "imageScanStatus": {"status": "COMPLETE"},
            "imageScanFindings": {
                "imageScanCompletedAt": self.now.isoformat(),
                "findingSeverityCounts": dict(Counter(row["severity"] for row in self.findings)),
                "findings": copy.deepcopy(self.findings),
            },
        }

    def accept(self, **kwargs):
        return scan_waiver.developer_exception(
            self.findings,
            self.digest,
            kwargs.get("now", self.now),
            kwargs.get("profile", DEVELOPER),
            kwargs.get("files", self.files),
        )

    def test_reviewed_fifteen_findings_record_explicit_acceptance(self):
        decision = {}
        counts = scan_policy(
            [self.page()],
            self.digest,
            self.now,
            source_files=self.files,
            decision=decision,
            profile=DEVELOPER,
        )
        self.assertEqual(counts, {"HIGH": 9, "MEDIUM": 5, "UNDEFINED": 1})
        self.assertEqual(decision["kind"], "developer_exception")
        self.assertEqual(decision["image_digest"], self.digest)
        self.assertEqual(decision["expires_at"], "2026-12-03T23:59:59+08:00")
        self.assertEqual(
            decision["runtime_sha256"],
            "6a3fb3fbe45f7c022febb214be94c1569fb7ab40fafa72b9ccdf304a4fae54f3",
        )

    def test_expiry_and_future_approval_block(self):
        for now in (
            datetime(2026, 11, 24, tzinfo=UTC),
            datetime(2026, 12, 3, 15, 59, 59, tzinfo=UTC),
        ):
            with self.subTest(now=now), self.assertRaisesRegex(RuntimeError, "expired or future"):
                self.accept(now=now)

    def test_other_account_repository_environment_block(self):
        for key, value in (
            ("account", "123456789012"),
            ("github_repository", "client/app"),
            ("github_environment", "production"),
        ):
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "target"):
                self.accept(profile={**DEVELOPER, key: value})

    def test_added_changed_missing_runtime_inputs_block(self):
        changes = [
            dict(self.files, **{"backend/app/new.py": "a" * 64}),
            dict(self.files, **{"backend/Dockerfile": "b" * 64}),
            {key: value for key, value in self.files.items() if key != "backend/Dockerfile"},
        ]
        for files in changes:
            with self.subTest(files=len(files)), self.assertRaisesRegex(RuntimeError, "runtime"):
                self.accept(files=files)

    def test_cve_package_version_severity_changes_block(self):
        original = copy.deepcopy(self.findings)
        for kind in ("cve", "package", "version", "severity"):
            self.findings = copy.deepcopy(original)
            if kind == "cve":
                self.findings[0]["name"] = "CVE-2099-99999"
            elif kind == "severity":
                self.findings[0]["severity"] = "CRITICAL"
            else:
                self.findings[0]["attributes"][0 if kind == "package" else 1]["value"] = "changed"
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, "finding set"):
                self.accept()

    def test_added_removed_duplicate_findings_block(self):
        original = copy.deepcopy(self.findings)
        for rows in (original[:-1], original + [original[0]], original[1:] + [original[1]]):
            self.findings = rows
            with self.assertRaisesRegex(RuntimeError, "finding set"):
                self.accept()

    def test_ambiguous_or_missing_package_attributes_block(self):
        original = copy.deepcopy(self.findings)
        for attrs in ([], [original[0]["attributes"][0]] * 2):
            self.findings = copy.deepcopy(original)
            self.findings[0]["attributes"] = attrs
            with self.assertRaisesRegex(RuntimeError, "package"):
                self.accept()

    def test_revocation_blocks(self):
        policy = {**self.policy, "status": "revoked"}
        with patch.object(Path, "read_bytes", return_value=json.dumps(policy).encode()):
            with self.assertRaisesRegex(RuntimeError, "not approved"):
                self.accept()

    def test_stale_incomplete_wrong_digest_scans_still_block(self):
        page = self.page()
        stale = copy.deepcopy(page)
        stale["imageScanFindings"]["imageScanCompletedAt"] = (
            self.now - timedelta(hours=25)
        ).isoformat()
        wrong = copy.deepcopy(page)
        wrong["imageId"]["imageDigest"] = "sha256:" + "b" * 64
        incomplete = copy.deepcopy(page)
        incomplete["imageScanStatus"]["status"] = "IN_PROGRESS"
        for value in (stale, wrong, incomplete):
            with self.assertRaises(RuntimeError):
                scan_policy([value], self.digest, self.now, source_files=self.files)

    def test_downstream_requires_matching_receipt_and_unexpired_policy(self):
        receipt = {
            "image_digest": self.digest,
            "source_files": self.files,
            "scan_acceptance": self.accept(),
        }
        validate_scan_acceptance(receipt, [self.page()], self.now, profile=DEVELOPER)
        for key in ("image_digest", "expires_at", "policy_sha256", "runtime_sha256"):
            changed = copy.deepcopy(receipt)
            changed["scan_acceptance"][key] = "tampered"
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "receipt differs"):
                validate_scan_acceptance(changed, [self.page()], self.now, profile=DEVELOPER)
        del receipt["scan_acceptance"]
        with self.assertRaisesRegex(RuntimeError, "receipt differs"):
            validate_scan_acceptance(receipt, [self.page()], self.now, profile=DEVELOPER)
        self.now = datetime(2026, 12, 4, tzinfo=UTC)
        with self.assertRaisesRegex(RuntimeError, "expired"):
            validate_scan_acceptance(receipt, [self.page()], self.now, profile=DEVELOPER)


if __name__ == "__main__":
    unittest.main()
