#!/usr/bin/env python3
"""Test della diagnostica di recupero delle rinomine."""

import tempfile
import unittest
from pathlib import Path

from update_rename_plan import (
    create_rename_plan,
    save_rename_plan,
)
from update_swap_recovery import inspect_swap_recovery

TXID = "0123456789abcdef0123456789abcdef"


class SwapRecoveryTests(unittest.TestCase):

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
        self.plan_path = self.root / "rename-plan.json"

    def inspect(self):
        save_rename_plan(self.plan_path, self.plan)
        return inspect_swap_recovery(self.app, self.plan_path)

    def test_clean_planned(self):
        result = self.inspect()
        self.assertFalse(result["requires_review"])

    def test_old_moved(self):
        previous = self.plan["operations"]["backend"]["previous"]
        (self.app / "backend").rename(self.app / previous)

        result = self.inspect()
        self.assertEqual(
            result["components"]["backend"]["classification"],
            "old_moved_target_missing",
        )

    def test_old_and_new_present(self):
        previous = self.plan["operations"]["backend"]["previous"]
        (self.app / previous).mkdir()

        result = self.inspect()
        self.assertEqual(
            result["components"]["backend"]["classification"],
            "old_and_new_present",
        )

    def test_prepared_with_target(self):
        prepared = self.plan["operations"]["frontend"]["prepared"]
        (self.app / prepared).mkdir()

        result = self.inspect()
        self.assertEqual(
            result["components"]["frontend"]["classification"],
            "prepared_with_target",
        )

    def test_prepared_target_missing(self):
        prepared = self.plan["operations"]["frontend"]["prepared"]
        (self.app / "frontend").rmdir()
        (self.app / prepared).mkdir()

        result = self.inspect()
        self.assertEqual(
            result["components"]["frontend"]["classification"],
            "prepared_target_missing",
        )

    def test_all_missing(self):
        (self.app / "admin").rmdir()

        result = self.inspect()
        self.assertEqual(
            result["components"]["admin"]["classification"],
            "all_missing",
        )

    def test_symlink_detected(self):
        previous = self.plan["operations"]["backend"]["previous"]
        (self.app / previous).symlink_to("/etc/passwd")

        result = self.inspect()
        self.assertEqual(
            result["components"]["backend"]["classification"],
            "unsafe_symlink",
        )

    def test_nonfinal_state_requires_review(self):
        self.plan["operations"]["backend"]["state"] = "old_moved"

        result = self.inspect()
        self.assertTrue(
            result["components"]["backend"]["requires_review"]
        )

    def test_read_only(self):
        before = sorted(p.name for p in self.app.iterdir())
        self.inspect()
        after = sorted(p.name for p in self.app.iterdir())

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
