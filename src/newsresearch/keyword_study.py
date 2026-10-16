"""Registered public RSS retrieval diagnostics, never relevance or event judgements."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
from itertools import combinations
import json
import random
import re
import time
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
import xml.etree.ElementTree as ET

from .common import Context, Json, ResearchError, digest, require_active, require_no_credentials, utc

if TYPE_CHECKING:
    from .runtime import Research

TERMS = ["hack", "gehackt", "hackers", "ransomware", "datalek", "datalekken",
         "cyberaanval", "cyberaanvallen", "gijzelsoftware", "datadiefstal"]
DOMAINS = ["nos.nl", "nu.nl", "rtl.nl", "ad.nl", "volkskrant.nl", "nrc.nl",
           "trouw.nl", "telegraaf.nl", "tweakers.net", "security.nl"]
METHOD = "nl-cyber-google-rss-balanced-550-v1"


def manifest() -> list[Json]:
    start, stop = date(2023, 10, 15), date(2026, 10, 16)
    boundaries = [start + timedelta(days=(stop-start).days*i//5) for i in range(6)]
    rows = []
    for domain in DOMAINS:
        for i in range(5):
            for term in [*TERMS, "control"]:
                words = "(" + " OR ".join(TERMS) + ")" if term == "control" else term
                query = (f"{words} site:{domain} after:{boundaries[i]-timedelta(days=1)} "
                         f"before:{boundaries[i+1]+timedelta(days=1)}")
                row = {"term": term, "domain": domain, "period": i+1,
                       "start": boundaries[i].isoformat(), "stop": boundaries[i+1].isoformat(),
                       "query": query, "parameters": {"q": query, "hl": "nl", "gl": "NL", "ceid": "NL:nl"}}
                row["id"] = digest(row)
                rows.append(row)
    random.Random(20261016).shuffle(rows)
    return rows


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def fetch(parameters: Json) -> tuple[int, bytes]:
    url = "https://news.google.com/rss/search?" + urlencode(parameters)
    request = Request(url, headers={"User-Agent": "NewsResearch/1.0 (public RSS metadata study)"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=25) as response:
            return response.status, response.read(8_000_001)
    except HTTPError as error:
        return error.code, error.read(8_000_001)


def parse(raw: bytes, query: Json) -> Json:
    if len(raw) > 8_000_000:
        raise ValueError("response_too_large")
    root = ET.fromstring(raw)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("not_rss")
    items, missing_dates, outside, quarantined = [], 0, 0, 0
    nodes = root.findall("./channel/item")
    for node in nodes:
        row: Json = {key: node.findtext(key) for key in ["title", "link", "guid", "pubDate"]}
        source = node.find("source")
        row["publisher"] = source.text if source is not None else None
        row["publisher_url"] = source.get("url") if source is not None else None
        try:
            require_no_credentials(row)
        except ResearchError:
            quarantined += 1
            continue
        try:
            stamp = parsedate_to_datetime(row["pubDate"] or "")
            if stamp.utcoffset() is None:
                raise ValueError("missing_timezone")
            day = stamp.astimezone(timezone.utc).date().isoformat()
        except (ValueError, TypeError, OverflowError):
            missing_dates += 1
            continue
        if not query["start"] <= day < query["stop"]:
            outside += 1
            continue
        row["published_utc"] = stamp.astimezone(timezone.utc).isoformat()
        row["identity"] = row["guid"] or row["link"] or digest(row)
        title = row["title"] or ""
        suffix = " - " + (row["publisher"] or "")
        if suffix != " - " and title.endswith(suffix):
            title = title[:-len(suffix)]
        row["title_words"] = re.findall(r"[^\W_]+", title.casefold())
        row["title_publisher_identity"] = digest([row["publisher_url"], row["title_words"]])
        items.append(row)
    return {"items": items, "returned": len(nodes), "in_window": len(items),
            "missing_dates": missing_dates, "outside_window": outside,
            "quarantined": quarantined, "possibly_capped": len(nodes) >= 100}


def rows(engine: Research, kind: str) -> list[Json]:
    return [{"record_id": r["id"], **json.loads(r["payload"])} for r in
            engine.ledger.db.execute("SELECT id,payload FROM records WHERE kind=? ORDER BY rowid", (kind,))]


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    selection = engine.ledger.get(context.versions["selection"], "selection")["content"]
    queries = manifest()
    if (policy.get("method") != METHOD or policy.get("requests") != queries
            or selection.get("rules") != queries):
        raise ResearchError("Exact registered 550-query public RSS manifest required")
    action = data.get("action", "run")
    previous = [r for r in rows(engine, "keyword_query") if r["versions"] == context.versions]
    reservations = [r for r in rows(engine, "keyword_reservation") if r["versions"] == context.versions]
    if action == "run":
        if engine.config.offline or data.get("execute") is not True:
            raise ResearchError("Explicit online execution required")
        limit = data.get("limit", 25)
        if not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ResearchError("Batch size must be 1 through 50")
        # Unknown dispatch outcomes remain reserved and are never silently retried.
        spent = {r["query_id"] for r in reservations}
        pending = [q for q in queries if q["id"] not in spent][:limit]
        for query in pending:
            engine.ledger.record(session, "keyword_reservation", query["id"],
                                 {"query_id": query["id"], "versions": context.versions,
                                  "query": query, "intended_at": utc()})
            start = utc()
            # Audit writes are outside this exception boundary: audit failure must stop.
            result: Json
            try:
                status, raw = fetch(query["parameters"])
            except (OSError, TimeoutError) as error:
                result = {"status": "failed", "http_status": None, "error": type(error).__name__}
            else:
                response_hash = hashlib.sha256(raw).hexdigest()
                retained = None
                try:
                    require_no_credentials(raw.decode("utf-8", errors="replace"))
                except ResearchError:
                    pass
                else:
                    retained = engine.ledger.artifacts.put_bytes(raw)
                    engine.ledger.append(session, "keyword.response.saved", {"artifact": retained})
                result = {"status": "completed" if status == 200 else "failed", "http_status": status,
                          "raw_hash": response_hash, "raw_artifact": retained, "error": None}
                if status == 200:
                    try:
                        result.update(parse(raw, query))
                    except (ValueError, ET.ParseError):
                        result.update(status="failed", error="invalid_rss")
            result.update(query_id=query["id"], query=query, versions=context.versions,
                          started_at=start, completed_at=utc())
            engine.ledger.record(session, "keyword_query", query["id"], result)
            print(json.dumps({"term": query["term"], "domain": query["domain"], "period": query["period"],
                              "status": result["status"], "returned": result.get("returned")}), flush=True)
            # Stop a denial/rate-limit response; no automatic retries or evasion.
            if result.get("http_status") in {403, 429, 503}:
                break
            time.sleep(0.9)
        previous = [r for r in rows(engine, "keyword_query") if r["versions"] == context.versions]
        reservations = [r for r in rows(engine, "keyword_reservation") if r["versions"] == context.versions]
    elif action != "report":
        raise ResearchError("Unknown keyword study action")
    result = analyze(queries, previous, reservations)
    result.update(versions=context.versions, query_results=[r["record_id"] for r in previous],
                  generated_at=utc(), model_calls=0, newsapi_calls=0, relevance_scored=0)
    identifier = engine.ledger.record(session, "keyword_study", digest(result), result)
    return {"id": identifier, **result}


def analyze(queries: list[Json], results: list[Json], reservations: list[Json]) -> Json:
    successful = [r for r in results if r["status"] == "completed"]
    pools: dict[str, set[str]] = {t: set() for t in [*TERMS, "control"]}
    records = {}
    term_titles: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    by_stratum: dict[tuple[str, int], dict[str, set[str]]] = {}
    for r in successful:
        term, query = r["query"]["term"], r["query"]
        stratum = by_stratum.setdefault((query["domain"], query["period"]), {})
        stratum[term] = {item["identity"] for item in r["items"]}
        for item in r["items"]:
            records[item["identity"]] = item
            pools[term].add(item["identity"])
        for field in ["returned", "missing_dates", "outside_window", "quarantined"]:
            missing[field] += r[field]
    union = set().union(*(pools[t] for t in TERMS))
    total = union | pools["control"]
    for item in records.values():
        term_titles.update(set(item["title_words"]) & set(TERMS))
    table = [{"term": t, "successful_queries": sum(r["query"]["term"] == t for r in successful),
              "unique_records": len(pools[t]), "title_occurrences_in_union": term_titles[t],
              "exclusive_vs_other_terms": len(pools[t] - set().union(*(pools[u] for u in TERMS if u != t)))}
             for t in TERMS]
    # Fixed first 4 periods train subset selection; final period held out chronologically.
    complete = {k: p for k, p in by_stratum.items() if set(p) == set([*TERMS, "control"])}
    train = {k: p for k, p in complete.items() if k[1] < 5}
    test = {k: p for k, p in complete.items() if k[1] == 5}
    def coverage(subset: tuple[str, ...], strata: dict[tuple[str, int], dict[str, set[str]]]) -> Json:
        numerator = denominator = 0
        for pools_s in strata.values():
            reference = set().union(*pools_s.values())
            numerator += len(set().union(*(pools_s[t] for t in subset)) & reference)
            denominator += len(reference)
        return {"found": numerator, "reference": denominator,
                "fraction": numerator / denominator if denominator else None}
    subsets = []
    for size in range(1, 7):
        candidates = [(coverage(s, train)["found"], s) for s in combinations(TERMS, size)]
        _, best = max(candidates, key=lambda pair: (pair[0], tuple(-TERMS.index(t) for t in pair[1])))
        subsets.append({"size": size, "terms": list(best), "train": coverage(best, train),
                        "heldout": coverage(best, test)})
    return {"planned": len(queries), "dispatched": len(reservations), "completed": len(successful),
            "failed": len(results)-len(successful), "unknown": len(reservations)-len(results),
            "pending": len(queries)-len(reservations), "possibly_capped": sum(r["possibly_capped"] for r in successful),
            "counts": dict(missing), "unique_records": len(total), "individual_terms_union": len(union),
            "control_unique": len(pools["control"]), "control_only": len(pools["control"]-union),
            "title_publisher_unique": len({r["title_publisher_identity"] for r in records.values()}),
            "terms": table, "subsets": subsets, "complete_strata": len(complete),
            "train_strata": len(train), "heldout_strata": len(test),
            "examples": list(records.values())[:5],
            "query_overview": [{"query": r["query"]["query"], "status": r["status"],
                                "returned": r.get("returned"), "in_window": r.get("in_window"),
                                "first": (r.get("items") or [None])[0]} for r in results]}
