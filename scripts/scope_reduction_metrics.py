"""Pure technical workload experiments; production use requires Research.execute.

No semantic labels, sources, model inputs or raw identifiers leave this module.
The caller binds one corpus manifest, registers this implementation, records
scan intent and protects the hash-only lineage. Equality here is a *candidate*
for exact, version-bound gateway reuse under the declared packet contract.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time
import hashlib
import re
from typing import Any

from newsresearch.common import Json, ResearchError, canonical, digest, require_no_credentials

METHOD = "partitioned-exact-packet-workload-v1"
CORPORA = ("incident-reports", "cybercrime")
DATE_FIELDS = ("date", "time", "dateTime", "dateTimePub")
PACKET_FIELDS = ("uri", "url", "title", "body", *DATE_FIELDS, "lang", "source")
NEUTRAL_FIELDS = ("title", "body", *DATE_FIELDS, "lang")
NEUTRAL_CONTRACT = {
    "version": "source-neutral-focus-extraction-packet-v1",
    "fields": list(NEUTRAL_FIELDS),
    "task": "Source-neutral focal-event screening and literal span extraction only",
    "forbidden_cached_decisions": ["publisher eligibility", "event membership", "credibility", "source identity"],
    "output_grounding": "relative offsets into exact title/body; rebind and validate separately for each source",
    "future_reuse_requires": "same corpus, packet, model, prompt, schema, parameters and code/version bindings",
}
FOCUS_FIELDS = ("title", "body", "lang")
FOCUS_CONTRACT = {
    "version": "intrinsic-single-focus-packet-v1", "fields": list(FOCUS_FIELDS),
    "task": "Intrinsic single-focus versus roundup, non-event or uncertain screening only",
    "forbidden_cached_decisions": ["event extraction", "temporal normalization", "event identity",
                                   "publisher eligibility", "credibility", "source identity"],
    "output_grounding": "relative title/body spans revalidated per publication appearance",
    "future_reuse_requires": "same corpus, packet, model, prompt, schema, parameters and code/version bindings",
}
FIELD_STATES = ("absent", "null", "blank", "bad_type", "nonblank")
STATES = (
    "unavailable_retention", "unavailable_body", "missing_publisher",
    "missing_event_id", "missing_article_identity", "one_known_source",
    "insufficient_distinct_article_identities", "multi_source_candidate",
)
MISSING = object()


def field_state(value: Any) -> str:
    if value is MISSING:
        return "absent"
    if value is None:
        return "null"
    if not isinstance(value, str):
        return "bad_type"
    return "nonblank" if value.strip() else "blank"


def string_hash(value: Any) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if field_state(value) == "nonblank" else None


def exact_packet(article: Json, fields: tuple[str, ...] = PACKET_FIELDS) -> Json:
    """Presence is distinct from null; values are never stripped or rewritten."""
    return {name: {"present": name in article, "value": article.get(name)} for name in fields}


def context_complete(article: Json) -> bool:
    """Conservative reuse: absent context never creates apparent savings."""
    source = article.get("source")
    if not isinstance(source, dict) or field_state(source.get("uri", MISSING)) != "nonblank":
        return False
    if any(field_state(article.get(name, MISSING)) != "nonblank" for name in ("title", "lang")):
        return False
    if re.fullmatch(r"[a-z]{2,3}", article["lang"]) is None:
        return False
    # At least one date-bearing field, not merely a time of day, must be known.
    if not any(field_state(article.get(name, MISSING)) == "nonblank" for name in
               ("date", "dateTime", "dateTimePub")):
        return False
    if any(name in article and field_state(article[name]) != "nonblank" for name in DATE_FIELDS):
        return False
    try:
        for name in DATE_FIELDS:
            if name not in article:
                continue
            parser = date.fromisoformat if name == "date" else time.fromisoformat if name == "time" else datetime.fromisoformat
            parser(article[name])
    except ValueError:
        return False
    # Exact provider identity or exact URL establishes the publication appearance.
    return any(field_state(article.get(name, MISSING)) == "nonblank" for name in ("uri", "url"))


def _pair(rows: list[Json]) -> tuple[Json, Json] | None:
    """Lexicographic hash order; no selection based on text length/content."""
    ordered = sorted(rows, key=lambda row: row["selection_hash"])
    if len(ordered) < 2:
        return None
    first = ordered[0]
    for other in ordered[1:]:
        if other["publisher_hash"] != first["publisher_hash"] and other["article_hash"] != first["article_hash"]:
            return first, other
    # A first row can conflict with both valid endpoints: a@X, a@Y, b@X.
    second = next((row for row in ordered[1:] if row["publisher_hash"] != first["publisher_hash"]), None)
    if second is not None:
        for other in ordered[1:]:
            if other["publisher_hash"] != second["publisher_hash"] and other["article_hash"] != second["article_hash"]:
                return second, other
    return None


class ScopeReductionCounts:
    """Streaming accumulator; raw rows/text are never retained on the instance."""

    def __init__(self, corpus_id: str) -> None:
        if corpus_id not in CORPORA:
            raise ResearchError("scope_reduction_unknown_corpus")
        self.corpus_id = corpus_id
        self.rows: list[Json] = []
        self.locators: set[str] = set()
        self.fields: dict[str, Counter[str]] = {
            name: Counter() for name in ("body", "title", "lang", "uri", "url", "eventUri", "source.uri", *DATE_FIELDS)
        }
        self.row_states: Counter[str] = Counter()
        self._finished = False

    def add(self, row: Json, locator: str) -> None:
        if self._finished:
            raise ResearchError("scope_reduction_already_finalized")
        locator_hash = digest({"corpus": self.corpus_id, "locator": locator})
        if locator_hash in self.locators:
            raise ResearchError("scope_reduction_duplicate_locator")
        self.locators.add(locator_hash)
        record: Json = {"locator_hash": locator_hash, "row_hash": digest(row), "usable": False,
                        "body_hash": None, "packet_hash": None, "reuse_key": None,
                        "neutral_packet_hash": None, "neutral_reuse_key": None,
                        "focus_packet_hash": None, "focus_reuse_key": None,
                        "publisher_hash": None, "article_hash": None, "event_hash": None,
                        "body_chars": 0, "packet_chars": 0, "neutral_packet_chars": 0, "focus_packet_chars": 0,
                        "context_complete": False, "focus_context_complete": False,
                        "selected_first_pair": False, "state": "unavailable_retention"}
        # Check the entire row before using any text or identifiers. Flagged rows
        # retain only a locator/content hash and aggregate unavailable status.
        try:
            require_no_credentials(row)
        except ResearchError:
            self.row_states["credential_flagged"] += 1
            self.rows.append(record)
            return
        article = row.get("article")
        if not isinstance(article, dict):
            self.row_states["article_bad_type_or_missing"] += 1
            record["state"] = "unavailable_body"
            self.rows.append(record)
            return
        source = article.get("source")
        source = source if isinstance(source, dict) else {}
        for name, counter in self.fields.items():
            value = source.get("uri", MISSING) if name == "source.uri" else article.get(name, MISSING)
            counter[field_state(value)] += 1
        record["publisher_hash"] = string_hash(source.get("uri", MISSING))
        uri = string_hash(article.get("uri", MISSING))
        url = string_hash(article.get("url", MISSING))
        record["article_hash"] = digest({"kind": "provider", "value": uri}) if uri else (
            digest({"kind": "exact_url", "value": url}) if url else None)
        record["event_hash"] = string_hash(article.get("eventUri", MISSING))
        body = article.get("body", MISSING)
        if field_state(body) != "nonblank":
            record["state"] = "unavailable_body"
            self.rows.append(record)
            return
        # Explicit archival exclusions are honored independently of text presence.
        excluded = any(obj.get("metadata_only") is True or obj.get("quarantined") is True
                       or obj.get("retention") == "metadata_only" for obj in (row, article))
        if excluded:
            self.row_states["explicit_retention_excluded"] += 1
            self.rows.append(record)
            return
        packet = exact_packet(article)
        packet_hash = digest(packet)
        neutral_packet = exact_packet(article, NEUTRAL_FIELDS)
        neutral_hash = digest(neutral_packet)
        focus_packet = exact_packet(article, FOCUS_FIELDS)
        focus_hash = digest(focus_packet)
        complete = context_complete(article)
        focus_complete = (field_state(article.get("title", MISSING)) == "nonblank"
                          and isinstance(article.get("lang"), str)
                          and re.fullmatch(r"[a-z]{2,3}", article["lang"]) is not None)
        record.update({"usable": True, "body_hash": string_hash(body), "packet_hash": packet_hash,
                       "context_complete": complete, "body_chars": len(body),
                       "packet_chars": len(canonical(packet)),
                       "reuse_key": digest({"method": METHOD, "corpus": self.corpus_id,
                                            "packet_hash": packet_hash}) if complete else
                                    digest({"unreusable": locator_hash}),
                       "neutral_packet_hash": neutral_hash,
                       "neutral_reuse_key": digest({"contract": NEUTRAL_CONTRACT, "corpus": self.corpus_id,
                                                    "packet_hash": neutral_hash}) if complete else
                                            digest({"unreusable_neutral": locator_hash}),
                       "neutral_packet_chars": len(canonical(neutral_packet)),
                       "focus_packet_hash": focus_hash,
                       "focus_reuse_key": digest({"contract": FOCUS_CONTRACT, "corpus": self.corpus_id,
                                                  "packet_hash": focus_hash}) if focus_complete else
                                          digest({"unreusable_focus": locator_hash}),
                       "focus_packet_chars": len(canonical(focus_packet)),
                       "focus_context_complete": focus_complete,
                       "state": "unresolved"})
        record["selection_hash"] = digest({"corpus": self.corpus_id, "event": record["event_hash"],
                                           "publisher": record["publisher_hash"], "article": record["article_hash"],
                                           "packet": packet_hash, "locator": locator_hash})
        self.rows.append(record)

    def _finalize(self) -> None:
        if self._finished:
            return
        events: dict[str, list[Json]] = defaultdict(list)
        for row in self.rows:
            if row["usable"] and row["event_hash"] and row["publisher_hash"] and row["article_hash"]:
                events[row["event_hash"]].append(row)
        pairs = {event: _pair(rows) for event, rows in events.items()}
        for pair in pairs.values():
            if pair is not None:
                for row in pair:
                    row["selected_first_pair"] = True
        for row in self.rows:
            if not row["usable"]:
                continue
            if row["publisher_hash"] is None:
                state = "missing_publisher"
            elif row["event_hash"] is None:
                state = "missing_event_id"
            elif row["article_hash"] is None:
                state = "missing_article_identity"
            elif pairs[row["event_hash"]] is not None:
                state = "multi_source_candidate"
            elif len({item["publisher_hash"] for item in events[row["event_hash"]]}) < 2:
                state = "one_known_source"
            else:
                state = "insufficient_distinct_article_identities"
            row["state"] = state
        self._finished = True

    def lineage(self) -> list[Json]:
        """Hash-only source mapping. Still store this in protected audit storage."""
        self._finalize()
        return [dict(row) for row in sorted(self.rows, key=lambda row: row["locator_hash"])]

    def result(self) -> Json:
        self._finalize()
        usable = [row for row in self.rows if row["usable"]]
        packets: dict[str, list[Json]] = defaultdict(list)
        neutral_packets: dict[str, list[Json]] = defaultdict(list)
        focus_packets: dict[str, list[Json]] = defaultdict(list)
        bodies: dict[str, list[Json]] = defaultdict(list)
        for row in usable:
            packets[row["reuse_key"]].append(row)
            neutral_packets[row["neutral_reuse_key"]].append(row)
            focus_packets[row["focus_reuse_key"]].append(row)
            bodies[row["body_hash"]].append(row)
        representatives = [min(rows, key=lambda row: row["locator_hash"]) for rows in packets.values()]
        selected_keys = {row["reuse_key"] for row in usable if row["selected_first_pair"]}
        prioritized = [row for row in representatives if row["reuse_key"] in selected_keys]
        deferred = [row for row in representatives if row["reuse_key"] not in selected_keys]
        neutral_representatives = [min(rows, key=lambda row: row["locator_hash"]) for rows in neutral_packets.values()]
        neutral_selected_keys = {row["neutral_reuse_key"] for row in usable if row["selected_first_pair"]}
        neutral_initial = [row for row in neutral_representatives if row["neutral_reuse_key"] in neutral_selected_keys]
        neutral_deferred = [row for row in neutral_representatives if row["neutral_reuse_key"] not in neutral_selected_keys]
        focus_representatives = [min(rows, key=lambda row: row["locator_hash"]) for rows in focus_packets.values()]
        focus_selected_keys = {row["focus_reuse_key"] for row in usable if row["selected_first_pair"]}
        focus_initial = [row for row in focus_representatives if row["focus_reuse_key"] in focus_selected_keys]
        focus_deferred = [row for row in focus_representatives if row["focus_reuse_key"] not in focus_selected_keys]
        states = Counter(row["state"] for row in self.rows)
        state_rows = {name: states[name] for name in STATES}
        assert sum(state_rows.values()) == len(self.rows)
        assert len(prioritized) + len(deferred) == len(representatives)
        unavailable = len(self.rows) - len(usable)
        safe_reuse = len(usable) - len(representatives)
        assert unavailable + safe_reuse + len(prioritized) + len(deferred) == len(self.rows)
        neutral_reuse = len(usable) - len(neutral_representatives)
        assert unavailable + neutral_reuse + len(neutral_initial) + len(neutral_deferred) == len(self.rows)
        focus_reuse = len(usable) - len(focus_representatives)
        assert unavailable + focus_reuse + len(focus_initial) + len(focus_deferred) == len(self.rows)
        raw_chars = sum(row["packet_chars"] for row in usable)
        rep_chars = sum(row["packet_chars"] for row in representatives)
        initial_chars = sum(row["packet_chars"] for row in prioritized)
        deferred_chars = sum(row["packet_chars"] for row in deferred)
        assert initial_chars + deferred_chars == rep_chars
        neutral_baseline_chars = sum(row["neutral_packet_chars"] for row in usable)
        neutral_rep_chars = sum(row["neutral_packet_chars"] for row in neutral_representatives)
        neutral_initial_chars = sum(row["neutral_packet_chars"] for row in neutral_initial)
        neutral_deferred_chars = sum(row["neutral_packet_chars"] for row in neutral_deferred)
        assert neutral_initial_chars + neutral_deferred_chars == neutral_rep_chars
        focus_baseline_chars = sum(row["focus_packet_chars"] for row in usable)
        focus_rep_chars = sum(row["focus_packet_chars"] for row in focus_representatives)
        focus_initial_chars = sum(row["focus_packet_chars"] for row in focus_initial)
        focus_deferred_chars = sum(row["focus_packet_chars"] for row in focus_deferred)
        assert focus_initial_chars + focus_deferred_chars == focus_rep_chars
        conflicts = [rows for rows in bodies.values() if len({row["packet_hash"] for row in rows}) > 1]
        identity_events: dict[str, set[str]] = defaultdict(set)
        identity_publishers: dict[str, set[str]] = defaultdict(set)
        for row in usable:
            if row["article_hash"]:
                if row["event_hash"]:
                    identity_events[row["article_hash"]].add(row["event_hash"])
                if row["publisher_hash"]:
                    identity_publishers[row["article_hash"]].add(row["publisher_hash"])
        result: Json = {
            "method": METHOD, "corpus_id": self.corpus_id,
            "rows_total": len(self.rows), "usable_body_rows": len(usable), "unavailable_rows": unavailable,
            "retention_flags": dict(sorted(self.row_states.items())),
            "disjoint_row_states": state_rows,
            "field_states_among_guard_passed_article_objects": {
                name: {state: count[state] for state in FIELD_STATES} for name, count in self.fields.items()},
            "packet_contract": {"fields": list(PACKET_FIELDS), "absence_and_null_distinct": True,
                                "exact_source_object": True, "source_and_publication_context_preserved": True,
                                "version_bound_gateway_reuse_required": True},
            "exact_packet_experiment": {
                "baseline_rows": len(usable), "distinct_processing_units": len(representatives),
                "exact_redundant_rows": safe_reuse,
                "rows_ineligible_for_reuse_missing_context": sum(not row["context_complete"] for row in usable),
                "baseline_packet_unicode_chars": raw_chars, "representative_packet_unicode_chars": rep_chars,
                "exact_redundant_packet_unicode_chars": raw_chars - rep_chars,
                "baseline_body_unicode_chars": sum(row["body_chars"] for row in usable),
                "representative_body_unicode_chars": sum(row["body_chars"] for row in representatives),
            },
            "source_neutral_packet_experiment": {
                "contract": NEUTRAL_CONTRACT, "contract_sha256": digest(NEUTRAL_CONTRACT),
                "conditional_on_this_contract": True, "actual_model_reuse_executed": False,
                "baseline_rows": len(usable), "distinct_processing_units": len(neutral_representatives),
                "exact_redundant_rows": neutral_reuse,
                "rows_ineligible_for_reuse_missing_context": sum(not row["context_complete"] for row in usable),
                "baseline_packet_unicode_chars": neutral_baseline_chars,
                "representative_packet_unicode_chars": neutral_rep_chars,
                "exact_redundant_packet_unicode_chars": neutral_baseline_chars - neutral_rep_chars,
                "representative_body_unicode_chars": sum(row["body_chars"] for row in neutral_representatives),
                "families_with_multiple_known_publishers": sum(
                    len({row["publisher_hash"] for row in rows if row["publisher_hash"]}) > 1
                    for rows in neutral_packets.values()),
                "publisher_appearances_retained": sum(row["publisher_hash"] is not None for row in usable),
                "initial_distinct_processing_units": len(neutral_initial),
                "deferred_distinct_processing_units": len(neutral_deferred),
                "initial_packet_unicode_chars": neutral_initial_chars,
                "deferred_packet_unicode_chars": neutral_deferred_chars,
                "conservation": {"all_rows": len(self.rows), "unavailable": unavailable,
                                 "exact_redundant": neutral_reuse, "initial": len(neutral_initial),
                                 "deferred": len(neutral_deferred), "equation_holds": True},
            },
            "focus_only_packet_experiment": {
                "contract": FOCUS_CONTRACT, "contract_sha256": digest(FOCUS_CONTRACT),
                "conditional_on_this_contract": True, "actual_model_reuse_executed": False,
                "baseline_rows": len(usable), "distinct_processing_units": len(focus_representatives),
                "exact_redundant_rows": focus_reuse,
                "rows_ineligible_for_reuse_missing_context": sum(not row["focus_context_complete"] for row in usable),
                "baseline_packet_unicode_chars": focus_baseline_chars,
                "representative_packet_unicode_chars": focus_rep_chars,
                "exact_redundant_packet_unicode_chars": focus_baseline_chars - focus_rep_chars,
                "representative_body_unicode_chars": sum(row["body_chars"] for row in focus_representatives),
                "publication_appearances_retained": len(usable),
                "initial_distinct_processing_units": len(focus_initial),
                "deferred_distinct_processing_units": len(focus_deferred),
                "initial_packet_unicode_chars": focus_initial_chars,
                "deferred_packet_unicode_chars": focus_deferred_chars,
                "conservation": {"all_rows": len(self.rows), "unavailable": unavailable,
                                 "exact_redundant": focus_reuse, "initial": len(focus_initial),
                                 "deferred": len(focus_deferred), "equation_holds": True},
            },
            "body_only_diagnostic_not_safe_reuse": {
                "distinct_exact_bodies": len(bodies),
                "raw_repeated_body_rows": len(usable) - len(bodies),
                "body_families_with_different_packet_context": len(conflicts),
                "rows_in_context_conflicting_body_families": sum(map(len, conflicts)),
            },
            "provider_first_pair_experiment": {
                "candidate_event_buckets": len({row["event_hash"] for row in usable if row["selected_first_pair"]}),
                "candidate_rows": states["multi_source_candidate"],
                "initial_selected_publication_appearances": sum(row["selected_first_pair"] for row in usable),
                "initial_distinct_processing_units": len(prioritized),
                "deferred_distinct_processing_units": len(deferred),
                "initial_packet_unicode_chars": initial_chars,
                "deferred_packet_unicode_chars": deferred_chars,
                "selection": "lexicographic SHA256 ordering; distinct exact source URI and article identity",
                "deferred_are_excluded": False, "same_event_confirmed": False,
                "single_focus_confirmed": False, "equivalent_to_full_evidence": False,
            },
            "article_identity_conflicts": {
                "multiple_event_ids": sum(len(values) > 1 for values in identity_events.values()),
                "multiple_publisher_ids": sum(len(values) > 1 for values in identity_publishers.values()),
            },
            "conservation": {"all_rows": len(self.rows), "unavailable": unavailable,
                             "exact_redundant": safe_reuse, "initial": len(prioritized), "deferred": len(deferred),
                             "equation_holds": True},
            "lineage_sha256": digest(self.lineage()),
            "semantic_exclusions": 0, "model_calls": 0, "new_embeddings": 0,
            "limitations": [
                "Technical processing units are not event dossiers or accepted memberships.",
                "Exact source URIs are publisher proxies; aliases and ownership are unverified.",
                "Provider event IDs are retrieval hints, not same-event or single-focus truth.",
                "Missing fields and unavailable text are unresolved, never negative findings or savings.",
                "Strict equality measures possible reuse only for this packet and identical task/version bindings.",
                "Source-neutral equality is conditional on the specified intrinsic screening/span-extraction contract; publisher/event decisions remain separate.",
                "Focus-only equality omits dates and publisher metadata solely for intrinsic article focus, never event extraction or eligibility decisions.",
                "First-pair processing postpones other evidence; it is not demonstrated total-workload saving.",
                "Unicode character counts are measured input volume, not token counts, prices or invoices.",
                "No semantic classification, recall evaluation, deletion or dossier adoption occurred.",
            ],
        }
        require_no_credentials(result)
        return result
