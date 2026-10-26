"""Bounded retained development evidence for the separately registered recall repair.

Only collect() performs I/O, inside the caller's offline Research.execute. It
borrows locked read-only views, never opens historical Research writers, and
never changes labels or infers missing historical attempts. precheck/diagnose
are pure descriptive projections, not calibration or permission to dispatch.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace

import dossier_contract as base
import dossier_contract_v5 as focal
import luna_quality_audit as audit
import luna_quality_source as frozen
from newsresearch.common import AuditError, digest, require_active, utc
from newsresearch.storage import check_permissions

ROOT = Path(__file__).resolve().parents[3]
METHOD = "cybercrime-luna-recall-retained-development-v1"
FIELDS = {"audit_plan_record", "audit_plan_artifact", "audit_report_record", "audit_report_artifact"}
REQUIRED_FIELDS = {"audit_plan_record", "audit_report_record"}
GRID = (.70, .75, .80, .85, .90, .95)
BASE_RUBRIC = digest({"pair": base.PAIR_RULES, "clarity": base.CLARITY_RULES})
FOCAL_RUBRIC = digest({"pair": base.PAIR_RULES, "clarity": base.CLARITY_RULES, "focus": focal.FOCUS_RULES})
PHASES = {"full_v6_seeds", "full_v6_seed_assignments", "full_v6_seed_expansion_plan",
    "full_v6_seed_checked_commit", "full_v6_recovery_assignments", "full_v6_recovery_expansion_plan",
    "full_v6_recovery_checked_commit", "full_v6_outcome"}
MEMBERSHIP_PHASES = {"summary", "summary_quality", "summary_quality_audit", "card_quality", "card_quality_audit"}
POLICY = {"development_only": True, "model_calls": 0, "original_owner_mutations": 0,
    "source_texts_reused_from_completed_audit": True, "embeddings_recomputed": False,
    "historical_global_closure_claimed": False, "threshold": .85, "threshold_validated": False,
    "maximum_prepare_seconds": 1800, "maximum_selected_bytes": 1_073_741_824,
    "missing_history_is_negative": False}


def require(value, reason):
    if not value:
        raise AuditError("luna_recall_source_" + reason)


def implementation():
    return {**audit.implementation(), **{p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__), Path(focal.__file__))}}


class Reader(frozen.SelectedSource):
    def __init__(self, *args, **kwargs):
        self.decoded = {}
        super().__init__(*args, **kwargs)

    def artifact_bytes(self, reference):
        self._active()
        if reference in self.copied and reference not in self.cache:
            raw = self.engine.ledger.artifacts.read_bytes(reference)
            require(hashlib.sha256(raw).hexdigest() == reference, "local_retained_hash")
            self.cache[reference] = raw
        else:
            raw = super().artifact_bytes(reference)
        require(self.unique_bytes <= POLICY["maximum_selected_bytes"], "selected_byte_limit")
        return raw

    def artifact(self, reference):
        self._active()
        if reference not in self.decoded:
            self.decoded[reference] = json.loads(self.artifact_bytes(reference))
        return self.decoded[reference]

    def release(self, *references):
        self._active()
        # Retained local bytes may be reused; the original owner is read once.
        for reference in references:
            self.decoded.pop(reference, None)
            self.cache.pop(reference, None)

    def rows(self, kind):
        self._active()
        return [self._row(r) for r in self.db.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def progress(self, stage, done, total):
        self._active()
        if done % 100 == 0 or done == total:
            callback = getattr(self.engine, "source_progress", None)
            if callback:
                callback({"stage": stage, "observed_at": utc(), "processed_units": done, "total_units": total,
                    "selected_artifacts": len(self.copied), "selected_bytes": self.unique_bytes})

    def close(self):
        try:
            super().close()
        finally:
            self.decoded.clear()


def _plain(row):
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _one(reader, kind, identity=None):
    rows = reader.rows(kind)
    require(len(rows) == 1 and (identity is None or rows[0]["_record_id"] == identity), "unique_" + kind)
    return rows[0]


def completed(reader, row, code, *, prepare=False):
    """Exact native successful session, not a durable row before a failed end."""
    session = reader.db.execute("SELECT session_id FROM events WHERE seq=?", (row["_created_event"],)).fetchone()[0]
    events = [dict(r) for r in reader.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (session,))]
    kinds = {k: [e for e in events if e["kind"] == k] for k in
        ("session.started", "operation.intended", "operation.completed", "session.ended", "operation.failed")}
    require(not kinds["operation.failed"] and all(len(kinds[k]) == 1 for k in
        ("session.started", "operation.intended", "operation.completed", "session.ended")), "producer_not_completed")
    start, intent, done, end = (kinds[k][0] for k in
        ("session.started", "operation.intended", "operation.completed", "session.ended"))
    require(start["seq"] < intent["seq"] < row["_created_event"] < done["seq"] < end["seq"]
        and json.loads(end["payload"]) == {"status": "completed"}, "producer_chronology")
    identity_ref = json.loads(start["payload"])["identity"]
    identity = reader.artifact(identity_ref)
    require(all(identity["code_files"].get(p) == h for p, h in code.items() if p.startswith("src/") and p.endswith(".py")),
        "producer_runtime_code")
    incoming, outgoing = json.loads(intent["payload"]), json.loads(done["payload"])
    require(incoming["operation"] == outgoing["operation"] == "status", "producer_operation")
    data, result = reader.artifact(incoming["input"]), reader.artifact(outgoing["result"])
    if prepare:
        expected = {"action": "prepare", **{k: row[k] for k in ("source_owner", "snapshot_owner", "binding", "seed", "approval")}}
        require(data == expected and result.get("plan") == row["_record_id"] and result.get("method") == audit.METHOD,
            "prepare_completion_binding")
    else:
        require(data in ({"action": "run", "allow_paid_execution": True}, {"action": "status"}, {"action": "report"})
            and result == {"id": row["_record_id"], **_plain(row)}, "report_completion_binding")
    return {"session": session, "input": incoming["input"], "output": outgoing["result"],
        "identity": identity_ref, "completed_event": done["seq"]}


class AuditView:
    """Read capabilities only; reuse the frozen audit's exact census, no writer."""
    def __init__(self, reader):
        self.reader = reader
        intended = {json.loads(r[0])["attempt"]: json.loads(r[0]) for r in reader.db.execute(
            "SELECT payload FROM events WHERE kind='model.attempt.intended'")}
        done = {json.loads(r[0])["attempt"] for r in reader.db.execute("SELECT payload FROM events WHERE kind='model.attempt.completed'")}
        self.ledger = SimpleNamespace(db=reader.db, artifacts=SimpleNamespace(read=reader.artifact),
            unresolved={k: v for k, v in intended.items() if k not in done})

    def rows(self, kind):
        return [{"id": r["_record_id"], **_plain(r)} for r in self.reader.rows(kind)]


def _audit_evidence(reader, binding):
    plan = _one(reader, audit.PLAN, binding["audit_plan_record"])
    report = reader.record(binding["audit_report_record"], audit.REPORT)
    require(plan["_artifact"] == binding.get("audit_plan_artifact", plan["_artifact"])
        and report["_artifact"] == binding.get("audit_report_artifact", report["_artifact"])
        and report["plan"] == plan["_record_id"] and report["method"] == plan["method"] == audit.METHOD,
        "audit_binding")
    require(plan["implementation"] == audit.implementation(), "audit_implementation")
    intent = _one(reader, audit.INTENT, plan["intent"])
    desired = _plain(intent)
    require(all(plan.get(k) == v for k, v in desired.items()), "audit_intent")
    for row, key in ((intent, audit.METHOD), (plan, plan["intent"])):
        raw = reader.db.execute("SELECT logical_key,supersedes FROM records WHERE id=?", (row["_record_id"],)).fetchone()
        require(raw[0] == key and raw[1] is None, "audit_record_key")
    expected = audit.version_contents(desired)
    require(set(plan["versions"]) == set(expected), "audit_version_set")
    for kind, content in expected.items():
        ids = [r[0] for r in reader.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, audit.METHOD))]
        require(ids == [plan["versions"][kind]], "audit_unique_version")
        version = reader.record(plan["versions"][kind], kind)
        raw = reader.db.execute("SELECT logical_key,supersedes FROM records WHERE id=?", (version["_record_id"],)).fetchone()
        require(raw[0] == audit.METHOD and raw[1] is None and version["content"] == content
            and version["branch"] == "main" and version["reason"] is None
            and intent["_created_event"] < version["_created_event"] < plan["_created_event"], "audit_version_binding")
    completions = [completed(reader, plan, plan["implementation"], prepare=True), completed(reader, report, plan["implementation"])]
    source = reader.artifact(plan["source_artifact"])
    audit.verify_source_binding(source, desired)
    saved = _one(reader, audit.SOURCE)
    require(saved["intent"] == plan["intent"] and saved["artifact"] == plan["source_artifact"], "audit_source_checkpoint")
    design, packets = (reader.artifact(plan[k]) for k in ("design_artifact", "packets_artifact"))
    bykey = {p["task_key"]: p for p in packets}
    require(len(bykey) == len(packets) == plan["planned_requests"], "audit_packet_partition")
    selected = {r["pair_key"]: [r["left"], r["right"]] for r in design["pair_tasks"]}
    require(len(selected) == len(design["pair_tasks"]) == plan["selected_distinct_pairs"], "audit_pair_partition")
    allpairs = []
    for n, p in enumerate(packets, 1):
        reader.progress("recall_audit_packets", n, len(packets))
        require(p["request_sha256"] == digest(p["request"])
            and p["task_key"] == digest([audit.METHOD, p["request_sha256"], p["pair_keys"]]), "audit_packet_key")
        for doc in p["documents"]:
            original = source["documents"][p["source_bindings"][doc["document_id"]]["document_id"]]
            require({k: doc[k] for k in ("title", "body")} == {k: original[k] for k in ("title", "body")}, "audit_packet_full_source")
        allpairs.extend(p["pair_keys"])
    require(len(set(allpairs)) == len(allpairs) and set(allpairs) | set(plan["unavailable_pairs"]) == set(selected), "audit_task_coverage")
    state = audit.Audit.census(AuditView(reader), {"id": plan["_record_id"], **_plain(plan)}, packets)
    for key in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unknown_holds", "returned_requests", "unreturned_requests"):
        require(report[key] == state[key], "audit_report_census")
    require(report["unattempted_requests"] == 0 and report["unreturned_requests"] == 0
        and report["attempted_requests"] == len(packets) == len(state["intents"])
        and report["assessed_response_records"] == len(state["responses"]), "audit_not_finished")
    observations, clarities = [], []
    for n, (key, response) in enumerate(state["responses"].items(), 1):
        reader.progress("recall_audit_responses", n, len(state["responses"]))
        packet = bykey[key]
        parsed = reader.artifact(response["parsed"]) if response["parsed"] else None
        rows, clear = normalize_pairs(packet, parsed, source["documents"],
            role="development_audit", attempt=response["attempt"], task_key=key,
            refs={"response": response["response"], "parsed": response["parsed"]}, usable=response["usable"] and not response["hold"])
        observations.extend(rows)
        clarities.extend(clear)
        if response["parsed"]:
            reader.release(response["parsed"])
    reader.release(plan["packets_artifact"])
    return source, {"plan_record": plan["_record_id"], "plan_artifact": plan["_artifact"],
        "report_record": report["_record_id"], "report_artifact": report["_artifact"],
        "design": design, "labels": {k: state["labels"].get(k, "unknown") for k in selected},
        "source_pairs": selected, "parsed": observations, "pair_observations": observations, "clarity": clarities,
        "attempts": list(state["intents"].values()), "commitment_nanousd": state["committed_nanousd"],
        "held_nanousd": state["held_nanousd"], "settled_nanousd": state["settled_nanousd"],
        "completions": completions, "development_exposed": True}, plan


def normalize_pairs(packet, parsed, documents, *, role, attempt, task_key, refs, usable):
    """Normalize exact source identities; retain repeated observations separately."""
    source_map = packet.get("source_bindings") if isinstance(packet.get("source_bindings"), dict) else None
    mapping = {k: v["document_id"] for k, v in source_map.items()} if source_map else {i: i for i in documents}
    originals = packet.get("original_documents", packet.get("documents", []))
    exact = bool(originals)
    for doc in originals:
        identity = mapping.get(doc["document_id"], doc["document_id"])
        expected = documents.get(identity)
        exact = exact and expected is not None and all(doc.get(k) == expected[k] for k in ("title", "body"))
    focus = packet.get("focus_rules_sha256", packet.get("normalization", {}).get("focus_rules_sha256"))
    wire = packet.get("request", {})
    questions = wire.get("questions", []) if packet.get("phase") == "seed" else json.loads(wire.get("input", "{}" )).get("questions", [])
    semantic = [q.get("instructions", "") for q in questions]
    core = bool(semantic) and all(base.PAIR_RULES in q or base.CLARITY_RULES in q for q in semantic)
    compatible = exact and core and packet.get("method") == focal.METHOD and focus == digest(focal.FOCUS_RULES) and all(focal.FOCUS_RULES in q for q in semantic)
    baseline = exact and core and not focus and all(focal.FOCUS_RULES not in q for q in semantic)
    rubric = FOCAL_RUBRIC if compatible else BASE_RUBRIC if baseline else None
    answers = list((parsed or {}).get("answers", {}).values())
    clear = []
    for a in answers:
        if a.get("kind") != "clarity":
            continue
        identity = mapping.get(a["document_id"], a["document_id"])
        require(identity in documents, "parsed_clarity_identity")
        clear.append({**a, "document_id": identity, "input_sha256": documents[identity]["input_sha256"],
            "physical_attempt": attempt, "task_key": task_key, "role": role, "method": packet.get("method"),
            "rubric_sha256": digest({"clarity": base.CLARITY_RULES, "focus": focal.FOCUS_RULES if compatible else None}) if rubric else None,
            "representation": "full_title_body" if exact else "unverified", "usable": usable and exact,
            "artifact_refs": refs, "reference_model": (parsed or {}).get("reference_model")})
    bydoc = {a["document_id"]: a for a in clear}
    result = []
    for answer in answers:
        if answer.get("kind") != "pair":
            continue
        pair = sorted(mapping.get(answer[k], answer[k]) for k in ("left", "right"))
        require(len(set(pair)) == 2 and all(i in documents for i in pair), "parsed_pair_identity")
        result.append({"pair": pair, "pair_key": digest(pair), "input_sha256": [documents[i]["input_sha256"] for i in pair],
            "role": role, "phase": packet.get("phase"), "method": packet.get("method"), "rubric_sha256": rubric,
            "representation": "full_title_body" if exact else "unverified", "label": answer.get("label"),
            "status": answer.get("status"), "probabilities": answer.get("probabilities"),
            "chosen_probability": answer.get("probability"), "confidence": answer.get("confidence"),
            "clarity": [bydoc.get(i) for i in pair], "physical_attempt": attempt, "task_key": task_key,
            "compatible_focal_rubric": compatible, "usable": usable and exact,
            "negative_rule": "chosen_label" if role == "development_audit" else "not_classified_by_seed_partition" if role == "native_seed" else "reference_categorical",
            "artifact_refs": refs, "reference_model": (parsed or {}).get("reference_model")})
    return result, clear


def _main_history(reader, source):
    provenance = source["provenance"]
    report = reader.record(provenance["binding"]["report_record"], "cyber_dossier_report")
    require(report["_artifact"] == provenance["binding"]["report_artifact"] and report.get("pipeline_finished") is True,
        "main_final_report")
    reader.ensure_report_last(report)
    phases, refs, gaps = {}, {}, []
    for row in reader.db.execute("SELECT * FROM records WHERE kind='cyber_dossier_phase' ORDER BY created_event"):
        if row["logical_key"] in PHASES:
            value = reader._row(row)
            require(value["name"] == row["logical_key"] and value["plan"] == report["plan"] and value["name"] not in phases,
                "native_phase_binding")
            payload = reader.artifact(value["artifact"])
            phases[value["name"]] = {k: v for k, v in payload.items() if k not in {"cards", "usable"}}
            refs[value["name"]] = {"record": row["id"], "artifact": value["artifact"]}
            reader.release(value["artifact"])
    for name in sorted(PHASES - set(phases)):
        gaps.append({"reason": "native_phase_unavailable", "phase": name})
    memberships, cards = {}, defaultdict(list)
    for row in reader.rows("cyber_dossier_evidence_card"):
        ids = row["document_ids"]
        require(row["membership_revision"] == digest(sorted(ids)) and set(ids) <= set(source["documents"]), "native_card_membership")
        key = (row["dossier_id"], row["membership_revision"])
        require(key not in memberships or memberships[key] == ids, "native_membership_conflict")
        memberships[key] = ids
        cards[row["dossier_id"]].append({"membership_revision": row["membership_revision"], "document_ids": sorted(ids),
            "record": row["_record_id"], "artifact": row["artifact"], "card_version": row.get("card_version"),
            "representation_type": row.get("representation_type")})
    intended = {}
    for event in reader.db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
        value = json.loads(event["payload"])
        if value.get("batch") != report["plan"]:
            continue
        require(value["attempt"] not in intended, "native_repeated_attempt")
        intended[value["attempt"]] = {**value, "event": event["seq"]}
    responses = {}
    for value in reader.rows("cyber_dossier_response"):
        require(value["plan"] == report["plan"] and value["attempt"] in intended and value["attempt"] not in responses,
            "native_response_identity")
        original = intended[value["attempt"]]
        require(all(value[k] == original[k] for k in ("task_key", "packet", "request", "phase")), "native_response_binding")
        responses[value["attempt"]] = value
    pairs, member_rows, clarities = [], [], []
    for n, (attempt, intent) in enumerate(intended.items(), 1):
        reader.progress("recall_native_attempts", n, len(intended))
        phase = intent.get("phase")
        if phase not in MEMBERSHIP_PHASES | {"seed", "audit"}:
            continue
        response = responses.get(attempt, {})
        parsed = reader.artifact(response["parsed"]) if response.get("parsed") else None
        usable = bool(parsed and not response.get("hold"))
        artifacts = {k: v for k, v in {"packet": intent["packet"], "request": intent["request"],
            "response_record": response.get("_record_id"), "response": response.get("response"), "parsed": response.get("parsed")}.items() if v}
        if phase in {"seed", "audit"}:
            packet = reader.artifact(intent["packet"])
            rows, clear = normalize_pairs(packet, parsed, source["documents"], role="independent_astra" if phase == "audit" else "native_seed",
                attempt=attempt, task_key=intent["task_key"], refs=artifacts, usable=usable)
            pairs.extend(rows)
            clarities.extend(clear)
            if rows and any(r["rubric_sha256"] is None for r in rows):
                gaps.append({"reason": "native_pair_rubric_unmatched", "attempt": attempt, "packet": intent["packet"]})
            # Missing/invalid replies still carry all intended pair identities.
            observed = {r["pair_key"] for r in rows}
            for item in packet.get("question_map", {}).values():
                if item.get("kind") == "pair":
                    ids = sorted([item["left"], item["right"]])
                    if set(ids) <= set(source["documents"]) and digest(ids) not in observed:
                        pairs.append({"pair": ids, "pair_key": digest(ids), "physical_attempt": attempt,
                            "task_key": intent["task_key"], "phase": phase, "role": "independent_astra" if phase == "audit" else "native_seed",
                            "status": "missing_or_invalid", "usable": False, "compatible_focal_rubric": False, "artifact_refs": artifacts})
        else:
            value = parsed or {}
            key = (value.get("dossier_id"), value.get("membership_revision"))
            ids = memberships.get(key) or value.get("source_document_ids")
            if not ids:
                packet = reader.artifact(intent["packet"])
                bound = packet.get("bindings", {})
                key = (bound.get("dossier_id"), bound.get("membership_revision"))
                ids = packet.get("document_ids", [])
            require(ids and set(ids) <= set(source["documents"]) and key[1] == digest(sorted(ids)), "native_attempt_membership")
            member_rows.append({"document_ids": sorted(ids), "membership_revision": key[1], "dossier_id": key[0],
                "phase": phase, "status": value.get("label", "missing_or_invalid"), "label": value.get("label"), "usable": usable and value.get("label") == "supported",
                "hold": response.get("hold", True), "physical_attempt": attempt, "task_key": intent["task_key"], "artifact_refs": artifacts})
        reader.release(*[ref for ref in (intent["packet"], response.get("parsed")) if ref in reader.copied])
    return {"pair_observations": pairs, "clarity_observations": clarities, "membership_attempts": member_rows, "task_keys": sorted({v["task_key"] for v in intended.values()}),
        "attempts": list(intended.values()), "native_phases": phases, "phase_refs": refs, "gaps": gaps, "cards": dict(cards),
        "native_observations_reused": True, "global_history_complete": False}


def collect(engine, session, *, audit_owner, binding, deadline_monotonic):
    """Audited caller owns registration, returned evidence retention and progress."""
    require_active(engine, session)
    require(engine.config.offline and isinstance(binding, dict) and REQUIRED_FIELDS <= set(binding) <= FIELDS, "offline_binding")
    require(type(deadline_monotonic) in (int, float) and math.isfinite(deadline_monotonic)
        and 0 < deadline_monotonic - time.monotonic() <= 1800, "deadline")
    for value in binding.values():
        frozen.source_api._sha(value)
    owner = frozen.discovery.canonical_path(str(audit_owner))
    code, started = implementation(), time.monotonic()
    observer, observations, readers = frozen.discovery.study.WindowsProcessObserver(), [], []
    def progress(stage):
        frozen._stop(engine, session, [], deadline_monotonic)
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "observed_at": utc(), "elapsed_seconds": time.monotonic() - started,
                "selected_artifacts": sum(len(r.copied) for r in readers), "selected_bytes": sum(r.unique_bytes for r in readers)})
    progress("recall_import_audit_metadata")
    with ExitStack() as stack:
        def opened(path):
            observations.append(frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), path))
            reader = Reader(engine, session, path, deadline=deadline_monotonic)
            stack.callback(reader.close)
            readers.append(reader)
            frozen.discovery.metadata_census(reader)
            return reader, reader.head(), frozen._historical_stop(path)
        parent, audit_head, audit_stop = opened(owner)
        source, evidence, plan = _audit_evidence(parent, binding)
        main_owner = frozen.discovery.canonical_path(source["provenance"]["source_owner"])
        require(main_owner != owner and main_owner != engine.ledger.root.resolve(), "separate_main_owner")
        progress("recall_import_native_obstructions")
        main, main_head, main_stop = opened(main_owner)
        require(main_head == source["provenance"]["source_head"], "main_head_changed")
        history = _main_history(main, source)
        progress("recall_import_exit_guards")
        for reader, head, stop in ((parent, audit_head, audit_stop), (main, main_head, main_stop)):
            reader._active()
            check_permissions(reader.owner, root=True)
            check_permissions(reader.owner / "objects")
            require(reader.head(fresh=True) == head and frozen._historical_stop(reader.owner) == stop, "source_changed")
            observations.append(frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), reader.owner))
        require(implementation() == code, "implementation_changed")
        imported = {"method": METHOD, "implementation": code, "policy": POLICY, "binding": binding,
            "audit_owner": str(owner), "audit_head": audit_head, "main_owner": str(main_owner), "main_head": main_head,
            "source_artifact": plan["source_artifact"], "design_artifact": plan["design_artifact"],
            "copied_artifacts": {str(r.owner): dict(r.copied) for r in readers}, "observations": observations,
            "historical_stops": {str(owner): audit_stop, str(main_owner): main_stop}, "source_heads_stable_during_copy": True,
            "current_quiescence_verified": False, "elapsed_seconds": time.monotonic() - started}
        result = {**source, "audit": evidence, "prior_history": history, "recall_provenance": imported}
        result["precheck"] = precheck(result)
        result["diagnostic"] = diagnose(result)
        progress("recall_import_complete")
        return result


def _distribution(value, labels):
    return isinstance(value, dict) and set(value) == set(labels) and all(
        type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in value.values()) and abs(sum(value.values()) - 1) <= .01


def _prediction(row, pair_threshold, clarity_threshold):
    if not row.get("usable") or row.get("status") != "valid":
        return "unknown", "unavailable_observation"
    clarity = row.get("clarity", [])
    if len(clarity) != 2 or any(not a or a.get("status") != "valid" for a in clarity):
        return "unknown", "clarity_unavailable"
    if any(a.get("label") != "clear_single_event" or not _distribution(a.get("probabilities"), base.CLARITY_LABELS)
        or a["probabilities"].get("clear_single_event", 0) < clarity_threshold for a in clarity):
        return "unknown", "clarity_gate"
    p = row.get("probabilities")
    if not _distribution(p, base.PAIR_LABELS):
        return "unknown", "pair_distribution_unavailable"
    if row.get("label") == "same_event" and p.get("same_event", 0) >= pair_threshold:
        return "same_event", "positive"
    if row.get("negative_rule") == "not_classified_by_seed_partition":
        return "unknown", "native_seed_nonpositive_not_classified"
    # Preserve the producer's native negative rule; do not silently recode audit.
    negative = p.get("related_event", 0) + p.get("different_event", 0) if row.get("negative_rule") == "sum_nonmatch" else p.get(row.get("label"), 0)
    if row.get("label") in {"related_event", "different_event"} and negative >= pair_threshold:
        return "negative", "negative"
    return "unknown", "pair_gate"


def _identity(row):
    return {k: row.get(k) for k in ("pair_key", "document_id", "physical_attempt", "task_key", "artifact_refs",
        "input_sha256", "method", "rubric_sha256", "representation", "role", "label", "status")}


def _equal_contract(row, ref):
    return all(row.get(k) is not None and row.get(k) == ref.get(k) for k in ("input_sha256", "rubric_sha256", "representation"))


def _ratios(counts, positive="same_event", negative="negative"):
    tp, fp = counts.get(positive + "__" + positive, 0), counts.get(negative + "__" + positive, 0)
    ref_positive = sum(v for k, v in counts.items() if k.startswith(positive + "__"))
    ref_negative = sum(v for k, v in counts.items() if k.startswith(negative + "__"))
    return {"conditional_precision": tp / (tp + fp) if tp + fp else None,
        "reference_positive_sensitivity": tp / ref_positive if ref_positive else None,
        "reference_positive_denominator": ref_positive, "reference_negative_denominator": ref_negative}


def _clarity_diagnostic(source):
    native = source.get("prior_history", {}).get("clarity_observations", [])
    observations = [*source.get("audit", {}).get("clarity", []), *[r for r in native if r.get("role") == "native_seed"]]
    references = [r for r in native if r.get("role") == "independent_astra" and r.get("reference_model") == "gpt-6-astra"]
    bydoc, aligned, unmatched = defaultdict(list), [], []
    for ref in references:
        bydoc[ref["document_id"]].append(ref)
    for row in observations:
        options = bydoc[row["document_id"]]
        if not options:
            unmatched.append({"observation": _identity(row), "reason": "no_independent_article_reference"})
        for ref in options:
            if not _equal_contract(row, ref):
                unmatched.append({"observation": _identity(row), "reference": _identity(ref), "reason": "source_rubric_or_representation_mismatch"})
                continue
            label = "unknown"
            if ref.get("usable") and ref.get("status") == "valid":
                label = "clear" if ref.get("label") == "clear_single_event" else "not_clear" if ref.get("label") in {
                    "multiple_focal_events", "not_event_focused"} else "unknown"
            aligned.append((row, ref, label))
    tables = []
    for threshold in GRID:
        counts = Counter()
        for row, ref, label in aligned:
            p = row.get("probabilities")
            valid = row.get("usable") and row.get("status") == "valid" and _distribution(p, base.CLARITY_LABELS)
            predicted = "clear" if valid and row.get("label") == "clear_single_event" and p["clear_single_event"] >= threshold else "not_clear" if valid and row.get("label") in {
                "multiple_focal_events", "not_event_focused"} and p[row["label"]] >= threshold else "unknown"
            counts[label + "__" + predicted] += 1
        tables.append({"threshold": threshold, "confusion": dict(counts), **_ratios(counts, "clear", "not_clear")})
    return {"independent_references": len(references), "matched_observations": len(aligned),
        "matched_manifest": [{"observation": _identity(r), "reference": _identity(f), "reference_label": label} for r, f, label in aligned],
        "unmatched_manifest": unmatched, "grid": tables, "threshold_validated": False,
        "insufficient_information_is_unknown": True, "negative_reference_coverage": any(label == "not_clear" for _, _, label in aligned)}


def precheck(source):
    """Conditional alignment/sensitivity only; .85 is never auto-selected."""
    native = source.get("prior_history", {}).get("pair_observations", [])
    observations = [*source.get("audit", {}).get("pair_observations", []), *[r for r in native if r.get("role") == "native_seed"]]
    refs = [r for r in native if r.get("role") == "independent_astra" and r.get("reference_model") == "gpt-6-astra"]
    bypair = defaultdict(list)
    for r in refs:
        bypair[r["pair_key"]].append(r)
    matched, unmatched, missing = [], Counter(), []
    for row in observations:
        options = bypair[row["pair_key"]]
        if not options:
            unmatched["no_independent_pair_reference"] += 1
            missing.append({"observation": _identity(row), "reason": "no_independent_pair_reference"})
        for ref in options:
            if not _equal_contract(row, ref):
                unmatched["source_rubric_or_representation_mismatch"] += 1
                missing.append({"observation": _identity(row), "reference": _identity(ref), "reason": "source_rubric_or_representation_mismatch"})
                continue
            if not ref.get("usable") or ref.get("status") != "valid" or len(ref.get("clarity", [])) != 2 or any(
                not c or c.get("label") != "clear_single_event" for c in ref["clarity"]):
                unmatched["reference_unavailable_or_unclear"] += 1
                missing.append({"observation": _identity(row), "reference": _identity(ref), "reason": "reference_unavailable_or_unclear"})
                continue
            label = "same_event" if ref.get("label") == "same_event" else "negative" if ref.get("label") in {"related_event", "different_event"} else "unknown"
            matched.append((row, ref, label))
    tables = []
    for axis in ("pair", "clarity"):
        for threshold in GRID:
            counts, reasons, strata, contracts = Counter(), Counter(), defaultdict(Counter), {}
            for row, ref, label in matched:
                predicted, reason = _prediction(row, threshold if axis == "pair" else .85, threshold if axis == "clarity" else .85)
                cell = label + "__" + predicted
                counts[cell] += 1
                reasons[reason] += 1
                contract = {k: row.get(k) for k in ("method", "rubric_sha256", "representation", "role", "negative_rule")}
                key = digest(contract)
                contracts[key] = contract
                strata[key][cell] += 1
            tables.append({"axis": axis, "threshold": threshold, "other_threshold": .85, "matched_observations": len(matched),
                "confusion": dict(counts), "gating_reasons": dict(reasons), "strata": {k: {"contract": contracts[k], "counts": dict(v)} for k, v in strata.items()},
                **_ratios(counts)})
    reference_labels = defaultdict(set)
    for row, ref, label in matched:
        reference_labels[row["pair_key"]].add(label)
    return {"method": METHOD, "selected_threshold": .85, "threshold_validated": False,
        "selection_supported": False, "reason": "historical_selected_cases_do_not_validate_new_rubric_threshold",
        "independent_references": len(refs), "matched_observations": len(matched), "unmatched": dict(unmatched),
        "matched_unique_pairs": len(reference_labels), "conflicting_reference_pairs": sum(len(v - {"unknown"}) > 1 for v in reference_labels.values()),
        "matched_manifest": [{"observation": _identity(row), "reference": _identity(ref), "reference_label": label} for row, ref, label in matched],
        "unmatched_manifest": missing, "clarity_diagnostic": _clarity_diagnostic(source),
        "repeated_observations_preserved": True, "population_calibration": False, "grid": tables}


def diagnose(source):
    """Only recorded per-query reasons; multiple reasons may overlap."""
    phases = source.get("prior_history", {}).get("native_phases", {})
    reasons, affected = Counter(), defaultdict(set)
    for name in ("full_v6_seed_assignments", "full_v6_recovery_assignments"):
        value = phases.get(name, {})
        for identity, reason in value.get("unresolved", {}).items():
            reasons[reason] += 1
            affected[identity].add(reason)
        for identity, coverage in value.get("packet_coverage", {}).items():
            if not coverage.get("coverage_complete"):
                reasons["incomplete_candidate_evaluation"] += 1
                affected[identity].add("incomplete_candidate_evaluation")
    for name in ("full_v6_seed_expansion_plan", "full_v6_recovery_expansion_plan"):
        value = phases.get(name, {})
        for identity, reason in value.get("conflicts", {}).items():
            reasons[reason] += 1
            affected[identity].add(reason)
        for identity, reason in value.get("eligibility", {}).get("exclusions", {}).items():
            reasons[reason] += 1
            affected[identity].add(reason)
    for name in ("full_v6_seed_checked_commit", "full_v6_recovery_checked_commit"):
        for row in phases.get(name, {}).get("rejected_expansions", {}).values():
            reason = "group_review:" + row.get("reason", "unavailable")
            reasons[reason] += 1
            for identity in row.get("document_ids", []):
                affected[identity].add(reason)
    labels = source.get("audit", {}).get("labels", {})
    pairmap = source.get("audit", {}).get("source_pairs", {})
    owner = {i: g for g in source["accepted_group_ids"] for i in source["groups"][g]}
    misses = []
    for key, label in labels.items():
        if label != "same_event" or key not in pairmap:
            continue
        a, b = pairmap[key]
        if a in owner and owner.get(a) == owner.get(b):
            continue
        local = sorted(affected.get(a, set()) | affected.get(b, set()))
        misses.append({"pair_key": key, "pair": [a, b], "recorded_reasons": local,
            "attribution": "recorded_obstruction_not_proven_cause" if local else "unattributed"})
    return {"method": METHOD, "recorded_reason_counts": dict(reasons), "audit_positive_nonjoins": misses,
        "unattributed_misses": sum(not r["recorded_reasons"] for r in misses),
        "causal_attribution_claimed": False, "trace_gaps": source.get("prior_history", {}).get("gaps", [])}
