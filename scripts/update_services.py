#!/usr/bin/env python3
"""Gestione dello stato dei servizi Dashboard durante gli aggiornamenti."""

import subprocess

from update_deployment import get_profile

# Compatibilità con i test e le installazioni Standard.
SERVICES = get_profile("standard")["services"]


def services_for(mode="standard"):
    """Servizi autorizzati per il profilo selezionato."""
    return get_profile(mode)["services"]



def service_state(service, mode="standard"):
    if service not in services_for(mode):
        raise ValueError("Servizio non autorizzato")

    def query(command):
        result = subprocess.run(
            ["systemctl", command, service],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode not in (0, 1, 3, 4):
            raise RuntimeError(
                f"Impossibile leggere {command} per {service}: "
                f"{result.stderr.strip()}"
            )
        return result.stdout.strip()

    return {
        "active": query("is-active"),
        "enabled": query("is-enabled"),
    }


def snapshot_services(mode="standard"):
    """Registra lo stato dei servizi senza modificarli."""
    return {
        service: service_state(service, mode)
        for service in services_for(mode)
    }


if __name__ == "__main__":
    import json
    print(json.dumps(snapshot_services(), indent=2))


def restore_services(snapshot, runner=None, mode="standard"):
    """Ripristina gli stati active/enabled salvati.

    Il runner permette di simulare systemctl durante i test.
    """
    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot non valido")

    if set(snapshot) != set(services_for(mode)):
        raise ValueError("Elenco servizi non valido")

    allowed_active = {"active", "inactive"}
    allowed_enabled = {"enabled", "disabled"}

    for service, state in snapshot.items():
        if not isinstance(state, dict):
            raise ValueError("Stato servizio non valido")

        if state.get("active") not in allowed_active:
            raise ValueError("Stato active non valido")

        if state.get("enabled") not in allowed_enabled:
            raise ValueError("Stato enabled non valido")

    if runner is None:
        def runner(command):
            subprocess.run(
                command,
                check=True,
                timeout=30,
            )

    # Prima ripristina l'abilitazione all'avvio.
    for service in services_for(mode):
        action = (
            "enable"
            if snapshot[service]["enabled"] == "enabled"
            else "disable"
        )
        runner(["systemctl", action, service])

    # Ferma i servizi che erano inattivi.
    for service in services_for(mode):
        if snapshot[service]["active"] == "inactive":
            runner(["systemctl", "stop", service])

    # Avvia soltanto quelli precedentemente attivi.
    for service in services_for(mode):
        if snapshot[service]["active"] == "active":
            runner(["systemctl", "start", service])

    return True
