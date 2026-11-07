#!/usr/bin/env python3
"""Verifica HTTP della Dashboard dopo un aggiornamento."""

import json
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BASE_URL = "http://127.0.0.1:8089"

REQUIRED_STATUS_FIELDS = ("repeater", "system", "agent")


def check_health(base_url=BASE_URL, attempts=10, delay=2):
    """Verifica che le API rispondano correttamente."""
    if attempts < 1:
        raise ValueError("Numero tentativi non valido")

    last_error = None

    for attempt in range(attempts):
        try:
            with urlopen(
                base_url + "/api/status", timeout=5
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"HTTP status: {response.status}"
                    )

                status = json.load(response)

            if not isinstance(status, dict):
                raise ValueError("Risposta status non valida")

            for field in REQUIRED_STATUS_FIELDS:
                if not isinstance(status.get(field), dict):
                    raise ValueError(
                        "Campo status mancante o non valido: " + field
                    )

            with urlopen(
                base_url + "/api/config", timeout=5
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"HTTP config: {response.status}"
                    )

                config = json.load(response)

            if not isinstance(config, dict):
                raise ValueError("Risposta config non valida")

            return True

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            RuntimeError,
            json.JSONDecodeError,
        ) as exc:
            last_error = str(exc)

            if attempt < attempts - 1:
                time.sleep(delay)

    raise RuntimeError(
        "Controllo Dashboard fallito: " + str(last_error)
    )



def check_services_health(snapshot, runner=None):
    """Verifica i servizi che erano attivi prima dell'aggiornamento."""
    allowed = {
        "mmdvm-dashboard-mqtt.service",
        "mmdvm-mqtt-collector.service",
        "mmdvm-telegram-bot.service",
    }

    if not isinstance(snapshot, dict) or set(snapshot) != allowed:
        raise ValueError("Snapshot servizi non valido")

    for service, state in snapshot.items():
        if not isinstance(state, dict):
            raise ValueError("Stato servizio non valido")

        if state.get("active") not in {"active", "inactive"}:
            raise ValueError("Stato active non valido")

    if runner is None:
        def runner(service):
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.stdout.strip()

    for service, state in snapshot.items():
        actual = runner(service)

        if state["active"] == "active" and actual != "active":
            raise RuntimeError(
                f"Servizio non attivo dopo aggiornamento: {service}"
            )

        if state["active"] == "inactive" and actual != "inactive":
            raise RuntimeError(
                f"Servizio precedentemente inattivo modificato: {service}"
            )

    return True


if __name__ == "__main__":
    check_health()
    print("OK - Dashboard HTTP funzionante")
