#!/usr/bin/env python3
"""Test isolati della sostituzione controllata."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_atomic import replace_component


class AtomicTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.old = self.root / "application"
        self.new = self.root / "release"

        self.old.mkdir()
        self.new.mkdir()

        for directory, version in (
            (self.old, "1.0.0"),
            (self.new, "1.2.3"),
        ):
            for name in ("backend", "frontend", "admin"):
                folder = directory / name
                folder.mkdir()
                (folder / "version.txt").write_text(version)

            (directory / "VERSION").write_text(version + "\n")

        (self.old / "config").mkdir()
        (self.old / "config/dashboard.ini").write_text("CONFIG")

        (self.old / "data").mkdir()
        (self.old / "data/events.sqlite3").write_text("DATABASE")

    def assert_persistent(self):
        self.assertEqual(
            (self.old / "config/dashboard.ini").read_text(),
            "CONFIG",
        )
        self.assertEqual(
            (self.old / "data/events.sqlite3").read_text(),
            "DATABASE",
        )

    def test_replace_backend(self):
        result = replace_component(
            self.new, self.old, "backend"
        )

        self.assertTrue(result["installed"])
        self.assertEqual(
            (self.old / "backend/version.txt").read_text(),
            "1.2.3",
        )
        self.assert_persistent()

    def test_replace_version(self):
        replace_component(self.new, self.old, "VERSION")
        self.assertEqual(
            (self.old / "VERSION").read_text().strip(),
            "1.2.3",
        )

    def test_reject_unknown_component(self):
        with self.assertRaises(ValueError):
            replace_component(
                self.new, self.old, "config"
            )

    def test_reject_missing_source(self):
        with self.assertRaises(ValueError):
            replace_component(
                self.new, self.old, "missing"
            )

    def test_reject_symlink(self):
        (self.new / "backend/version.txt").unlink()
        (self.new / "backend/version.txt").symlink_to(
            "/etc/passwd"
        )

        with self.assertRaises(ValueError):
            replace_component(
                self.new, self.old, "backend"
            )

    def test_failure_before_replacement(self):
        with patch(
            "update_atomic.shutil.copytree",
            side_effect=OSError("Copia fallita"),
        ):
            with self.assertRaises(OSError):
                replace_component(
                    self.new, self.old, "backend"
                )

        self.assertEqual(
            (self.old / "backend/version.txt").read_text(),
            "1.0.0",
        )

    def test_no_temporary_files_after_success(self):
        replace_component(self.new, self.old, "frontend")

        leftovers = [
            p.name for p in self.old.iterdir()
            if p.name.startswith(".update-")
        ]

        self.assertEqual(leftovers, [])
        self.assert_persistent()


if __name__ == "__main__":
    unittest.main(verbosity=2)
