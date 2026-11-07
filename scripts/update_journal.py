#!/usr/bin/env python3
"""Registro persistente delle transazioni di aggiornamento."""

import json
import os
import tempfile
from pathlib import Path

STATES = {
    "prepared",
    "stopped",
    "installing",
    "installed",
    "checking",
    "completed",
    "rolling_back",
    "rolled_back",
}

COMPONENTS = ("backend", "frontend", "admin", "VERSION")


def validate_journal(data):
    if not isinstance(data, dict):
        raise ValueError("Registro non valido")

    required = {"state", "completed_components"}
    optional = {"pending_component", "transaction_id", "installation_path"}

    if not required.issubset(data):
        raise ValueError("Campi obbligatori mancanti")

    if not set(data).issubset(required | optional):
        raise ValueError("Campi del registro non validi")

    if data["state"] not in STATES:
        raise ValueError("Stato transazione non valido")

    completed = data["completed_components"]

    if not isinstance(completed, list):
        raise ValueError("Elenco componenti non valido")

    if len(completed) != len(set(completed)):
        raise ValueError("Componenti duplicati")

    if any(name not in COMPONENTS for name in completed):
        raise ValueError("Componente sconosciuto")

    transaction_id = data.get("transaction_id")

    if transaction_id is not None:
        import re

        if not isinstance(transaction_id, str):
            raise ValueError("Identificativo transazione non valido")

        if not re.fullmatch(
            r"[0-9a-f]{32}", transaction_id
        ):
            raise ValueError("Formato identificativo non valido")

    installation_path = data.get("installation_path")

    if installation_path is not None:
        if not isinstance(installation_path, str):
            raise ValueError("Percorso installazione non valido")

        path = Path(installation_path)

        if (
            not path.is_absolute()
            or ".." in path.parts
            or installation_path != str(path)
            or path == Path("/")
        ):
            raise ValueError("Percorso installazione non sicuro")

    pending = data.get("pending_component")

    if pending is not None:
        if pending not in COMPONENTS:
            raise ValueError("Componente pending non valido")

        if pending in completed:
            raise ValueError("Componente pending già completato")

        if data["state"] not in {"installing", "rolling_back"}:
            raise ValueError("Pending non ammesso in questo stato")

    return True


def save_journal(path, data):
    """Salva il registro con sostituzione atomica del file."""
    validate_journal(data)

    path = Path(path)
    parent = path.parent

    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("Directory registro non valida")

    fd, temporary = tempfile.mkstemp(
        prefix=".update-journal-",
        dir=parent,
    )

    try:
        os.fchmod(fd, 0o600)

        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(temporary, path)

        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_journal(path):
    path = Path(path)

    if path.is_symlink():
        raise ValueError("Registro con link simbolico")

    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)

    validate_journal(data)
    return data
