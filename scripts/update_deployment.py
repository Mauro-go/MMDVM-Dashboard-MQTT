#!/usr/bin/env python3
"""Profili di aggiornamento Dashboard Standard e Multi."""

from pathlib import Path

PROFILES = {
    "standard": {
        "directory": "/opt/mmdvm-dashboard",
        "port": 8089,
        "services": (
            "mmdvm-dashboard-mqtt.service",
            "mmdvm-mqtt-collector.service",
            "mmdvm-telegram-bot.service",
        ),
    },
    "multi": {
        "directory": "/opt/mmdvm-dashboard-multi",
        "port": 8090,
        "services": (
            "mmdvm-dashboard-multi.service",
            "mmdvm-multi-collector.service",
        ),
    },
}


def detect_deployment(installation_path):
    """Riconosce il profilo dal percorso di installazione."""
    path = Path(installation_path).resolve()

    for name, profile in PROFILES.items():
        if path == Path(profile["directory"]):
            return name

    raise ValueError(
        f"Installazione Dashboard non riconosciuta: {path}"
    )


def get_profile(mode):
    """Restituisce il profilo senza modificare i servizi."""
    if mode not in PROFILES:
        raise ValueError(f"Modalità non valida: {mode}")

    profile = PROFILES[mode]

    return {
        "mode": mode,
        "directory": profile["directory"],
        "port": profile["port"],
        "services": tuple(profile["services"]),
    }


if __name__ == "__main__":
    for name in PROFILES:
        print(get_profile(name))
