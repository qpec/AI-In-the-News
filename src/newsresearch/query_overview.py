"""Audited technical summaries of stored article-query scores, without fresh inference."""
from __future__ import annotations

from collections import Counter
import io
import math
from typing import TYPE_CHECKING

from .common import AuditError, Context, Json, ResearchError, digest, require_active
from .retrieval import save
from .tagging import same_versions

if TYPE_CHECKING:
    from .runtime import Research

SCORE_SQL = """SELECT id AS result_id,
 json_extract(payload,'$.source_version') AS source_version,
 json_extract(payload,'$.score') AS score,
 json_extract(payload,'$.status') AS status,
 json_extract(payload,'$.answer') AS answer,
 json_extract(payload,'$.query_request_started_at') AS query_request_started_at,
 json_extract(payload,'$.query_response_received_at') AS query_response_received_at,
 json_extract(payload,'$.score_run_started_at') AS score_run_started_at,
 json_extract(payload,'$.score_run_completed_at') AS score_run_completed_at
 FROM records WHERE kind='article_query_result' AND json_extract(payload,'$.run')=?
 ORDER BY score,source_version"""
TOP_SQL = """SELECT r.id AS result_id,
 json_extract(r.payload,'$.source_version') AS source_version,
 json_extract(r.payload,'$.score') AS score,
 json_extract(r.payload,'$.answer') AS answer,
 json_extract(s.payload,'$.title') AS title,
 json_extract(s.payload,'$.url') AS url,
 json_extract(s.payload,'$.published_at') AS published_at,
 json_extract(r.payload,'$.evidence.chunk.passage_id') AS passage_id,
 json_extract(r.payload,'$.evidence.chunk.source_start') AS source_start,
 json_extract(r.payload,'$.evidence.chunk.source_end') AS source_end
 FROM records r JOIN sources s ON s.id=json_extract(r.payload,'$.source_version')
 WHERE r.kind='article_query_result' AND json_extract(r.payload,'$.run')=?
 AND json_extract(r.payload,'$.score') IS NOT NULL
 ORDER BY score DESC,source_version LIMIT ?"""


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def plot(bands: list[Json], expected: int, scored: int, cutoff: Json | None = None) -> bytes:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator

    figure = Figure(figsize=(11, 4.6), dpi=150, facecolor="white")
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    bars = axes.bar([b["label"] for b in bands], [b["articles"] for b in bands], color="#325b82")
    axes.bar_label(bars, fontsize=8, padding=3)
    axes.set_title("Verdeling van de zoekresultaten", loc="left", fontsize=14, pad=16)
    axes.set_xlabel("Maximale cosinusovereenkomst per artikel (geen waarschijnlijkheid)")
    axes.set_ylabel("Aantal artikelen")
    axes.yaxis.set_major_locator(MaxNLocator(integer=True))
    axes.tick_params(axis="x", labelsize=8)
    axes.margins(y=0.16)
    axes.spines[["top", "right"]].set_visible(False)
    cutoff_text = "geen cutoff toegepast"
    if cutoff and cutoff["threshold"] is not None:
        cutoff_text = f"cutoff {cutoff['threshold']:g} ({'gevalideerd' if cutoff['validated'] else 'voorlopig'})"
    figure.text(0.08, 0.025, f"Pilot: {expected:,} artikelen · {scored:,} scores · {expected-scored:,} zonder score · {cutoff_text}", fontsize=9)
    figure.tight_layout(rect=(0.02, 0.06, 1, 1))
    output = io.BytesIO()
    figure.savefig(output, format="png", metadata={"Software": "AI In the News audited query overview"})
    return output.getvalue()


def overview(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    ledger = engine.ledger
    run = ledger.get(data["run"], "article_query_manifest")
    same_versions(run, context)
    top_n = data.get("top", 10)
    if type(top_n) is not int or not 1 <= top_n <= 100:
        raise ResearchError("Top article limit must be between 1 and 100")
    profile = engine._version(session, context, {"kind": "profile", "key": "article-query-overview-v1",
        "content": {"mode": "exploratory", "method": "article-query-overview-v1",
            "unit": "Technical article-query diagnostics; not dossiers or incident prevalence",
            "population_estimate": False, "quantiles": "Linear interpolation at (n-1)*q, scored articles only",
            "bands": "[-1,0), then [0.0,0.1), ... [0.9,1.0]; final upper edge inclusive",
            "ranking": "Stored maximum passage score descending; ties by source version",
            "cutoff_reporting": "Copy applied cutoff and validation/policy provenance; do not select a threshold in this overview",
            "missingness": "Keep unprocessed and pending articles in expected denominator, outside score statistics"},
        "amend_latest": True, "reason": "Register a reproducible overview of existing query results before reading scores"})["id"]
    rows = [dict(row) for row in ledger.db.execute(SCORE_SQL, (data["run"],))]
    frame = set(run["source_ids"])
    dataset = set(ledger.get(context.versions["dataset"], "dataset")["source_versions"])
    observed = [row["source_version"] for row in rows]
    if frame != dataset or run["expected_articles"] != len(frame) or len(set(observed)) != len(observed) or not set(observed) <= frame:
        raise AuditError("Overview article frame or row uniqueness differs from the registered dataset")
    values = [row["score"] for row in rows if row["score"] is not None]
    if any(type(v) not in {int, float} or not math.isfinite(v) or not -1 <= v <= 1 for v in values):
        raise AuditError("Overview contains invalid cosine scores")
    bands = [{"label": "< 0.0", "lower": -1.0, "upper": 0.0, "articles": sum(v < 0 for v in values)}]
    for n in range(10):
        lower, upper = n / 10, (n + 1) / 10
        bands.append({"label": f"{lower:.1f}–{upper:.1f}", "lower": lower, "upper": upper,
                      "articles": sum(lower <= value < upper or (n == 9 and value == 1) for value in values)})
    expected, logged, scored = len(frame), len(rows), len(values)
    stats = {key: quantile(values, q) for key, q in {
        "minimum": 0, "p25": 0.25, "median": 0.5, "p75": 0.75, "p90": 0.9, "p95": 0.95, "p99": 0.99, "maximum": 1}.items()}
    stats["mean"] = math.fsum(values) / scored if scored else None
    top = [dict(row) for row in ledger.db.execute(TOP_SQL, (data["run"], top_n))]
    question = ledger.get(context.versions["question"], "question")["content"]
    threshold = run.get("threshold")
    validated = run.get("threshold_validated")
    if run.get("calibration"):
        if run.get("calibration_kind") == "adaptive_cutoff_result":
            calibration = ledger.get(run["calibration"], "adaptive_cutoff_result")
            if calibration["status"] != "passed_model_reference":
                raise AuditError("Adaptive tag overview requires the passing frozen model-reference check")
            threshold, validated = calibration["candidate_cutoff"], False
        else:
            calibration = ledger.get(run["calibration"], "similarity_calibration")
            threshold, validated = calibration["threshold"], calibration["passed"]
    cutoff = {"threshold": threshold, "validated": validated, "policy": run.get("cutoff_policy"),
              "calibration": run.get("calibration"), "calibration_kind": run.get("calibration_kind"),
              "comparison": "score >= threshold" if threshold is not None else None}
    snapshot = save(engine, session, rows)
    result = {"run": data["run"], "versions": context.versions, "overview_profile": profile,
        "query": question["query"], "question": question["text"], "phase": run["phase"],
        "sql": {"scores": SCORE_SQL, "top": TOP_SQL}, "parameters": {"scores": [data["run"]], "top": [data["run"], top_n]},
        "snapshot_artifact": snapshot, "expected_articles": expected, "logged_articles": logged,
        "scored_articles": scored, "unprocessed_articles": logged-scored, "pending_articles": expected-logged,
        "coverage_percent": 100 * scored / expected if expected else None,
        "status_counts": dict(Counter(row["status"] for row in rows)), "answer_counts": dict(Counter(str(row["answer"]) for row in rows)),
        "score_statistics": stats, "score_bands": bands, "top_articles": top, "cutoff": cutoff,
        "scope": "Technical distribution/ranking of stored article relevance scores; no confirmed incident count or population estimate",
        "network_calls": 0, "model_calls": 0}
    identifier = ledger.record(session, "article_query_overview", digest(result), result)
    image = ledger.artifacts.put_bytes(plot(bands, expected, scored, cutoff))
    ledger.append(session, "retrieval.artifact.saved", {"artifact": image})
    chart = {"table": identifier, "table_digest": digest(result), "image": image,
             "versions": context.versions, "calculation": "Histogram from frozen score_bands; unscored sources excluded"}
    chart_id = ledger.record(session, "article_query_chart", identifier, chart)
    return {"id": identifier, **result, "chart": chart_id, "image_path": str(ledger.artifacts.root / image)}
