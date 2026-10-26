"""One fixed candidate, positive metadata locators, no history or quiescence claim.

The original observer is retained unchanged. Its unresolved matches do not
override the independent exclusive ledger lock, and are never called safe.
Completed local scope derivation is reused; historical bundles are not reread.
"""
from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

import final_validation_retained_scope as scope
from newsresearch.common import AuditError, Config, canonical, digest, require_active, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

METHOD = "final-validation-single-candidate-positive-locator-v1"
INTENT = "final_validation_exact_locator_probe_intent"
CUTOFF = "final_validation_exact_locator_probe_cutoff"
RESULT = "final_validation_exact_locator_probe"
CANDIDATE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/research")
ROOT = scope.ROOT
SOURCE = scope.retained.discovery.source_api
STUDY = scope.retained.discovery.study
POLICY = {"candidate_count": 1, "nested_artifacts_opened": 0, "source_mutations": 0,
    "new_model_calls": 0, "new_seed_draws": 0, "frame_or_sample_recomputed": False,
    "completed_scope_derivation_reused": True, "scope_bundles_recomputed": False,
    "global_quiescence_verified": False, "loaded_process_code_verified": False,
    "native_origin_verified": False, "absence_or_exclusion_proved": False,
    "history_complete": False, "gaps_removed": False, "dispatch_authorized": False,
    "fresh_pair_eligibility": "unknown", "full_source_preflight_performed": False}
DEFAULT_WRITERS = {"judge_cross_window_event_review.py", "run_event_pairs.py",
    "prepare_cross_window_event_review.py", "prepare_event_pairs.py"}
LINK_FIELDS = {"event_group_evidence_judgment_result": ("manifest", "prepared_result", "original_study_key"),
    "event_group_evidence_judging_manifest": ("prepared_result",),
    "event_pair_experiment": ("execution_key",),
    "result_presentation": ("results", "content_artifact", "content_sha256")}


def require(value, code):
    if not value:
        raise AuditError("exact_locator_probe_" + code)


def implementation():
    paths = (Path(__file__), ROOT / "scripts/judge_cross_window_event_review.py",
        ROOT / "src/newsresearch/common.py", ROOT / "src/newsresearch/event_group_evidence_judging.py")
    return {**scope.implementation(), **{p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _argv(command):
    """Use the Windows parser, including quoted --workspace=value arguments."""
    require(os.name == "nt", "windows_observer_required")
    argc = ctypes.c_int()
    parser = ctypes.windll.shell32.CommandLineToArgvW
    parser.argtypes, parser.restype = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)], ctypes.POINTER(ctypes.c_wchar_p)
    pointer = parser(command, ctypes.byref(argc))
    require(bool(pointer), "command_parse")
    try:
        return [pointer[i] for i in range(argc.value)]
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes, free.restype = [ctypes.c_void_p], ctypes.c_void_p
        free(pointer)


def writer_route(command, owner):
    args = _argv(command)
    expected = str(owner).replace("\\", "/").casefold().rstrip("/")
    explicit = []
    for i, arg in enumerate(args):
        for option in ("--workspace", "--research-workspace"):
            if arg.casefold() == option:
                require(i + 1 < len(args), "workspace_argument_missing")
                explicit.append(args[i + 1])
            elif arg.casefold().startswith(option + "="):
                explicit.append(arg[len(option) + 1:])
    if any(p.replace("\\", "/").casefold().rstrip("/") == expected for p in explicit):
        return "explicit_candidate_workspace"
    native = any(Path(a.replace("\\", "/")).name.casefold() in DEFAULT_WRITERS for a in args)
    native = native or any(a == "-m" and i + 1 < len(args) and args[i + 1] in {"newsresearch", "newsresearch.cli"} for i, a in enumerate(args))
    return "native_default_workspace_writer" if native and not explicit else None


class ProbeObserver(STUDY.WindowsProcessObserver):
    def inspect(self, engine, session, owner):
        # observe() validates the complete inventory and retains its exact matches.
        captured = self._capture()
        class Captured(STUDY.WindowsProcessObserver):
            def _capture(self):
                return captured
        observation = Captured().observe(engine, session, owner)
        rows = [r for r in engine._rows("cyber_final_validation_process_observation")
            if r["payload"]["evidence_artifact"] == observation["evidence_sha256"]]
        require(len(rows) == 1, "observer_record")
        inventory_ref = rows[0]["payload"]["inventory_artifact"]
        inventory = engine.ledger.artifacts.read(inventory_ref)
        ignored = set(inventory["verified_observer_process_ids"])
        identified = []
        for row in captured:
            if row["pid"] in ignored:
                continue
            reason = writer_route(row["command_line"], owner)
            if reason:
                identified.append({"pid": row["pid"], "created_at": row["created_at"], "reason": reason,
                    "command_sha256": hashlib.sha256(row["command_line"].encode()).hexdigest()})
        return {"observation": observation, "process_inventory_artifact": inventory_ref,
            "identified_writer_routes": identified}


def select_metadata(db):
    """Only exact ID/key/native presentation fields, never arbitrary text search."""
    selected, selectors = {}, []
    rows = db.execute("SELECT * FROM records WHERE id=? OR logical_key=? OR kind IN ('result_presentation','event_pair_experiment') ORDER BY created_event",
        (scope.PAIR_RESULT, scope.PAIR_KEY))
    for raw in rows:
        row, found = dict(raw), []
        value = json.loads(row["payload"])
        if row["id"] == scope.PAIR_RESULT:
            found.append("exact_result_id")
        if row["logical_key"] == scope.PAIR_KEY or (row["kind"] == "event_pair_experiment" and value.get("execution_key") == scope.PAIR_KEY):
            found.append("exact_execution_key")
        if row["kind"] == "result_presentation" and value.get("content_artifact") == scope.PAIR_PRESENTATION:
            require(value.get("content_sha256") == scope.PAIR_PRESENTATION, "presentation_hash_contradiction")
            found.append("exact_presentation_artifact")
        if found:
            selected[row["id"]] = row
            selectors.extend({"record_id": row["id"], "selector": item} for item in found)
    saved = [dict(r) for r in db.execute("SELECT * FROM events WHERE kind='presentation.artifact.saved' ORDER BY seq")
        if json.loads(r["payload"]).get("artifact") == scope.PAIR_PRESENTATION]
    sessions = {db.execute("SELECT session_id FROM events WHERE seq=?", (r["created_event"],)).fetchone()[0] for r in selected.values()}
    sessions.update(r["session_id"] for r in saved)
    events = {r["seq"]: r for r in saved}
    for row in selected.values():
        event = dict(db.execute("SELECT * FROM events WHERE seq=?", (row["created_event"],)).fetchone())
        events[event["seq"]] = event
    references, links = [], []
    for sid in sorted(sessions):
        for raw in db.execute("SELECT * FROM events WHERE session_id=? AND kind IN ('session.started','operation.intended','operation.completed','operation.failed','session.ended') ORDER BY seq", (sid,)):
            event = dict(raw)
            events[event["seq"]] = event
            field = scope.LIFECYCLE_FIELDS.get(event["kind"])
            if field:
                reference = json.loads(event["payload"]).get(field)
                references.append({"event_hash": event["event_hash"], "session_id": sid, "field": field,
                    "artifact": reference if scope._sha(reference) else None,
                    "state": "not_materialized_by_probe" if scope._sha(reference) else "missing_or_malformed_pointer"})
    for row in selected.values():
        value = json.loads(row["payload"])
        for field in LINK_FIELDS.get(row["kind"], ()):
            if field in value:
                links.append({"record_id": row["id"], "field": field, "literal_value": value[field], "origin_verified": False})
    return {"records": list(selected.values()), "events": [events[k] for k in sorted(events)],
        "selectors": selectors, "presentation_saved_events": [r["event_hash"] for r in saved],
        "native_links": links, "uninspected_lifecycle_references": references}


class ExactLocatorProbe(scope.RetainedScope):
    def __init__(self, workspace, *, config=None):
        super().__init__(workspace, config=config or Config(offline=True))
        self.observer = ProbeObserver()

    def _progress_probe(self, value):
        target = self.ledger.root / "exact-locator-probe-progress.json"
        require(not target.is_symlink() and not target.is_junction(), "progress_link")
        temporary = self.ledger.root / ("exact-locator-probe-" + uuid.uuid4().hex + ".writing")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(canonical({"method": METHOD, "observed_at": utc(), **value}))
                stream.flush()
                os.fsync(stream.fileno())
            check_permissions(temporary)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "scope_record", "scope_artifact"}
            and data["action"] in {"probe", "status"} and scope._sha(data["scope_record"])
            and scope._sha(data["scope_artifact"]), "operation_shape")
        return Research.execute(self, operation, {"method": METHOD, **data}, objective=objective, actor=actor)

    def _raw(self, identity):
        row = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (identity,)).fetchone()
        require(row is not None, "missing_record")
        return row

    def _completed_scope(self, row, code):
        event = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (row["created_event"],)).fetchone()
        events = list(self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (event[0],)))
        parts = {kind: [r for r in events if r["kind"] == kind] for kind in
            ("session.started", "operation.intended", "operation.completed", "session.ended", "operation.failed")}
        require(not parts["operation.failed"] and all(len(parts[k]) == 1 for k in parts if k != "operation.failed"), "scope_completion_partition")
        start, intended, completed, end = [parts[k][0] for k in ("session.started", "operation.intended", "operation.completed", "session.ended")]
        require(start["seq"] < intended["seq"] < row["created_event"] < completed["seq"] < end["seq"]
            and json.loads(end["payload"]) == {"status": "completed"}, "scope_completed_order")
        identity_ref = json.loads(start["payload"])["identity"]
        runtime = self.ledger.artifacts.read(identity_ref)
        require(all(runtime["code_files"].get(p) == sha for p, sha in code.items() if p.startswith("src/") and p.endswith(".py")), "scope_runtime_identity")
        inp, out = json.loads(intended["payload"]), json.loads(completed["payload"])
        require(inp["operation"] == out["operation"] == "status", "scope_native_operation")
        data, output = self.ledger.artifacts.read(inp["input"]), self.ledger.artifacts.read(out["result"])
        require(data == {"method": scope.METHOD, "action": "derive", "inventory_record": row["payload"]["binding"]["inventory_record"]}
            and output["retained_scope_record"] == row["id"] and output["retained_scope_artifact"] == digest(row["payload"]), "scope_completed_binding")
        return {"identity_artifact": identity_ref, "input_artifact": inp["input"], "output_artifact": out["result"], "completed_event": completed["event_hash"]}

    def _authority(self, session, identity, artifact):
        self._stop_local(session)
        row = self._one(scope.RESULT)
        value = row["payload"]
        require(row["id"] == identity and digest(value) == artifact, "selected_scope")
        desired = value["binding"]
        code = scope.implementation()
        require(desired == {"method": scope.METHOD, "implementation": code, "policy": scope.POLICY,
            "catalog_artifact": code[scope.CATALOG.relative_to(ROOT).as_posix()],
            "inventory_record": desired["inventory_record"], "inventory_artifact": desired["inventory_artifact"]}
            and value["method"] == scope.METHOD and value["policy"] == scope.POLICY, "scope_implementation")
        intent = self._one(scope.INTENT)
        require(intent["id"] == value["intent_record"] and intent["payload"] == desired, "scope_intent")
        seq = self._scope_protocol(intent["id"], value["protocol_record"], desired)
        raw = self._raw(identity)
        require(raw["logical_key"] == intent["id"] and raw["supersedes"] is None and seq < row["created_event"], "scope_result_order")
        completion = self._completed_scope(row, code)
        inventory = self._one(scope.retained.RESULT)
        inv = inventory["payload"]
        inv_desired = inv["binding"]
        require(inv_desired == {"method": scope.retained.METHOD, "binding": inv_desired["binding"],
            "implementation": scope.retained.implementation(), "policy": scope.retained.POLICY}
            and inv["method"] == scope.retained.METHOD and inv["policy"] == scope.retained.POLICY
            and self._one(scope.retained.INTENT)["id"] == inv["intent_record"]
            and self.ledger.get(inv["intent_record"], scope.retained.INTENT) == inv_desired, "inventory_native_binding")
        invseq = self._protocol(inv["intent_record"], inv["protocol_record"], inv_desired)
        invraw = self._raw(inventory["id"])
        require(invraw["logical_key"] == inv["intent_record"] and invraw["supersedes"] is None
            and invseq < inventory["created_event"], "inventory_native_order")
        require(inventory["id"] == desired["inventory_record"] and digest(inv) == desired["inventory_artifact"]
            and inventory["created_event"] < intent["created_event"]
            and self._completed_inventory(inventory) == value["producer_completion"], "scope_inventory_binding")
        preserved = value["preserved_authority"]
        authority = self.ledger.artifacts.read(inv["snapshot_authority"])
        require(preserved == {"validation_head": inv["validation_head"], "original_binding": inv["binding"]["binding"],
            "input_index_digest": authority["input_index_digest"], "main_source_bindings": authority["source_bindings"],
            "declared_gap_counts": inv["declared_gap_counts"], "reconciliation_gap_counts": inv["reconciliation_gap_counts"],
            "interrupted_task_census": inv["interrupted_task_census"], "positive_preparation_scope_complete": False}, "scope_preserved_authority")
        checkpoints, bundles = self._rows(scope.OWNER), self._rows(scope.retained.BUNDLE)
        require([r["id"] for r in checkpoints] == value["owner_records"] and [r["id"] for r in bundles] == inv["bundle_records"]
            and len(checkpoints) == len(bundles), "scope_checkpoint_set")
        matches = []
        for checkpoint, bundle in zip(checkpoints, bundles):
            child, original = checkpoint["payload"], bundle["payload"]
            raw = self._raw(checkpoint["id"])
            require(child["method"] == scope.METHOD and child["intent_record"] == intent["id"]
                and child["bundle_record"] == bundle["id"] and child["bundle_artifact"] == digest(original)
                and child["derivation"]["owner_sha256"] == original["owner_sha256"]
                and child["derivation"]["source_head"] == original["source_head"]
                and raw["logical_key"] == digest([intent["id"], bundle["id"]]) and raw["supersedes"] is None
                and seq < checkpoint["created_event"] < row["created_event"], "scope_checkpoint_binding")
            matches.extend(child["derivation"]["matches"])
        catalog = self.ledger.artifacts.read(desired["catalog_artifact"])
        states = self.ledger.artifacts.read(value["root_states_artifact"])
        require(states == [{"root_id": root["id"], "matches": [m for m in matches if m["root_id"] == root["id"]], "scope_closed": False}
            for root in catalog["roots"]], "scope_root_states")
        pair = [s for s in states if s["root_id"] == "event-pair-cross-window"]
        require(len(pair) == 1 and pair[0]["matches"] == [], "pair_already_located")
        return {"scope_record": identity, "scope_artifact": artifact, "scope_completion": completion,
            "inventory_record": inventory["id"], "inventory_artifact": digest(inv),
            "root_states_artifact": value["root_states_artifact"], "preserved_authority": preserved,
            "scope_checkpoint_records": value["owner_records"]}

    def _completed_probe(self, row, desired):
        """A result followed by a failed final guard cannot be adopted on reopen."""
        creation = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (row["created_event"],)).fetchone()
        events = list(self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (creation[0],)))
        kinds = ("session.started", "operation.intended", "operation.completed", "session.ended")
        parts = [[r for r in events if r["kind"] == kind] for kind in kinds]
        require(all(len(rows) == 1 for rows in parts) and not any(r["kind"] == "operation.failed" for r in events), "probe_not_completed")
        start, intended, completed, end = [rows[0] for rows in parts]
        require(start["seq"] < intended["seq"] < row["created_event"] < completed["seq"] < end["seq"]
            and json.loads(end["payload"]) == {"status": "completed"}, "probe_completion_order")
        runtime = self.ledger.artifacts.read(json.loads(start["payload"])["identity"])
        require(all(runtime["code_files"].get(p) == sha for p, sha in desired["implementation"].items()
            if p.startswith("src/") and p.endswith(".py")), "probe_runtime_identity")
        inp, out = json.loads(intended["payload"]), json.loads(completed["payload"])
        require(inp["operation"] == out["operation"] == "status" and self.ledger.artifacts.read(inp["input"]) == {
            "method": METHOD, "action": "probe", "scope_record": desired["scope_record"], "scope_artifact": desired["scope_artifact"]}, "probe_completed_input")
        output = self.ledger.artifacts.read(out["result"])
        require(output["exact_locator_probe_record"] == row["id"] and output["exact_locator_probe_artifact"] == digest(row["payload"]), "probe_completed_output")

    def _protocol_probe(self, intent, protocol, desired):
        rows = list(self.ledger.db.execute("SELECT * FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        raw = self._raw(intent)
        require(len(rows) == 1 and rows[0]["id"] == protocol and rows[0]["supersedes"] is None
            and raw["logical_key"] == METHOD and raw["supersedes"] is None
            and raw["created_event"] < rows[0]["created_event"], "prospective_protocol")
        saved = self.ledger.get(protocol, "protocol")
        require(saved["content"] == desired and saved["reason"] is None and saved["branch"] == "main", "protocol_binding")
        return rows[0]["created_event"]

    def _observation(self, session, candidate):
        value = self.observer.inspect(self, session, candidate)
        observation = value["observation"]
        SOURCE._retained_liveness(self, observation)
        now = datetime.now(timezone.utc)
        observed = datetime.fromisoformat(observation["observed_at"])
        require(observed.tzinfo is not None and -5 <= (now - observed).total_seconds() <= 30
            and observation["source_owner"] == str(candidate) and observation["inspection_complete"] is True
            and observation["active_writers"] == observation["matching_processes"], "fresh_complete_observation")
        require(value["identified_writer_routes"] == [], "identified_writer_route")
        return value

    def _guard(self, session, source, head, code):
        self._stop_local(session)
        source._active()
        check_permissions(source.owner, root=True)
        check_permissions(source.owner / "objects")
        require(not (source.owner / "STOP").exists(), "source_stop")
        require(source.head(fresh=True) == head, "source_head_changed")
        require(implementation() == code, "implementation_changed")

    def _summary_probe(self, session, row, desired, intent, protocol, sequence):
        value, raw = row["payload"], self._raw(row["id"])
        cutoff = self._one(CUTOFF)
        cutraw = self._raw(cutoff["id"])
        require(value["method"] == METHOD and value["binding"] == desired and value["policy"] == POLICY
            and value["intent_record"] == intent and value["protocol_record"] == protocol
            and value["cutoff_record"] == cutoff["id"] and raw["logical_key"] == intent and raw["supersedes"] is None
            and cutraw["logical_key"] == intent and cutraw["supersedes"] is None
            and sequence < cutoff["created_event"] < row["created_event"]
            and cutoff["payload"] == {"intent_record": intent, "candidate": desired["candidate"], "source_head": value["source_head"]}, "result_binding")
        metadata = self.ledger.artifacts.read(value["metadata_artifact"])
        selected = self.ledger.artifacts.read(value["selected_metadata_artifact"])
        require(metadata["source_head"] == value["source_head"] and metadata["source_owner"] == desired["candidate"], "metadata_binding")
        roster = {r["record_id"]: r for r in metadata["records"]}
        events = {e["seq"]: e for e in metadata["events"]}
        for r in selected["records"]:
            require(r["id"] in roster and hashlib.sha256(r["payload"].encode()).hexdigest() == r["artifact"]
                and roster[r["id"]] == {"record_id": r["id"], "kind": r["kind"], "artifact": r["artifact"],
                    "logical_key_sha256": digest(r["logical_key"]), "created_event": r["created_event"]}, "selected_record_binding")
        for e in selected["events"]:
            require(events.get(e["seq"]) == {k: e[k] for k in ("seq", "kind", "event_hash")}
                and digest({**{k: v for k, v in e.items() if k != "event_hash"}, "payload": json.loads(e["payload"])}) == e["event_hash"], "selected_event_binding")
        for item in value["process_observations"]:
            SOURCE._retained_liveness(self, item["observation"])
            self.ledger.artifacts.read(item["process_inventory_artifact"])
            require(item["identified_writer_routes"] == [] and item["observation"]["inspection_complete"] is True, "saved_process_observation")
        summary = _counts(selected, value["process_observations"])
        require(summary == value["summary"], "summary_binding")
        self._stop_local(session)
        return {"exact_locator_probe_record": row["id"], "exact_locator_probe_artifact": digest(value), **summary, **POLICY}

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        require(self.config.offline and data["method"] == METHOD, "offline_method")
        self._stop_local(session)
        began = time.perf_counter()
        self._progress_probe({"stage": "verifying_completed_scope", "elapsed_seconds": 0, "final_result": False})
        code = implementation()
        candidate = scope.retained.discovery.canonical_path(str(CANDIDATE))
        desired = {"method": METHOD, "implementation": code, "policy": POLICY, "candidate": str(candidate),
            "scope_record": data["scope_record"], "scope_artifact": data["scope_artifact"],
            "selectors": {"result_id": scope.PAIR_RESULT, "execution_key": scope.PAIR_KEY, "presentation_artifact": scope.PAIR_PRESENTATION}}
        old, done = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        require(old is None or old["payload"] == desired, "changed_binding")
        require(done is None or old is not None, "result_without_intent")
        if old is None and data["action"] == "status":
            return {"probed": False, **POLICY}
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD, desired)
        sequence = self._protocol_probe(intent, protocol, desired)
        authority = self._authority(session, data["scope_record"], data["scope_artifact"])
        require(self._raw(data["scope_record"])["created_event"] < self._raw(intent)["created_event"], "scope_not_prospective")
        if done:
            require(done["payload"]["scope_authority"] == authority, "completed_authority_changed")
            self._completed_probe(done, desired)
            return {**self._summary_probe(session, done, desired, intent, protocol, sequence), "reused_completed": True}
        if data["action"] == "status":
            return {"probed": False, "incomplete_intent": intent, **POLICY}
        before = self._observation(session, candidate)
        require(not (candidate / "STOP").exists(), "source_stop")
        source = SOURCE.Source(self, session, candidate)
        try:
            head = source.head()
            cut = {"intent_record": intent, "candidate": str(candidate), "source_head": head}
            old_cut = self._one(CUTOFF, optional=True)
            if old_cut:
                raw = self._raw(old_cut["id"])
                require(old_cut["payload"] == cut and raw["logical_key"] == intent and raw["supersedes"] is None
                    and sequence < old_cut["created_event"], "pinned_cutoff_changed")
                cutoff = old_cut["id"]
            else:
                cutoff = self.ledger.record(session, CUTOFF, intent, cut)
            self._progress_probe({"stage": "candidate_metadata", "elapsed_seconds": round(time.perf_counter() - began, 3), "final_result": False})
            metadata = scope.retained.discovery.metadata_census(source)
            selected = select_metadata(source.db)
            # No source artifact is opened: these bytes are verified SQL projections.
            require(not source.checked, "unexpected_nested_read")
            self._guard(session, source, head, code)
            after = self._observation(session, candidate)
            self._guard(session, source, head, code)
            result = {"method": METHOD, "binding": desired, "policy": POLICY, "intent_record": intent,
                "protocol_record": protocol, "cutoff_record": cutoff, "scope_authority": authority,
                "source_head": head, "metadata_artifact": self.ledger.artifacts.put(metadata),
                "selected_metadata_artifact": self.ledger.artifacts.put(selected),
                "process_observations": [before, after], "summary": _counts(selected, [before, after])}
            identity = self.ledger.record(session, RESULT, intent, result)
            self._guard(session, source, head, code)
            output = self._summary_probe(session, self._one(RESULT), desired, intent, protocol, sequence)
            self._progress_probe({"stage": "complete", **result["summary"], "elapsed_seconds": round(time.perf_counter() - began, 3),
                "result_record": identity, "final_result": True})
            return {**output, "reused_completed": False}
        finally:
            source.close()


def _counts(selected, observations):
    require(len(observations) == 2, "observation_pair")
    return {"matched_records": len(selected["records"]), "matched_events": len(selected["events"]),
        "exact_result_matches": sum(s["selector"] == "exact_result_id" for s in selected["selectors"]),
        "exact_key_matches": sum(s["selector"] == "exact_execution_key" for s in selected["selectors"]),
        "presentation_matches": sum(s["selector"] == "exact_presentation_artifact" for s in selected["selectors"]) + len(selected["presentation_saved_events"]),
        "native_link_count": len(selected["native_links"]), "uninspected_lifecycle_references": len(selected["uninspected_lifecycle_references"]),
        "unresolved_process_matches_before": len(observations[0]["observation"]["matching_processes"]),
        "unresolved_process_matches_after": len(observations[1]["observation"]["matching_processes"])}
