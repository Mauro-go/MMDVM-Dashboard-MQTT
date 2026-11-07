import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_install
from update_install import COMPONENTS, recover_components


class PersistentRecoveryTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.app = root / "app"
        self.backup = root / "backup"

        self.app.mkdir()
        self.backup.mkdir()

        for component in COMPONENTS:
            for parent, value in (
                (self.app, "updated"),
                (self.backup, "original"),
            ):
                path = parent / component
                if component == "VERSION":
                    path.write_text(value)
                else:
                    path.mkdir()
                    (path / "test.txt").write_text(value)

        (self.app / "config").mkdir()
        (self.app / "config" / "dashboard.ini").write_text(
            "password=preserved"
        )

        (self.app / "data").mkdir()
        (self.app / "data" / "history.db").write_bytes(
            b"database-preserved"
        )

    def assert_restored(self):
        for component in COMPONENTS:
            path = self.app / component
            if component == "VERSION":
                self.assertEqual(path.read_text(), "original")
            else:
                self.assertEqual(
                    (path / "test.txt").read_text(),
                    "original",
                )

        self.assertEqual(
            (self.app / "config/dashboard.ini").read_text(),
            "password=preserved",
        )
        self.assertEqual(
            (self.app / "data/history.db").read_bytes(),
            b"database-preserved",
        )

    def test_complete_recovery(self):
        recover_components(self.backup, self.app)
        self.assert_restored()

    def test_recovery_can_repeat(self):
        recover_components(self.backup, self.app)
        recover_components(self.backup, self.app)
        self.assert_restored()

    def test_interrupted_recovery_can_resume(self):
        real_replace = update_install.os.replace
        failed = [False]

        def interrupted_replace(src, dst):
            if (
                not failed[0]
                and Path(src).name == ".mmdvm-restore-backend"
            ):
                failed[0] = True
                raise OSError("Interruzione simulata")
            return real_replace(src, dst)

        with patch.object(
            update_install.os,
            "replace",
            side_effect=interrupted_replace,
        ):
            with self.assertRaisesRegex(
                OSError, "Interruzione simulata"
            ):
                recover_components(self.backup, self.app)

        recover_components(self.backup, self.app)
        self.assert_restored()

    def test_incomplete_backup_rejected(self):
        (self.backup / "VERSION").unlink()

        with self.assertRaises(RuntimeError):
            recover_components(self.backup, self.app)

        self.assertEqual(
            (self.app / "VERSION").read_text(),
            "updated",
        )

    def test_symlink_in_backup_rejected(self):
        target = self.backup / "backend" / "test.txt"
        target.unlink()
        target.symlink_to("/etc/passwd")

        with self.assertRaises(RuntimeError):
            recover_components(self.backup, self.app)

        self.assertEqual(
            (self.app / "VERSION").read_text(),
            "updated",
        )


if __name__ == "__main__":
    unittest.main()
