import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_live
from update_transaction_engine import (
    copy_snapshot,
    fingerprint,
    restore_snapshot,
    save_fingerprint,
    verify_fingerprint,
)
from update_transaction_state import (
    write_state,
    read_state,
)


class HardeningTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.root = Path(self.tmp.name)
        self.app = self.root / "app"
        self.backup = self.root / "backup"
        self.transaction = self.root / "transaction"

        self.app.mkdir()
        self.transaction.mkdir()

        for component in update_live.COMPONENTS:
            path = self.app / component

            if component == "VERSION":
                path.write_text("original")
            else:
                path.mkdir()
                (path / "file.txt").write_text("original")

        copy_snapshot(self.app, self.backup)

        self.expected = fingerprint(self.backup)

        save_fingerprint(
            self.transaction / "backup-fingerprint.json",
            self.expected,
        )

    def test_backup_integrity(self):
        self.assertTrue(
            verify_fingerprint(
                self.backup,
                self.transaction / "backup-fingerprint.json",
            )
        )

    def test_corrupted_backup_rejected(self):
        (self.backup / "VERSION").write_text("corrupted")

        with self.assertRaises(RuntimeError):
            verify_fingerprint(
                self.backup,
                self.transaction / "backup-fingerprint.json",
            )

    def test_restore_twice(self):
        (self.app / "VERSION").write_text("new")

        restore_snapshot(
            self.backup,
            self.app,
            self.transaction,
        )

        restore_snapshot(
            self.backup,
            self.app,
            self.transaction,
        )

        self.assertEqual(
            fingerprint(self.app),
            self.expected,
        )

    def test_restore_after_missing_component(self):
        (self.app / "VERSION").unlink()

        restore_snapshot(
            self.backup,
            self.app,
            self.transaction,
        )

        self.assertEqual(
            fingerprint(self.app),
            self.expected,
        )

    def test_preparing_journal(self):
        journal = self.transaction / "state.json"

        write_state(journal, {
            "status": "preparing",
            "destination": str(self.app),
        })

        self.assertEqual(
            read_state(journal)["status"],
            "preparing",
        )


if __name__ == "__main__":
    unittest.main()
