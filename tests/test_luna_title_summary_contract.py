"""Pure synthetic summary/search binding, exhaustive coverage and pilot checks."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_title_summary_contract as subject


def fixture(n=100):
    documents = {f"d{i:04d}": {"title": f"Incident title {i}",
        "body": f"The organization reports intrusion {i}.\r\nIts precise date is uncertain.",
        "article_row_ids": [f"row{i}"]} for i in range(n)}
    for d in documents.values():
        d["input_sha256"] = digest({k: d[k] for k in ("title", "body")})
    ids = sorted(documents)
    return {"source": {"documents": documents},
        "state": {"groups": {"g1": [ids[-1]], "g2": ids[-3:-1]}, "accepted_group_ids": ["g1", "g2"],
            "unresolved_ids": ids[:85]}, "history": {"quarantine_document_ids": []},
        "audit_positives": {i: [ids[n + 1]] for n, i in enumerate(ids[:81])}, "provenance": {"source": "synthetic"}}


def count(text):
    return len(text.encode("utf-8")) // 4


def response(answer, *, model=None, status="completed"):
    return {"model": model or subject.MODEL, "status": status,
        "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}]}


def summary(source, identity, text="The organization reports an intrusion. Its exact date remains uncertain."):
    packet = subject.summary_packet(source, identity, count)
    refs = [r["passage_id"] for r in packet["source_passage_catalog"]["passages"] if r["field"] == "body"]
    return packet, subject.parse_summary(packet, response({"document_id": "S1", "summary": text, "passage_ids": refs}))


@pytest.fixture(scope="module")
def prepared():
    imported = fixture()
    design = subject.build_design(imported, "fixed-pilot-seed", count_tokens=count)
    summaries = {i: summary(imported["source"], i)[1] for i in design["query_order"]}
    return imported, design, summaries


def search_response(packet, *, candidates=None, status="complete"):
    return response({"results": [{"query_id": f"Q{n + 1}", "status": status, "uncertainty": "",
        "candidates": [{"article_id": i, "clue": "Plausible title correspondence", "uncertainty": "Full source still required"}
            for i in (candidates or {}).get(q["document_id"], [])]} for n, q in enumerate(packet["queries"])]})


def test_fixed_sample_precedes_exclusions_priority_and_work_units(prepared):
    imported, design, _ = prepared
    selected = design["selection"]["pilot_ids"]
    assert len(selected) == 20 and len(set(selected)) == 20
    assert design["query_order"][:20] == selected
    assert set(design["query_order"]) == set(imported["source"]["documents"])
    remainder = [i for i in sorted(imported["audit_positives"]) if i not in selected]
    assert design["query_order"][20:20 + len(remainder)] == remainder
    assert design["work_units"][0] == selected
    assert all(len(unit) <= 32 for unit in design["work_units"][1:])
    for d in design["descriptors"]:
        assert set(d["query_ids"]) <= set(design["work_units"][d["work_unit"]])
        assert len(d["query_ids"]) <= 8
    changed = deepcopy(imported)
    changed["history"]["quarantine_document_ids"] = selected[:7]
    rerendered = subject.build_design(changed, "fixed-pilot-seed", count_tokens=count)
    assert rerendered["selection"]["pilot_ids"] == selected
    assert set(selected[:7]) <= set(rerendered["query_unavailable"])
    assert all(not set(d["query_ids"]) & set(selected[:7]) for d in rerendered["descriptors"])
    # Provisional articles precede remaining accepted multi-group articles even
    # when the latter have smaller lexical IDs.
    changed = deepcopy(imported)
    changed["state"]["groups"] = {"single": ["d0085"], "accepted": ["d0086", "d0087"], "provisional": ["d0097", "d0098"]}
    changed["state"]["accepted_group_ids"] = ["single", "accepted"]
    ordered = subject.build_design(changed, "fixed-pilot-seed", count_tokens=count)["query_order"]
    assert ordered.index("d0085") < ordered.index("d0097") < ordered.index("d0086")


def test_catalogue_preserves_all_6691_slots_duplicate_titles_missing_and_aliases():
    source = fixture()["source"]
    template = source["documents"]["d0000"]
    source["documents"] = {f"d{n:05d}": {**template, "article_row_ids": [f"row{n}"]} for n in range(6691)}
    source["documents"]["d00009"]["title"] = ""
    source["documents"]["d00009"].pop("input_sha256")
    c = subject.build_catalogue(source, [f"d{n:05d}" for n in range(7)])
    assert len(c["slots"]) == 6691 and len(c["eligible_document_ids"]) == 6683
    assert len({s["article_id"] for s in c["slots"]}) == 6691
    assert c["aliases"]["row8"] == "d00008"
    assert c["unavailable"]["d00009"] == "missing_title"
    assert c["slots"][7]["title"] == c["slots"][8]["title"]


def test_summary_whole_source_exact_passages_low_output_and_no_entailment_claim(prepared):
    imported, _, _ = prepared
    packet, result = summary(imported["source"], "d0000")
    supplied = json.loads(packet["request"]["input"])
    assert supplied["article"]["body"] == imported["source"]["documents"]["d0000"]["body"]
    assert supplied["article"]["title"] == imported["source"]["documents"]["d0000"]["title"]
    assert packet["request"]["max_output_tokens"] == 2048
    assert packet["request"]["reasoning"] == {"effort": "low"}
    assert packet["role"] == "article_summary"
    assert subject.focal.FOCUS_RULES in packet["request"]["instructions"]
    assert not result["semantic_entailment_verified"]
    for citation in result["citations"]:
        assert supplied["article"][citation["field"]][citation["start"]:citation["end"]] == citation["text"]
    assert result["passage_ids"]


@pytest.mark.parametrize("fault", ["words", "characters", "unknown_passage", "duplicate_passage", "wrong_document", "extra", "model", "incomplete", "refusal", "duplicate_json", "request", "source"])
def test_summary_malformed_or_changed_bindings_fail_without_repair(prepared, fault):
    source = prepared[0]["source"]
    packet = subject.summary_packet(source, "d0000", count)
    answer = {"document_id": "S1", "summary": "A factual intrusion report.", "passage_ids": ["S1.B1"]}
    if fault == "words":
        answer["summary"] = "word " * 151
    elif fault == "characters":
        answer["summary"] = "x" * 1801
    elif fault == "unknown_passage":
        answer["passage_ids"] = ["S9.B1"]
    elif fault == "duplicate_passage":
        answer["passage_ids"] *= 2
    elif fault == "wrong_document":
        answer["document_id"] = "d0000"
    elif fault == "extra":
        answer["confidence"] = .99
    payload = response(answer)
    if fault == "model":
        payload["model"] = "other"
    elif fault == "incomplete":
        payload["status"] = "incomplete"
    elif fault == "refusal":
        payload["output"][0]["content"][0]["type"] = "refusal"
    elif fault == "duplicate_json":
        payload["output"][0]["content"][0]["text"] = '{"document_id":"S1","document_id":"S1","summary":"x","passage_ids":["S1.B1"]}'
    elif fault in {"request", "source"}:
        if fault == "request":
            packet["request"]["instructions"] += " changed"
        else:
            packet["original_document"]["body"] += " changed"
        packet = subject._seal({k: v for k, v in packet.items() if k != "digest"})
    before = deepcopy(payload)
    with pytest.raises(ResearchError):
        subject.parse_summary(packet, payload)
    assert payload == before


def test_frozen_shards_complete_targets_independent_of_summary_and_safe_quote(prepared, monkeypatch):
    imported = deepcopy(prepared[0])
    for i, document in imported["source"]["documents"].items():
        document["title"] = ("Lengthy title " * 45) + i
        document.pop("input_sha256")
    monkeypatch.setattr(subject, "MAX_SEARCH_TOKENS", 100_000)
    calls = []

    def measured(text):
        calls.append(len(text))
        return count(text)

    design = subject.build_design(imported, "fixed-pilot-seed", count_tokens=measured)
    assert len(calls) == len(imported["source"]["documents"]) + len({d["query_batch"] for d in design["descriptors"]})
    assert design["quote"]["sharding_reason"] == subject.POLICY["sharding"]
    for batch in {d["query_batch"] for d in design["descriptors"]}:
        rows = [d for d in design["descriptors"] if d["query_batch"] == batch]
        ids = [i for d in rows for i in d["target_ids"]]
        assert ids == design["catalogue"]["eligible_document_ids"]
        assert len(ids) == len(set(ids))
    assert any(d["block"] > 0 for d in design["descriptors"])
    descriptor = design["descriptors"][0]
    # Maximum allowed Unicode width, not a cheap ASCII repetitive placeholder.
    summaries = {i: summary(imported["source"], i, "😀" * 1800)[1] for i in descriptor["query_ids"]}
    packet = subject.search_packet(design["catalogue"], descriptor, summaries, count)
    assert packet["role"] == "title_search"
    assert packet["wire_bytes"] <= descriptor["quote"]["wire_bytes_upper"]
    assert packet["reservation_nanousd"] <= descriptor["quote"]["reservation_nanousd_upper"]
    assert packet["request"]["max_output_tokens"] == 8192
    assert design["quote"]["pilot_reservation_nanousd"] == sum(design["summary_quotes"][i]["reservation_nanousd"] for i in design["selection"]["pilot_ids"]) + sum(d["quote"]["reservation_nanousd_upper"] for d in design["descriptors"] if d["work_unit"] == 0)


def test_full_source_capacity_retains_selected_query_without_replacement(prepared):
    imported = deepcopy(prepared[0])
    anchor = prepared[1]["selection"]["pilot_ids"][0]
    imported["source"]["documents"][anchor]["body"] = "Full body. " * 100_000
    imported["source"]["documents"][anchor].pop("input_sha256")
    design = subject.build_design(imported, "fixed-pilot-seed", count_tokens=count)
    assert design["selection"]["pilot_ids"] == prepared[1]["selection"]["pilot_ids"]
    assert design["summary_unavailable"][anchor] == "full_source_summary_capacity"
    assert anchor in design["query_order"]
    assert all(anchor not in d["query_ids"] for d in design["descriptors"])


@pytest.mark.parametrize("fault", ["missing_query", "duplicate_query", "foreign_query", "foreign_candidate", "self", "duplicate_candidate", "extra", "incomplete", "changed_summary", "changed_title", "changed_map"])
def test_search_exact_query_candidate_schema_and_binding(prepared, fault):
    _, design, summaries = prepared
    descriptor = design["descriptors"][0]
    packet = subject.search_packet(design["catalogue"], descriptor, summaries, count)
    catalogue_before = digest(design["catalogue"])
    payload = search_response(packet)
    answer = json.loads(payload["output"][0]["content"][0]["text"])
    if fault == "missing_query":
        answer["results"].pop()
    elif fault == "duplicate_query":
        answer["results"][-1] = deepcopy(answer["results"][0])
    elif fault == "foreign_query":
        answer["results"][0]["query_id"] = "Q99"
    elif fault in {"foreign_candidate", "self", "duplicate_candidate"}:
        alias = "T99999" if fault == "foreign_candidate" else packet["queries"][0]["article_id"] if fault == "self" else next(e["article_id"] for e in packet["entries"] if e["document_id"] != packet["queries"][0]["document_id"])
        candidate = {"article_id": alias, "clue": "x", "uncertainty": ""}
        answer["results"][0]["candidates"] = [candidate] * (2 if fault == "duplicate_candidate" else 1)
    elif fault == "extra":
        answer["results"][0]["confidence"] = .99
    elif fault in {"changed_summary", "changed_title", "changed_map"}:
        if fault == "changed_summary":
            packet["queries"][0]["summary"] = "Changed prose."
        elif fault == "changed_title":
            packet["entries"][0]["title"] += "changed"
        else:
            packet["queries"][0]["document_id"] = "foreign"
        packet = subject._seal({k: v for k, v in packet.items() if k != "digest"})
    payload["output"][0]["content"][0]["text"] = json.dumps(answer)
    if fault == "incomplete":
        payload["status"] = "incomplete"
    with pytest.raises(ResearchError):
        subject.parse_search(packet, payload)
    assert digest(design["catalogue"]) == catalogue_before


def test_overflow_and_empty_candidates_never_establish_absence(prepared):
    _, design, summaries = prepared
    packet = subject.search_packet(design["catalogue"], design["descriptors"][0], summaries, count)
    result = subject.parse_search(packet, search_response(packet, status="overflow"))
    assert all(not r["complete"] and r["candidate_ids"] == [] for r in result["results"])
    report = subject.summarize_pilot(design, [result], {i: "complete" for i in design["selection"]["pilot_ids"]})
    assert report["unknown"] == 20 and not report["threshold_met"]
    assert report["population_recall"] is None and report["confidence_interval"] is None
    assert not report["global_absence_proved"]


def test_development_witness_threshold_missingness_and_exact_result_partition(prepared):
    _, design, summaries = prepared
    selected = design["selection"]["pilot_ids"]
    aliases = {r["document_id"]: r["article_id"] for r in design["catalogue"]["slots"]}
    results = []
    for d in design["descriptors"]:
        if d["work_unit"] != 0:
            continue
        p = subject.search_packet(design["catalogue"], d, summaries, count)
        candidates = {i: [aliases[w] for w in design["selection"]["witnesses"][i] if w in d["target_ids"]]
            for i in d["query_ids"] if i in selected[:18]}
        results.append(subject.parse_search(p, search_response(p, candidates=candidates)))
    report = subject.summarize_pilot(design, results)
    assert (report["recovered"], report["not_recovered"], report["unknown"]) == (18, 2, 0)
    assert report["threshold_met"] and report["all_selected_title_coverage_complete"]
    assert report["development_only"] and report["population_recall"] is None
    with pytest.raises(ResearchError, match="result_scope"):
        subject.summarize_pilot(design, results + results[:1])
    missing = subject.summarize_pilot(design, results[:-1])
    assert missing["unknown"] > 0


def test_no_catalogue_id_enum_and_implementation_binds_contracts():
    subject.schemas.validate_wire_schema(subject.SUMMARY_SCHEMA)
    subject.schemas.validate_wire_schema(subject.SEARCH_SCHEMA)
    assert '"enum"' not in json.dumps(subject.SEARCH_SCHEMA["properties"]["results"]["items"]["properties"]["candidates"])
    paths = subject.implementation()
    for name in ("luna_title_summary_contract.py", "dossier_contract_v3.py", "dossier_contract_v5.py", "summary_fidelity_contract_v2.py", "luna_recall_contract.py", "final_validation_design.py"):
        assert any(p.endswith(name) for p in paths)
