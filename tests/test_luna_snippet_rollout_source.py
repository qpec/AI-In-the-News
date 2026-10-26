"""Compact completed native pilot and selected retained evidence only."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from itertools import combinations
import json
from pathlib import Path
import sys
import uuid

import pytest

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_rollout_source as subject
import test_luna_recall_run as recall_tests
from test_final_validation_inventory import bytes_snapshot
from test_final_validation_study import process
from test_luna_snippet_run import execute, network, response

pilot = subject.pilot


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    # Genuine predecessor operations, with no inherited fixed crash-packet
    # injection: the pilot fixture below owns those cases with untouched IDs.
    patch = pytest.MonkeyPatch()
    run = subject.base.recall
    patch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    patch.setattr(run, "RPM", 10**9)
    patch.setattr(run, "TPM", 10**9)
    patch.setattr(subject.retained.frozen.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    root = tmp_path_factory.mktemp("rollout-prior")
    engine = run.Recall(root/run.OWNER_NAME)
    value = recall_tests.source()
    value["prior_history"]["membership_attempts"] = [{"document_ids": ["d000", "d003"],
        "membership_revision": digest(["d000", "d003"]), "phase": "card_quality", "hold": True,
        "usable": False, "physical_attempt": "synthetic-baseline-held"}]
    value["prior_history"]["gaps"] = [{"reason": "synthetic_retained_unknown"}]
    data = {"audit_owner": str(root/"never-open-audit"),
        "binding": {"audit_plan_record": "1"*64, "audit_report_record": "2"*64},
        "seed": "synthetic-snippet-native-recall",
        "approval": {**run.APPROVAL, "method_sha256": hashlib.sha256(run.SPEC.read_bytes()).hexdigest()}}
    value["recall_provenance"] = {"method": run.source_module.METHOD,
        "implementation": run.source_module.implementation(), "binding": data["binding"],
        "audit_owner": str(Path(data["audit_owner"]).resolve()), "source_heads_stable_during_copy": True}
    patch.setattr(run.source_module, "collect", lambda *a, **k: deepcopy(value))
    def change(item, number, wire):
        articles = json.loads(wire["input"]).get("articles", [])
        if len(articles) >= 4 and any(q["name"].startswith("membership_") for q in wire.get("questions", [])):
            for answer in item.payload["answers"]:
                if answer["name"].startswith("membership_"):
                    answer["choice"] = "different_event"
                    for p in answer["probabilities"]:
                        p["probability"] = .95 if p["value"] == "different_event" else .05/3
        return item
    try:
        recall_tests.execute(engine, "prepare", **data)
        recall_tests.network(patch, engine, change)
        report = recall_tests.execute(engine, "run", allow_paid_execution=True)
        plan, freeze = engine.one(run.PLAN), engine.one(run.FREEZE)
    finally:
        engine.close()
    owner = root/run.OWNER_NAME
    (owner/"STOP").write_text("Historical predecessor stop", encoding="utf-8")
    for key, val in {"OWNER": owner, "PLAN": plan["id"], "REPORT": report["id"],
            "FREEZE": freeze["id"], "SUCCESSOR": report["successor_artifact"],
            "PRIOR_COMMITMENT": report["committed_including_prior_nanousd"]}.items():
        patch.setattr(subject.base, key, val)
    patch.setattr(run.source_module, "collect", lambda *a, **k: pytest.fail("original historical sources reopened"))
    yield {"owner": owner, "source": value, "plan": plan, "report": report}
    patch.undo()


@pytest.fixture(scope="module")
def completed_pilot(native, tmp_path_factory):
    patch = pytest.MonkeyPatch()
    for key in ("OWNER", "PLAN", "REPORT", "FREEZE", "SUCCESSOR", "PRIOR_COMMITMENT"):
        patch.setattr(subject.bounded, key, getattr(subject.base, key))
    patch.setattr(subject.bounded.previous, "PRIOR_COMMITMENT", subject.bounded.PRIOR_COMMITMENT)
    patch.setattr(pilot, "PRIOR_COMMITMENT", subject.bounded.PRIOR_COMMITMENT)
    patch.setattr(pilot, "POLICY", {**pilot.POLICY, "prior_commitment_nanousd": pilot.PRIOR_COMMITMENT})
    patch.setattr(pilot, "RPM", 10**9)
    patch.setattr(pilot, "TPM", 10**9)
    root = tmp_path_factory.mktemp("rollout-source") / pilot.OWNER_NAME
    engine = pilot.Pilot(root)
    extra = {}
    try:
        execute(engine, "prepare")
        plan, imported, selection = engine.load_plan()
        calls = network(patch, engine)
        original = engine.qa
        def qa(session, plan, value, name, proposals, supported, attempted):
            rejected = original(session, plan, value, name, proposals, supported, attempted)
            if name != "fallback":
                return rejected
            used = set(imported["history"]["membership_attempts"]) | {
                p["membership_revision"] for p in engine._state["packets"].values() if "membership_revision" in p}
            choices = [list(pair) for n in (2, 3, 4) for pair in combinations(sorted(value["source"]["documents"]), n)
                if digest(list(pair)) not in used][:3]
            assert len(choices) == 3
            encoder = pilot.offline_tokenizer()
            packets = [pilot.contract.member_packet(value["source"], pair,
                lambda text: len(encoder.encode(text, disallowed_special=()))) for pair in choices]
            q = engine.queue(session, plan, "synthetic-retained-outcomes", packets)
            for mode, packet, members in zip(("held", "orphan", "negative"), packets, choices):
                extra[mode] = members
                attempt = str(uuid.uuid4())
                intent = {"method": pilot.METHOD, "attempt": attempt, "task_key": packet["task_key"], "number": 1,
                    "batch": plan["id"], "queue": q["id"], "category": "pilot", "started_at": utc(),
                    "packet": engine.ledger.artifacts.put(packet), "request": engine.ledger.artifacts.put(packet["request"]),
                    "dispatch": engine.ledger.artifacts.put(pilot.wire.Invocation(packet["request"], attempt).manifest()),
                    "reserved_nanousd": packet["reservation_nanousd"]}
                engine.ledger.append(session, "model.attempt.intended", intent)
                engine.ledger.unresolved[attempt] = intent
                if mode == "orphan":
                    continue
                payload = response(packet["request"])
                if mode == "negative":
                    for answer in payload["answers"]:
                        if answer["name"].startswith("membership_"):
                            answer["choice"] = "different_event"
                            for p in answer["probabilities"]:
                                p["probability"] = .95 if p["value"] == "different_event" else .05/3
                    returned = ProviderResponse(payload, "synthetic", "gpt-6-luna", usage={"input_tokens": 100}, raw_response={"http_status": 200})
                else:
                    returned = ProviderResponse(None, "synthetic", "gpt-6-luna", raw_response={"http_status": 400, "unknown_outcome": True})
                ref = engine.ledger.artifacts.put(asdict(returned))
                engine.ledger.append(session, "luna_snippet.response.received", {"attempt": attempt, "response": ref})
                derived, parsed = pilot.outcome(packet, returned)
                record = engine.ledger.record(session, pilot.RESPONSE, attempt,
                    {"plan": plan["id"], "attempt": attempt, "task_key": packet["task_key"], "response": ref,
                        "parsed": engine.ledger.artifacts.put(parsed) if parsed is not None else None, **derived})
                if mode == "negative":
                    assert derived["usable"] and not derived["members_supported"] and not derived["hold"]
                    engine.complete(session, intent, ref, record, "valid")
            return rejected
        patch.setattr(engine, "qa", qa)
        report = execute(engine, "run", allow_paid_execution=True)
        assert report["unknown_holds"] == 2 and len(calls) > 0
    finally:
        engine.close()
    for key, val in {"OWNER": root, "PLAN": plan["id"], "REPORT": report["id"],
            "SUCCESSOR": report["successor_artifact"], "PRIOR_COMMITMENT": report["combined_commitment_nanousd"]}.items():
        patch.setattr(subject, key, val)
    (root/"STOP").write_text("Historical pilot stop", encoding="utf-8")
    yield {"owner": root, "plan": plan, "report": report, "imported": imported, "selection": selection, **extra}
    patch.undo()


class Consumer(Research):
    imported = None
    def source_progress(self, value):
        self.progress.append(value)
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(), "policy": subject.POLICY}})
        self.imported = subject.collect(self, session)
        return {"artifact": self.ledger.artifacts.put(self.imported)}


def consume(tmp_path):
    engine = Consumer(tmp_path / "consumer", config=Config(offline=True))
    engine.progress = []
    return engine


def test_completed_pilot_import_preserves_baseline_cost_history_and_question_ids(tmp_path, completed_pilot, monkeypatch):
    value = completed_pilot
    before = bytes_snapshot(value["owner"])
    source = subject.retained.frozen.source_api.Source
    original_init = source.__init__
    opened = []
    def init(self, engine, session, owner):
        opened.append(owner)
        assert owner == value["owner"]
        original_init(self, engine, session, owner)
    monkeypatch.setattr(source, "__init__", init)
    engine = consume(tmp_path)
    try:
        execute(engine, "status")
        got = engine.imported
        history = got["history"]
        assert got["source"] == value["imported"]["source"]
        assert digest(got["state"]) == subject.SUCCESSOR
        assert got["source"]["groups"] == value["imported"]["source"]["groups"]
        assert got["prior_commitment_nanousd"] == value["report"]["combined_commitment_nanousd"]
        assert history["pilot_unknown_holds"] == 2
        assert history["pilot_held_nanousd"] == value["report"]["new_held_nanousd"]
        assert history["pilot_settled_nanousd"] == value["report"]["new_settled_nanousd"]
        assert history["pair_observations"] == value["imported"]["history"]["pair_observations"]
        assert history["gaps"] == value["imported"]["history"]["gaps"] and not history["global_history_complete"]
        for mode in ("held", "orphan", "negative"):
            assert history["membership_attempts"][digest(value[mode])]["blocked"]
        assert history["membership_attempts"][digest(value["orphan"])]["member_result_ref"] is None
        assert any(m["member_supported"] and m["card_supported"] and not m["blocked"] for m in history["membership_attempts"].values())
        prior_ids = {f["physical_attempt"] for f in value["imported"]["history"]["physical_attempts"]}
        all_ids = {f["physical_attempt"] for f in history["physical_attempts"]}
        assert prior_ids < all_ids and len(all_ids-prior_ids) == value["report"]["attempted_requests"]
        assert history["proposal_questions"] and history["logical_ids"]
        for packet in value["selection"]["packets"]:
            assert set(packet["article_ids"]) <= set(history["development_exposed_documents"])
            for name in packet["question_map"]:
                assert subject.question_identity(packet, name) in history["proposal_questions"]
        assert history["prior_final_reference_logical_ids"]
        assert history["original_validation_seed"] == "synthetic-snippet-native-recall"
        assert len(opened) == 1 and before == bytes_snapshot(value["owner"])
        assert engine.progress[-1]["stage"] == "rollout_source_complete"
        manifest = engine.ledger.artifacts.read(got["provenance"]["size_manifest_artifact"])
        allowed = {r["reference"]: r["bytes"] for r in manifest["entries"]}
        assert len(allowed) == manifest["distinct_references"]
        assert sum(allowed.values()) == manifest["total_distinct_bytes"] <= 3*1024**3
        assert all(size == allowed[ref] for ref, size in got["provenance"]["copied_artifacts"].items())
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["foreign_report", "cost", "import_binding", "packet", "response", "head", "limit", "stop"])
def test_selected_graph_guards_fail_closed(tmp_path, completed_pilot, monkeypatch, fault):
    old = subject.Reader
    class Altered(old):
        def artifact_size(self, ref):
            if fault == "limit" and ref == completed_pilot["plan"]["import_artifact"]:
                return 3*1024**3+1
            return super().artifact_size(ref)
        def artifact(self, ref):
            assert fault != "limit" or ref != completed_pilot["plan"]["import_artifact"], "large payload read before rejected preflight"
            v = super().artifact(ref)
            if fault == "import_binding" and ref == completed_pilot["plan"]["import_artifact"]:
                v["provenance"]["report_record"] = "f"*64
            if fault == "packet" and isinstance(v, dict) and v.get("role") == "group_membership":
                v["request_sha256"] = "f"*64
            if fault == "response" and isinstance(v, dict) and "raw_response" in v:
                v["usage"] = {"input_tokens": 999999}
            return v
        def head(self, fresh=False):
            return [1, "f"*64] if fresh and fault == "head" else super().head(fresh=fresh)
    monkeypatch.setattr(subject, "Reader", Altered)
    if fault == "foreign_report":
        monkeypatch.setattr(subject, "REPORT", "f"*64)
    if fault == "cost":
        monkeypatch.setattr(subject, "PRIOR_COMMITMENT", subject.PRIOR_COMMITMENT+1)
    engine = consume(tmp_path)
    if fault == "stop":
        (engine.ledger.root/"STOP").write_text("new operation stop", encoding="utf-8")
    try:
        with pytest.raises(AuditError):
            execute(engine, "status")
        assert engine.imported is None
    finally:
        engine.close()


def test_normalized_question_is_shared_with_grouping_and_not_a_pair_label(completed_pilot):
    assert subject.question_identity is subject.rollout_grouping.normalized_question_identity
    packet = deepcopy(completed_pilot["selection"]["packets"][0])
    name = next(iter(packet["question_map"]))
    identity = subject.question_identity(packet, name)
    packet["question_map"]["renamed"] = packet["question_map"].pop(name)
    for targets in packet["menus"].values():
        targets.reverse()
    assert subject.question_identity(packet, "renamed") == identity
    assert subject.POLICY["proposal_choices_are_reference_labels"] is False
