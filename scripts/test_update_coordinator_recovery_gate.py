import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from update_backup import backup_application, save_backup_manifest
from update_coordinator import check_previous_transactions
from update_journal import save_journal
from update_paths import transaction_paths


class CoordinatorRecoveryGateTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = self.root / "application"
        self.backups = self.root / "backups"
        self.app.mkdir()
        self.backups.mkdir()

        for name in ("backend", "frontend", "admin"):
            folder = self.app / name
            folder.mkdir()
            (folder / "example.txt").write_text("original")

        (self.app / "VERSION").write_text("1.0")

        self.transaction_id = uuid.uuid4().hex
        self.paths = transaction_paths(
            self.backups, self.transaction_id
        )
        self.paths["transaction"].mkdir(mode=0o700)

        backup_application(self.app, self.paths["backup"])
        save_backup_manifest(
            self.paths["backup"], self.paths["manifest"]
        )

    def journal(self, state):
        save_journal(self.paths["journal"], {
            "transaction_id": self.transaction_id,
            "installation_path": str(self.app),
            "state": state,
            "completed_components": [],
            "pending_component": None,
        })

    def test_prepared_requires_recovery(self):
        self.journal("prepared")
        with self.assertRaisesRegex(RuntimeError, "recupero richiesto"):
            check_previous_transactions(self.backups)

    def test_installing_requires_recovery(self):
        self.journal("installing")
        with self.assertRaisesRegex(RuntimeError, "recupero richiesto"):
            check_previous_transactions(self.backups)

    def test_completed_allows_updates(self):
        self.journal("completed")
        check_previous_transactions(self.backups)

    def test_rolled_back_allows_updates(self):
        self.journal("rolled_back")
        check_previous_transactions(self.backups)

    def test_corrupted_backup_blocks_updates(self):
        self.journal("installing")
        (self.paths["backup"] / "VERSION").write_text("corrupt")

        with self.assertRaisesRegex(RuntimeError, "non verificabile"):
            check_previous_transactions(self.backups)

    def test_recovery_inspection_does_not_restore(self):
        self.journal("installing")
        (self.app / "VERSION").write_text("2.0")

        with patch(
            "update_coordinator.restore_application",
            side_effect=AssertionError("Rollback non autorizzato"),
        ):
            with self.assertRaises(RuntimeError):
                check_previous_transactions(self.backups)

        self.assertEqual(
            (self.app / "VERSION").read_text(), "2.0"
        )


if __name__ == "__main__":
    unittest.main()
