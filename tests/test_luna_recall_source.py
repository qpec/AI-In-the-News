"""Compact retained-audit import; synthetic owners and fake transport only."""
from copy import deepcopy
from pathlib import Path
import sys
import time
import uuid

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_recall_source as subject
from test_luna_quality_audit import approved, answer, execute, install_network
from test_luna_quality_design import source_fixture
from test_final_validation_study import process
from test_final_validation_inventory import bytes_snapshot


class NativeMain(Research):
    @audited_handler
    def _status(self, session, context, data):
        source = data["source"]
        plan = self.ledger.record(session, "cyber_dossier_plan", "synthetic", {"synthetic": True})
        docs = [{"document_id": i, **d} for i, d in source["documents"].items()][:2]
        members = [d["document_id"] for d in docs]
        revision = digest(sorted(members))
        self.ledger.record(session, "cyber_dossier_evidence_card", "g", {"dossier_id": "g", "document_ids": members,
            "membership_revision": revision, "artifact": self.ledger.artifacts.put({"not_read": "old card text"})})
        packet = subject.base.seed_request(docs, count_tokens=lambda _: 100)
        parsed = subject.base.parse_decisions(packet, answer(packet["request"]))
        reference = deepcopy(parsed)
        reference["reference_model"] = "gpt-6-astra"
        for row in reference["answers"].values():
            row["probabilities"] = None
        qa_packet = {"phase": "card_quality", "document_ids": members, "bindings": {"dossier_id": "g", "membership_revision": revision},
            "request": {"synthetic": "qa"}}
        for phase, payload, result in (("seed", packet, parsed), ("audit", packet, reference),
                ("card_quality", qa_packet, {"status": "valid", "label": "incoherent_group", "dossier_id": "g", "membership_revision": revision}),
                ("summary", qa_packet, None)):
            attempt = str(uuid.uuid4())
            packet_ref, request = self.ledger.artifacts.put(payload), self.ledger.artifacts.put(payload["request"])
            key = digest([phase, packet_ref])
            self.ledger.append(session, "model.attempt.intended", {"attempt": attempt, "task_key": key, "number": 1,
                "batch": plan, "phase": phase, "packet": packet_ref, "request": request})
            if result is not None:
                self.ledger.record(session, "cyber_dossier_response", key, {"plan": plan, "attempt": attempt,
                    "task_key": key, "phase": phase, "packet": packet_ref, "request": request,
                    "response": self.ledger.artifacts.put({"synthetic": phase}), "parsed": self.ledger.artifacts.put(result), "hold": False})
        for name in subject.PHASES:
            value = {"unresolved": {"d002": "multiple_positive_targets"}, "packet_coverage": {"d003": {"coverage_complete": False}}} if name.endswith("assignments") else {}
            self.ledger.record(session, "cyber_dossier_phase", name, {"plan": plan, "name": name, "artifact": self.ledger.artifacts.put(value)})
        report = {"plan": plan, "pipeline_finished": True}
        return {"record": self.ledger.record(session, "cyber_dossier_report", "final", report), "artifact": digest(report)}


class Consumer(Research):
    imported = None
    deadline_delta = 1200

    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(), "binding": data["binding"]}})
        self.imported = subject.collect(self, session, **data, deadline_monotonic=time.monotonic() + self.deadline_delta)
        return {"artifact": self.ledger.artifacts.put(self.imported), "threshold_validated": self.imported["precheck"]["threshold_validated"]}


@pytest.fixture(scope="module")
def retained(tmp_path_factory):
    root = tmp_path_factory.mktemp("recall-source")
    patch = pytest.MonkeyPatch()
    patch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    patch.setattr(subject.frozen.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    source = source_fixture(4, groups={"g": ["d000", "d001"], "s2": ["d002"], "s3": ["d003"]})
    native = NativeMain(root / "source", config=Config(offline=True))
    try:
        final = native.execute("status", {"source": source}, objective="Synthetic native history", actor="test")
        head = list(native.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        native.close()
    data = approved(root)
    data["binding"].update(source_head=head, report_record=final["record"], report_artifact=final["artifact"])
    source["provenance"] = {"method": subject.frozen.METHOD, "implementation": subject.frozen.implementation(),
        "binding": data["binding"], "source_head": head, "source_owner": data["source_owner"], "snapshot_owner": data["snapshot_owner"],
        "source_heads_stable_during_copy": True, "source_quiescence_verified_during_copy": True}
    patch.setattr(subject.frozen, "load_frozen", lambda *args, **kwargs: deepcopy(source))
    auditor = subject.audit.Audit(root / subject.audit.OWNER_NAME)
    try:
        execute(auditor, "prepare", **data)
        install_network(patch, auditor)
        report = execute(auditor, "run", allow_paid_execution=True)
        plan = auditor.one(subject.audit.PLAN)
        binding = {"audit_plan_record": plan["id"], "audit_report_record": report["id"]}
        plan_artifact = auditor.ledger.db.execute("SELECT artifact FROM records WHERE id=?", (plan["id"],)).fetchone()[0]
        report_artifact = auditor.ledger.db.execute("SELECT artifact FROM records WHERE id=?", (report["id"],)).fetchone()[0]
    finally:
        auditor.close()
    yield {"audit_owner": str(root / subject.audit.OWNER_NAME), "binding": binding}, source, (plan_artifact, report_artifact)
    patch.undo()


def consume(tmp_path, data):
    engine = Consumer(tmp_path / "consumer", config=Config(offline=True))
    try:
        out = engine.execute("status", data, objective="Synthetic retained import", actor="test")
        return out, engine.imported
    finally:
        engine.close()


def test_real_completed_audit_import_native_history_no_source_rescan(tmp_path, retained, monkeypatch):
    data, original, refs = retained
    owners = [Path(data["audit_owner"]), Path(original["provenance"]["source_owner"])]
    before = [bytes_snapshot(p) for p in owners]
    calls, readers, updates = {}, [], []
    read = subject.frozen.source_api.Source.artifact_bytes
    init = subject.Reader.__init__
    def copied(self, ref):
        key = str(self.owner), ref
        calls[key] = calls.get(key, 0) + 1
        return read(self, ref)
    def construct(self, *args, **kwargs):
        init(self, *args, **kwargs)
        readers.append(self)
        with pytest.raises(AuditError):
            Research(self.owner, config=Config(offline=True))
    monkeypatch.setattr(subject.Reader, "__init__", construct)
    monkeypatch.setattr(subject.frozen.source_api.Source, "artifact_bytes", copied)
    monkeypatch.setattr(Consumer, "source_progress", lambda self, status: updates.append(status), raising=False)
    monkeypatch.setattr(subject.frozen, "load_frozen", lambda *a, **k: pytest.fail("old source collection repeated"))
    out, loaded = consume(tmp_path, data)
    assert out["threshold_validated"] is False
    assert loaded["documents"] == original["documents"] and loaded["candidate_manifest"] == original["candidate_manifest"]
    assert loaded["audit"]["commitment_nanousd"] > 0 and loaded["audit"]["labels"]
    assert len(loaded["prior_history"]["membership_attempts"]) == 2
    assert {r["label"] for r in loaded["prior_history"]["membership_attempts"]} == {"incoherent_group", None}
    assert any(r["hold"] for r in loaded["prior_history"]["membership_attempts"])
    card = loaded["prior_history"]["cards"]["g"][0]
    assert card["document_ids"] == ["d000", "d001"] and card["membership_revision"] == digest(card["document_ids"])
    assert len(card["record"]) == len(card["artifact"]) == 64
    assert all(card["artifact"] not in r.copied for r in readers)  # reference only, no old card body read
    assert loaded["precheck"]["matched_observations"] >= 1
    assert loaded["precheck"]["clarity_diagnostic"]["matched_observations"] >= 2
    assert loaded["diagnostic"]["recorded_reason_counts"]["multiple_positive_targets"] == 2
    assert all(n == 1 for n in calls.values())
    assert all(r.closed and not r.cache and not r.decoded for r in readers)
    for reader in readers:
        with pytest.raises(AuditError):
            reader.artifact(next(iter(reader.copied)))
    assert updates[0]["stage"] == "recall_import_audit_metadata" and updates[-1]["stage"] == "recall_import_complete"
    assert any(u.get("processed_units") for u in updates)
    assert before == [bytes_snapshot(p) for p in owners]
    assert loaded["recall_provenance"]["current_quiescence_verified"] is False
    assert loaded["audit"]["plan_artifact"] == refs[0] and loaded["audit"]["report_artifact"] == refs[1]


@pytest.mark.parametrize("field", ["audit_plan_record", "audit_report_record", "audit_plan_artifact", "audit_report_artifact", "unknown"])
def test_exact_binding_rejects_foreign_and_unrecognized(tmp_path, retained, field):
    data = deepcopy(retained[0])
    data["binding"][field] = "a" * 64
    with pytest.raises(AuditError):
        consume(tmp_path, data)


def test_source_writer_exclusion(tmp_path, retained):
    writer = Research(Path(retained[0]["audit_owner"]), config=Config(offline=True))
    try:
        with pytest.raises(AuditError):
            consume(tmp_path, retained[0])
    finally:
        writer.close()


def test_new_stop_and_deadline_before_source(tmp_path, retained, monkeypatch):
    monkeypatch.setattr(subject, "Reader", lambda *a, **k: pytest.fail("source opened"))
    engine = Consumer(tmp_path / "consumer")
    try:
        engine.deadline_delta = -1
        with pytest.raises(AuditError, match="deadline"):
            engine.execute("status", retained[0], objective="Synthetic deadline", actor="test")
        engine.deadline_delta = 1200
        (engine.ledger.root / "STOP").write_text("synthetic stop")
        with pytest.raises(AuditError, match="stop"):
            engine.execute("status", retained[0], objective="Synthetic stop", actor="test")
    finally:
        engine.close()


def observations():
    packet = subject.base.seed_request([{"document_id": i, **d} for i, d in source_fixture(2, groups={"g": ["d000", "d001"]})["documents"].items()], count_tokens=lambda _: 100)
    parsed = subject.base.parse_decisions(packet, answer(packet["request"], probability=.8))
    docs = source_fixture(2, groups={"g": ["d000", "d001"]})["documents"]
    rows, clarity = subject.normalize_pairs(packet, parsed, docs, role="development_audit", attempt="luna", task_key="luna", refs={"parsed": "1"*64}, usable=True)
    reference = deepcopy(parsed)
    reference["reference_model"] = "gpt-6-astra"
    for a in reference["answers"].values():
        a["probabilities"] = None
    refs, clear_refs = subject.normalize_pairs(packet, reference, docs, role="independent_astra", attempt="astra", task_key="astra", refs={"parsed": "2"*64}, usable=True)
    return {"audit": {"pair_observations": rows, "clarity": clarity}, "prior_history": {"pair_observations": refs, "clarity_observations": clear_refs}}


def test_precheck_separate_threshold_axes_and_exact_identity_manifest():
    source = observations()
    for c in source["audit"]["pair_observations"][0]["clarity"]:
        c["probabilities"] = {k: .95 if k == "clear_single_event" else .05/3 for k in subject.base.CLARITY_LABELS}
    result = subject.precheck(source)
    assert len(result["grid"]) == 12 and result["selected_threshold"] == .85 and not result["threshold_validated"]
    pair = {r["threshold"]: r for r in result["grid"] if r["axis"] == "pair"}
    assert pair[.75]["confusion"] == {"same_event__same_event": 1}
    assert pair[.85]["confusion"] == {"same_event__unknown": 1}
    assert pair[.85]["conditional_precision"] is None
    assert result["matched_manifest"][0]["reference"]["physical_attempt"] == "astra"


@pytest.mark.parametrize("field", ["input_sha256", "rubric_sha256", "representation"])
def test_mismatched_reference_is_not_calibration(field):
    source = observations()
    source["prior_history"]["pair_observations"][0][field] = "mismatch"
    result = subject.precheck(source)
    assert result["matched_observations"] == 0
    assert result["unmatched_manifest"][0]["reference"]["physical_attempt"] == "astra"
    assert result["unmatched"]["source_rubric_or_representation_mismatch"] == 1


def test_clarity_diagnostic_includes_negative_and_unknown_article_refs():
    source = observations()
    references = source["prior_history"]["clarity_observations"]
    references[0]["label"] = "multiple_focal_events"
    references[1]["label"] = "insufficient_information"
    result = subject.precheck(source)["clarity_diagnostic"]
    assert result["negative_reference_coverage"]
    assert {r["reference_label"] for r in result["matched_manifest"]} == {"not_clear", "unknown"}
    assert result["grid"][0]["reference_negative_denominator"] == 1
    assert result["grid"][0]["reference_positive_sensitivity"] is None


def test_contradictory_repeated_references_and_missing_distributions_explicit():
    source = observations()
    other = deepcopy(source["prior_history"]["pair_observations"][0])
    other.update(label="different_event", physical_attempt="astra2")
    source["prior_history"]["pair_observations"].append(other)
    source["audit"]["pair_observations"][0]["probabilities"]["same_event"] = float("nan")
    result = subject.precheck(source)
    assert result["matched_observations"] == 2 and result["matched_unique_pairs"] == 1 and result["conflicting_reference_pairs"] == 1
    assert not result["selection_supported"] and len(result["matched_manifest"]) == 2


def test_diagnosis_preserves_unattributed_and_does_not_claim_causation():
    source = source_fixture(3, groups={"g": ["d000"], "h": ["d001"], "i": ["d002"]})
    key = digest(["d000", "d001"])
    source["audit"] = {"labels": {key: "same_event"}, "source_pairs": {key: ["d000", "d001"]}}
    source["prior_history"] = {"native_phases": {}, "gaps": [{"reason": "missing_phase"}]}
    result = subject.diagnose(source)
    assert result["unattributed_misses"] == 1 and result["causal_attribution_claimed"] is False
    assert result["trace_gaps"] == source["prior_history"]["gaps"]


def test_native_seed_preserves_scores_without_inventing_negative_routing():
    docs = source_fixture(2, groups={"g": ["d000", "d001"]})["documents"]
    packet = subject.focal.seed_request([{"document_id": i, **d} for i, d in docs.items()], count_tokens=lambda _: 100)
    parsed = subject.base.parse_decisions(packet, answer(packet["request"], pair="different_event"))
    rows, _ = subject.normalize_pairs(packet, parsed, docs, role="native_seed", attempt="old", task_key="old", refs={}, usable=True)
    assert rows[0]["compatible_focal_rubric"] and rows[0]["probabilities"]["different_event"] == .95
    assert rows[0]["negative_rule"] == "not_classified_by_seed_partition"
    assert subject._prediction(rows[0], .85, .85) == ("unknown", "native_seed_nonpositive_not_classified")
