"""Offline rejection probes for the current-source release inventory."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from release_readiness import migration_chain, report


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "backend/migrations/versions"
        self.directory.mkdir(parents=True)
        infrastructure = self.root / "backend/infrastructure"
        infrastructure.mkdir()
        (infrastructure / "test-db-migration-contract.json").write_text(
            json.dumps({"revisions": ["old_schema"]})
        )
        (infrastructure / "private-runtime-contract.json").write_text(
            json.dumps({"revision": "b" * 40})
        )

    def write(self, name, revision, parent):
        path = self.directory / name
        path.write_text(f"revision = {revision!r}\ndown_revision = {parent!r}\n")
        return path

    def test_order_and_content_fingerprint(self):
        tail = self.write("a.py", "second", "first")
        self.write("z.py", "first", None)
        chain = migration_chain(self.directory)
        self.assertEqual([item["revision"] for item in chain], ["first", "second"])
        self.assertEqual(chain[-1]["sha256"], hashlib.sha256(tail.read_bytes()).hexdigest())
        tail.write_text(tail.read_text() + "# changed\n")
        self.assertNotEqual(chain[-1]["sha256"], migration_chain(self.directory)[-1]["sha256"])

    def test_missing_parent(self):
        self.write("a.py", "first", "missing")
        with self.assertRaises(ValueError):
            migration_chain(self.directory)

    def test_cycle(self):
        self.write("a.py", "first", "second")
        self.write("b.py", "second", "first")
        with self.assertRaises(ValueError):
            migration_chain(self.directory)

    def test_branch(self):
        self.write("a.py", "first", None)
        self.write("b.py", "second", "first")
        self.write("c.py", "third", "first")
        with self.assertRaises(ValueError):
            migration_chain(self.directory)

    def test_duplicate_and_empty(self):
        with self.assertRaises(ValueError):
            migration_chain(self.directory)
        self.write("a.py", "first", None)
        self.write("b.py", "first", None)
        with self.assertRaises(ValueError):
            migration_chain(self.directory)

    def test_dynamic_declaration_never_executed(self):
        marker = self.root / "executed"
        (self.directory / "a.py").write_text(
            f"revision = open({str(marker)!r}, 'w')\ndown_revision = None\n"
        )
        with self.assertRaises(ValueError):
            migration_chain(self.directory)
        self.assertFalse(marker.exists())

    def test_report_always_holds_and_preserves_historical_contracts(self):
        self.write("a.py", "current", None)
        before = {path: path.read_bytes() for path in self.root.rglob("*.json")}
        result = report(self.root, "a" * 40)
        self.assertEqual(result["deployment_decision"], "HOLD")
        self.assertEqual(result["current_schema_head"], "current")
        self.assertEqual(result["historical_bootstrap_head"], "old_schema")
        self.assertEqual(result["aws_observation"], "not performed")
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertTrue(result["required_before_rollout"])
        self.assertTrue(result["not_established"])

    def test_reject_nonexact_source(self):
        for revision in ["main", "a" * 39, "a" * 41, "$(command)"]:
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                report(self.root, revision)


if __name__ == "__main__":
    unittest.main()
