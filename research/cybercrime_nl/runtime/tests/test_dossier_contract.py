"""Synthetic contract checks; never reads research owners or calls providers."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dossier_contract as c  # noqa: E402
from newsresearch.common import ResearchError, canonical, digest  # noqa: E402


def documents(n=2):
    return [{"document_id": f"doc-{i}", "title": f"Report {i}",
             "body": "  Café outage\nThe service stopped.\n  "} for i in range(n)]


def count(value):
    return len(value)


def answer(packet, labels=None):
    answers = []
    for q in packet["request"]["questions"]:
        values = [v["value"] for v in q["choices"]]
        chosen = (labels or {}).get(q["name"], values[0])
        answers.append({"name": q["name"], "type": "choice", "choice": chosen,
            "confidence": .88, "probabilities": [{"value": v, "probability": 1.0 if v == chosen else 0.0} for v in values]})
    return {"model": c.MODEL, "answers": answers}


def summary(docs, identity="group-1"):
    citations = [{"document_id": d["document_id"], "field": "body", "quote": d["body"][2:13]} for d in docs]
    claim = {"text": "Reported service outage", "citations": citations}
    return {"dossier_id": identity, "membership_revision": "revision-1",
            "source_document_ids": [d["document_id"] for d in docs],
            "event_title": deepcopy(claim), "overview": deepcopy(claim),
            "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
                         **{key: [] for key in c.IDENTITY_FIELDS}, "unknowns": ["Occurrence date unavailable."]}}


def response_json(value, model=c.MODEL):
    return {"model": model, "status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(value)}]}]}


def snapshot(docs, identity="group-1"):
    packet = c.summary_request(docs, identity, "revision-1", count_tokens=count)
    return c.parse_summary(packet, response_json(summary(docs, identity)))


def test_full_text_unicode_preserved_and_named_questions():
    docs = documents(8)
    packet = c.seed_request(docs, count_tokens=lambda _: 100)
    assert json.loads(packet["request"]["input"])["articles"] == docs
    assert len(packet["question_map"]) == 8 + 28
    assert packet["request"]["prompt_cache_options"] == {"mode": "explicit"}
    parsed = c.parse_decisions(packet, answer(packet))
    assert parsed["answers"]["pair_0"]["probability"] == 1
    assert parsed["answers"]["pair_0"]["confidence"] == .88


def test_split_never_slices_or_drops_full_documents():
    docs = documents(10)
    first_two = c.seed_request(docs[:2], count_tokens=count)["input_tokens_proxy"]
    packed = c.pack_seed_requests(docs, count_tokens=count, max_tokens=first_two)
    recovered = [d for p in packed["requests"] for d in p["documents"]]
    assert recovered == docs
    assert all(len(p["documents"]) <= 2 for p in packed["requests"])
    assert packed["cross_packet_pairs_checked"] is False


def test_oversize_deferred_and_following_document_retained():
    docs = documents(2)
    docs[0]["body"] = "x" * 40_000
    result = c.pack_seed_requests(docs, count_tokens=count, max_tokens=6000)
    assert result["deferred"][0]["document_id"] == "doc-0"
    assert result["requests"][0]["documents"] == [docs[1]]


def test_changed_body_hash_and_duplicate_input_rejected():
    docs = documents()
    docs[0]["body_sha256"] = "wrong"
    with pytest.raises(ResearchError, match="hash_mismatch"):
        c.seed_request(docs, count_tokens=count)
    with pytest.raises(ResearchError, match="duplicate_input"):
        c.pack_seed_requests([documents()[0]] * 2, count_tokens=count)


@pytest.mark.parametrize("mutation", ["duplicate_answer", "probability_sum", "nan", "wrong_model", "wrong_name"])
def test_invalid_decisions_fail_closed(mutation):
    packet = c.seed_request(documents(), count_tokens=count)
    value = answer(packet)
    if mutation == "duplicate_answer":
        value["answers"][1] = deepcopy(value["answers"][0])
    elif mutation == "probability_sum":
        value["answers"][0]["probabilities"][0]["probability"] = .5
    elif mutation == "nan":
        value["answers"][0]["confidence"] = float("nan")
    elif mutation == "wrong_model":
        value["model"] = "other"
    else:
        value["answers"][0]["name"] = "not-requested"
    with pytest.raises(ResearchError):
        c.parse_decisions(packet, value)


def test_answers_reordered_and_individual_refusal_preserved():
    packet = c.seed_request(documents(), count_tokens=count)
    value = answer(packet)
    value["answers"][-1] = {"name": "pair_0", "type": "refusal"}
    value["answers"].reverse()
    parsed = c.parse_decisions(packet, value)
    assert parsed["status"] == "partial_refusal"
    assert parsed["answers"]["pair_0"]["label"] is None
    assert parsed["answers"]["clarity_0"]["label"] == "clear_single_event"


def test_summary_citations_and_source_coverage_are_mechanical_only():
    docs = documents()
    valid = snapshot(docs)
    assert valid["summary_version"] == digest(valid["summary"])
    assert valid["validation"]["semantic_entailment_verified"] is False
    assert valid["validation"]["resolved_citations"][0]["exact_occurrences"] == [{"start": 2, "end": 13}]
    corrupt = summary(docs)
    corrupt["overview"]["citations"][0]["quote"] = "invented quotation"
    with pytest.raises(ResearchError, match="citation_invalid"):
        c.validate_summary(corrupt, docs)
    corrupt = summary(docs)
    corrupt["source_document_ids"].append("doc-0")
    with pytest.raises(ResearchError, match="source_coverage"):
        c.validate_summary(corrupt, docs)


def test_summary_binding_and_incomplete_response_block_assignment():
    docs = documents()
    packet = c.summary_request(docs, "group-1", "revision-1", count_tokens=count)
    value = summary(docs)
    value["membership_revision"] = "revision-2"
    with pytest.raises(ResearchError, match="binding_mismatch"):
        c.parse_summary(packet, response_json(value))
    value = response_json(summary(docs))
    value["status"] = "incomplete"
    with pytest.raises(ResearchError, match="incomplete"):
        c.parse_summary(packet, value)


def test_assignment_conflict_uncertainty_and_stale_guard():
    docs = documents()
    summaries = [snapshot([docs[0]], "group-a"), snapshot([docs[1]], "group-b")]
    incoming = {"document_id": "new", "title": "new report", "body": "Service outage."}
    packet = c.assignment_request(incoming, summaries, count_tokens=count)
    parsed = c.parse_decisions(packet, answer(packet))
    assert c.assignment_outcome(packet, parsed, packet["bindings"])["route"] == "conflict"
    parsed = c.parse_decisions(packet, answer(packet, {"dossier_1": "uncertain"}))
    assert c.assignment_outcome(packet, parsed, packet["bindings"])["route"] == "unresolved"
    parsed = c.parse_decisions(packet, answer(packet, {"dossier_1": "different_event"}))
    assert c.assignment_outcome(packet, parsed, packet["bindings"])["dossier_id"] == "group-a"
    with pytest.raises(ResearchError, match="stale_summary"):
        c.assignment_outcome(packet, parsed, {})


def test_faithfulness_has_full_sources_and_independent_labels():
    docs = documents()
    packet = c.summary_faithfulness_request(docs, snapshot(docs), count_tokens=count)
    assert json.loads(packet["request"]["input"])["articles"] == docs
    assert [x["value"] for x in packet["request"]["questions"][0]["choices"]] == [
        "supported", "unsupported", "identity_missing", "uncertain"]
    assert c.parse_decisions(packet, answer(packet))["answers"]["summary_faithfulness"]["label"] == "supported"


def test_blind_audit_all_named_answers_and_exact_pair_citations():
    docs = documents()
    packet = c.audit_request(docs, count_tokens=count)
    values = []
    for name, metadata in packet["question_map"].items():
        ids = [metadata["document_id"]] if metadata["kind"] == "clarity" else [metadata["left"], metadata["right"]]
        values.append({"name": name, "label": "clear_single_event" if metadata["kind"] == "clarity" else "same_event",
                       "reason": "Synthetic evidence", "citations": [
                           {"document_id": i, "field": "title", "quote": "Report"} for i in ids]})
    response = response_json({"answers": values}, model="gpt-6-astra")
    parsed = c.parse_audit(packet, response)
    assert parsed["answers"]["pair_0"]["probabilities"] is None
    values[-1]["citations"].pop()
    with pytest.raises(ResearchError, match="incomplete_citations"):
        c.parse_audit(packet, response_json({"answers": values}, model="gpt-6-astra"))
    assert "same_event" not in canonical(packet["bindings"])


def test_repeated_quote_reports_all_offsets_without_selecting_a_fake_unique_one():
    doc = {"document_id": "repeated", "title": "", "body": "same same"}
    value = c.resolve_citation({"document_id": "repeated", "field": "body", "quote": "same"}, {"repeated": doc})
    assert value["exact_occurrences"] == [{"start": 0, "end": 4}, {"start": 5, "end": 9}]
    assert value["unique_locator"] is False


def test_assignment_requires_clear_focus_and_full_exact_reference_version():
    docs = documents()
    packet = c.assignment_request(docs[1], [snapshot([docs[0]])], count_tokens=count)
    parsed = c.parse_decisions(packet, answer(packet, {"clarity_0": "multiple_focal_events"}))
    assert c.assignment_outcome(packet, parsed, packet["bindings"])["route"] == "unresolved_clarity"
    changed = deepcopy(packet)
    changed["request"]["input"] += "changed"
    with pytest.raises(ResearchError, match="request_mismatch"):
        c.parse_decisions(changed, answer(packet))


def test_large_summary_and_faithfulness_keep_all_sources_without_expanding_seed_limit():
    docs = documents(9)
    with pytest.raises(ResearchError, match="document_count"):
        c.seed_request(docs, count_tokens=count)
    packet = c.summary_request(docs, "large", "revision-1", count_tokens=count, max_tokens=96_000)
    saved = c.parse_summary(packet, response_json(summary(docs, "large")))
    check = c.summary_faithfulness_request(docs, saved, count_tokens=count, max_tokens=96_000)
    assert check["document_ids"] == [d["document_id"] for d in docs]
    with pytest.raises(ResearchError, match="document_count"):
        c.summary_request(documents(65), "large", "revision-1", count_tokens=lambda _: 1, max_tokens=96_000)


def test_assignment_allows_twenty_compact_candidates_with_no_silent_trim():
    docs = documents(20)
    summaries = [snapshot([doc], f"group-{i}") for i, doc in enumerate(docs)]
    packet = c.assignment_request({"document_id": "incoming", "title": "", "body": "new full text"},
                                  summaries, count_tokens=lambda _: 100)
    assert len(packet["question_map"]) == 21
    assert len(json.loads(packet["request"]["input"])["candidate_summaries"]) == 20


def test_matching_view_preserves_every_statement_and_full_snapshot_identity():
    docs = documents()
    full = summary(docs)
    full["event_title"]["text"] = "Alleged incident — not confirmed.\nExact Unicode café."
    full["overview"]["text"] = "Full overview with distinct wording."
    for name in c.IDENTITY_FIELDS:
        full["identity"][name] = [
            {"text": f"First {name} statement.", "citations": deepcopy(full["overview"]["citations"])},
            {"text": f"Second {name} statement.", "citations": deepcopy(full["overview"]["citations"])}]
    full["identity"]["unknowns"] = ["Exact occurrence date unknown.", "Participant role disputed."]
    original = deepcopy(full)
    packet = c.summary_request(docs, "group-1", "revision-1", count_tokens=count)
    saved = c.parse_summary(packet, response_json(full))
    view = c.summary_matching_view(full)

    def statement_paths(value, prefix=()):
        if isinstance(value, dict):
            return {path: text for key, item in value.items() if key not in {
                "citations", "source_document_ids", "dossier_id", "membership_revision"}
                for path, text in statement_paths(item, (*prefix, key)).items()}
        if isinstance(value, list):
            return {path: text for i, item in enumerate(value)
                    for path, text in statement_paths(item, (*prefix, i)).items()}
        return {prefix: value}

    assert statement_paths(view) == statement_paths(full)
    assert set(view) == {"event_title", "overview", "identity"}
    assert "citations" not in canonical(view) and "source_document_ids" not in canonical(view)
    assert "quote" not in canonical(view) and "exact_occurrences" not in canonical(view)
    assert full == original
    incoming = {"document_id": "incoming", "title": "New report", "body": "Full new article."}
    assignment = c.assignment_request(incoming, [saved], count_tokens=count)
    supplied = json.loads(assignment["request"]["input"])["candidate_summaries"][0]
    assert supplied["summary"] == view
    assert supplied["summary_version"] == digest(full) == assignment["bindings"]["group-1"]["summary_version"]
    assert supplied["membership_revision"] == "revision-1" and supplied["dossier_id"] == "group-1"
    assert len(canonical(supplied)) < len(canonical({"summary_version": digest(full), "summary": full}))
    assert saved["summary"] == full
    faithfulness = c.summary_faithfulness_request(docs, saved, count_tokens=count)
    assert json.loads(faithfulness["request"]["input"])["summary"] == full

    changed = deepcopy(full)
    changed["overview"]["citations"][0]["quote"] = "The service stopped."
    updated = c.parse_summary(packet, response_json(changed))
    updated_assignment = c.assignment_request(incoming, [updated], count_tokens=count)
    assert c.summary_matching_view(changed) == view
    assert updated["summary_version"] != saved["summary_version"]
    assert updated_assignment["request_sha256"] != assignment["request_sha256"]
    assert updated_assignment["bindings"] != assignment["bindings"]
