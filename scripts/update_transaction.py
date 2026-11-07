#!/usr/bin/env python3
"""Transazione applicativa sperimentale per test isolati."""

import shutil
from pathlib import Path

from update_backup import (
    COMPONENTS,
    backup_application,
    backup_manifest,
    restore_application,
    verify_backup,
)


def install_components(source, destination):
    """Copia componenti applicativi in una destinazione di prova."""
    source = Path(source)
    destination = Path(destination)

    if source.is_symlink() or not source.is_dir():
        raise ValueError("Sorgente non valida")

    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Destinazione non valida")

    for component in COMPONENTS:
        item = source / component

        if item.is_symlink() or not item.exists():
            raise ValueError("Componente sorgente non valido")

        if component == "VERSION":
            if not item.is_file():
                raise ValueError("VERSION non valida")
        elif not item.is_dir():
            raise ValueError("Directory sorgente non valida")

    for component in COMPONENTS:
        target = destination / component

        if target.is_symlink():
            raise ValueError("Link simbolico nella destinazione")

        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

        source_item = source / component

        if component == "VERSION":
            shutil.copy2(source_item, target)
        else:
            shutil.copytree(source_item, target, symlinks=False)


def test_transaction(application, release, backup, health_check):
    """Simula installazione, controllo e rollback in ambiente isolato."""
    backup_application(application, backup)
    manifest = backup_manifest(backup)

    verify_backup(backup, manifest)

    try:
        install_components(release, application)

        if not health_check(application):
            raise RuntimeError("Controllo funzionamento fallito")

        return "updated"

    except Exception:
        restore_application(backup, application, manifest)
        return "rolled_back"


def prepare_release(source, staging):
    """Prepara una copia applicativa senza modificare la destinazione."""
    import os

    source = Path(source)
    staging = Path(staging)

    if source.is_symlink() or not source.is_dir():
        raise ValueError("Sorgente non valida")

    if staging.exists() or staging.is_symlink():
        raise ValueError("Staging già esistente")

    for component in COMPONENTS:
        item = source / component

        if item.is_symlink() or not item.exists():
            raise ValueError("Componente non valido: " + component)

        if component == "VERSION":
            if not item.is_file():
                raise ValueError("VERSION non valida")
        elif not item.is_dir():
            raise ValueError("Directory non valida: " + component)

        if component != "VERSION":
            for root, dirs, files in os.walk(item, followlinks=False):
                for name in dirs + files:
                    if (Path(root) / name).is_symlink():
                        raise ValueError("Link simbolico nella release")

    staging.mkdir(mode=0o700)

    try:
        for component in COMPONENTS:
            source_item = source / component
            target = staging / component

            if component == "VERSION":
                shutil.copy2(source_item, target)
            else:
                shutil.copytree(
                    source_item,
                    target,
                    symlinks=False,
                )

        # Verifica che la copia preparata corrisponda alla sorgente.
        if backup_manifest(source) != backup_manifest(staging):
            raise ValueError("Integrità dello staging non valida")

    except Exception:
        shutil.rmtree(staging)
        raise

    return staging
