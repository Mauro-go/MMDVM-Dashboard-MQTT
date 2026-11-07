#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path

from update_rename_plan import create_rename_plan, save_rename_plan
from update_tracked_swap import verify_tracked_completion


class CompletionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.root = Path(self.tmp.name)
        self.app = self.root / "application"
        self.app.mkdir()

        self.txid = "a" * 32
        self.plan = create_rename_plan(self.txid)
        self.plan_path = self.root / "plan.json"

        for component, operation in self.plan["operations"].items():
            operation["state"] = "new_installed"

            target = self.app / component
            previous = self.app / operation["previous"]

            if component == "VERSION":
                target.write_text("2.0.0")
                previous.write_text("1.0.0")
            else:
                target.mkdir()
                previous.mkdir()

        save_rename_plan(self.plan_path, self.plan)

    def test_complete(self):
        result = verify_tracked_completion(
            self.app, self.plan_path
        )
        self.assertTrue(result["ready"])

    def test_missing_previous(self):
        previous = self.app / self.plan["operations"]["VERSION"]["previous"]
        previous.unlink()

        result = verify_tracked_completion(
            self.app, self.plan_path
        )
        self.assertFalse(result["ready"])

    def test_prepared_residue(self):
        prepared = self.app / self.plan["operations"]["VERSION"]["prepared"]
        prepared.write_text("partial")

        result = verify_tracked_completion(
            self.app, self.plan_path
        )
        self.assertFalse(result["ready"])

    def test_incomplete_state(self):
        self.plan["operations"]["backend"]["state"] = "old_moved"
        save_rename_plan(self.plan_path, self.plan)

        result = verify_tracked_completion(
            self.app, self.plan_path
        )
        self.assertFalse(result["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
