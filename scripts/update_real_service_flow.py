#!/usr/bin/env python3
"""Esecuzione transazionale protetta Standard/Multi."""

from pathlib import Path
from tempfile import gettempdir

from update_deployment import get_profile
from update_service_flow import execute_service_flow
from update_systemd_adapter import SystemdAdapter


def prepare_real_service_flow(mode):
    profile = get_profile(mode)
    adapter = SystemdAdapter(mode)

    return {
        "mode": mode,
        "services": list(adapter.services),
        "port": profile["port"],
        "production_enabled": False,
        "ready_for_execution": False,
    }


def execute_real_service_flow(
    mode,
    application,
    release,
    backup_root,
    *,
    authorized=False,
    adapter=None,
    fail_after=None,
):
    """Esegue la transazione solo con adapter esplicito di prova.

    Le directory devono trovarsi sotto la directory temporanea.
    L'adapter systemd reale rimane vietato.
    """
    get_profile(mode)

    if not authorized:
        raise PermissionError("Autorizzazione esplicita necessaria")

    if adapter is None:
        raise RuntimeError("Adapter di prova obbligatorio")

    if isinstance(adapter, SystemdAdapter):
        raise RuntimeError("Adapter systemd reale non ancora autorizzato")

    for name in ("stop", "start", "health"):
        if not callable(getattr(adapter, name, None)):
            raise ValueError("Adapter non valido: " + name)

    temporary_root = Path(gettempdir()).resolve(strict=True)

    for path in (application, release, backup_root):
        resolved = Path(path).resolve(strict=True)

        if temporary_root not in resolved.parents:
            raise ValueError("Percorso fuori dalla directory temporanea")

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
