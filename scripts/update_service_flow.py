#!/usr/bin/env python3
"""Flusso sperimentale con rollback post-installazione.

Solo copie temporanee. Non esegue comandi systemd.
"""

from pathlib import Path

from update_orchestration import execute_simulated_plan
from update_deployment import get_profile
from update_backup import (
    load_backup_manifest,
    restore_application,
    verify_backup,
)
from update_journal import load_journal, save_journal
from update_lock import update_lock
from update_paths import transaction_paths


def rollback_completed_update(backup_root, transaction_id, application):
    """Ripristina una transazione completata, dopo verifica."""
    backup_root = Path(backup_root).resolve(strict=True)
    application = Path(application).resolve(strict=True)

    with update_lock(backup_root / "update.lock"):
        paths = transaction_paths(backup_root, transaction_id)
        journal = load_journal(paths["journal"])

        if journal["state"] != "completed":
            raise RuntimeError("Transazione non completata")

        if journal.get("transaction_id") != transaction_id:
            raise RuntimeError("Identificativo transazione non valido")

        if journal.get("installation_path") != str(application):
            raise RuntimeError("Destinazione rollback non corrispondente")

        if journal.get("pending_component") is not None:
            raise RuntimeError("Transazione con operazione pendente")

        from update_paths import (
            verify_directory_chain,
            verify_transaction_paths,
        )

        verify_transaction_paths(backup_root, transaction_id)
        verify_directory_chain(backup_root)
        verify_directory_chain(paths["transaction"])
        verify_directory_chain(paths["backup"])
        verify_directory_chain(application)

        manifest = load_backup_manifest(paths["manifest"])
        verify_backup(paths["backup"], manifest)

        journal["state"] = "rolling_back"
        save_journal(paths["journal"], journal)

        restore_application(paths["backup"], application, manifest)

        journal["state"] = "rolled_back"
        journal["pending_component"] = None
        save_journal(paths["journal"], journal)

        return {
            "status": "rolled_back",
            "transaction_id": transaction_id,
        }


def execute_service_flow(
    mode, application, release, backup_root,
    *, stop, start, health, fail_after=None
):
    """Esegue aggiornamento e rollback su una copia di prova."""
    get_profile(mode)

    if not all(callable(fn) for fn in (stop, start, health)):
        raise ValueError("Gestori servizi non validi")

    # Tutti i percorsi devono appartenere all'area temporanea.
    import tempfile
    temporary_root = Path(tempfile.gettempdir()).resolve()

    for path in (application, release, backup_root):
        resolved = Path(path).resolve(strict=True)
        if temporary_root not in resolved.parents:
            raise ValueError("Percorso fuori dall'ambiente temporaneo")

    stopped = False
    updated = False
    result = None

    try:
        if not health():
            raise RuntimeError("Controllo iniziale fallito")

        stop()
        stopped = True

        result = execute_simulated_plan(
            mode, application, release, backup_root,
            fail_after=fail_after,
        )
        updated = True

        start()
        stopped = False

        if not health():
            raise RuntimeError("Controllo finale fallito")

        return {
            **result,
            "health": "ok",
            "services": "running",
        }

    except Exception as original_error:
        errors = []

        if updated:
            try:
                stop()
                stopped = True

                rollback_completed_update(
                    backup_root,
                    result["transaction_id"],
                    application,
                )

                start()
                stopped = False

                if not health():
                    errors.append(
                        "Controllo salute dopo rollback fallito"
                    )

            except Exception as exc:
                errors.append("Rollback fallito: " + str(exc))

        if stopped:
            try:
                start()
                stopped = False
            except Exception as exc:
                errors.append("Riavvio servizi fallito: " + str(exc))

        if errors:
            raise RuntimeError(
                str(original_error) + "; " + "; ".join(errors)
            ) from original_error

        raise RuntimeError(
            "Aggiornamento annullato e versione precedente ripristinata"
            if updated else str(original_error)
        ) from original_error
