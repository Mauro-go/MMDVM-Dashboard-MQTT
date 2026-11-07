#!/usr/bin/env python3
"""Verifica non distruttiva dei residui associati alle transazioni."""

from pathlib import Path

from update_rename_plan import (
    create_rename_plan,
    inspect_rename_plan,
    load_rename_plan,
    validate_rename_plan,
)


def audit_rename_transaction(application, plan_path):
    """Confronta un piano salvato con i residui presenti sul disco."""
    application = Path(application)

    if application.is_symlink() or not application.is_dir():
        raise ValueError("Directory applicativa non valida")

    plan = load_rename_plan(plan_path)
    validate_rename_plan(plan)

    inspection = inspect_rename_plan(application, plan)

    expected = set()

    for operation in plan["operations"].values():
        expected.add(operation["prepared"])
        expected.add(operation["previous"])

    actual = {
        path.name
        for path in application.iterdir()
        if path.name.startswith((".update-new-", ".update-old-"))
    }

    unknown = sorted(actual - expected)
    recognized = sorted(actual & expected)

    symlinks = sorted(
        path.name
        for path in application.iterdir()
        if path.name in actual and path.is_symlink()
    )

    return {
        "transaction_id": plan["transaction_id"],
        "recognized": recognized,
        "unknown": unknown,
        "symlinks": symlinks,
        "inspection": inspection,
        "safe_to_start": not actual,
        "requires_review": bool(actual),
    }


def require_clean_rename_state(application, plan_path):
    """Blocca nuove operazioni se esistono residui."""
    result = audit_rename_transaction(application, plan_path)

    if result["requires_review"]:
        raise RuntimeError(
            "Residui di aggiornamento presenti: "
            + ", ".join(
                result["recognized"] + result["unknown"]
            )
        )

    return True
