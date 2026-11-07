#!/usr/bin/env python3
"""Motore transazionale: installazione e rollback su percorsi di test."""

import hashlib
import json
import os
import shutil
from pathlib import Path

from update_transaction_state import (
    write_state,
    read_state,
    pending_transactions,
)

COMPONENTS = ("backend", "frontend", "admin", "VERSION")


def fingerprint(root):
    root = Path(root)
    result = {}

    for component in COMPONENTS:
        path = root / component

        if path.is_symlink():
            raise RuntimeError("Symlink non consentito: " + str(path))

        if component == "VERSION":
            if not path.is_file():
                raise RuntimeError("VERSION mancante")
            files = [path]
        else:
            if not path.is_dir():
                raise RuntimeError("Componente mancante: " + component)
            files = sorted(p for p in path.rglob("*") if p.is_file())

        for file in files:
            if file.is_symlink():
                raise RuntimeError("Symlink non consentito: " + str(file))
            relative = file.relative_to(root).as_posix()
            result[relative] = hashlib.sha256(file.read_bytes()).hexdigest()

    return result


def copy_snapshot(source, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)

    for component in COMPONENTS:
        src = Path(source) / component
        dst = destination / component

        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)


def swap_component(staged, application, transaction, component):
    staged = Path(staged)
    application = Path(application)
    transaction = Path(transaction)

    previous_dir = transaction / "previous"
    previous_dir.mkdir(exist_ok=True)

    current = application / component
    incoming = staged / component
    previous = previous_dir / component

    if previous.exists():
        raise RuntimeError("Componente precedente già presente")

    os.replace(current, previous)

    try:
        os.replace(incoming, current)
    except BaseException:
        if not current.exists() and previous.exists():
            os.replace(previous, current)
        raise



def restore_snapshot(snapshot, application, transaction):
    """Ripristino ripetibile anche dopo interruzione fra due rename."""
    snapshot = Path(snapshot).resolve(strict=True)
    application = Path(application).resolve(strict=True)
    transaction = Path(transaction).resolve(strict=True)

    expected = fingerprint(snapshot)

    for component in COMPONENTS:
        source = snapshot / component
        current = application / component
        temporary = application / (".restore-" + component)
        displaced = transaction / ("displaced-" + component)

        for path in (temporary, displaced):
            if path.is_symlink():
                raise RuntimeError("Symlink imprevisto")

            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

        if source.is_dir():
            shutil.copytree(source, temporary, symlinks=False)
        else:
            shutil.copy2(source, temporary)

        if current.exists() or current.is_symlink():
            os.replace(current, displaced)

        try:
            os.replace(temporary, current)
        except BaseException:
            if displaced.exists() and not current.exists():
                os.replace(displaced, current)
            raise

        if displaced.is_dir():
            shutil.rmtree(displaced)
        elif displaced.exists():
            displaced.unlink()

    if fingerprint(application) != expected:
        raise RuntimeError("Ripristino non coerente")

def save_fingerprint(path, values):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(values, indent=2, sort_keys=True)
    )
    os.replace(temporary, path)


def verify_fingerprint(snapshot, manifest):
    expected = json.loads(Path(manifest).read_text())
    actual = fingerprint(snapshot)

    if actual != expected:
        raise RuntimeError("Integrità backup non valida")

    return True


def recover_transaction(transaction, application):
    """Recupera una transazione incompleta da backup verificato."""
    transaction = Path(transaction).resolve(strict=True)
    application = Path(application).resolve(strict=True)

    journal = transaction / "state.json"
    backup = transaction / "backup"
    manifest = transaction / "backup-fingerprint.json"

    state = read_state(journal)

    if state["status"] in ("completed", "rolled_back"):
        return state["status"]

    if state["status"] not in (
        "backup",
        "stopping",
        "installing",
        "starting",
        "rolling_back",
    ):
        raise RuntimeError("Stato non recuperabile")

    if not backup.is_dir() or not manifest.is_file():
        raise RuntimeError(
            "Backup verificabile assente: recupero bloccato"
        )

    verify_fingerprint(backup, manifest)

    state["status"] = "rolling_back"
    write_state(journal, state)

    restore_snapshot(backup, application, transaction)

    verify_fingerprint(backup, manifest)

    if fingerprint(application) != fingerprint(backup):
        raise RuntimeError("Ripristino non coerente")

    state["status"] = "rolled_back"
    write_state(journal, state)

    return "rolled_back"


def execute_test_transaction(
    release,
    application,
    backup_root,
    *,
    fail_after=None,
):
    release = Path(release).resolve(strict=True)
    application = Path(application).resolve(strict=True)
    backup_root = Path(backup_root).resolve(strict=True)

    if pending_transactions(backup_root):
        raise RuntimeError("Transazione precedente incompleta")

    if fingerprint(release) == {}:
        raise RuntimeError("Release vuota")

    transaction = backup_root / "transaction-test"

    if transaction.exists():
        raise RuntimeError("Transazione già presente")

    transaction.mkdir()
    journal = transaction / "state.json"

    backup = transaction / "backup"
    staged = transaction / "staged"

    try:
        write_state(journal, {"status": "backup"})
        copy_snapshot(application, backup)
        original = fingerprint(backup)
        save_fingerprint(
            transaction / "backup-fingerprint.json",
            original,
        )

        if fingerprint(application) != original:
            raise RuntimeError("Backup non coerente")

        copy_snapshot(release, staged)

        if fingerprint(staged) != fingerprint(release):
            raise RuntimeError("Staging non coerente")

        write_state(journal, {"status": "installing"})

        for index, component in enumerate(COMPONENTS, 1):
            swap_component(staged, application, transaction, component)

            if fail_after == index:
                raise RuntimeError("Errore simulato")

        if fingerprint(application) != fingerprint(release):
            raise RuntimeError("Installazione non coerente")

        write_state(journal, {"status": "completed"})
        return "completed"

    except Exception:
        write_state(journal, {"status": "rolling_back"})

        if backup.exists():
            verify_fingerprint(
                backup,
                transaction / "backup-fingerprint.json",
            )
            restore_snapshot(backup, application, transaction)

            if fingerprint(application) != fingerprint(backup):
                raise RuntimeError("Rollback non coerente")

            write_state(journal, {"status": "rolled_back"})

        raise
