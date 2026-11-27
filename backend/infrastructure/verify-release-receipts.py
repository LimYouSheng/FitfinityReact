"""Reject substituted or unsafe child receipts before stage advancement."""

import hashlib
import io
import json
import unittest
import warnings
import zipfile

from deployment_profile import DEVELOPER
from release_receipts import documents, fetch


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.source = "a" * 40
        self.body = self.archive([("fitfinity-image-candidate.json", {"revision": self.source})])
        self.run = {
            "id": 123,
            "run_attempt": 1,
            "head_sha": self.source,
            "head_repository": {"full_name": DEVELOPER["github_repository"]},
            "head_branch": "main",
            "path": ".github/workflows/aws-image.yml",
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
        }
        self.artifact = {
            "id": 456,
            "name": "fitfinity-image-candidate-123-1",
            "expired": False,
            "size_in_bytes": len(self.body),
            "digest": "sha256:" + hashlib.sha256(self.body).hexdigest(),
        }
        self.downloads = []

    def archive(self, rows):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, value in rows:
                archive.writestr(name, json.dumps(value))
        return output.getvalue()

    def read(self, path):
        if path.endswith("/artifacts?per_page=100"):
            return {"total_count": 1, "artifacts": [self.artifact]}
        return self.run

    def download(self, path):
        self.downloads.append(path)
        return self.body

    def check(self):
        return fetch(
            "image", 123, self.source, DEVELOPER, read=self.read, fetch_bytes=self.download
        )

    def test_exact_successful_attempt_and_digest_are_bound(self):
        result = self.check()
        self.assertEqual(result["artifact_id"], 456)
        self.assertEqual(
            result["documents"]["fitfinity-image-candidate.json"], {"revision": self.source}
        )
        self.assertEqual(
            self.downloads, [f"repos/{DEVELOPER['github_repository']}/actions/artifacts/456/zip"]
        )

    def test_failed_foreign_and_rerun_producers_are_rejected_before_download(self):
        for field, value in (
            ("conclusion", "failure"),
            ("head_sha", "b" * 40),
            ("run_attempt", 2),
            ("id", 999),
            ("event", "pull_request"),
        ):
            original = dict(self.run)
            self.run[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.check()
            self.run = original
        self.assertEqual(self.downloads, [])

    def test_expired_or_wrong_named_artifact_is_not_downloaded(self):
        for field, value in (("expired", True), ("name", "foreign"), ("size_in_bytes", 0)):
            original = dict(self.artifact)
            self.artifact[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.check()
            self.artifact = original
        self.assertEqual(self.downloads, [])

    def test_substituted_bytes_fail_digest_verification(self):
        self.body = self.archive([("fitfinity-image-candidate.json", {"revision": "b" * 40})])
        with self.assertRaisesRegex(RuntimeError, "digest differs"):
            self.check()
        self.assertEqual(len(self.downloads), 1)

    def test_missing_or_duplicate_receipt_is_rejected(self):
        with self.assertRaises(RuntimeError):
            documents(self.archive([]), ("receipt.json",))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            body = self.archive([("receipt.json", {}), ("receipt.json", {})])
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            documents(body, ("receipt.json",))

    def test_path_traversal_and_symlink_members_are_rejected(self):
        for name in ("../receipt.json", "/receipt.json", "folder\\receipt.json"):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                documents(self.archive([(name, {})]), ())
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            info = zipfile.ZipInfo("receipt.json")
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "{}")
        with self.assertRaises(RuntimeError):
            documents(output.getvalue(), ("receipt.json",))


if __name__ == "__main__":
    unittest.main()
