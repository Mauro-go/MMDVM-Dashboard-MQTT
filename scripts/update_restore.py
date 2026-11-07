#!/usr/bin/env python3
"""Recupero sperimentale di transazioni interrotte.

ATTENZIONE: non utilizzare su installazioni di produzione.
Non gestisce systemd, blackout durante il ripristino o
modifiche concorrenti alla directory applicativa.
"""

from pathlib import Path

from update_backup import (
    load_backup_manifest,
    restore_application,
    verify_backup,
)
from update_journal import load_journal, save_journal
from update_lock import update_lock
from update_paths import transaction_paths
from update_recovery import preflight_recovery

RECOVERABLE = {
    "prepared",
    "stopped",
    "installing",
    "installed",
    "checking",
    "rolling_back",
}


def recover_simulated_transaction(
    backup_root,
    transaction_id,
    application,
):
    """Ripristina una transazione di prova, previa verifica."""
    backup_root = Path(backup_root).resolve(strict=True)
    application = Path(application).resolve(strict=True)

    with update_lock(backup_root / "update.lock"):
        paths = transaction_paths(backup_root, transaction_id)
        journal = load_journal(paths["journal"])

        if journal["state"] not in RECOVERABLE:
            raise RuntimeError(
                "Transazione non recuperabile: " + journal["state"]
            )

        # Preflight obbligatorio prima di qualsiasi modifica.
        result = preflight_recovery(
            backup_root, transaction_id, application
        )

        if not result["authorized_for_review"]:
            raise RuntimeError("Recupero non autorizzato")

        manifest = load_backup_manifest(paths["manifest"])
        verify_backup(paths["backup"], manifest)

        journal["state"] = "rolling_back"
        save_journal(paths["journal"], journal)

        restore_application(
            paths["backup"],
            application,
            manifest,
        )

        journal["state"] = "rolled_back"
        journal["pending_component"] = None
        save_journal(paths["journal"], journal)

        return {
            "status": "rolled_back",
            "transaction_id": transaction_id,
        }


if __name__ == "__main__":
    print("Modulo sperimentale: utilizzare i test dedicati.")
