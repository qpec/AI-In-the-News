"""Audited, offline, hash-selected full-source inspection for entity-method design.

One eligible row per cybercrime archive is selected before presentation. This is
an exploratory development sample, not a prevalence sample or model judgment.
All source text and raw provider records remain in the protected owner.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from newsresearch.common import Config, Context, Json, ResearchError, digest, require_no_credentials
from newsresearch.legacy import sha256, within
from newsresearch.runtime import Research, audited_handler

from audit_article_scope_metadata import read_partition

METHOD = "cybercrime-entity-design-full-source-inspection-v1"
OWNER = "entity-design-cybercrime-20261017-v1"
SEED = "cybercrime-entity-design-one-per-archive-20261017-v1"
CORPUS = "cybercrime"
RETRIEVAL_REASON = "Original row-level retrieval timestamp and query parameters are unavailable in this inspection."


def eligible_article(row: Json) -> tuple[str, Json | None]:
    """Whole-row retention guard precedes using any article text or metadata."""
    try:
        require_no_credentials(row)
    except ResearchError:
        return "credential_guard", None
    article = row.get("article")
    if not isinstance(article, dict):
        return "missing_article_object", None
    for value in (row, article):
        if (value.get("metadata_only") is True or value.get("quarantined") is True
                or value.get("quarantine") is True or value.get("retention") == "metadata_only"
                or value.get("retention_exclusion") not in (None, False, "")):
            return "explicit_retention_excluded", None
    body = article.get("body")
    if not isinstance(body, str) or not body.strip():
        return "missing_or_blank_body", None
    return "usable", article


def candidate_rank(archive_sha256: str, line: int, row_hash: str) -> str:
    return digest({"seed": SEED, "archive_sha256": archive_sha256,
                   "jsonl_line": line, "exact_row_bytes_sha256": row_hash})


def deduplicate_selected(candidates: list[Json]) -> tuple[list[Json], list[Json]]:
    """Keep the first archive-path appearance of an exact title/body; no refill."""
    selected: list[Json] = []
    collisions: list[Json] = []
    seen: dict[str, Json] = {}
    for item in sorted(candidates, key=lambda value: value["locator"]["path"]):
        fingerprint = digest({"title_present": "title" in item["article"],
                              "title": item["article"].get("title"), "body": item["article"]["body"]})
        if fingerprint in seen:
            collisions.append({"excluded_locator": item["locator"],
                               "retained_locator": seen[fingerprint]["locator"],
                               "reason": "exact_title_body_collision_no_refill"})
        else:
            seen[fingerprint] = item
            selected.append(item)
    return selected, collisions


def render(result: Json, source_rows: list[Json], inspected: Json) -> str:
    lines = ["**Executed exploratory cybercrime source inspection.**", "",
             f"Scanned {result['rows_scanned']:,} saved rows across {len(result['archives'])} verified archives; "
             f"{result['usable_rows']:,} usable and {result['unavailable_rows']:,} unavailable. "
             f"Selected {len(source_rows)} distinct full-text articles after {len(result['collisions'])} "
             "exact title/body collisions, without replacement.", "",
             "Selection: minimum fixed-seed locator/row hash within each archive, then deterministic "
             "exact title/body deduplication. No semantic selection, model calls, entity labels, embeddings "
             "or membership changes. This is a development inspection, not a representative prevalence estimate.", "",
             "| Row state | Count |", "| --- | ---: |"]
    for state, count in result["row_states"].items():
        lines.append(f"| {state} | {count:,} |")
    lines.extend(["", f"Failed archives: {result['failed_archives']}; pending archives: {result['pending_archives']}. "
                  f"Inspected all {len(inspected['passages'])} stored passages; human reading is not observable.", ""])
    for index, item in enumerate(source_rows, 1):
        source = item["source"]
        article = source["raw_record"]
        locator = source["archive_provenance"]
        own = [p for p in inspected["passages"] if p["source_id"] == item["source_id"]]
        title = source.get("title")
        url = source.get("url")
        lines.extend([f"### Article {index}", "", f"Title (exact): {title}", "",
                      f"Source URL (saved): {url}", "",
                      f"Archive: {locator['path']}; JSONL line {locator['jsonl_line']}; "
                      f"source version `{item['source_id']}`.", "",
                      "Saved publication/source metadata: " + json.dumps({
                          field: article.get(field) for field in
                          ("date", "time", "dateTime", "dateTimePub", "lang", "source")}, ensure_ascii=False), "",
                      "Full retained body (exact; untrusted source evidence):", "", source["body"], "",
                      "Stable inspected passage references: " + ", ".join(
                          f"`{p['id']}`" for p in own), ""])
    lines.extend(["This exact overview is a protected technical-note artifact. record_presentation does not "
                  "support this inspection-note kind. No verified chat delivery or accepted entity finding is claimed.", ""])
    return "\n".join(lines)


class CyberInspectionResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.name != OWNER or (config is not None and not config.offline):
            raise ResearchError("cyber_inspection_dedicated_offline_owner_required")
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if set(data) != {"data_root"} or not self.config.offline:
            raise ResearchError("cyber_inspection_invalid_request")
        self.ledger.append(session, "cyber_inspection.partition_read.intended", data)
        partition = read_partition(Path(data["data_root"]), CORPUS)
        files = [Path(__file__), Path(__file__).with_name("audit_article_scope_metadata.py")]
        binding = {"method": METHOD, "seed": SEED, "partition": partition,
                   "code": {path.name: sha256(path) for path in files}}
        key = digest(binding)
        definitions = {
            "protocol": {"method": METHOD, "binding": binding,
                "unavailable_retrieval_reason": RETRIEVAL_REASON,
                "procedure": "Verify all selected-corpus archive hashes before row parsing. Guard each complete "
                "row before using fields; exclude explicit retention restrictions and missing bodies. Select "
                "one minimum fixed-seed archive/line/raw-row hash per archive. Reconcile all archive hashes and "
                "counts before freezing locators. Deduplicate selected exact title/body pairs in archive-path "
                "order with no refill. Freeze this sample before ingestion, inspect every stored passage, "
                "and retain exact raw selected rows and full evidence in protected storage only.",
                "limits": "No live collection, model inference, entity annotation, semantic filtering or "
                "population prevalence estimation. Historic incident holdouts are not opened."},
            "selection": {"rules": "One eligible hash-minimum row per cybercrime archive; exact title/body "
                "deduplication across selected rows only; no replacement. Offline exploratory development sample.",
                "corpus_id": CORPUS, "manifest_sha256": partition["manifest_sha256"], "seed": SEED},
            "question": {"text": "Inspect actual cybercrime article evidence to inform a later entity "
                "extraction specification; this operation produces no substantive model findings."},
            "dossier_definition": {"unit": "One real-world event reported by at least two different "
                "publishers; this article inspection does not establish any dossier."},
            "profile": {"mode": "exploratory", "population_estimate": False,
                "unit": "One development article appearance per archive, before exact-title/body collisions"},
        }
        previous = self.ledger.db.execute("SELECT id FROM records WHERE kind='note' AND logical_key=? "
            "ORDER BY created_event DESC LIMIT 1", (METHOD + "-result-" + key,)).fetchone()
        root = Path(partition["resolved_root"])
        bundles = partition["manifest"]["bundles"]
        if previous:
            result = self.ledger.get(previous[0], "note")["content"]
            self.ledger.append(session, "cyber_inspection.reuse_verification.intended", {"note": previous[0]})
            for bundle in bundles:
                if sha256(within(root, bundle["path"])) != bundle["sha256"]:
                    raise ResearchError("cyber_inspection_archive_pre_hash_mismatch")
            if result["dataset"] is not None:
                self._inspect(session, Context(context.objective, context.actor, result["versions"]),
                              {"passage_ids": result["passage_ids"]})
            self.ledger.append(session, "cyber_inspection.result_reused", {"note": previous[0]})
            return {"id": previous[0], **result,
                    "markdown": self.ledger.artifacts.read_bytes(result["markdown_artifact"]).decode("utf-8")}
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD + "-" + key,
                    "content": value})["id"] for kind, value in definitions.items()}
        bound = Context(context.objective, context.actor, versions)
        self.ledger.append(session, "cyber_inspection.archive_verification.intended", {"versions": versions})
        for bundle in bundles:
            if sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError("cyber_inspection_archive_pre_hash_mismatch")
        archives: list[Json] = []
        candidates: list[Json] = []
        states: Counter[str] = Counter()
        for bundle in sorted(bundles, key=lambda value: value["path"]):
            self.ledger.append(session, "cyber_inspection.bundle_scan.intended", {
                "path": bundle["path"], "sha256": bundle["sha256"], "versions": versions})
            scanned = 0
            current: Json | None = None
            local_states: Counter[str] = Counter()
            with zipfile.ZipFile(within(root, bundle["path"])) as archive:
                if archive.namelist().count("artikelen.jsonl") != 1:
                    raise ResearchError("cyber_inspection_stream_invalid")
                with archive.open("artikelen.jsonl") as stream:
                    for line_number, raw in enumerate(stream, 1):
                        if not raw.strip():
                            continue
                        row = json.loads(raw)
                        if not isinstance(row, dict):
                            raise ResearchError("cyber_inspection_row_invalid")
                        state, article = eligible_article(row)
                        states[state] += 1
                        local_states[state] += 1
                        scanned += 1
                        if article is None:
                            continue
                        row_hash = hashlib.sha256(raw).hexdigest()
                        rank = candidate_rank(bundle["sha256"], line_number, row_hash)
                        if current is None or rank < current["selection_hash"]:
                            current = {"selection_hash": rank, "article": article, "raw": raw,
                                "locator": {"path": bundle["path"], "archive_sha256": bundle["sha256"],
                                    "jsonl_line": line_number, "exact_row_bytes_sha256": row_hash}}
            if scanned != bundle["declared_records"] or sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError("cyber_inspection_archive_postcheck_mismatch")
            report = {"path": bundle["path"], "sha256": bundle["sha256"], "rows": scanned,
                      "row_states": dict(local_states), "eligible_selection_available": current is not None}
            archives.append(report)
            self.ledger.append(session, "cyber_inspection.bundle_scan.completed", report)
            if current is not None:
                candidates.append(current)
        if sum(states.values()) != partition["manifest"]["summary"]["declared_article_records"]:
            raise ResearchError("cyber_inspection_row_total_mismatch")
        # Recheck every archive after the entire scan, before freezing any sample.
        for bundle in bundles:
            if sha256(within(root, bundle["path"])) != bundle["sha256"]:
                raise ResearchError("cyber_inspection_archive_postcheck_mismatch")
        selected, collisions = deduplicate_selected(candidates)
        frozen = {"binding": binding, "versions": versions, "selected": [
            {"selection_hash": item["selection_hash"], "locator": item["locator"]} for item in selected],
            "collisions": collisions, "archives": archives, "row_states": dict(states)}
        frozen_id = self._version(session, bound, {"kind": "note", "key": METHOD + "-frozen-" + key,
                                 "content": frozen})["id"]
        articles = []
        for item in selected:
            raw_ref = self.ledger.artifacts.put_bytes(item["raw"])
            self.ledger.append(session, "cyber_inspection.selected_row_saved", {
                "frozen_selection": frozen_id, "artifact": raw_ref, "locator": item["locator"]})
            article = item["article"]
            articles.append({"source_key": CORPUS + ":" + digest(item["locator"]),
                "body": article["body"], "title": article.get("title"), "url": article.get("url"),
                "published_at": article.get("dateTimePub") or article.get("dateTime"),
                "retention": "permitted", "raw_record": article, "archive_provenance": item["locator"],
                "exact_archive_row_artifact": raw_ref, "corpus_id": CORPUS,
                "corpus_manifest_sha256": partition["manifest_sha256"]})
        source_rows: list[Json] = []
        passage_ids: list[str] = []
        inspection: Json = {"id": None, "passages": []}
        dataset_id = None
        if articles:
            imported = self._ingest(session, bound, {"articles": articles, "key": METHOD + "-" + key,
                "retrieval": {"source": "saved cybercrime archives with frozen per-row provenance",
                    "retrieved_at": None, "parameters": None, "unavailable_reason": RETRIEVAL_REASON}})
            dataset_id = imported["id"]
            versions = {**versions, "dataset": dataset_id}
            bound = Context(context.objective, context.actor, versions)
            for source_id, article in zip(imported["sources"], articles, strict=True):
                source_rows.append({"source_id": source_id, "source": article})
                passage_ids.extend(row[0] for row in self.ledger.db.execute(
                    "SELECT id FROM passages WHERE source_id=? ORDER BY start", (source_id,)))
            inspection = self._inspect(session, bound, {"passage_ids": passage_ids})
        result = {"method": METHOD, "corpus_id": CORPUS, "binding": binding, "versions": versions,
            "frozen_selection": frozen_id, "dataset": dataset_id, "inspection": inspection["id"],
            "passage_ids": passage_ids, "selected_sources": [item["source_id"] for item in source_rows],
            "archives": archives, "collisions": collisions, "row_states": dict(sorted(states.items())),
            "rows_scanned": sum(states.values()), "usable_rows": states["usable"],
            "unavailable_rows": sum(states.values()) - states["usable"], "failed_archives": 0,
            "pending_archives": 0, "model_calls": 0, "new_embeddings": 0, "record_presentation_supported": False}
        markdown = render(result, source_rows, inspection)
        result["markdown_artifact"] = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        self.ledger.append(session, "cyber_inspection.report_saved", {"artifact": result["markdown_artifact"],
            "status": "prepared_for_delivery; UI delivery unobserved"})
        identifier = self._version(session, bound, {"kind": "note", "key": METHOD + "-result-" + key,
                                  "content": result})["id"]
        return {"id": identifier, **result, "markdown": markdown}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    engine = CyberInspectionResearch(args.workspace)
    try:
        result = engine.execute("status", {"data_root": str(args.data_root)},
            objective="Inspect fixed-seed full cybercrime article evidence for entity-method development",
            actor="codex:entity-design-cybercrime")
        print(result["markdown"], flush=True)
        print(json.dumps({"note": result["id"], "frozen_selection": result["frozen_selection"],
            "inspection": result["inspection"],
            "report": str(engine.ledger.artifacts.root / result["markdown_artifact"])}), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
