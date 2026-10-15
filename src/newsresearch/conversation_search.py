"""Bounded, explicit local keyword retrieval for an audited conversation."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import TYPE_CHECKING

from .common import Context, Json, ResearchError, digest, require_active, utc

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "conversation-local-fts-v1"
MAX_ARTICLES = 20
MAX_PASSAGES_PER_ARTICLE = 2


def query_expression(query: str) -> str:
    """Quote literal keywords: the browser cannot supply FTS operators or SQL."""
    words = list(dict.fromkeys(re.findall(r"[^\W_]+", query.casefold(), re.UNICODE)))
    if not words or len(words) > 40 or len(query.encode("utf-8")) > 2000:
        raise ResearchError("Use 1 through 40 literal search keywords, within 2000 UTF-8 bytes")
    return " OR ".join('"' + word + '"' for word in words)


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"query", "question", "key", "parent_conversation"}:
        raise ResearchError("Unsupported conversation retrieval fields")
    engine._require(context, {"dataset"})
    for name in ("query", "question", "key"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise ResearchError("Conversation search requires a query, question and stable key")
    expression = query_expression(data["query"])
    versions = {"dataset": context.versions["dataset"]}
    definitions = {
        "protocol": {"method": METHOD, "purpose": "Explicit exploratory keyword retrieval for conversation",
            "rules": "Casefolded literal words joined by OR; FTS5 BM25 ascending; source ID/offset tie breaks",
            "article_limit": MAX_ARTICLES, "passages_per_article": MAX_PASSAGES_PER_ARTICLE,
            "limitations": "Lexical retrieval, not semantic vector search, exhaustive relevance tagging or incident counts"},
        "question": {"text": data["question"]},
        "selection": {"rules": {"dataset": versions["dataset"], "query": data["query"],
            "fts_expression": expression, "method": METHOD, "article_limit": MAX_ARTICLES,
            "passages_per_article": MAX_PASSAGES_PER_ARTICLE}},
        "profile": {"mode": "exploratory", "population_estimate": False, "method": METHOD},
    }
    for kind, content in definitions.items():
        versions[kind] = engine._version(session, context, {"kind": kind,
            "key": data["key"] + "-" + kind, "content": content, "amend_latest": True,
            "reason": "Register explicit local conversation search before retrieval"})["id"]
    dataset = engine.ledger.get(versions["dataset"], "dataset")
    sources = dataset["source_versions"]
    # The dataset filter occurs before counting or limiting. FTS ranking is
    # materialized before window aggregation because SQLite bm25 is auxiliary.
    frame = ("p.source_id IN (SELECT value FROM records d,json_each(d.payload,'$.source_versions') "
        "WHERE d.id=? AND d.kind='dataset')")
    cte = ("WITH matched AS MATERIALIZED (SELECT p.id,p.source_id,p.start,bm25(passage_fts) AS score "
        "FROM passage_fts JOIN passages p ON p.id=passage_fts.id WHERE passage_fts MATCH ? "
        "AND " + frame + "), "
        "ranked AS (SELECT *,row_number() OVER (PARTITION BY source_id ORDER BY score,start,id) AS n "
        "FROM matched), selected AS (SELECT source_id,min(score) AS best FROM ranked "
        "GROUP BY source_id ORDER BY best,source_id LIMIT ?) ")
    sql = cte + ("SELECT r.id,r.source_id,r.score,s.best FROM ranked r JOIN selected s USING(source_id) "
        "WHERE r.n<=? ORDER BY s.best,r.source_id,r.n")
    parameters = [expression, versions["dataset"], MAX_ARTICLES, MAX_PASSAGES_PER_ARTICLE]
    count_sql = ("SELECT count(*) AS passages,count(DISTINCT p.source_id) AS articles "
        "FROM passage_fts JOIN passages p ON p.id=passage_fts.id WHERE passage_fts MATCH ? "
        "AND " + frame)
    engine.ledger.append(session, "conversation.retrieval.intended", {"method": METHOD,
        "sql": sql, "parameters": parameters, "count_sql": count_sql, "versions": versions})
    started_at = utc()
    try:
        counts = engine.ledger.db.execute(count_sql, parameters[:2]).fetchone()
        hits = list(engine.ledger.db.execute(sql, parameters))
    except sqlite3.Error as error:
        raise ResearchError("Local keyword retrieval failed; no answer was dispatched") from error
    source_rows: list[Json] = []
    evidence: list[Json] = []
    seen: set[str] = set()
    for hit in hits:
        source = json.loads(engine.ledger.db.execute("SELECT payload FROM sources WHERE id=?",
            (hit["source_id"],)).fetchone()[0])
        title, url = source.get("title", ""), source.get("url")
        if hit["source_id"] not in seen:
            seen.add(hit["source_id"])
            source_rows.append({"rank": len(source_rows) + 1, "source_version": hit["source_id"],
                "title": title, "url": url, "score": hit["best"]})
        evidence.append({**engine._evidence(hit["id"]), "title": title, "url": url})
    searchable = engine.ledger.db.execute("SELECT count(DISTINCT p.source_id) FROM passages p WHERE " + frame,
        (versions["dataset"],)).fetchone()[0]
    result = {"method": METHOD, "query": data["query"], "question": data["question"],
        "fts_expression": expression, "sql": sql, "parameters": parameters,
        "count_sql": count_sql, "count_parameters": parameters[:2], "versions": versions,
        "query_started_at": started_at, "query_completed_at": utc(), "pending_processing": 0,
        "dataset_articles": len(sources), "matching_articles": counts["articles"],
        "searchable_articles": searchable, "text_unavailable_articles": len(sources) - searchable,
        "matching_passages": counts["passages"], "returned_articles": len(source_rows),
        "returned_passages": len(evidence), "article_limit": MAX_ARTICLES,
        "source_rows": source_rows, "evidence": evidence,
        "missing_scores": None, "embedding_requests": 0, "model_calls": 0,
        "cutoff": None, "tagging": "No binary relevance decisions or new tags",
        "scope": "Dataset-bounded literal keyword retrieval; not corpus-wide semantic relevance",
        "inspection_observation": "Returned passages retained; human reading unobserved"}
    identifier = engine.ledger.record(session, "conversation_retrieval", digest({"key": data["key"],
        "versions": versions, "parent": data.get("parent_conversation")}), result)
    from .conversation import start_from_evidence
    selection = start_from_evidence(engine, session, Context(context.objective, context.actor, versions), {
        "key": data["key"], "origin": {"kind": "conversation_retrieval", "id": identifier},
        "question": data["question"], "query": data["query"], "source_rows": source_rows,
        "evidence": evidence, "parent_conversation": data.get("parent_conversation")})
    from .presentation import record
    text = render({"id": identifier, **result})
    presentation = record(engine, session, Context(context.objective, context.actor, versions), {
        "results": [{"kind": "conversation_retrieval", "id": identifier}], "markdown": text,
        "destination": "local_app"})
    return {"id": identifier, **result, "selection": selection, "presentation": presentation}


def render(result: Json) -> str:
    # Escape structural Markdown and admit web source links only.
    from urllib.parse import urlsplit
    def escaped(value: object) -> str:
        return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("\n", " ")
    lines = ["### Explicit local corpus search", "", "Query: " + escaped(result["query"]),
        f"Dataset scope: {result['dataset_articles']} articles; {result['matching_articles']} keyword matches "
        f"in {result['matching_passages']} passages. Returned {result['returned_articles']} articles / "
        f"{result['returned_passages']} passages (maximum {MAX_ARTICLES} articles).", "",
        "FTS5 BM25 ranks lexical matches (lower is better); these are not semantic similarities or probabilities. "
        f"No relevance cutoff or yes/no tags applied. {result['text_unavailable_articles']} articles have no searchable "
        "passages and cannot match; semantic coverage "
        "is unmeasured. No embedding or model call for retrieval.", ""]
    for row in result["source_rows"]:
        title = escaped(row.get("title") or row["source_version"])
        url = row.get("url")
        try:
            if (isinstance(url, str) and urlsplit(url).scheme in {"http", "https"}
                    and urlsplit(url).netloc and not any(c in url for c in "\r\n<>")):
                title = f"[{title}](<{url}>)"
        except ValueError:
            pass
        lines.append(f"{row['rank']}. {title} — BM25 {row['score']:.6g}; source `{row['source_version']}`")
    if not result["source_rows"]:
        lines.append("No keyword matches. No evidence available for an answer from this search.")
    return "\n".join(lines)
