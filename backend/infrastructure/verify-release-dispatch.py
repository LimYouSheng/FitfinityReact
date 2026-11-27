"""Prove workflow dispatch preserves uncertain intent and exact child identity."""

import unittest
from copy import deepcopy
from unittest.mock import Mock

from release_dispatch import dispatch, reconcile


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.record = Mock()
        self.record.identity = {
            "repository": "client/portal",
            "source_sha": "a" * 40,
            "profile_sha256": "b" * 64,
        }
        self.record.value = {
            "schema_version": 1,
            "identity": self.record.identity,
            "generation": 0,
            "stages": {},
            "pending": None,
        }
        self.events = []
        self.read = lambda path: {"object": {"sha": "a" * 40}}
        self.record.intent.side_effect = self.intent
        self.run = {
            "id": 123,
            "run_attempt": 1,
            "head_sha": "a" * 40,
            "head_repository": {"full_name": "client/portal"},
            "head_branch": "main",
            "event": "workflow_dispatch",
            "path": ".github/workflows/aws-image.yml",
            "display_title": "Release operation " + "c" * 32,
            "status": "completed",
            "conclusion": "success",
        }

    def intent(self, stage, operation_id, inputs, now):
        self.events.append("intent")
        self.record.value["pending"] = {
            "stage": stage,
            "operation_id": operation_id,
            "inputs": inputs,
            "state": "dispatch_intent",
        }

    def send(self, path, payload):
        self.events.append("send")
        self.assertEqual(path, "repos/client/portal/actions/workflows/aws-image.yml/dispatches")
        self.assertEqual(payload["inputs"]["orchestration_id"], "c" * 32)
        self.assertEqual(payload["ref"], "main")

    def start(self, send=None):
        return dispatch(
            self.record,
            "image",
            "c" * 32,
            {"target": "client"},
            read=self.read,
            now=100,
            send=send or self.send,
        )

    def test_dispatch_persists_intent_first_and_does_not_advance_stage(self):
        result = self.start()
        self.assertEqual(self.events, ["intent", "send"])
        self.assertEqual(result["state"], "dispatch_requested")
        self.assertEqual(self.record.value["stages"], {})
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertEqual(self.events, ["intent", "send"])

    def test_lost_dispatch_acknowledgement_retains_intent_and_blocks_replay(self):
        def fail(*args):
            self.events.append("send")
            raise RuntimeError("timeout")

        with self.assertRaises(RuntimeError):
            self.start(fail)
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertEqual(self.events, ["intent", "send"])
        self.assertEqual(
            reconcile(self.record, {"total_count": 0, "workflow_runs": []}),
            {"action": "hold", "reason": "dispatch_not_observed"},
        )

    def test_main_movement_blocks_dispatch_before_intent(self):
        self.read = lambda path: {"object": {"sha": "d" * 40}}
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertEqual(self.events, [])

    def test_success_requires_receipt_authentication_and_failure_holds(self):
        self.start()
        payload = {"total_count": 1, "workflow_runs": [self.run]}
        self.assertEqual(
            reconcile(self.record, payload), {"action": "authenticate_receipt", "run_id": 123}
        )
        self.run["conclusion"] = "failure"
        self.assertEqual(reconcile(self.record, payload)["reason"], "child_unsuccessful")
        self.run.update(status="waiting", conclusion=None)
        self.assertEqual(reconcile(self.record, payload), {"action": "wait", "run_id": 123})

    def test_duplicate_foreign_and_rerun_children_are_rejected(self):
        self.start()
        for field, value in (
            ("head_sha", "d" * 40),
            ("run_attempt", 2),
            ("head_repository", {"full_name": "foreign/repo"}),
            ("event", "pull_request"),
            ("path", ".github/workflows/other.yml"),
        ):
            run = {**deepcopy(self.run), field: value}
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                reconcile(self.record, {"total_count": 1, "workflow_runs": [run]})
        with self.assertRaises(RuntimeError):
            reconcile(self.record, {"total_count": 2, "workflow_runs": [self.run, self.run]})
        with self.assertRaises(RuntimeError):
            reconcile(self.record, {"total_count": 2, "workflow_runs": [self.run]})

    def test_storage_failure_prevents_github_dispatch(self):
        self.record.intent.side_effect = RuntimeError("storage failed")
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
