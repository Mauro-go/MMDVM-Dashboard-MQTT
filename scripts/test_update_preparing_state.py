import tempfile
import unittest
from pathlib import Path

from update_transaction_state import (
    write_state,
    read_state,
    pending_transactions,
)


class PreparingStateTests(unittest.TestCase):

    def test_preparing_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "state.json"

            write_state(journal, {"status": "preparing"})

            self.assertEqual(
                read_state(journal)["status"],
                "preparing",
            )

    def test_preparing_is_detected_as_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            backups = Path(tmp)
            transaction = backups / "test"
            transaction.mkdir()

            write_state(
                transaction / "state.json",
                {"status": "preparing"},
            )

            pending = pending_transactions(backups)

            self.assertEqual(len(pending), 1)
            self.assertEqual(
                pending[0]["status"],
                "preparing",
            )


if __name__ == "__main__":
    unittest.main()
