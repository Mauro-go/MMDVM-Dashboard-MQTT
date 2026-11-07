#!/usr/bin/env python3
"""Diagnostica non distruttiva delle transazioni di aggiornamento."""

from pathlib import Path

from update_journal import load_journal
from update_recovery import inspect_recovery


def diagnose_update(journal_path, backup_path):
    """Determina se un aggiornamento può procedere o richiede recupero."""
    journal_path = Path(journal_path)

    if not journal_path.exists() and not journal_path.is_symlink():
        return {
            "status": "READY",
            "reason": "Nessuna transazione precedente",
        }

    try:
        journal = load_journal(journal_path)
    except (OSError, ValueError, TypeError) as exc:
        return {
            "status": "BLOCKED",
            "reason": f"Registro non valido: {exc}",
        }

    if journal["state"] in {"completed", "rolled_back"}:
        return {
            "status": "READY",
            "reason": "Transazione precedente conclusa",
        }

    try:
        result = inspect_recovery(journal_path, backup_path)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        return {
            "status": "BLOCKED",
            "reason": f"Backup non verificabile: {exc}",
        }

    if result.get("recovery_required") and result.get("backup_verified"):
        return {
            "status": "RECOVERY_REQUIRED",
            "reason": "Transazione incompleta con backup verificato",
            "state": result["state"],
            "pending_component": result.get("pending_component"),
        }

    return {
        "status": "BLOCKED",
        "reason": "Stato transazione non riconosciuto",
    }
