from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING
import zipfile

from .common import Context, Json, ResearchError, require_no_credentials

if TYPE_CHECKING:
    from .runtime import Research


def import_newsapi(engine: Research, session: str, context: Context, data: Json) -> Json:
    if session not in engine._active:
        raise ResearchError("Import requires an audited session")
    retention = data.get("retention")
    if retention not in {"permitted", "metadata_only"}:
        raise ResearchError("Explicit source retention permission is required")
    path = Path(data["path"]).resolve()
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            with archive.open("artikelen.jsonl") as stream:
                records = []
                for line in stream:
                    if line.strip():
                        item = json.loads(line)
                        require_no_credentials(item)
                        records.append(item["article"])
                    if len(records) > engine.config.max_articles:
                        raise ResearchError(
                            "Bundle exceeds the configured import limit; register a bounded selection first"
                        )
    else:
        document = json.loads(raw)
        require_no_credentials(document)
        if isinstance(document, dict) and isinstance(document.get("articles"), dict):
            records = document["articles"]["results"]
        elif isinstance(document, list):
            records = document
        else:
            raise ResearchError("Expected an Event Registry articles.results response or article list")
    require_no_credentials(records)
    original = engine.ledger.artifacts.put_bytes(raw) if retention == "permitted" else None
    articles = []
    for record in records:
        article = {
            "source_key": f"eventregistry:{record['uri']}",
            "title": record.get("title", ""),
            "url": record.get("url"),
            "published_at": record.get("dateTimePub") or record.get("dateTime"),
            "body": record.get("body", "") if retention == "permitted" else "",
            "retention": retention,
            "synthetic": bool(data.get("synthetic", False)),
            "original_artifact": original,
            "original_sha256": source_hash,
        }
        if retention == "permitted":
            article["raw_record"] = record
        articles.append(article)
    return engine._ingest(
        session,
        context,
        {
            "key": data.get("key", path.name),
            "articles": articles,
            "retrieval": {
                "source": "NewsAPI.ai/Event Registry stored response",
                "retrieved_at": data["retrieved_at"],
                "parameters": data["parameters"],
                "imported_source_sha256": source_hash,
                "original_artifact": original,
                "network_calls": 0,
            },
        },
    )
