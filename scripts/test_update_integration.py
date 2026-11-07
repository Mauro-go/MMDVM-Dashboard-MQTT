#!/usr/bin/env python3
"""Test integrati del sistema di aggiornamento MMDVM Dashboard."""

import os
import tempfile
import unittest
from pathlib import Path

from update_backup import backup_application, save_backup_manifest
from update_diagnostics import diagnose_update
from update_health import check_services_health
from update_journal import load_journal, save_journal
from update_lock import update_lock
from update_paths import transaction_paths
from update_recovery import (
    ensure_update_allowed,
    inspect_transaction_recovery,
    preflight_recovery,
)

TRANSACTION_ID = "0123456789abcdef0123456789abcdef"


class UpdateIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.backup_root = self.root / "updates"
        self.backup_root.mkdir(mode=0o700)

        self.app = self.root / "application"
        self.app.mkdir()

        for name in ("backend", "frontend", "admin"):
            folder = self.app / name
            folder.mkdir()
            (folder / "test.txt").write_text("originale")

        (self.app / "VERSION").write_text("1.0.0\n")

        self.paths = transaction_paths(
            self.backup_root, TRANSACTION_ID
        )
        self.paths["transaction"].mkdir(mode=0o700)

        backup_application(self.app, self.paths["backup"])
        os.chmod(self.paths["backup"], 0o700)

        save_backup_manifest(
            self.paths["backup"],
            self.paths["manifest"],
        )

        self.journal = {
            "state": "installing",
            "completed_components": ["backend"],
            "pending_component": "frontend",
            "transaction_id": TRANSACTION_ID,
            "installation_path": str(self.app),
        }

        save_journal(self.paths["journal"], self.journal)

    def test_01_backup_and_transaction(self):
        result = inspect_transaction_recovery(
            self.backup_root, TRANSACTION_ID
        )
        self.assertTrue(result["backup_verified"])
        self.assertTrue(result["recovery_required"])

    def test_02_recovery_preflight(self):
        result = preflight_recovery(
            self.backup_root, TRANSACTION_ID, self.app
        )
        self.assertTrue(result["authorized_for_review"])

    def test_03_new_update_blocked(self):
        with self.assertRaises(RuntimeError):
            ensure_update_allowed(self.paths["journal"])

    def test_04_corrupted_backup(self):
        target = self.paths["backup"] / "backend" / "test.txt"
        target.write_text("MANOMESSO")

        with self.assertRaises(ValueError):
            preflight_recovery(
                self.backup_root, TRANSACTION_ID, self.app
            )

    def test_05_wrong_destination(self):
        other = self.root / "other"
        other.mkdir()

        with self.assertRaises(RuntimeError):
            preflight_recovery(
                self.backup_root, TRANSACTION_ID, other
            )

    def test_06_wrong_transaction(self):
        journal = dict(self.journal)
        journal["transaction_id"] = "f" * 32
        save_journal(self.paths["journal"], journal)

        with self.assertRaises(RuntimeError):
            inspect_transaction_recovery(
                self.backup_root, TRANSACTION_ID
            )

    def test_07_diagnostics(self):
        result = diagnose_update(
            self.paths["journal"], self.paths["backup"]
        )
        self.assertEqual(result["status"], "RECOVERY_REQUIRED")

    def test_08_lock(self):
        lock = self.root / "update.lock"

        with update_lock(lock):
            with self.assertRaises(RuntimeError):
                with update_lock(lock):
                    pass

        with update_lock(lock):
            pass

    def test_09_services(self):
        snapshot = {
            "mmdvm-dashboard-mqtt.service": {
                "active": "active", "enabled": "enabled"
            },
            "mmdvm-mqtt-collector.service": {
                "active": "active", "enabled": "enabled"
            },
            "mmdvm-telegram-bot.service": {
                "active": "inactive", "enabled": "disabled"
            },
        }

        self.assertTrue(check_services_health(
            snapshot,
            runner=lambda service: snapshot[service]["active"],
        ))

    def test_10_completed_transaction(self):
        journal = dict(self.journal)
        journal["state"] = "completed"
        journal["completed_components"] = [
            "backend", "frontend", "admin", "VERSION"
        ]
        journal["pending_component"] = None

        save_journal(self.paths["journal"], journal)

        self.assertTrue(
            ensure_update_allowed(self.paths["journal"])
        )

        self.assertEqual(
            load_journal(self.paths["journal"])["state"],
            "completed",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
