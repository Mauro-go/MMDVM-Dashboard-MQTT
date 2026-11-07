#!/usr/bin/env python3
"""Test del controllo dei residui per transazione."""

import tempfile
import unittest
from pathlib import Path

from update_rename_audit import (
    audit_rename_transaction,
    require_clean_rename_state,
)
from update_rename_plan import (
    create_rename_plan,
    save_rename_plan,
)

TXID = "0123456789abcdef0123456789abcdef"


class RenameAuditTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.app = self.root / "application"
        self.app.mkdir()

        for component in ("backend", "frontend", "admin"):
            (self.app / component).mkdir()

        (self.app / "VERSION").write_text("1.0.0\n")

        self.plan = create_rename_plan(TXID)
        self.plan_path = self.root / "rename-plan.json"
        save_rename_plan(self.plan_path, self.plan)

    def test_clean_state(self):
        result = audit_rename_transaction(
            self.app, self.plan_path
        )
        self.assertTrue(result["safe_to_start"])
        self.assertTrue(
            require_clean_rename_state(self.app, self.plan_path)
        )

    def test_recognized_old(self):
        name = self.plan["operations"]["backend"]["previous"]
        (self.app / name).mkdir()

        result = audit_rename_transaction(
            self.app, self.plan_path
        )
        self.assertIn(name, result["recognized"])

    def test_recognized_new(self):
        name = self.plan["operations"]["frontend"]["prepared"]
        (self.app / name).mkdir()

        result = audit_rename_transaction(
            self.app, self.plan_path
        )
        self.assertIn(name, result["recognized"])

    def test_unknown_transaction(self):
        name = ".update-old-" + "f" * 32 + "-backend"
        (self.app / name).mkdir()

        result = audit_rename_transaction(
            self.app, self.plan_path
        )
        self.assertIn(name, result["unknown"])

    def test_block_residues(self):
        name = self.plan["operations"]["backend"]["previous"]
        (self.app / name).mkdir()

        with self.assertRaises(RuntimeError):
            require_clean_rename_state(
                self.app, self.plan_path
            )

    def test_symlink_residue(self):
        name = self.plan["operations"]["backend"]["previous"]
        (self.app / name).symlink_to("/etc/passwd")

        result = audit_rename_transaction(
            self.app, self.plan_path
        )
        self.assertIn(name, result["symlinks"])

    def test_read_only(self):
        before = sorted(p.name for p in self.app.iterdir())

        audit_rename_transaction(self.app, self.plan_path)

        after = sorted(p.name for p in self.app.iterdir())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
