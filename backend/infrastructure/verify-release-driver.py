"""Check bounded coordinator observation and terminal holds without replaying writes."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from deployment_profile import DEVELOPER
from release_driver import drive


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.clock = 100
        self.record = SimpleNamespace(identity={"source_sha": "a" * 40})

    def pause(self, seconds):
        self.clock += seconds

    def test_unobserved_dispatch_is_polled_until_budget_without_new_dispatch(self):
        with patch("release_driver.load_or_start") as load, patch("release_driver.tick") as tick:
            tick.return_value = {"state": "hold", "reason": "dispatch_not_observed"}
            result = drive(
                self.record, DEVELOPER, {}, now=lambda: self.clock, pause=self.pause, budget=40
            )
            self.assertEqual(result["state"], "waiting")
            self.assertEqual(tick.call_count, 2)
            load.assert_called_once()

    def test_failed_child_stops_without_another_tick(self):
        with patch("release_driver.load_or_start"), patch("release_driver.tick") as tick:
            tick.return_value = {"state": "hold", "reason": "child_unsuccessful", "run_id": 123}
            result = drive(self.record, DEVELOPER, {}, now=lambda: self.clock, pause=self.pause)
            self.assertEqual(result["run_id"], 123)
            tick.assert_called_once()

    def test_complete_release_returns_without_polling(self):
        with patch("release_driver.load_or_start"), patch("release_driver.tick") as tick:
            tick.return_value = {"state": "release_complete"}
            self.assertEqual(
                drive(self.record, DEVELOPER, {}, now=lambda: self.clock, pause=self.pause),
                {"state": "release_complete"},
            )
            self.assertEqual(self.clock, 100)

    def test_uncertain_write_exception_is_not_retried(self):
        def advance(record, **kwargs):
            kwargs["plan"]("backup", {})
            self.fail("Invalid child inputs advanced past validation")

        with (
            patch("release_driver.load_or_start"),
            patch("release_driver.tick", side_effect=advance),
            patch("release_driver.worker_readiness", return_value=None),
            patch("release_driver.plan", return_value={"inputs": {"mode": "backup"}}),
            patch("release_driver.subprocess.run") as validate,
        ):
            validate.return_value.returncode = 1
            validate.return_value.stderr = "Required input missing: review_sha256"
            with self.assertRaisesRegex(
                RuntimeError, "review_sha256; validation failed before dispatch intent"
            ):
                drive(self.record, DEVELOPER, {}, now=lambda: self.clock, pause=self.pause)
            self.assertEqual(validate.call_count, 1)
            self.assertEqual(validate.call_args.args[0][-1], "aws-maintenance.yml")
        with patch("release_driver.load_or_start"), patch("release_driver.tick") as tick:
            tick.side_effect = RuntimeError("uncertain")
            with self.assertRaisesRegex(RuntimeError, "uncertain"):
                drive(self.record, DEVELOPER, {}, now=lambda: self.clock, pause=self.pause)
            tick.assert_called_once()
