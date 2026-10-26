"""One end-to-end synthetic audited experiment, including isolation failures."""
from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler
from newsresearch import luna_output_matching as cards_api

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "workbench"))
import luna_event_contract_v2 as contract  # noqa: E402
from run_luna_scalable_experiment import Experiment  # noqa: E402
from luna_scalable_rule_experiment_v2 import Successor  # noqa: E402
from run_luna_scalable_experiment_v3 import Experiment as Fresh  # noqa: E402
from group_luna_scalable_candidates_v3 import Grouping as FreshGrouping  # noqa: E402


class Fixture(Experiment):
    @audited_handler
    def _status(self, session, context, data):
        if data["action"] != "fixture":
            return super()._status(session, context, data)
        cards = []
        for corpus in ("first", "second"):
            for family in range(12):
                for member, side in enumerate("ABCD"):
                    _, output = contract.fictional_example()
                    name = f"{corpus} family{family} labs"
                    action = "launched" if member < 3 else "sued"
                    output["event"]["summary"] = f"{name} {action} a specialized service"
                    output["event"]["action"]["surface"] = action + " specialized service"
                    output["event"]["participants"][0]["surface"] = name
                    output["event"]["participants"] = output["event"]["participants"][:1]
                    output["event"]["facts"] = [{"subject": output["event"]["participants"][0]["id"],
                        "predicate": "version", "status": "stated", "attributed_to": None,
                        "support_refs": ["p1"], "value": {"surface": f"{family} release42" if member < 3 else f"{family} case99", "refs": ["p1"]}}]
                    identifier = f"{corpus}-{family}-{side}"
                    card = cards_api.make_card(article_id=identifier, corpus=corpus,
                        body_sha256=digest(identifier), published_at="2026-10-01" if member < 3 else "2026-10-30",
                        variants=[{"assessment": identifier, "raw_status": "valid", "derived_status": "valid", "raw_output": output, "output": output}])
                    card["metadata_variants"] = [{"publisher": {"uri": f"publisher-{member}.example"}}]
                    card["provenance"] = []
                    cards.append(card)
        ref = self.ledger.artifacts.put(cards)
        identifier = self.ledger.record(session, "luna_scalable_input", "synthetic", {"chunks": [ref], "cards": len(cards),
            "counts": {"ready": len(cards)}, "by_corpus": {c: {"ready": len(cards)//2} for c in ("first", "second")}})
        return {"id": identifier}


class Prior(Research):
    @audited_handler
    def _status(self, session, context, data):
        return {"id": self.ledger.record(session, "luna_matching_pilot_plan", "synthetic", {"cards": self.ledger.artifacts.put([])})}


def execute(engine, action, **kwargs):
    return engine.execute("status", {"action": action, **kwargs},
        objective="Synthetic software test only", actor="pytest:synthetic")


def test_audited_retrieval_reference_separation_and_evaluation(tmp_path):
    prior_path = tmp_path / "prior"
    prior = Prior(prior_path, config=Config(offline=True))
    try:
        execute(prior, "fixture")
    finally:
        prior.close()
    engine = Fixture(tmp_path / "experiment", config=Config(offline=True))
    successor = Successor(tmp_path / "successor", config=Config(offline=True))
    try:
        execute(engine, "fixture")
        retrieval = execute(engine, "retrieve")
        assert retrieval["counts"]["articles"] == 96
        assert retrieval["counts"]["unique_pairs"] <= 96 * 20
        execute(engine, "panels", prior_owner=str(prior_path))
        with pytest.raises(AuditError, match="freeze_development"):
            execute(engine, "dispatch", split="test")
        for split in ("development", "test"):
            execute(engine, "dispatch", split=split)
            with pytest.raises(AuditError, match="no_retry"):
                execute(engine, "dispatch", split=split)
            packet = execute(engine, "read", split=split, start=1, end=12)
            replies = []
            for panel in packet["panels"]:
                for a, b in combinations(panel["cards"], 2):
                    aa, bb = (c["records"][0]["output"]["event"]["action"]["surface"] for c in (a, b))
                    replies.append({"panel": panel["panel"], "a": a["side"], "b": b["side"],
                        "label": "same_event" if aa == bb else "different_event", "rationale": "Synthetic fixture assigns separate launch and lawsuit occurrences.",
                        "evidence_a": aa, "evidence_b": bb})
            path = engine.ledger.root / (split + ".json")
            if split == "development":
                corrupt = deepcopy(replies)
                corrupt[0]["evidence_a"] = "This quotation was never in the evidence."
                path.write_text(json.dumps(corrupt), encoding="utf-8")
                with pytest.raises(AuditError, match="quote_invalid"):
                    execute(engine, "submit", split=split, input=str(path))
                assert len(engine.ledger.unresolved) == 1
            path.write_text(json.dumps(replies), encoding="utf-8")
            execute(engine, "submit", split=split, input=str(path))
            assert not engine.ledger.unresolved
            result = execute(engine, "evaluate", split=split)
            assert result["selected_rule"]["false_same"] == 0
            assert result["selected_rule"]["correct_same"] > 0
            assert result["groups"].get("false_joins", 0) == 0
            assert result["retrieval_recovery"]["20"]["recovered"] == result["reference_labels"]["same_event"]
            if split == "development":
                revised = execute(successor, "calibrate", source_owner=str(engine.ledger.root))
                assert revised["selection_passed"]
                with pytest.raises(AuditError, match="already_frozen"):
                    execute(successor, "calibrate", source_owner=str(engine.ledger.root))
        revised = execute(successor, "evaluate", source_owner=str(engine.ledger.root))
        assert revised["promotion_passed"]
        grouped = execute(successor, "group", source_owner=str(engine.ledger.root))
        assert grouped["articles"] == 96
        assert grouped["counts"]["multi_article_groups"] == 24
        assert grouped["counts"]["unmatched_articles"] == 24
        assert grouped["counts"]["remaining_pairs"] == 0
        late = Successor(tmp_path / "late", config=Config(offline=True))
        try:
            with pytest.raises(AuditError, match="before_test_dispatch"):
                execute(late, "calibrate", source_owner=str(engine.ledger.root))
        finally:
            late.close()
        fresh = Fresh(tmp_path / "fresh", config=Config(offline=True))
        try:
            copied = execute(fresh, "import", source_owner=str(engine.ledger.root), rule_owner=str(successor.ledger.root))
            assert copied["excluded_previous_panel_bodies"] == 48
            execute(fresh, "retrieve")
            plan = execute(fresh, "panels", prior_owner=str(prior_path))
            assert plan["panel_counts"] == {"test": 6}
            original_map = engine.one("luna_scalable_panel_plan")["mapping"]
            fresh_map = fresh.one("luna_scalable_panel_plan")["mapping"]
            assert not {i for p in original_map for i in p["cards"].values()} & {i for p in fresh_map for i in p["cards"].values()}
            execute(fresh, "dispatch", split="test")
            packet = execute(fresh, "read", split="test", start=1, end=6)
            replies = []
            for panel in packet["panels"]:
                for a, b in combinations(panel["cards"], 2):
                    aa, bb = (c["records"][0]["output"]["event"]["action"]["surface"] for c in (a, b))
                    replies.append({"panel": panel["panel"], "a": a["side"], "b": b["side"],
                        "label": "same_event" if aa == bb else "different_event", "rationale": "Synthetic separate launch and lawsuit occurrences.", "evidence_a": aa, "evidence_b": bb})
            path = fresh.ledger.root / "test.json"
            path.write_text(json.dumps(replies), encoding="utf-8")
            execute(fresh, "submit", split="test", input=str(path))
            measured = execute(fresh, "evaluate", split="test")
            assert measured["selected_rule"]["correct_same"] == 18
            assert measured["groups"]["false_joins"] == 0
            full = FreshGrouping(tmp_path / "fresh-groups", config=Config(offline=True))
            try:
                measured = execute(full, "group", source_owner=str(fresh.ledger.root), kind="real")
                assert measured["counts"]["multi_article_groups"] == 24
                assert measured["counts"]["unmatched_articles"] == 24
            finally:
                full.close()
            assert fresh.ledger.verify()["events"] > 0
        finally:
            fresh.close()
        assert engine.ledger.verify()["events"] > 0
        assert successor.ledger.verify()["events"] > 0
    finally:
        successor.close()
        engine.close()
