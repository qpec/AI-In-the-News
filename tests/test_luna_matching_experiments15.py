"""Structural guards and one audited synthetic end-to-end 15-method study."""
from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler
from newsresearch import luna_output_matching as cards_api
from newsresearch import luna_scalable_matching as base
from newsresearch import luna_matching_experiments15 as core

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "workbench"))
import luna_event_contract_v2 as contract  # noqa: E402
import run_luna_matching_experiments15 as adapter  # noqa: E402
import report_luna_matching_experiments15 as diagnosis  # noqa: E402


def card(corpus, family, member):
    _, output = contract.fictional_example()
    name = f"{corpus} family{family} labs"
    action = "launched specialized service" if member < 3 else "filed separate lawsuit"
    output["event"]["summary"] = f"{name} {action} version fortytwo"
    output["event"]["action"]["surface"] = action
    output["event"]["participants"] = output["event"]["participants"][:1]
    output["event"]["participants"][0].update({"surface": name, "kind": "organization", "named": True,
        "roles": [{"role": "initiator", "refs": ["p1"]}]})
    output["event"]["facts"] = []
    identifier = f"{corpus}-{family:03d}-{member}"
    value = cards_api.make_card(article_id=identifier, corpus=corpus, body_sha256=digest(identifier),
        published_at="2026-10-01" if member < 3 else "2026-10-30",
        variants=[{"assessment": identifier, "raw_status": "valid", "derived_status": "valid", "raw_output": output, "output": output}])
    value["metadata_variants"] = [{"publisher": {"uri": f"publisher-{member}.example"}}]
    return value


def test_role_guards_and_deterministic_name_number_features():
    a, b = card("test", 1, 0), card("test", 1, 1)
    for c, actor, place in ((a, "West Veterinary Centre", "Westtown"), (b, "East Veterinary Centre", "Easttown")):
        event = c["records"][0]["output"]["event"]
        event["summary"] = f"{actor} launched the Shared Plan for local customers"
        event["participants"][0]["surface"] = actor
        event["participants"] += [
            {"id": "e9", "surface": "Shared Plan", "kind": "product", "named": True, "roles": [{"role": "subject", "refs": ["p1"]}], "refs": ["p1"]},
            {"id": "e8", "surface": place, "kind": "place", "named": True, "roles": [{"role": "event_place", "refs": ["p1"]}], "refs": ["p1"]}]
    p = core.rich_pair(core.enrich(a), core.enrich(b), {})
    assert p["initiator_conflict"] and p["place_conflict"] and p["clean_shared_names"] == 1
    for method in ("E01", "E02", "E03", "E10", "E15"):
        assert core.score(method, p, {"constant": .99}) < 0
    assert core.alias_forms("Example Agency (EXA)") == {"example agency exa", "example agency", "exa"}
    assert core.alias_forms("the report") == frozenset()
    c = deepcopy(a)
    c["article_id"] = "other"
    c["published_at"] = None
    assert core.score("E04", core.rich_pair(core.enrich(a), core.enrich(c), {})) < 0


def call(engine, action, **kwargs):
    return engine.execute("status", {"action": action, **kwargs}, objective="Synthetic fifteen-method software verification", actor="pytest:fifteen")


class Parent(Research):
    @audited_handler
    def _status(self, session, context, data):
        if data["pilot"]:
            return {"id": self.ledger.record(session, "luna_matching_pilot_plan", "fixture", {"cards": self.ledger.artifacts.put([{"corpus": "first", "body_sha256": None, "article_id": "missing-hash"}])})}
        cards = [card(c, family, member) for c in ("first", "second") for family in range(24) for member in range(4)]
        self.ledger.record(session, "luna_scalable_input", "fixture", {"chunks": [self.ledger.artifacts.put(cards)]})
        index = base.Index((base.features(c) for c in cards), base.Settings(minimum_score=.05))
        path = self.ledger.root / "candidates.sqlite3"
        base.write_candidates(index, path)
        self.ledger.record(session, "luna_scalable_retrieval", "fixture", {"candidate_artifact": self.ledger.artifacts.put_file(path)})
        mapping, replies = [], []
        families = range(6) if data["old"] else range(6, 9)
        for corpus in ("first", "second"):
            for family in families:
                panel = len(mapping) + 1
                mapping.append({"panel": panel, "split": "development", "corpus": corpus,
                    "family_key": f"{corpus} family{family} labs", "cards": {s: f"{corpus}-{family:03d}-{i}" for i, s in enumerate("ABCD")}})
                for a, b in combinations("ABCD", 2):
                    replies.append({"panel": panel, "a": a, "b": b, "label": "same_event" if b != "D" else "different_event"})
        self.ledger.record(session, "luna_scalable_panel_plan", "fixture", {"mapping": mapping})
        self.ledger.record(session, "luna_scalable_panel_references", "fixture", {"replies": replies})
        return {"cards": len(cards)}


def test_fifteen_full_audited_workflow_and_holdout_freeze(tmp_path, monkeypatch):
    for name, pilot, old in (("luna-matching-pilot-20261020-v1", True, False),
        ("luna-scalable-experiment-20261020-v1", False, True), ("luna-scalable-experiment-20261020-v3", False, False)):
        parent = Parent(tmp_path / name, config=Config(offline=True))
        try:
            call(parent, "fixture", pilot=pilot, old=old)
        finally:
            parent.close()
    study = adapter.Study(tmp_path / "study", config=Config(offline=True))
    try:
        prepared = call(study, "prepare", base=str(tmp_path))
        assert prepared["ready_articles"] == 192
        assert prepared["development_pairs_count"] == 108
        with pytest.raises(AuditError, match="one_matching15_development"):
            call(study, "dispatch")
        original = adapter.implementation
        monkeypatch.setattr(adapter, "implementation", lambda: {"changed": "yes"})
        with pytest.raises(AuditError, match="implementation_changed"):
            call(study, "develop")
        monkeypatch.setattr(adapter, "implementation", original)
        developed = call(study, "develop")
        assert len(developed["experiments"]) == 15
        assert developed["selected_experiment"] == "E01"
        with pytest.raises(AuditError, match="already_frozen"):
            call(study, "develop")
        panels = call(study, "panels")
        assert panels["panels"] == 12
        frozen = study.one("matching15_input")
        assert frozen["excluded_body_keys_missing_hash"] == 1
        plan = study.one("luna_scalable_panel_plan")
        assert not set(tuple(f) for f in frozen["excluded_families"]) & {(m["corpus"], m["family_key"]) for m in plan["mapping"]}
        call(study, "dispatch")
        with pytest.raises(AuditError, match="no_retry"):
            call(study, "dispatch")
        packet = call(study, "read", start=1, end=12)
        replies = []
        for panel in packet["panels"]:
            for a, b in combinations(panel["cards"], 2):
                aa, bb = (c["records"][0]["output"]["event"]["action"]["surface"] for c in (a, b))
                replies.append({"panel": panel["panel"], "a": a["side"], "b": b["side"], "label": "same_event" if aa == bb else "different_event",
                    "rationale": "Fictional separate launch and later lawsuit.", "evidence_a": aa, "evidence_b": bb})
        path = study.ledger.root / "replies.json"
        path.write_text(json.dumps(replies), encoding="utf-8")
        call(study, "submit", input=str(path))
        measured = call(study, "evaluate")
        assert measured["promotion_passed"]
        assert len(measured["experiments"]) == 16
        assert measured["selected"]["rule"]["correct_same"] == 36
        assert not study.ledger.unresolved
        profiled = call(study, "profile")
        assert profiled["experiments_executed"] == 15
        assert profiled["grouping"]["counts"]["multi_article_groups"] == 48
        assert profiled["grouping"]["counts"]["unmatched_articles"] == 48
        assert study.ledger.verify()["events"] > 0
        before = study.ledger.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        report = diagnosis.Diagnosis(tmp_path / "diagnosis", config=Config(offline=True))
        try:
            verified = call(report, "diagnosis", source=str(study.ledger.root))
            assert all(verified["checks"].values())
            assert verified["local_computations"] == 3
            assert verified["completed_gateway_attempts"] == 4
            assert len(verified["table"]) == 16
        finally:
            report.close()
        assert study.ledger.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before
    finally:
        study.close()
