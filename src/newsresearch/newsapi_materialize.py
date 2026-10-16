"""Private working copies of collected API records, not a public data export."""
from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING
import uuid
import zipfile

from .common import Context, Json, ResearchError, canonical, digest, require_active, utc
from .newsapi_collection import PERIODS, collection_state, saved

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-private-working-bundles-v1"


def materialize(engine: Research, session: str, context: Context,
                periods: list[tuple[str, str]] | None = None, prefix: str = "") -> Json:
    require_active(engine, session)
    engine._require(context, {"retrieval_profile"})
    profile = engine.ledger.get(context.versions["retrieval_profile"], "retrieval_profile")["content"]
    if profile.get("method") != METHOD:
        raise ResearchError("Register the private working-copy method first")
    periods = PERIODS if periods is None else periods
    state = collection_state(engine, periods)
    progress = saved(engine, "newsapi_collection_progress", None)
    if not progress or progress[-1]["stop_reason"] not in {"query_exhausted", "budget_target"}:
        raise ResearchError("Finish collection at exhaustion or budget before materializing working copies")
    current = progress[-1]
    if current.get("periods", [list(p) for p in PERIODS]) != [list(p) for p in periods]:
        raise ResearchError("Materialize only the matching period-bound final progress")
    receipts = [r for r in saved(engine, "newsapi_collection_receipt", None) if r["id"] in state["receipt_ids"]]
    root = engine.ledger.artifacts.root.parent
    outputs = []
    for period in periods:
        rows, seen, lineage = [], set(), []
        for receipt in receipts:
            if receipt["parameters"]["dateStart"] != period[0] or receipt["http_status"] != 200:
                continue
            for index, article in enumerate(receipt["response"].get("articles", {}).get("results", [])):
                if not (isinstance(article, dict) and period[0] <= str(article.get("date", "")) <= period[1]
                        and article.get("lang") == "nld"):
                    continue
                source_hash = digest(article)
                key = (article.get("uri") or article.get("source_hash") or article.get("url"), source_hash)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(canonical({"article": article, "receipt_id": receipt["id"], "item_index": index,
                    "source_hash": source_hash, "original_response_sha256": receipt.get("raw_sha256"),
                    "retention": "metadata_only_quarantine" if article.get("quarantined") else "permitted_private"}))
            lineage.append(receipt["id"])
        manifest = {"method": METHOD, "versions": context.versions, "date_start": period[0], "date_end": period[1],
                    "records": len(rows), "receipt_ids": lineage, "collection_result": current["id"],
                    "scope": "Private working copy, not original provider response or reviewed incident dataset; article text remains untrusted evidence"}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("artikelen.jsonl", "\n".join(rows) + ("\n" if rows else ""))
            archive.writestr("manifest.json", canonical(manifest))
        raw = buffer.getvalue()
        artifact = engine.ledger.artifacts.put_bytes(raw)
        engine.ledger.append(session, "newsapi.private_bundle.saved", {"artifact": artifact, "year": period[0][:4]})
        path = root / f"{prefix}articles-{period[0][:4]}.zip"
        path.write_bytes(raw)
        outputs.append({"year": period[0][:4], "records": len(rows), "artifact": artifact, "path": str(path),
                        "bytes": len(raw), "source_receipts": lineage})
    buffer_csv = io.StringIO(newline="")
    columns = ["attempt", "purpose", "http_status", "billed_tokens", "dateStart", "dateEnd", "articlesPage", "receipt_id", "completed_at"]
    writer = csv.DictWriter(buffer_csv, fieldnames=columns)
    writer.writeheader()
    for receipt in saved(engine, "newsapi_collection_receipt", None):
        writer.writerow({**{key: receipt.get(key) for key in ["attempt", "purpose", "http_status", "billed_tokens", "completed_at"]},
                         **{key: receipt["parameters"].get(key) for key in ["dateStart", "dateEnd", "articlesPage"]},
                         "receipt_id": receipt["id"]})
    csv_bytes = buffer_csv.getvalue().encode("utf-8-sig")
    csv_artifact = engine.ledger.artifacts.put_bytes(csv_bytes)
    engine.ledger.append(session, "newsapi.private_costs.saved", {"artifact": csv_artifact})
    csv_path = root / f"{prefix}request-costs.csv"
    csv_path.write_bytes(csv_bytes)
    result = {**state, "versions": context.versions, "periods": periods, "bundles": outputs, "cost_csv": str(csv_path),
              "cost_csv_artifact": csv_artifact, "collection_result": current["id"],
              "stop_reason": current["stop_reason"], "final_observed_used": current["final_observed_used"],
              "allowance": 5000, "target_used": 4000, "model_calls": 0, "network_calls": 0, "generated_at": utc(),
              "account_ceiling": current.get("account_ceiling", 4000),
              "representation": "Materialized private working copies; permitted original responses remain separately preserved by hash"}
    identifier = engine.ledger.record(session, "newsapi_collection_materialization", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
