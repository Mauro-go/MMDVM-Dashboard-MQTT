#!/usr/bin/env python3
"""Analisi non distruttiva delle rinomine interrotte.

Non modifica, sposta o elimina alcun file.
"""

import re
from pathlib import Path

COMPONENTS = ("backend", "frontend", "admin", "VERSION")
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
PREFIXES = (".update-old-", ".update-new-")


def inspect_rename_residues(application):
    """Identifica i residui e lo stato dei componenti."""
    application = Path(application)

    if application.is_symlink() or not application.is_dir():
        raise ValueError("Directory applicativa non valida")

    residues = []
    unknown = []

    for path in sorted(application.iterdir()):
        name = path.name

        if not name.startswith(PREFIXES):
            continue

        kind = "old" if name.startswith(".update-old-") else "new"
        token = name.removeprefix(".update-" + kind + "-")

        record = {
            "name": name,
            "kind": kind,
            "token": token,
            "valid_token": bool(TOKEN_RE.fullmatch(token)),
            "is_directory": path.is_dir(),
            "is_file": path.is_file(),
            "is_symlink": path.is_symlink(),
        }

        residues.append(record)

        if not record["valid_token"] or record["is_symlink"]:
            unknown.append(name)

    components = {}

    for component in COMPONENTS:
        path = application / component

        components[component] = {
            "exists": path.exists(),
            "is_symlink": path.is_symlink(),
            "is_directory": path.is_dir(),
            "is_file": path.is_file(),
        }

    return {
        "clean": not residues,
        "residues": residues,
        "unknown": unknown,
        "components": components,
        "requires_manual_review": bool(residues),
    }
