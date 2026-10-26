"""Compact native request/proof fixtures; no real owner, account or model access."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from newsresearch.codex_provider import CodexCLIProvider, PreparedCodexInvocation, build_prompt
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.event_pair_answers import TASK_INSTRUCTION, build_request
from newsresearch import event_group_evidence_judging as judging
from newsresearch import event_pair_experiment as original
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_native_reference as subject  # noqa: E402
import test_final_validation_exact_locator_probe as previous  # noqa: E402


def article(number):
    """Literal bytes of the existing four-input synthetic Snapshot fixture."""
    title = f"PRIVATE FULL TITLE {number} \u2014 e\u0301"
    body = f"PRIVATE BODY {number}\r\n\r\n tweede alinea \U0001f600\n with whitespace \t\n"
    source = digest(["synthetic-native-source", number])
    return {"source_version": source, "title": title, "body": body, "published_at": None,
        "evidence": [{"id": digest(["synthetic-passage", number]), "source_id": source,
            "start": 0, "end": len(body), "text": body,
            "text_hash": hashlib.sha256(body.encode()).hexdigest()}]}


def request_and_dispatch(owner, versions, numbers=(0, 1), worker_name="codex-judge-synthetic-planning"):
    request = build_request(left=article(numbers[0]), right=article(numbers[1]), versions=versions)
    # Only deterministic native argument/manifest builders; never prepare/run.
    worker = owner / "codex-workers" / worker_name
    provider = CodexCLIProvider(owner / "codex-workers", executable="C:/synthetic/codex.exe", model="synthetic-native-model")
    invocation = PreparedCodexInvocation(provider._command(worker), worker, build_prompt(request),
        request["schema"], request, provider.model)
    return request, invocation.manifest()


def approval_for(identifier, prepared, frozen, key):
    return {"method": "cross-window-event-review-run-approval-v1", "prepared_result": identifier,
        "study_key": key, "original_study_key": "synthetic-native-original",
        "prepared_binding": judging.approval_binding(identifier, prepared, frozen),
        "max_pair_attempts": 100, "max_primary_pairs": 90, "max_known_invalid_retries": 10,
        "synthetic_permission_only": True, "authorization_key": "synthetic-native-approved"}


class NativeSource(Research):
    """Recorded native schemas, synthetic producer output; no provider runs."""

    @audited_handler
    def _prepare_cross_window_event_review(self, session, context, data):
        preparation = judging.preparation
        config = {"codex_executable": "C:/synthetic/codex.exe", "codex_model": "synthetic-native-model",
            "executable_sha256": digest("synthetic executable"), "timeout_seconds": 180,
            "max_input_bytes": 500_000, "max_output_bytes": 2_000_000,
            "authentication": "existing Codex account; no API fallback", "provider_billing": None,
            "configuration_origin": {"mode": "explicit_model_and_executable"}}
        method = {"method": preparation.METHOD, "implementation": preparation.links.base._hashes(preparation.CODE),
            "previous_result": data["previous_result"], "config": config, "instructions": TASK_INSTRUCTION}
        versions = {}
        for kind in ("protocol", "question", "selection", "profile", "dossier_definition", "prompt", "codebook", "model_profile"):
            content = config if kind == "model_profile" else {**method, "binding_role": kind,
                "mode": "exploratory", "population_estimate": False,
                "text": "Which separate seven-day groups warrant full-source same-event review?",
                "unit": "One real-world event across sources or reporting times; every union member must be evidenced",
                "rules": "Missing, failed, pending and unjudged evidence never means different events",
                "labels": ["same_event", "different_event", "uncertain"]}
            versions[kind] = self._version(session, context, {"kind": kind, "key": data["study_key"], "content": content,
                "branch": "exploratory-cross-window-event-evidence",
                "reason": "Continue source-backed same-event review preparation after provider-only tier found no candidates"})["id"]
        manifest = self.ledger.record(session, "event_group_evidence_manifest", data["study_key"],
            {"versions": versions, "method": method, "started_at": utc()})
        request, dispatch = request_and_dispatch(self.ledger.root, versions)
        pair = sorted(a["source_version"] for a in request["articles"])
        # Native request order follows canonical source IDs.
        if request["articles"][0]["source_version"] != pair[0]:
            request, dispatch = request_and_dispatch(self.ledger.root, versions, (1, 0))
        task = {"pair_id": digest(pair), "left": pair[0], "right": pair[1]}
        queue = {"tasks": [task], "selected": []}
        queue_ref = self.ledger.artifacts.put(queue)
        frozen = self.ledger.record(session, "event_group_evidence_queue", data["study_key"],
            {"manifest": manifest, "versions": versions, "artifact": queue_ref, "frozen_before_reference_check": True})
        request_ref, dispatch_ref = self.ledger.artifacts.put(request), self.ledger.artifacts.put(dispatch)
        packet = {**task, "status": "prepared", "request_ref": request_ref, "dispatch_ref": dispatch_ref,
            "task_key": digest({"manifest": manifest, "request": request,
                "contract": request["gateway_contract"], "config": config})}
        packets_ref = self.ledger.artifacts.put([packet])
        self.ledger.record(session, "event_group_evidence_packets", data["study_key"], {"manifest": manifest,
            "versions": versions, "frozen_queue": frozen, "artifact": packets_ref})
        value = {"status": "prepared_evidence_queue", "versions": versions, "manifest": manifest,
            "frozen_queue": frozen, "exports": {"packets": {"artifact": packets_ref}}, "config": config,
            "previous_result": data["previous_result"]}
        identity = self.ledger.record(session, "event_group_evidence_result", data["study_key"], value)
        return {"id": identity, **value}

    @audited_handler
    def _judge_cross_window_event_review(self, session, context, data):
        prepared = self.ledger.get(data["prepared_result"], "event_group_evidence_result")
        frozen = self.ledger.get(prepared["frozen_queue"], "event_group_evidence_queue")
        versions, config = prepared["versions"], prepared["config"]
        approval = approval_for(data["prepared_result"], prepared, frozen, data["study_key"])
        assert approval == data["run_approval"]
        binding = {"method": judging.METHOD, "prepared_result": data["prepared_result"],
            "prepared_binding": judging.approval_binding(data["prepared_result"], prepared, frozen),
            "approval": approval, "implementation": judging.preparation.links.base._hashes(judging.CODE),
            "request_versions": versions, "config": config, "original_study_key": "synthetic-native-original",
            "budget_reset": False,
            "transport": "unchanged original audited _phase and shared gateway; no Responses substitute",
            "acceptance": "all-pair references only; no automatic merges or accepted event dossiers"}
        method_version = self._version(session, context, {"kind": "protocol", "key": data["study_key"],
            "content": {"method": judging.METHOD, **binding}, "branch": "authorized-cross-window-pairwise-review"})["id"]
        approval_version = self._version(session, context, {"kind": "policy", "key": data["study_key"], "content": approval})["id"]
        manifest = self.ledger.record(session, "event_group_evidence_judging_manifest", data["study_key"],
            {"versions": versions, "binding": binding, "method_version": method_version,
                "approval_version": approval_version, "budget_before": {"synthetic": True}})
        packet = self.ledger.artifacts.read(prepared["exports"]["packets"]["artifact"])[0]
        request = self.ledger.artifacts.read(packet["request_ref"])
        order = (0, 1) if request["articles"][0]["source_version"] == article(0)["source_version"] else (1, 0)
        actual_request, actual_dispatch = request_and_dispatch(self.ledger.root, versions, order, "codex-judge-synthetic-actual")
        assert actual_request == request
        actual_dispatch_ref = self.ledger.artifacts.put(actual_dispatch)
        assert actual_dispatch_ref != packet["dispatch_ref"]
        task_key = digest({"plan": manifest, "request": request, "config": config, "method": original.METHOD})
        self.ledger.record(session, "event_group_evidence_task_bindings", data["study_key"], {
            "manifest": manifest, "versions": versions, "items": [{"pair_id": packet["pair_id"],
                "planning_task_key": packet["task_key"], "actual_task_key": task_key,
                "request_ref": packet["request_ref"], "request_hash": digest(request),
                "source_versions": [packet["left"], packet["right"]], "request_versions": versions,
                "dispatch_manifest": "Original phase regenerates and records its own exact invocation; planning cwd identity is not claimed"}]})
        batch = self.ledger.record(session, "codex_batch_manifest", digest({"plan": manifest, "tasks": [task_key]}),
            {"versions": versions, "plan": manifest, "task_kind": "event_pair_identity",
                "event_pair_study": binding["original_study_key"], "items": [{"pair_id": packet["pair_id"],
                    "task_key": task_key, "request_ref": packet["request_ref"], "dispatch_ref": actual_dispatch_ref}]})
        self.ledger.append(session, "model.attempt.intended", {"attempt": "synthetic-native-orphan", "task_key": task_key,
            "number": 1, "batch": batch, "plan": manifest, "request": packet["request_ref"],
            "dispatch": actual_dispatch_ref, "event_pair_study": binding["original_study_key"],
            "pair_id": packet["pair_id"], "event_pair_retry": False, "authorization_key": approval["authorization_key"],
            "reserved_pair_attempts": 1, "reserved_article_exposures": 2,
            "source_versions": [packet["left"], packet["right"]], "started_at": utc()})
        value = {"versions": versions, "manifest": manifest, "prepared_result": data["prepared_result"],
            "method_version": method_version, "approval_version": approval_version,
            "original_study_key": binding["original_study_key"], "status": "partial", "judgements": {},
            "pair_tasks": 1, "new_model_attempts": 1, "provider_billing": None}
        identity = self.ledger.record(session, "event_group_evidence_judgment_result", data["study_key"], value)
        return {"id": identity, **value}


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    base = previous.template.__wrapped__(tmp_path_factory)
    candidate = tmp_path_factory.mktemp("native-reference") / "candidate"
    engine = NativeSource(candidate, config=Config(offline=True))
    try:
        prepared = engine.execute("prepare_cross_window_event_review", {
            "study_key": "synthetic-native-preparation", "previous_result": digest("synthetic previous result"),
            "output_directory": str(candidate / "exports")}, objective="Synthetic native schema preparation", actor="test")
    finally:
        engine.close()
    engine = NativeSource(candidate, config=Config(offline=False))
    try:
        frozen = engine.ledger.get(prepared["frozen_queue"], "event_group_evidence_queue")
        result = engine.execute("judge_cross_window_event_review", {
            "prepared_result": prepared["id"], "study_key": previous.subject.scope.PAIR_KEY,
            "run_approval": approval_for(prepared["id"], prepared, frozen, previous.subject.scope.PAIR_KEY),
            "workers": 1, "reuse_cache": True},
            objective="Synthetic recorded native attempt; no provider invocation", actor="test")
    finally:
        engine.close()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(previous.subject, "CANDIDATE", candidate)
        patch.setattr(previous.subject.scope, "PAIR_RESULT", result["id"])
        patch.setattr(previous.subject.ProbeObserver, "_capture", staticmethod(lambda: [previous.previous.compact.process()]))
        engine = previous.subject.ExactLocatorProbe(base["scope_owner"])
        try:
            probed = previous.execute(engine, {"scope_record": base["scope_record"], "scope_artifact": base["scope_artifact"]})
            probe_value = engine.ledger.get(probed["exact_locator_probe_record"], previous.subject.RESULT)
            metadata = engine.ledger.artifacts.read(probe_value["metadata_artifact"])
        finally:
            engine.close()
        proof = subject.NativeReferenceProof(base["scope_owner"])
        try:
            index, _ = proof._index(probe_value)
        finally:
            proof.close()
    events, records = previous.previous.compact.stored_rows(candidate)
    objects = {p.name: p.read_bytes() for p in (candidate / "objects").iterdir() if p.is_file()}
    return {"owner": base["scope_owner"], "candidate": candidate, "native_result": result["id"],
        "prepared_result": prepared["id"], "probe": probed, "metadata": metadata, "index": index,
        "events": events, "records": records, "objects": objects}


@pytest.fixture
def case(tmp_path, template, monkeypatch):
    owner = tmp_path / "observer"
    prepare_root(owner)
    shutil.copytree(template["owner"], owner, dirs_exist_ok=True)
    monkeypatch.setattr(previous.subject, "CANDIDATE", template["candidate"])
    monkeypatch.setattr(previous.subject.scope, "PAIR_RESULT", template["native_result"])
    monkeypatch.setattr(previous.subject.ProbeObserver, "_capture", staticmethod(lambda: [previous.previous.compact.process()]))
    return owner, template, {"probe_record": template["probe"]["exact_locator_probe_record"],
        "probe_artifact": template["probe"]["exact_locator_probe_artifact"]}


def execute(engine, selected, action="prove"):
    return engine.execute("status", {"action": action, **selected}, objective="Synthetic bounded native reference proof", actor="test")


class MemoryReader(subject.NativeReader):
    """Pure compiler fixture over already-captured synthetic native SQL rows."""
    def __init__(self, template):
        self.source = SimpleNamespace(owner=template["candidate"], db=sqlite3.connect(":memory:"),
            head=lambda: template["metadata"]["source_head"])
        self.source.db.row_factory = sqlite3.Row
        for table, rows in (("events", template["events"]), ("records", template["records"])):
            columns = list(rows[0])
            self.source.db.execute(f"CREATE TABLE {table} ({','.join(columns)})")
            self.source.db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in columns)})",
                [tuple(row[k] for k in columns) for row in rows])
        self.record_roster = {r["record_id"]: r for r in template["metadata"]["records"]}
        self.event_roster = {r["seq"]: r for r in template["metadata"]["events"]}
        self.records, self.events, self.copied, self.reasons = {}, {}, {}, {}
        self.bytes, self.objects, self.progress = 0, template["objects"], lambda *_a, **_k: None

    def active(self):
        pass

    def read(self, reference, reason):
        if reference not in self.objects:
            raise subject.Unavailable("native_artifact_absent", reference)
        raw = self.objects[reference]
        assert hashlib.sha256(raw).hexdigest() == reference
        if reference not in self.copied:
            self.copied[reference] = len(raw)
            self.bytes += len(raw)
        self.reasons.setdefault(reference, set()).add(reason)
        return json.loads(raw)


@pytest.fixture
def memory(template, monkeypatch):
    monkeypatch.setattr(previous.subject.scope, "PAIR_RESULT", template["native_result"])
    reader = MemoryReader(template)
    try:
        yield reader, template
    finally:
        reader.source.db.close()


def compile_memory(memory):
    reader, native = memory
    return subject.compile_reference(reader, native["index"], native["native_result"])


def test_native_full_request_actual_dispatch_orphan_aliases_and_cached_status(case, monkeypatch):
    owner, native, selected = case
    before = previous.previous.compact.file_hashes(native["candidate"])
    reads = []
    native_read = previous.subject.SOURCE.Source.artifact_bytes
    def counted(source, reference):
        reads.append(reference)
        return native_read(source, reference)
    monkeypatch.setattr(previous.subject.SOURCE.Source, "artifact_bytes", counted)
    engine = subject.NativeReferenceProof(owner)
    try:
        result = execute(engine, selected)
        assert result["observed_physical_intents"] == result["processed_attempts"] == 1
        assert result["verified_actual_request_dispatches"] == result["native_origin_attempts"] == 1
        assert result["uncompleted_intents"] == 1 and result["gap_counts"] == {}
        assert not result["dispatch_authorized"] and not result["whole_history_complete"] and not result["old_labels_reused"]
        assert result["all_original_gaps_preserved"] and result["new_model_calls"] == 0
        value = engine.ledger.get(result["native_reference_record"], subject.RESULT)
        compiled = engine.ledger.artifacts.read(value["proof_artifact"])
        attempt = compiled["attempts"][0]
        assert attempt["label"] is None and not attempt["current_reference_compatible"]
        assert attempt["joined_events"] == [] and attempt["physical_id"] == digest([str(native["candidate"]), "synthetic-native-orphan"])
        matches = [m for e in attempt["endpoints"] for m in e["final_inputs"]]
        assert all(matches) and set(m["document_id"] for m in matches) <= {r.document_id for r in native["index"].inputs}
        assert any(len(m["article_row_ids"]) == 2 for m in matches)
        assert value["input_index_digest"] == native["index"].digest and len(native["index"].inputs) == 4
        assert value["preserved_authority"]["declared_gap_counts"] == {"manual_review_scope_missing": 1}
        assert len(reads) == len(set(reads)) == result["materialized_artifacts"] > 0
        assert 0 < result["materialized_bytes"] <= subject.MAX_BYTES
        progress = json.loads((owner / "native-reference-progress.json").read_text(encoding="utf-8"))
        assert progress["method"] == subject.METHOD and progress["final_result"] is True and progress["elapsed_seconds"] >= 0
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        assert "PRIVATE BODY" not in json.dumps(result)
        identity = result["native_reference_record"]
    finally:
        engine.close()
    assert previous.previous.compact.file_hashes(native["candidate"]) == before
    monkeypatch.setattr(previous.subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("cached native proof reopened source"))
    monkeypatch.setattr(previous.subject.ProbeObserver, "_capture", staticmethod(lambda: pytest.fail("cached native proof reobserved source")))
    engine = subject.NativeReferenceProof(owner)
    try:
        repeated = execute(engine, selected, "status")
        assert repeated["native_reference_record"] == identity and repeated["reused_completed"]
        assert not repeated["global_quiescence_verified"]
        # Contradict the retained producer input only at the typed read boundary;
        # completed status must reject it without opening the source again.
        creation = engine.ledger.db.execute("SELECT session_id FROM events WHERE seq=?",
            (engine._raw(identity)["created_event"],)).fetchone()[0]
        intended = engine.ledger.db.execute("SELECT payload FROM events WHERE session_id=? AND kind='operation.intended'",
            (creation,)).fetchone()[0]
        input_ref = json.loads(intended)["input"]
        native_read = engine.ledger.artifacts.read
        def wrong_producer_input(reference):
            value = native_read(reference)
            return {**value, "action": "status"} if reference == input_ref else value
        with monkeypatch.context() as patch:
            patch.setattr(engine.ledger.artifacts, "read", wrong_producer_input)
            with pytest.raises(AuditError, match="producer_input"):
                execute(engine, selected, "status")
    finally:
        engine.close()


def test_compiler_preserves_actual_dispatch_not_planning_packet(memory):
    reader, native = memory
    compiled = compile_memory(memory)
    assert compiled["native_graph_verified"] and not compiled["native_scope_complete"]
    row = compiled["attempts"][0]
    assert row["request_and_dispatch_verified"] and not row["gaps"]
    request = next(json.loads(r["payload"]) for r in native["events"] if r["kind"] == "model.attempt.intended")
    prepared = reader.record(native["prepared_result"], "event_group_evidence_result")
    packet = reader.read(prepared["exports"]["packets"]["artifact"], "test planning comparison")[0]
    assert request["dispatch"] != packet["dispatch_ref"]


@pytest.fixture
def wire(tmp_path):
    config = {"codex_executable": "C:/synthetic/codex.exe", "codex_model": "synthetic-native-model",
        "timeout_seconds": 180, "max_input_bytes": 500_000, "max_output_bytes": 2_000_000}
    request, dispatch = request_and_dispatch(tmp_path, {"protocol": digest("synthetic protocol")})
    intent = {"plan": digest("synthetic plan"), "request": digest(request), "dispatch": digest(dispatch),
        "source_versions": [a["source_version"] for a in request["articles"]],
        "pair_id": digest(sorted(a["source_version"] for a in request["articles"]))}
    intent["task_key"] = digest({"plan": intent["plan"], "request": request, "config": config, "method": original.METHOD})
    return request, dispatch, intent, config, tmp_path


@pytest.mark.parametrize("fault", ["extra_request_field", "body_changed", "stdin", "schema", "command", "model", "request_ref", "task_key", "source_order", "boolean_limit"])
def test_exact_native_request_dispatch_contradictions_fail_closed(wire, fault):
    request, dispatch, intent, config, candidate = deepcopy(wire)
    if fault == "extra_request_field":
        request["caller_semantics"] = True
    elif fault == "body_changed":
        request["articles"][0]["body"] = request["articles"][0]["body"].replace("\r\n", "\n")
    elif fault == "stdin":
        dispatch["stdin"] += " "
    elif fault == "schema":
        dispatch["schema"] = {}
    elif fault == "command":
        dispatch["command"] += ["--unexpected"]
    elif fault == "model":
        dispatch["configured_model"] = "different model"
    elif fault == "request_ref":
        intent["request"] = digest("wrong request")
    elif fault == "task_key":
        intent["task_key"] = digest("wrong task")
    elif fault == "source_order":
        intent["source_versions"].reverse()
    else:
        config["timeout_seconds"] = True
        intent["task_key"] = digest({"plan": intent["plan"], "request": request, "config": config, "method": original.METHOD})
    from newsresearch.common import ResearchError
    with pytest.raises((AuditError, ResearchError)):
        subject.prove_request_dispatch(request, dispatch, intent, config, candidate)


def test_full_title_body_identity_preserves_unicode_whitespace_and_copy_origin(wire):
    request, dispatch, intent, config, candidate = wire
    proof = subject.prove_request_dispatch(request, dispatch, intent, config, candidate)
    assert proof["origin_matches_candidate"]
    for row, supplied in zip(proof["endpoints"], request["articles"], strict=True):
        assert row["full_input_identity_verified"]
        assert row["input_sha256"] == digest({"title": supplied["title"], "body": supplied["body"]})
        assert row["title_sha256"] == hashlib.sha256(supplied["title"].encode()).hexdigest()
        assert row["body_sha256"] == hashlib.sha256(supplied["body"].encode()).hexdigest()
        assert "\r\n\r\n" in supplied["body"] and "e\u0301" in supplied["title"]
    copied = subject.prove_request_dispatch(request, dispatch, intent, config, candidate / "copied-owner")
    assert not copied["origin_matches_candidate"] and copied["recorded_origin_owner"] == str(candidate)


def test_missing_title_does_not_become_verified_full_input(wire):
    _, _, intent, config, candidate = deepcopy(wire)
    left, right = article(0), article(1)
    left["title"] = None
    request = build_request(left=left, right=right, versions={"protocol": digest("synthetic protocol")})
    cwd = candidate / "codex-workers" / "codex-judge-missing-title"
    provider = CodexCLIProvider(candidate / "codex-workers", executable=config["codex_executable"], model=config["codex_model"])
    dispatch = PreparedCodexInvocation(provider._command(cwd), cwd, build_prompt(request), request["schema"], request, provider.model).manifest()
    intent.update(request=digest(request), dispatch=digest(dispatch),
        task_key=digest({"plan": intent["plan"], "request": request, "config": config, "method": original.METHOD}))
    proof = subject.prove_request_dispatch(request, dispatch, intent, config, candidate)
    assert proof["endpoints"][0]["full_input_identity_verified"] is False
    assert proof["endpoints"][1]["full_input_identity_verified"] is True


@pytest.mark.parametrize("fault", ["result_versions", "manifest_method", "task_request", "protocol_content"])
def test_native_graph_contradictions_cannot_borrow_valid_request_evidence(memory, monkeypatch, fault):
    reader, _ = memory
    native_record = reader.record
    def altered(identity, kind):
        value = deepcopy(native_record(identity, kind))
        if fault == "result_versions" and kind == subject.RESULT_KIND:
            value["versions"] = {"protocol": digest("wrong version")}
        elif fault == "manifest_method" and kind == subject.MANIFEST_KIND:
            value["binding"]["method"] = "unknown native method"
        elif fault == "task_request" and kind == subject.TASKS_KIND:
            value["items"][0]["request_hash"] = digest("different request")
        elif fault == "protocol_content" and kind == "protocol" and value["content"].get("method") == judging.METHOD:
            value["content"]["config"] = {"changed": True}
        return value
    monkeypatch.setattr(reader, "record", altered)
    with pytest.raises(AuditError):
        compile_memory(memory)


def test_missing_request_artifact_preserves_orphan_with_explicit_gap(memory):
    reader, native = memory
    event = next(json.loads(r["payload"]) for r in native["events"] if r["kind"] == "model.attempt.intended")
    reader.objects = dict(reader.objects)
    del reader.objects[event["request"]]
    result = compile_memory(memory)
    assert result["matched_intents"] == len(result["attempts"]) == 1
    attempt = result["attempts"][0]
    assert not attempt["origin_verified"] and attempt["physical_id"] is None and attempt["label"] is None
    assert attempt["gaps"] == [{"reason": "native_artifact_absent", "reference": event["request"]}]
    assert not result["native_scope_complete"]


def test_native_session_without_exact_operation_prefix_is_rejected(memory):
    reader, native = memory
    event = next(r for r in native["events"] if r["kind"] == "model.attempt.intended")
    reader.source.db.execute("DELETE FROM events WHERE session_id=? AND kind='operation.intended'", (event["session_id"],))
    with pytest.raises(AuditError, match="native_session_prefix"):
        compile_memory(memory)


def test_more_than_36_queue_tasks_is_an_explicit_whole_graph_gap(memory, monkeypatch):
    reader, _ = memory
    native_read = reader.read
    def overfull(reference, reason):
        value = native_read(reference, reason)
        return {**value, "tasks": value["tasks"] * 37} if reason == "native_frozen_queue" else value
    monkeypatch.setattr(reader, "read", overfull)
    result = compile_memory(memory)
    assert result["matched_intents"] == 1 and len(result["attempts"]) == 1
    assert not result["native_graph_verified"] and not result["native_scope_complete"]
    assert {g["reason"] for g in result["gaps"]} == {"crosswindow_binding_limit"}
    assert result["attempts"][0]["physical_id"] is None


def test_over_100_physical_attempts_retains_all_unprocessed_event_identities(memory):
    reader, native = memory
    first = next(r for r in native["events"] if r["kind"] == "model.attempt.intended")
    last_seq = max(r["seq"] for r in native["events"])
    columns = list(first)
    for number in range(100):
        row = dict(first)
        value = json.loads(row["payload"])
        value["attempt"] = f"synthetic-over-cap-{number}"
        row.update(seq=last_seq + number + 1, payload=json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        row["event_hash"] = digest({**{k: v for k, v in row.items() if k != "event_hash"}, "payload": value})
        reader.source.db.execute(f"INSERT INTO events VALUES ({','.join('?' for _ in columns)})", tuple(row[k] for k in columns))
        reader.event_roster[row["seq"]] = {k: row[k] for k in ("seq", "kind", "event_hash")}
    result = compile_memory(memory)
    assert result["matched_intents"] == 101 and result["attempts"] == []
    assert len(set(result["unprocessed_attempt_event_hashes"])) == 101
    assert {g["reason"] for g in result["gaps"]} == {"physical_attempt_limit"}
    assert not result["native_scope_complete"]


@pytest.mark.parametrize("limit", ["single_artifact", "total_transfer"])
def test_artifact_limits_refuse_materialization_without_truncation(tmp_path, limit):
    objects = tmp_path / "objects"
    objects.mkdir()
    reference = digest("synthetic oversized metadata")
    with (objects / reference).open("wb") as stream:
        stream.truncate(subject.MAX_ARTIFACT + 1 if limit == "single_artifact" else 2)
    source = SimpleNamespace(owner=tmp_path, _active=lambda: None,
        artifact_bytes=lambda *_: pytest.fail("over-limit artifact was read"))
    engine = SimpleNamespace(_stop_local=lambda *_: None)
    reader = subject.NativeReader(engine, "synthetic", source, {"records": [], "events": []}, digest("intent"), lambda *_a, **_k: None)
    if limit == "total_transfer":
        reader.bytes = subject.MAX_BYTES
    with pytest.raises(subject.Unavailable) as error:
        reader.read(reference, "synthetic limit")
    assert error.value.reason == "native_artifact_byte_limit" and not reader.copied


def test_copied_native_bytes_do_not_create_verified_independent_origin(memory):
    reader, native = memory
    reader.source.owner = native["candidate"] / "copied-view"
    result = compile_memory(memory)
    attempt = result["attempts"][0]
    assert attempt["request_and_dispatch_verified"] and not attempt["origin_verified"]
    assert attempt["physical_id"] is None and attempt["label"] is None
    assert attempt["gaps"] == [{"reason": "different_recorded_origin_owner", "owner": str(native["candidate"])}]


def test_pure_endpoint_mapping_preserves_every_matching_id_without_certifying_index(memory):
    reader, native = memory
    sha = digest({k: article(0)[k] for k in ("title", "body")})
    matched = next(row for row in native["index"].inputs if row.input_sha256 == sha)
    # This deliberately noncanonical list exercises only mapping losslessness.
    # Actual proof construction still validates the frozen unique-primary index.
    duplicate = replace(matched, document_id="synthetic-additional-matching-id", article_row_ids=("synthetic-alias",))
    input_list = SimpleNamespace(inputs=(*native["index"].inputs, duplicate))
    result = subject.compile_reference(reader, input_list, native["native_result"])
    endpoint = next(e for e in result["attempts"][0]["endpoints"] if e["input_sha256"] == sha)
    assert {row["document_id"] for row in endpoint["final_inputs"]} == {matched.document_id, duplicate.document_id}


@pytest.mark.parametrize("field", ["probe_record", "probe_artifact"])
def test_foreign_probe_binding_fails_before_source(case, monkeypatch, field):
    owner, _, selected = case
    selected[field] = digest("foreign native parent")
    monkeypatch.setattr(previous.subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("foreign parent opened source"))
    engine = subject.NativeReferenceProof(owner)
    try:
        with pytest.raises(AuditError, match="selected_completed_probe"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("missing_endpoint", [False, True])
def test_unsupported_old_code_preserves_exact_inputs_but_not_reference_purpose(memory, monkeypatch, missing_endpoint):
    reader, native = memory
    native_record = reader.record
    def old_code(identity, kind):
        value = deepcopy(native_record(identity, kind))
        if kind == subject.MANIFEST_KIND:
            value["binding"]["implementation"] = {"unknown_old_producer.py": digest("old")}
        return value
    monkeypatch.setattr(reader, "record", old_code)
    index = native["index"]
    if missing_endpoint:
        sha = digest({k: article(0)[k] for k in ("title", "body")})
        index = SimpleNamespace(inputs=tuple(row for row in index.inputs if row.input_sha256 != sha))
    result = subject.compile_reference(reader, index, native["native_result"])
    attempt = result["attempts"][0]
    assert result["matched_intents"] == 1 and not result["native_graph_verified"]
    assert {g["reason"] for g in result["gaps"]} == {"unsupported_historical_producer_code"}
    assert attempt["intended_input_identity_verified"] and len(attempt["endpoints"]) == 2
    assert attempt["role"] == "possible_primary" and not attempt["origin_verified"]
    assert attempt["physical_id"] is None and attempt["label"] is None
    assert all(e["outside_final_frame_proved"] is False for e in attempt["endpoints"])
    if missing_endpoint:
        assert any(not e["final_inputs"] for e in attempt["endpoints"])


@pytest.mark.parametrize("where", ["observer", "candidate"])
def test_stop_is_checked_before_new_source_access(case, monkeypatch, where):
    owner, native, selected = case
    stop = (owner if where == "observer" else native["candidate"]) / "STOP"
    stop.write_text("synthetic stop", encoding="utf-8")
    monkeypatch.setattr(previous.subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("STOP allowed source reopen"))
    engine = subject.NativeReferenceProof(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()
        stop.unlink()


def test_postcommit_failure_is_not_a_completed_native_proof(case, monkeypatch):
    owner, _, selected = case
    engine = subject.NativeReferenceProof(owner)
    native_guard = engine._guard
    def fail_after_result(*args, **kwargs):
        native_guard(*args, **kwargs)
        if engine._rows(subject.RESULT):
            raise AuditError("synthetic native postcommit failure")
    monkeypatch.setattr(engine, "_guard", fail_after_result)
    try:
        with pytest.raises(AuditError, match="synthetic native postcommit"):
            execute(engine, selected)
        assert len(engine._rows(subject.RESULT)) == 1
    finally:
        engine.close()
    monkeypatch.setattr(previous.subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("failed native result reopened source"))
    engine = subject.NativeReferenceProof(owner)
    try:
        with pytest.raises(AuditError, match="producer_not_completed"):
            execute(engine, selected, "status")
    finally:
        engine.close()
