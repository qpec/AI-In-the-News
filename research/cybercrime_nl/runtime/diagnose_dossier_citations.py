"""Registered read-only mechanical citation diagnosis; never repairs outputs."""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import hashlib
import html
import json
from pathlib import Path
import re
import statistics
import unicodedata

import dossier_contract_v2 as contract
import prepare_dossiers as preparation
from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-dossier-citation-diagnostics-v1"
ACTIVE_OWNER = preparation.OWNER
OWNER = ACTIVE_OWNER.parent / "cybercrime-nl-dossier-citation-diagnostics-20261023-v1"
PLAN = "99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2"
AMENDMENT = "08c7ad39990dc926e6e74a04e8758fae4423e88341d056e416bc0b5b29b24282"
PUNCTUATION = str.maketrans({"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"',
                           "–": "-", "—": "-", "−": "-", "…": "..."})


def implementation():
    paths = [Path(__file__), Path(contract.__file__), Path(contract.v1.__file__),
             preparation.ROOT / "workbench/run_luna_incident_screening_v2.py",
             preparation.ROOT / "scripts/lean_luna_state.py", preparation.ROOT / "src/newsresearch/runtime.py",
             preparation.ROOT / "src/newsresearch/storage.py", preparation.ROOT / "src/newsresearch/common.py"]
    return {str(path.relative_to(preparation.ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def whitespace(value):
    return re.sub(r"\s+", " ", value).strip()


def formatting(value):
    return "".join(char for char in unicodedata.normalize("NFKC", value) if unicodedata.category(char) != "Cf")


def best_excerpt(quote, source):
    """Bounded deterministic substring heuristic, not an exhaustive alignment."""
    if not quote or not source:
        return {"ratio": 0., "start": 0, "end": 0, "excerpt": ""}
    if quote in source:
        start = source.index(quote)
        return {"ratio": 1., "start": start, "end": start + len(quote), "excerpt": quote}
    matcher = SequenceMatcher(None, quote, source, autojunk=False)
    anchors = {0, max(0, len(source) - len(quote))}
    for block in sorted(matcher.get_matching_blocks(), key=lambda b: (-b.size, b.b, b.a))[:4]:
        if block.size:
            anchors.add(max(0, block.b - block.a))
    shift, width = min(12, max(1, len(quote) // 8)), min(80, max(8, len(quote) // 10))
    candidates = {(max(0, min(len(source), start + delta)),
                   max(0, min(len(source), start + delta + len(quote) + size)))
                  for start in anchors for delta in (-shift, 0, shift) for size in (-width, 0, width)}
    best = (0., 0, 0)
    for start, end in sorted(candidates):
        if start >= end:
            continue
        ratio = SequenceMatcher(None, quote, source[start:end], autojunk=False).ratio()
        if ratio > best[0] or (ratio == best[0] and (start, end) < best[1:]):
            best = (ratio, start, end)
    ratio, start, end = best
    return {"ratio": ratio, "start": start, "end": end, "excerpt": source[start:end]}


def ellipsis_match(quote, source):
    pieces = [whitespace(piece) for piece in re.split(r"\.{3,}|…", quote)]
    pieces = [piece for piece in pieces if piece]
    if len(pieces) < 2:
        return False
    cursor, normalized = 0, whitespace(source)
    for piece in pieces:
        position = normalized.find(piece, cursor)
        if position < 0:
            return False
        cursor = position + len(piece)
    return True


def diagnose_citation(citation, documents):
    identity, field, quote = (citation.get(key) for key in ("document_id", "field", "quote"))
    basic = {"source_alias": identity, "field": field,
             "quote_characters": len(quote) if isinstance(quote, str) else None,
             "quote_sha256": hashlib.sha256(quote.encode()).hexdigest() if isinstance(quote, str) else None}
    if identity not in documents or field not in {"title", "body"} or not isinstance(quote, str) or not quote:
        return {**basic, "exact": False, "category": "invalid_source_or_field"}
    source = documents[identity][field]
    if quote in source:
        return {**basic, "exact": True, "category": "exact"}
    flags = []
    exact_elsewhere = []
    for other_id, document in sorted(documents.items()):
        for other_field in ("title", "body"):
            if quote in document[other_field] and (other_id, other_field) != (identity, field):
                category = ("wrong_field" if other_id == identity else "wrong_source" if other_field == field
                            else "wrong_source_and_field")
                flags.append(category)
                exact_elsewhere.append({"source_alias": other_id, "field": other_field})
    for category, normalize in (
        ("whitespace_only", whitespace),
        ("unicode_canonical_normalization", lambda s: unicodedata.normalize("NFC", s)),
        ("unicode_compatibility_or_formatting", formatting),
        ("punctuation_only", lambda s: s.translate(PUNCTUATION)),
        ("whitespace_and_punctuation", lambda s: whitespace(s.translate(PUNCTUATION))),
        ("case_only", str.casefold),
        ("case_and_whitespace", lambda s: whitespace(s).casefold()),
        ("html_entity_rendering", html.unescape),
    ):
        normalized_quote = normalize(quote)
        if normalized_quote and normalized_quote in normalize(source):
            flags.append(category)
    if ellipsis_match(quote, source):
        flags.append("ellipsis_omission")
    local = best_excerpt(quote, source)
    best = {**local, "source_alias": identity, "field": field}
    for other_id, document in sorted(documents.items()):
        for other_field in ("title", "body"):
            if (other_id, other_field) == (identity, field):
                continue
            candidate = best_excerpt(quote, document[other_field])
            if candidate["ratio"] > best["ratio"]:
                best = {**candidate, "source_alias": other_id, "field": other_field}
    category = flags[0] if flags else ("nonverbatim_high_similarity" if local["ratio"] >= .8
                                      else "nonverbatim_low_similarity")
    changes = Counter()
    for op, a, b, c, d in SequenceMatcher(None, quote, local["excerpt"], autojunk=False).get_opcodes():
        if op != "equal":
            changes[op + "_quote_characters"] += b - a
            changes[op + "_source_characters"] += d - c
    return {**basic, "exact": False, "category": category, "matching_transforms_or_other_locations": flags,
            "exact_other_locations": exact_elsewhere,
            "declared_source_candidate": {key: value for key, value in local.items() if key != "excerpt"},
            "best_packet_candidate": {key: value for key, value in best.items() if key != "excerpt"},
            "character_edit_counts": dict(changes),
            "paraphrase_or_entailment_assessed": False}


def citations(summary):
    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "citations":
                    for i, citation in enumerate(item):
                        yield "/".join([*path, key, str(i)]), citation
                else:
                    yield from walk(item, [*path, key])
        elif isinstance(value, list):
            for i, item in enumerate(value):
                yield from walk(item, [*path, str(i)])
    yield from walk(summary, [])


def range_stats(values):
    return {"count": len(values), "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "median": statistics.median(values) if values else None}


class Diagnostic(Research):
    def __init__(self, workspace, *args, **kwargs):
        if Path(workspace).resolve() == ACTIVE_OWNER.resolve():
            raise AuditError("citation_diagnostic_owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        if data or not self.config.offline:
            raise AuditError("citation_diagnostic_offline_empty_input_required")
        code = implementation()
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "procedure": "Read a consistent immutable-record snapshot of the dossier owner using only its read-only Source adapter. Select completed v2 summary responses rejected with dossier_summary_citation_invalid. Reproduce the frozen parser failure; compare every citation against its declared exact full field and other supplied fields. Classify deterministic Unicode/whitespace/punctuation/case/entity/ellipsis transformations or exact wrong source/field. Use bounded SequenceMatcher candidate spans and edit counts only for unexplained nonverbatim text. No acceptance, output repair, provider calls, retries, cost releases or writes to the active owner. Export metadata only.",
                "limits": "Transform matches and high string similarity are diagnostic candidates, never valid citations or semantic entailment. Nonverbatim strings may be paraphrases but this procedure cannot establish that. Candidate alignment is bounded heuristic, not exhaustive. Selected records/artifacts are verified, not a full replay of the active owner."},
            "question": {"text": "Which mechanical mismatches explain completed v2 summary citation rejections?"},
            "selection": {"rules": "All snapshot responses under the exact v2 amendment, phase summary, completed payload and recorded dossier_summary_citation_invalid; no other corpus or model call.", "source_plan": PLAN, "amendment": AMENDMENT},
            "profile": {"mode": "exploratory", "population_estimate": False},
            "policy": {"method": "read-only-citation-diagnosis-v1", "user_permission": "Diagnose existing pipeline failures within the authorized dossier experiment; no new model calls or source publication.", "new_model_calls": 0, "new_cost_nanousd": 0},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        source = preparation.screening.original.base.pilot.Source(ACTIVE_OWNER)
        try:
            head, observed = source.head(), utc()
            if source.one("cyber_dossier_plan")["_record_id"] != PLAN or source.one("cyber_dossier_execution_amendment")["_record_id"] != AMENDMENT:
                raise AuditError("citation_diagnostic_source_binding_changed")
            summaries = [row for row in source.rows("cyber_dossier_response")
                         if row["phase"] == "summary" and row.get("execution_amendment") == AMENDMENT]
            failed = [row for row in summaries if (row.get("validation_error") or "").endswith("dossier_summary_citation_invalid")]
            records, failures = [], []
            for row in failed:
                packet = source.artifacts.json(row["packet"])
                envelope = source.artifacts.json(row["response"])
                payload = envelope["payload"]
                if payload.get("status") != "completed" or digest(packet["request"]) != row["request"]:
                    raise AuditError("citation_diagnostic_response_binding_changed")
                try:
                    contract.parse_summary(packet, payload)
                except ResearchError as error:
                    if str(error) != "dossier_summary_citation_invalid":
                        raise AuditError("citation_diagnostic_failure_not_reproduced") from error
                else:
                    raise AuditError("citation_diagnostic_failure_not_reproduced")
                parts = [part for item in payload["output"] if item.get("type") == "message" for part in item["content"]]
                summary = json.loads(parts[0]["text"])
                docs = {doc["document_id"]: doc for doc in packet["wire_documents"]}
                rows = [{"path": path, **diagnose_citation(citation, docs)} for path, citation in citations(summary)]
                invalid = [result for result in rows if not result["exact"]]
                if not invalid:
                    raise AuditError("citation_diagnostic_missing_invalid_quote")
                failures.extend(invalid)
                records.append({"response_record": row["_record_id"], "packet_artifact": row["packet"],
                    "response_artifact": row["response"], "citations": len(rows), "invalid_citations": invalid,
                    "exact_citations": len(rows) - len(invalid), "failure_reproduced": True})
            result = {"method": METHOD, "observed_at": observed, "source_head": head, "versions": versions,
                "source_owner": str(ACTIVE_OWNER), "source_plan": PLAN, "execution_amendment": AMENDMENT,
                "v2_summary_responses_in_snapshot": len(summaries), "selected_failed_responses": len(failed),
                "failed_response_records": [row["_record_id"] for row in failed],
                "citations_in_failed_responses": sum(row["citations"] for row in records),
                "invalid_citation_occurrences": len(failures),
                "unique_invalid_source_field_quote_triples": len({(row["response_record"], item["source_alias"], item["field"], item["quote_sha256"])
                    for row in records for item in row["invalid_citations"]}),
                "primary_categories": dict(Counter(item["category"] for item in failures)),
                "diagnostic_flag_counts": dict(Counter(flag for item in failures for flag in item.get("matching_transforms_or_other_locations", []))),
                "quote_character_lengths": range_stats([item["quote_characters"] for item in failures if item["quote_characters"] is not None]),
                "declared_source_candidate_similarity": range_stats([item["declared_source_candidate"]["ratio"] for item in failures if "declared_source_candidate" in item]),
                "best_packet_candidate_similarity": range_stats([item["best_packet_candidate"]["ratio"] for item in failures if "best_packet_candidate" in item]),
                "private_metadata_artifact": self.ledger.artifacts.put(records),
                "verified_source_artifacts": self.ledger.artifacts.put(sorted(source.artifacts.checked)),
                "new_model_calls": 0, "new_cost_nanousd": 0, "outputs_modified": False,
                "semantic_paraphrase_or_entailment_assessed": False,
                "exact_chat_presentation_capture_supported": False}
        finally:
            source.close()
        if implementation() != code:
            raise AuditError("citation_diagnostic_code_changed")
        identifier = self.ledger.record(session, "dossier_citation_diagnostic", digest([observed, head]), result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    study = Diagnostic(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Diagnose exact citation failures without repair or new model calls",
                                       actor="codex:dossier-citation-diagnostic")))
    finally:
        study.close()
