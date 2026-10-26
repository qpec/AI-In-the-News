"""Synthetic immutable owner cutoffs; no owner/model/CLI/account accesses."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_external_task_scope as module  # noqa: E402
import test_final_validation_conversation_prior as conversation_fixture  # noqa: E402
import test_final_validation_legacy_pair_history as pair_fixture  # noqa: E402
import test_final_validation_legacy_prior as cli_fixture  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402
from newsresearch.storage import Artifacts, prepare_root  # noqa: E402


def normalize(sample, *, origin=True, name=None):
    owner = sample.owner(name) if name else sample.owner()
    return module.normalize_external_task_scope(owner, cli_fixture.index(), origin_owner=owner if origin else None)


def test_exact_classifier_manifest_is_persistable_with_unchanged_credential_guard(tmp_path):
    sample = pair_fixture.PairFixture()
    sample.attempt(missing_handoff=True)
    result = normalize(sample)
    artifacts = Artifacts(prepare_root(tmp_path / "protected-artifacts"))
    reference = artifacts.put(result)
    assert reference == digest(result) and artifacts.read(reference) == result
    assert result["policy"] == "exact-native-contract-purpose-independent-of-review-outcome-v1"


class AstraFixture(cli_fixture.LegacyFixture):
    """Use actual native registered definitions, not the old P fixture's mock question."""
    def __init__(self):
        self.data = conversation_fixture.Census()
        self.items = [{"article_id": "a" + str(n), "title": d["title"], "body": d["body"]}
                      for n, d in enumerate(cli_fixture.fixture.docs(2))]
        paths = (module.ROOT / "workbench/validate_incident_decisions_astra.py",
                 Path(module.prior.legacy.__file__), Path(module.prior.cli.__file__))
        impl = {str(p.relative_to(module.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        questions = deepcopy(module.screening.QUESTIONS)
        content = {"protocol": {"method": module.prior.FAMILY, "implementation": impl},
            "question": {"text": "Original native question"}, "selection": {"rules": "Original sample"},
            "profile": {"mode": "exploratory"}, "policy": {"max_retries": 0},
            "prompt": {"instructions": module.prior.legacy.RULES, "model": module.prior.legacy.MODEL,
                "reasoning_effort": "medium", "batch_size_max": 5,
                "questions": "Exact questions verified identical across all selected frozen requests before dispatch; bound in plan."},
            "codebook": {"labels": sorted({v for choices in module.prior.legacy.LABELS.values() for v in choices}),
                "questions": questions, "boundary_ambiguous_policy": "Retain as unresolved in primary confusion matrix"}}
        versions = {kind: self.data.record(kind, module.prior.FAMILY, {"content": value})["id"] for kind, value in content.items()}
        self.plan = {"method": module.prior.FAMILY, "versions": versions, "implementation": impl,
            "questions": questions, "batches": [{"phase": "pilot", "items": self.data.put(self.items), "count": 2}],
            "source_owner": "original-frozen-input-owner", "codex_executable": "C:/synthetic/codex.exe",
            "codex_binary_sha256": digest("synthetic-binary")}
        self.plan_row = self.data.record(module.prior.PLAN, module.prior.FAMILY, self.plan)
        self.plan = json.loads(canonical(self.plan))
        self.request = module.prior.legacy.request_for(self.items, self.plan["questions"])
        self.dispatch = cli_fixture.dispatch(self.request)


@pytest.mark.parametrize("outcome", ["orphan", "valid", "invalid"])
def test_pair_role_survives_missing_P_and_failed_or_orphan_response(outcome):
    sample = pair_fixture.PairFixture(prepared_extra=True)
    sample.attempt(missing_handoff=outcome == "orphan")
    if outcome != "orphan":
        sample.submit(invalid=outcome == "invalid")
    result = normalize(sample)
    task = result["dispositions"][0]
    assert task["disposition"] == "pair_reference" and task["primary_blocker_required"]
    assert task["matched_document_ids"] == ["d0", "d1"] and task["origin_verified"]
    assert not task["creates_pair_y"] and not result["establishes_P"]
    assert result["census"]["physical_intent_count"] == 1
    assert result["inspected_task_semantics_complete"]
    assert len(result["prepared_only"]) == 1 and result["prepared_only"][0]["slot"] == 2
    assert "Synthetic full body" not in canonical(result) and "Synthetic rationale" not in canonical(result)


@pytest.mark.parametrize("family", list(module.conversation.FAMILIES))
@pytest.mark.parametrize("reply", [False, True])
def test_exact_article_contract_is_nonpair_without_read_or_response(family, reply):
    sample = conversation_fixture.ConversationFixture(family, docs=cli_fixture.fixture.docs(2))
    sample.attempt(missing_handoff=not reply)
    if reply:
        sample.submit([1])
        sample.submit([2])
    result = normalize(sample)
    assert len(result["dispositions"]) == 1
    assert result["dispositions"][0]["disposition"] == "nonpair_screening"
    assert not result["dispositions"][0]["primary_blocker_required"]
    assert result["inspected_task_semantics_complete"] and not result["possible_pair_gaps"]
    assert sum(v["disposition"] == "nonpair_article_subresult" for v in result["record_dispositions"].values()) == (2 if reply else 0)


@pytest.mark.parametrize("variant", ["orphan", "wrong_model", "opaque", "predispatch", "clean"])
def test_exact_CLI_screening_contract_is_nonpair_independent_of_serving_evidence(variant):
    sample = AstraFixture()
    sample.attempt(variant)
    result = normalize(sample)
    assert result["dispositions"][0]["disposition"] == "nonpair_screening"
    assert result["inspected_task_semantics_complete"]
    assert result["census"]["intent_partition_exact"] and result["census"]["record_partition_exact"]
    assert not result["historical_discovery_complete"]


def test_merely_named_CLI_plan_does_not_prove_nonpair_contract():
    sample = cli_fixture.LegacyFixture()
    sample.attempt("orphan")
    result = normalize(sample)
    assert result["dispositions"][0]["disposition"] == "possible_pair_unknown"
    assert not result["inspected_task_semantics_complete"]


@pytest.mark.parametrize("family", ["pair", "article", "cli"])
def test_prepared_only_selection_creates_no_physical_task(family):
    sample = pair_fixture.PairFixture() if family == "pair" else AstraFixture() if family == "cli" else conversation_fixture.ConversationFixture()
    result = normalize(sample)
    assert result["dispositions"] == [] and result["census"]["physical_intent_count"] == 0
    assert result["prepared_only"] and all(not x["physical_attempt_created"] for x in result["prepared_only"])


def test_verified_copied_origin_deduplicates_even_without_response():
    sample = conversation_fixture.ConversationFixture()
    sample.attempt()
    native, copy = sample.owner("original"), sample.owner("retrospective-copy")
    a = module.normalize_external_task_scope(native, cli_fixture.index(), origin_owner=native)
    b = module.normalize_external_task_scope(copy, cli_fixture.index(), origin_owner=native)
    merged = module.merge_verified_dispositions([a, b])
    assert len(merged["physical_tasks"]) == 1
    assert len(next(iter(merged["physical_tasks"].values()))["views"]) == 2
    assert not merged["unresolved_origin_views"]


def test_unverified_nonpair_origin_preserves_semantics_not_false_pair_gap():
    sample = conversation_fixture.ConversationFixture()
    sample.attempt()
    result = normalize(sample, origin=False)
    assert result["dispositions"][0]["disposition"] == "nonpair_screening"
    assert result["possible_pair_gaps"] == [] and result["physical_origin_gaps"]
    assert result["inspected_task_semantics_complete"] and not result["verified_physical_origin_census_complete"]
    assert module.merge_verified_dispositions([result])["physical_tasks"] == {}


def test_unknown_records_and_omitted_scope_cannot_be_hidden_by_family_coverage():
    sample = conversation_fixture.ConversationFixture()
    sample.attempt()
    manual = sample.data.record("manual_same_event_review", "arbitrary", {"statement": "Not a known producer"})
    owner = sample.owner()
    owner.census["out_of_scope_record_ids"] = [digest("omitted")]
    result = module.normalize_external_task_scope(owner, cli_fixture.index(), origin_owner=owner)
    assert result["unclassified_record_ids"] == [manual["id"]]
    assert {g["reason_code"] for g in result["possible_pair_gaps"]} == {
        "unclassified_record_possible_manual_pair", "omitted_record_scope_unverified"}
    assert result["census"]["record_partition_exact"] and not result["inspected_task_semantics_complete"]


def test_missing_selected_record_breaks_census_not_silent_subset():
    sample = pair_fixture.PairFixture()
    sample.attempt()
    owner = sample.owner()
    owner.records.pop()
    with pytest.raises(ValueError, match="selected_census"):
        module.normalize_external_task_scope(owner, cli_fixture.index(), origin_owner=owner)


@pytest.mark.parametrize("change", ["request", "dispatch"])
def test_modified_native_contract_fails_closed(change):
    sample = conversation_fixture.ConversationFixture()
    sample.attempt(**{"mutate_" + change: lambda value: value.update(extra="changed")})
    with pytest.raises(ValueError, match="native_request_dispatch"):
        normalize(sample)


def test_one_missing_pair_source_scopes_gap_to_known_final_endpoint():
    sample = pair_fixture.PairFixture(withheld=(1,))
    sample.attempt()
    result = normalize(sample)
    gap = next(g for g in result["possible_pair_gaps"] if g["reason_code"] == "pair_source_identity_unavailable")
    assert gap["input_sha256"] == [cli_fixture.index().inputs[0].input_sha256]
    assert result["dispositions"][0]["disposition"] == "pair_reference"


def test_exact_nonintersecting_pair_is_not_corpus_name_assumption():
    sample = pair_fixture.PairFixture(docs=[{"title": "Outside1", "body": "Exact1"}, {"title": "Outside2", "body": "Exact2"}])
    sample.attempt()
    result = normalize(sample)
    assert result["dispositions"][0]["matched_document_ids"] == []
    assert len(result["dispositions"][0]["source_identities"]) == 2
    assert result["inspected_task_semantics_complete"]


def test_unsupported_orphan_intent_is_counted_once_not_guessed_from_name():
    sample = conversation_fixture.ConversationFixture()
    sample.data.event("model.attempt.intended", {"attempt": "unknown", "plan": digest("other"),
        "request": digest("missing"), "dispatch": digest("missing2")})
    result = normalize(sample)
    assert result["census"]["expected_intent_ids"] == result["census"]["classified_intent_ids"] == ["unknown"]
    assert result["dispositions"][0]["physical_identity"] is None
    assert result["possible_pair_gaps"][0]["input_sha256"] is None


def test_copied_origin_conflict_is_integrity_error_not_new_attempt():
    sample = pair_fixture.PairFixture()
    sample.attempt()
    native, copy = sample.owner(), sample.owner("copy")
    native.artifacts = dict(native.artifacts)
    native.artifacts[sample.intent["dispatch"]] = b"conflicting bytes"
    with pytest.raises(ValueError):
        module.normalize_external_task_scope(copy, cli_fixture.index(), origin_owner=native)


def test_scope_manifest_tampering_rejected_by_merge():
    sample = pair_fixture.PairFixture()
    sample.attempt()
    result = normalize(sample)
    result["dispositions"][0]["disposition"] = "nonpair_screening"
    with pytest.raises(ValueError, match="manifest_digest"):
        module.merge_verified_dispositions([result])


def test_custom_manual_event_without_a_record_is_not_lost():
    sample = conversation_fixture.ConversationFixture()
    sample.attempt()
    event = sample.data.event("manual.article_pair.checked", {"opaque_reference": digest("manual")})
    result = normalize(sample)
    assert result["unclassified_event_hashes"] == [event["event_hash"]]
    assert result["census"]["event_partition_exact"]
    assert any(g["reason_code"] == "unclassified_event_possible_manual_pair" for g in result["possible_pair_gaps"])


def test_missing_request_on_attempted_task_never_becomes_prepared_only():
    sample = pair_fixture.PairFixture(prepared_extra=True)
    sample.attempt()
    sample.data.artifacts.pop(sample.intent["request"])
    result = normalize(sample)
    assert result["dispositions"][0]["disposition"] == "possible_pair_unknown"
    assert [p["slot"] for p in result["prepared_only"]] == [2]


def test_recorded_inspection_and_partial_submissions_do_not_create_extra_tasks():
    sample = conversation_fixture.ConversationFixture()
    sample.attempt()
    sample.read(1, 2)
    sample.submit([1])
    sample.read(3, 3)
    sample.submit([3])
    result = normalize(sample)
    assert result["census"]["physical_intent_count"] == 1
    assert result["inspected_task_semantics_complete"]
    assert result["census"]["event_partition_exact"] and not result["unclassified_event_hashes"]


def test_extra_manual_payload_cannot_hide_under_preparation_kind():
    sample = conversation_fixture.ConversationFixture()
    sample.attempt()
    record = sample.data.record(sample.prefix + "_preparation", sample.family,
        {"versions": sample.versions, "started_at": "synthetic", "manual_pair_reference": "unproved"})
    result = normalize(sample)
    assert record["id"] in result["unclassified_record_ids"]


def test_known_response_artifact_gap_is_not_invented_pair_scope_gap():
    sample = AstraFixture()
    sample.attempt("clean")
    owner = sample.owner()
    owner.gaps.append({"reason_code": "declared_artifact_missing", "artifact": sample.response_ref,
        "affected_input_sha256": None, "owner_sha256": owner.census["owner_sha256"]})
    result = module.normalize_external_task_scope(owner, cli_fixture.index(), origin_owner=owner)
    assert result["outcome_only_inventory_gaps"] and not result["possible_pair_gaps"]
    assert result["inspected_task_semantics_complete"]
    assert result["full_manual_event_inventory_verified"] is False


def test_unknown_inventory_gap_keeps_its_exact_endpoint_scope():
    sample = conversation_fixture.ConversationFixture()
    sample.attempt()
    owner = sample.owner()
    bound = [cli_fixture.index().inputs[0].input_sha256]
    owner.gaps.append({"reason_code": "declared_record_missing", "record_id": digest("missing"), "affected_input_sha256": bound})
    result = module.normalize_external_task_scope(owner, cli_fixture.index(), origin_owner=owner)
    assert result["possible_pair_gaps"][0]["input_sha256"] == bound


def test_generic_status_wrappers_do_not_hide_manual_pair_task():
    sample = conversation_fixture.ConversationFixture()
    sample.data.session = "manual-review"
    first = sample.data.event("operation.intended", {"operation": "status",
        "input": sample.data.put({"action": "manual_pair_review", "sources": ["unbound-A", "unbound-B"]})})
    last = sample.data.event("operation.completed", {"operation": "status",
        "result": sample.data.put({"same_event": True})})
    result = normalize(sample)
    assert set(result["unclassified_event_hashes"]) == {first["event_hash"], last["event_hash"]}
    assert result["census"]["physical_intent_count"] == 0 and not result["inspected_task_semantics_complete"]


def test_missing_native_read_return_does_not_discharge_generic_operation():
    sample = conversation_fixture.ConversationFixture()
    sample.attempt()
    sample.read(1, 1, no_completion=True)
    result = normalize(sample)
    assert result["unclassified_event_hashes"]
    assert not result["inspected_task_semantics_complete"]
