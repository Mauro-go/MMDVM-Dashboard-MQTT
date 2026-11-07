#!/usr/bin/env python3
"""Sostituzione controllata di componenti applicativi.

Modulo sperimentale: non utilizzare direttamente in produzione.
Richiede servizi arrestati e un coordinatore con journal.
"""

import os
import shutil
import uuid
from pathlib import Path

COMPONENTS = ("backend", "frontend", "admin", "VERSION")



def check_update_residues(destination):
    """Blocca nuove installazioni se esistono residui di rinomina."""
    destination = Path(destination)

    if not destination.is_dir() or destination.is_symlink():
        raise ValueError("Destinazione non valida")

    residues = sorted(
        path.name
        for path in destination.iterdir()
        if path.name.startswith((".update-new-", ".update-old-"))
    )

    if residues:
        raise RuntimeError(
            "Residui di aggiornamento: " + ", ".join(residues)
        )

    return True


def replace_component(source, destination, component):
    """Prepara e sostituisce un componente con ripristino sugli errori."""
    if component not in COMPONENTS:
        raise ValueError("Componente non consentito")

    source = Path(source)
    destination = Path(destination)

    if source.is_symlink() or destination.is_symlink():
        raise ValueError("Percorso simbolico non consentito")

    origin = source / component
    target = destination / component

    if origin.is_symlink() or target.is_symlink():
        raise ValueError("Componente simbolico non consentito")

    if not origin.exists():
        raise ValueError("Componente sorgente mancante")

    if not destination.is_dir():
        raise ValueError("Destinazione non valida")

    if component == "VERSION":
        if not origin.is_file():
            raise ValueError("VERSION non è un file")
    elif not origin.is_dir():
        raise ValueError("Componente non è una directory")

    token = uuid.uuid4().hex
    prepared = destination / (".update-new-" + token)
    previous = destination / (".update-old-" + token)

    old_moved = False
    new_installed = False

    try:
        if origin.is_dir():
            shutil.copytree(origin, prepared, symlinks=True)
        else:
            shutil.copy2(origin, prepared, follow_symlinks=False)

        # Rifiuta collegamenti anche all'interno del componente.
        if prepared.is_dir():
            for path in prepared.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Link interno non consentito")

        if target.exists():
            os.rename(target, previous)
            old_moved = True

        try:
            os.rename(prepared, target)
            new_installed = True
        except Exception:
            if old_moved:
                os.rename(previous, target)
                old_moved = False
            raise

        if old_moved:
            if previous.is_dir():
                shutil.rmtree(previous)
            else:
                previous.unlink()
            old_moved = False

    finally:
        # Se il ripristino immediato fallisce, conserviamo la
        # copia precedente per un recupero successivo.
        if prepared.exists():
            if prepared.is_dir():
                shutil.rmtree(prepared)
            else:
                prepared.unlink()

    return {
        "component": component,
        "installed": new_installed,
    }
