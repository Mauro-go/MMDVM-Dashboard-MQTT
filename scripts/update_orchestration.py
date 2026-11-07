#!/usr/bin/env python3
"""Orchestrazione sperimentale degli aggiornamenti.

Non arresta servizi e non autorizza aggiornamenti di produzione.
"""

from update_deployment import get_profile


def build_update_plan(mode):
    """Prepara il piano senza modificare il sistema."""
    profile = get_profile(mode)

    return {
        "mode": mode,
        "profile": profile,
        "production_enabled": False,
        "steps": [
            "validate",
            "backup",
            "stop_services",
            "install",
            "start_services",
            "health_check",
            "complete",
        ],
        "rollback_steps": [
            "stop_services",
            "restore_backup",
            "start_services",
            "health_check",
        ],
    }


def validate_update_plan(plan):
    """Verifica la struttura del piano."""
    if not isinstance(plan, dict):
        raise ValueError("Piano non valido")

    if plan.get("production_enabled") is not False:
        raise RuntimeError(
            "Aggiornamenti di produzione non autorizzati"
        )

    steps = plan.get("steps")

    if not isinstance(steps, list):
        raise ValueError("Passaggi non validi")

    required = [
        "validate",
        "backup",
        "stop_services",
        "install",
        "start_services",
        "health_check",
        "complete",
    ]

    if steps != required:
        raise ValueError(
            "Sequenza aggiornamento non valida"
        )

    return True


def simulate_update_plan(mode):
    """Simula il piano senza eseguire operazioni sui servizi."""
    plan = build_update_plan(mode)
    validate_update_plan(plan)

    return {
        "status": "simulated",
        "mode": mode,
        "production_enabled": False,
        "steps": plan["steps"],
        "rollback_steps": plan["rollback_steps"],
    }



def execute_simulated_plan(
    mode,
    application,
    release,
    backup_root,
    *,
    fail_after=None,
):
    """Esegue una transazione esclusivamente in un ambiente temporaneo.

    Non controlla servizi systemd e non abilita la produzione.
    """
    from pathlib import Path
    import tempfile
    from update_coordinator import run_simulated_update

    plan = build_update_plan(mode)
    validate_update_plan(plan)

    application = Path(application).resolve(strict=True)
    release = Path(release).resolve(strict=True)
    backup_root = Path(backup_root).resolve(strict=True)

    temporary_root = Path(tempfile.gettempdir()).resolve()

    for path in (application, release, backup_root):
        if temporary_root not in path.parents:
            raise ValueError(
                "Simulazione consentita solo in directory temporanee"
            )

    result = run_simulated_update(
        application,
        release,
        backup_root,
        mode=mode,
        production=False,
        fail_after=fail_after,
    )

    return {
        **result,
        "mode": mode,
        "production_enabled": False,
        "services_modified": False,
    }

def execute_production_update(*args, **kwargs):
    """Blocco esplicito degli aggiornamenti reali."""
    raise RuntimeError(
        "Aggiornamenti di produzione non ancora abilitati"
    )
