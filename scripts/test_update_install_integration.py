import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_install
from update_transaction_engine import fingerprint
from update_transaction_state import read_state


class InstallerIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        root = Path(self.tmp.name)
        self.app = root / "app"
        self.release = root / "release"
        self.backups = root / "backups"

        for directory in (self.app, self.release, self.backups):
            directory.mkdir()

        for component in update_install.COMPONENTS:
            for parent, value in (
                (self.app, "original"),
                (self.release, "updated"),
            ):
                path = parent / component
                if component == "VERSION":
                    path.write_text(value)
                else:
                    path.mkdir()
                    (path / "test.txt").write_text(value)

        (self.app / "config").mkdir()
        (self.app / "config" / "settings.ini").write_text(
            "preserved"
        )
        (self.app / "data").mkdir()
        (self.app / "data" / "history.db").write_bytes(
            b"preserved"
        )

        self.original = fingerprint(self.app)
        self.updated = fingerprint(self.release)

    def test_successful_transaction(self):
        from update_transaction_engine import (
            copy_snapshot,
            swap_component,
            save_fingerprint,
            verify_fingerprint,
        )
        from update_transaction_state import write_state

        transaction = self.backups / "success"
        transaction.mkdir()
        backup = transaction / "backup"
        staged = transaction / "staged"
        journal = transaction / "state.json"
        manifest = transaction / "backup-fingerprint.json"

        write_state(journal, {"status": "backup"})
        copy_snapshot(self.app, backup)
        save_fingerprint(manifest, fingerprint(backup))
        copy_snapshot(self.release, staged)

        self.assertTrue(verify_fingerprint(backup, manifest))

        write_state(journal, {"status": "stopping"})
        write_state(journal, {"status": "installing"})

        for component in update_install.COMPONENTS:
            swap_component(staged, self.app, transaction, component)

        write_state(journal, {"status": "starting"})
        self.assertEqual(fingerprint(self.app), self.updated)

        write_state(journal, {"status": "completed"})

        self.assertEqual(
            read_state(journal)["status"], "completed"
        )
        self.assertEqual(
            (self.app / "config/settings.ini").read_text(),
            "preserved"
        )

    def test_failed_health_requires_rollback(self):
        from update_transaction_engine import (
            copy_snapshot,
            swap_component,
            save_fingerprint,
            recover_transaction,
        )
        from update_transaction_state import write_state

        transaction = self.backups / "failure"
        transaction.mkdir()
        backup = transaction / "backup"
        staged = transaction / "staged"
        journal = transaction / "state.json"

        write_state(journal, {
            "status": "backup",
            "destination": str(self.app),
        })

        copy_snapshot(self.app, backup)
        save_fingerprint(
            transaction / "backup-fingerprint.json",
            fingerprint(backup),
        )
        copy_snapshot(self.release, staged)

        write_state(journal, {
            "status": "installing",
            "destination": str(self.app),
        })

        for component in update_install.COMPONENTS:
            swap_component(staged, self.app, transaction, component)

        self.assertEqual(fingerprint(self.app), self.updated)

        result = recover_transaction(transaction, self.app)

        self.assertEqual(result, "rolled_back")
        self.assertEqual(fingerprint(self.app), self.original)
        self.assertEqual(
            (self.app / "data/history.db").read_bytes(),
            b"preserved"
        )


if __name__ == "__main__":
    unittest.main()
