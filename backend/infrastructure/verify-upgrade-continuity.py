"""Prove completed upgrades preserve original ownership without weakening source checks."""

import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from deployment_profile import DEVELOPER, fingerprint
from upgrade_continuity import bind_marker, evidence


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.target = fingerprint(DEVELOPER)
        self.receipt = {
            "result": {"source_sha": "b" * 40},
            "readiness": {
                "maintenance_identity": {
                    "source_sha": "a" * 40,
                    "operation_id": "d" * 32,
                    "profile_sha256": self.target,
                    "review_sha256": "e" * 64,
                }
            },
            "backup_transition": {
                "from_source": "a" * 40,
                "to_source": "b" * 40,
                "inputs_sha256": "f" * 64,
                "maintenance_sha256": "1" * 64,
                "baseline_catalog_sha256": "2" * 64,
            },
        }
        self.review = {
            "source_sha": "c" * 40,
            "profile_sha256": self.target,
            "maintenance_marker": "d" * 32 + ":" + "a" * 40 + ":" + self.target,
        }
        self.tree = patch("upgrade_continuity.source_fingerprint", return_value="f" * 64)
        self.ancestor = patch(
            "upgrade_continuity.subprocess.run", return_value=SimpleNamespace(returncode=0)
        )
        self.tree.start()
        self.ancestor.start()
        self.addCleanup(self.tree.stop)
        self.addCleanup(self.ancestor.stop)

    def test_completed_upgrade_carries_original_marker_without_receipt_mutation(self):
        original = deepcopy(self.receipt)
        proof = evidence(self.receipt, "c" * 40, DEVELOPER)
        bind_marker(self.review, {"schema_action": "upgrade", "upgrade_continuity": proof})
        self.assertEqual(proof["maintenance_marker"], self.review["maintenance_marker"])
        self.assertEqual(proof["upgrade_source"], "b" * 40)
        self.assertEqual(self.receipt, original)

    def test_changed_inputs_and_nonancestor_source_are_rejected(self):
        with patch("upgrade_continuity.source_fingerprint", side_effect=["f" * 64, "0" * 64]):
            with self.assertRaisesRegex(RuntimeError, "inputs changed"):
                evidence(self.receipt, "c" * 40, DEVELOPER)
        with patch("upgrade_continuity.subprocess.run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "not an ancestor"):
                evidence(self.receipt, "c" * 40, DEVELOPER)

    def test_foreign_maintenance_and_tampered_transition_are_rejected(self):
        for owner, key, value in (
            ("maintenance", "profile_sha256", "0" * 64),
            ("transition", "from_source", "0" * 40),
            ("transition", "inputs_sha256", "0" * 64),
        ):
            changed = deepcopy(self.receipt)
            target = (
                changed["readiness"]["maintenance_identity"]
                if owner == "maintenance"
                else changed["backup_transition"]
            )
            target[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                evidence(changed, "c" * 40, DEVELOPER)

    def test_previous_marker_requires_matching_upgrade_proof(self):
        proof = evidence(self.receipt, "c" * 40, DEVELOPER)
        for collected in (
            {},
            {"schema_action": "unchanged", "upgrade_continuity": proof},
            {"schema_action": "upgrade", "upgrade_continuity": {**proof, "source_sha": "a" * 40}},
            {
                "schema_action": "upgrade",
                "upgrade_continuity": {**proof, "maintenance_marker": "foreign"},
            },
        ):
            with self.subTest(collected=collected), self.assertRaises(RuntimeError):
                bind_marker(self.review, collected)

    def test_operator_entry_points_reject_missing_proof_before_provider_calls(self):
        from resumption_operator import execute_step as resume
        from rollout_operator import execute_step as rollout

        for operation, mode, options in (
            (rollout, "upload", {}),
            (rollout, "execute", {}),
            (resume, "resume-create", {"verified": {}}),
            (resume, "resume-finalize", {"verified": {}}),
        ):
            call, persist = Mock(), Mock()
            with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, "continuity"):
                operation(mode, self.review, {}, None, call, persist, profile=DEVELOPER, **options)
            call.assert_not_called()
            persist.assert_not_called()

    def test_cross_source_upgrade_cannot_omit_original_maintenance_identity(self):
        del self.receipt["readiness"]
        with self.assertRaises(RuntimeError):
            evidence(self.receipt, "c" * 40, DEVELOPER)
        self.assertIsNone(evidence(self.receipt, "b" * 40, DEVELOPER))


if __name__ == "__main__":
    unittest.main()
