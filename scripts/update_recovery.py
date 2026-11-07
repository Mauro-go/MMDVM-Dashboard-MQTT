#!/usr/bin/env python3
"""Controlli preliminari per il recupero degli aggiornamenti."""

from pathlib import Path

from update_backup import (
    COMPONENTS,
    load_backup_manifest,
    verify_backup,
    verify_backup_directory,
)
from update_journal import load_journal


RECOVERABLE_STATES = {
    "prepared",
    "stopped",
    "installing",
    "installed",
    "checking",
    "rolling_back",
}


def inspect_recovery(journal_path, backup_path):
    """Analizza un aggiornamento interrotto senza modificare nulla."""
    journal = load_journal(journal_path)

    if journal["state"] not in RECOVERABLE_STATES:
        return {
            "recovery_required": False,
            "state": journal["state"],
            "pending_component": journal.get("pending_component"),
        }

    backup_path = Path(backup_path)

    if backup_path.is_symlink() or not backup_path.is_dir():
        raise RuntimeError("Directory backup non valida")

    verify_backup_directory(backup_path)

    manifest = load_backup_manifest(backup_path.parent / "manifest.json")

    verify_backup(backup_path, manifest)

    for component in COMPONENTS:
        if not (backup_path / component).exists():
            raise RuntimeError(
                "Componente backup mancante: " + component
            )

    return {
        "recovery_required": True,
        "state": journal["state"],
        "pending_component": journal.get("pending_component"),
        "backup_verified": True,
    }


def ensure_update_allowed(journal_path):
    """Impedisce nuovi aggiornamenti con transazioni irrisolte."""
    journal_path = Path(journal_path)

    if not journal_path.exists() and not journal_path.is_symlink():
        return True

    try:
        journal = load_journal(journal_path)
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(
            "Registro aggiornamento non leggibile: intervento richiesto"
        ) from exc

    if journal["state"] not in {"completed", "rolled_back"}:
        raise RuntimeError(
            "Aggiornamento precedente non concluso: "
            + journal["state"]
        )

    if journal.get("pending_component") is not None:
        raise RuntimeError(
            "Operazione precedente ancora pendente"
        )

    return True


def inspect_transaction_recovery(backup_root, transaction_id):
    """Verifica identità della transazione e integrità del backup.

    Non modifica file e non esegue alcun rollback.
    """
    from update_paths import verify_transaction_paths

    paths = verify_transaction_paths(backup_root, transaction_id)

    journal = load_journal(paths["journal"])

    if journal.get("transaction_id") != transaction_id:
        raise RuntimeError(
            "Identificativo del registro assente o non corrispondente"
        )

    if journal["state"] in {"completed", "rolled_back"}:
        if journal.get("pending_component") is not None:
            raise RuntimeError("Transazione conclusa con operazione pendente")

        return {
            "recovery_required": False,
            "transaction_id": transaction_id,
            "state": journal["state"],
        }

    result = inspect_recovery(
        paths["journal"],
        paths["backup"],
    )

    if not result.get("recovery_required"):
        raise RuntimeError("Stato recupero non riconosciuto")

    if not result.get("backup_verified"):
        raise RuntimeError("Integrità backup non confermata")

    return {
        **result,
        "transaction_id": transaction_id,
    }


def verify_recovery_destination(
    backup_root, transaction_id, installation_path
):
    """Verifica che la transazione appartenga all'installazione richiesta.

    Non modifica file e non esegue rollback.
    """
    from update_paths import verify_transaction_paths

    destination = Path(installation_path)

    if (
        not destination.is_absolute()
        or ".." in destination.parts
        or destination == Path("/")
    ):
        raise ValueError("Destinazione non autorizzata")

    paths = verify_transaction_paths(backup_root, transaction_id)
    journal = load_journal(paths["journal"])

    if journal.get("transaction_id") != transaction_id:
        raise RuntimeError("Identificativo transazione non corrispondente")

    recorded = journal.get("installation_path")

    if not recorded or recorded != str(destination):
        raise RuntimeError("Installazione diversa da quella registrata")

    if destination.is_symlink() or not destination.is_dir():
        raise RuntimeError("Directory installazione non valida")

    return True


def preflight_recovery(backup_root, transaction_id, installation_path):
    """Controlli preliminari completi, senza modificare file."""
    from update_paths import (
        verify_directory_chain,
        verify_transaction_paths,
    )

    paths = verify_transaction_paths(backup_root, transaction_id)

    verify_directory_chain(backup_root)
    verify_directory_chain(paths["transaction"])
    verify_directory_chain(paths["backup"])
    verify_directory_chain(installation_path)

    verify_recovery_destination(
        backup_root,
        transaction_id,
        installation_path,
    )

    result = inspect_transaction_recovery(
        backup_root,
        transaction_id,
    )

    if not result.get("recovery_required"):
        raise RuntimeError(
            "La transazione non richiede recupero"
        )

    if not result.get("backup_verified"):
        raise RuntimeError(
            "Backup non verificato"
        )

    return {
        "authorized_for_review": True,
        "transaction_id": transaction_id,
        "installation_path": str(installation_path),
        "backup_path": str(paths["backup"]),
        "state": result["state"],
        "pending_component": result.get("pending_component"),
    }
