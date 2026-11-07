#!/usr/bin/env python3
"""Simulazione isolata del motore di aggiornamento."""

import tempfile
import unittest
from pathlib import Path

from update_backup import (
    backup_application,
    backup_manifest,
    restore_application,
)
from update_transaction import install_components

COMPONENTS = ("backend", "frontend", "admin", "VERSION")


def make_application(path, version):
    path.mkdir()

    for name in COMPONENTS:
        if name == "VERSION":
            (path / name).write_text(version + "\n")
        else:
            directory = path / name
            directory.mkdir()
            (directory / "version.txt").write_text(version)


class EngineTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)

        self.application = root / "application"
        self.release = root / "release"
        self.backup = root / "backup"

        make_application(self.application, "1.0.0")
        make_application(self.release, "1.2.3")

        config = self.application / "config"
        config.mkdir()
        (config / "dashboard.ini").write_text("configurazione")

        data = self.application / "data"
        data.mkdir()
        (data / "events.sqlite3").write_text("database")

        backup_application(
            self.application,
            self.backup,
        )
        self.original_manifest = backup_manifest(self.backup)

    def assert_persistent_data(self):
        self.assertEqual(
            (self.application / "config/dashboard.ini").read_text(),
            "configurazione",
        )
        self.assertEqual(
            (self.application / "data/events.sqlite3").read_text(),
            "database",
        )

    def test_successful_installation(self):
        install_components(self.release, self.application)

        self.assertEqual(
            (self.application / "VERSION").read_text().strip(),
            "1.2.3",
        )
        self.assert_persistent_data()

    def test_backup_integrity(self):
        self.assertEqual(
            backup_manifest(self.backup),
            self.original_manifest,
        )

    def test_rollback_after_installation(self):
        install_components(self.release, self.application)

        restore_application(
            self.backup,
            self.application,
            self.original_manifest,
        )

        self.assertEqual(
            (self.application / "VERSION").read_text().strip(),
            "1.0.0",
        )
        self.assert_persistent_data()

    def test_rollback_after_partial_installation(self):
        # Simula un aggiornamento interrotto dopo il backend.
        target = self.application / "backend/version.txt"
        target.write_text("1.2.3")

        restore_application(
            self.backup,
            self.application,
            self.original_manifest,
        )

        self.assertEqual(
            (self.application / "backend/version.txt").read_text(),
            "1.0.0",
        )
        self.assert_persistent_data()

    def test_reject_corrupted_backup(self):
        (self.backup / "backend/version.txt").write_text("ALTERATO")

        with self.assertRaises(ValueError):
            restore_application(
                self.backup,
                self.application,
                self.original_manifest,
            )

    def test_release_does_not_include_persistent_data(self):
        for name in ("config", "data"):
            self.assertFalse((self.release / name).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
