"""Prove durable release records reject replay, stale writers and foreign state."""

import json
import unittest
from copy import deepcopy

from deployment_journal import MissingJournalObject
from deployment_profile import DEVELOPER
from release_record import STAGES, ReleaseRecord, claim_target, identity, initial, next_stage


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.profile = DEVELOPER
        self.source = "a" * 40
        self.objects = {}
        self.writes = []
        self.record = ReleaseRecord(self.profile, self.source, self.read, self.write)
        self.seed = initial(
            self.profile,
            self.source,
            {
                "state": "source_verified",
                "source_sha": self.source,
                "repository": self.profile["github_repository"],
            },
            100,
        )

    def read(self, key):
        if key not in self.objects:
            raise MissingJournalObject("absent")
        body, etag = self.objects[key]
        return json.loads(body), etag

    def write(self, key, body, *, if_match=None, if_none_match=None):
        self.writes.append(key)
        if if_none_match == "*" and key in self.objects:
            raise RuntimeError("PreconditionFailed")
        if if_match is not None and self.objects.get(key, (None, None))[1] != if_match:
            raise RuntimeError("PreconditionFailed")
        etag = str(len(self.writes))
        self.objects[key] = (body, etag)
        return etag

    def test_intent_is_retained_before_completion_and_advances_once(self):
        self.record.commit(self.seed)
        self.record.intent("image", "b" * 32, {"target": "synthetic"}, 101)
        value = self.record.refresh()
        self.assertEqual(next_stage(value, self.record.identity)["action"], "reconcile")
        self.assertEqual(value["pending"]["inputs"], {"target": "synthetic"})
        self.record.complete("b" * 32, {"run_id": 123}, outcome="complete", now=102)
        self.assertEqual(
            next_stage(self.record.value, self.record.identity),
            {"action": "prepare", "stage": "observation"},
        )
        self.assertEqual(self.record.value["stages"]["image"]["evidence"], {"run_id": 123})
        with self.assertRaises(RuntimeError):
            self.record.complete("b" * 32, {}, outcome="complete", now=103)

    def test_concurrent_writer_cannot_replace_accepted_intent(self):
        self.record.commit(self.seed)
        other = ReleaseRecord(self.profile, self.source, self.read, self.write)
        other.refresh()
        self.record.intent("image", "b" * 32, {}, 101)
        with self.assertRaisesRegex(RuntimeError, "PreconditionFailed"):
            other.intent("image", "c" * 32, {}, 102)
        self.assertEqual(other.refresh()["pending"]["operation_id"], "b" * 32)
        with self.assertRaises(RuntimeError):
            other.intent("image", "c" * 32, {}, 103)

    def test_lost_pointer_acknowledgement_requires_read_before_any_write(self):
        self.record.commit(self.seed)
        original = self.record.write

        def lose_ack(key, body, **condition):
            result = original(key, body, **condition)
            if key.endswith("current.json"):
                raise RuntimeError("timeout")
            return result

        self.record.write = lose_ack
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            self.record.intent("image", "b" * 32, {}, 101)
        count = len(self.writes)
        with self.assertRaisesRegex(RuntimeError, "Refresh required"):
            self.record.intent("image", "c" * 32, {}, 102)
        self.assertEqual(len(self.writes), count)
        self.assertEqual(self.record.refresh()["pending"]["operation_id"], "b" * 32)

    def test_history_failure_prevents_pointer_update(self):
        def fail(*args, **kwargs):
            raise RuntimeError("storage unavailable")

        self.record.write = fail
        with self.assertRaises(RuntimeError):
            self.record.commit(self.seed)
        self.assertEqual(self.objects, {})
        self.assertIsNone(self.record.value)

    def test_foreign_profile_or_source_is_rejected_without_writes(self):
        for field in ("repository", "profile_sha256", "source_sha"):
            with self.subTest(field=field):
                changed = deepcopy(self.seed)
                changed["identity"][field] = "foreign"
                with self.assertRaises(RuntimeError):
                    self.record.commit(changed)
        self.assertEqual(self.writes, [])

    def test_wrong_stage_and_foreign_completion_cannot_advance(self):
        self.record.commit(self.seed)
        with self.assertRaises(RuntimeError):
            self.record.intent("resume", "b" * 32, {}, 101)
        self.record.intent("image", "b" * 32, {}, 101)
        before = len(self.writes)
        with self.assertRaises(RuntimeError):
            self.record.complete("c" * 32, {}, outcome="complete", now=102)
        with self.assertRaises(RuntimeError):
            self.record.complete("b" * 32, {}, outcome="failed", now=102)
        self.assertEqual(len(self.writes), before)

    def test_failed_stage_status_is_not_success(self):
        changed = deepcopy(self.seed)
        changed["stages"]["image"] = {"outcome": "failed", "evidence_sha256": "b" * 64}
        with self.assertRaises(RuntimeError):
            next_stage(changed, identity(self.profile, self.source))

    def test_target_claim_refuses_another_source_until_cleanup_is_complete(self):
        claim_target(self.profile, self.source, self.read, self.write, 100)
        self.record.commit(self.seed)
        before = len(self.writes)
        claim_target(self.profile, self.source, self.read, self.write, 101)
        self.assertEqual(len(self.writes), before)
        with self.assertRaisesRegex(RuntimeError, "Prior release still owns"):
            claim_target(self.profile, "b" * 40, self.read, self.write, 102)
        self.assertEqual(len(self.writes), before)
        changed = {**self.profile, "github_environment": "different-environment"}
        with self.assertRaisesRegex(RuntimeError, "Target claim identity differs"):
            claim_target(changed, self.source, self.read, self.write, 102)
        self.assertEqual(len(self.writes), before)
        for index, stage in enumerate(STAGES):
            operation = f"{index + 1:032x}"
            self.record.intent(stage, operation, {}, 103)
            self.record.complete(operation, {"run_id": index + 1}, outcome="complete", now=104)
        self.assertEqual(
            claim_target(self.profile, "b" * 40, self.read, self.write, 105)["identity"][
                "source_sha"
            ],
            "b" * 40,
        )

    def test_target_claim_lost_acknowledgement_is_reconciled_without_new_writes(self):
        def lose_ack(key, body, **condition):
            result = self.write(key, body, **condition)
            if key.endswith("current.json"):
                raise RuntimeError("timeout")
            return result

        with self.assertRaisesRegex(RuntimeError, "timeout"):
            claim_target(self.profile, self.source, self.read, lose_ack, 100)
        before = len(self.writes)
        claim_target(self.profile, self.source, self.read, self.write, 101)
        self.assertEqual(len(self.writes), before)
        with self.assertRaises(MissingJournalObject):
            claim_target(self.profile, "b" * 40, self.read, self.write, 102)
        self.assertEqual(len(self.writes), before)

    def test_foreign_verification_cannot_seed_release(self):
        with self.assertRaises(RuntimeError):
            initial(
                self.profile, self.source, {"state": "source_verified", "source_sha": "b" * 40}, 100
            )


if __name__ == "__main__":
    unittest.main()
