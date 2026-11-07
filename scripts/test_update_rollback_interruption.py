import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from update_backup import (
    backup_application,
    save_backup_manifest,
)
from update_journal import load_journal, save_journal
from update_paths import transaction_paths
from update_restore import recover_simulated_transaction
from update_service_flow import rollback_completed_update


class RollbackInterruptionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        root = Path(self.tmp.name)
        self.app = root / "application"
        self.backups = root / "backups"

        self.app.mkdir()
        self.backups.mkdir()

        for component in ("backend", "frontend", "admin"):
            folder = self.app / component
            folder.mkdir()
            (folder / "test.txt").write_text("original")

        (self.app / "VERSION").write_text("1.0")

        self.transaction_id = uuid.uuid4().hex
        self.paths = transaction_paths(
            self.backups, self.transaction_id
        )
        self.paths["transaction"].mkdir(mode=0o700)

        backup_application(self.app, self.paths["backup"])
        save_backup_manifest(
            self.paths["backup"],
            self.paths["manifest"],
        )

        for component in ("backend", "frontend", "admin"):
            (self.app / component / "test.txt").write_text("updated")

        (self.app / "VERSION").write_text("2.0")

        save_journal(self.paths["journal"], {
            "transaction_id": self.transaction_id,
            "installation_path": str(self.app),
            "state": "completed",
            "completed_components": [
                "backend", "frontend", "admin", "VERSION"
            ],
            "pending_component": None,
        })

    def assert_original_restored(self):
        for component in ("backend", "frontend", "admin"):
            self.assertEqual(
                (self.app / component / "test.txt").read_text(),
                "original",
            )
        self.assertEqual(
            (self.app / "VERSION").read_text(), "1.0"
        )

    def test_interrupted_rollback_can_resume(self):
        import update_service_flow

        real_restore = update_service_flow.restore_application

        def interrupted_restore(backup, destination, manifest):
            (destination / "backend" / "test.txt").write_text(
                "original"
            )
            raise RuntimeError("Interruzione simulata")

        with patch.object(
            update_service_flow,
            "restore_application",
            side_effect=interrupted_restore,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "Interruzione simulata"
            ):
                rollback_completed_update(
                    self.backups, self.transaction_id, self.app
                )

        journal = load_journal(self.paths["journal"])
        self.assertEqual(journal["state"], "rolling_back")

        result = recover_simulated_transaction(
            self.backups, self.transaction_id, self.app
        )

        self.assertEqual(result["status"], "rolled_back")
        self.assert_original_restored()
        self.assertEqual(
            load_journal(self.paths["journal"])["state"],
            "rolled_back",
        )

    def test_corrupted_backup_prevents_rollback(self):
        (self.paths["backup"] / "VERSION").write_text("corrupt")

        with self.assertRaises(ValueError):
            rollback_completed_update(
                self.backups, self.transaction_id, self.app
            )

        self.assertEqual(
            load_journal(self.paths["journal"])["state"],
            "completed",
        )
        self.assertEqual(
            (self.app / "VERSION").read_text(), "2.0"
        )

    def test_wrong_destination_prevents_rollback(self):
        other = self.app.parent / "other"
        other.mkdir()

        with self.assertRaises(RuntimeError):
            rollback_completed_update(
                self.backups, self.transaction_id, other
            )

        self.assertEqual(
            (self.app / "VERSION").read_text(), "2.0"
        )

    def test_completed_rollback_cannot_repeat(self):
        rollback_completed_update(
            self.backups, self.transaction_id, self.app
        )

        self.assert_original_restored()

        with self.assertRaises(RuntimeError):
            rollback_completed_update(
                self.backups, self.transaction_id, self.app
            )


if __name__ == "__main__":
    unittest.main()
