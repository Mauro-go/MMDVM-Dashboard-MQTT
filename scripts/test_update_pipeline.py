#!/usr/bin/env python3
"""Test integrati della preparazione delle release."""

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from update_release import extract_release, validate_archive
from update_transaction import prepare_release
from update_backup import backup_manifest


FILES = {
    "VERSION": b"1.2.3\n",
    "backend/app.py": b"print('app')\n",
    "backend/admin_api.py": b"print('admin')\n",
    "backend/update_checker.py": b"print('updates')\n",
    "frontend/index.html": b"<html></html>\n",
    "admin/admin.html": b"<html></html>\n",
    "README.md": b"Documentazione",
    "install.sh": b"#!/bin/sh\n",
    "agent/agent.py": b"print('agent')\n",
    "config/dashboard.ini.example": b"[repeater]\n",
}


def create_archive(filename, files):
    with tarfile.open(filename, "w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(
                "MMDVM-Dashboard-MQTT-1.2.3/" + name
            )
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


class PipelineTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        self.archive = self.root / "release.tar.gz"
        self.extracted = self.root / "extracted"
        self.staging = self.root / "staging"

        self.application = self.root / "application"
        self.application.mkdir()

        for component in ("backend", "frontend", "admin"):
            folder = self.application / component
            folder.mkdir()
            (folder / "original.txt").write_text("originale")

        (self.application / "VERSION").write_text("1.0.0\n")

        config = self.application / "config"
        config.mkdir()
        (config / "dashboard.ini").write_text("segreto")

        data = self.application / "data"
        data.mkdir()
        (data / "events.sqlite3").write_text("database")

    def test_prepare_valid_release(self):
        create_archive(self.archive, FILES)

        self.assertTrue(
            validate_archive(self.archive, "v1.2.3")
        )

        extract_release(
            self.archive,
            "v1.2.3",
            self.extracted,
        )

        prepare_release(
            self.extracted,
            self.staging,
        )

        self.assertEqual(
            (self.staging / "VERSION").read_text().strip(),
            "1.2.3",
        )

        self.assertEqual(
            backup_manifest(self.extracted),
            backup_manifest(self.staging),
        )

        self.assertFalse((self.staging / "config").exists())
        self.assertFalse((self.staging / "data").exists())
        self.assertFalse((self.staging / "agent").exists())

        self.assertEqual(
            (self.application / "VERSION").read_text().strip(),
            "1.0.0",
        )
        self.assertEqual(
            (self.application / "config/dashboard.ini").read_text(),
            "segreto",
        )
        self.assertEqual(
            (self.application / "data/events.sqlite3").read_text(),
            "database",
        )

    def test_invalid_archive_no_partial_release(self):
        files = dict(FILES)
        del files["backend/app.py"]

        create_archive(self.archive, files)

        with self.assertRaises(ValueError):
            extract_release(
                self.archive,
                "v1.2.3",
                self.extracted,
            )

        self.assertFalse(self.extracted.exists())

    def test_wrong_version_no_partial_release(self):
        create_archive(self.archive, FILES)

        with self.assertRaises(ValueError):
            extract_release(
                self.archive,
                "v9.9.9",
                self.extracted,
            )

        self.assertFalse(self.extracted.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
