#!/usr/bin/env python3
"""Test isolati del coordinatore sperimentale."""

import tempfile
import unittest
from pathlib import Path

from update_coordinator import run_simulated_update
from update_journal import load_journal
from update_paths import transaction_paths


class CoordinatorTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.application = self.root / "application"
        self.release = self.root / "release"
        self.backups = self.root / "backups"

        self.backups.mkdir(mode=0o700)

        for directory, version in (
            (self.application, "1.0.0"),
            (self.release, "1.2.3"),
        ):
            directory.mkdir()
            for component in ("backend", "frontend", "admin"):
                folder = directory / component
                folder.mkdir()
                (folder / "version.txt").write_text(version)
            (directory / "VERSION").write_text(version + "\n")

        (self.application / "config").mkdir()
        (self.application / "config/dashboard.ini").write_text(
            "configurazione"
        )
        (self.application / "data").mkdir()
        (self.application / "data/events.sqlite3").write_text(
            "database"
        )

    def assert_persistent(self):
        self.assertEqual(
            (self.application / "config/dashboard.ini").read_text(),
            "configurazione",
        )
        self.assertEqual(
            (self.application / "data/events.sqlite3").read_text(),
            "database",
        )

    def test_success(self):
        result = run_simulated_update(
            self.application, self.release, self.backups
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            (self.application / "VERSION").read_text().strip(),
            "1.2.3",
        )
        self.assert_persistent()

        paths = transaction_paths(
            self.backups, result["transaction_id"]
        )
        self.assertEqual(
            load_journal(paths["journal"])["state"],
            "completed",
        )

    def test_rollback_after_backend(self):
        with self.assertRaises(RuntimeError):
            run_simulated_update(
                self.application,
                self.release,
                self.backups,
                fail_after="backend",
            )

        self.assertEqual(
            (self.application / "VERSION").read_text().strip(),
            "1.0.0",
        )
        self.assertEqual(
            (self.application / "backend/version.txt").read_text(),
            "1.0.0",
        )
        self.assert_persistent()

    def test_rollback_after_version(self):
        with self.assertRaises(RuntimeError):
            run_simulated_update(
                self.application,
                self.release,
                self.backups,
                fail_after="VERSION",
            )

        self.assertEqual(
            (self.application / "VERSION").read_text().strip(),
            "1.0.0",
        )
        self.assert_persistent()

    def test_reject_same_source_destination(self):
        with self.assertRaises(ValueError):
            run_simulated_update(
                self.application,
                self.application,
                self.backups,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
