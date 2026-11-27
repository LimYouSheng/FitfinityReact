"""Verify stage inputs preserve reviewed resources and prior successful operations."""

import json
import unittest
from unittest.mock import patch

import hosting_design
from deployment_profile import DEVELOPER, fingerprint
from release_observation import digest
from release_stage_inputs import plan


class InputTests(unittest.TestCase):
    def setUp(self):
        self.source = "a" * 40
        self.config = {
            "target": "developer",
            "profile_sha256": fingerprint(DEVELOPER),
            "probe": {"db_name": "fitfinity", "db_host": "synthetic"},
        }
        self.record = {
            "identity": {"source_sha": self.source, "profile_sha256": fingerprint(DEVELOPER)},
            "verification": {"verification_run": 100},
            "stages": {},
        }
        self.stage(
            "image", 101, {"fitfinity-image-candidate.json": {"image_digest": "sha256:" + "b" * 64}}
        )
        self.stage(
            "observation",
            102,
            {
                "release-observation.json": {
                    "runtime": {"reserved_concurrency": 2, "revision_id": "revision"},
                    "database": {"DbiResourceId": "db-resource"},
                    "stack": {"id": "stack", "template_sha256": "f" * 64},
                }
            },
        )

    def stage(self, stage, run, docs, inputs=None):
        self.record["stages"][stage] = {
            "evidence": {"run_id": run, "documents": docs, "dispatch_inputs": inputs or {}}
        }

    def check(self, stage):
        return plan(stage, self.record, self.config, DEVELOPER, now=1000, new_id=lambda: "c" * 32)[
            "inputs"
        ]

    def test_image_reuses_the_authenticated_verification_run(self):
        self.assertEqual(
            self.check("image"),
            {"target": "developer", "source_sha": self.source, "verification_run": "100"},
        )
        self.assertEqual(self.check("observation"), {"target": "developer"})

    def test_prepare_binds_image_live_revision_and_original_capacity(self):
        result = self.check("prepare")
        probe = json.loads(result["probe_bindings"])
        maintenance = json.loads(result["maintenance_bindings"])
        self.assertEqual(probe["source_sha"], self.source)
        self.assertEqual(probe["image_digest"], "sha256:" + "b" * 64)
        self.assertEqual(probe["expires_at"], 4600)
        self.assertEqual(maintenance["function_revision"], "revision")
        self.assertEqual(maintenance["previous_concurrency"], 2)
        self.assertEqual(maintenance["operation_id"], "c" * 32)

    def test_existing_pause_cannot_silently_start_another_backup(self):
        self.record["stages"]["observation"]["evidence"]["documents"]["release-observation.json"][
            "runtime"
        ]["reserved_concurrency"] = 0
        with self.assertRaisesRegex(RuntimeError, "authenticated continuation"):
            self.check("prepare")

    def test_probe_followup_and_cleanup_keep_original_operation_and_stack(self):
        self.stage(
            "prepare", 103, {"schema-probe-review/review.json": {"template_sha256": "d" * 64}}
        )
        created = self.check("probe_create")
        self.stage(
            "probe_create",
            104,
            {"schema-probe-receipt.json": {"stack_id": "original-stack"}},
            created,
        )
        for stage, mode in (
            ("catalog", "collect"),
            ("cleanup_probe", "cleanup"),
            ("cleanup_probe_check", "cleanup-check"),
        ):
            with self.subTest(stage=stage):
                result = self.check(stage)
                self.assertEqual(result["mode"], mode)
                self.assertEqual(result["operation_id"], "c" * 32)
                self.assertEqual(result["stack_id"], "original-stack")
                self.assertEqual(result["review_run"], "103")
                if mode.startswith("cleanup"):
                    self.assertNotIn("image_run", result)

    def test_wrong_target_and_unintegrated_stage_fail_closed(self):
        self.config["profile_sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            self.check("image")
        self.config["profile_sha256"] = fingerprint(DEVELOPER)
        with self.assertRaisesRegex(RuntimeError, "Unknown release stage"):
            self.check("unknown")

    def test_rollout_and_resume_bind_actual_candidate_and_original_producers(self):
        template = hosting_design.app_template(
            "releases/" + "d" * 40 + "/" + "e" * 64,
            "arn:aws:wafv2:us-east-1:418638389566:global/webacl/"
            "fitfinity-test-login-cloudfront/00000000-0000-0000-0000-000000000000",
        )
        template["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 0
        self.stage("prepare", 103, {"release-readiness.json": {"frontend_manifest": {}}})
        self.stage(
            "backup",
            104,
            {
                "maintenance-receipt.json": {
                    "identity": {
                        "operation_id": "d" * 32,
                        "source_sha": self.source,
                        "profile_sha256": fingerprint(DEVELOPER),
                    }
                }
            },
        )
        self.stage("post_upgrade_catalog", 105, {})
        self.record["stages"]["upgrade"] = {"outcome": "not_required"}
        with patch("release_stage_inputs.template", return_value=template):
            result = self.check("rollout")
        review = json.loads(result["review_json"])
        self.assertEqual(review["original_template_sha256"], digest(template))
        self.assertEqual(result["review_sha256"], digest(review))
        self.assertEqual(
            json.loads(result["producer_runs_json"]),
            {"frontend": "103", "image": "101", "catalog": "105"},
        )
        self.assertEqual(result["mode"], "deploy")
        self.stage("rollout", 106, {}, result)
        resumed = self.check("resume")
        resume_review = json.loads(resumed["review_json"])
        self.assertEqual(resume_review["resumption"]["verified_run"], "106")
        self.assertEqual(resume_review["resumption"]["concurrency"], 2)
        self.assertEqual(
            resume_review["candidate_template_sha256"], review["candidate_template_sha256"]
        )
        self.assertEqual(resumed["review_sha256"], digest(resume_review))


if __name__ == "__main__":
    unittest.main()
