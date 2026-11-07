#!/usr/bin/env python3
"""Test del coordinatore con sostituzione controllata."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_coordinator import run_simulated_update


class AtomicIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "application"
        self.release = self.root / "release"
        self.backups = self.root / "backups"
        self.backups.mkdir(mode=0o700)

        for directory, version in (
            (self.app, "1.0.0"),
            (self.release, "1.2.3"),
        ):
            directory.mkdir()

            for name in ("backend", "frontend", "admin"):
                component = directory / name
                component.mkdir()
                (component / "version.txt").write_text(version)

            (directory / "VERSION").write_text(version + "\n")

        (self.app / "config").mkdir()
        (self.app / "config/dashboard.ini").write_text("CONFIG")

        (self.app / "data").mkdir()
        (self.app / "data/events.sqlite3").write_text("DATABASE")

    def assert_original(self):
        for name in ("backend", "frontend", "admin"):
            self.assertEqual(
                (self.app / name / "version.txt").read_text(),
                "1.0.0",
            )

        self.assertEqual(
            (self.app / "VERSION").read_text().strip(),
            "1.0.0",
        )

        self.assertEqual(
            (self.app / "config/dashboard.ini").read_text(),
            "CONFIG",
        )

        self.assertEqual(
            (self.app / "data/events.sqlite3").read_text(),
            "DATABASE",
        )

    def test_success(self):
        result = run_simulated_update(
            self.app, self.release, self.backups
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            (self.app / "VERSION").read_text().strip(),
            "1.2.3",
        )

    def test_failure_during_frontend(self):
        from update_atomic import replace_component

        def fail_frontend(source, destination, component):
            if component == "frontend":
                raise OSError("Errore simulato frontend")
            return replace_component(source, destination, component)

        with patch(
            "update_coordinator.replace_component",
            side_effect=fail_frontend,
        ):
            with self.assertRaises(OSError):
                run_simulated_update(
                    self.app, self.release, self.backups
                )

        self.assert_original()

    def test_failure_after_version(self):
        with self.assertRaises(RuntimeError):
            run_simulated_update(
                self.app,
                self.release,
                self.backups,
                fail_after="VERSION",
            )

        self.assert_original()


if __name__ == "__main__":
    unittest.main(verbosity=2)
