import subprocess
import unittest
from unittest.mock import patch

from update_systemd_adapter import SystemdAdapter


class SystemdAdapterTests(unittest.TestCase):

    def setUp(self):
        self.commands = []

        def runner(args, **kwargs):
            self.commands.append(args)
            return subprocess.CompletedProcess(
                args, 0, stdout="active", stderr=""
            )

        self.runner = runner

    def test_standard_profile(self):
        adapter = SystemdAdapter(
            "standard",
            runner=self.runner,
            http_check=lambda url: True,
        )
        self.assertTrue(adapter.services)

    def test_multi_profile(self):
        adapter = SystemdAdapter(
            "multi",
            runner=self.runner,
            http_check=lambda url: True,
        )
        self.assertTrue(adapter.services)

    def test_stop_reverse_order(self):
        adapter = SystemdAdapter(
            "standard", runner=self.runner
        )
        adapter.stop()
        self.assertEqual(
            [cmd[2] for cmd in self.commands],
            list(reversed(adapter.services)),
        )

    def test_start_order(self):
        adapter = SystemdAdapter(
            "standard", runner=self.runner
        )
        adapter.start()
        self.assertEqual(
            [cmd[2] for cmd in self.commands],
            list(adapter.services),
        )

    def test_health_success(self):
        adapter = SystemdAdapter(
            "multi",
            runner=self.runner,
            http_check=lambda url: True,
        )
        self.assertTrue(adapter.health())

    def test_health_http_failure(self):
        adapter = SystemdAdapter(
            "standard",
            runner=self.runner,
            http_check=lambda url: False,
        )
        self.assertFalse(adapter.health())

    def test_systemd_failure(self):
        def failed(args, **kwargs):
            return subprocess.CompletedProcess(args, 1)

        adapter = SystemdAdapter(
            "standard", runner=failed
        )

        with self.assertRaises(RuntimeError):
            adapter.stop()

    def test_inactive_service(self):
        def inactive(args, **kwargs):
            return subprocess.CompletedProcess(args, 3)

        adapter = SystemdAdapter(
            "multi",
            runner=inactive,
            http_check=lambda url: True,
        )
        self.assertFalse(adapter.health())

    def test_invalid_service_rejected(self):
        profile = {
            "services": ["../../bad.service"],
            "port": 8080,
        }

        with patch(
            "update_systemd_adapter.get_profile",
            return_value=profile,
        ):
            with self.assertRaises(ValueError):
                SystemdAdapter("standard", runner=self.runner)


if __name__ == "__main__":
    unittest.main()
