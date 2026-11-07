#!/usr/bin/env python3
"""Test di rilevamento dei residui di aggiornamento."""

import tempfile
import unittest
from pathlib import Path

from update_atomic import check_update_residues
from update_coordinator import run_simulated_update


class ResidueTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "application"
        self.release = self.root / "release"
        self.backups = self.root / "backups"

        self.backups.mkdir(mode=0o700)

        for path, version in (
            (self.app, "1.0.0"),
            (self.release, "1.2.3"),
        ):
            path.mkdir()

            for name in ("backend", "frontend", "admin"):
                folder = path / name
                folder.mkdir()
                (folder / "version.txt").write_text(version)

            (path / "VERSION").write_text(version + "\n")

    def test_clean_directory(self):
        self.assertTrue(check_update_residues(self.app))

    def test_old_directory_detected(self):
        (self.app / ".update-old-test").mkdir()

        with self.assertRaises(RuntimeError):
            check_update_residues(self.app)

    def test_new_directory_detected(self):
        (self.app / ".update-new-test").mkdir()

        with self.assertRaises(RuntimeError):
            check_update_residues(self.app)

    def test_old_file_detected(self):
        (self.app / ".update-old-test").write_text("originale")

        with self.assertRaises(RuntimeError):
            check_update_residues(self.app)

    def test_interrupted_rename_blocks_update(self):
        # Simula il vecchio backend spostato, prima
        # dell'installazione del nuovo.
        (self.app / "backend").rename(
            self.app / ".update-old-interrupted"
        )

        with self.assertRaises(RuntimeError):
            run_simulated_update(
                self.app, self.release, self.backups
            )

        self.assertTrue(
            (self.app / ".update-old-interrupted/version.txt").exists()
        )

    def test_normal_update_still_works(self):
        result = run_simulated_update(
            self.app, self.release, self.backups
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            (self.app / "VERSION").read_text().strip(),
            "1.2.3",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
