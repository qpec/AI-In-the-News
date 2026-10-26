"""Exact logical pair lookup; synthetic adapter inputs, no real source/model."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_batch_pair_lookup as module  # noqa: E402
import test_final_validation_representation_history as base  # noqa: E402
import test_final_validation_matching_history as matching_base  # noqa: E402
from final_validation_frame import build_input_index  # noqa: E402
from newsresearch.common import AuditError, digest  # noqa: E402


@pytest.fixture(scope="module")
def blueprint():
    return base.Fixture()


@pytest.fixture
def sample(blueprint):
    return deepcopy(blueprint)


def source(result):
    return {"manifest": deepcopy(result.manifest), "bindings": deepcopy(list(result.pair_attempt_bindings))}


def seal(value):
    value["manifest"]["pair_attempt_bindings_sha256"] = digest(value["bindings"])
    value["manifest"]["logical_pair_bindings"] = len(value["bindings"])
    return value


def test_exact_pairs_do_not_overblock_unrelated_pairs_sharing_endpoints(sample):
    sample.attempt(handoff=False)
    actual = module._compile([source(sample.result())], sample.index())
    assert actual["counts"] == {"verified_physical_reference_batches": 1,
        "unverified_reference_batch_views": 0, "unique_logical_slots": 60,
        "retained_slot_views": 60, "unique_current_pair_blockers": 60,
        "unresolved_regions": 0, "excluded_logical_slots": 0}
    hashes = [d.input_sha256 for d in sample.index().inputs]
    keys = {r["pair_key"] for r in actual["pair_blockers"]}
    assert module.pair_key([hashes[0], hashes[1]], "primary") in keys
    assert module.pair_key([hashes[0], hashes[4]], "primary") not in keys
    assert module.pair_key([hashes[0], hashes[1]], "qc") not in keys
    assert not actual["creates_pair_y"] and not actual["dispatch_authorized"]
    assert not actual["whole_history_complete"]


def test_verified_copy_deduplicates_slots_and_batches_without_invented_attempts(sample):
    sample.attempt()
    first = source(sample.result())
    second = deepcopy(first)
    second["manifest"]["source_id"] = digest("retained-copy-view")
    actual = module._compile([first, second], sample.index())
    assert actual["counts"]["verified_physical_reference_batches"] == 1
    assert actual["counts"]["unique_logical_slots"] == 60
    assert actual["counts"]["retained_slot_views"] == 120
    assert all(len(row["logical_references"]) == 1 for row in actual["pair_blockers"])


def test_unknown_origin_still_blocks_exact_pairs_without_physical_count(sample):
    sample.attempt()
    actual = module._compile([source(sample.result(origin=False))], sample.index())
    assert len(actual["pair_blockers"]) == 60
    assert actual["counts"]["verified_physical_reference_batches"] == 0
    assert actual["counts"]["unverified_reference_batch_views"] == 1
    assert not actual["unresolved_regions"]
    for row in actual["pair_blockers"]:
        assert row["logical_references"][0]["physical_id"] is None
        assert row["logical_references"][0]["unverified_source_view"]


def test_one_missing_endpoint_keeps_only_its_three_known_partner_regions(sample):
    sample.attempt()
    sample.standard.artifacts.pop(sample.original_requests["historical-0"])
    actual = module._compile([source(sample.result())], sample.index())
    assert len(actual["pair_blockers"]) == 57
    assert len(actual["unresolved_regions"]) == 3
    assert all(len(r["affected_input_sha256"]) == 1 for r in actual["unresolved_regions"])


def test_two_missing_endpoints_retain_global_region(sample):
    sample.attempt()
    for n in (0, 1):
        sample.standard.artifacts.pop(sample.original_requests[f"historical-{n}"])
    actual = module._compile([source(sample.result())], sample.index())
    assert any(row["affected_input_sha256"] is None for row in actual["unresolved_regions"])
    assert len(actual["pair_blockers"]) == 55


def test_complete_outside_sources_are_excluded_without_corpus_heuristic(sample):
    sample.attempt()
    actual = module._compile([source(sample.result(count=4))], sample.index(4))
    assert len(actual["pair_blockers"]) == 6
    assert actual["counts"]["excluded_logical_slots"] == 54
    assert not actual["unresolved_regions"]


def test_unknown_partner_with_proven_outside_endpoint_is_excluded(sample):
    sample.attempt()
    sample.standard.artifacts.pop(sample.original_requests["historical-4"])
    actual = module._compile([source(sample.result(count=4))], sample.index(4))
    assert not actual["unresolved_regions"]
    assert len(actual["pair_blockers"]) == 6
    assert actual["counts"]["excluded_logical_slots"] == 54
    assert sum(row["reason_code"] == "one_proven_source_outside_current_frame"
               for row in actual["excluded_slots"]) == 3


def test_prepared_only_and_experimental_arms_create_no_pair_reference_blocker(sample):
    sample.arm()
    actual = module._compile([source(sample.result())], sample.index())
    assert not actual["pair_blockers"] and not actual["unresolved_regions"]
    assert actual["counts"]["verified_physical_reference_batches"] == 0


def test_unknown_intent_and_inherited_owner_gap_are_never_dropped(sample):
    sample.attempt()
    value = source(sample.result())
    value["manifest"]["unresolved_evidence"].append({"reason_code": "unsupported_physical_intent", "attempt": "unknown", "input_sha256": None})
    value["manifest"]["inherited_inventory_gaps"].append({"reason_code": "missing", "affected_input_sha256": [sample.index().inputs[0].input_sha256]})
    actual = module._compile([value], sample.index())
    assert len(actual["unresolved_regions"]) == 2
    assert {r["reason_code"] for r in actual["unresolved_regions"]} == {"unsupported_physical_intent", "inherited_owner_inventory_gap"}


def test_alias_slots_collapse_pair_keys_without_independent_alias_pair(sample):
    sample.attempt()
    value = source(sample.result())
    original = value["bindings"][0]["source_identities"][0]
    alias = value["bindings"][0]["source_identities"][1]["input_sha256"]
    documents = [row for row in sample.documents if row["input_sha256"] != alias]
    index = build_input_index(documents, {row["document_id"]: None for row in documents}, bindings=dict(sample.index().bindings))
    for row in value["bindings"]:
        row["source_identities"] = [deepcopy(original) if identity["input_sha256"] == alias else identity for identity in row["source_identities"]]
        row["matched_input_sha256"] = sorted({i["input_sha256"] for i in row["source_identities"]})
    value["manifest"]["input_index_digest"] = index.digest
    actual = module._compile([seal(value)], index)
    assert actual["counts"]["unique_logical_slots"] == 60
    assert len(actual["pair_blockers"]) == 57
    assert len(actual["excluded_slots"]) == 1
    assert any(len(row["logical_references"]) == 2 for row in actual["pair_blockers"])


@pytest.mark.parametrize("mutation,reason", [
    (lambda v: v["manifest"].update(input_index_digest=digest("other")), "adapter_binding"),
    (lambda v: v["bindings"][0].update(role_policy={"final_validation_role": "qc"}), "logical_slot_binding"),
    (lambda v: v["bindings"][0].update(logical_slot_id=digest("other")), "logical_slot_binding"),
    (lambda v: v["bindings"][0].update(physical_id=digest("other")), "batch_origin_binding"),
    (lambda v: v["bindings"][0].update(matched_input_sha256=[]), "current_endpoint_mapping"),
    (lambda v: v["bindings"][0]["source_identities"][0].update(full_retained_source_proven=False), "full_source_provenance"),
    (lambda v: v["bindings"].append(deepcopy(v["bindings"][0])), "duplicate_slot_in_view"),
    (lambda v: v["bindings"].pop(), "complete_batch_slot_partition"),
])
def test_conflicting_or_incomplete_bindings_fail_closed(sample, mutation, reason):
    sample.attempt()
    value = source(sample.result())
    mutation(value)
    seal(value)
    with pytest.raises(AuditError, match=reason):
        module._compile([value], sample.index())


def test_conflicting_verified_copy_is_not_counted_as_another_attempt(sample):
    sample.attempt()
    first = source(sample.result())
    second = deepcopy(first)
    second["manifest"]["source_id"] = digest("copy")
    second["bindings"][0]["request_artifact"] = digest("different-wire")
    with pytest.raises(AuditError, match="conflicting_physical_batch_contract"):
        module._compile([first, seal(second)], sample.index())


def test_same_input_hash_cannot_hide_conflicting_title_body_identity(sample):
    sample.attempt()
    value = source(sample.result())
    value["bindings"][0]["source_identities"] = deepcopy(value["bindings"][0]["source_identities"])
    value["bindings"][0]["source_identities"][0]["title_sha256"] = digest("wrong-title")
    with pytest.raises(AuditError, match="conflicting_full_input_identity"):
        module._compile([seal(value)], sample.index())


def test_child_rejects_arbitrary_parent_hash_or_forged_reader_without_active_research():
    with pytest.raises(AuditError, match="concrete_parent_required"):
        module.protocol_content(object(), "fake-session", digest("parent"))


@pytest.fixture(scope="module")
def matching_blueprint():
    return matching_base.Fixture()


@pytest.fixture
def matching_sample(matching_blueprint):
    return deepcopy(matching_blueprint)


def test_matching_twenty_four_exact_pairs_keep_one_physical_primary_batch(matching_sample):
    matching_sample.attempt(handoff=False)
    result = matching_sample.result()
    actual = module._compile([source(result)], matching_sample.index)
    expected = {module.pair_key(row["matched_input_sha256"], "primary") for row in result.pair_attempt_bindings}
    assert {r["pair_key"] for r in actual["pair_blockers"]} == expected
    assert actual["counts"]["verified_physical_reference_batches"] == 1
    assert actual["counts"]["unique_logical_slots"] == 24
    assert not actual["unresolved_regions"] and not actual["creates_pair_y"]
    assert all(r["role"] == "primary" for r in actual["pair_blockers"])
    assert all(ref["family"] == module.matching.FAMILY for r in actual["pair_blockers"] for ref in r["logical_references"])


def test_matching_copy_views_deduplicate_same_batch_and_logical_slots(matching_sample):
    matching_sample.attempt()
    first = source(matching_sample.result())
    second = deepcopy(first)
    second["manifest"]["source_id"] = digest("matching-copy")
    actual = module._compile([first, second], matching_sample.index)
    assert actual["counts"]["verified_physical_reference_batches"] == 1
    assert actual["counts"]["unique_logical_slots"] == 24
    assert actual["counts"]["retained_slot_views"] == 48
    assert all(len(r["logical_references"]) == 1 for r in actual["pair_blockers"])


def test_matching_unknown_origin_blocks_pairs_without_fabricated_physical_identity(matching_sample):
    matching_sample.attempt()
    actual = module._compile([source(matching_sample.result(origin=False))], matching_sample.index)
    assert actual["counts"]["verified_physical_reference_batches"] == 0
    assert actual["counts"]["unverified_reference_batch_views"] == 1
    assert len(actual["pair_blockers"]) == 24 and not actual["unresolved_regions"]
    assert all(ref["physical_id"] is None for r in actual["pair_blockers"] for ref in r["logical_references"])


def test_matching_missing_original_sources_keep_endpoint_or_global_unknown(matching_sample):
    matching_sample.attempt()
    task = matching_sample.selected[0]
    card = next(c for c in matching_sample.cards if c["article_id"] == task["left"])
    p = next(p for p in matching_sample.provenance if p["assessment"] == card["records"][0]["extraction_id"])
    matching_sample.standard.artifacts.pop(p["request"])
    partial = module._compile([source(matching_sample.result())], matching_sample.index)
    assert partial["unresolved_regions"] and all(len(r["affected_input_sha256"]) == 1 for r in partial["unresolved_regions"])
    unknown = module._compile([source(matching_sample.result(standard=False))], matching_sample.index)
    assert not unknown["pair_blockers"]
    assert all(r["affected_input_sha256"] is None for r in unknown["unresolved_regions"])


def test_matching_proven_outside_sources_exclude_slots_without_corpus_assumption(matching_sample):
    matching_sample.attempt()
    # All matching pairs use the first20 inputs; the final frame contains only
    # independently identified second20 inputs, including the same source corpus
    # label would not by itself be enough to establish this exact disjointness.
    docs = matching_sample.documents[20:]
    matching_sample.index = build_input_index(docs, {d["document_id"]: None for d in docs}, bindings=dict(matching_sample.index.bindings))
    actual = module._compile([source(matching_sample.result())], matching_sample.index)
    assert not actual["pair_blockers"] and not actual["unresolved_regions"]
    assert actual["counts"]["excluded_logical_slots"] == 24


def test_two_supported_families_preserve_distinct_physical_batches_and_shared_pairs(sample, matching_sample):
    sample.attempt()
    matching_sample.attempt()
    assert sample.index().digest == matching_sample.index.digest
    first, second = source(sample.result()), source(matching_sample.result())
    a = module._compile([first], sample.index())
    b = module._compile([second], sample.index())
    actual = module._compile([first, second], sample.index())
    assert actual["counts"]["verified_physical_reference_batches"] == 2
    assert actual["counts"]["unique_logical_slots"] == 84
    assert {r["pair_key"] for r in actual["pair_blockers"]} == {r["pair_key"] for r in a["pair_blockers"] + b["pair_blockers"]}
    assert any(len(r["logical_references"]) == 2 for r in actual["pair_blockers"])


def test_same_physical_attempt_cannot_change_family_between_views(sample, matching_sample):
    sample.attempt()
    matching_sample.attempt()
    first, second = source(sample.result()), source(matching_sample.result())
    original = first["bindings"][0]
    for row in second["bindings"]:
        row.update(original_attempt=original["original_attempt"], original_owner_source_id=original["original_owner_source_id"], physical_id=original["physical_id"])
    second["manifest"]["reference_batches"][0].update(original_attempt=original["original_attempt"], physical_id=original["physical_id"])
    with pytest.raises(AuditError, match="conflicting_physical_batch_contract"):
        module._compile([first, seal(second)], sample.index())


@pytest.mark.parametrize("mutation,reason", [
    (lambda v: v["manifest"].update(family="caller-selected-family"), "unsupported_adapter_family"),
    (lambda v: v["manifest"]["implementation"].update(unbound="changed"), "adapter_binding"),
    (lambda v: v["bindings"][0].update(role_policy={"final_validation_role": "qc"}), "logical_slot_binding"),
    (lambda v: v["bindings"][0].update(evidence_scope="full_article"), "matching_logical_slot"),
    (lambda v: v["bindings"][0]["source_identities"][0].update(full_retained_source_identity_proven=False), "full_source_provenance"),
    (lambda v: v["bindings"].pop(), "complete_batch_slot_partition"),
])
def test_matching_exact_contract_and_slot_binding_fail_closed(matching_sample, mutation, reason):
    matching_sample.attempt()
    value = source(matching_sample.result())
    mutation(value)
    with pytest.raises(AuditError, match=reason):
        module._compile([seal(value)], matching_sample.index)


def test_matching_copy_cannot_change_historical_parent_pair_binding(matching_sample):
    matching_sample.attempt()
    first = source(matching_sample.result())
    second = deepcopy(first)
    second["manifest"]["source_id"] = digest("copy")
    second["bindings"][0]["parent_pair_request"] = digest("altered-parent-pair")
    with pytest.raises(AuditError, match="conflicting_copied_slot"):
        module._compile([first, seal(second)], matching_sample.index)


def test_matching_slots_with_duplicate_numbers_do_not_satisfy_partition(matching_sample):
    matching_sample.attempt()
    value = source(matching_sample.result())
    first = value["bindings"][0]
    previous = first["logical_slot_id"]
    first["logical_slot"]["number"] = value["bindings"][1]["logical_slot"]["number"]
    first["logical_slot_id"] = digest(first["logical_slot"])
    batch = value["manifest"]["reference_batches"][0]
    batch["logical_pair_slots"] = [first["logical_slot_id"] if v == previous else v for v in batch["logical_pair_slots"]]
    with pytest.raises(AuditError, match="matching_number_partition"):
        module._compile([seal(value)], matching_sample.index)


def test_matching_aliases_keep_logical_slots_without_self_pairs(matching_sample):
    matching_sample.attempt()
    value = source(matching_sample.result())
    original, old = value["bindings"][0]["source_identities"]
    docs = [d for d in matching_sample.documents if d["input_sha256"] != old["input_sha256"]]
    index = build_input_index(docs, {d["document_id"]: None for d in docs}, bindings=dict(matching_sample.index.bindings))
    for row in value["bindings"]:
        row["source_identities"] = [deepcopy(original) if i["input_sha256"] == old["input_sha256"] else i for i in row["source_identities"]]
        row["matched_input_sha256"] = sorted({i["input_sha256"] for i in row["source_identities"]})
    value["manifest"]["input_index_digest"] = index.digest
    actual = module._compile([seal(value)], index)
    assert actual["counts"]["unique_logical_slots"] == 24
    assert any(r["reason_code"] == "exact_alias_not_distinct_pair" for r in actual["excluded_slots"])
    assert all(len(set(r["input_sha256"])) == 2 for r in actual["pair_blockers"])
