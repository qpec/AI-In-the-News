"""Audit saved article metadata within one corpus; no classification or model calls.

Only aggregate field-state/type counts and provider-ID multiplicities are retained.
Raw titles, bodies, entity names, category values, identifiers and URLs are never
returned or saved. Run once per corpus through the dedicated protected owner.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import zipfile

from newsresearch.common import Config, Context, Json, ResearchError, digest
from newsresearch.legacy import sha256, within
from newsresearch.runtime import Research, audited_handler

METHOD = "partitioned-article-scope-metadata-v1"
WORKSPACE_NAME = "article-scope-metadata-audit-20261017-v1"
SCRIPT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
CORPORA = ("incident-reports", "cybercrime")
STATES = ("absent", "null", "empty", "populated")
TYPES = ("null", "boolean", "number", "string", "array", "object")
ARTICLE_FIELDS = (
    "uri", "url", "title", "body", "dataType", "categories", "concepts", "eventUri",
    "isDuplicate", "duplicateList", "sim", "lang", "date", "time", "dateTime", "dateTimePub",
    "source", "sentiment", "relevance", "wgt", "importance", "socialScore", "authors",
    "image", "links", "videos", "shares", "wordCount", "bodyLen", "contentLength",
    "articleType", "type", "genre", "eventTypeUri", "eventTypes", "mentions", "signals",
    "facticity", "factuality", "retention", "metadata_only", "quarantined", "storyUri",
    "originalArticle", "location", "extractedDates",
)
SOURCE_FIELDS = ("uri", "title", "dataType", "type", "location", "country", "ranking",
                 "rank", "alexaGlobalRank", "alexaCountryRank", "importance", "details")
ROW_FIELDS = ("article", "collection_cohort", "retention", "metadata_only", "quarantined",
              "quarantine", "retention_exclusion", "body_missing_reason")
CONCEPT_TYPES = ("org", "person", "loc", "wiki", "organization", "location")
DATA_TYPES = ("news", "pr", "blog")
MISSING = object()
LIMITATIONS = [
    "Counts describe saved metadata and article rows, not accepted event dossiers or eligibility.",
    "Provider eventUri, article IDs and source URIs are hints, not same-event truth, independent reporting or publisher ownership verification.",
    "Multiple source URIs can name related outlets; distinct publisher ownership is unmeasured.",
    "Missing event IDs, source IDs and unobserved companion reports remain unknown, never singleton exclusions.",
    "Metadata-only or quarantine markers are counted only if explicitly saved; prior protected-workspace quarantine is not re-evaluated or inferred here.",
    "The two corpus namespaces are isolated; shared articles across corpora are not compared or merged.",
    "No single-event classification, recall evaluation, relevance threshold, deletion, set-aside decision or cost-saving estimate is produced.",
]


def state(value: Any) -> str:
    if value is MISSING:
        return "absent"
    if value is None:
        return "null"
    if isinstance(value, str) and not value.strip():
        return "empty"
    if isinstance(value, (dict, list)) and not value:
        return "empty"
    return "populated"


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise ResearchError("metadata_non_json_type")


def nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def count_bucket(count: int) -> str:
    return str(count) if count < 3 else ("3-5" if count < 6 else "6-10" if count < 11 else "11+")


def private_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_url(value: Any) -> str | None:
    """Conservative URL identity only: lowercase scheme/host, drop fragment.

    Do not remove queries or rewrite paths: neither publication identity nor
    duplicate article identity can be inferred from those changes.
    """
    if not nonblank(value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or parsed.username:
            return None
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
    except ValueError:
        return None


class FieldCounts:
    def __init__(self) -> None:
        self.states: Counter[str] = Counter()
        self.types: Counter[str] = Counter()

    def add(self, value: Any) -> None:
        self.states[state(value)] += 1
        if value is not MISSING:
            self.types[json_type(value)] += 1

    def result(self) -> Json:
        return {"denominator": sum(self.states.values()),
                "states": {key: self.states[key] for key in STATES},
                "types": {key: self.types[key] for key in TYPES}}


class MetadataCounts:
    """Pure aggregate implementation; production rows enter only in audited handler."""
    def __init__(self) -> None:
        self.rows = 0
        self.fields = {"article." + key: FieldCounts() for key in ARTICLE_FIELDS}
        self.fields.update({"article.source." + key: FieldCounts() for key in SOURCE_FIELDS})
        self.fields.update({"row." + key: FieldCounts() for key in ROW_FIELDS})
        self.keys: Counter[str] = Counter()
        self.enums: dict[str, Counter[str]] = {key: Counter() for key in
            ("article.dataType", "article.source.dataType", "article.lang", "article.isDuplicate")}
        self.list_counts: dict[str, Counter[str]] = {key: Counter() for key in
            ("categories", "concepts", "duplicateList")}
        self.item_fields = {key: FieldCounts() for key in
            ("category.score", "category.wgt", "category.uri", "concept.score", "concept.wgt", "concept.type", "concept.uri")}
        self.items: Counter[str] = Counter()
        self.concept_type_items: Counter[str] = Counter()
        self.concept_type_articles: Counter[str] = Counter()
        self.events: dict[str, Json] = {}
        self.identity_counts: Counter[str] = Counter()
        self.provider_ids: set[str] = set()
        self.provider_events: dict[str, set[str]] = {}
        self.provider_sources: dict[str, set[str]] = {}
        self.urls: set[str] = set()
        self.body_counts: Counter[str] = Counter()
        self.explicit_markers: Counter[str] = Counter()

    def add(self, row: Json) -> None:
        article = row.get("article")
        if not isinstance(article, dict):
            raise ResearchError("metadata_article_object_missing")
        self.rows += 1
        source = article.get("source")
        if not isinstance(source, dict):
            source = {}
        for prefix, keys, obj in (("article.", ARTICLE_FIELDS, article),
                                  ("article.source.", SOURCE_FIELDS, source), ("row.", ROW_FIELDS, row)):
            for key in keys:
                self.fields[prefix + key].add(obj.get(key, MISSING))
            self.keys[prefix + "allowlisted_key_occurrences"] += sum(key in keys for key in obj)
            self.keys[prefix + "other_key_occurrences"] += sum(key not in keys for key in obj)
        for name, obj in (("article.dataType", article), ("article.source.dataType", source)):
            value = obj.get("dataType", MISSING)
            label = value if isinstance(value, str) and value in DATA_TYPES else (
                "other_populated" if state(value) == "populated" else state(value))
            self.enums[name][label] += 1
        lang = article.get("lang", MISSING)
        label = lang if isinstance(lang, str) and re.fullmatch("[a-z]{2,3}", lang) else (
            "other_populated" if state(lang) == "populated" else state(lang))
        self.enums["article.lang"][label] += 1
        duplicate = article.get("isDuplicate", MISSING)
        label = str(duplicate).lower() if type(duplicate) is bool else (
            "other_populated" if state(duplicate) == "populated" else state(duplicate))
        self.enums["article.isDuplicate"][label] += 1
        self.body_counts["nonblank_string" if nonblank(article.get("body")) else "missing_or_nontext"] += 1
        for prefix, obj in (("row", row), ("article", article)):
            for key in ("metadata_only", "quarantined"):
                if obj.get(key) is True:
                    self.explicit_markers[prefix + "." + key + "_true"] += 1
            if obj.get("retention") == "metadata_only":
                self.explicit_markers[prefix + ".retention_metadata_only"] += 1
        for field in self.list_counts:
            value = article.get(field)
            if isinstance(value, list):
                self.list_counts[field][count_bucket(len(value))] += 1
        for field, singular in (("categories", "category"), ("concepts", "concept")):
            value = article.get(field)
            if not isinstance(value, list):
                continue
            seen_types = set()
            for item in value:
                self.items[singular + ".items"] += 1
                if not isinstance(item, dict):
                    self.items[singular + ".non_object_items"] += 1
                    continue
                for key in ("score", "wgt", "uri"):
                    self.item_fields[singular + "." + key].add(item.get(key, MISSING))
                if field == "concepts":
                    item_type = item.get("type", MISSING)
                    self.item_fields["concept.type"].add(item_type)
                    label = item_type if isinstance(item_type, str) and item_type in CONCEPT_TYPES else (
                        "other_populated" if state(item_type) == "populated" else state(item_type))
                    self.concept_type_items[label] += 1
                    seen_types.add(label)
            self.concept_type_articles.update(seen_types)
        provider = private_hash(article["uri"]) if nonblank(article.get("uri")) else None
        url = canonical_url(article.get("url"))
        url_hash = private_hash(url) if url is not None else None
        if provider:
            self.provider_ids.add(provider)
            if nonblank(source.get("uri")):
                self.provider_sources.setdefault(provider, set()).add(private_hash(source["uri"]))
        if url_hash:
            self.urls.add(url_hash)
        identity = ("provider:" + provider) if provider else ("url:" + url_hash) if url_hash else None
        self.identity_counts["provider_id" if provider else "url_fallback" if url_hash else "unknown"] += 1
        event = article.get("eventUri")
        if not nonblank(event):
            return
        if provider:
            self.provider_events.setdefault(provider, set()).add(private_hash(str(event)))
        group = self.events.setdefault(private_hash(str(event)), {
            "rows": 0, "provider_ids": set(), "urls": set(), "identities": set(),
            "sources": set(), "source_rows": 0, "identity_unknown_rows": 0})
        group["rows"] += 1
        for key, value in (("provider_ids", provider), ("urls", url_hash), ("identities", identity)):
            if value:
                group[key].add(value)
        if identity is None:
            group["identity_unknown_rows"] += 1
        if nonblank(source.get("uri")):
            group["sources"].add(private_hash(source["uri"]))
            group["source_rows"] += 1

    def result(self) -> Json:
        summary: Counter[str] = Counter()
        multiplicity: dict[str, Counter[str]] = {key: Counter() for key in
            ("provider_ids", "urls", "identities", "sources")}
        for group in self.events.values():
            summary["event_id_groups"] += 1
            summary["rows_with_event_id"] += group["rows"]
            summary["rows_with_event_id_missing_source_uri"] += group["rows"] - group["source_rows"]
            summary["rows_with_event_id_unknown_article_identity"] += group["identity_unknown_rows"]
            for key in multiplicity:
                size = len(group[key])
                multiplicity[key][count_bucket(size)] += 1
                if size >= 2:
                    summary["groups_with_2plus_" + key] += 1
                    summary["rows_in_groups_with_2plus_" + key] += group["rows"]
            if len(group["identities"]) >= 2 and len(group["sources"]) >= 2:
                summary["groups_with_2plus_identities_and_source_uris"] += 1
                summary["rows_in_groups_with_2plus_identities_and_source_uris"] += group["rows"]
            if len(group["sources"]) == 1:
                summary["rows_in_groups_with_one_observed_source_uri"] += group["rows"]
            if len(group["identities"]) == 1:
                summary["rows_in_groups_with_one_observed_identity"] += group["rows"]
        keys = ("event_id_groups", "rows_with_event_id", "rows_with_event_id_missing_source_uri",
                "rows_with_event_id_unknown_article_identity", "groups_with_2plus_identities_and_source_uris",
                "rows_in_groups_with_2plus_identities_and_source_uris", "rows_in_groups_with_one_observed_source_uri",
                "rows_in_groups_with_one_observed_identity")
        summary.update({key: 0 for key in keys})
        for key in multiplicity:
            for prefix in ("groups_with_2plus_", "rows_in_groups_with_2plus_"):
                summary[prefix + key] += 0
        return {"rows": self.rows, "fields": {key: value.result() for key, value in self.fields.items()},
                "allowlisted_key_counts": dict(self.keys), "controlled_value_histograms": self.enums,
                "list_length_histograms": self.list_counts, "list_item_counts": dict(self.items),
                "list_item_fields": {key: value.result() for key, value in self.item_fields.items()},
                "concept_type_item_histogram": dict(self.concept_type_items),
                "concept_type_article_presence": dict(self.concept_type_articles),
                "body_availability": {key: self.body_counts[key] for key in ("nonblank_string", "missing_or_nontext")},
                "explicit_retention_markers": dict(self.explicit_markers),
                "distinct_provider_ids": len(self.provider_ids), "distinct_canonical_urls": len(self.urls),
                "provider_ids_with_multiple_nonblank_event_uris": sum(len(values) > 1 for values in self.provider_events.values()),
                "provider_ids_with_multiple_nonblank_source_uris": sum(len(values) > 1 for values in self.provider_sources.values()),
                "article_identity_rows": {key: self.identity_counts[key] for key in ("provider_id", "url_fallback", "unknown")},
                "provider_event_multiplicity": dict(summary), "event_group_size_histograms": multiplicity,
                "identity_rule": "Exact nonblank provider ID; conservative canonical URL only as fallback. Independent provider-ID and URL multiplicities also shown. No raw identifiers retained.",
                "source_rule": "Exact nonblank article.source.uri; no parent-company or publisher ownership resolution."}


def read_partition(root: Path, corpus: str) -> Json:
    root = root.resolve()
    registry_path = within(root, "corpora/registry.json")
    registry = json.loads(registry_path.read_bytes())
    if (registry.get("cross_corpus_grouping") != "forbidden_by_default"
            or {entry["corpus_id"] for entry in registry.get("corpora", [])} != set(CORPORA)
            or len(registry["corpora"]) != 2):
        raise ResearchError("metadata_partition_registry_invalid")
    manifests = {}
    archive_paths: set[str] = set()
    for entry in registry["corpora"]:
        identifier = entry["corpus_id"]
        expected_path = f"corpora/{identifier}/manifest.json"
        if entry["manifest"] != expected_path or entry["dossier_namespace"] != identifier + ":":
            raise ResearchError("metadata_partition_namespace_invalid")
        path = within(root, expected_path)
        raw = path.read_bytes()
        manifest = json.loads(raw)
        if manifest.get("corpus_id") != identifier or manifest.get("dossier_namespace") != identifier + ":":
            raise ResearchError("metadata_manifest_namespace_invalid")
        bundles = manifest["bundles"]
        if not bundles or len(bundles) != manifest["summary"]["bundles"]:
            raise ResearchError("metadata_manifest_bundle_count_invalid")
        if sum(item["declared_records"] for item in bundles) != manifest["summary"]["declared_article_records"]:
            raise ResearchError("metadata_manifest_row_count_invalid")
        for item in bundles:
            archive = within(root, item["path"])
            resolved = str(archive).casefold()
            if resolved in archive_paths or archive.suffix != ".zip" or not archive.is_file():
                raise ResearchError("metadata_manifest_archive_overlap_or_missing")
            if not re.fullmatch("[a-f0-9]{64}", item["sha256"]):
                raise ResearchError("metadata_manifest_hash_invalid")
            archive_paths.add(resolved)
        manifests[identifier] = {"path": expected_path, "sha256": hashlib.sha256(raw).hexdigest(), "content": manifest}
    selected = manifests[corpus]
    for item in selected["content"].get("metadata_sources", []):
        if sha256(within(root, item["path"])) != item["sha256"]:
            raise ResearchError("metadata_inventory_hash_mismatch")
    verify_declared_inventory(root, corpus, selected["content"])
    return {"registry_sha256": sha256(registry_path), "manifests": {
        key: {"path": value["path"], "sha256": value["sha256"]} for key, value in manifests.items()},
        "corpus_id": corpus, "manifest_sha256": selected["sha256"],
        "manifest": selected["content"], "resolved_root": str(root)}


def verify_declared_inventory(root: Path, corpus: str, manifest: Json) -> None:
    """Reconcile the selected manifest with original source-free inventories."""
    expected: dict[str, Json] = {}
    if corpus == "incident-reports":
        inventory = json.loads(within(root, "metadata/source-inventory.json").read_bytes())
        if not inventory.get("complete") or inventory.get("pending"):
            raise ResearchError("metadata_source_inventory_incomplete")
        for item in inventory["files"]:
            if item.get("kind") == "article-bundle":
                expected[item["path"]] = {key: item[key] for key in
                    ("path", "sha256", "cohort", "declared_records", "declared_with_text")}
    else:
        for base, snapshot in (("topics/cybercrime-nl", "2023-2026"),
                               ("topics/cybercrime-nl/extensions/2020-2023", "2020-2023-extension")):
            checksums = {line.split(maxsplit=1)[1]: line.split(maxsplit=1)[0]
                for line in within(root, base + "/SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines() if line.strip()}
            raw = within(root, base + "/coverage-by-year.csv").read_bytes()
            if hashlib.sha256(raw).hexdigest() != checksums["coverage-by-year.csv"]:
                raise ResearchError("metadata_coverage_inventory_hash_mismatch")
            for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
                relative = f"articles/articles-{row['year']}.zip"
                path = base + "/" + relative
                expected[path] = {"path": path, "sha256": checksums[relative], "cohort": "cybercrime-nl",
                    "snapshot": snapshot, "date_start": row["date_start"], "date_end": row["date_end"],
                    "declared_records": int(row["returned"]), "declared_with_text": int(row["body_present"])}
    if {item["path"]: item for item in manifest["bundles"]} != expected:
        raise ResearchError("metadata_manifest_differs_from_inventory")


def scan_archive(path: Path, counts: MetadataCounts) -> int:
    before = counts.rows
    with zipfile.ZipFile(path) as archive:
        if archive.namelist().count("artikelen.jsonl") != 1:
            raise ResearchError("metadata_archive_article_stream_invalid")
        with archive.open("artikelen.jsonl") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    raise ResearchError("metadata_archive_json_invalid") from None
                if not isinstance(row, dict):
                    raise ResearchError("metadata_archive_row_invalid")
                counts.add(row)
    return counts.rows - before


def render(result: Json) -> str:
    aggregate = result["aggregate"]
    event = aggregate["provider_event_multiplicity"]
    lines = [f"**Saved metadata audit: {result['corpus_id']}.**", "",
        f"Scanned {aggregate['rows']:,} article rows in {len(result['bundles'])} verified archives; "
        "0 failed or pending archives. Zero models, embeddings, retrieval queries or grouping decisions.", "",
        "| Saved field | Populated | Empty | Null | Absent |", "| --- | ---: | ---: | ---: | ---: |"]
    shown = ("article.dataType", "article.source.dataType", "article.categories", "article.concepts",
             "article.eventUri", "article.isDuplicate", "article.duplicateList", "article.sim", "article.lang",
             "article.date", "article.dateTimePub", "article.source.uri", "article.source.location",
             "article.articleType", "article.type", "article.genre", "article.eventTypeUri", "article.eventTypes",
             "article.mentions", "article.signals", "article.facticity", "article.factuality",
             "article.storyUri", "article.originalArticle", "article.location", "article.extractedDates")
    for key in shown:
        values = aggregate["fields"][key]["states"]
        lines.append(f"| {key} | {values['populated']:,} | {values['empty']:,} | {values['null']:,} | {values['absent']:,} |")
    lines.extend(["", "Populated means a non-null, nonempty JSON value; the protected aggregate also records JSON types. "
        "Candidate articleType/genre/signal field names are availability checks, not claims that the API supplies them.", "",
        "| Controlled metadata values | Row counts |", "| --- | --- |"])
    for key, histogram in aggregate["controlled_value_histograms"].items():
        lines.append(f"| {key} | " + "; ".join(f"{label}: {count:,}" for label, count in sorted(histogram.items())) + " |")
    lines.extend(["", "**Provider-event metadata hints, within this corpus only:**", "",
        f"- Nonblank event IDs: {event['rows_with_event_id']:,} rows across {event['event_id_groups']:,} exact IDs; "
        f"{aggregate['rows'] - event['rows_with_event_id']:,} rows have absent/null/empty/non-string IDs.",
        f"- At least two distinct observed article identities and two source URIs: "
        f"{event['groups_with_2plus_identities_and_source_uris']:,} provider-ID groups / "
        f"{event['rows_in_groups_with_2plus_identities_and_source_uris']:,} rows.",
        f"- One observed source URI: {event['rows_in_groups_with_one_observed_source_uri']:,} rows; "
        f"event-ID rows missing a source URI: {event['rows_with_event_id_missing_source_uri']:,}. "
        "Neither is a confirmed singleton exclusion.",
        f"- Distinct provider IDs: {aggregate['distinct_provider_ids']:,}; "
        f"distinct conservative canonical URLs: {aggregate['distinct_canonical_urls']:,}; "
        f"rows lacking both identities: {aggregate['article_identity_rows']['unknown']:,}.", "",
        f"Provider-ID conflicts across saved rows: {aggregate['provider_ids_with_multiple_nonblank_event_uris']:,} IDs have "
        f"multiple nonblank event IDs; {aggregate['provider_ids_with_multiple_nonblank_source_uris']:,} IDs have multiple source URIs. "
        "These are metadata conflicts; repeated versions of one provider article are not counted as separate article identities.", "",
        f"Saved body availability: {aggregate['body_availability']['nonblank_string']:,} nonblank strings; "
        f"{aggregate['body_availability']['missing_or_nontext']:,} missing/blank/nontext. No source content is reproduced.", "",
        "**Limits:** " + " ".join(LIMITATIONS), "",
        "The exact Markdown is retained as a protected note/artifact. `record_presentation` does not support "
        "this metadata-note kind; no supported presentation record or verified chat delivery is claimed."])
    return "\n".join(lines) + "\n"


class MetadataAuditResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.name != WORKSPACE_NAME:
            raise ResearchError("metadata_audit_requires_dedicated_owner")
        if config is not None and not config.offline:
            raise ResearchError("metadata_audit_requires_offline_configuration")
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if (not self.config.offline or set(data) != {"data_root", "corpus_id"}
                or not isinstance(data["data_root"], str) or data["corpus_id"] not in CORPORA):
            raise ResearchError("metadata_audit_invalid_request")
        for table in ("sources", "passages", "attempts"):
            if self.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                raise ResearchError("metadata_audit_owner_must_not_contain_sources_or_models")
        self.ledger.append(session, "metadata.partition.read.intended", data)
        partition = read_partition(Path(data["data_root"]), data["corpus_id"])
        root = Path(partition["resolved_root"])
        binding = {"method": METHOD, "script_sha256": SCRIPT_SHA256, **partition}
        key = digest(binding)
        methods = {
            "protocol": {"method": METHOD, "binding": binding, "field_paths": list(MetadataCounts().fields),
                "procedure": "Verify both manifest namespaces are disjoint and internally consistent; reconcile the selected corpus manifest to its original inventories and verify selected metadata/archive SHA-256 hashes before streaming. Stream all selected rows once, count allowlisted field states/types, bounded enum values and hashed in-memory ID multiplicities; verify row totals and post-read hashes. No semantic inference, saved raw values or source reads outside handler.",
                "limitations": LIMITATIONS},
            "selection": {"rules": "Every article row in exactly one manifest corpus; no content-based exclusion or cross-corpus comparison.",
                "corpus_id": data["corpus_id"], "manifest_sha256": partition["manifest_sha256"]},
            "question": {"text": "Which saved metadata fields are available to design a later single-event, multiple-publisher scope filter?"},
            "dossier_definition": {"unit": "One real-world event with two or more different reporting publishers; this metadata audit does not establish event identity or publisher independence.", "corpus_id": data["corpus_id"]},
            "profile": {"mode": "exploratory", "population_estimate": False, "method": METHOD,
                "unit": "technical metadata coverage and exact provider-ID multiplicities; not dossier measurements",
                "corpus_id": data["corpus_id"], "manifest_sha256": partition["manifest_sha256"]},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD + "-" + key,
            "content": content})["id"] for kind, content in methods.items()}
        bound = Context(context.objective, context.actor, versions)
        bundles = partition["manifest"]["bundles"]
        self.ledger.append(session, "metadata.archive.verification.intended", {"binding": key, "versions": versions,
            "bundles": [{"path": row["path"], "sha256": row["sha256"]} for row in bundles]})
        for bundle in bundles:
            if sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError("metadata_archive_pre_scan_hash_mismatch")
        self.ledger.append(session, "metadata.scan.intended", {"binding": key, "versions": versions,
            "expected_rows": partition["manifest"]["summary"]["declared_article_records"]})
        counts = MetadataCounts()
        reports = []
        for bundle in bundles:
            path = within(root, bundle["path"])
            self.ledger.append(session, "metadata.bundle.scan.intended", {"corpus_id": data["corpus_id"],
                "manifest_sha256": partition["manifest_sha256"], "path": bundle["path"], "sha256": bundle["sha256"]})
            rows = scan_archive(path, counts)
            if rows != bundle["declared_records"]:
                raise ResearchError("metadata_archive_row_count_mismatch")
            if sha256(path) != bundle["sha256"]:
                raise ResearchError("metadata_archive_post_scan_hash_mismatch")
            report = {"path": bundle["path"], "sha256": bundle["sha256"], "rows": rows,
                      "compressed_bytes": path.stat().st_size}
            self.ledger.append(session, "metadata.bundle.scan.completed", report)
            reports.append(report)
        if counts.rows != partition["manifest"]["summary"]["declared_article_records"]:
            raise ResearchError("metadata_corpus_row_count_mismatch")
        result = {"method": METHOD, "corpus_id": data["corpus_id"], "manifest_sha256": partition["manifest_sha256"],
                  "binding": binding, "versions": versions, "bundles": reports, "aggregate": counts.result(),
                  "failed_archives": 0, "pending_archives": 0, "model_calls": 0, "new_embeddings": 0,
                  "membership_changes": 0, "record_presentation_supported": False, "limitations": LIMITATIONS}
        markdown = render(result)
        artifact = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        self.ledger.append(session, "metadata.report.saved", {"artifact": artifact,
            "state": "prepared; no verified chat delivery", "binding": key})
        result["markdown_artifact"] = artifact
        note = self._version(session, bound, {"kind": "note", "key": METHOD + "-result-" + key, "content": result})["id"]
        return {"id": note, **result, "markdown": markdown,
                "content_path": str(self.ledger.artifacts.root / artifact)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--corpus-id", choices=CORPORA, required=True)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = MetadataAuditResearch(args.workspace, config=config)
    try:
        result = engine.execute("status", {"data_root": str(args.data_root), "corpus_id": args.corpus_id},
            objective="Audit saved article metadata availability and provider event-ID multi-source hints in one isolated corpus; no filtering, models or grouping",
            actor="codex:article-scope-metadata-audit")
        print(result["markdown"], flush=True)
        print(json.dumps({"note": result["id"], "report": result["content_path"],
            "corpus_id": result["corpus_id"], "manifest_sha256": result["manifest_sha256"],
            "record_presentation_supported": False}), flush=True)
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
