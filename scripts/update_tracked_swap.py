#!/usr/bin/env python3
"""Sostituzione sperimentale con piano persistente.

Da usare esclusivamente su copie di test.
Non gestisce ancora fsync delle directory applicative,
segnali fatali, servizi systemd o recupero automatico.
"""

import os
import shutil
from pathlib import Path

from update_rename_plan import (
    COMPONENTS,
    save_rename_plan,
    validate_rename_plan,
)


def _exists(path):
    return os.path.lexists(path)


def _check_tree(path):
    if path.is_symlink():
        raise ValueError("Link simbolico non consentito")

    if path.is_dir():
        for entry in path.rglob("*"):
            if entry.is_symlink():
                raise ValueError("Link simbolico interno non consentito")


def _remove(path):
    if path.is_symlink():
        raise ValueError("Rimozione link simbolico vietata")

    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def tracked_swap(source, application, component, plan, plan_path):
    """Esegue una sostituzione registrando le fasi sul disco."""
    validate_rename_plan(plan)

    if component not in COMPONENTS:
        raise ValueError("Componente non consentito")

    source = Path(source)
    application = Path(application)

    if source.is_symlink() or application.is_symlink():
        raise ValueError("Directory simbolica non consentita")

    if not source.is_dir() or not application.is_dir():
        raise ValueError("Directory non valida")

    operation = plan["operations"][component]

    if operation["state"] != "planned":
        raise RuntimeError("Operazione già iniziata")

    origin = source / component
    target = application / operation["target"]
    prepared = application / operation["prepared"]
    previous = application / operation["previous"]

    if not origin.exists():
        raise ValueError("Sorgente mancante")

    if component == "VERSION":
        if not origin.is_file():
            raise ValueError("VERSION non valido")
    elif not origin.is_dir():
        raise ValueError("Directory componente non valida")

    _check_tree(origin)

    for path in (prepared, previous):
        if _exists(path):
            raise RuntimeError("Residuo già presente: " + path.name)

    if target.is_symlink():
        raise ValueError("Destinazione simbolica non consentita")

    # Il piano viene registrato prima di qualsiasi modifica.
    save_rename_plan(plan_path, plan)

    try:
        if origin.is_dir():
            shutil.copytree(origin, prepared, symlinks=False)
        else:
            shutil.copy2(origin, prepared)

        operation["state"] = "prepared"
        save_rename_plan(plan_path, plan)

        if _exists(target):
            os.rename(target, previous)

        # In caso di interruzione qui, il piano permette
        # di individuare la copia precedente.
        operation["state"] = "old_moved"
        save_rename_plan(plan_path, plan)

        os.rename(prepared, target)

        operation["state"] = "new_installed"
        save_rename_plan(plan_path, plan)

        # La copia precedente rimane disponibile fino
        # alla conferma dell'installazione.
        return {
            "component": component,
            "state": "new_installed",
            "previous_exists": _exists(previous),
        }

    except Exception:
        # Non eliminiamo residui ambigui: verranno
        # esaminati dal recupero della transazione.
        raise


def finish_tracked_swap(application, component, plan, plan_path):
    """Conclude una sostituzione già verificata."""
    validate_rename_plan(plan)

    if component not in COMPONENTS:
        raise ValueError("Componente non consentito")

    operation = plan["operations"][component]

    if operation["state"] != "new_installed":
        raise RuntimeError("Sostituzione non confermata")

    application = Path(application)

    if application.is_symlink() or not application.is_dir():
        raise ValueError("Applicazione non valida")

    target = application / operation["target"]
    previous = application / operation["previous"]
    prepared = application / operation["prepared"]

    if not target.exists() or target.is_symlink():
        raise RuntimeError("Componente installato non valido")

    if _exists(prepared):
        raise RuntimeError("Preparazione residua presente")

    # La pulizia è consentita solo dopo una verifica
    # esplicita dello stato installato.
    if _exists(previous):
        _remove(previous)

    operation["state"] = "done"
    save_rename_plan(plan_path, plan)

    return True


def verify_tracked_completion(application, plan_path):
    """Verifica senza modifiche una sostituzione tracciata completa.

    Non autorizza da sola la cancellazione delle copie precedenti.
    """
    from update_rename_plan import load_rename_plan, COMPONENTS

    application = Path(application)
    plan_path = Path(plan_path)

    if application.is_symlink() or not application.is_dir():
        raise ValueError("Directory applicazione non valida")

    plan = load_rename_plan(plan_path)
    operations = plan["operations"]

    result = {
        "transaction_id": plan["transaction_id"],
        "ready": True,
        "components": {},
        "problems": [],
    }

    for component in COMPONENTS:
        operation = operations[component]

        target = application / component
        prepared = application / operation["prepared"]
        previous = application / operation["previous"]

        problems = []

        if operation["state"] != "new_installed":
            problems.append("state_not_installed")

        if not target.exists() or target.is_symlink():
            problems.append("target_missing_or_unsafe")

        if not previous.exists() or previous.is_symlink():
            problems.append("previous_missing_or_unsafe")

        if prepared.exists() or prepared.is_symlink():
            problems.append("prepared_residue")

        result["components"][component] = {
            "state": operation["state"],
            "ready": not problems,
            "problems": problems,
        }

        for problem in problems:
            result["problems"].append(component + ":" + problem)

    result["ready"] = not result["problems"]
    return result
