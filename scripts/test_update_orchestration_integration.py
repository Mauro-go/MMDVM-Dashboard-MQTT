import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_orchestration import execute_simulated_plan


class OrchestrationIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        root = Path(self.tmp.name)
        self.app = root / "application"
        self.release = root / "release"
        self.backups = root / "backups"

        for folder in (self.app, self.release, self.backups):
            folder.mkdir()

        for name in ("backend", "frontend", "admin"):
            for parent, content in (
                (self.app, "original"),
                (self.release, "updated"),
            ):
                directory = parent / name
                directory.mkdir()
                (directory / "test.txt").write_text(content)

        (self.app / "VERSION").write_text("1.0")
        (self.release / "VERSION").write_text("2.0")

    def test_standard_installation(self):
        result = execute_simulated_plan(
            "standard", self.app, self.release, self.backups
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual((self.app / "VERSION").read_text(), "2.0")
        self.assertFalse(result["services_modified"])

    def test_multi_installation(self):
        result = execute_simulated_plan(
            "multi", self.app, self.release, self.backups
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual((self.app / "VERSION").read_text(), "2.0")
        self.assertFalse(result["production_enabled"])

    def test_rollback_on_failure(self):
        with self.assertRaises(RuntimeError):
            execute_simulated_plan(
                "standard",
                self.app,
                self.release,
                self.backups,
                fail_after="frontend",
            )

        self.assertEqual((self.app / "VERSION").read_text(), "1.0")
        self.assertEqual(
            (self.app / "frontend" / "test.txt").read_text(),
            "original",
        )

    def test_invalid_mode(self):
        with self.assertRaises((ValueError, KeyError)):
            execute_simulated_plan(
                "invalid",
                self.app,
                self.release,
                self.backups,
            )

    def test_production_not_called(self):
        with patch(
            "update_orchestration.execute_production_update",
            side_effect=AssertionError("Produzione invocata"),
        ):
            result = execute_simulated_plan(
                "multi",
                self.app,
                self.release,
                self.backups,
            )

        self.assertEqual(result["status"], "completed")

    def test_outside_temporary_directory_rejected(self):
        with patch(
            "tempfile.gettempdir",
            return_value="/var/lib",
        ):
            with self.assertRaises(ValueError):
                execute_simulated_plan(
                    "standard",
                    self.app,
                    self.release,
                    self.backups,
                )


if __name__ == "__main__":
    unittest.main()
