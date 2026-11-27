"""Exercise every milestone's retained-intent diagnosis without provider mutations."""

import hashlib
import unittest
from copy import deepcopy
from unittest.mock import patch

from deployment_profile import DEVELOPER
from release_dispatch import WORKFLOWS
from release_driver import recovery_report
from release_record import STAGES, encode, identity, initial
from release_recovery import RECOVERY, inspect_record, inspect_target, inventory


class RecoveryTests(unittest.TestCase):
    def record(self, stage):
        source = "a" * 40
        value = initial(
            DEVELOPER,
            source,
            {
                "state": "source_verified",
                "source_sha": source,
                "repository": DEVELOPER["github_repository"],
            },
            100,
        )
        for name in STAGES[: STAGES.index(stage)]:
            evidence = {"run_id": 42}
            value["stages"][name] = {
                "outcome": "complete",
                "evidence": evidence,
                "evidence_sha256": hashlib.sha256(encode(evidence)).hexdigest(),
            }
        value["pending"] = {
            "stage": stage,
            "state": "dispatch_intent",
            "operation_id": "b" * 32,
            "inputs": {"workflow": WORKFLOWS[stage], "inputs": {}},
        }
        return value

    def run_row(self, stage, status="completed", conclusion="success"):
        return {
            "id": 123,
            "display_title": "Release operation " + "b" * 32,
            "path": ".github/workflows/" + WORKFLOWS[stage],
            "head_sha": "a" * 40,
            "head_branch": "main",
            "event": "workflow_dispatch",
            "head_repository": {"full_name": DEVELOPER["github_repository"]},
            "run_attempt": 1,
            "status": status,
            "conclusion": conclusion,
        }

    def test_every_milestone_classifies_running_failed_and_success_without_changing_evidence(self):
        self.assertEqual(set(RECOVERY), set(STAGES))
        for stage in STAGES:
            for status, conclusion, action in (
                ("in_progress", None, "wait"),
                ("completed", "failure", "hold"),
                ("completed", "cancelled", "hold"),
                ("completed", "success", "authenticate_receipt"),
            ):
                with self.subTest(stage=stage, status=status, conclusion=conclusion):
                    record = self.record(stage)
                    original = deepcopy(record)
                    row = self.run_row(stage, status, conclusion)
                    result = inspect_record(
                        record,
                        DEVELOPER,
                        "a" * 40,
                        lambda path, row=row: {"total_count": 1, "workflow_runs": [row]},
                    )
                    self.assertEqual(result["action"], action)
                    self.assertEqual(result["stage"], stage)
                    self.assertEqual(result["run_id"], 123)
                    self.assertFalse(result["mutation_authorized"])
                    self.assertFalse(result["resource_state_checked"])
                    self.assertFalse(result["receipt_authenticated"])
                    self.assertEqual(record, original)

    def test_no_child_at_any_stage_remains_held_not_rejected_or_safe_to_retry(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                result = inspect_record(
                    self.record(stage),
                    DEVELOPER,
                    "c" * 40,
                    lambda path: {"total_count": 0, "workflow_runs": []},
                )
                self.assertEqual(result["action"], "hold")
                self.assertEqual(result["reason"], "dispatch_not_observed")
                self.assertTrue(result["source_transition_required"])
                self.assertIn("prove rejection", result["next"])

    def test_new_source_reads_original_claim_and_rejects_foreign_record(self):
        record = self.record("backup")
        claim = {"schema_version": 1, "identity": record["identity"]}
        reads = []

        def read(key):
            reads.append(key)
            return (claim if "/targets/" in key else record), "etag"

        result = inspect_target(
            DEVELOPER, "c" * 40, read, lambda path: {"total_count": 0, "workflow_runs": []}
        )
        self.assertEqual(result["source_sha"], "a" * 40)
        self.assertIn("/" + "a" * 40 + "/current.json", reads[-1])
        record["identity"] = identity(DEVELOPER, "d" * 40)
        with self.assertRaisesRegex(RuntimeError, "Claim and release record differ"):
            inspect_target(DEVELOPER, "c" * 40, read, lambda path: self.fail("Foreign read"))

    def test_pagination_must_be_complete_stable_unique_and_bounded(self):
        calls = []

        def read(path):
            calls.append(path)
            rows = [{"id": i} for i in range(100)] if len(calls) == 1 else [{"id": 100}]
            return {"total_count": 101, "workflow_runs": rows}

        self.assertEqual(len(inventory("repo", "workflow", "source", read)["workflow_runs"]), 101)
        self.assertTrue(calls[-1].endswith("page=2"))
        for payload in (
            {"total_count": 1, "workflow_runs": []},
            {"total_count": 2, "workflow_runs": [{"id": 1}, {"id": 1}]},
            {"total_count": "1", "workflow_runs": []},
        ):
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                inventory("repo", "workflow", "source", lambda path, payload=payload: payload)
        with self.assertRaisesRegex(RuntimeError, "changed"):
            inventory(
                "repo",
                "workflow",
                "source",
                lambda path: {
                    "total_count": 101 if path.endswith("page=1") else 102,
                    "workflow_runs": [{"id": i} for i in range(100)],
                },
            )

    def test_duplicate_wrong_source_and_rerun_cannot_authorize_recovery(self):
        for kind in ("duplicate", "foreign", "rerun"):
            rows = [self.run_row("backup")]
            if kind == "duplicate":
                rows.append({**rows[0], "id": 124})
            elif kind == "foreign":
                rows[0]["head_sha"] = "d" * 40
            else:
                rows[0]["run_attempt"] = 2
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                inspect_record(
                    self.record("backup"),
                    DEVELOPER,
                    "a" * 40,
                    lambda path, rows=rows: {"total_count": len(rows), "workflow_runs": rows},
                )

    def test_diagnostic_failure_preserves_primary_error_and_never_reports_success(self):
        original = {"state": "held", "reason": "Prior release still owns target"}
        with patch("release_driver.inspect_target", side_effect=ValueError("private payload")):
            result = recovery_report(original, DEVELOPER, "c" * 40, None, None)
        self.assertEqual(result["reason"], original["reason"])
        self.assertEqual(result["state"], "held")
        self.assertEqual(result["recovery"]["action"], "hold")
        self.assertNotIn("private payload", str(result))
        with patch("release_driver.inspect_target", return_value={"action": "wait"}) as inspect:
            result = recovery_report(original, DEVELOPER, "c" * 40, None, None)
            inspect.assert_called_once()
            self.assertEqual(result["recovery"], {"action": "wait"})
        with patch("release_driver.inspect_target") as inspect:
            self.assertEqual(
                recovery_report({"state": "release_complete"}, DEVELOPER, "c" * 40, None, None),
                {"state": "release_complete"},
            )
            inspect.assert_not_called()

    def test_unstarted_stage_does_not_allow_different_source_to_continue(self):
        record = self.record("backup")
        record["pending"] = None

        def read(path):
            self.fail("Undispatched stage has no child to inspect")

        result = inspect_record(record, DEVELOPER, "c" * 40, read)
        self.assertEqual(result["action"], "hold")
        result = inspect_record(record, DEVELOPER, "a" * 40, read)
        self.assertEqual(result["action"], "continue_verified_source")
        self.assertEqual(result["stage"], "backup")


if __name__ == "__main__":
    unittest.main()
