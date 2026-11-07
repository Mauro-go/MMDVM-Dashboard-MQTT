import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_live
from update_transaction_engine import fingerprint
from update_transaction_state import pending_transactions


class LiveIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        root = Path(self.tmp.name)
        self.app = root / "app"
        self.release = root / "release"
        self.base = root / "updates"
        self.backups = self.base / "backups"

        for directory in (
            self.app, self.release, self.backups
        ):
            directory.mkdir(parents=True)

        for component in update_live.COMPONENTS:
            for parent, value in (
                (self.app, "old"),
                (self.release, "new"),
            ):
                path = parent / component

                if component == "VERSION":
                    path.write_text(value)
                else:
                    path.mkdir()
                    (path / "content.txt").write_text(value)

        for name in ("config", "data"):
            directory = self.app / name
            directory.mkdir()
            (directory / "preserved.txt").write_text(name)

        self.original = fingerprint(self.app)
        self.updated = fingerprint(self.release)

        self.actions = []

        self.patches = [
            patch.object(update_live, "BASE", self.base),
            patch.object(update_live, "BACKUPS", self.backups),
            patch.object(update_live, "DESTINATION", self.app),
            patch.object(
                update_live, "check_release",
                return_value=self.release,
            ),
            patch.object(
                update_live, "verify_services",
                return_value=True,
            ),
            patch.object(
                update_live, "health",
                return_value=True,
            ),
            patch.object(
                update_live, "run_systemctl",
                side_effect=lambda action, service:
                    self.actions.append((action, service)),
            ),
        ]

        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_successful_apply(self):
        update_live.install(self.release)

        self.assertEqual(
            fingerprint(self.app),
            self.updated,
        )

        self.assertEqual(
            pending_transactions(self.backups),
            [],
        )

        self.assertTrue(
            any(action == "stop" for action, _ in self.actions)
        )
        self.assertTrue(
            any(action == "start" for action, _ in self.actions)
        )

        for name in ("config", "data"):
            self.assertEqual(
                (self.app / name / "preserved.txt").read_text(),
                name,
            )

    def test_failed_http_rolls_back(self):
        calls = [True, False, True]

        def simulated_health(timeout=30):
            return calls.pop(0) if calls else True

        with patch.object(
            update_live, "health",
            side_effect=simulated_health,
        ):
            with self.assertRaises(RuntimeError):
                update_live.install(self.release)

        self.assertEqual(
            fingerprint(self.app),
            self.original,
        )

        self.assertEqual(
            pending_transactions(self.backups),
            [],
        )

    def test_recover_interrupted_installation(self):
        from update_transaction_engine import (
            copy_snapshot,
            save_fingerprint,
            swap_component,
        )
        from update_transaction_state import write_state

        transaction = self.backups / "interrupted"
        transaction.mkdir()

        backup = transaction / "backup"
        staged = self.app.parent / ".mmdvm-stage-interrupted"

        copy_snapshot(self.app, backup)
        save_fingerprint(
            transaction / "backup-fingerprint.json",
            fingerprint(backup),
        )
        copy_snapshot(self.release, staged)

        state = {
            "status": "installing",
            "destination": str(self.app),
            "staging": str(staged),
        }

        write_state(transaction / "state.json", state)

        swap_component(
            staged,
            self.app,
            transaction,
            "backend",
        )

        update_live.recover_pending()

        self.assertEqual(
            fingerprint(self.app),
            self.original,
        )
        self.assertEqual(
            pending_transactions(self.backups),
            [],
        )

        for name in ("config", "data"):
            self.assertEqual(
                (self.app / name / "preserved.txt").read_text(),
                name,
            )


if __name__ == "__main__":
    unittest.main()
