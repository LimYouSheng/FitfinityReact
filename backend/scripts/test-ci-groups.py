"""Partition ownership must fail closed before any grouped CI execution."""

import unittest
from unittest.mock import patch

import ci_groups as groups


class PartitionTests(unittest.TestCase):
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
    unittest.main()
