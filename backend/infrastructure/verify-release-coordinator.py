"""Verify coordinator progression uses persisted intent and authenticated evidence."""

import json
import unittest
from unittest.mock import Mock

from deployment_journal import MissingJournalObject
from deployment_profile import DEVELOPER
from release_coordinator import load_or_start, start, tick
from release_record import STAGES, ReleaseRecord, claim_target


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.objects = {}
        self.version = 0
        self.source = "a" * 40
        self.record = ReleaseRecord(DEVELOPER, self.source, self.read, self.write)
        self.verification = {
            "state": "source_verified",
            "source_sha": self.source,
            "repository": DEVELOPER["github_repository"],
        }
        self.rows = []
        self.send = Mock()
        self.auth = Mock(side_effect=self.authenticate)
        self.args = {
            "verify": lambda: self.verification,
            "plan": lambda stage, value: {"inputs": {"target": "developer"}},
            "read_runs": lambda workflow, source: {
                "total_count": len(self.rows),
                "workflow_runs": self.rows,
            },
            "authenticate": self.auth,
            "read": lambda path: {"object": {"sha": self.source}},
            "send": self.send,
            "now": 100,
        }
        start(self.record, DEVELOPER, lambda: self.verification, 100)

    def read(self, key):
        if key not in self.objects:
            raise MissingJournalObject("absent")
        body, etag = self.objects[key]
        return json.loads(body), etag

    def write(self, key, body, *, if_match=None, if_none_match=None):
        if if_none_match and key in self.objects:
            raise RuntimeError("already exists")
        if if_match and self.objects[key][1] != if_match:
            raise RuntimeError("stale")
        self.version += 1
        self.objects[key] = (body, str(self.version))
        return str(self.version)

    def authenticate(self, stage, run_id, record):
        return {
            "outcome": "complete",
            "evidence": {
                "stage": stage,
                "run_id": run_id,
                "source_sha": self.source,
                "profile_sha256": self.record.identity["profile_sha256"],
            },
        }

    def child(self, workflow, operation):
        return {
            "id": 123,
            "run_attempt": 1,
            "head_sha": self.source,
            "head_repository": {"full_name": DEVELOPER["github_repository"]},
            "head_branch": "main",
            "event": "workflow_dispatch",
            "path": ".github/workflows/" + workflow,
            "display_title": "Release operation " + operation,
            "status": "completed",
            "conclusion": "success",
        }

    def test_entire_synthetic_stage_sequence_completes_once_per_dispatch(self):
        for index, stage in enumerate(STAGES):
            operation = f"{index + 1:032x}"
            self.assertEqual(
                tick(self.record, **self.args, operation_id=operation)["state"],
                "dispatch_requested",
            )
            workflow = self.record.value["pending"]["inputs"]["workflow"]
            self.rows = [self.child(workflow, operation)]
            self.assertEqual(tick(self.record, **self.args)["stage"], stage)
        self.assertEqual(tick(self.record, **self.args), {"state": "release_complete"})
        self.assertEqual(self.send.call_count, len(STAGES))
        self.assertEqual(self.auth.call_count, len(STAGES))

    def test_missing_child_holds_without_replaying_dispatch(self):
        tick(self.record, **self.args, operation_id="b" * 32)
        self.assertEqual(tick(self.record, **self.args)["reason"], "dispatch_not_observed")
        self.send.assert_called_once()
        self.auth.assert_not_called()

    def test_foreign_authenticated_receipt_does_not_advance(self):
        tick(self.record, **self.args, operation_id="b" * 32)
        self.rows = [self.child("aws-image.yml", "b" * 32)]
        self.auth.side_effect = None
        self.auth.return_value = {"outcome": "complete", "evidence": {"run_id": 999}}
        with self.assertRaisesRegex(RuntimeError, "authority differs"):
            tick(self.record, **self.args)
        self.assertEqual(self.record.refresh()["stages"], {})
        self.assertIsNotNone(self.record.value["pending"])
        self.send.assert_called_once()

    def test_new_release_cannot_replace_existing_record(self):
        other = ReleaseRecord(DEVELOPER, self.source, self.read, self.write)
        with self.assertRaises(RuntimeError):
            start(other, DEVELOPER, lambda: self.verification, 100)
        self.assertEqual(self.record.refresh()["generation"], 0)

    def test_initialization_resumes_without_resetting_pending_intent(self):
        tick(self.record, **self.args, operation_id="b" * 32)
        claim_target(DEVELOPER, self.source, self.read, self.write, 100)
        other = ReleaseRecord(DEVELOPER, self.source, self.read, self.write)
        before = self.version
        self.assertEqual(
            load_or_start(other, DEVELOPER, lambda: self.verification, 200),
            {"state": "release_loaded"},
        )
        self.assertEqual(other.value["pending"]["operation_id"], "b" * 32)
        self.assertEqual(self.version, before)

    def test_initialization_requires_proven_absence_and_no_prior_loaded_record(self):
        self.objects.clear()
        reader = Mock(side_effect=self.read)
        fresh = ReleaseRecord(DEVELOPER, self.source, reader, self.write)
        self.assertEqual(
            load_or_start(fresh, DEVELOPER, lambda: self.verification, 200),
            {"state": "release_created"},
        )
        before = self.version
        del self.objects[fresh.prefix + "current.json"]
        with self.assertRaisesRegex(RuntimeError, "disappeared"):
            load_or_start(fresh, DEVELOPER, lambda: self.verification, 201)
        reader.side_effect = RuntimeError("AccessDenied")
        unknown = ReleaseRecord(DEVELOPER, self.source, reader, self.write)
        with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
            load_or_start(unknown, DEVELOPER, lambda: self.verification, 202)
        self.assertEqual(self.version, before)

    def test_failed_source_check_prevents_dispatch(self):
        self.verification["state"] = "failed"
        with self.assertRaises(RuntimeError):
            tick(self.record, **self.args)
        self.send.assert_not_called()
        self.assertIsNone(self.record.refresh()["pending"])

    def test_readiness_wait_has_no_dispatch_or_pending_write(self):
        self.args["plan"] = lambda stage, value: {"wait": "Worker creation is still in progress"}
        result = tick(self.record, **self.args)
        self.assertEqual(result["state"], "wait")
        self.assertIsNone(self.record.value["pending"])
        self.send.assert_not_called()

    def test_current_schema_skips_worker_stages_without_dispatch(self):
        import hashlib
        from copy import deepcopy
        from pathlib import Path

        from release_readiness import migration_chain
        from release_record import encode

        head = migration_chain(Path(__file__).parents[1] / "migrations/versions")[-1]["revision"]
        value = deepcopy(self.record.value)
        for stage in STAGES[: STAGES.index("upgrade_prepare")]:
            evidence = (
                {
                    "documents": {
                        "schema-probe-receipt.json": {
                            "receipt": {"catalog": {"alembic_revisions": [head]}}
                        }
                    }
                }
                if stage == "catalog"
                else {}
            )
            value["stages"][stage] = {
                "outcome": "complete",
                "evidence": evidence,
                "evidence_sha256": hashlib.sha256(encode(evidence)).hexdigest(),
            }
        value["generation"] += 1
        self.record.commit(value)
        for stage in ("upgrade_prepare", "upgrade_create", "upgrade_inspect", "upgrade"):
            self.assertEqual(
                tick(self.record, **self.args), {"state": "stage_not_required", "stage": stage}
            )
            self.assertEqual(self.record.value["stages"][stage]["outcome"], "not_required")
        self.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
