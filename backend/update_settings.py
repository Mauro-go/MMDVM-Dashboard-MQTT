#!/usr/bin/env python3
"""Preferenze aggiornamenti Dashboard.

La modalità automatica è solo una preferenza.
Non abilita l'esecuzione degli aggiornamenti.
"""

import json
import os
import tempfile
from pathlib import Path

from node_paths import data_file

SETTINGS = data_file("update-settings.json")
DEFAULT_SETTINGS = {"mode": "manual"}


def public():
    return read_settings(SETTINGS)


def save(mode):
    return save_settings(SETTINGS, mode)


def read_settings(path):
    path = Path(path)

    if not path.exists():
        return DEFAULT_SETTINGS.copy()

    if path.is_symlink() or not path.is_file():
        raise ValueError("File impostazioni non valido")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Formato impostazioni non valido")

    mode = data.get("mode")

    if mode not in ("manual", "automatic"):
        raise ValueError("Modalità aggiornamento non valida")

    return {"mode": mode}


def save_settings(path, mode):
    if mode not in ("manual", "automatic"):
        raise ValueError("Modalità aggiornamento non valida")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_symlink():
        raise ValueError("Collegamento simbolico non consentito")

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".update-settings-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump({"mode": mode}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(temporary, path)
        temporary = None

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    return {"mode": mode}
