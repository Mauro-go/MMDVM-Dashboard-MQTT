#!/usr/bin/env python3
"""Piano verificabile delle rinomine di aggiornamento.

Modulo sperimentale. Non esegue rinomine né rollback.
"""

import json
import os
import re
import tempfile
from pathlib import Path

COMPONENTS = ("backend", "frontend", "admin", "VERSION")
TXID_RE = re.compile(r"^[0-9a-f]{32}$")
STATES = ("planned", "prepared", "old_moved", "new_installed", "done")


def create_rename_plan(transaction_id):
    if not TXID_RE.fullmatch(transaction_id):
        raise ValueError("Identificativo transazione non valido")

    return {
        "transaction_id": transaction_id,
        "operations": {
            component: {
                "state": "planned",
                "target": component,
                "prepared": f".update-new-{transaction_id}-{component}",
                "previous": f".update-old-{transaction_id}-{component}",
            }
            for component in COMPONENTS
        },
    }


def validate_rename_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("Piano non valido")

    txid = plan.get("transaction_id")
    expected = create_rename_plan(txid)

    operations = plan.get("operations")

    if not isinstance(operations, dict):
        raise ValueError("Operazioni non valide")

    if set(operations) != set(COMPONENTS):
        raise ValueError("Componenti mancanti o sconosciuti")

    for component in COMPONENTS:
        operation = operations[component]
        if not isinstance(operation, dict):
            raise ValueError("Operazione non valida")

        template = expected["operations"][component]

        if set(operation) != set(template):
            raise ValueError("Campi operazione non validi")

        for field in ("target", "prepared", "previous"):
            if operation[field] != template[field]:
                raise ValueError("Percorso operazione non valido")

        if operation["state"] not in STATES:
            raise ValueError("Stato operazione non valido")

    return True


def save_rename_plan(path, plan):
    """Salva atomicamente il piano, senza seguire link sul file finale."""
    validate_rename_plan(plan)

    path = Path(path)
    parent = path.parent

    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("Directory piano non valida")

    if path.is_symlink():
        raise ValueError("Piano simbolico non consentito")

    fd, temporary = tempfile.mkstemp(
        prefix=".rename-plan-",
        dir=parent,
    )

    try:
        os.fchmod(fd, 0o600)

        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(plan, stream, indent=2, sort_keys=True)
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
        if os.path.lexists(temporary):
            os.unlink(temporary)


def load_rename_plan(path):
    path = Path(path)

    if path.is_symlink():
        raise ValueError("Piano simbolico non consentito")

    stat = path.stat()

    if not path.is_file() or stat.st_mode & 0o077:
        raise ValueError("Permessi piano non validi")

    with path.open("r", encoding="utf-8") as stream:
        plan = json.load(stream)

    validate_rename_plan(plan)
    return plan


def inspect_rename_plan(application, plan):
    """Confronta il piano con il filesystem, senza modificarlo."""
    validate_rename_plan(plan)

    application = Path(application)

    if application.is_symlink() or not application.is_dir():
        raise ValueError("Applicazione non valida")

    result = {}

    for component, operation in plan["operations"].items():
        paths = {
            "target": application / operation["target"],
            "prepared": application / operation["prepared"],
            "previous": application / operation["previous"],
        }

        result[component] = {
            "state": operation["state"],
            "paths": {
                name: {
                    "exists": path.exists() or path.is_symlink(),
                    "symlink": path.is_symlink(),
                }
                for name, path in paths.items()
            },
        }

    return result
