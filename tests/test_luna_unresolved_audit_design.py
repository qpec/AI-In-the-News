"""Compact pure coverage, full-source wire, no-retry and interval checks."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_unresolved_audit_design as subject


def fixture(n=12, unresolved=None):
    documents = {f"d{i:05d}": {"title": f"Incident {i}", "body": f"Complete source {i}.\n\nLast detail {i}."} for i in range(n)}
    for document in documents.values():
        document["input_sha256"] = digest(document)
    ids = sorted(documents)
    return {"source": {"documents": documents, "candidate_manifest": {"document_ids": ids, "neighbors": {}}, "provenance": {}},
        "state": {"unresolved_ids": ids[:n if unresolved is None else unresolved]},
        "history": {"quarantine_document_ids": [], "development_exposed_documents": [],
            "prior_final_reference_logical_ids": [], "logical_ids": []}}


def count(text):
    return len(text.encode()) // 4


def descriptor(plan, anchors, targets, *, quarantine=(), prior=()):
    selection = plan["selection"]
    row = {"method": subject.METHOD, "selection_digest": selection["digest"],
        "ordinal": 0, "anchor_block": 0, "target_offset": 0, "anchor_ids": list(anchors), "target_ids": list(targets),
        "sample_ids": selection["sample_ids"], "source_bindings": {i: selection["source_bindings"][i] for i in sorted(set(anchors) | set(targets))},
        "quarantine_document_ids": list(quarantine), "prior_blocked_pair_keys": list(prior),
        "stop_after_positive": selection["stop_after_positive"]}
    row["pair_count"] = len(subject.descriptor_pairs(row))
    return subject._seal(row)


def response(packet, *, pair_label="same_event", clarity_label="clear_single_event"):
    answers = []
    for question in packet["request"]["questions"]:
        labels = [c["value"] for c in question["choices"]]
        label = clarity_label if question["name"].startswith("c") else pair_label
        probabilities = [{"value": v, "probability": .94 if v == label else .06 / (len(labels) - 1)} for v in labels]
        answers.append({"name": question["name"], "type": "choice", "choice": label, "probabilities": probabilities, "confidence": .11})
    return {"model": subject.base.MODEL, "answers": answers}


def observation(a, b, label):
    pair = sorted([a, b])
    return {"pair": pair, "pair_key": subject.contract.pair_key(*pair), "label": label, "role": "final_reference"}


def test_exact_production_size_fixed_sample_before_exclusions_and_round_robin():
    imported = fixture(6691, 1429)
    plan = subject.build_plan(imported, "prospective-fixed-seed")
    assert plan["expected_unique_pairs"] == 664050
    assert plan["directed_neighbor_slots"] == 669000
    assert plan["selection"]["sample_size"] == 100
    assert [d["anchor_block"] for d in plan["descriptors"][:5]] == list(range(5))
    selected = plan["selection"]["sample_ids"]
    imported["history"]["quarantine_document_ids"] = selected[:5]
    imported["history"]["development_exposed_documents"] = selected[:7]
    changed = subject.build_plan(imported, "prospective-fixed-seed")
    assert changed["selection"]["sample_ids"] == selected
    assert changed["selection"]["development_exposed_sample_ids"] == sorted(selected[:7])
    assert changed["expected_unique_pairs"] == 664050
    assert "pair_tasks" not in changed  # Compact rectangles, no repeated full-source matrix.


def test_small_grid_covers_every_unordered_sample_edge_exactly_once():
    imported = fixture(135, 110)
    plan = subject.build_plan(imported, "seed")
    pairs = [tuple(sorted(p)) for d in plan["descriptors"] for p in subject.descriptor_pairs(d)]
    sample, universe = set(plan["selection"]["sample_ids"]), set(imported["source"]["documents"])
    expected = {tuple(sorted((a, t))) for a in sample for t in universe if a != t}
    assert len(pairs) == len(set(pairs)) == len(expected)
    assert set(pairs) == expected


def test_rrf_prioritizes_retained_neighbors_but_keeps_complete_lexical_tail():
    imported = fixture(60)
    sample = subject.build_plan(imported, "rrf")["selection"]["sample_ids"]
    anchor, target = sample[0], "d00059"
    if anchor == target:
        target = "d00058"
    imported["source"]["candidate_manifest"]["neighbors"][anchor] = {"vector": [{"document_id": target, "rank": 1}]}
    plan = subject.build_plan(imported, "rrf")
    rows = [d for d in plan["descriptors"] if d["anchor_block"] == 0]
    assert rows[0]["target_ids"][0] == target
    targets = [i for d in rows for i in d["target_ids"]]
    assert targets == [target] + [i for i in sorted(imported["source"]["documents"]) if i != target]


def test_dense_full_source_398_questions_shared_rules_and_original_pair_ids():
    imported = fixture(138, 100)
    plan = subject.build_plan(imported, "dense")
    anchors, targets = plan["selection"]["sample_ids"][:20], sorted(imported["source"]["documents"])[100:118]
    d = descriptor(plan, anchors, targets)
    bundle = subject.packet(imported["source"], d, count)
    assert len(bundle["packets"]) == 1
    packet = bundle["packets"][0]
    assert len(packet["request"]["questions"]) == 398 and len(packet["pair_entries"]) == 360
    wire_input = json.loads(packet["request"]["input"])
    assert wire_input["rules"]["focal_rules"] == subject.focal.FOCUS_RULES
    assert all(subject.focal.FOCUS_RULES not in q["instructions"] for q in packet["request"]["questions"])
    for doc in wire_input["articles"]:
        original = imported["source"]["documents"][packet["source_bindings"][doc["document_id"]]["document_id"]]
        assert (doc["title"], doc["body"]) == (original["title"], original["body"])
    for entry in packet["pair_entries"]:
        assert entry["logical_id"] == subject.contract.identity(imported["source"], entry["pair"], "final_reference", False)
    assert bundle["quote"]["reservation_nanousd"] == subject.contract.reservation(packet)
    payload = response(packet)
    payload["answers"].reverse()  # Provider answer order is irrelevant.
    parsed, observations = subject.parse(packet, payload)
    assert parsed["status"] == "valid" and len(observations) == 360
    assert all(r["label"] == "same_event" and r["confidence"] == .11 for r in observations)


def test_sample_sample_pair_remains_for_other_active_endpoint_and_never_moves():
    imported = fixture(4)
    plan = subject.build_plan(imported, "active")
    a, b, c = sorted(imported["source"]["documents"])[:3]
    d = descriptor(plan, [a], [b, c])
    full = subject.packet(imported["source"], d, count)
    part = subject.packet(imported["source"], d, count, [b])
    assert [r["pair"] for p in part["packets"] for r in p["pair_entries"]] == [[a, b]]
    assert part["packets"][0]["logical_ids"][0] == full["packets"][0]["logical_ids"][0]
    assert part["skipped_after_positive"][0]["pair"] == [a, c]
    assert not subject.packet(imported["source"], d, count, [])["packets"]
    reverse = descriptor(plan, [b], [a])
    assert subject.descriptor_pairs(reverse) == []


def test_all_pairs_mode_cannot_be_silently_pruned():
    imported = fixture(4)
    plan = subject.build_plan(imported, "all", stop_after_positive=False)
    with pytest.raises(ResearchError, match="active_sample_scope"):
        subject.packet(imported["source"], plan["descriptors"][0], count, [])


def test_quarantine_and_prior_exact_identity_remain_unknown_without_any_packet():
    imported = fixture(3)
    a, b, c = sorted(imported["source"]["documents"])
    imported["history"]["quarantine_document_ids"] = [b]
    imported["history"]["logical_ids"] = [subject.contract.identity(imported["source"], [a, c], "final_reference", False)]
    plan = subject.build_plan(imported, "blocked")
    bundles = [subject.packet(imported["source"], d, count) for d in plan["descriptors"]]
    assert not any(p for bundle in bundles for p in bundle["packets"])
    coverage = [r for bundle in bundles for r in bundle["unavailable"]]
    assert CounterLike(coverage) == {"quarantined_source": 2, "prior_final_reference_attempt": 1}
    report = subject.summarize(plan["selection"], [], coverage)
    assert report["summary"]["unknown"] == 3 and report["confidence_interval_95"] == [0, 1]
    with pytest.raises(ResearchError, match="blocked_pair_cannot_resolve"):
        subject.summarize(plan["selection"], [observation(a, b, "same_event")])


def CounterLike(rows):
    return {reason: sum(r["reason"] == reason for r in rows) for reason in {r["reason"] for r in rows}}


def test_adaptive_split_preserves_all_pairs_and_whole_documents():
    imported = fixture(15)
    plan = subject.build_plan(imported, "split")
    d = descriptor(plan, ["d00000", "d00001"], ["d00002", "d00003", "d00004", "d00005"])
    calls = []
    def capacity(wire):
        request = json.loads(wire)
        docs = json.loads(request["input"])["articles"]
        calls.append(len(docs))
        return 96001 if len(docs) > 3 else 100
    result = subject.packet(imported["source"], d, capacity)
    assert len(result["packets"]) > 1 and not result["unavailable"]
    rows = [r for p in result["packets"] for r in p["pair_entries"]]
    assert len(rows) == len({r["pair_key"] for r in rows}) == d["pair_count"]
    assert max(calls) == 6
    assert all(p["input_tokens_proxy"] <= 96000 for p in result["packets"])
    assert result == subject.packet(imported["source"], d, capacity)


def test_individually_oversized_source_is_unavailable_never_truncated():
    imported = fixture(2)
    imported["source"]["documents"]["d00000"]["body"] = "x" * (subject.MAX_WIRE_BYTES + 10)
    doc = imported["source"]["documents"]["d00000"]
    doc["input_sha256"] = digest({k: doc[k] for k in ("title", "body")})
    plan = subject.build_plan(imported, "capacity")
    result = subject.packet(imported["source"], plan["descriptors"][0], lambda _: 0)
    assert not result["packets"] and result["unavailable"][0]["reason"] == "full_source_capacity"


@pytest.mark.parametrize("case", ["source", "descriptor", "active", "rank"])
def test_foreign_changed_or_malformed_inputs_fail_closed(case):
    imported = fixture(6)
    plan = subject.build_plan(imported, "guards")
    d = deepcopy(plan["descriptors"][0])
    if case == "source":
        imported["source"]["documents"]["d00000"]["body"] += " changed"
    elif case == "descriptor":
        d["target_ids"] = ["foreign"]
    elif case == "rank":
        imported["source"]["candidate_manifest"]["neighbors"]["d00000"] = {"vector": [{"document_id": "foreign", "rank": 1}]}
    with pytest.raises(ResearchError):
        if case == "rank":
            subject.build_plan(imported, "guards")
        else:
            subject.packet(imported["source"], d, count, ["foreign"] if case == "active" else None)


@pytest.mark.parametrize("case", ["missing", "duplicate", "model", "probability", "map", "source_binding", "extra_question"])
def test_strict_response_and_question_source_binding(case):
    imported = fixture(2)
    plan = subject.build_plan(imported, "parser")
    packet = subject.packet(imported["source"], plan["descriptors"][0], count)["packets"][0]
    payload = response(packet)
    if case == "missing":
        payload["answers"].pop()
    elif case == "duplicate":
        payload["answers"][-1] = deepcopy(payload["answers"][0])
    elif case == "model":
        payload["model"] = "other"
    elif case == "probability":
        payload["answers"][0]["probabilities"][0]["probability"] = float("nan")
    elif case == "map":
        packet["question_map"]["p0"]["right"] = "A1"
    elif case == "source_binding":
        packet["source_bindings"]["A1"]["input_sha256"] = "f" * 64
    else:
        packet["request"]["questions"].append(deepcopy(packet["request"]["questions"][0]))
        packet["request_sha256"] = digest(packet["request"])
    with pytest.raises(ResearchError):
        subject.parse(packet, payload)


def test_clarity_gate_negative_sum_and_refusal_are_preserved():
    imported = fixture(2)
    plan = subject.build_plan(imported, "labels")
    packet = subject.packet(imported["source"], plan["descriptors"][0], count)["packets"][0]
    assert subject.parse(packet, response(packet, clarity_label="multiple_focal_events"))[1][0]["label"] == "unknown"
    payload = response(packet)
    pair = payload["answers"][-1]
    values = {"same_event": .02, "related_event": .50, "different_event": .40, "uncertain": .08}
    pair.update(choice="related_event", probabilities=[{"value": k, "probability": v} for k, v in values.items()])
    assert subject.parse(packet, payload)[1][0]["label"] == "negative"
    payload["answers"][0] = {"name": "c0", "type": "refusal"}
    assert subject.parse(packet, payload)[1][0]["label"] == "unknown"


def test_positive_witness_stops_existence_not_coverage_and_shared_sample_edge_counts_both():
    imported = fixture(4)
    selection = subject.build_plan(imported, "outcomes")["selection"]
    a, b, c, d = sorted(imported["source"]["documents"])
    rows = [observation(a, b, "same_event"), observation(a, c, "negative"), observation(b, c, "negative"), observation(c, d, "negative")]
    result = subject.summarize(selection, rows)
    assert result["summary"] == {"selected_articles": 4, "population_articles": 4, "detected_missed_match": 2,
        "no_match_in_frozen_corpus": 1, "unknown": 1, "unique_observed_pairs": 4, "full_neighbor_coverage_articles": 1}
    assert result["articles"][a]["outcome"] == result["articles"][b]["outcome"] == "detected_missed_match"
    assert not result["articles"][a]["neighbor_coverage_complete"]
    assert result["sample_identification_interval"] == [.5, .75]
    assert result["confidence_interval_95"] == [.5, .75]  # Census of four, one unknown.
    assert result["point_estimate"] is None and result["whole_pipeline_recall"] is None


def test_no_match_requires_every_other_corpus_article_and_coverage_flags_cannot_supply_labels():
    imported = fixture(7, 3)
    selection = subject.build_plan(imported, "negative")["selection"]
    a = selection["sample_ids"][0]
    others = [i for i in selection["all_document_ids"] if i != a]
    rows = [observation(a, b, "negative") for b in others]
    full = subject.summarize(selection, rows)
    assert full["articles"][a]["outcome"] == "no_match_in_frozen_corpus"
    coverage = [{**rows[-1], "reason": "claimed_complete"}]
    partial = subject.summarize(selection, rows[:-1], coverage)
    assert partial["articles"][a]["outcome"] == "unknown"
    assert subject.summarize(selection, [])["confidence_interval_95"] == [0, 1]


@pytest.mark.parametrize("case", ["duplicate", "outside", "development", "bad_key"])
def test_report_does_not_accept_foreign_or_repeated_observations(case):
    imported = fixture(5, 2)
    selection = subject.build_plan(imported, "scope")["selection"]
    rows = [observation("d00000", "d00001", "same_event")]
    if case == "duplicate":
        rows += deepcopy(rows)
    elif case == "outside":
        rows = [observation("d00003", "d00004", "same_event")]
    elif case == "development":
        rows[0]["role"] = "development"
    else:
        rows[0]["pair_key"] = "wrong"
    with pytest.raises(ResearchError):
        subject.summarize(selection, rows)


def test_implementation_binds_numerical_and_rubric_dependencies():
    files = subject.implementation()
    assert all("research/cybercrime_nl/runtime/" + name in files for name in
        ("luna_unresolved_audit_design.py", "final_validation_design.py", "luna_recall_contract.py", "dossier_contract.py", "dossier_contract_v5.py"))
    assert "uv.lock" in files
