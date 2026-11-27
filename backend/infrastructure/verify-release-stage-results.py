"""Verify child success requires the intended operational result and original identity."""

import json
import unittest
from copy import deepcopy

from deployment_profile import DEVELOPER, identities
from release_observation import digest
from release_stage_results import validate


class StageTests(unittest.TestCase):
    def setUp(self):
        self.target = identities(DEVELOPER)
        self.source = "a" * 40
        self.record = {
            "identity": {
                "source_sha": self.source,
                "profile_sha256": self.target["profile_sha256"],
            },
            "pending": {"inputs": {"inputs": {}}},
            "stages": {},
        }
        self.documents = {}

    def check(self, stage):
        return validate(
            stage,
            {
                "run_id": 123,
                "source_sha": self.source,
                "artifact_id": 456,
                "documents": self.documents,
            },
            self.record,
            DEVELOPER,
            now=1000,
        )

    def test_image_must_be_published_and_accepted_at_exact_target(self):
        value = {
            "revision": self.source,
            "profile_sha256": self.target["profile_sha256"],
            "account": self.target["account"],
            "region": self.target["region"],
            "candidate_ready": True,
            "image_published": True,
            "scan_policy_passed": True,
            "image_digest": "sha256:" + "b" * 64,
        }
        self.documents["fitfinity-image-candidate.json"] = value
        self.assertEqual(self.check("image")["evidence"]["stage"], "image")
        for key, changed in (
            ("image_published", False),
            ("scan_policy_passed", False),
            ("revision", "b" * 40),
            ("account", "000000000000"),
        ):
            original = value[key]
            value[key] = changed
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.check("image")
            value[key] = original

    def test_preparation_must_contain_exact_dispatched_review(self):
        bindings = {"source_sha": self.source, "db_name": "synthetic"}
        self.record["pending"]["inputs"]["inputs"] = {"probe_bindings": json.dumps(bindings)}
        self.documents = {
            "release-readiness.json": {
                "source_sha": self.source,
                "profile_sha256": self.target["profile_sha256"],
                "frontend_manifest": [{"path": "index.html"}],
            },
            "schema-probe-review/review.json": {"bindings": bindings},
        }
        self.assertEqual(self.check("prepare")["outcome"], "complete")
        self.documents["schema-probe-review/review.json"] = {
            "bindings": {**bindings, "db_name": "foreign"}
        }
        with self.assertRaisesRegex(RuntimeError, "dispatched bindings"):
            self.check("prepare")

    def test_probe_creation_requires_original_operation_and_retained_stack(self):
        self.record["pending"]["inputs"]["inputs"] = {"operation_id": "b" * 32}
        value = {
            "source_sha": self.source,
            "profile_sha256": self.target["profile_sha256"],
            "operation_id": "b" * 32,
            "state": "create_submitted",
            "stack_id": (
                f"arn:aws:cloudformation:{self.target['region']}:{self.target['account']}:stack/"
                f"{self.target['probe_name']}/owned"
            ),
        }
        self.documents["schema-probe-receipt.json"] = value
        self.assertEqual(self.check("probe_create")["outcome"], "complete")
        for key, changed in (
            ("state", "failed_or_uncertain"),
            ("operation_id", "c" * 32),
            ("stack_id", None),
            ("stack_id", "foreign"),
        ):
            original = value[key]
            value[key] = changed
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.check("probe_create")
            value[key] = original

    def test_cleanup_submission_does_not_establish_deletion(self):
        self.record["pending"]["inputs"]["inputs"] = {"operation_id": "b" * 32}
        value = {
            "source_sha": self.source,
            "profile_sha256": self.target["profile_sha256"],
            "operation_id": "b" * 32,
            "state": "cleanup_submitted",
        }
        self.documents["schema-probe-receipt.json"] = value
        self.assertEqual(self.check("cleanup_probe")["outcome"], "complete")
        with self.assertRaises(RuntimeError):
            self.check("cleanup_probe_check")
        value["state"] = "cleanup_verified"
        self.assertEqual(self.check("cleanup_probe_check")["outcome"], "complete")

    def test_rollout_and_resume_require_separate_operational_states(self):
        review = {"operation_id": "b" * 32}
        self.record["pending"]["inputs"]["inputs"] = {"review_json": json.dumps(review)}
        value = {
            "review_sha256": digest(review),
            "state": "template_verified",
            "evidence": deepcopy(self.record["identity"]),
        }
        self.documents["rollout-receipt.json"] = value
        self.assertEqual(self.check("rollout")["outcome"], "complete")
        with self.assertRaises(RuntimeError):
            self.check("resume")
        value["state"] = "maintenance_finalized"
        self.assertEqual(self.check("resume")["outcome"], "complete")
        value["review_sha256"] = "f" * 64
        with self.assertRaises(RuntimeError):
            self.check("resume")


if __name__ == "__main__":
    unittest.main()
