#!/usr/bin/env python3
"""Collaudo end-to-end su directory temporanee.

Non modifica installazioni reali e non utilizza systemctl.
"""

import hashlib
import tempfile
import unittest
from pathlib import Path

from update_coordinator import run_simulated_update
from update_journal import load_journal
from update_rename_plan import load_rename_plan
from update_tracked_swap import verify_tracked_completion
from update_atomic import check_update_residues


COMPONENTS = ("backend", "frontend", "admin", "VERSION")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class EndToEndTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.root = Path(self.tmp.name)
        self.application = self.root / "application"
        self.release = self.root / "release"
        self.backups = self.root / "backups"

        self.backups.mkdir(mode=0o700)

        for folder, version in (
            (self.application, "1.0.0"),
            (self.release, "2.0.0"),
        ):
            folder.mkdir()

            for component in COMPONENTS:
                if component == "VERSION":
                    (folder / component).write_text(version + "\n")
                else:
                    directory = folder / component
                    directory.mkdir()
                    (directory / "app.py").write_text(
                        f"# {component} {version}\n"
                    )

        # Dati persistenti: non devono essere modificati.
        self.persistent = [
            self.application / "config" / "dashboard.ini",
            self.application / "data" / "mqtt-settings.json",
            self.application / "data" / "telegram-settings.json",
            self.application / "data" / "events.sqlite3",
            self.application / "data" / "events.sqlite3-wal",
            self.application / "data" / "events.sqlite3-shm",
        ]

        for index, path in enumerate(self.persistent):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                f"PERSISTENT-{index}-DO-NOT-TOUCH".encode()
            )

        self.original_hashes = {
            str(path): digest(path)
            for path in self.persistent
        }

    def assert_persistent_unchanged(self):
        for path in self.persistent:
            self.assertTrue(path.is_file(), str(path))
            self.assertEqual(
                digest(path),
                self.original_hashes[str(path)],
                str(path),
            )

    def transaction_directory(self):
        directories = [
            path for path in self.backups.iterdir()
            if path.is_dir()
        ]
        self.assertEqual(len(directories), 1)
        return directories[0]

    def test_success_journal_plan_and_persistent_data(self):
        result = run_simulated_update(
            self.application,
            self.release,
            self.backups,
            tracked=True,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            (self.application / "VERSION").read_text().strip(),
            "2.0.0",
        )

        transaction = self.transaction_directory()

        journal = load_journal(transaction / "journal.json")
        plan = load_rename_plan(transaction / "rename-plan.json")

        self.assertEqual(journal["state"], "completed")
        self.assertEqual(
            set(journal["completed_components"]),
            set(COMPONENTS),
        )
        self.assertEqual(
            plan["transaction_id"],
            journal["transaction_id"],
        )

        verification = verify_tracked_completion(
            self.application,
            transaction / "rename-plan.json",
        )

        self.assertTrue(
            verification["ready"],
            verification["problems"],
        )

        self.assert_persistent_unchanged()

    def test_failure_restores_code_and_persistent_data(self):
        with self.assertRaises(RuntimeError):
            run_simulated_update(
                self.application,
                self.release,
                self.backups,
                tracked=True,
                fail_after="frontend",
            )

        self.assertEqual(
            (self.application / "VERSION").read_text().strip(),
            "1.0.0",
        )

        for component in ("backend", "frontend", "admin"):
            self.assertIn(
                "1.0.0",
                (self.application / component / "app.py").read_text(),
            )

        transaction = self.transaction_directory()
        journal = load_journal(transaction / "journal.json")

        self.assertEqual(journal["state"], "rolled_back")
        self.assert_persistent_unchanged()

    def test_residues_block_another_update(self):
        run_simulated_update(
            self.application,
            self.release,
            self.backups,
            tracked=True,
        )

        with self.assertRaises(Exception):
            check_update_residues(self.application)

    def test_previous_transaction_blocks_reuse(self):
        with self.assertRaises(RuntimeError):
            run_simulated_update(
                self.application,
                self.release,
                self.backups,
                tracked=True,
                fail_after="backend",
            )

        # La transazione precedente ha effettuato il rollback,
        # ma ha lasciato residui tracciati: il secondo tentativo
        # non deve sovrascriverli.
        with self.assertRaises(Exception):
            run_simulated_update(
                self.application,
                self.release,
                self.backups,
                tracked=True,
            )

        self.assert_persistent_unchanged()


if __name__ == "__main__":
    unittest.main(verbosity=2)
