import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from update_real_service_flow import (
    prepare_real_service_flow,
    execute_real_service_flow,
)
from update_systemd_adapter import SystemdAdapter


class FakeAdapter:
    def __init__(self, health_results=(True, True)):
        self.events = []
        self.results = iter(health_results)

    def stop(self):
        self.events.append("stop")

    def start(self):
        self.events.append("start")

    def health(self):
        self.events.append("health")
        return next(self.results)


class RealServiceFlowTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.app = root / "application"
        self.release = root / "release"
        self.backups = root / "backups"

        for directory in (self.app, self.release, self.backups):
            directory.mkdir()

        for component in ("backend", "frontend", "admin"):
            for parent, version in (
                (self.app, "old"),
                (self.release, "new"),
            ):
                folder = parent / component
                folder.mkdir()
                (folder / "test.txt").write_text(version)

        (self.app / "VERSION").write_text("1")
        (self.release / "VERSION").write_text("2")

    def execute(self, mode, adapter, **kwargs):
        return execute_real_service_flow(
            mode,
            self.app,
            self.release,
            self.backups,
            adapter=adapter,
            authorized=True,
            **kwargs,
        )

    def test_standard_preparation(self):
        result = prepare_real_service_flow("standard")
        self.assertFalse(result["production_enabled"])
        self.assertTrue(result["services"])

    def test_multi_preparation(self):
        result = prepare_real_service_flow("multi")
        self.assertFalse(result["production_enabled"])
        self.assertTrue(result["services"])

    def test_no_systemctl_during_preparation(self):
        with patch(
            "update_systemd_adapter.subprocess.run",
            side_effect=AssertionError("systemctl invocato"),
        ):
            prepare_real_service_flow("standard")
            prepare_real_service_flow("multi")

    def test_standard_success(self):
        adapter = FakeAdapter()
        result = self.execute("standard", adapter)
        self.assertEqual(result["status"], "completed")
        self.assertEqual((self.app / "VERSION").read_text(), "2")
        self.assertEqual(
            adapter.events,
            ["health", "stop", "start", "health"],
        )

    def test_multi_success(self):
        adapter = FakeAdapter()
        result = self.execute("multi", adapter)
        self.assertEqual(result["status"], "completed")

    def test_health_failure_restores_previous_version(self):
        adapter = FakeAdapter((True, False, True))

        with self.assertRaisesRegex(RuntimeError, "ripristinata"):
            self.execute("standard", adapter)

        self.assertEqual((self.app / "VERSION").read_text(), "1")
        self.assertEqual(
            adapter.events,
            ["health", "stop", "start", "health",
             "stop", "start", "health"],
        )

    def test_authorization_required(self):
        adapter = Mock()

        with self.assertRaises(PermissionError):
            execute_real_service_flow(
                "standard",
                self.app,
                self.release,
                self.backups,
                authorized=False,
                adapter=adapter,
            )

        adapter.stop.assert_not_called()

    def test_real_systemd_adapter_rejected(self):
        adapter = SystemdAdapter("standard")

        with self.assertRaises(RuntimeError):
            self.execute("standard", adapter)

    def test_missing_adapter_rejected(self):
        with self.assertRaises(RuntimeError):
            self.execute("standard", None)

    def test_invalid_adapter_rejected(self):
        with self.assertRaises(ValueError):
            self.execute("standard", object())

    def test_invalid_mode(self):
        with self.assertRaises((ValueError, KeyError)):
            prepare_real_service_flow("invalid")


if __name__ == "__main__":
    unittest.main()
