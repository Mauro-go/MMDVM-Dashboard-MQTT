#!/usr/bin/env python3
"""Integrazione protetta dei servizi nel flusso aggiornamenti."""

from update_service_flow import execute_service_flow
from update_systemd_adapter import SystemdAdapter


def execute_integrated_update(
    mode,
    application,
    release,
    backup_root,
    *,
    adapter=None,
    production=False,
    fail_after=None,
):
    """Esegue aggiornamenti soltanto con adapter di prova.

    Un adapter reale non viene mai creato automaticamente.
    """
    if production:
        raise RuntimeError(
            "Aggiornamenti di produzione non ancora abilitati"
        )

    if adapter is None:
        raise RuntimeError(
            "Adapter di prova obbligatorio"
        )

    if isinstance(adapter, SystemdAdapter):
        raise RuntimeError(
            "Adapter systemd reale non autorizzato"
        )

    for name in ("stop", "start", "health"):
        if not callable(getattr(adapter, name, None)):
            raise ValueError(
                "Adapter privo della funzione: " + name
            )

    return execute_service_flow(
        mode,
        application,
        release,
        backup_root,
        stop=adapter.stop,
        start=adapter.start,
        health=adapter.health,
        fail_after=fail_after,
    )
