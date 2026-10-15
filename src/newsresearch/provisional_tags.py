"""Explicit provisional retrieval cutoffs, separate from held-out calibration."""
from __future__ import annotations

from collections import Counter
import html
import math
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .retrieval import implementation
from .tagging import same_versions

if TYPE_CHECKING:
    from .runtime import Research


def literal(value: object) -> str:
    text = html.escape(str(value or "Zonder titel"), quote=False).replace("\n", " ").replace("\r", " ")
    for character in ("\\", "|", "[", "]", "*", "_", "`", "#"):
        text = text.replace(character, "\\" + character)
    return text


def render(overview: Json) -> str:
    cutoff = str(overview["cutoff"]["threshold"]).replace(".", ",")
    counts = overview["answer_counts"]
    def number(value: int) -> str:
        return f"{value:,}".replace(",", ".")

    lines = [f"Voor de query **{literal(overview['query'])}** geldt voorlopig **cutoff {cutoff}**.", "",
        f"Scope: {number(overview['expected_articles'])} artikelen in de pilot; {number(overview['pending_articles'])} nog wachtend op verwerking.", "",
        "| Uitkomst | Regel | Artikelen |", "|---|---|---:|",
        f"| Ja | Score ≥ {cutoff} | {number(counts.get('yes', 0))} |",
        f"| Nee | Score < {cutoff} | {number(counts.get('no', 0))} |",
        f"| Onverwerkt | Geen bruikbare score | {number(overview['unprocessed_articles'])} |", "",
        "**Deze cutoff is voorlopig en nog niet gevalideerd met menselijke beoordelingen.** ‘Ja’ betekent geselecteerd door deze zoekregel; het bevestigt geen AI-incident. Ontbrekende scores tellen niet als nee.", "",
        f"De {len(overview['top_articles'])} hoogst scorende artikelen:", "",
        "| Score | Uitkomst | Artikel |", "|---:|---|---|"]
    for article in overview["top_articles"]:
        title = literal(article["title"])
        url = article.get("url")
        try:
            safe_url = isinstance(url, str) and urlsplit(url).scheme in {"https", "http"} and bool(urlsplit(url).netloc)
        except ValueError:
            safe_url = False
        if safe_url:
            title = f"[{title}]({quote(url, safe=':/?#=&%+-._~')})"
        score = f"{article['score']:.4f}".replace(".", ",")
        lines.append(f"| {score} | {'Ja' if article['answer'] == 'yes' else 'Nee'} | {title} |")
    return "\n".join(lines)


def apply(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"scores", "threshold", "reason", "reuse_cache", "top"}:
        raise ResearchError("Provisional cutoff does not accept corpus filters or inference settings")
    threshold = data.get("threshold")
    if (not isinstance(threshold, (int, float)) or isinstance(threshold, bool)
            or not -1 <= threshold <= 1 or not math.isfinite(threshold)):
        raise ResearchError("Provisional cosine threshold must be finite and within [-1,1]")
    if not isinstance(data.get("reason"), str) or not data["reason"].strip():
        raise ResearchError("Record why this provisional cutoff was selected")
    top = data.get("top", 5)
    if type(top) is not int or not 1 <= top <= 100:
        raise ResearchError("Top article limit must be between 1 and 100")
    ledger = engine.ledger
    scored = ledger.get(data["scores"], "article_query_run")
    same_versions(scored, context)
    frame = ledger.get(context.versions["dataset"], "dataset")["source_versions"]
    allowed = set(frame)
    if (scored["phase"] != "scores" or set(scored["source_ids"]) != set(frame)
            or scored["expected_articles"] != len(frame) or len(set(frame)) != len(frame)
            or len(scored["result_ids"]) != len(frame) or len(set(scored["result_ids"])) != len(frame)):
        raise ResearchError("Apply a provisional cutoff only to a complete original score frame")
    policy_content = {"method": "provisional-cosine-query-cutoff-v1", "scores": data["scores"],
        "score_run": scored["run"], "versions": context.versions, "threshold": threshold,
        "comparison": "score >= threshold", "validated": False, "reason": data["reason"],
        "decision_origin": "deterministic_similarity_threshold", "selection_priority": "recall",
        "limitations": "Heuristic operating value; no measured recall, precision, F2 or incident validity",
        "validation_next": "Independent human calibration and separate held-out evaluation; no labels or accuracy invented",
        "scope": "Provisional article retrieval tags; never accepted dossier findings"}
    policy = engine._version(session, context, {"kind": "policy",
        "key": "provisional-query-cutoff-" + digest({"scores": data["scores"], "threshold": threshold}),
        "content": policy_content, "amend_latest": True, "reason": data["reason"]})["id"]
    code = implementation(engine)
    manifest = {"scores": data["scores"], "cutoff_policy": policy, "versions": context.versions,
        "expected_articles": len(frame), "source_ids": frame, "implementation_digest": code,
        "phase": "provisional_tags", "threshold": threshold, "threshold_validated": False,
        "comparison": "score >= threshold"}
    run_id = ledger.record(session, "article_query_manifest", digest(manifest), manifest)
    existing = ledger.db.execute("SELECT 1 FROM records WHERE kind='article_query_result' AND json_extract(payload,'$.run')=? LIMIT 1", (run_id,)).fetchone()
    if existing and data.get("reuse_cache") is not True:
        raise ResearchError("Existing provisional results require explicit reuse_cache")
    ids, seen = [], set()
    counts: Counter[str] = Counter()
    started = utc()
    for parent in scored["result_ids"]:
        original = ledger.get(parent, "article_query_result")
        same_versions(original, context)
        source, value = original["source_version"], original["score"]
        if (source not in allowed or source in seen or original["run"] != scored["run"]
                or original["phase"] != "scores" or original["answer"] is not None
                or (value is not None and (type(value) not in {int, float} or not math.isfinite(value) or not -1 <= value <= 1))):
            raise AuditError("Provisional input does not reconcile to valid original scores")
        seen.add(source)
        answer = ("yes" if value >= threshold else "no") if value is not None else None
        counts[str(answer)] += 1
        key = digest({"run": run_id, "source": source})
        cached = ledger.db.execute("SELECT id FROM records WHERE kind='article_query_result' AND logical_key=?", (key,)).fetchone()
        if cached:
            ledger.append(session, "similarity.result.reused", {"result": cached[0], "run": run_id})
            ids.append(cached[0])
            continue
        row = {**original, "run": run_id, "phase": "provisional_tags", "parent_result": parent,
            "answer": answer, "threshold": threshold, "calibration": None, "cutoff_policy": policy,
            "threshold_validated": False, "decision_origin": "deterministic_similarity_threshold",
            "comparison": "score >= threshold", "status": "provisionally_classified" if value is not None else original["status"],
            "scoring_method": original["method"], "method": policy_content["method"],
            "answer_semantics": "Selected by an unvalidated retrieval cutoff; not a confirmed incident or reviewed relevance judgement",
            "actor": context.actor, "session": session, "started_at": started, "completed_at": utc(),
            "tag_application_started_at": started, "tag_applied_at": utc(),
            "implementation_digest": code, "review_status": "provisional_unvalidated_cutoff"}
        ids.append(ledger.record(session, "article_query_result", key, row))
    if (seen != set(frame) or counts["None"] != scored["missing_articles"]
            or counts["yes"] + counts["no"] != scored["scored_articles"]):
        raise AuditError("Provisional decisions do not reconcile with original coverage")
    result = {**manifest, "run": run_id, "result_ids": ids, "answer_counts": dict(counts),
        "classified_articles": counts["yes"] + counts["no"], "missing_articles": counts["None"],
        "network_calls": 0, "model_calls": 0}
    identifier = ledger.record(session, "article_query_run", digest(result), result)
    from .query_overview import overview
    from .presentation import record

    summary = overview(engine, session, context, {"run": run_id, "top": top})
    presented = record(engine, session, context, {"results": [
        {"kind": "article_query_run", "id": identifier},
        {"kind": "article_query_overview", "id": summary["id"]},
        {"kind": "article_query_chart", "id": summary["chart"]}],
        "markdown": render(summary), "destination": "codex_chat"})
    return {"id": identifier, **{k: v for k, v in result.items() if k not in {"result_ids", "source_ids"}},
        "overview": summary, "presentation": presented}
