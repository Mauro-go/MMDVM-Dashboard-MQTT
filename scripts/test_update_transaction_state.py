import tempfile
import unittest
from pathlib import Path

from update_transaction_state import (
    write_state,
    read_state,
    pending_transactions,
)


class TransactionStateTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def create_transaction(self, name, status):
        directory = self.root / name
        directory.mkdir()
        write_state(
            directory / "state.json",
            {"status": status},
        )
        return directory

    def test_completed_transaction(self):
        directory = self.create_transaction(
            "transaction-1", "completed"
        )

        self.assertEqual(
            read_state(directory / "state.json")["status"],
            "completed",
        )
        self.assertEqual(
            pending_transactions(self.root), [],
        )

    def test_interrupted_installation(self):
        self.create_transaction(
            "transaction-2", "installing"
        )

        pending = pending_transactions(self.root)

        self.assertEqual(len(pending), 1)
        self.assertEqual(
            pending[0]["status"], "installing"
        )

    def test_interrupted_rollback(self):
        self.create_transaction(
            "transaction-3", "rolling_back"
        )

        pending = pending_transactions(self.root)

        self.assertEqual(len(pending), 1)
        self.assertEqual(
            pending[0]["status"], "rolling_back"
        )

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError):
            write_state(
                self.root / "state.json",
                {"status": "unknown"},
            )


if __name__ == "__main__":
    unittest.main()
