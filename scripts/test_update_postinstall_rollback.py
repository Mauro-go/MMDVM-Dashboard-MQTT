import tempfile
import unittest
from pathlib import Path

from update_service_flow import execute_service_flow
from update_journal import load_journal


class PostInstallRollbackTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)

        self.app = root / "app"
        self.release = root / "release"
        self.backups = root / "backups"

        for path in (self.app, self.release, self.backups):
            path.mkdir()

        for component in ("backend", "frontend", "admin"):
            for parent, content in (
                (self.app, "original"),
                (self.release, "updated"),
            ):
                folder = parent / component
                folder.mkdir()
                (folder / "test.txt").write_text(content)

        (self.app / "VERSION").write_text("1.0")
        (self.release / "VERSION").write_text("2.0")

        self.events = []

    def stop(self):
        self.events.append("stop")

    def start(self):
        self.events.append("start")

    def test_standard_rollback_after_health_failure(self):
        results = iter([True, False, True])

        def health():
            return next(results)

        with self.assertRaisesRegex(
            RuntimeError, "versione precedente ripristinata"
        ):
            execute_service_flow(
                "standard", self.app, self.release, self.backups,
                stop=self.stop, start=self.start, health=health,
            )

        self.assertEqual((self.app / "VERSION").read_text(), "1.0")
        self.assertEqual(
            self.events, ["stop", "start", "stop", "start"]
        )

        transactions = [
            path for path in self.backups.iterdir()
            if path.is_dir()
        ]
        self.assertEqual(len(transactions), 1)

        journal = load_journal(transactions[0] / "journal.json")
        self.assertEqual(journal["state"], "rolled_back")

    def test_multi_rollback_after_health_failure(self):
        results = iter([True, False, True])

        with self.assertRaisesRegex(RuntimeError, "ripristinata"):
            execute_service_flow(
                "multi", self.app, self.release, self.backups,
                stop=self.stop, start=self.start,
                health=lambda: next(results),
            )

        self.assertEqual((self.app / "VERSION").read_text(), "1.0")

    def test_success_does_not_rollback(self):
        result = execute_service_flow(
            "standard", self.app, self.release, self.backups,
            stop=self.stop, start=self.start,
            health=lambda: True,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual((self.app / "VERSION").read_text(), "2.0")

    def test_initial_health_failure_does_not_modify_files(self):
        with self.assertRaisesRegex(RuntimeError, "iniziale"):
            execute_service_flow(
                "standard", self.app, self.release, self.backups,
                stop=self.stop, start=self.start,
                health=lambda: False,
            )

        self.assertEqual((self.app / "VERSION").read_text(), "1.0")
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
