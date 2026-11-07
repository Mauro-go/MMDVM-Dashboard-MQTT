#!/usr/bin/env python3
"""Adattatore systemd/HTTP per Standard e Multi.

Non esegue aggiornamenti. Le operazioni sono esplicite
e i comandi vengono eseguiti solo quando invocati.
"""

import subprocess
import urllib.request

from update_deployment import get_profile


class SystemdAdapter:
    def __init__(self, mode, *, runner=None, http_check=None):
        self.profile = get_profile(mode)
        self.runner = runner or subprocess.run
        self.http_check = http_check or self._http_check

        services = self.profile.get("services")
        if not isinstance(services, (list, tuple)) or not services:
            raise ValueError("Profilo senza servizi validi")

        for service in services:
            if (
                not isinstance(service, str)
                or not service.endswith(".service")
                or "/" in service
                or service.startswith("-")
            ):
                raise ValueError("Nome servizio non valido")

        self.services = tuple(services)

    def _run(self, action, service):
        result = self.runner(
            ["systemctl", action, service],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "systemctl " + action + " fallito: " + service
            )

    def stop(self):
        for service in reversed(self.services):
            self._run("stop", service)

    def start(self):
        for service in self.services:
            self._run("start", service)

    def _http_check(self, url):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    def health(self):
        for service in self.services:
            result = self.runner(
                ["systemctl", "is-active", service],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return False

        port = self.profile.get("port")

        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Porta HTTP non valida")

        return bool(
            self.http_check("http://127.0.0.1:" + str(port) + "/")
        )
