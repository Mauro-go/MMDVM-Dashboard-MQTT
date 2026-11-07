import tempfile
import unittest
import uuid
from pathlib import Path

from update_backup import (
    backup_application,
    save_backup_manifest,
)
from update_journal import save_journal, load_journal
from update_restore import recover_simulated_transaction
from update_paths import transaction_paths


class PreparedRecoveryTests(unittest.TestCase):

    def test_recovery_from_prepared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "application"
            release = root / "backups"
            app.mkdir()
            release.mkdir()

            for name in ("backend", "frontend", "admin"):
                (app / name).mkdir()
                (app / name / "test.txt").write_text("original")

            (app / "VERSION").write_text("1.0")

            transaction_id = uuid.uuid4().hex
            paths = transaction_paths(release, transaction_id)
            paths["transaction"].mkdir(mode=0o700)

            backup_application(app, paths["backup"])
            save_backup_manifest(
                paths["backup"],
                paths["manifest"],
            )

            journal = {
                "transaction_id": transaction_id,
                "installation_path": str(app),
                "state": "prepared",
                "completed_components": [],
                "pending_component": None,
            }
            save_journal(paths["journal"], journal)

            (app / "VERSION").write_text("2.0")

            result = recover_simulated_transaction(
                release,
                transaction_id,
                app,
            )

            self.assertEqual(result["status"], "rolled_back")
            self.assertEqual(
                (app / "VERSION").read_text(),
                "1.0",
            )
            self.assertEqual(
                load_journal(paths["journal"])["state"],
                "rolled_back",
            )


if __name__ == "__main__":
    unittest.main()
