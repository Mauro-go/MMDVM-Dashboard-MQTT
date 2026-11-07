#!/usr/bin/env python3
"""Test di sicurezza del coordinatore sperimentale."""

import tempfile
import unittest
from pathlib import Path

from update_coordinator import (
    check_previous_transactions,
    run_simulated_update,
)
from update_journal import save_journal


class CoordinatorSafetyTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "app"
        self.release = self.root / "release"
        self.backups = self.root / "backups"
        self.backups.mkdir(mode=0o700)

        for path, version in (
            (self.app, "1.0.0"),
            (self.release, "1.2.3"),
        ):
            path.mkdir()
            for component in ("backend", "frontend", "admin"):
                folder = path / component
                folder.mkdir()
                (folder / "version.txt").write_text(version)
            (path / "VERSION").write_text(version + "\n")

    def make_transaction(self, state):
        directory = self.backups / ("a" * 32)
        directory.mkdir(mode=0o700, exist_ok=True)

        save_journal(
            directory / "journal.json",
            {
                "transaction_id": "a" * 32,
                "installation_path": str(self.app),
                "state": state,
                "completed_components": [],
                "pending_component": None,
            },
        )

    def test_no_previous_transactions(self):
        check_previous_transactions(self.backups)

    def test_incomplete_transaction_blocked(self):
        self.make_transaction("installing")

        with self.assertRaises(RuntimeError):
            run_simulated_update(
                self.app, self.release, self.backups
            )

        self.assertEqual(
            (self.app / "VERSION").read_text().strip(),
            "1.0.0",
        )

    def test_completed_transaction_allowed(self):
        self.make_transaction("completed")
        check_previous_transactions(self.backups)

    def test_rolled_back_transaction_allowed(self):
        self.make_transaction("rolled_back")
        check_previous_transactions(self.backups)

    def test_missing_journal_blocked(self):
        (self.backups / ("b" * 32)).mkdir()

        with self.assertRaises(RuntimeError):
            check_previous_transactions(self.backups)

    def test_consecutive_updates(self):
        first = run_simulated_update(
            self.app, self.release, self.backups
        )
        second = run_simulated_update(
            self.app, self.release, self.backups
        )

        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
