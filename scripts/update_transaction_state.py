#!/usr/bin/env python3
"""Registro persistente delle transazioni di aggiornamento."""

import json
import os
from pathlib import Path

ACTIVE_STATES = {
    "preparing",
    "backup",
    "stopping",
    "installing",
    "starting",
    "rolling_back",
}

FINAL_STATES = {
    "completed",
    "rolled_back",
}

VALID_STATES = ACTIVE_STATES | FINAL_STATES


def write_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if state["status"] not in VALID_STATES:
        raise ValueError("Stato transazione non valido")

    temporary = path.with_name(path.name + ".tmp")

    with temporary.open("w") as handle:
        json.dump(state, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temporary, path)

    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def read_state(path):
    path = Path(path)

    with path.open() as handle:
        state = json.load(handle)

    if not isinstance(state, dict):
        raise ValueError("Journal non valido")

    if state.get("status") not in VALID_STATES:
        raise ValueError("Stato journal non valido")

    return state


def pending_transactions(backups):
    backups = Path(backups)

    if not backups.exists():
        return []

    pending = []

    for directory in sorted(backups.iterdir()):
        if not directory.is_dir():
            continue

        journal = directory / "state.json"

        if not journal.exists():
            continue

        state = read_state(journal)

        if state["status"] in ACTIVE_STATES:
            pending.append({
                "directory": str(directory),
                "status": state["status"],
            })

    return pending
