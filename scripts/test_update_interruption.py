#!/usr/bin/env python3
"""Test di recupero ripetibile dopo interruzioni simulate."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_backup import (
    backup_application,
    save_backup_manifest,
)
from update_journal import load_journal, save_journal
from update_paths import transaction_paths
from update_restore import recover_simulated_transaction

TXID = "fedcba9876543210fedcba9876543210"


class InterruptionTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "application"
        self.backups = self.root / "backups"

        self.app.mkdir()
        self.backups.mkdir(mode=0o700)

        for name in ("backend", "frontend", "admin"):
            folder = self.app / name
            folder.mkdir()
            (folder / "version.txt").write_text("1.0.0")

        (self.app / "VERSION").write_text("1.0.0\n")

        (self.app / "config").mkdir()
        (self.app / "config/dashboard.ini").write_text("CONFIG")

        (self.app / "data").mkdir()
        (self.app / "data/events.sqlite3").write_text("DATABASE")

        self.paths = transaction_paths(self.backups, TXID)
        self.paths["transaction"].mkdir(mode=0o700)

        backup_application(self.app, self.paths["backup"])
        os.chmod(self.paths["backup"], 0o700)

        save_backup_manifest(
            self.paths["backup"],
            self.paths["manifest"],
        )

        self.journal = {
            "transaction_id": TXID,
            "installation_path": str(self.app),
            "state": "installing",
            "completed_components": ["backend"],
            "pending_component": "frontend",
        }

        save_journal(self.paths["journal"], self.journal)

    def assert_original(self):
        for name in ("backend", "frontend", "admin"):
            self.assertEqual(
                (self.app / name / "version.txt").read_text(),
                "1.0.0",
            )

        self.assertEqual(
            (self.app / "VERSION").read_text().strip(),
            "1.0.0",
        )

        self.assertEqual(
            (self.app / "config/dashboard.ini").read_text(),
            "CONFIG",
        )

        self.assertEqual(
            (self.app / "data/events.sqlite3").read_text(),
            "DATABASE",
        )

    def test_recovery_from_rolling_back(self):
        self.journal["state"] = "rolling_back"
        save_journal(self.paths["journal"], self.journal)

        (self.app / "backend/version.txt").write_text("1.2.3")

        result = recover_simulated_transaction(
            self.backups, TXID, self.app
        )

        self.assertEqual(result["status"], "rolled_back")
        self.assert_original()

    def test_interrupted_restore_then_retry(self):
        (self.app / "backend/version.txt").write_text("1.2.3")

        with patch(
            "update_restore.restore_application",
            side_effect=OSError("Interruzione simulata"),
        ):
            with self.assertRaises(OSError):
                recover_simulated_transaction(
                    self.backups, TXID, self.app
                )

        self.assertEqual(
            load_journal(self.paths["journal"])["state"],
            "rolling_back",
        )

        result = recover_simulated_transaction(
            self.backups, TXID, self.app
        )

        self.assertEqual(result["status"], "rolled_back")
        self.assert_original()

    def test_corrupted_backup_blocks_retry(self):
        self.journal["state"] = "rolling_back"
        save_journal(self.paths["journal"], self.journal)

        (self.paths["backup"] / "backend/version.txt").write_text(
            "ALTERATO"
        )

        with self.assertRaises(ValueError):
            recover_simulated_transaction(
                self.backups, TXID, self.app
            )

        self.assertEqual(
            load_journal(self.paths["journal"])["state"],
            "rolling_back",
        )

    def test_wrong_destination_blocks_retry(self):
        self.journal["state"] = "rolling_back"
        save_journal(self.paths["journal"], self.journal)

        other = self.root / "other"
        other.mkdir()

        with self.assertRaises(RuntimeError):
            recover_simulated_transaction(
                self.backups, TXID, other
            )

    def test_completed_recovery_cannot_repeat(self):
        recover_simulated_transaction(
            self.backups, TXID, self.app
        )

        with self.assertRaises(RuntimeError):
            recover_simulated_transaction(
                self.backups, TXID, self.app
            )

    def test_persistent_data_after_retry(self):
        self.journal["state"] = "rolling_back"
        save_journal(self.paths["journal"], self.journal)

        for name in ("backend", "frontend", "admin"):
            (self.app / name / "version.txt").write_text("1.2.3")

        (self.app / "VERSION").write_text("1.2.3\n")

        recover_simulated_transaction(
            self.backups, TXID, self.app
        )

        self.assert_original()


if __name__ == "__main__":
    unittest.main(verbosity=2)
