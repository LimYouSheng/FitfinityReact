"""Exercise explicit handover proof, immutable applied migrations and downstream ownership."""

import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from backup_handover import chain_at, migration_evidence, proposal, validate
from backup_transition import prepare_transition
from deployment_profile import DEVELOPER, fingerprint
from upgrade_continuity import evidence


class HandoverTests(unittest.TestCase):
    def setUp(self):
        self.old, self.new = "a" * 40, "b" * 40
        self.base = [
            {"revision": "0052", "down_revision": None, "file": "old.py", "sha256": "1" * 64}
        ]
        self.next = self.base + [
            {"revision": "0053", "down_revision": "0052", "file": "new.py", "sha256": "2" * 64}
        ]
        self.maintenance = {
            "identity": {
                "source_sha": self.old,
                "profile_sha256": fingerprint(DEVELOPER),
                "operation_id": "c" * 32,
                "review_sha256": "d" * 64,
            },
            "state": "snapshot_ready",
            "snapshot_requested": True,
            "runtime_sha256": "e" * 64,
        }
        self.catalog = {"alembic_revisions": ["0052"]}
        for target, kwargs in (
            (
                "backup_handover.chain_at",
                {
                    "side_effect": lambda source: deepcopy(
                        self.base if source == self.old else self.next
                    )
                },
            ),
            ("backup_handover.subprocess.run", {"return_value": SimpleNamespace(returncode=0)}),
            ("backup_handover.subprocess.check_output", {"return_value": "same-sql-blob"}),
            (
                "backup_transition.source_fingerprint",
                {"side_effect": lambda source: ("1" if source == self.old else "2") * 64},
            ),
        ):
            mock = patch(target, **kwargs)
            mock.start()
            self.addCleanup(mock.stop)

    def test_explicit_review_allows_forward_extension_without_rewriting_receipt(self):
        original = deepcopy(self.maintenance)
        with self.assertRaises(RuntimeError):
            prepare_transition(self.maintenance, self.catalog, self.new)
        plan = proposal(self.maintenance, self.catalog, self.new)
        result = prepare_transition(self.maintenance, self.catalog, self.new, handover=plan)
        self.assertEqual(result["handover"], plan)
        self.assertEqual(validate(plan, self.old, self.new), "2" * 64)
        self.assertEqual(self.maintenance, original)

    def test_changed_applied_migrations_and_nonforward_or_foreign_source_rejected(self):
        for changed in (
            self.base,
            [{**self.base[0], "sha256": "0" * 64}] + self.next[1:],
            self.next[1:],
        ):
            with patch("backup_handover.chain_at", side_effect=[self.base, changed]):
                with self.assertRaises(RuntimeError):
                    migration_evidence(self.old, self.new, "0052")
        with self.assertRaises(RuntimeError):
            migration_evidence(self.old, self.new, "other")
        with patch("backup_handover.subprocess.run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(RuntimeError):
                proposal(self.maintenance, self.catalog, self.new)
        with patch("backup_handover.subprocess.check_output", side_effect=["old", "new"]):
            with self.assertRaises(RuntimeError):
                proposal(self.maintenance, self.catalog, self.new)

    def test_tampered_or_unready_review_never_authorizes_transition(self):
        plan = proposal(self.maintenance, self.catalog, self.new)
        for key in plan:
            changed = {**plan, key: "tampered"}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                prepare_transition(self.maintenance, self.catalog, self.new, handover=changed)
        with self.assertRaises(RuntimeError):
            proposal({**self.maintenance, "state": "snapshot_submitted"}, self.catalog, self.new)

    def test_completed_upgrade_carries_original_marker_into_rollout(self):
        plan = proposal(self.maintenance, self.catalog, self.new)
        transition = prepare_transition(self.maintenance, self.catalog, self.new, handover=plan)
        receipt = {
            "result": {"source_sha": self.new},
            "readiness": {"maintenance_identity": self.maintenance["identity"]},
            "backup_transition": transition,
        }
        proof = evidence(receipt, self.new, DEVELOPER)
        self.assertEqual(
            proof["maintenance_marker"], ":".join(("c" * 32, self.old, fingerprint(DEVELOPER)))
        )
        for key in ("maintenance_sha256", "baseline_catalog_sha256", "inputs_sha256"):
            broken = deepcopy(receipt)
            broken["backup_transition"][key] = "0" * 64
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                evidence(broken, self.new, DEVELOPER)

    def test_real_migration_parser_reads_git_blobs_without_executing_them(self):
        listing = b"100644 blob " + b"1" * 40 + b"\tbackend/migrations/versions/old.py\0"
        code = b"revision = '0052'\ndown_revision = None\nraise RuntimeError('must not execute')\n"
        with patch("backup_handover.subprocess.check_output", side_effect=[listing, code]):
            result = chain_at(self.old)
        self.assertEqual(result[0]["revision"], "0052")
        with patch(
            "backup_handover.subprocess.check_output",
            return_value=listing.replace(b"100644", b"120000"),
        ):
            with self.assertRaises(RuntimeError):
                chain_at(self.old)


if __name__ == "__main__":
    unittest.main()
