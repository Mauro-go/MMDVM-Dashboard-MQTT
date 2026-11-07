import tempfile
import unittest
from pathlib import Path

from update_service_flow import execute_service_flow


class ServiceFlowTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)

        self.app = root / "app"
        self.release = root / "release"
        self.backups = root / "backups"

        for path in (self.app, self.release, self.backups):
            path.mkdir()

        for component in ("backend", "frontend", "admin"):
            for parent, value in (
                (self.app, "old"),
                (self.release, "new"),
            ):
                folder = parent / component
                folder.mkdir()
                (folder / "test.txt").write_text(value)

        (self.app / "VERSION").write_text("1")
        (self.release / "VERSION").write_text("2")
        self.events = []

    def stop(self):
        self.events.append("stop")

    def start(self):
        self.events.append("start")

    def healthy(self):
        self.events.append("health")
        return True

    def test_standard_success(self):
        result = execute_service_flow(
            "standard", self.app, self.release, self.backups,
            stop=self.stop, start=self.start, health=self.healthy,
        )
        self.assertEqual(result["health"], "ok")
        self.assertEqual(
            self.events, ["health", "stop", "start", "health"]
        )
        self.assertEqual((self.app / "VERSION").read_text(), "2")

    def test_multi_success(self):
        result = execute_service_flow(
            "multi", self.app, self.release, self.backups,
            stop=self.stop, start=self.start, health=self.healthy,
        )
        self.assertEqual(result["status"], "completed")

    def test_initial_health_failure(self):
        def unhealthy():
            return False

        with self.assertRaisesRegex(RuntimeError, "iniziale"):
            execute_service_flow(
                "standard", self.app, self.release, self.backups,
                stop=self.stop, start=self.start, health=unhealthy,
            )

        self.assertEqual(self.events, [])
        self.assertEqual((self.app / "VERSION").read_text(), "1")

    def test_install_failure_restores_services(self):
        with self.assertRaises(RuntimeError):
            execute_service_flow(
                "standard", self.app, self.release, self.backups,
                stop=self.stop, start=self.start,
                health=self.healthy, fail_after="frontend",
            )

        self.assertEqual(
            self.events, ["health", "stop", "start"]
        )
        self.assertEqual((self.app / "VERSION").read_text(), "1")

    def test_final_health_failure_is_reported(self):
        calls = iter([True, False, True])

        def health():
            return next(calls)

        with self.assertRaisesRegex(
            RuntimeError, "versione precedente ripristinata"
        ):
            execute_service_flow(
                "multi", self.app, self.release, self.backups,
                stop=self.stop, start=self.start, health=health,
            )

        self.assertEqual(
            (self.app / "VERSION").read_text(), "1"
        )
        self.assertEqual(
            self.events,
            ["stop", "start", "stop", "start"],
        )

    def test_invalid_handlers(self):
        with self.assertRaises(ValueError):
            execute_service_flow(
                "standard", self.app, self.release, self.backups,
                stop=None, start=self.start, health=self.healthy,
            )


if __name__ == "__main__":
    unittest.main()
