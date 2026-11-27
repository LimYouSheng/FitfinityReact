"""Verify grouped release phases preserve guarded ordering and uncertain intent."""

import unittest
from copy import deepcopy
from unittest.mock import patch

from release_milestones import Milestone, maintenance_backup, rollout_milestone


class MilestoneTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.calls = []
        self.saved = []
        self.polls = 0
        self.fail = None

    def pause(self, seconds):
        self.now += seconds

    def step(self, mode, prior, save):
        self.calls.append(mode)
        if prior is not None:
            self.assertEqual(prior["review_sha256"], "reviewed")
        value = {"state": "submitted", "review_sha256": "reviewed"}
        if mode.endswith("inspect") and mode not in {"upload-inspect", "resume-finalize-inspect"}:
            self.polls += 1
            value.update(change_set_status="CREATE_COMPLETE", execution_status="AVAILABLE")
            if prior.get("execution_requested"):
                value.update(
                    execution_requested=True,
                    execution_status="EXECUTE_COMPLETE",
                    stack_status="UPDATE_COMPLETE",
                )
            elif self.polls == 1:
                value.update(change_set_status="CREATE_IN_PROGRESS", execution_status="UNAVAILABLE")
        if mode.endswith("execute"):
            value["execution_requested"] = True
        if mode == "resume-finalize-inspect":
            value["state"] = "maintenance_finalized"
        save(value)
        if mode == self.fail:
            raise RuntimeError("uncertain provider response")
        # Canonical wrappers enrich the persisted receipt, not their return value.
        return {"state": value["state"]}

    def run_milestone(self, mode):
        return rollout_milestone(
            mode,
            self.step,
            lambda row: self.saved.append(deepcopy(row)),
            clock=lambda: self.now,
            pause=self.pause,
        )

    def test_deploy_groups_phases_without_resuming(self):
        result = self.run_milestone("deploy")
        self.assertEqual(
            self.calls,
            [
                "upload",
                "upload-inspect",
                "create",
                "inspect",
                "inspect",
                "execute",
                "inspect",
                "verify",
            ],
        )
        self.assertEqual(result["milestone_phase"], "verify")
        self.assertEqual(result["review_sha256"], "reviewed")
        self.assertEqual(self.now, 1010)

    def test_resume_requires_health_before_finalization(self):
        result = self.run_milestone("resume")
        self.assertEqual(
            self.calls,
            [
                "resume-create",
                "resume-inspect",
                "resume-inspect",
                "resume-execute",
                "resume-inspect",
                "resume-verify",
                "resume-health",
                "resume-finalize",
                "resume-finalize-inspect",
            ],
        )
        self.assertEqual(result["state"], "maintenance_finalized")
        self.assertEqual(result["milestone_phase"], "resume-finalize-inspect")

    def test_uncertain_writes_and_failed_health_stop_without_replay(self):
        for mode, failure in (
            ("deploy", "upload"),
            ("deploy", "upload-inspect"),
            ("deploy", "create"),
            ("deploy", "inspect"),
            ("deploy", "execute"),
            ("deploy", "verify"),
            ("resume", "resume-create"),
            ("resume", "resume-inspect"),
            ("resume", "resume-execute"),
            ("resume", "resume-verify"),
            ("resume", "resume-health"),
            ("resume", "resume-finalize"),
            ("resume", "resume-finalize-inspect"),
        ):
            with self.subTest(failure=failure):
                self.setUp()
                self.fail = failure
                with self.assertRaisesRegex(RuntimeError, "uncertain"):
                    self.run_milestone(mode)
                self.assertEqual(self.calls[-1], failure)
                self.assertEqual(self.calls.count(failure), 1)
                self.assertEqual(self.saved[-1]["milestone_phase"], failure)

    def test_backup_stops_at_every_interrupted_phase_and_preserves_original_receipt(self):
        phases = [
            "pause",
            "inspect",
            "record-pause-create",
            "record-pause-inspect",
            "record-pause-execute",
            "record-pause-inspect",
            "record-pause-verify",
            "snapshot",
            "snapshot-check",
        ]
        for failure_index in range(len(phases)):
            with self.subTest(failure_index=failure_index):
                calls, saved = [], []

                def execute(
                    mode,
                    review,
                    call,
                    persist,
                    *,
                    calls=calls,
                    failure_index=failure_index,
                    **kwargs,
                ):
                    calls.append(mode)
                    receipt = {
                        "state": "paused",
                        "drained_after": 1000,
                        "identity": {"operation_id": "original"},
                    }
                    if mode.startswith("record-pause"):
                        receipt["pause_record"] = {
                            "change_set_status": "CREATE_COMPLETE",
                            "execution_status": "AVAILABLE",
                        }
                        if "record-pause-execute" in calls:
                            receipt["pause_record"].update(
                                execution_requested=True,
                                stack_status="UPDATE_COMPLETE",
                                execution_status="EXECUTE_COMPLETE",
                            )
                    if mode == "snapshot-check":
                        receipt["state"] = "snapshot_ready"
                    persist(receipt)
                    if len(calls) - 1 == failure_index:
                        raise RuntimeError("uncertain acknowledgement")

                with patch("release_maintenance.execute", side_effect=execute):
                    with self.assertRaisesRegex(RuntimeError, "uncertain acknowledgement"):
                        maintenance_backup(
                            {}, None, saved.append, profile={}, clock=lambda: 1000, pause=self.pause
                        )
                self.assertEqual(calls, phases[: failure_index + 1])
                self.assertEqual(saved[-1]["milestone_phase"], phases[failure_index])
                self.assertEqual(saved[-1]["identity"]["operation_id"], "original")

    def test_polling_is_bounded_and_never_retries_writes(self):
        def pending(mode, prior, save):
            self.calls.append(mode)
            save({"state": "pending"})

        runner = Milestone(
            pending, self.saved.append, clock=lambda: self.now, pause=self.pause, budget=20
        )
        with self.assertRaisesRegex(RuntimeError, "deadline"):
            runner.wait("inspect", {}, lambda row: False)
        self.assertEqual(self.calls, ["inspect", "inspect"])
        self.assertEqual(self.now, 1020)

    def test_missing_durable_receipt_stops_next_phase(self):
        runner = Milestone(lambda *args: {}, self.saved.append)
        with self.assertRaisesRegex(RuntimeError, "durable"):
            runner.run("create")
        self.assertFalse(self.saved)

    def test_terminal_provider_failure_stops_polling(self):
        from release_milestones import change_set_ready, stack_complete

        self.assertFalse(
            stack_complete(
                {
                    "stack_status": "CREATE_COMPLETE",
                    "execution_requested": True,
                    "execution_status": "AVAILABLE",
                }
            )
        )
        with self.assertRaises(RuntimeError):
            stack_complete(
                {
                    "stack_status": "UPDATE_COMPLETE",
                    "execution_requested": True,
                    "execution_status": "EXECUTE_FAILED",
                }
            )
        for status in ("FAILED", "DELETE_COMPLETE"):
            with self.assertRaises(RuntimeError):
                change_set_ready({"change_set_status": status})
        for status in ("UPDATE_ROLLBACK_IN_PROGRESS", "UPDATE_ROLLBACK_COMPLETE", "UPDATE_FAILED"):
            with self.assertRaises(RuntimeError):
                stack_complete({"stack_status": status, "execution_requested": True})
        with self.assertRaisesRegex(RuntimeError, "do not replay"):
            change_set_ready({"change_set_status": "CREATE_COMPLETE", "execution_requested": True})


if __name__ == "__main__":
    unittest.main()
