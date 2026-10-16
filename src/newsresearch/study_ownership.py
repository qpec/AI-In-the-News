"""Fail-closed execution ownership for explicitly transferred Luna studies."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import Json, ResearchError


def enforce(engine: Any, session: str, operation: str, data: Json) -> None:
    if operation not in {"luna_group_validation", "luna_group_validation_continue"}:
        return
    if operation == "luna_group_validation" and data.get("phase") == "prepare":
        return
    study = data.get("study_key")
    if not isinstance(study, str) or not study:
        return  # The model adapter still enforces its mandatory study binding.
    row = engine.ledger.db.execute(
        "SELECT id FROM records WHERE kind='study_execution_ownership' AND logical_key=? "
        "ORDER BY created_event DESC LIMIT 1", (study,)).fetchone()
    if row is None:
        return
    ownership = engine.ledger.get(row[0], "study_execution_ownership")
    if (ownership.get("study_key") != study or ownership.get("status") != "imported_owner"
            or not isinstance(ownership.get("owner_workspace"), str)
            or Path(ownership["owner_workspace"]).resolve() != engine.ledger.root.resolve()
            or operation not in ownership.get("allowed_operations", [])):
        raise ResearchError("Study execution was transferred; use its exact owning workspace and authorized adapter")
    engine.ledger.append(session, "study.execution.ownership.checked", {
        "study_key": study, "ownership": row[0], "operation": operation,
        "owner_workspace": str(engine.ledger.root), "transfer_id": ownership.get("transfer_id")})
