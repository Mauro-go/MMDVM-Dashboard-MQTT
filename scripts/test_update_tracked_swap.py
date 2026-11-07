#!/usr/bin/env python3
"""Test della sostituzione con tracciamento persistente."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_rename_plan import (
    create_rename_plan,
    load_rename_plan,
)
from update_tracked_swap import (
    finish_tracked_swap,
    tracked_swap,
)

TXID = "0123456789abcdef0123456789abcdef"


class TrackedSwapTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "application"
        self.release = self.root / "release"
        self.transaction = self.root / "transaction"

        self.transaction.mkdir(mode=0o700)

        for directory, version in (
            (self.app, "1.0.0"),
            (self.release, "1.2.3"),
        ):
            directory.mkdir()

            for component in ("backend", "frontend", "admin"):
                folder = directory / component
                folder.mkdir()
                (folder / "version.txt").write_text(version)

            (directory / "VERSION").write_text(version + "\n")

        (self.app / "data").mkdir()
        (self.app / "data/events.sqlite3").write_text("DATABASE")

        self.plan = create_rename_plan(TXID)
        self.plan_path = self.transaction / "rename-plan.json"

    def test_success_backend(self):
        result = tracked_swap(
            self.release, self.app, "backend",
            self.plan, self.plan_path,
        )

        self.assertEqual(result["state"], "new_installed")
        self.assertEqual(
            (self.app / "backend/version.txt").read_text(),
            "1.2.3",
        )

        previous = self.plan["operations"]["backend"]["previous"]
        self.assertTrue((self.app / previous).exists())

    def test_persistent_data_unchanged(self):
        tracked_swap(
            self.release, self.app, "backend",
            self.plan, self.plan_path,
        )

        self.assertEqual(
            (self.app / "data/events.sqlite3").read_text(),
            "DATABASE",
        )

    def test_plan_saved(self):
        tracked_swap(
            self.release, self.app, "backend",
            self.plan, self.plan_path,
        )

        saved = load_rename_plan(self.plan_path)

        self.assertEqual(
            saved["operations"]["backend"]["state"],
            "new_installed",
        )

    def test_failure_after_old_rename(self):
        original_rename = __import__("os").rename

        def interrupt(source, destination):
            if Path(destination).name == "backend":
                raise OSError("Interruzione simulata")
            return original_rename(source, destination)

        with patch(
            "update_tracked_swap.os.rename",
            side_effect=interrupt,
        ):
            with self.assertRaises(OSError):
                tracked_swap(
                    self.release, self.app, "backend",
                    self.plan, self.plan_path,
                )

        previous = self.plan["operations"]["backend"]["previous"]

        self.assertTrue((self.app / previous).exists())
        self.assertFalse((self.app / "backend").exists())

        saved = load_rename_plan(self.plan_path)
        self.assertEqual(
            saved["operations"]["backend"]["state"],
            "old_moved",
        )

    def test_finish(self):
        tracked_swap(
            self.release, self.app, "backend",
            self.plan, self.plan_path,
        )

        self.assertTrue(
            finish_tracked_swap(
                self.app, "backend",
                self.plan, self.plan_path,
            )
        )

        previous = self.plan["operations"]["backend"]["previous"]
        self.assertFalse((self.app / previous).exists())

        saved = load_rename_plan(self.plan_path)
        self.assertEqual(
            saved["operations"]["backend"]["state"],
            "done",
        )

    def test_reject_second_swap(self):
        tracked_swap(
            self.release, self.app, "backend",
            self.plan, self.plan_path,
        )

        with self.assertRaises(RuntimeError):
            tracked_swap(
                self.release, self.app, "backend",
                self.plan, self.plan_path,
            )

    def test_reject_symlink_source(self):
        (self.release / "backend/version.txt").unlink()
        (self.release / "backend/version.txt").symlink_to(
            "/etc/passwd"
        )

        with self.assertRaises(ValueError):
            tracked_swap(
                self.release, self.app, "backend",
                self.plan, self.plan_path,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
