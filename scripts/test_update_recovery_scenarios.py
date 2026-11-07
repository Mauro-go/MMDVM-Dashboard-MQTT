#!/usr/bin/env python3
"""Scenari isolati di recupero delle transazioni."""

import os
import tempfile
import unittest
from pathlib import Path

from update_backup import backup_application, save_backup_manifest
from update_journal import save_journal
from update_paths import transaction_paths
from update_recovery import preflight_recovery

TXID = "abcdef0123456789abcdef0123456789"


class RecoveryScenarioTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.backup_root = self.root / "transactions"
        self.backup_root.mkdir(mode=0o700)

        self.app = self.root / "application"
        self.app.mkdir()

        for component in ("backend", "frontend", "admin"):
            folder = self.app / component
            folder.mkdir()
            (folder / "version.txt").write_text("1.0.0")

        (self.app / "VERSION").write_text("1.0.0\n")

        self.paths = transaction_paths(self.backup_root, TXID)
        self.paths["transaction"].mkdir(mode=0o700)

        backup_application(self.app, self.paths["backup"])
        os.chmod(self.paths["backup"], 0o700)

        save_backup_manifest(
            self.paths["backup"],
            self.paths["manifest"],
        )

        self.original_version = (
            self.app / "VERSION"
        ).read_text()

    def write_journal(self, state, completed=None, pending=None):
        save_journal(
            self.paths["journal"],
            {
                "state": state,
                "transaction_id": TXID,
                "installation_path": str(self.app),
                "completed_components": completed or [],
                "pending_component": pending,
            },
        )

    def test_interrupted_installation(self):
        self.write_journal(
            "installing",
            ["backend"],
            "frontend",
        )

        result = preflight_recovery(
            self.backup_root, TXID, self.app
        )

        self.assertTrue(result["authorized_for_review"])
        self.assertEqual(
            (self.app / "VERSION").read_text(),
            self.original_version,
        )

    def test_corrupted_backup(self):
        self.write_journal("installing")

        target = self.paths["backup"] / "backend/version.txt"
        target.write_text("ALTERATO")

        with self.assertRaises(ValueError):
            preflight_recovery(
                self.backup_root, TXID, self.app
            )

    def test_wrong_destination(self):
        self.write_journal("installing")

        other = self.root / "other"
        other.mkdir()

        with self.assertRaises(RuntimeError):
            preflight_recovery(
                self.backup_root, TXID, other
            )

    def test_completed_transaction(self):
        self.write_journal(
            "completed",
            ["backend", "frontend", "admin", "VERSION"],
        )

        # Il completamento non deve autorizzare un rollback.
        try:
            result = preflight_recovery(
                self.backup_root, TXID, self.app
            )
        except (RuntimeError, ValueError):
            return

        self.assertFalse(
            result.get("recovery_required", False)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
