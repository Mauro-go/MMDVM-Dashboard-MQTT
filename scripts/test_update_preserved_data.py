import tempfile
import unittest
from pathlib import Path

from update_service_flow import execute_service_flow


class PreservedDataTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        root = Path(self.tmp.name)
        self.app = root / "application"
        self.release = root / "release"
        self.backups = root / "backups"

        for directory in (self.app, self.release, self.backups):
            directory.mkdir()

        for component in ("backend", "frontend", "admin"):
            for parent, value in (
                (self.app, "old"),
                (self.release, "new"),
            ):
                folder = parent / component
                folder.mkdir()
                (folder / "test.txt").write_text(value)

        (self.app / "VERSION").write_text("1")
        (self.release / "VERSION").write_text("2")

        (self.app / "config").mkdir()
        (self.app / "config" / "dashboard.ini").write_text(
            "[mqtt]\\npassword=secret\\n"
        )

        (self.app / "data").mkdir()
        (self.app / "data" / "history.db").write_bytes(
            b"database-original"
        )

    def update(self, health):
        return execute_service_flow(
            "multi",
            self.app,
            self.release,
            self.backups,
            stop=lambda: None,
            start=lambda: None,
            health=health,
        )

    def assert_preserved(self):
        self.assertEqual(
            (self.app / "config" / "dashboard.ini").read_text(),
            "[mqtt]\\npassword=secret\\n",
        )
        self.assertEqual(
            (self.app / "data" / "history.db").read_bytes(),
            b"database-original",
        )

    def test_configuration_and_data_survive_update(self):
        result = self.update(lambda: True)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            (self.app / "VERSION").read_text(), "2"
        )
        self.assert_preserved()

    def test_configuration_and_data_survive_rollback(self):
        results = iter([True, False, True])

        with self.assertRaises(RuntimeError):
            self.update(lambda: next(results))

        self.assertEqual(
            (self.app / "VERSION").read_text(), "1"
        )
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main()
