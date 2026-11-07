import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_production_guard import (
    production_lock,
    verify_no_pending,
)


class ProductionGuardTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_lock_acquired(self):
        with production_lock(self.root):
            self.assertTrue(
                (self.root / "install.lock").exists()
            )

    def test_second_lock_rejected(self):
        with production_lock(self.root):
            with self.assertRaisesRegex(
                RuntimeError, "già in corso"
            ):
                with production_lock(self.root):
                    pass

    def test_no_pending_transactions(self):
        (self.root / "backups").mkdir()
        self.assertTrue(
            verify_no_pending(self.root)
        )

    def test_pending_transaction_rejected(self):
        transaction = (
            self.root / "backups" / "transaction-1"
        )
        transaction.mkdir(parents=True)
        (transaction / "state.json").write_text(
            '{"status":"installing"}'
        )

        with self.assertRaisesRegex(
            RuntimeError, "incomplete"
        ):
            verify_no_pending(self.root)


if __name__ == "__main__":
    unittest.main()
