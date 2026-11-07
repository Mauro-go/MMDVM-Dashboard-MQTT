#!/usr/bin/env python3
"""Test isolati del recupero delle transazioni."""

import os
import tempfile
import unittest
from pathlib import Path

from update_backup import (
    backup_application,
    save_backup_manifest,
)
from update_journal import load_journal, save_journal
from update_paths import transaction_paths
from update_restore import recover_simulated_transaction

TXID = "1234567890abcdef1234567890abcdef"


class RestoreTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "application"
        self.backups = self.root / "backups"

        self.app.mkdir()
        self.backups.mkdir(mode=0o700)

        for component in ("backend", "frontend", "admin"):
            folder = self.app / component
            folder.mkdir()
            (folder / "version.txt").write_text("1.0.0")

        (self.app / "VERSION").write_text("1.0.0\n")

        (self.app / "config").mkdir()
        (self.app / "config/dashboard.ini").write_text(
            "configurazione"
        )

        (self.app / "data").mkdir()
        (self.app / "data/events.sqlite3").write_text(
            "database"
        )

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

    def assert_persistent(self):
        self.assertEqual(
            (self.app / "config/dashboard.ini").read_text(),
            "configurazione",
        )
        self.assertEqual(
            (self.app / "data/events.sqlite3").read_text(),
            "database",
        )

    def test_recovery_after_partial_update(self):
        (self.app / "backend/version.txt").write_text("1.2.3")

        result = recover_simulated_transaction(
            self.backups, TXID, self.app
        )

        self.assertEqual(result["status"], "rolled_back")
        self.assertEqual(
            (self.app / "backend/version.txt").read_text(),
            "1.0.0",
        )
        self.assertEqual(
            load_journal(self.paths["journal"])["state"],
            "rolled_back",
        )
        self.assert_persistent()

    def test_corrupted_backup_rejected(self):
        (self.paths["backup"] / "backend/version.txt").write_text(
            "ALTERATO"
        )

        with self.assertRaises(ValueError):
            recover_simulated_transaction(
                self.backups, TXID, self.app
            )

        self.assertEqual(
            load_journal(self.paths["journal"])["state"],
            "installing",
        )

    def test_wrong_destination_rejected(self):
        other = self.root / "other"
        other.mkdir()

        with self.assertRaises(RuntimeError):
            recover_simulated_transaction(
                self.backups, TXID, other
            )

    def test_completed_transaction_rejected(self):
        journal = dict(self.journal)
        journal["state"] = "completed"
        journal["completed_components"] = [
            "backend", "frontend", "admin", "VERSION"
        ]
        journal["pending_component"] = None
        save_journal(self.paths["journal"], journal)

        with self.assertRaises(RuntimeError):
            recover_simulated_transaction(
                self.backups, TXID, self.app
            )

    def test_recovery_is_not_repeated(self):
        recover_simulated_transaction(
            self.backups, TXID, self.app
        )

        with self.assertRaises(RuntimeError):
            recover_simulated_transaction(
                self.backups, TXID, self.app
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
