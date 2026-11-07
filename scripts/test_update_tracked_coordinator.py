#!/usr/bin/env python3
"""Test integrazione coordinatore e sostituzione tracciata."""

import tempfile
import unittest
from pathlib import Path

from update_coordinator import run_simulated_update


class TrackedCoordinatorTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "application"
        self.release = self.root / "release"
        self.backups = self.root / "backups"
        self.backups.mkdir(mode=0o700)

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

    def test_tracked_success(self):
        result = run_simulated_update(
            self.app,
            self.release,
            self.backups,
            tracked=True,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            (self.app / "VERSION").read_text().strip(),
            "1.2.3",
        )

        self.assertEqual(
            (self.app / "data/events.sqlite3").read_text(),
            "DATABASE",
        )

        self.assertTrue(
            list(self.app.glob(".update-old-*"))
        )

    def test_tracked_failure_rolls_back(self):
        with self.assertRaises(RuntimeError):
            run_simulated_update(
                self.app,
                self.release,
                self.backups,
                fail_after="frontend",
                tracked=True,
            )

        self.assertEqual(
            (self.app / "backend/version.txt").read_text(),
            "1.0.0",
        )

        self.assertEqual(
            (self.app / "VERSION").read_text().strip(),
            "1.0.0",
        )

        self.assertEqual(
            (self.app / "data/events.sqlite3").read_text(),
            "DATABASE",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
