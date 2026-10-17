"""Pure exact-request reconstruction and conservative production eligibility.

This module performs no research reads, storage, network or model operations.
An audited Research.execute caller supplies verified preparation artifacts, a
freshly reconciled exclusion capsule, and archive rows read after durable intent.
The caller must verify whole-archive bytes before and after streaming and retain
every disposition. Eligibility is operational only, never an event judgement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from newsresearch.common import digest

import luna_multibatch as core
from prepare_luna_multibatch import normalize_context, retention_reason

METHOD = "luna-batch-production-eligibility-v1"
REQUIRED_CHECKS = frozenset({"sealed_body_validation", "stopped_extraction_lineage",
                             "prior_speed_attempt", "unresolved_prior_attempt"})
AVAILABLE_STATES = frozenset({"ready", "alias", "manual_context_check", "shard_oversized"})
UNAVAILABLE_STATES = frozenset({"retention_unavailable", "body_unavailable", "record_unavailable"})
SELECTORS = ("source_sha256", "retained_body_sha256")


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{field}_must_be_sha256")
    return value


def _locator(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "archive_path", "archive_sha256", "stream", "line", "row_bytes_sha256"
    }:
        raise ValueError("invalid_source_locator")
    if (not isinstance(value["archive_path"], str) or not value["archive_path"]
            or value["stream"] != "artikelen.jsonl" or type(value["line"]) is not int
            or value["line"] < 1):
        raise ValueError("invalid_source_locator")
    _sha(value["archive_sha256"], "archive_sha256")
    _sha(value["row_bytes_sha256"], "row_bytes_sha256")
    return dict(value)


def locator_from_legacy(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize retained pilot provenance only; do not invent missing values."""
    line = provenance.get("line_number", provenance.get("jsonl_line"))
    row_hash = provenance.get("row_sha256", provenance.get("exact_row_bytes_sha256"))
    if (("line_number" in provenance and "jsonl_line" in provenance
         and provenance["line_number"] != provenance["jsonl_line"])
            or ("row_sha256" in provenance and "exact_row_bytes_sha256" in provenance
                and provenance["row_sha256"] != provenance["exact_row_bytes_sha256"])):
        raise ValueError("legacy_locator_alias_conflict")
    return _locator({"archive_path": provenance.get("bundle"),
                     "archive_sha256": provenance.get("bundle_sha256"),
                     "stream": "artikelen.jsonl", "line": line,
                     "row_bytes_sha256": row_hash})


def _partition(partition: Mapping[str, Any]) -> tuple[str, str, dict[str, str]]:
    corpus = partition.get("corpus_id")
    if corpus not in {"incident-reports", "cybercrime"}:
        raise ValueError("invalid_partition_corpus")
    manifest = _sha(partition.get("manifest_sha256"), "manifest_sha256")
    bundles = partition.get("manifest", {}).get("bundles")
    if not isinstance(bundles, list) or not bundles:
        raise ValueError("partition_bundles_unavailable")
    hashes = {}
    for bundle in bundles:
        if not isinstance(bundle.get("path"), str) or not bundle["path"] or bundle["path"] in hashes:
            raise ValueError("partition_bundle_invalid_or_duplicate")
        hashes[bundle["path"]] = _sha(bundle.get("sha256"), "archive_sha256")
    return corpus, manifest, hashes


def validate_preparation_binding(
    result: Mapping[str, Any], manifest: Mapping[str, Any], partition: Mapping[str, Any],
    snapshot: core.ContractSnapshot,
) -> None:
    """Verify saved preparations against the current explicit immutable inputs.

    This does not verify artifact bytes or current filesystem checksums. Those
    checks belong to the audited artifact reader and archive-verification phase.
    """
    corpus, manifest_hash, _ = _partition(partition)
    binding = result.get("binding")
    if not isinstance(binding, dict) or result.get("binding_sha256") != digest(binding):
        raise ValueError("preparation_binding_hash_mismatch")
    if (result.get("corpus_id") != corpus or manifest.get("corpus_id") != corpus
            or manifest.get("manifest_sha256") != manifest_hash
            or binding.get("partition") != dict(partition)
            or manifest.get("binding_sha256") != result["binding_sha256"]
            or manifest.get("versions") != result.get("versions")
            or manifest.get("shard_plan_artifact") != result.get("shard_plan_artifact")):
        raise ValueError("preparation_partition_or_lineage_mismatch")
    if (binding.get("contract_sha256") != snapshot.contract_sha256
            or binding.get("model") != core.MODEL
            or binding.get("max_output_tokens") != core.DEFAULT_MAX_OUTPUT_TOKENS
            or binding.get("reasoning_effort") != "none"):
        raise ValueError("preparation_contract_or_parameters_changed")
    if (manifest.get("prospective_request_count") != result.get("totals", {}).get("requests")
            or sum(chunk["rows"] for chunk in manifest.get("descriptor_chunks", []))
            != result.get("totals", {}).get("rows")):
        raise ValueError("preparation_manifest_count_mismatch")


def make_exclusion_capsule(
    rows: Iterable[Mapping[str, Any]], *, corpus_manifests: Mapping[str, str],
    checks: Mapping[str, Any], provenance: Mapping[str, Any],
    sealed_body_hashes: Iterable[str] = (),
) -> dict[str, Any]:
    """Freeze a source-free exclusion capsule from an audited owner inspection.

    Every required check must carry reconciled=True and source_count. Each row
    names one original source and all applicable reasons, with its raw article
    and/or complete retained-body hash. Exact-body matches are intentionally
    conservative: changed archive copies stay aside rather than leaking sealed
    evidence or silently retrying earlier model exposure. They are not negatives.
    """
    if set(checks) != REQUIRED_CHECKS:
        raise ValueError("exclusion_checks_incomplete")
    if not isinstance(provenance, Mapping) or not provenance:
        raise ValueError("exclusion_provenance_required")
    manifests = dict(corpus_manifests)
    if not manifests or not set(manifests) <= {"incident-reports", "cybercrime"}:
        raise ValueError("exclusion_corpus_binding_invalid")
    for value in manifests.values():
        _sha(value, "manifest_sha256")
    normalized: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seen = set()
    for incoming in rows:
        row = dict(incoming)
        source = _sha(row.get("source_version"), "source_version")
        if source in seen or row.get("corpus_id") not in manifests:
            raise ValueError("exclusion_source_duplicate_or_corpus_unbound")
        seen.add(source)
        reasons = row.get("reasons")
        if (not isinstance(reasons, list) or not reasons or len(reasons) != len(set(reasons))
                or not set(reasons) <= REQUIRED_CHECKS):
            raise ValueError("exclusion_reasons_invalid")
        selectors = {field: _sha(row[field], field) for field in SELECTORS if row.get(field) is not None}
        if not selectors:
            raise ValueError("exclusion_source_identity_unavailable")
        if "sealed_body_validation" in reasons and "retained_body_sha256" not in selectors:
            raise ValueError("sealed_exclusion_requires_full_body_hash")
        item: dict[str, Any] = {"source_version": source, "corpus_id": row["corpus_id"],
                                "reasons": sorted(reasons), **selectors}
        if row.get("source_locator") is not None:
            item["source_locator"] = _locator(row["source_locator"])
        normalized.append(item)
        counts.update(reasons)
    for reason, check in checks.items():
        if (not isinstance(check, Mapping) or check.get("reconciled") is not True
                or type(check.get("source_count")) is not int or check["source_count"] != counts[reason]):
            raise ValueError("exclusion_check_unreconciled_or_count_mismatch")
    sealed_hashes = list(sealed_body_hashes)
    if len(sealed_hashes) != len(set(sealed_hashes)):
        raise ValueError("sealed_body_hash_duplicate")
    for body_hash in sealed_hashes:
        _sha(body_hash, "sealed_body_sha256")
    if any("sealed_body_validation" in row["reasons"]
           and row["retained_body_sha256"] not in sealed_hashes for row in normalized):
        raise ValueError("sealed_body_frame_does_not_cover_source_rows")
    capsule_value = {"method": METHOD, "corpus_manifests": manifests, "checks": dict(checks),
             "provenance": dict(provenance), "sources": sorted(normalized, key=lambda r: r["source_version"]),
             "sealed_body_hashes": sorted(sealed_hashes),
             "matching": "same-corpus exact raw-article or retained-full-body or archived-row identity; held-out body hashes protected across corpora; no semantic judgement"}
    return {**capsule_value, "capsule_sha256": digest(capsule_value)}


@dataclass(frozen=True)
class ExclusionIndex:
    capsule_sha256: str
    corpus_manifests: dict[str, str]
    selectors: dict[tuple[str, str, str], tuple[dict[str, Any], ...]]
    sealed_body_hashes: frozenset[str]


def build_exclusion_index(capsule: Mapping[str, Any]) -> ExclusionIndex:
    rebuilt = make_exclusion_capsule(capsule.get("sources", []),
        corpus_manifests=capsule.get("corpus_manifests", {}), checks=capsule.get("checks", {}),
        provenance=capsule.get("provenance", {}), sealed_body_hashes=capsule.get("sealed_body_hashes", []))
    if rebuilt != dict(capsule):
        raise ValueError("exclusion_capsule_changed")
    selectors: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rebuilt["sources"]:
        for field in SELECTORS:
            if field in row:
                selectors[(row["corpus_id"], field, row[field])].append(row)
        if "source_locator" in row:
            selectors[(row["corpus_id"], "source_locator", digest(row["source_locator"]))].append(row)
    return ExclusionIndex(rebuilt["capsule_sha256"], rebuilt["corpus_manifests"],
                          {key: tuple(value) for key, value in selectors.items()},
                          frozenset(rebuilt["sealed_body_hashes"]))


def index_from_owner_export(export: Mapping[str, Any], corpus_manifests: Mapping[str, str]) -> ExclusionIndex:
    """Adapt the audited budget runner's explicit original-owner export.

    The entire validation-fold body set is required, including representatives
    outside the old grouping membership. Protecting the same sealed bytes in
    another corpus is evaluation-leakage prevention, not cross-corpus grouping.
    """
    rename = {"stopped_extraction": "stopped_extraction_lineage"}
    categories = export.get("categories")
    if (export.get("completed") is not True or not isinstance(categories, list)
            or len(categories) != len(set(categories))
            or {rename.get(key, key) for key in categories} != REQUIRED_CHECKS):
        raise ValueError("owner_export_incomplete_categories")
    counts = export.get("category_counts")
    rows = export.get("rows")
    sealed = export.get("sealed_body_hashes")
    if (not isinstance(counts, Mapping) or set(counts) != set(categories)
            or not isinstance(rows, list) or not isinstance(sealed, list)
            or export.get("sealed_body_hash_count") != len(sealed)):
        raise ValueError("owner_export_missing_counts_or_sealed_body_frame")
    partition_hashes = export.get("partition", {}).get("file_sha256", {})
    if any(partition_hashes.get(f"corpora/{corpus}/manifest.json") != value
           for corpus, value in corpus_manifests.items()):
        raise ValueError("owner_export_manifest_binding_changed")
    normalized = []
    for row in rows:
        item = {key: row[key] for key in ("source_version", "corpus_id", *SELECTORS) if key in row}
        item["reasons"] = [rename.get(reason, reason) for reason in row.get("reasons", [])]
        if "archive_provenance" in row:
            item["source_locator"] = locator_from_legacy(row["archive_provenance"])
        normalized.append(item)
    checks = {str(rename.get(key, key)): {"reconciled": True, "source_count": counts[key]} for key in categories}
    provenance = {"owner_export_sha256": digest(dict(export)), "source_owner": export.get("source_owner"),
                  "original_result": export.get("original_result"), "protocol": export.get("protocol"),
                  "created_at": export.get("created_at")}
    capsule = make_exclusion_capsule(normalized, corpus_manifests=corpus_manifests, checks=checks,
                                     provenance=provenance, sealed_body_hashes=sealed)
    return build_exclusion_index(capsule)


def assess_descriptor(descriptor: Mapping[str, Any], index: ExclusionIndex) -> dict[str, Any]:
    corpus = descriptor.get("corpus_id")
    if corpus not in index.corpus_manifests or descriptor.get("manifest_sha256") != index.corpus_manifests[corpus]:
        raise ValueError("eligibility_corpus_or_manifest_unreconciled")
    matches: dict[str, dict[str, Any]] = {}
    selectors = {field: _sha(descriptor.get(field), field) for field in SELECTORS}
    selectors["source_locator"] = digest(_locator(descriptor.get("source_locator")))
    for field, value in selectors.items():
        for row in index.selectors.get((corpus, field, value), ()):
            match = matches.setdefault(row["source_version"], {"source_version": row["source_version"],
                "reasons": row["reasons"], "matched_by": []})
            match["matched_by"].append(field)
    sealed_match = descriptor["retained_body_sha256"] in index.sealed_body_hashes
    reasons = {reason for item in matches.values() for reason in item["reasons"]}
    if sealed_match:
        reasons.add("sealed_body_validation")
    return {"eligible": not matches and not sealed_match, "capsule_sha256": index.capsule_sha256,
            "global_sealed_body_match": sealed_match, "reasons": sorted(reasons),
            "matches": sorted(matches.values(), key=lambda r: r["source_version"])}


def reconcile_rows(rows: Iterable[Mapping[str, Any]], index: ExclusionIndex) -> Iterator[dict[str, Any]]:
    """Reconcile all frozen archive rows in original order, without source I/O.

    Existing aliases cannot be promoted when their canonical row is withheld.
    Every unavailable/deferred row is yielded explicitly. Only `eligible` rows
    may be considered for a budgeted production request; alias reuse remains
    a separate mapping and is not an accepted finding or prior-output reuse.
    """
    canonical: dict[str, dict[str, Any]] = {}
    seen_rows: set[str] = set()
    seen_requests: set[str] = set()
    for incoming in rows:
        row = dict(incoming)
        if not isinstance(row.get("id"), str) or row["id"] in seen_rows:
            raise ValueError("prepared_row_id_missing_or_duplicate")
        seen_rows.add(row["id"])
        corpus = row.get("corpus_id")
        locator = _locator(row.get("source_locator"))
        if corpus not in index.corpus_manifests or row["id"] != digest({"corpus_id": corpus,
                "manifest_sha256": index.corpus_manifests[corpus], "source_locator": locator}):
            raise ValueError("prepared_row_identity_or_partition_changed")
        state = row.get("state")
        if state in UNAVAILABLE_STATES:
            yield {**row, "production_eligibility": "unavailable", "eligibility": {
                "eligible": False, "capsule_sha256": index.capsule_sha256,
                "reasons": [state], "matches": []}}
            continue
        if state not in AVAILABLE_STATES or not isinstance(row.get("descriptor"), Mapping):
            raise ValueError("prepared_row_state_or_descriptor_invalid")
        descriptor = row["descriptor"]
        if (row.get("corpus_id") != descriptor.get("corpus_id")
                or row.get("source_locator") != descriptor.get("source_locator")):
            raise ValueError("prepared_row_descriptor_lineage_mismatch")
        custom = descriptor.get("custom_id")
        if not isinstance(custom, str) or custom in seen_requests:
            raise ValueError("prepared_descriptor_custom_id_missing_or_duplicate")
        seen_requests.add(custom)
        decision = assess_descriptor(descriptor, index)
        if state == "alias":
            canonical_id = row.get("canonical_row_id")
            if not isinstance(canonical_id, str):
                raise ValueError("alias_canonical_lineage_missing_or_changed")
            target = canonical.get(canonical_id)
            if (target is None or target["descriptor"]["custom_id"] != row.get("canonical_custom_id")
                    or any(descriptor.get(key) != target["descriptor"].get(key) for key in
                           ("corpus_id", "manifest_sha256", "request_body_sha256"))):
                raise ValueError("alias_canonical_lineage_missing_or_changed")
            if not target["eligibility"]["eligible"]:
                decision["eligible"] = False
                decision["reasons"] = sorted(set(decision["reasons"]) | {"canonical_request_withheld"})
            decision["canonical_row_id"] = target["id"]
            disposition = "alias" if decision["eligible"] else "set_aside"
        else:
            if state != "ready":
                decision["eligible"] = False
                decision["reasons"] = sorted(set(decision["reasons"]) | {state})
            disposition = "eligible" if decision["eligible"] else "set_aside"
        output = {**row, "production_eligibility": disposition, "eligibility": decision}
        if state != "alias":
            canonical[row["id"]] = output
        yield output


def materialize_descriptor(
    descriptor: Mapping[str, Any], raw_row: bytes, *, partition: Mapping[str, Any],
    contract_snapshot: core.ContractSnapshot, count_tokens: Callable[[str], int],
) -> dict[str, Any]:
    """Reconstruct one saved request byte-for-byte, retaining the original cap.

    Caller owns retention permission, audited archive reads and eligibility.
    The unchanged raw-row retention guard is rechecked here before body access.
    Hash, metadata, packet, schema or token-proxy drift fails closed. No lowering
    of max_output_tokens, rephrasing or automatic citation repair is supported.
    """
    corpus, manifest_hash, archives = _partition(partition)
    locator = _locator(descriptor.get("source_locator"))
    if (descriptor.get("corpus_id") != corpus or descriptor.get("manifest_sha256") != manifest_hash
            or archives.get(locator["archive_path"]) != locator["archive_sha256"]):
        raise ValueError("materialize_partition_or_archive_mismatch")
    if (type(raw_row) is not bytes or hashlib.sha256(raw_row).hexdigest() != locator["row_bytes_sha256"]):
        raise ValueError("materialize_raw_row_hash_mismatch")
    if (descriptor.get("contract_sha256") != contract_snapshot.contract_sha256
            or descriptor.get("max_output_tokens") != core.DEFAULT_MAX_OUTPUT_TOKENS):
        raise ValueError("materialize_contract_or_output_limit_changed")
    row = json.loads(raw_row)
    if not isinstance(row, dict) or retention_reason(row):
        raise ValueError("materialize_retention_unavailable")
    article = row.get("article")
    if not isinstance(article, dict) or digest(article) != descriptor.get("source_sha256"):
        raise ValueError("materialize_article_hash_mismatch")
    if not isinstance(article.get("body"), str) or not article["body"].strip():
        raise ValueError("materialize_body_unavailable")
    normalized, states = normalize_context(article)
    record = core.build_request_record(normalized, corpus_id=corpus, manifest_sha256=manifest_hash,
        source_locator=locator, source_sha256=digest(article),
        max_output_tokens=core.DEFAULT_MAX_OUTPUT_TOKENS, count_tokens=count_tokens,
        token_proxy_method="cl100k_base_serialized_body_plus_32", context_availability=states,
        contract_snapshot=contract_snapshot)
    if record["descriptor"] != dict(descriptor):
        differing = sorted(set(record["descriptor"]) ^ set(descriptor) |
                           {key for key in record["descriptor"] if record["descriptor"][key] != descriptor.get(key)})
        raise ValueError("materialize_descriptor_changed:" + ",".join(differing))
    return record
