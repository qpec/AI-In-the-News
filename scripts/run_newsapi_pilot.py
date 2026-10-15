"""Register and execute only the user's bounded Dutch cyber-news search pilot."""
from __future__ import annotations

import argparse
import json
import os

from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research

ACTOR = "codex:nl-cyber-search-pilot"
OBJECTIVE = "Compare Dutch cyber-incident article retrieval, 2023-10-15 to 2026-10-15, at most 200 NewsAPI.ai tokens"
NL = "http://en.wikipedia.org/wiki/Netherlands"
BASE = ["hack", "ransomware", "datalek"]
EXPANDED = ["hack", "hacks", "gehackt", "hacker", "hackers", "ransomware", "gijzelsoftware",
            "datalek", "datalekken", "cyberaanval", "cyberaanvallen", "gegevenslek", "gegevensdiefstal"]


def requests() -> list[dict]:
    base = {"action": "getArticles", "resultType": "articles", "dateStart": "2023-10-15",
            "dateEnd": "2026-10-15", "lang": "nld", "keyword": BASE, "keywordOper": "or",
            "keywordLoc": "body,title", "keywordSearchMode": "simple", "articlesPage": 1,
            "articlesCount": 100, "articlesSortBy": "rel", "articlesSortByAsc": False,
            "includeArticleBody": False, "dataType": "news", "isDuplicateFilter": "keepAll"}
    broad = {**base, "keyword": EXPANDED}
    local = {**broad, "sourceLocationUri": NL}
    local.pop("lang")
    return [base, broad, {**broad, "sourceLocationUri": NL}, {**broad, "locationUri": NL},
            {**broad, "conceptUri": NL}, local, {**broad, "keywordLoc": "title"},
            {**broad, "articlesSortBy": "date", "articlesSortByAsc": True},
            {**broad, "dateEnd": "2023-12-31"},
            {**broad, "dateStart": "2024-01-01", "dateEnd": "2024-12-31"}]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--index", type=int)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--amend-archive", action="store_true")
    parser.add_argument("--amend-string", action="store_true")
    parser.add_argument("--amend-clean", action="store_true")
    parser.add_argument("--amend-filters", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    workspace = default_workspace().parent / "research-nl-cyber-20261015"
    engine = Research(workspace, config=Config(offline=not args.execute))
    context_path = workspace / "pilot-context.json"
    try:
        if args.prepare:
            if context_path.exists():
                raise RuntimeError("Pilot context already exists; preserve the registered pilot")
            versions = {}
            content = {
                "protocol": {"method": "nl-cyber-search-pilot-v1", "requests": requests(),
                    "comparison": "Provider match totals, page-1 overlap, language/source/date coverage. No relevance labels or recall estimates.",
                    "retention": "Private API response metadata requested without article bodies; exact responses protected outside Git",
                    "budget": "Reserve 20 tokens per dispatch including failures/unknown outcomes; 10 maximum; no retries or pagination.",
                    "price_basis": "https://newsapi.ai/plans, accessed 2026-10-15: archive article search 5 tokens/searched year; at most four calendar years.",
                    "scope_limitations": "Dutch language and publisher country do not prove an incident occurred in the Netherlands; geographic metadata can be incomplete. No model or manual relevance judgement in this pilot."},
                "question": {"text": OBJECTIVE},
                "selection": {"rules": requests(), "stage": "exploratory retrieval pilot, not incident enumeration"},
                "dossier_definition": {"unit": "One real-world cyber incident in the Netherlands, potentially reported by several sources; no dossiers formed in this pilot"},
                "profile": {"mode": "exploratory", "population_estimate": False},
                "policy": {"method": "newsapi-probe-approval-v1", "authorization_id": "nl-cyber-search-pilot-2026-10-15-200",
                    "max_tokens": 200, "requests": requests(), "authorized_by": "user in current Codex chat",
                    "instruction": "Now run the tests with 200 NewsAPI.ai tokens max to find the best search strategy for Dutch articles about hacks, ransomware and datalekken over the past 3 years."}}
            for kind, body in content.items():
                result = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1", "content": body},
                                        objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = result["id"]
            context_path.write_text(json.dumps(versions), encoding="utf-8")
            print(json.dumps({"registered_versions": versions, "workspace": str(workspace), "network_calls": 0}))
            return
        versions = json.loads(context_path.read_text(encoding="utf-8"))
        if args.summary:
            result = engine.execute("newsapi_overview", objective=OBJECTIVE, actor=ACTOR, versions=versions)
            rows = result["results"][-3:]
            text = "The pilot is complete, but **the best three-year strategy is not established: the provider did not search its archive**.\n\n"
            text += "Requested scope: Dutch news, 15 October 2023-15 October 2026, title/body search, page 1 (up to 100), provider relevance order.\n\n"
            text += "| Search | Provider matches | Collected | Archive used |\n|---|---:|---:|---|\n"
            for label, row in zip(["hack OR ransomware OR datalek", "Expanded Dutch terms", "Expanded terms + Netherlands publishers"], rows):
                text += f"| {label} | {row['total']:,} | {row['returned']} | No |\n"
            text += ("\nExpanded terms: `hack OR hacks OR gehackt OR hacker OR hackers OR ransomware OR gijzelsoftware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen OR gegevenslek OR gegevensdiefstal`. "
                     "All three comparisons used the same complex-query syntax and default keyword matching; the publisher condition was "
                     "`sourceLocationUri=http://en.wikipedia.org/wiki/Netherlands`. No Cyber Crime category filter was required.\n\n")
            text += (f"The expanded query returned {result['expanded_match_increase_percent']:.1f}% more provider matches than the three-term query. "
                     "It is the provisional starting query for broader Dutch-language retrieval. Publisher country is an optional narrower branch; it does not establish where an incident happened. "
                     "No relevance evaluation establishes which query finds the most actual Netherlands incidents.\n\n")
            text += (f"Budget and processing: **{result['dispatches']} dispatches; 200/200 tokens conservatively reserved; no further requests**. "
                     f"The provider explicitly reported {result['explicitly_reported_tokens']:g} tokens across five calls. Billing for "
                     f"{result['dispatches_with_unavailable_billing']} dispatches is unavailable; 200 is the reservation ceiling, not observed expenditure. "
                     "Six requests succeeded, three returned HTTP 400, and one returned a non-JSON error before result capture and remains unresolved. "
                     "The four problematic dispatches arose while correcting the complex-query adapter; they were not strategy results. "
                     f"There are {result['unique_collected_uris']} distinct collected article URIs. Articles have not been grouped into incidents.\n\n")
            text += ("Archive checks: both the simple and corrected complex requests for 15 October-31 December 2023 returned zero, "
                     "with `req-archive=0` and `req-years=0`. The full-period comparisons also reported no archive use. "
                     "These are not evidence of no historical articles. **Archive access/routing must be resolved with the account/provider before collecting the three-year corpus**; the account entitlement cause is not confirmed.\n\n")
            text += "Examples, in provider rank order for the expanded query:\n\n"
            for i, a in enumerate(rows[1]["articles"][:3], 1):
                text += f"{i}. [{a['title']}]({a['url']}) - {a['date']}\n"
            text += ("\nOnly page 1 was collected for each successful nonempty query; all other matching pages remain pending. "
                     "Scored articles: 0. No validated relevance score/cutoff, yes/no labels, model judging, or reviewed incident findings were produced. "
                     "Provider order and match totals do not measure recall or precision. Exact requests, results and this prepared overview are preserved in protected storage; UI delivery is unverified.")
            captured = engine.execute("record_presentation", {"results": [{"kind": "newsapi_overview", "id": result["id"]}],
                "markdown": text, "destination": "codex_chat"}, objective=OBJECTIVE, actor=ACTOR, versions=versions)
            print(json.dumps({"id": result["id"], "presentation": captured["id"], "markdown": text,
                              "overlap": result["overlap"]}, ensure_ascii=True))
            return
        if args.amend_filters:
            policy = engine.ledger.get(versions["policy"], "policy")["content"]
            extra = [{k: value for k, value in p.items() if k not in {"isDuplicateFilter", "dataType"}}
                     for p in policy["requests"][26:34]]
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "sdk_default_filter_queries": extra}
                if kind == "policy":
                    new["requests"] = old["requests"] + extra
                result = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1",
                    "content": new, "supersedes": versions[kind],
                    "reason": "Remove redundant top-level dataType and isDuplicateFilter to use SDK defaults with a complex query; retain same cumulative budget"},
                    objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = result["id"]
            context_path.write_text(json.dumps(versions), encoding="utf-8")
            print(json.dumps({"amended": True, "network_calls": 0}))
            return
        if args.amend_clean:
            policy = engine.ledger.get(versions["policy"], "policy")["content"]
            extra = [{k: value for k, value in p.items() if k not in {"dateStart", "dateEnd", "keywordSearchMode"}}
                     for p in policy["requests"][18:26]]
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "clean_complex_queries": extra}
                if kind == "policy":
                    new["requests"] = old["requests"] + extra
                result = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1",
                    "content": new, "supersedes": versions[kind],
                    "reason": "Provider requires all search conditions inside query; remove redundant top-level dates and search mode. Default keyword mode retained. Same budget."},
                    objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = result["id"]
            context_path.write_text(json.dumps(versions), encoding="utf-8")
            print(json.dumps({"amended": True, "network_calls": 0}))
            return
        if args.amend_string:
            policy = engine.ledger.get(versions["policy"], "policy")["content"]
            extra = [{**p, "query": json.dumps(p["query"], sort_keys=True)}
                     for p in policy["requests"][10:18]]
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "sdk_serialized_queries": extra}
                if kind == "policy":
                    new["requests"] = old["requests"] + extra
                result = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1",
                    "content": new, "supersedes": versions[kind],
                    "reason": "Object-form queries returned HTTP 400; register official SDK JSON-string serialization diagnostic before execution; same cumulative budget"},
                    objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = result["id"]
            context_path.write_text(json.dumps(versions), encoding="utf-8")
            print(json.dumps({"amended": True, "network_calls": 0}))
            return
        if args.amend_archive:
            registered = engine.ledger.get(versions["policy"], "policy")["content"]
            # Preserve the two completed requests and register complex-query
            # diagnostics before further dispatch. The budget identity is unchanged.
            complex_requests = []
            for i in [8, 0, 1, 2, 3, 4, 6, 9]:
                original = requests()[i]
                filters = {k: original[k] for k in ["dateStart", "dateEnd", "lang"] if k in original}
                filters["keyword"] = {"$or": original["keyword"]}
                for k in ["sourceLocationUri", "locationUri", "conceptUri", "keywordLoc"]:
                    if k in original:
                        filters[k] = original[k]
                p = {k: v for k, v in original.items() if k not in
                     {"keyword", "keywordOper", "lang", "sourceLocationUri", "locationUri", "conceptUri", "keywordLoc"}}
                p["query"] = {"$query": filters}
                complex_requests.append(p)
            registered = {**registered, "requests": registered["requests"] + complex_requests}
            result = engine.execute("version", {"kind": "policy", "key": "nl-cyber-search-pilot-v1",
                    "content": registered, "supersedes": versions["policy"],
                    "reason": "Simple requests reported req-archive=0 despite historical dates; add documented complex-query diagnostics, retaining the original 200-token authorization and spent reservations"},
                    objective=OBJECTIVE, actor=ACTOR)
            versions["policy"] = result["id"]
            for kind in ["protocol", "selection"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "archive_diagnostic_requests": complex_requests,
                       "amendment": "Compare documented complex-query form after archive non-use; earlier zero was not historical absence"}
                v = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1", "content": new,
                    "supersedes": versions[kind], "reason": "Register archive diagnostic before dispatch"},
                    objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = v["id"]
            context_path.write_text(json.dumps(versions), encoding="utf-8")
            print(json.dumps({"amended": True, "network_calls": 0, "remaining_dispatches": 8}))
            return
        approved = engine.ledger.get(versions["policy"], "policy")["content"]["requests"]
        if args.index is None or not 0 <= args.index < len(approved) or not args.execute:
            raise RuntimeError("Explicit execution and a registered request index required")
        result = engine.execute("newsapi_probe", {"execute": True, "parameters": approved[args.index]},
                                objective=OBJECTIVE, actor=ACTOR, versions=versions)
        p = result["parameters"]
        text = (f"Pilot test {args.index + 1}: `{json.dumps(p, ensure_ascii=False, sort_keys=True)}`\n\n"
                f"Status: {result['status']}; HTTP {result['http_status']}. Provider total: {result['provider_total']}; "
                f"returned {result['returned']}; scored 0. Cumulative conservative reservation: {result['cumulative_reserved_tokens']}/200 tokens. "
                f"Provider billing headers: `{json.dumps(result['headers'])}`.\n\n"
                "Page 1 only; remaining pages uncollected. No incident or relevance assessment; no calibrated score, cutoff, or yes/no labels. "
                "Provider relevance order is unvalidated. Examples below follow the returned order.\n\n")
        if result["provider_notes"]:
            text += f"Provider diagnostics: `{json.dumps(result['provider_notes'], ensure_ascii=False)}`\n\n"
        for i, article in enumerate(result["articles"][:5], 1):
            text += f"{i}. [{article.get('title', '(untitled)')}]({article.get('url', '')}) — {article.get('dateTimePub', article.get('date'))}; score {article.get('sim', 'unavailable')}\n"
        if not result["articles"]:
            text += "No articles returned. This is a failed request if status is failed, rather than a zero-match finding.\n"
        captured = engine.execute("record_presentation", {"results": [{"kind": "newsapi_probe", "id": result["id"]}],
                    "markdown": text, "destination": "codex_chat"}, objective=OBJECTIVE, actor=ACTOR, versions=versions)
        print(json.dumps({"result_id": result["id"], "presentation_id": captured["id"], "markdown": text}, ensure_ascii=False))
    finally:
        os.environ.pop("EVENTREGISTRY_API_KEY", None)
        engine.close()


if __name__ == "__main__":
    main()
