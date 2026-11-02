"""Partition ownership must fail closed before any grouped CI execution."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import ci_groups as groups


class PartitionTests(unittest.TestCase):
    def test_fresh_processes_collect_identical_complete_case_identities(self):
        inventories = []
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, __file__, "--collect-identities"],
                capture_output=True,
                text=True,
                check=True,
            )
            lines = [
                line.removeprefix("CASE_IDS=")
                for line in result.stdout.splitlines()
                if line.startswith("CASE_IDS=")
            ]
            self.assertEqual(len(lines), 1)
            inventory = json.loads(lines[0])
            self.assertEqual(len(inventory), groups.EXPECTED)
            self.assertEqual(len(set(inventory)), groups.EXPECTED)
            for group in groups.GROUPS:
                groups.partition(
                    inventory, group, [str(p) for p in Path("tests").glob("test_*.py")]
                )
            inventories.append(inventory)
        self.assertEqual(inventories[0], inventories[1])

    def test_complete_disjoint_partition_and_invalid_inputs(self):
        ownership = {"a": ["tests/test_a.py"], "b": ["tests/test_b.py"]}
        inventory = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
        files = ["tests/test_a.py", "tests/test_b.py"]
        with patch.object(groups, "GROUPS", ownership), patch.object(groups, "EXPECTED", 2):
            self.assertEqual(groups.partition(inventory, "a", files), inventory[:1])
            self.assertEqual(groups.partition(inventory, "b", files), inventory[1:])
            for nodes, group, names in [
                (inventory[:1], "a", files),
                ([inventory[0], inventory[0]], "a", files),
                (inventory, "unknown", files),
                (inventory, "a", files + ["tests/test_new.py"]),
                ([inventory[0], "tests/test_foreign.py::test_two"], "a", files),
            ]:
                with self.assertRaises(ValueError):
                    groups.partition(nodes, group, names)
            ownership["b"].append(files[0])
            with self.assertRaises(ValueError):
                groups.partition(inventory, "a", files)


if __name__ == "__main__":
    if sys.argv[1:] == ["--collect-identities"]:
        import pytest

        class Inventory:
            def pytest_collection_finish(self, session):
                print("\nCASE_IDS=" + json.dumps(sorted(item.nodeid for item in session.items)))

        raise SystemExit(pytest.main(["--collect-only", "-q"], plugins=[Inventory()]))
    else:
        unittest.main()
