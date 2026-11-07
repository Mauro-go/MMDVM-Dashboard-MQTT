#!/usr/bin/env python3
"""Test del tracciamento delle rinomine."""

import tempfile
import unittest
from pathlib import Path

from update_rename_plan import (
    create_rename_plan,
    inspect_rename_plan,
    load_rename_plan,
    save_rename_plan,
    validate_rename_plan,
)

TXID = "0123456789abcdef0123456789abcdef"


class RenamePlanTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "application"
        self.app.mkdir()

        for component in ("backend", "frontend", "admin"):
            (self.app / component).mkdir()

        (self.app / "VERSION").write_text("1.0.0\n")

        self.plan = create_rename_plan(TXID)
        self.path = self.root / "rename-plan.json"

    def test_create_plan(self):
        self.assertTrue(validate_rename_plan(self.plan))
        self.assertEqual(len(self.plan["operations"]), 4)

    def test_save_and_load(self):
        save_rename_plan(self.path, self.plan)
        self.assertEqual(load_rename_plan(self.path), self.plan)

    def test_invalid_transaction(self):
        with self.assertRaises(ValueError):
            create_rename_plan("../invalid")

    def test_invalid_component(self):
        self.plan["operations"]["config"] = {
            "state": "planned"
        }

        with self.assertRaises(ValueError):
            validate_rename_plan(self.plan)

    def test_modified_path(self):
        self.plan["operations"]["backend"]["previous"] = (
            "../../etc/passwd"
        )

        with self.assertRaises(ValueError):
            validate_rename_plan(self.plan)

    def test_detect_old_component(self):
        previous = self.plan["operations"]["backend"]["previous"]

        (self.app / "backend").rename(self.app / previous)

        result = inspect_rename_plan(self.app, self.plan)

        self.assertTrue(
            result["backend"]["paths"]["previous"]["exists"]
        )
        self.assertFalse(
            result["backend"]["paths"]["target"]["exists"]
        )

    def test_detect_prepared_component(self):
        prepared = self.plan["operations"]["frontend"]["prepared"]
        (self.app / prepared).mkdir()

        result = inspect_rename_plan(self.app, self.plan)

        self.assertTrue(
            result["frontend"]["paths"]["prepared"]["exists"]
        )

    def test_reject_symlink_plan(self):
        self.path.symlink_to("/etc/passwd")

        with self.assertRaises(ValueError):
            save_rename_plan(self.path, self.plan)

    def test_read_only_inspection(self):
        before = sorted(p.name for p in self.app.iterdir())

        inspect_rename_plan(self.app, self.plan)

        after = sorted(p.name for p in self.app.iterdir())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
