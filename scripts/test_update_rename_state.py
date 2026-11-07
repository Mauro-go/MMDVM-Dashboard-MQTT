#!/usr/bin/env python3
"""Test di ricostruzione non distruttiva delle rinomine."""

import tempfile
import unittest
from pathlib import Path

from update_rename_state import inspect_rename_residues

TOKEN = "0123456789abcdef0123456789abcdef"


class RenameStateTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.app = Path(self.temp.name) / "application"
        self.app.mkdir()

        for name in ("backend", "frontend", "admin"):
            (self.app / name).mkdir()

        (self.app / "VERSION").write_text("1.0.0\n")

    def test_clean_application(self):
        result = inspect_rename_residues(self.app)
        self.assertTrue(result["clean"])
        self.assertFalse(result["requires_manual_review"])

    def test_old_directory(self):
        (self.app / (".update-old-" + TOKEN)).mkdir()

        result = inspect_rename_residues(self.app)

        self.assertFalse(result["clean"])
        self.assertEqual(result["residues"][0]["kind"], "old")
        self.assertTrue(result["residues"][0]["valid_token"])

    def test_new_directory(self):
        (self.app / (".update-new-" + TOKEN)).mkdir()

        result = inspect_rename_residues(self.app)

        self.assertEqual(result["residues"][0]["kind"], "new")

    def test_missing_component(self):
        (self.app / "backend").rename(
            self.app / (".update-old-" + TOKEN)
        )

        result = inspect_rename_residues(self.app)

        self.assertFalse(
            result["components"]["backend"]["exists"]
        )
        self.assertTrue(result["requires_manual_review"])

    def test_unknown_token(self):
        (self.app / ".update-old-interrupted").mkdir()

        result = inspect_rename_residues(self.app)

        self.assertIn(
            ".update-old-interrupted",
            result["unknown"],
        )

    def test_symlink_residue(self):
        (self.app / (".update-old-" + TOKEN)).symlink_to(
            "/etc/passwd"
        )

        result = inspect_rename_residues(self.app)

        self.assertTrue(result["requires_manual_review"])
        self.assertTrue(result["residues"][0]["is_symlink"])

    def test_multiple_residues(self):
        (self.app / (".update-old-" + TOKEN)).mkdir()
        (self.app / (".update-new-" + TOKEN)).mkdir()

        result = inspect_rename_residues(self.app)

        self.assertEqual(len(result["residues"]), 2)

    def test_read_only(self):
        before = sorted(p.name for p in self.app.iterdir())

        inspect_rename_residues(self.app)

        after = sorted(p.name for p in self.app.iterdir())

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
