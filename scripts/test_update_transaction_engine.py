import tempfile
import unittest
from pathlib import Path

from update_transaction_engine import (
    COMPONENTS,
    execute_test_transaction,
    fingerprint,
)


class TransactionEngineTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.application = root / "application"
        self.release = root / "release"
        self.backups = root / "backups"

        for directory in (
            self.application,
            self.release,
            self.backups,
        ):
            directory.mkdir()

        for component in COMPONENTS:
            for parent, value in (
                (self.application, "original"),
                (self.release, "updated"),
            ):
                path = parent / component

                if component == "VERSION":
                    path.write_text(value)
                else:
                    path.mkdir()
                    (path / "file.txt").write_text(value)

        (self.application / "config").mkdir()
        (self.application / "config" / "settings.ini").write_text(
            "preserved"
        )

        (self.application / "data").mkdir()
        (self.application / "data" / "history.db").write_bytes(
            b"preserved"
        )

        self.original = fingerprint(self.application)
        self.updated = fingerprint(self.release)

    def assert_preserved(self):
        self.assertEqual(
            (self.application / "config/settings.ini").read_text(),
            "preserved",
        )
        self.assertEqual(
            (self.application / "data/history.db").read_bytes(),
            b"preserved",
        )

    def test_successful_installation(self):
        result = execute_test_transaction(
            self.release, self.application, self.backups
        )
        self.assertEqual(result, "completed")
        self.assertEqual(
            fingerprint(self.application), self.updated
        )
        self.assert_preserved()

    def test_rollback_after_first_component(self):
        with self.assertRaisesRegex(
            RuntimeError, "Errore simulato"
        ):
            execute_test_transaction(
                self.release,
                self.application,
                self.backups,
                fail_after=1,
            )

        self.assertEqual(
            fingerprint(self.application), self.original
        )
        self.assert_preserved()

    def test_rollback_after_third_component(self):
        with self.assertRaisesRegex(
            RuntimeError, "Errore simulato"
        ):
            execute_test_transaction(
                self.release,
                self.application,
                self.backups,
                fail_after=3,
            )

        self.assertEqual(
            fingerprint(self.application), self.original
        )
        self.assert_preserved()

    def test_pending_transaction_blocks_install(self):
        directory = self.backups / "interrupted"
        directory.mkdir()
        (directory / "state.json").write_text(
            '{"status":"installing"}'
        )

        with self.assertRaisesRegex(
            RuntimeError, "incompleta"
        ):
            execute_test_transaction(
                self.release,
                self.application,
                self.backups,
            )

        self.assertEqual(
            fingerprint(self.application), self.original
        )


if __name__ == "__main__":
    unittest.main()
