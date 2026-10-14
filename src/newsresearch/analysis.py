from __future__ import annotations

from collections import Counter
import io
import os
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, digest, require_active

if TYPE_CHECKING:
    from .runtime import Research

AGGREGATE_SQL = "SELECT label, COUNT(*) AS dossiers FROM snapshot GROUP BY label ORDER BY label"
ROW_SQL = """WITH chosen AS (
 SELECT json_extract(value,'$.dossier') AS dossier_id,
        json_extract(value,'$.claim_key') AS claim_key FROM json_each(:chosen)
), ranked AS (
 SELECT a.*, ROW_NUMBER() OVER(PARTITION BY a.claim_key ORDER BY a.revision DESC) AS position
 FROM accepted a JOIN records r ON r.id=a.id
 WHERE json_extract(r.payload,'$.versions')=:versions
)
SELECT c.dossier_id, COALESCE(a.label,'missing') AS label, a.id AS acceptance
FROM chosen c LEFT JOIN ranked a ON a.claim_key=c.claim_key AND a.position=1
ORDER BY c.dossier_id"""


def aggregate(rows: list[Json]) -> list[Json]:
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE snapshot(dossier_id TEXT PRIMARY KEY,label TEXT,acceptance TEXT)")
        db.executemany(
            "INSERT INTO snapshot VALUES (?,?,?)",
            [(r["dossier_id"], r["label"], r["acceptance"]) for r in rows],
        )
        return [dict(row) for row in db.execute(AGGREGATE_SQL)]


def compatible(table: Json, context: Context) -> None:
    if any(context.versions.get(key) != value for key, value in table["versions"].items()):
        raise ResearchError("Snapshot and command version bindings differ")


def measure(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    ledger = engine.ledger
    profile = ledger.get(context.versions["profile"], "profile")["content"]
    if profile.get("population_estimate"):
        raise ResearchError("Population estimation needs a validated sampling design; not implemented")
    collection = ledger.get(context.versions["dossiers"], "dossiers")
    if collection["versions"]["dataset"] != context.versions["dataset"]:
        raise ResearchError("Dossier and dataset versions differ")
    frame = {group["id"] for group in collection["dossiers"]}
    supplied = data.get("include_ids", sorted(frame))
    if not supplied or len(supplied) != len(set(supplied)) or not set(supplied) <= frame:
        raise ResearchError("Measurement needs distinct in-frame dossier IDs")
    included = sorted(supplied)
    exclusions = data.get("exclusions", {})
    omitted = frame - set(included)
    if set(exclusions) != omitted:
        raise ResearchError("Every excluded dossier needs a versioned exclusion decision")
    for identifier, decision in exclusions.items():
        version = ledger.get(decision, "exclusion")["content"]
        if identifier not in version.get("dossier_ids", []) or not version.get("reason"):
            raise ResearchError("Exclusion decision does not cover the dossier")
    chosen = [
        {
            "dossier": identifier,
            "claim_key": digest(
                {
                    "dataset": context.versions["dataset"],
                    "dossiers": context.versions["dossiers"],
                    "dossier": identifier,
                    "question": context.versions["question"],
                    "codebook": context.versions["codebook"],
                    "slot": data.get("slot", "primary"),
                }
            ),
        }
        for identifier in included
    ]
    parameters = {"chosen": canonical(chosen), "versions": canonical(context.versions)}
    rows = [dict(row) for row in ledger.db.execute(ROW_SQL, parameters)]
    summary = aggregate(rows)
    missing = [row["dossier_id"] for row in rows if row["acceptance"] is None]
    dataset_sources = set(ledger.get(context.versions["dataset"], "dataset")["source_versions"])
    framed_sources = {member["source"] for group in collection["dossiers"] for member in group["members"]}
    value = {
        "versions": context.versions,
        "profile": profile,
        "unit": "dossier",
        "scope": "registered sample; no external population inference",
        "mode": profile["mode"],
        "sql": ROW_SQL,
        "parameters": parameters,
        "calculation_sql": AGGREGATE_SQL,
        "included_dossier_ids": included,
        "frame_dossier_ids": sorted(frame),
        "denominator": len(included),
        "source_frame_coverage": {
            "dataset_sources": len(dataset_sources),
            "assigned_sources": len(framed_sources),
            "unassigned_source_versions": sorted(dataset_sources - framed_sources),
        },
        "exclusions": exclusions,
        "missing_dossier_ids": missing,
        "coverage": {"accepted": len(rows) - len(missing), "expected": len(rows)},
        "membership_uncertainty": {
            group["id"]: sum(member["assignment"] == "uncertain" for member in group["members"])
            for group in collection["dossiers"]
            if group["id"] in included
        },
        "rows": rows,
        "summary": summary,
        "result_digest": digest({"rows": rows, "summary": summary}),
        "measurement_status": "complete" if not missing else "incomplete; missing is not negative",
    }
    return {"id": ledger.record(session, "table", data.get("key", str(uuid.uuid4())), value), **value}


def chart_png(summary: list[Json]) -> bytes:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator

    figure = Figure(figsize=(7, 4), dpi=140, facecolor="#f0e6d1")
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    axes.set_facecolor("#f0e6d1")
    axes.bar([row["label"] for row in summary], [row["dossiers"] for row in summary], color="#b5302d")
    axes.set_title("Dossiers in the registered sample")
    axes.set_ylabel("Dossiers")
    axes.yaxis.set_major_locator(MaxNLocator(integer=True))
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", metadata={"Software": "AI In the News"})
    return buffer.getvalue()


def chart(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    table = engine.ledger.get(data["table"], "table")
    compatible(table, context)
    if aggregate(table["rows"]) != table["summary"]:
        raise ResearchError("Table calculation integrity failure")
    image = engine.ledger.artifacts.put_bytes(chart_png(table["summary"]))
    record = {
        "table": data["table"],
        "table_digest": table["result_digest"],
        "image": image,
        "calculation_sql": table["calculation_sql"],
        "versions": context.versions,
    }
    return {
        "id": engine.ledger.record(session, "chart", data["table"], record),
        **record,
        "image_path": str(engine.ledger.artifacts.root / image),
    }


def replay(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    row = engine.ledger.db.execute("SELECT kind FROM records WHERE id=?", (data["id"],)).fetchone()
    if not row:
        raise ResearchError("Unknown replay record")
    source = engine.ledger.get(data["id"])
    compatible(source, context)
    if row[0] == "table":
        summary = aggregate(source["rows"])
        reconstructed = digest({"rows": source["rows"], "summary": summary})
        if reconstructed != source["result_digest"]:
            raise ResearchError("Stored analysis replay differs")
        result = {
            "source": data["id"],
            "summary": summary,
            "result_digest": reconstructed,
            "fresh_inference": False,
        }
    elif row[0] == "assessment":
        from .gateway import validate_result

        request = engine.ledger.artifacts.read(source["request_ref"])
        validate_result(engine, request, source["result"])
        result = {"source": data["id"], "result": source["result"], "fresh_inference": False}
    elif row[0] == "chart":
        table = engine.ledger.get(source["table"], "table")
        regenerated = engine.ledger.artifacts.put_bytes(chart_png(table["summary"]))
        if regenerated != source["image"]:
            raise ResearchError("Chart bytes differ under this environment; retain the stored original")
        result = {"source": data["id"], "image": regenerated, "fresh_inference": False}
    else:
        raise ResearchError("Only assessments, tables and charts support deterministic replay")
    engine.ledger.record(session, "replay", str(uuid.uuid4()), {**result, "versions": context.versions})
    return result


def export(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    table = engine.ledger.get(data["table"], "table")
    compatible(table, context)
    policy_id = context.versions["export_policy"]
    policy = engine.ledger.get(policy_id, "export_policy")["content"]
    dataset = engine.ledger.get(context.versions["dataset"], "dataset")
    if not dataset["synthetic"] and not policy.get("allow_restricted_aggregates", False):
        raise ResearchError("Policy does not permit release of aggregates from restricted sources")
    if data.get("reviewer") != context.actor or not data.get("reason"):
        raise ResearchError("Public export requires an identified review decision and rationale")
    labels = set(policy.get("allowed_labels", []))
    threshold = int(policy.get("minimum_cell_size", 5))
    if threshold < 1 or any(
        row["label"] not in labels or row["dossiers"] < threshold for row in table["summary"]
    ):
        raise ResearchError("Export contains unapproved labels or cells below the release threshold")
    # Construct an allowlisted projection. Never serialize the private table or model response.
    public = {
        "schema_version": 1,
        "unit": "dossier",
        "scope": "registered sample",
        "denominator": table["denominator"],
        "counts": table["summary"],
        "missing_dossiers": len(table["missing_dossier_ids"]),
        "calculation_sql": AGGREGATE_SQL,
    }
    artifact = engine.ledger.artifacts.put(public)
    record = {
        "table": data["table"],
        "public_artifact": artifact,
        "policy": policy_id,
        "reviewer": context.actor,
        "reason": data["reason"],
        "versions": context.versions,
    }
    identifier = engine.ledger.record(session, "export_approved", str(uuid.uuid4()), record)
    destination = Path(data.get("destination", engine.ledger.root / "exports")).expanduser().absolute()
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = destination / f"dossier-counts-{artifact[:16]}.json"
    content = (canonical(public) + "\n").encode()
    engine.ledger.append(
        session, "export.write_intended", {"approval": identifier, "path": str(output), "artifact": artifact}
    )
    if output.exists():
        if output.read_bytes() != content:
            raise ResearchError("Export target already exists with different content")
    else:
        with output.open("xb") as stream:
            if os.name != "nt":
                output.chmod(0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    return {"id": identifier, "path": str(output), "artifact": artifact, "public": public}


def evaluate(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    plan = engine.ledger.get(context.versions["evaluation"], "evaluation")["content"]
    if plan.get("split") != "held_out" or not plan.get("items"):
        raise ResearchError("Evaluation needs a previously registered held-out manifest")
    batch = engine.ledger.get(data["batch_run"], "batch_run")
    if batch["versions"] != context.versions:
        raise ResearchError("Evaluation version mismatch")
    gold = {item["dossier_id"]: item["label"] for item in plan["items"]}
    if len(gold) != len(plan["items"]) or {item["dossier_id"] for item in batch["items"]} != set(gold):
        raise ResearchError("Held-out coverage manifest mismatch")
    confusion: Counter[tuple[str, str]] = Counter()
    missing = []
    correct = 0
    successful = 0
    for item in batch["items"]:
        if not item["assessment"]:
            missing.append(item["dossier_id"])
            continue
        assessment = engine.ledger.get(item["assessment"], "assessment")
        if not assessment["validation"]["coverage_complete"]:
            missing.append(item["dossier_id"])
            continue
        actual = assessment["result"]["label"]
        expected = gold[item["dossier_id"]]
        confusion[(expected, actual)] += 1
        successful += 1
        correct += expected == actual
    report = {
        "versions": context.versions,
        "split": "held_out",
        "batch": data["batch_run"],
        "expected": len(gold),
        "processed": successful,
        "missing": missing,
        "correct": correct,
        "accuracy_on_processed": correct / successful if successful else None,
        "coverage": successful / len(gold),
        "confusion": [{"gold": a, "predicted": b, "count": n} for (a, b), n in sorted(confusion.items())],
        "validity": "Synthetic held-out software evaluation; not scientific validation",
    }
    return {"id": engine.ledger.record(session, "evaluation_result", str(uuid.uuid4()), report), **report}
