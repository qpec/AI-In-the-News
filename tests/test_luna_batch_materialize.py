"""Synthetic lineage/eligibility checks; no archive, owner or model research."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import luna_batch_materialize as module
    import luna_multibatch as core
finally:
    sys.path.pop(0)

CORPUS = "incident-reports"
MANIFESTS = {CORPUS: "a" * 64, "cybercrime": "b" * 64}
SNAPSHOT = core.load_contract_snapshot()


def fixture(*, number=1, corpus=CORPUS, body="All retained evidence.\r\n\r\nSecond paragraph é 😀. "):
    article = {"uri": f"synthetic:{number}", "body": body, "title": "Synthetic event title",
               "date": "2026-01-01", "lang": "eng", "source": {"uri": "synthetic.example"}}
    raw = (json.dumps({"article": article}, ensure_ascii=False) + "\n").encode("utf-8")
    locator = {"archive_path": corpus + ".zip", "archive_sha256": "c" * 64,
               "stream": "artikelen.jsonl", "line": number,
               "row_bytes_sha256": hashlib.sha256(raw).hexdigest()}
    partition = {"corpus_id": corpus, "manifest_sha256": MANIFESTS[corpus],
                 "manifest": {"bundles": [{"path": locator["archive_path"], "sha256": "c" * 64}]}}
    normalized, availability = module.normalize_context(article)
    record = core.build_request_record(normalized, corpus_id=corpus,
        manifest_sha256=MANIFESTS[corpus], source_locator=locator, source_sha256=digest(article),
        count_tokens=len, token_proxy_method="cl100k_base_serialized_body_plus_32",
        context_availability=availability, contract_snapshot=SNAPSHOT)
    row = {"id": digest({"corpus_id": corpus, "manifest_sha256": MANIFESTS[corpus],
                         "source_locator": locator}), "corpus_id": corpus, "source_locator": locator,
           "state": "ready", "descriptor": record["descriptor"],
           "canonical_custom_id": record["descriptor"]["custom_id"]}
    return raw, partition, record, row


def checks(rows):
    return {reason: {"reconciled": True, "source_count": sum(reason in row["reasons"] for row in rows)}
            for reason in module.REQUIRED_CHECKS}


def capsule(rows=(), *, sealed=()):
    rows = list(rows)
    return module.make_exclusion_capsule(rows, corpus_manifests=MANIFESTS, checks=checks(rows),
                                         provenance={"owner_export": "d" * 64}, sealed_body_hashes=sealed)


def exclusion(descriptor, reason="prior_speed_attempt", *, source="e" * 64):
    return {"source_version": source, "corpus_id": descriptor["corpus_id"], "reasons": [reason],
            "source_sha256": descriptor["source_sha256"],
            "retained_body_sha256": descriptor["retained_body_sha256"],
            "source_locator": descriptor["source_locator"]}


def rebuild(descriptor=None, **kwargs):
    raw, partition, record, _ = fixture()
    return module.materialize_descriptor(descriptor or record["descriptor"], raw,
        partition=partition, contract_snapshot=SNAPSHOT, count_tokens=kwargs.get("count_tokens", len))


def test_exact_fulltext_reconstruction():
    _, _, record, _ = fixture()
    replayed = rebuild()
    assert replayed == record
    assert replayed["request"]["body"]["max_output_tokens"] == 4096
    assert replayed["request"]["body"]["instructions"] == SNAPSHOT.prompt
    assert replayed["packet"]["source_map"]["source_fields"]["body"]["text"].endswith("😀. ")


@pytest.mark.parametrize("field,value", [
    ("source_sha256", "e" * 64), ("source_map_sha256", "e" * 64),
    ("packet_sha256", "e" * 64), ("retained_body_sha256", "e" * 64),
    ("line_sha256", "e" * 64), ("line_bytes", 12), ("request_sha256", "e" * 64),
    ("request_body_sha256", "e" * 64), ("input_tokens_proxy", 1),
    ("input_tokens_exact", 12), ("token_proxy_validated_for_luna", True),
    ("contract_sha256", "e" * 64), ("max_output_tokens", 2048),
    ("manifest_sha256", "e" * 64), ("corpus_id", "cybercrime"),
])
def test_descriptor_tampering_fails_closed(field, value):
    _, _, record, _ = fixture()
    record["descriptor"][field] = value
    with pytest.raises(ValueError):
        rebuild(record["descriptor"])


def test_wrong_proxy_function_is_rejected():
    with pytest.raises(ValueError, match="input_tokens_proxy"):
        rebuild(count_tokens=lambda text: 1)


def test_raw_row_must_retain_exact_whitespace_and_ending():
    raw, partition, record, _ = fixture()
    with pytest.raises(ValueError, match="raw_row_hash"):
        module.materialize_descriptor(record["descriptor"], raw.rstrip(), partition=partition,
                                      contract_snapshot=SNAPSHOT, count_tokens=len)


def test_archive_binding_is_required():
    raw, partition, record, _ = fixture()
    partition["manifest"]["bundles"][0]["sha256"] = "d" * 64
    with pytest.raises(ValueError, match="archive_mismatch"):
        module.materialize_descriptor(record["descriptor"], raw, partition=partition,
                                      contract_snapshot=SNAPSHOT, count_tokens=len)


def test_missing_unreconciled_or_wrong_count_capsule_rejected():
    value = capsule()
    for changed in ({}, {**value["checks"], "prior_speed_attempt": {"reconciled": False, "source_count": 0}},
                    {**value["checks"], "prior_speed_attempt": {"reconciled": True, "source_count": 1}}):
        with pytest.raises(ValueError):
            module.make_exclusion_capsule([], corpus_manifests=MANIFESTS, checks=changed,
                                          provenance={"owner": "synthetic"})


def test_mutated_capsule_rejected():
    value = capsule()
    value["provenance"]["owner_export"] = "f" * 64
    with pytest.raises(ValueError, match="capsule_changed"):
        module.build_exclusion_index(value)


def test_all_reasons_and_matching_keys_are_preserved():
    _, _, record, _ = fixture()
    row = exclusion(record["descriptor"])
    row["reasons"] = sorted(module.REQUIRED_CHECKS)
    value = capsule([row], sealed=[row["retained_body_sha256"]])
    decision = module.assess_descriptor(record["descriptor"], module.build_exclusion_index(value))
    assert not decision["eligible"]
    assert decision["reasons"] == sorted(module.REQUIRED_CHECKS)
    assert decision["matches"][0]["matched_by"] == ["source_sha256", "retained_body_sha256", "source_locator"]
    assert decision["global_sealed_body_match"] is True


def test_prior_exposure_exact_body_copy_is_withheld():
    _, _, record, _ = fixture(number=1)
    _, _, copy, _ = fixture(number=2)
    assert record["descriptor"]["source_sha256"] != copy["descriptor"]["source_sha256"]
    index = module.build_exclusion_index(capsule([exclusion(record["descriptor"])]))
    decision = module.assess_descriptor(copy["descriptor"], index)
    assert not decision["eligible"]
    assert decision["matches"][0]["matched_by"] == ["retained_body_sha256"]


def test_sealed_body_protection_covers_other_corpus_and_outside_old_membership():
    _, _, cyber, _ = fixture(corpus="cybercrime")
    body_hash = cyber["descriptor"]["retained_body_sha256"]
    index = module.build_exclusion_index(capsule(sealed=[body_hash]))
    decision = module.assess_descriptor(cyber["descriptor"], index)
    assert decision["reasons"] == ["sealed_body_validation"]
    assert not decision["eligible"]
    assert decision["matches"] == []


def test_prior_speed_other_corpus_not_implicitly_reused_or_combined():
    _, _, incident, _ = fixture()
    _, _, cyber, _ = fixture(corpus="cybercrime")
    index = module.build_exclusion_index(capsule([exclusion(incident["descriptor"])]))
    assert module.assess_descriptor(cyber["descriptor"], index)["eligible"]


def test_sealed_source_requires_body_and_inclusion_in_full_frame():
    _, _, record, _ = fixture()
    row = exclusion(record["descriptor"], "sealed_body_validation")
    with pytest.raises(ValueError, match="does_not_cover"):
        capsule([row])
    del row["retained_body_sha256"]
    with pytest.raises(ValueError, match="requires_full_body_hash"):
        capsule([row])


def test_reconciliation_preserves_aliases_and_unavailable_rows():
    _, _, record, first = fixture(number=1)
    _, _, _, second = fixture(number=2)
    second.update(state="alias", canonical_row_id=first["id"], canonical_custom_id=record["descriptor"]["custom_id"])
    _, _, _, third = fixture(number=3)
    third.pop("descriptor")
    third.update(state="body_unavailable", reason="missing_blank_or_nontext_body")
    results = list(module.reconcile_rows([first, second, third], module.build_exclusion_index(capsule())))
    assert [row["production_eligibility"] for row in results] == ["eligible", "alias", "unavailable"]


def test_excluded_canonical_is_not_promoted_through_alias():
    _, _, record, first = fixture(number=1)
    _, _, _, second = fixture(number=2)
    second.update(state="alias", canonical_row_id=first["id"], canonical_custom_id=record["descriptor"]["custom_id"])
    index = module.build_exclusion_index(capsule([exclusion(record["descriptor"])]))
    results = list(module.reconcile_rows([first, second], index))
    assert [row["production_eligibility"] for row in results] == ["set_aside", "set_aside"]
    assert "canonical_request_withheld" in results[1]["eligibility"]["reasons"]


@pytest.mark.parametrize("mutation", ["foreign_alias", "duplicate_row", "reversed_alias", "changed_id"])
def test_reconciliation_invalid_lineage_rejected(mutation):
    _, _, record, first = fixture(number=1)
    _, _, _, second = fixture(number=2)
    second.update(state="alias", canonical_row_id=first["id"], canonical_custom_id=record["descriptor"]["custom_id"])
    rows = [first, second]
    if mutation == "foreign_alias":
        second["canonical_custom_id"] = "wrong"
    elif mutation == "duplicate_row":
        rows.append(first)
    elif mutation == "reversed_alias":
        rows.reverse()
    elif mutation == "changed_id":
        first["id"] = "f" * 64
    with pytest.raises(ValueError):
        list(module.reconcile_rows(rows, module.build_exclusion_index(capsule())))


def owner_export():
    _, _, record, _ = fixture()
    row = exclusion(record["descriptor"])
    locator = row.pop("source_locator")
    row["archive_provenance"] = {"bundle": locator["archive_path"], "bundle_sha256": locator["archive_sha256"],
                                 "line_number": locator["line"], "row_sha256": locator["row_bytes_sha256"]}
    categories = ["sealed_body_validation", "stopped_extraction", "prior_speed_attempt", "unresolved_prior_attempt"]
    return {"completed": True, "categories": categories, "category_counts": {k: int(k == "prior_speed_attempt") for k in categories},
            "rows": [row], "sealed_body_hashes": [], "sealed_body_hash_count": 0,
            "partition": {"file_sha256": {f"corpora/{c}/manifest.json": v for c, v in MANIFESTS.items()}},
            "source_owner": "synthetic-owner", "original_result": "d" * 64, "protocol": "f" * 64,
            "created_at": "2026-01-01T00:00:00+00:00"}


def test_owner_export_adapts_without_model_outputs_or_body_reads():
    value = owner_export()
    index = module.index_from_owner_export(value, MANIFESTS)
    assert len(index.selectors) == 3
    assert len(index.sealed_body_hashes) == 0


@pytest.mark.parametrize("mutation", ["incomplete", "missing_frame", "bad_frame_count", "bad_source_count", "changed_manifest"])
def test_owner_export_requires_complete_provenance(mutation):
    value = owner_export()
    if mutation == "incomplete":
        value["completed"] = False
    elif mutation == "missing_frame":
        del value["sealed_body_hashes"]
    elif mutation == "bad_frame_count":
        value["sealed_body_hash_count"] = 1
    elif mutation == "bad_source_count":
        value["category_counts"]["prior_speed_attempt"] = 5
    else:
        value["partition"]["file_sha256"][f"corpora/{CORPUS}/manifest.json"] = "f" * 64
    with pytest.raises(ValueError):
        module.index_from_owner_export(value, MANIFESTS)


def test_legacy_locator_rejects_conflicting_aliases():
    value = owner_export()["rows"][0]["archive_provenance"]
    value["jsonl_line"] = 999
    with pytest.raises(ValueError, match="alias_conflict"):
        module.locator_from_legacy(value)


def prepared_binding():
    _, partition, _, _ = fixture()
    binding = {"partition": partition, "contract_sha256": SNAPSHOT.contract_sha256,
               "model": core.MODEL, "reasoning_effort": "none", "max_output_tokens": 4096}
    result = {"binding": binding, "binding_sha256": digest(binding), "corpus_id": CORPUS,
              "versions": {"protocol": "d" * 64}, "shard_plan_artifact": "f" * 64,
              "totals": {"rows": 3, "requests": 2}}
    manifest = {"binding_sha256": result["binding_sha256"], "corpus_id": CORPUS,
                "manifest_sha256": MANIFESTS[CORPUS], "versions": result["versions"],
                "shard_plan_artifact": "f" * 64, "prospective_request_count": 2,
                "descriptor_chunks": [{"rows": 3}]}
    return result, manifest, partition


def test_saved_preparation_binding_validates_exactly():
    result, manifest, partition = prepared_binding()
    module.validate_preparation_binding(result, manifest, partition, SNAPSHOT)


@pytest.mark.parametrize("mutation", ["hash", "count", "partition", "contract", "output_limit"])
def test_changed_preparation_binding_is_rejected(mutation):
    result, manifest, partition = deepcopy(prepared_binding())
    if mutation == "hash":
        result["binding_sha256"] = "e" * 64
    elif mutation == "count":
        manifest["prospective_request_count"] = 9
    elif mutation == "partition":
        partition["manifest_sha256"] = "f" * 64
    else:
        result["binding"]["contract_sha256" if mutation == "contract" else "max_output_tokens"] = "e" * 64 if mutation == "contract" else 2048
        result["binding_sha256"] = digest(result["binding"])
        manifest["binding_sha256"] = result["binding_sha256"]
    with pytest.raises(ValueError):
        module.validate_preparation_binding(result, manifest, partition, SNAPSHOT)
