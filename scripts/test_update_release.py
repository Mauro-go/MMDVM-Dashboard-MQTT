#!/usr/bin/env python3
"""Test isolati del validatore delle release."""

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from update_release import validate_archive, extract_release

REQUIRED = {
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


def make_archive(path, files, extra=None):
    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            data = io.BytesIO(content)
            info = tarfile.TarInfo(
                "MMDVM-Dashboard-MQTT-1.2.3/" + name
            )
            info.size = len(content)
            archive.addfile(info, data)

        if extra is not None:
            archive.addfile(extra)


class ReleaseTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "release.tar.gz"

    def test_valid_github_archive(self):
        make_archive(self.archive, REQUIRED)
        self.assertTrue(validate_archive(self.archive, "v1.2.3"))

        destination = self.root / "extracted"
        extract_release(self.archive, "v1.2.3", destination)

        self.assertTrue((destination / "backend/app.py").is_file())
        self.assertTrue((destination / "VERSION").is_file())
        self.assertFalse((destination / "agent").exists())
        self.assertFalse((destination / "config").exists())
        self.assertFalse((destination / "install.sh").exists())

    def test_wrong_version(self):
        make_archive(self.archive, REQUIRED)
        with self.assertRaises(ValueError):
            validate_archive(self.archive, "v2.0.0")

    def test_missing_file(self):
        files = dict(REQUIRED)
        del files["backend/app.py"]
        make_archive(self.archive, files)

        with self.assertRaises(ValueError):
            validate_archive(self.archive, "v1.2.3")

    def test_path_traversal(self):
        extra = tarfile.TarInfo(
            "MMDVM-Dashboard-MQTT-1.2.3/../evil"
        )
        extra.size = 0
        make_archive(self.archive, REQUIRED, extra)

        with self.assertRaises(ValueError):
            validate_archive(self.archive, "v1.2.3")

    def test_symlink(self):
        extra = tarfile.TarInfo(
            "MMDVM-Dashboard-MQTT-1.2.3/backend/link"
        )
        extra.type = tarfile.SYMTYPE
        extra.linkname = "/etc/passwd"
        make_archive(self.archive, REQUIRED, extra)

        with self.assertRaises(ValueError):
            validate_archive(self.archive, "v1.2.3")

    def test_protected_file(self):
        files = dict(REQUIRED)
        files["backend/data/events.sqlite3"] = b"database"
        make_archive(self.archive, files)

        with self.assertRaises(ValueError):
            validate_archive(self.archive, "v1.2.3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
