"""Deterministic source/passages preparation; no semantic inference or dossier assignments."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Iterator
import zipfile

from .common import Context, Json, ResearchError, digest, require_active, require_no_credentials, utc
from .legacy import event_uri_state, event_uri_summary, sha256, within

if TYPE_CHECKING:
    from .runtime import Research


METHOD = "legacy-pilot-v1"
CHUNK_METHOD = "unicode-window-1600-overlap-200-v1"
RETRIEVAL_UNKNOWN = (
    "Historical provider retrieval timestamps and query parameters have not been linked to individual "
    "archive records. Original selected rows are retained; preparation time is not retrieval time."
)


def allocate(counts: dict[str, int], limit: int) -> dict[str, int]:
    total = sum(counts.values())
    target = min(limit, total)
    if total < 1 or target < 1:
        raise ResearchError("The pilot requires a nonempty frame and a positive limit")
    quotas = {key: target * value // total for key, value in counts.items()}
    ranked = sorted(counts, key=lambda key: (-(target * counts[key] % total), key))
    for key in ranked[: target - sum(quotas.values())]:
        quotas[key] += 1
    return quotas


def rows(root: Path, bundles: list[Json]) -> Iterator[tuple[Json, int, bytes, Json]]:
    for bundle in bundles:
        with zipfile.ZipFile(within(root, bundle["path"])) as archive:
            with archive.open("artikelen.jsonl") as stream:
                for number, raw in enumerate(stream, 1):
                    if raw.strip():
                        yield bundle, number, raw, json.loads(raw)


def chunks(passage: Json) -> Iterator[Json]:
    text = passage["text"]
    if not text.strip():
        return
    offset = 0
    while offset < len(text):
        end = min(offset + 1600, len(text))
        value = text[offset:end]
        content = {
            "method": CHUNK_METHOD,
            "source_version": passage["source_id"],
            "passage_id": passage["id"],
            "source_start": passage["start"] + offset,
            "source_end": passage["start"] + end,
            "text_hash": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        }
        yield {"id": digest(content), **content, "text": value}
        if end == len(text):
            break
        offset = end - 200


def prepare_legacy_pilot(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    limit = data.get("limit", 20000)
    seed = data.get("seed")
    if type(limit) is not int or not 1 <= limit <= engine.config.max_articles:
        raise ResearchError("Pilot limit must fit the configured article limit")
    if not isinstance(seed, str) or not seed.strip() or data.get("retention") != "permitted":
        raise ResearchError("A fixed selection seed and explicit permitted retention are required")
    selection = engine.ledger.get(context.versions["selection"], "selection")["content"]
    protocol = engine.ledger.get(context.versions["protocol"], "protocol")["content"]
    profile = engine.ledger.get(context.versions["profile"], "profile")["content"]
    if any(
        selection.get(key) != value for key, value in {"method": METHOD, "limit": limit, "seed": seed}.items()
    ):
        raise ResearchError("Pilot selection must exactly match its registered method, limit and seed")
    if (
        protocol.get("preparation_method") != METHOD
        or protocol.get("unavailable_retrieval_reason") != RETRIEVAL_UNKNOWN
    ):
        raise ResearchError("Register preparation and unknown historical retrieval before execution")
    if profile.get("mode") != "exploratory" or profile.get("population_estimate") is not False:
        raise ResearchError("Preparation requires an exploratory profile without population inference")
    root = Path(data["data_root"]).resolve()
    verification = engine._verify_legacy(session, context, {"data_root": str(root)})
    inventory = engine.ledger.artifacts.read(verification["input_inventory"])
    bundles = sorted(
        (entry for entry in inventory["files"] if entry["kind"] == "article-bundle"), key=lambda x: x["path"]
    )
    identity = {
        "inventory": verification["input_inventory"],
        "versions": context.versions,
        "method": METHOD,
        "chunk_method": CHUNK_METHOD,
        "implementation": engine.identity()["code_digest"],
    }
    key = digest(identity)
    previous = engine.ledger.db.execute(
        "SELECT id FROM records WHERE kind='corpus_preparation' AND logical_key=?", (key,)
    ).fetchone()
    if previous:
        result = engine.ledger.get(previous[0], "corpus_preparation")
        engine.ledger.append(
            session, "preparation.reused", {"record": previous[0], "verification": verification["id"]}
        )
        return {"id": previous[0], **result, "reused": True}

    def artifact(kind: str, value: object) -> str:
        reference = engine.ledger.artifacts.put(value)
        engine.ledger.append(session, "preparation.artifact.saved", {"kind": kind, "artifact": reference})
        return reference

    candidates: dict[str, list[Json]] = defaultdict(list)
    for bundle, number, raw, row in rows(root, bundles):
        uri = str(row["article"]["uri"])
        cohort = row["collection_cohort"]
        candidates[cohort].append(
            {
                "article_uri": uri,
                "cohort": cohort,
                "bundle": bundle["path"],
                "bundle_sha256": bundle["sha256"],
                "line_number": number,
                "row_sha256": hashlib.sha256(raw).hexdigest(),
                "selection_rank": digest({"seed": seed, "article_uri": uri}),
            }
        )
    quotas = allocate({cohort: len(items) for cohort, items in candidates.items()}, limit)
    selected: list[Json] = []
    excluded: list[Json] = []
    for cohort, items in sorted(candidates.items()):
        items.sort(key=lambda item: (item["selection_rank"], item["article_uri"]))
        selected.extend(items[: quotas[cohort]])
        excluded.extend(
            {**item, "reason": "outside_registered_pilot_quota"} for item in items[quotas[cohort] :]
        )
    selected_ref = artifact("selected_archive_records", selected)
    excluded_ref = artifact("excluded_archive_records", excluded)
    lookup = {(item["bundle"], item["line_number"]): item for item in selected}
    prepared: dict[tuple[str, int], Json] = {}
    event_counts: Counter[str] = Counter()
    event_values: set[str] = set()
    missing_text = []
    for bundle in bundles:
        original = bytearray()
        articles = []
        for _, number, raw, row in rows(root, [bundle]):
            location = (bundle["path"], number)
            if location not in lookup:
                continue
            require_no_credentials(row)
            locator = lookup[location]
            if hashlib.sha256(raw).hexdigest() != locator["row_sha256"]:
                raise ResearchError("Selected archive row changed between selection and import")
            record = row["article"]
            body = record.get("body")
            if body is not None and not isinstance(body, str):
                raise ResearchError("Selected provider body must be text, absent or null")
            has_text = isinstance(body, str) and bool(body.strip())
            if not has_text:
                missing_text.append(locator)
            state = event_uri_state(record)
            event_counts[state] += 1
            if state == "populated":
                event_values.add(record["eventUri"])
            start = len(original)
            original.extend(raw)
            article = {
                "source_key": "eventregistry:" + locator["article_uri"],
                "title": record.get("title", ""),
                "url": record.get("url"),
                "published_at": record.get("dateTimePub") or record.get("dateTime"),
                "body": body if isinstance(body, str) else "",
                "has_text": has_text,
                "retention": "permitted",
                "synthetic": False,
                "raw_record": record,
                "event_uri_state": state,
                "collection_cohort": locator["cohort"],
                "archive_provenance": {
                    **locator,
                    "original_rows_start": start,
                    "original_rows_end": len(original),
                },
            }
            prepared[location] = article
            articles.append(article)
        if articles:
            reference = engine.ledger.artifacts.put_bytes(bytes(original))
            engine.ledger.append(
                session,
                "preparation.artifact.saved",
                {"kind": "original_selected_rows", "artifact": reference},
            )
            for article in articles:
                article["original_artifact"] = reference
                article["original_sha256"] = reference
        # Close the time-of-check gap for both scans before accepting an import.
        if sha256(within(root, bundle["path"])) != bundle["sha256"]:
            raise ResearchError("Archive changed during pilot preparation")
    if len(prepared) != len(selected):
        raise ResearchError("Selected archive coverage is incomplete")
    dataset = engine._ingest(
        session,
        context,
        {
            "key": "incident-pilot-" + key,
            "articles": [prepared[(item["bundle"], item["line_number"])] for item in selected],
            "retrieval": {
                "source": "Preserved NewsAPI.ai/Event Registry archive",
                "retrieved_at": None,
                "parameters": None,
                "unavailable_reason": RETRIEVAL_UNKNOWN,
                "input_inventory": verification["input_inventory"],
                "network_calls": 0,
            },
        },
    )
    del prepared, candidates
    chunk_artifacts = []
    pending = []
    chunk_count = passage_count = 0
    sql = (
        "SELECT * FROM passages WHERE source_id IN (SELECT value FROM json_each(?)) ORDER BY source_id,start"
    )
    for row in engine.ledger.db.execute(sql, (json.dumps(dataset["sources"]),)):
        passage_count += 1
        for chunk in chunks(dict(row)):
            pending.append(chunk)
            chunk_count += 1
            if len(pending) == 1000:
                chunk_artifacts.append(artifact("embedding_input_chunks", pending))
                pending = []
    if pending:
        chunk_artifacts.append(artifact("embedding_input_chunks", pending))
    result = {
        **identity,
        "prepared_at": utc(),
        "dataset": dataset["id"],
        "verification": verification["id"],
        "frame_records": verification["article_records"],
        "selected_records": len(selected),
        "excluded_records": len(excluded),
        "cohort_quotas": quotas,
        "selection_manifest": selected_ref,
        "exclusion_manifest": excluded_ref,
        "missing_text_records": len(missing_text),
        "missing_text_manifest": artifact("missing_text", missing_text),
        "event_uri": event_uri_summary(event_counts, event_values),
        "passages": passage_count,
        "embedding_input_chunks": chunk_count,
        "chunk_artifacts": chunk_artifacts,
        "context_artifact": artifact(
            "pilot_version_context", {"versions": {**context.versions, "dataset": dataset["id"]}}
        ),
        "pending_stages": [
            "embeddings",
            "event_extraction",
            "event_coreference",
            "incident_linking",
            "human_evaluation",
        ],
        "network_calls": 0,
        "model_calls": 0,
        "scope": "Exploratory development pilot; sources and exact chunks, no inferred events or dossiers",
    }
    identifier = engine.ledger.record(session, "corpus_preparation", key, result)
    return {"id": identifier, **result, "reused": False}
