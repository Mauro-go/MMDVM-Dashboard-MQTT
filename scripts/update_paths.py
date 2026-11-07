#!/usr/bin/env python3
"""Percorsi controllati per le transazioni di aggiornamento."""

import re
from pathlib import Path


def validate_transaction_id(transaction_id):
    """Accetta esclusivamente identificativi esadecimali di 32 caratteri."""
    if not isinstance(transaction_id, str):
        raise ValueError("Identificativo transazione non valido")

    if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise ValueError("Formato identificativo non valido")

    return transaction_id


def transaction_paths(backup_root, transaction_id):
    """Restituisce i percorsi previsti per una transazione."""
    transaction_id = validate_transaction_id(transaction_id)
    backup_root = Path(backup_root)

    if not backup_root.is_absolute():
        raise ValueError("Percorso backup non assoluto")

    if backup_root.is_symlink():
        raise ValueError("Directory backup con link simbolico")

    transaction = backup_root / transaction_id

    return {
        "transaction": transaction,
        "backup": transaction / "backup",
        "manifest": transaction / "manifest.json",
        "journal": transaction / "journal.json",
    }


def verify_transaction_paths(backup_root, transaction_id):
    """Verifica le directory esistenti senza crearle o modificarle."""
    paths = transaction_paths(backup_root, transaction_id)
    root = Path(backup_root)

    for directory in (root, paths["transaction"], paths["backup"]):
        if directory.is_symlink():
            raise ValueError("Link simbolico nel percorso backup")

        if directory.exists() and not directory.is_dir():
            raise ValueError("Componente percorso non è una directory")

    for name in ("manifest", "journal"):
        path = paths[name]

        if path.is_symlink():
            raise ValueError("Link simbolico nel file " + name)

        if path.exists() and not path.is_file():
            raise ValueError("File transazione non regolare")

    return paths


def verify_directory_chain(path, require_root=False):
    """Controlla ogni componente di un percorso assoluto."""
    import os
    import stat

    path = Path(path)

    if (
        not path.is_absolute()
        or ".." in path.parts
        or str(path) != os.path.normpath(str(path))
    ):
        raise ValueError("Percorso non valido")

    current = Path("/")

    for component in path.parts[1:]:
        current = current / component

        try:
            info = current.lstat()
        except FileNotFoundError as exc:
            raise ValueError(
                "Directory mancante: " + str(current)
            ) from exc

        if stat.S_ISLNK(info.st_mode):
            raise ValueError(
                "Link simbolico non autorizzato: " + str(current)
            )

        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(
                "Componente non directory: " + str(current)
            )

        if require_root and info.st_uid != 0:
            raise ValueError(
                "Directory non appartenente a root: " + str(current)
            )

        if require_root and info.st_mode & 0o022:
            raise ValueError(
                "Directory modificabile da gruppo/altri: "
                + str(current)
            )

    return True
