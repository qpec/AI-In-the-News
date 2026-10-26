"""Synthetic representation isolation and audited execution checks, not accuracy."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, ResearchError, digest
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler
from newsresearch import luna_output_matching as cards_api
from newsresearch import luna_representation_comparison as core

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "workbench"))
import luna_event_contract_v2 as contract  # noqa: E402
import run_luna_representation_comparison as adapter  # noqa: E402


def fixture():
    packet, output = contract.fictional_example()
    card = cards_api.make_card(article_id="fictional", corpus="test", published_at="2026-10-01",
        body_sha256=digest("fictional"), variants=[{"assessment": "fictional",
            "raw_status": "valid", "derived_status": "valid", "raw_output": output, "output": output}])
    return card, packet


def test_representation_isolation_and_exact_support():
    card, packet = fixture()
    packet["model_input"]["evidence"]["paragraphs"].append({"id": "p999", "text": "UNREFERENCED_SENTINEL"})
    result = core.views(card, {"fictional": packet})
    assert "UNREFERENCED_SENTINEL" in str(result["article"])
    assert "UNREFERENCED_SENTINEL" not in str(result["luna"])
    assert "UNREFERENCED_SENTINEL" not in str(result["luna_passages"])
    assert result["luna"]["extractions"][0]["output"] == card["records"][0]["output"]
    support = result["luna_passages"]["extractions"][0]["supporting_passages"]
    assert {p["id"] for p in support} == core.referenced_units(card["records"][0]["output"])
    assert core.referenced_units({"refs": ["p1"], "excluded": [{"refs": ["p999"]}]}) == {"p1"}
    requests = [core.request(result[a], result[a]) for a in core.ARMS]
    assert all(r["questions"] == requests[0]["questions"] for r in requests)
    card["records"][0]["output"]["refs"] = ["missing"]
    with pytest.raises(ResearchError, match="unknown_support"):
        core.views(card, {"fictional": packet})
    with pytest.raises(ResearchError, match="wire_byte_cap"):
        core.request({"text": "x" * 65000}, {})


def test_conflicting_source_variants_rejected():
    card, packet = fixture()
    second = deepcopy(card["records"][0])
    second["extraction_id"] = "second"
    card["records"].append(second)
    other = deepcopy(packet)
    other["model_input"]["evidence"]["title"]["text"] = "different"
    with pytest.raises(ResearchError, match="source_variants_disagree"):
        core.views(card, {"fictional": packet, "second": other})


def parsed(label, probability):
    return {"status": "valid", "label": label,
        "probabilities": {v: probability if v == label else (1 - probability) / 2 for v in adapter.transport.LABELS}}


def test_threshold_selection_penalizes_false_and_uncertain_matches():
    rows = [{"reference": r, "decision": parsed("same_event", p)} for r, p in [
        ("same_event", .98), ("different_event", .89), ("insufficient_evidence", .94)]]
    value = core.calibrate(rows)
    assert value["selected"]["threshold"] == .975
    assert value["selected"]["supported_same"] == 1
    assert value["selected"]["false_same"] == value["selected"]["unverifiable_same"] == 0
    assert core.calibrate([{"reference": "different_event", "decision": parsed("same_event", 1)}])["selected"]["threshold"] == 1.01
    assert core.measure(rows, None)["false_same"] == 1


def call(study, action, **kwargs):
    return study.execute("status", {"action": action, **kwargs},
        objective="Synthetic paired representation software verification", actor="pytest:representations")


class SeededStudy(adapter.Study):
    @audited_handler
    def _status(self, session, context, data):
        if data["action"] != "seed":
            return super()._status(session, context, data)
        manifest, references = [], []
        for panel in range(1, 11):
            for a, b in adapter.combinations("ABCD", 2):
                references.append({"panel": panel, "a": a, "b": b, "label": "same_event"})
                for arm in core.ARMS:
                    manifest.append({"pair_id": digest([panel, a, b]), "panel": panel, "a": a, "b": b,
                        "arm": arm, "split": "development" if panel <= 4 else "test",
                        "request": self.ledger.artifacts.put(core.request({"title": "fiction"}, {"title": "fiction"}))})
        self.ledger.record(session, "representation_plan", "fixture", {
            "implementation": adapter.implementation(), "manifest": self.ledger.artifacts.put(manifest),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "reservation_nanousd": adapter.transport.RESERVATION_NANOUSD,
            "maximum_cost_nanousd": adapter.STUDY_BUDGET, "prior_cost_nanousd": 100})
        self.ledger.record(session, "representation_references", "fixture", {"replies": references})
        return {}


def test_audited_split_order_cost_and_unknown_hold(tmp_path, monkeypatch):
    calls = []
    class Fake:
        unknown = False

        def complete_prepared(self, invocation):
            calls.append(invocation)
            if self.unknown:
                return ProviderResponse(None, "openai-decisions", None, raw_response={"unknown_outcome": True})
            payload = {"model": "gpt-6-luna", "answers": [{"type": "choice", "name": "event_identity",
                "choice": "same_event", "confidence": .99, "probabilities": [
                    {"value": v, "probability": .98 if v == "same_event" else .01} for v in adapter.transport.LABELS]}]}
            return ProviderResponse(payload, "openai-decisions", "gpt-6-luna",
                usage={"input_tokens": 1000}, raw_response={"http_status": 200})
    monkeypatch.setattr(adapter.transport, "DecisionsTransport", Fake)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    study = SeededStudy(tmp_path / "study", config=Config(offline=False))
    try:
        call(study, "seed")
        with pytest.raises(AuditError, match="representation_calibration"):
            call(study, "run", split="test", allow_paid_execution=True)
        assert not calls
        result = call(study, "run", split="development", allow_paid_execution=True)
        assert result["stored_responses"] == 72 and result["unresolved_attempts"] == 0
        value = call(study, "calibrate")
        assert all(v["threshold"] == .975 for v in value["selected"].values())
        with pytest.raises(AuditError, match="already_frozen"):
            call(study, "run", split="development", allow_paid_execution=True)
        call(study, "run", split="test", allow_paid_execution=True)
        report = call(study, "report")
        assert len(calls) == 180 and report["completed_api_requests"] == 180
        assert report["cost_usd_with_margin"] == pytest.approx(.0198)
        assert report["splits"]["test"]["arms"]["article"]["raw"]["supported_same"] == 36
        assert report["extraction_cost_usd"] is None
        assert set(report["extraction_break_even_usd_for_40_articles"].values()) == {0}
    finally:
        study.close()
    hold = SeededStudy(tmp_path / "held", config=Config(offline=False))
    try:
        call(hold, "seed")
        Fake.unknown = True
        result = call(hold, "run", split="development", allow_paid_execution=True)
        assert len(calls) == 181 and result["unresolved_attempts"] == 1
        assert hold.rows("representation_decision")[0]["reserved_nanousd"] == 250_000_000
        with pytest.raises(AuditError):
            call(hold, "calibrate")
        with pytest.raises(AuditError, match="already_frozen"):
            call(hold, "run", split="development", allow_paid_execution=True)
        assert len(calls) == 181
    finally:
        hold.close()


class SyntheticParents(Research):
    @audited_handler
    def _status(self, session, context, data):
        if data["part"] == "pilot":
            self.ledger.record(session, "luna_matching_pilot_decision", "fixture",
                {"unknown_or_billing_hold": False, "reserved_nanousd": 0, "cost_nanousd_with_regional_margin": 100})
            return {}
        if data["part"] == "input":
            self.ledger.record(session, "matching15_input", "fixture", {
                "chunks": [self.ledger.artifacts.put(data["cards"])], "excluded_bodies": [],
                "excluded_families": [], "excluded_article_ids": [], "pilot_cards_missing_body_hash": 0})
            self.ledger.record(session, "luna_scalable_panel_plan", "fixture", {"mapping": []})
            return {}
        cards = []
        for corpus in ("first", "second"):
            for family in range(7):
                for member in range(4):
                    name = f"Fictional {corpus} council {family}"
                    body = f"{name} launched a school service. Report {member}.\n\nThe service covers 12 schools."
                    date = "2026-10-01" if member < 3 else "2026-10-30"
                    article = {"title": name + " launches school service", "body": body, "lang": "eng",
                        "dateTimePub": date, "source": {"uri": f"fictional-{member}.example", "title": "Fictional Gazette"}}
                    packet = contract.build_input(article)
                    _, output = contract.fictional_example()
                    output["excluded"] = []
                    output["event"]["participants"] = output["event"]["participants"][:1]
                    output["event"]["participants"][0]["surface"] = name
                    output["event"]["summary"] = name + " launched a school service"
                    output["event"]["facts"] = []
                    identifier = f"{corpus}-{family}-{member}"
                    card = cards_api.make_card(article_id=identifier, corpus=corpus, published_at=date,
                        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
                        variants=[{"assessment": identifier, "raw_status": "valid", "derived_status": "valid",
                            "raw_output": output, "output": output}])
                    card["metadata_variants"] = [packet["model_input"]["context"]]
                    card["provenance"] = [{"owner": str(self.ledger.root), "assessment": identifier,
                        "request": self.ledger.artifacts.put({"packet": packet}), "response": "synthetic-unused"}]
                    cards.append(card)
        return {"cards": cards}


def test_fresh_selection_source_handoff_and_quote_validation(tmp_path):
    parents = {}
    try:
        for name in (adapter.STANDARD, adapter.PARENT, adapter.PILOT):
            parents[name] = SyntheticParents(tmp_path / name, config=Config(offline=True))
        cards = call(parents[adapter.STANDARD], "fixture", part="originals")["cards"]
        call(parents[adapter.PARENT], "fixture", part="input", cards=cards)
        call(parents[adapter.PILOT], "fixture", part="pilot")
    finally:
        for parent in parents.values():
            parent.close()
    study = adapter.Study(tmp_path / "comparison", config=Config(offline=True))
    try:
        plan = call(study, "prepare", base=str(tmp_path))
        assert plan["planned_requests"] == 180 and plan["articles"] == 40
        assert plan["mechanical_panel_exclusions"] == 0
        call(study, "dispatch")
        incomplete = call(study, "read", start=1, end=9)
        assert len(incomplete["panels"]) == 9
        reference_file = study.ledger.root / "synthetic-references.json"
        with pytest.raises(AuditError, match="all_originals_must_be_read"):
            call(study, "submit", input=str(reference_file))
        packet = call(study, "read", start=1, end=10)
        assert all("extractions" not in c and "records" not in c for p in packet["panels"] for c in p["cards"])
        replies = [{"panel": p["panel"], "a": a["side"], "b": b["side"], "label": "same_event",
            "rationale": "Synthetic identical launch used only for software verification.",
            "evidence_a": a["title"], "evidence_b": b["title"]}
            for p in packet["panels"] for a, b in adapter.combinations(p["cards"], 2)]
        wrong = deepcopy(replies)
        wrong[0]["evidence_a"] = "A quote that is absent."
        reference_file.write_text(json.dumps(wrong), encoding="utf-8")
        with pytest.raises(AuditError, match="reference_quote"):
            call(study, "submit", input=str(reference_file))
        reference_file.write_text(json.dumps(replies), encoding="utf-8")
        result = call(study, "submit", input=str(reference_file))
        assert result["pairs"] == 60 and not study.ledger.unresolved
        with pytest.raises(AuditError, match="already_frozen"):
            call(study, "submit", input=str(reference_file))
    finally:
        study.close()
