import tempfile
import unittest
from pathlib import Path

from update_transaction_engine import (
    COMPONENTS,
    fingerprint,
    copy_snapshot,
    save_fingerprint,
    recover_transaction,
)
from update_transaction_state import write_state, read_state


class TransactionRecoveryTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.app = root / "application"
        self.transaction = root / "transaction"
        self.original = root / "original"

        for directory in (
            self.app,
            self.transaction,
            self.original,
        ):
            directory.mkdir()

        for component in COMPONENTS:
            for parent, value in (
                (self.app, "updated"),
                (self.original, "original"),
            ):
                path = parent / component

                if component == "VERSION":
                    path.write_text(value)
                else:
                    path.mkdir()
                    (path / "file.txt").write_text(value)

        (self.app / "config").mkdir()
        (self.app / "config" / "settings.ini").write_text(
            "preserved"
        )

        (self.app / "data").mkdir()
        (self.app / "data" / "history.db").write_bytes(
            b"preserved"
        )

        self.expected = fingerprint(self.original)

        copy_snapshot(
            self.original,
            self.transaction / "backup",
        )

        save_fingerprint(
            self.transaction / "backup-fingerprint.json",
            self.expected,
        )

    def set_status(self, status):
        write_state(
            self.transaction / "state.json",
            {"status": status},
        )

    def assert_restored(self):
        self.assertEqual(
            fingerprint(self.app),
            self.expected,
        )
        self.assertEqual(
            (self.app / "config/settings.ini").read_text(),
            "preserved",
        )
        self.assertEqual(
            (self.app / "data/history.db").read_bytes(),
            b"preserved",
        )

    def test_recover_interrupted_install(self):
        self.set_status("installing")
        self.assertEqual(
            recover_transaction(
                self.transaction, self.app
            ),
            "rolled_back",
        )
        self.assert_restored()

    def test_recover_interrupted_rollback(self):
        self.set_status("rolling_back")
        self.assertEqual(
            recover_transaction(
                self.transaction, self.app
            ),
            "rolled_back",
        )
        self.assert_restored()

    def test_recovery_is_repeatable(self):
        self.set_status("installing")
        recover_transaction(self.transaction, self.app)
        self.assertEqual(
            recover_transaction(
                self.transaction, self.app
            ),
            "rolled_back",
        )
        self.assert_restored()

    def test_corrupted_backup_rejected(self):
        self.set_status("installing")
        (
            self.transaction / "backup" /
            "backend" / "file.txt"
        ).write_text("corrupted")

        with self.assertRaisesRegex(
            RuntimeError, "Integrità backup"
        ):
            recover_transaction(
                self.transaction, self.app
            )

        self.assertEqual(
            (self.app / "VERSION").read_text(),
            "updated",
        )

    def test_completed_transaction_unchanged(self):
        self.set_status("completed")
        self.assertEqual(
            recover_transaction(
                self.transaction, self.app
            ),
            "completed",
        )
        self.assertEqual(
            (self.app / "VERSION").read_text(),
            "updated",
        )


if __name__ == "__main__":
    unittest.main()
