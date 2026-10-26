"""Freeze exact screened Cybercrime NL articles for a separately budgeted dossier study."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import run_screening_v2 as screening
from newsresearch.common import AuditError, Config, canonical, digest, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.runtime import audited_handler

ROOT = screening.original.ROOT
METHOD = "cybercrime-nl-dossier-inputs-20261023-v1"
OWNER = screening.original.base.pilot.BASE / "cybercrime-nl-dossiers-20261023-v1"
SCREEN_PLAN = "14fad3705b1e8fde7ecbeb8436d8c66c7eb69fe187da05ba6a5d521cae78317f"
FINAL_REPORT = "66c0547f71a5477ab023696a135a3b2ca427e08cc5e725d48942ccbcc940df38"
EXPECTED = {"selected_articles": 61_089, "eligible_articles": 7_743,
            "unique_documents": 6_691, "selected_alias_articles": 1_052,
            "routes": {"keep": 7_743, "exclude": 47_790, "review": 5_239,
                       "invalid_or_unknown": 5, "retention_unavailable": 251, "sealed_validation": 61}}
BUDGET_NANOUSD = 50_000_000_000


def sha_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def implementation():
    bound = screening.implementation()
    paths = [Path(__file__), ROOT / "workbench/run_luna_incident_screening_v2.py",
             ROOT / "scripts/lean_luna_state.py", ROOT / "src/newsresearch/embeddings.py",
             ROOT / "src/newsresearch/common.py", ROOT / "src/newsresearch/runtime.py",
             ROOT / "src/newsresearch/storage.py", ROOT / "uv.lock"]
    bound.update({str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
    return bound


def route_for(row):
    decision = row.get("decision") or {}
    if decision.get("status") != "valid":
        return "refusal" if decision.get("status") == "refusal" else "invalid_or_unknown"
    route = decision.get("route")
    if route not in {"keep", "exclude", "review"}:
        raise AuditError("dossier_invalid_screen_route")
    if route == "keep":
        labels = {name: answer.get("label") for name, answer in decision.get("answers", {}).items()}
        if (labels != {"event_scope": "single_event", "cybercrime_incident": "yes", "netherlands_nexus": "direct"}
                or row["unknown_or_billing_hold"]):
            raise AuditError("dossier_keep_not_settled_three_axis_positive")
    return route


def select_articles(rows, mapping, plan_id):
    """Source-free selection with every original identity retained in coverage."""
    decisions = {row["custom_id"]: row for row in rows}
    if len(decisions) != len(rows):
        raise AuditError("dossier_duplicate_screen_response")
    for row in rows:
        if row["plan"] != plan_id or row["corpus"] != "cybercrime":
            raise AuditError("dossier_other_plan_or_corpus")
    identities, request_hashes, represented, originals = set(), {}, set(), {}
    coverage, selected, counts = [], [], Counter()
    for entry in mapping:
        key = entry["custom_id"]
        if key in identities or entry["corpus"] != "cybercrime":
            raise AuditError("dossier_duplicate_or_other_corpus_article")
        identities.add(key)
        originals[key] = entry
        item = {name: entry[name] for name in ("custom_id", "canonical_custom_id", "request_hash",
                                              "exact_input_reuse", "source_locator")}
        screening.original.base.pilot.materializer.materialize._locator(item["source_locator"])
        if entry["request_hash"] is None:
            route = entry["status"]
            if route not in {"retention_unavailable", "sealed_validation"}:
                raise AuditError("dossier_unknown_source_disposition")
            item["screening_decision_record"] = None
        else:
            canonical_id = entry["canonical_custom_id"]
            if canonical_id not in decisions:
                raise AuditError("dossier_final_mapping_has_unfinished_request")
            represented.add(canonical_id)
            row = decisions[canonical_id]
            if row["request"] != entry["request_hash"]:
                raise AuditError("dossier_screen_input_hash_mismatch")
            if entry["exact_input_reuse"] != (key != canonical_id):
                raise AuditError("dossier_alias_identity_mismatch")
            prior = request_hashes.setdefault(canonical_id, entry["request_hash"])
            if prior != entry["request_hash"]:
                raise AuditError("dossier_alias_request_conflict")
            route = route_for(row)
            item["screening_decision_record"] = row["_record_id"]
        item["screening_route"] = route
        counts[route] += 1
        coverage.append(item)
        if route == "keep":
            selected.append(item)
    if represented != set(decisions):
        raise AuditError("dossier_response_missing_from_article_frame")
    for canonical_id in represented:
        if (canonical_id not in identities or originals[canonical_id]["canonical_custom_id"] != canonical_id
                or originals[canonical_id]["exact_input_reuse"]
                or originals[canonical_id]["request_hash"] != request_hashes[canonical_id]):
            raise AuditError("dossier_missing_canonical_article")
    selected_ids = {r["canonical_custom_id"] for r in selected}
    return selected, coverage, {key: decisions[key] for key in sorted(selected_ids)}, dict(counts)


def exact_document(request, row):
    """Extract the exact supplied title/body, preserving all Unicode and whitespace."""
    if digest(request) != row["request"]:
        raise AuditError("dossier_original_request_hash_mismatch")
    article = json.loads(request["input"])
    if (set(article) != {"title", "body"} or not isinstance(article["title"], str)
            or not isinstance(article["body"], str) or not article["body"].strip()
            or screening.original.core.request_for(article["title"], article["body"]) != request):
        raise AuditError("dossier_original_input_contract_changed")
    descriptor = row["descriptor"]
    if (descriptor["corpus_id"] != "cybercrime" or descriptor["custom_id"] != row["custom_id"]
            or descriptor["retained_body_sha256"] != sha_text(article["body"])):
        raise AuditError("dossier_source_descriptor_mismatch")
    document_id = digest({"method": METHOD, "screening_request": row["request"], "input": digest(article)})
    return {"document_id": document_id, "canonical_custom_id": row["custom_id"], **article,
            "title_sha256": sha_text(article["title"]), "body_sha256": sha_text(article["body"]),
            "input_sha256": digest(article), "screening_request_hash": row["request"],
            "canonical_original_source_sha256": descriptor["source_sha256"],
            "canonical_source_descriptor": descriptor, "screening_decision_record": row["_record_id"],
            "retention": "permitted_by_verified_screening_source_preparation",
            "metadata_scope": "Exact screened title/body only; no inferred language, publisher, publication date or event date."}


def profile(values):
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "total": 0, "minimum": None, "maximum": None, "mean": None, "percentiles": {}}
    return {"count": len(ordered), "total": sum(ordered), "minimum": ordered[0], "maximum": ordered[-1],
            "mean": sum(ordered) / len(ordered),
            "percentiles": {str(p): ordered[max(0, math.ceil(len(ordered) * p / 100) - 1)] for p in (50, 90, 95, 99)}}


class Study(screening.original.base.pilot.Study):
    def __init__(self, workspace, *args, **kwargs):
        if Path(workspace).resolve() == screening.OWNER.resolve():
            raise AuditError("dossier_owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        if not self.config.offline or data:
            raise AuditError("dossier_preparation_offline_empty_input_required")
        self.absent("cyber_dossier_preparation_intent")
        code = implementation()
        definitions = {name: (ROOT / "research/shared/dossiers" / name).read_text(encoding="utf-8")
                       for name in ("DEFINITION.md", "METHODOLOGY.md")}
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "procedure": "Freeze the final full Cybercrime NL screening keep selection from a verified read-only snapshot. Require valid, settled single_event + cybercrime yes + direct Netherlands nexus. Verify every original article identity and exact-input alias. Read only selected original Decisions request artifacts, never re-fetch or truncate source text. Preserve exact title/body and canonical source descriptor, and full source-free coverage. Store immutable child documents, article mapping, input/length profiles and provenance. No paid call or old screening liability transfer. This is offline preparation, not candidate grouping or dossier acceptance.",
                "source_integrity": "Selected record projection and content-addressed artifact verification; frozen final report and plan identity. Not a full replay of the historical screening owner.",
                "definition_snapshot": definitions,
                "limits": "Screening labels remain provisional; aliases share exact model input but remain distinct source rows. Token counts are cl100k_base proxies for Luna. No vector coverage assertion without a separate verified source/profile intersection."},
            "question": {"text": "Which retained clear single-event Cybercrime NL reports describe the same specific occurrence under the generic dossier definition?"},
            "selection": {"rules": "All and only settled valid screening keep decisions, expanded to every exact-title/body alias, from the fixed final cybercrime report. No incident-report corpus or uncertain/excluded/sealed/unavailable/technical-failure source enters grouping.",
                "screening_owner": str(screening.OWNER), "screening_plan": SCREEN_PLAN, "final_report": FINAL_REPORT,
                "expected": EXPECTED},
            "dossier_definition": {"unit": definitions["DEFINITION.md"]},
            "profile": {"mode": "exploratory", "population_estimate": False, "semantic_screening_validated": False},
            "policy": {"method": "separate-cybercrime-dossier-budget-v1", "user_permission": "User explicitly authorized applying all four dossier processes to the cybercrime selection with a new USD50 total cap.",
                "total_budget_nanousd": BUDGET_NANOUSD, "prior_screening_cost_transferred_nanousd": 0,
                "scope": "One total cap for dossier vector work, pilot, verification, summaries, assignment, recovery and audit; stage-specific execution plans and durable reservations precede paid calls.",
                "paid_calls_in_this_preparation": 0, "old_owners_and_holds_unchanged": True},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        self.ledger.record(session, "cyber_dossier_preparation_intent", METHOD,
                           {"versions": versions, "implementation": code, "at": utc()})
        source = screening.original.base.pilot.Source(screening.OWNER)
        try:
            observed, head = utc(), source.head()
            plan, continuation = source.one("cyber_screen_plan"), source.one("cyber_preparation_continuation")
            reports = source.rows("cyber_screen_report")
            report = reports[-1]
            if (plan["_record_id"] != SCREEN_PLAN or report["_record_id"] != FINAL_REPORT
                    or report["plan"] != SCREEN_PLAN or not report["dispatch_complete"]
                    or plan["implementation"] != screening.original.implementation()
                    or continuation["implementation"] != screening.implementation()):
                raise AuditError("dossier_final_screening_binding_changed")
            rows = source.rows("cyber_screen_decision")
            mapping_raw = source.artifacts.read(report["article_results_artifact"])
            mapping = [json.loads(line) for line in mapping_raw.splitlines() if line]
            articles, coverage, kept, routes = select_articles(rows, mapping, SCREEN_PLAN)
            observed_frame = {"selected_articles": len(mapping), "eligible_articles": len(articles),
                              "unique_documents": len(kept),
                              "selected_alias_articles": sum(a["exact_input_reuse"] for a in articles), "routes": routes}
            if observed_frame != EXPECTED:
                raise AuditError("dossier_selected_frame_changed")
            encoding = offline_tokenizer()
            documents, by_canonical = [], {}
            measurements = {key: [] for key in ("title_tokens", "body_tokens", "title_body_json_tokens",
                                                "title_characters", "body_characters", "title_body_json_bytes")}
            per_document_tokens = {}
            for canonical_id, row in kept.items():
                request_raw = source.artifacts.read(row["request"])
                document = exact_document(json.loads(request_raw), row)
                if self.ledger.artifacts.put_bytes(request_raw) != row["request"]:
                    raise AuditError("dossier_copied_request_hash_changed")
                title, body = document["title"], document["body"]
                text = canonical({"title": title, "body": body})
                measured = {"title_tokens": len(encoding.encode(title, disallowed_special=())),
                            "body_tokens": len(encoding.encode(body, disallowed_special=())),
                            "title_body_json_tokens": len(encoding.encode(text, disallowed_special=())),
                            "title_characters": len(title), "body_characters": len(body),
                            "title_body_json_bytes": len(text.encode("utf-8"))}
                for key, value in measured.items():
                    measurements[key].append(value)
                artifact = self.ledger.artifacts.put(document)
                entry = {key: document[key] for key in ("document_id", "canonical_custom_id", "title_sha256", "body_sha256",
                         "input_sha256", "screening_request_hash", "canonical_original_source_sha256", "screening_decision_record")}
                entry.update(document_artifact=artifact, measurements=measured)
                documents.append(entry)
                by_canonical[canonical_id] = document["document_id"]
                per_document_tokens[canonical_id] = measured["title_body_json_tokens"]
                if len(documents) % 1000 == 0:
                    print(json.dumps({"phase": "preparing_dossiers", "documents": len(documents), "planned": len(kept)}), flush=True)
            for article in articles:
                article["document_id"] = by_canonical[article["canonical_custom_id"]]
            selected_by_id = {article["custom_id"]: article for article in articles}
            for entry in coverage:
                if entry["custom_id"] in selected_by_id:
                    entry["document_id"] = selected_by_id[entry["custom_id"]]["document_id"]
            profiles = {key: profile(values) for key, values in measurements.items()}
            profiles["article_weighted_title_body_json_tokens"] = profile(
                [per_document_tokens[a["canonical_custom_id"]] for a in articles])
            profiles["body_token_threshold_counts"] = {str(limit): sum(v > limit for v in measurements["body_tokens"])
                                                       for limit in (4096, 6000, 8191, 8192, 16384, 32768)}
            profiles["title_body_json_token_threshold_counts"] = {
                str(limit): sum(v > limit for v in measurements["title_body_json_tokens"])
                for limit in (4096, 6000, 8191, 8192, 16384, 32768)}
            profiles["tokenizer"] = {"name": encoding.name, "is_luna_model_exact": False,
                "input": "Exact title, body and canonical title/body JSON measured separately; no prompt or framing overhead included.",
                "no_truncation": True}
            provenance = {"owner": str(source.owner), "snapshot_head": head, "observed_at": observed,
                          "screening_plan": SCREEN_PLAN, "screening_continuation": continuation["_record_id"],
                          "final_screening_report": FINAL_REPORT, "mapping_artifact": report["article_results_artifact"],
                          "copied_final_report_artifact": self.ledger.artifacts.put(report),
                          "selected_decision_records_artifact": self.ledger.artifacts.put([r["_record_id"] for r in kept.values()]),
                          "verified_source_artifacts_artifact": self.ledger.artifacts.put(sorted(source.artifacts.checked)),
                          "old_screening_cost_and_holds_retained_in_original_owner": True}
        finally:
            source.close()
        if implementation() != code:
            raise AuditError("dossier_preparation_code_changed_during_execution")
        manifest = {"method": METHOD, "implementation": code, "versions": versions, "provenance": provenance,
                    **observed_frame, "documents_artifact": self.ledger.artifacts.put(documents),
                    "articles_artifact": self.ledger.artifacts.put(articles),
                    "coverage_artifact": self.ledger.artifacts.put(coverage), "profiles": profiles,
                    "vector_reuse": {"status": "not_measured", "reused_vectors": 0,
                                     "requirement": "Exact source/body/input and embedding profile compatibility must be audited before reuse."},
                    "budget_nanousd": BUDGET_NANOUSD, "settled_cost_nanousd": 0, "held_reservations_nanousd": 0,
                    "new_model_calls": 0, "accepted_dossiers": 0, "human_validated": False,
                    "at": utc(), "exact_chat_presentation_capture_supported": False}
        identifier = self.ledger.record(session, "cyber_dossier_input_manifest", METHOD, manifest)
        return {"id": identifier, "owner": str(self.ledger.root), **observed_frame,
                "profiles": profiles, "documents_artifact": manifest["documents_artifact"],
                "articles_artifact": manifest["articles_artifact"], "coverage_artifact": manifest["coverage_artifact"],
                "budget_usd": BUDGET_NANOUSD / 1e9, "new_model_calls": 0, "new_cost_usd": 0,
                "vector_reuse": manifest["vector_reuse"], "accepted_dossiers": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=OWNER)
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Freeze exact screened Cybercrime NL inputs for the separately authorized USD50 dossier method",
                                       actor="codex:cybercrime-dossier-preparation"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
