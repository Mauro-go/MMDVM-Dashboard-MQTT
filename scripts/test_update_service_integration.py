import tempfile
import unittest
from pathlib import Path

from update_service_integration import execute_integrated_update
from update_systemd_adapter import SystemdAdapter


class FakeAdapter:
    def __init__(self, health_results=None):
        self.events = []
        self.health_results = iter(
            health_results or [True, True]
        )

    def stop(self):
        self.events.append("stop")

    def start(self):
        self.events.append("start")

    def health(self):
        self.events.append("health")
        return next(self.health_results)


class ServiceIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        root = Path(self.tmp.name)
        self.app = root / "app"
        self.release = root / "release"
        self.backups = root / "backups"

        for directory in (self.app, self.release, self.backups):
            directory.mkdir()

        for component in ("backend", "frontend", "admin"):
            for parent, content in (
                (self.app, "old"),
                (self.release, "new"),
            ):
                folder = parent / component
                folder.mkdir()
                (folder / "test.txt").write_text(content)

        (self.app / "VERSION").write_text("1")
        (self.release / "VERSION").write_text("2")

    def run_update(self, mode, adapter, **kwargs):
        return execute_integrated_update(
            mode,
            self.app,
            self.release,
            self.backups,
            adapter=adapter,
            **kwargs,
        )

    def test_standard_success(self):
        adapter = FakeAdapter()
        result = self.run_update("standard", adapter)
        self.assertEqual(result["status"], "completed")
        self.assertEqual((self.app / "VERSION").read_text(), "2")

    def test_multi_success(self):
        adapter = FakeAdapter()
        result = self.run_update("multi", adapter)
        self.assertEqual(result["status"], "completed")

    def test_rollback_after_health_failure(self):
        adapter = FakeAdapter([True, False, True])

        with self.assertRaisesRegex(RuntimeError, "ripristinata"):
            self.run_update("standard", adapter)

        self.assertEqual((self.app / "VERSION").read_text(), "1")
        self.assertEqual(
            adapter.events,
            ["health", "stop", "start", "health",
             "stop", "start", "health"],
        )

    def test_production_blocked(self):
        with self.assertRaises(RuntimeError):
            self.run_update(
                "standard", FakeAdapter(), production=True
            )

    def test_missing_adapter_blocked(self):
        with self.assertRaises(RuntimeError):
            self.run_update("standard", None)

    def test_real_systemd_adapter_blocked(self):
        adapter = SystemdAdapter(
            "standard",
            runner=lambda *a, **k: None,
            http_check=lambda url: True,
        )
        with self.assertRaises(RuntimeError):
            self.run_update("standard", adapter)

    def test_invalid_adapter_blocked(self):
        with self.assertRaises(ValueError):
            self.run_update("standard", object())


if __name__ == "__main__":
    unittest.main()
