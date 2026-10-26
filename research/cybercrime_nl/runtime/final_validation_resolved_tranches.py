"""Explicit prospective bridge from resolved initial authority to later epochs.

The reviewed LaterValidationRun remains an unchanged subproducer, including its
module-global dispatcher. This parent adds a separately registered authority and
an audited per-operation receipt, checked before each prepare/intent boundary.
It opens no source owner: complete retained evidence is replayed each operation.
No initial resource window, logical identity, liability or unknown is reset.

Operator route: use this module with --owner, --source-owner and --input pointing
to protected exact JSON. First action is register (prepared_record plus
resolved_initial_authority); subsequent action fields are the old later API.
Registration itself makes no account request and grants no quota capacity.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import final_validation_resolved_run as resolved
import final_validation_run_tranches as later
from newsresearch.common import AuditError, canonical, digest, require_active, require_no_credentials
from newsresearch.runtime import Research, audited_handler

initial, kernel, original = later.initial, later.kernel, later.original
METHOD = "final-validation-resolved-later-account-run-v1"
INTENT = "cyber_final_validation_resolved_later_intent"
AUTHORITY = "cyber_final_validation_resolved_later_authority"
OPERATION = "cyber_final_validation_resolved_later_operation"
POLICY = {"resolved_initial_authority_required": True, "unchanged_later_subproducer": True,
    "prospective_operation_binding": True, "retrospective_later_adoption": False,
    "source_owner_reads": 0, "retained_protected_artifacts_reverified": True,
    "initial_window_renewed": False, "new_seed_draws": 0, "remaining_history_gaps_preserved": True,
    "unknown_outcomes_retried": False, "paid_api_fallback": False, "account_dollar_cost": None}
FIELDS = {
    "register": {"action", "prepared_record", "resolved_initial_authority"},
    "prepare-next": {"action", "prepared_record", "primary_limit", "quota_receipt", "resource_policy"},
    "admit": {"action", "prepared_record", "producer_record", "quota_receipt", "resource_policy"},
    "run": {"action", "prepared_record", "producer_record", "epoch_record", "quota_receipt"},
    "resume": {"action", "prepared_record", "producer_record", "epoch_record", "quota_receipt"},
    "status": {"action", "prepared_record"},
    "fixed-look": {"action", "prepared_record", "look"},
}


def require(value, reason):
    if not value:
        raise AuditError("resolved_later_" + reason)


def implementation():
    path = Path(__file__)
    return {**resolved.implementation(), **later.implementation(),
        path.relative_to(initial.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def later_kinds():
    return (later.INTENT, later.PRODUCER, later.EPOCH, later.REPORT, kernel.TRANCHE,
        kernel.ADMISSION, kernel.INTENT, kernel.RESULT, kernel.SLOT, kernel.HALT, kernel.LOOK)


class ResolvedLaterValidationRun(later.LaterValidationRun):
    """New method; old producer and dispatch records retain their exact methods."""

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and data.get("action") in FIELDS
            and set(data) == FIELDS[data["action"]], "entry_shape")
        for name in ("prepared_record", "resolved_initial_authority", "producer_record", "epoch_record"):
            if name in data:
                initial.sha(data[name])
        require_no_credentials(data)
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _selection(self, selected):
        require(set(selected) == {"prepared_record", "resolved_initial_authority"}, "selection")
        require(self._one(resolved.AUTHORITY)["id"] == selected["resolved_initial_authority"]
            and self._one(original.PREPARED)["id"] == selected["prepared_record"], "initial_authority_selection")
        return deepcopy(selected)

    def _intent(self, selected):
        return {"method": METHOD, "selection": self._selection(selected), "implementation": implementation(),
            "policy": POLICY, "subproducer_method": later.METHOD,
            "subproducer_implementation": later.implementation(), "actions": {k: sorted(v) for k, v in FIELDS.items()}}

    def _protocol(self, identifier, intent, desired, *, authority=None):
        rows = list(self.ledger.db.execute("SELECT id,created_event FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        require(len(rows) == 1 and rows[0]["id"] == identifier, "authority_protocol")
        value = self.ledger.get(identifier, "protocol")
        require(later.same(value["content"], {"method": METHOD, "intent_record": intent["id"], "binding": desired})
            and value["reason"] is None and value["branch"] == "main"
            and intent["created_event"] < rows[0]["created_event"], "authority_protocol")
        if authority is not None:
            require(rows[0]["created_event"] < authority["created_event"], "authority_protocol")

    def _authority(self):
        intent, row = self._one(INTENT), self._one(AUTHORITY)
        desired = self._intent(intent["payload"]["selection"])
        require(later.same(intent["payload"], desired), "intent_changed")
        value = row["payload"]
        require(set(value) == {"method", "intent_record", "intent_sha256", "protocol_record", "proof", "implementation", "policy"}
            and value["method"] == METHOD and value["intent_record"] == intent["id"]
            and value["intent_sha256"] == digest(desired) and later.same(value["implementation"], implementation())
            and later.same(value["policy"], POLICY), "authority_binding")
        for entry, key in ((intent, METHOD), (row, intent["id"])):
            require(self.ledger.db.execute("SELECT logical_key FROM records WHERE id=?", (entry["id"],)).fetchone()[0] == key,
                "authority_logical_key")
        self._protocol(value["protocol_record"], intent, desired, authority=row)
        require(self._sequence(desired["selection"]["resolved_initial_authority"])
            < self._sequence(desired["selection"]["prepared_record"]) < intent["created_event"], "initial_chronology")
        return row

    def _proof(self, loaded):
        value, manifest, runtime, verified, _ = loaded
        source = self._one(resolved.AUTHORITY)
        return {"resolved_initial_authority": source["id"], "resolved_initial_payload_sha256": digest(source["payload"]),
            "resolved_initial_proof": source["payload"]["proof"], "prepared_record": self._one(original.PREPARED)["id"],
            "prepared_payload_sha256": digest(value), "manifest_record": value["manifest_record"],
            "manifest_sha256": manifest["manifest_sha256"], "scope_sha256": manifest["scope_sha256"],
            "initial_resources_sha256": digest(manifest["resources"]), "series_record": value["series_record"],
            "series_payload_sha256": digest(self.ledger.get(value["series_record"], kernel.SERIES)),
            "fixed_slot_artifact": value["fixed_slot_artifact"], "runtime_profile_sha256": digest(runtime["cli_profile"]),
            "effective_projection_artifact": verified[4]["effective_projection_artifact"]}

    def _initial_attempts(self, loaded):
        """Only exact initial identities can predate this new later authority.

        Missing completion stays unresolved; this check never settles billing or
        converts an orphan into a result. The inherited cumulative census blocks it.
        """
        value, manifest, runtime, *_ = loaded
        tasks = {t["logical_task_id"]: t for t in manifest["tasks"]}
        intended = {}
        for row in self.ledger.db.execute("SELECT seq,kind,payload FROM events WHERE kind LIKE 'model.attempt.%' ORDER BY seq"):
            payload = json.loads(row["payload"])
            if row["kind"] == "model.attempt.intended":
                task = tasks.get(payload.get("logical_task_id"))
                require(task is not None and task["disposition"] == "fresh"
                    and payload.get("manifest") == payload.get("batch") == value["manifest_record"]
                    and payload.get("validation_scope") == manifest["scope_sha256"]
                    and payload.get("task_key") == task["logical_task_id"] and payload.get("task_sha256") == digest(task)
                    and payload.get("packet") == digest(task["packet"])
                    and payload.get("request") == digest(task["packet"]["request"])
                    and later.same(payload.get("reservation_tokens"), task["reservation_tokens"])
                    and payload.get("role") == task["role"] and later.same(payload.get("pair_rank"), task["pair_rank"])
                    and payload.get("number") == 1 and payload.get("attempt") not in intended,
                    "foreign_or_unbound_initial_attempt")
                later.dispatch_binding(task["packet"], self.ledger.artifacts.read(payload["dispatch"]), runtime["cli_profile"], self.ledger.root)
                intended[payload["attempt"]] = payload
            else:
                require(row["kind"] in {"model.attempt.completed", "model.attempt.resolved"}
                    and payload.get("attempt") in intended, "foreign_initial_attempt_state")
        require(set(self.ledger.unresolved) <= set(intended), "foreign_unresolved_attempt")
        return digest(list(intended.values()))

    def _register(self, session, context, data):
        selected = self._selection({k: data[k] for k in ("prepared_record", "resolved_initial_authority")})
        desired = self._intent(selected)
        intent, done = self._one(INTENT, optional=True), self._one(AUTHORITY, optional=True)
        require(intent is None or later.same(intent["payload"], desired), "registration_changed_requires_amendment")
        require(done is None or intent is not None, "authority_without_intent")
        if done:
            self._authority()
            loaded = self._load_run(session, context, selected["prepared_record"])
            return {"authority_record": done["id"], "reused": True, "initial_manifest_record": loaded[0]["manifest_record"]}
        require(not any(self._rows(kind) for kind in later_kinds()) and not self._rows(OPERATION), "prior_later_evidence_forbids_adoption")
        identity = intent["id"] if intent else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD,
            {"method": METHOD, "intent_record": identity, "binding": desired})
        self._protocol(protocol, self._one(INTENT), desired)
        self._bridge_registration = (session, selected)
        try:
            loaded = original.FinalValidationRun._load_run(self, session, context, selected["prepared_record"])
            self._initial_attempts(loaded)
            proof = self._proof(loaded)
        finally:
            self._bridge_registration = None
        require(later.same(desired, self._intent(selected)), "implementation_changed")
        result = {"method": METHOD, "intent_record": identity, "intent_sha256": digest(desired), "protocol_record": protocol,
            "proof": proof, "implementation": desired["implementation"], "policy": POLICY}
        identifier = self.ledger.record(session, AUTHORITY, identity, result)
        self._authority()
        return {"authority_record": identifier, "reused": False, "initial_manifest_record": loaded[0]["manifest_record"]}

    def _frame_and_closure(self, session, context, selected):
        require_active(self, session)
        pending = getattr(self, "_bridge_registration", None)
        chosen = pending[1] if pending and pending[0] == session else self._one(INTENT)["payload"]["selection"]
        require(self._one(resolved.AUTHORITY)["id"] == chosen["resolved_initial_authority"], "resolved_authority_changed")
        if not pending:
            self._authority()
        return resolved.verified_frame_and_closure(self, session, context, selected)

    def _load_run(self, session, context, identifier):
        authority = self._authority()
        require(identifier == authority["payload"]["proof"]["prepared_record"], "prepared_changed")
        loaded = original.FinalValidationRun._load_run(self, session, context, identifier)
        require(later.same(self._proof(loaded), authority["payload"]["proof"]), "initial_proof_changed")
        self._bridge_loaded = (session, loaded)
        # Every old subproducer record must have been made inside this parent's
        # prospective operation, including provider-free local recovery records.
        for kind in later_kinds():
            for row in self._rows(kind):
                self._operation_for(row["created_event"], expected_prepared=identifier)
        return loaded

    def _operation_for(self, sequence, *, expected_prepared):
        authority = self._authority()
        event = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (sequence,)).fetchone()
        require(event is not None and authority["created_event"] < sequence, "subproducer_chronology")
        matches = [row for row in self._rows(OPERATION) if self.ledger.db.execute(
            "SELECT session_id FROM events WHERE seq=?", (row["created_event"],)).fetchone()[0] == event[0]]
        require(len(matches) == 1, "operation_receipt_required")
        row, value = matches[0], matches[0]["payload"]
        require(authority["created_event"] < row["created_event"] <= sequence
            and set(value) == {"method", "authority_record", "authority_payload_sha256", "implementation_sha256", "inputs"}
            and value["method"] == METHOD and value["authority_record"] == authority["id"]
            and value["authority_payload_sha256"] == digest(authority["payload"])
            and value["implementation_sha256"] == digest(implementation())
            and value["inputs"].get("prepared_record") == expected_prepared, "operation_binding")
        data = value["inputs"]
        require(data.get("action") in FIELDS and data["action"] != "register"
            and set(data) == FIELDS[data["action"]], "operation_shape")
        events = list(self.ledger.db.execute("SELECT seq,payload FROM events WHERE session_id=? AND kind='operation.intended'", (event[0],)))
        require(len(events) == 1 and events[0][0] < row["created_event"], "operation_framework_chronology")
        intended = json.loads(events[0][1])
        require(later.same(intended, {"operation": "status", "input": digest({"method": METHOD, **data})})
            and later.same(self.ledger.artifacts.read(intended["input"]), {"method": METHOD, **data}), "operation_framework_input")
        return row

    def _dispatch_proofs(self, loaded, *, before=None):
        proofs = []
        for row in self.ledger.db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
            if before is not None and row["seq"] >= before:
                continue
            value = json.loads(row["payload"])
            if value.get("manifest") == loaded[0]["manifest_record"]:
                continue
            operation = self._operation_for(row["seq"], expected_prepared=self._one(original.PREPARED)["id"])
            data = operation["payload"]["inputs"]
            require(data["action"] in {"run", "resume"} and data["producer_record"] == value.get("producer_record")
                and data["epoch_record"] == value.get("epoch_record"), "dispatch_operation_scope")
            quota = self.ledger.get(value["fresh_quota_record"], original.admission.QUOTA)
            require(later.same(self.ledger.artifacts.read(quota["receipt_artifact"]), data["quota_receipt"]), "dispatch_quota_binding")
            proofs.append({"attempt": value["attempt"], "intent_sha256": digest(value), "operation_record": operation["id"]})
        return proofs

    def _census(self, session, loaded, *, producers=None):
        state = super()._census(session, loaded, producers=producers)
        authority = self._authority()
        return {**state, "resolved_later_method": METHOD, "resolved_later_authority": authority["id"],
            "resolved_later_implementation_sha256": digest(implementation()),
            "resolved_later_dispatches": self._dispatch_proofs(loaded)}

    def _prior_state(self, session, reference, sequence, loaded, manifest_ids):
        state = super()._prior_state(session, reference, sequence, loaded, manifest_ids)
        require(state.get("resolved_later_method") == METHOD and state.get("resolved_later_authority") == self._authority()["id"]
            and state.get("resolved_later_implementation_sha256") == digest(implementation())
            and later.same(state.get("resolved_later_dispatches"), self._dispatch_proofs(loaded, before=sequence)), "prior_resolved_census")
        return state

    def _conditions(self, session, loaded, epoch, fresh_quota, producers):
        require_active(self, session)
        current = getattr(self, "_bridge_operation", None)
        require(current is not None and current[0] == session, "active_operation_required")
        operation = self._operation_for(self._sequence(current[1]), expected_prepared=self._one(original.PREPARED)["id"])
        data = operation["payload"]["inputs"]
        require(data["action"] in {"run", "resume"} and data["producer_record"] == epoch["producer_record"]
            and later.same(self.ledger.get(data["epoch_record"], later.EPOCH), epoch), "active_epoch_binding")
        require(getattr(self, "_bridge_loaded", (None,))[0] == session
            and later.same(self._proof(loaded), self._authority()["payload"]["proof"]), "active_initial_proof")
        require(fresh_quota["receipt_artifact"] == digest(data["quota_receipt"]), "active_fresh_quota")
        return super()._conditions(session, loaded, epoch, fresh_quota, producers)

    @audited_handler
    def _status(self, session, context, data):
        require(data["method"] == METHOD, "method")
        if data["action"] == "register":
            result = self._register(session, context, data)
            return {**result, "method": METHOD, "subproducer_method": later.METHOD, "new_model_calls": 0,
                "registration_is_quota_authority": False, "source_owner_reads": 0}
        authority = self._authority()
        inputs = {k: deepcopy(v) for k, v in data.items() if k != "method"}
        value = {"method": METHOD, "authority_record": authority["id"], "authority_payload_sha256": digest(authority["payload"]),
            "implementation_sha256": digest(implementation()), "inputs": inputs}
        operation = self.ledger.record(session, OPERATION, session, value)
        self._bridge_operation = (session, operation)
        try:
            self._operation_for(self._sequence(operation), expected_prepared=inputs["prepared_record"])
            result = later.LaterValidationRun._status(self, session, context, {**inputs, "method": later.METHOD})
            self._authority()  # no completed outer result after implementation drift
            return {**result, "method": METHOD, "subproducer_method": later.METHOD,
                "resolved_later_authority": authority["id"], "operation_record": operation}
        finally:
            self._bridge_operation = self._bridge_loaded = None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit resolved-initial to later account authority; no API route.")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--source-owner", required=True)
    parser.add_argument("--input", required=True, help="Protected exact action JSON, outside the repository")
    args = parser.parse_args(argv)
    path = Path(args.input)
    require(path.is_absolute() and path.is_file() and not path.is_symlink()
        and not path.resolve().is_relative_to(initial.ROOT.resolve()), "protected_input_required")
    raw = path.read_bytes()
    require(0 < len(raw) <= 1024 * 1024, "input_size")
    engine = ResolvedLaterValidationRun(args.owner, source_owner=args.source_owner)
    try:
        result = engine.execute("status", json.loads(raw), objective="Continue exact registered resolved validation tranches.",
            actor="codex-resolved-later-validation")
    finally:
        engine.close()
    print(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
