"""Full cybercrime partition after the user's explicit include-extension correction."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import run_screening as original
import audit_article_scope_metadata
from audit_article_scope_metadata import read_partition
from newsresearch.common import AuditError, Config, utc
from newsresearch.runtime import audited_handler

METHOD = "luna-decisions-cybercrime-nl-preparation-continuation-20261023-v2"
OWNER = original.base.pilot.BASE / "luna-decisions-cybercrime-nl-20261023-v2"
PRIOR_OWNER = original.DEFAULT_OWNER


def implementation():
    result = original.implementation()
    for path in (Path(__file__), Path(audit_article_scope_metadata.__file__),
                 original.ROOT / "src/newsresearch/legacy.py"):
        result[str(path.relative_to(original.ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def prior_state(path):
    """Metadata-only proof that the interrupted preparation made no attempts."""
    source = original.base.pilot.Source(path)
    try:
        if not (source.owner / "STOP").is_file():
            raise AuditError("cyber_v1_partial_owner_must_remain_stopped")
        preparation = source.one("cyber_screen_preparation")
        protocols = [p for p in source.rows("protocol") if p["_record_id"] == preparation["versions"]["protocol"]]
        if len(protocols) != 1 or protocols[0]["content"]["implementation"] != original.implementation():
            raise AuditError("cyber_v1_registered_implementation_changed")
        count = source.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
        launches = source.rows("cyber_screen_launch")
        decisions = source.rows("cyber_screen_decision")
        if count or launches or decisions:
            raise AuditError("cyber_v1_zero_model_attempt_premise_changed")
        return {"owner": str(source.owner), "head": source.head(), "preparation": preparation["_record_id"],
                "original_protocol": protocols[0]["_record_id"],
                "model_attempts": count, "model_launches": len(launches), "stored_decisions": len(decisions),
                "audited_model_cost_nanousd": 0, "unknown_reservations_nanousd": 0, "stop_preserved": True}
    finally:
        source.close()


class Study(original.Study):
    @audited_handler
    def _status(self, session, context, data):
        if data["action"] == "prepare":
            self.absent("cyber_preparation_continuation")
            protocol = self._version(session, context, {"kind": "protocol", "key": METHOD,
                "content": {"method": METHOD, "implementation": implementation(),
                    "procedure": "Confirm the full explicit cybercrime partition, including its older extension, against current registry/manifest bytes. Preserve the interrupted v1 preparation and STOP. Verify it recorded zero model launches, attempts, responses and liabilities. Start a fresh preparation owner with the unchanged reviewed full-frame runner and exact questions. This continues the same USD20 authorization; it does not create another allowance or restart an old article controller.",
                    "scope_correction": "Wait include the extension",
                    "final_scope": "All eight bundles in corpora/cybercrime/manifest.json, calendar 2020 through 2026-10-15; no incident-reports.",
                    "previous_subset_choice_revoked": True, "total_budget_nanousd": original.CAP,
                    "provider_retries": 0}})["id"]
            previous = prior_state(data["prior_owner"])
            source = original.base.pilot.Source(data["parent"])
            try:
                note = source.one("note")
                bound = note["content"]["binding"]["partition"]
                current = read_partition(Path(bound["resolved_root"]), "cybercrime")
                if current != bound:
                    raise AuditError("cyber_current_partition_differs_from_frozen_source")
                partition = {"manifest_sha256": current["manifest_sha256"],
                             "registry_sha256": current["registry_sha256"],
                             "bundles": len(current["manifest"]["bundles"]),
                             "summary": current["manifest"]["summary"], "exact_current_binding_match": True}
            finally:
                source.close()
            self.ledger.record(session, "cyber_preparation_continuation", METHOD,
                {"protocol": protocol, "implementation": implementation(), "previous": previous,
                 "partition": partition, "total_budget_nanousd": original.CAP, "at": utc()})
        else:
            continuation = self.one("cyber_preparation_continuation")
            if continuation["implementation"] != implementation():
                raise AuditError("cyber_v2_implementation_changed")
            if prior_state(continuation["previous"]["owner"]) != continuation["previous"]:
                raise AuditError("cyber_v1_preserved_state_changed")
        return super()._status(session, context, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "operational", "approve-operational", "run", "report", "status"])
    parser.add_argument("--workspace", type=Path, default=OWNER)
    parser.add_argument("--parent", type=Path, default=original.DEFAULT_PARENT)
    parser.add_argument("--sealed-owner", type=Path, default=original.DEFAULT_SEALED_OWNER)
    parser.add_argument("--prior-owner", type=Path, default=PRIOR_OWNER)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action not in {"run", "operational"}))
    try:
        print(json.dumps(study.execute("status", {"action": args.action, "parent": str(args.parent),
            "sealed_owner": str(args.sealed_owner), "prior_owner": str(args.prior_owner),
            "allow_paid_execution": args.allow_paid_execution},
            objective="Screen the full cybercrime dataset group including its extension under the same USD20 authorization",
            actor="codex:cybercrime-nl-screening-v2"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
