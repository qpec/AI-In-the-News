"""Evidence-based continuation under the original authorization, never a fresh budget."""
from __future__ import annotations

import argparse
import json
import os

from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research

from run_newsapi_pilot import ACTOR, EXPANDED, NL, OBJECTIVE


def planned_requests():
    base = {"action": "getArticles", "resultType": "articles", "endpointVariant": "sdk",
            "dateStart": "2023-10-15", "dateEnd": "2026-10-15", "lang": "nld",
            "keyword": EXPANDED, "keywordOper": "or", "keywordSearchMode": "phrase",
            "keywordLoc": "body,title", "articlesPage": 1, "articlesCount": 100,
            "articlesSortBy": "date", "articlesSortByAsc": True, "includeArticleBody": False}
    planned = [{**base, "dateEnd": "2023-12-31"}, base,
            {**base, "dateStart": "2024-01-01", "dateEnd": "2024-12-31"},
            {**base, "locationUri": NL}, {**base, "conceptUri": NL},
            {**base, "keywordLoc": "title"},
            {**base, "keyword": " OR ".join(EXPANDED), "keywordSearchMode": "exact"},
            {**base, "keyword": EXPANDED + ["cyberaanvallen", "digitale inbraak", "computerinbraak",
                "computervredebreuk", "gegevens gelekt", "gestolen gegevens", "data breach", "databreach",
                "gegevens op straat", "beveiligingslek", "losgeld", "cyberincident", "cyberincidenten"]},
            {"endpointVariant": "usage"},
            {k: v for k, v in {**base, "dateStart": "2026-01-01", "resultType": "uriWgtList",
                "uriWgtListCount": 10000, "uriWgtListPage": 1, "uriWgtListSortBy": "date",
                "uriWgtListSortByAsc": True}.items() if not k.startswith("articles")}]
    frame = planned[9]
    condition = {k: frame[k] for k in ["dateStart", "dateEnd", "lang", "keywordLoc", "keywordSearchMode"]}
    condition["keyword"] = {"$or": EXPANDED}
    controls = {k: value for k, value in frame.items() if k not in
                {"dateStart", "dateEnd", "lang", "keywordLoc", "keywordSearchMode", "keyword", "keywordOper"}}
    planned.append({**controls, "query": json.dumps({"$query": condition}, sort_keys=True)})
    default = {k: value for k, value in condition.items() if k != "keywordSearchMode"}
    planned.append({**controls, "query": json.dumps({"$query": default}, sort_keys=True)})
    planned.append({**frame, "keyword": " OR ".join(EXPANDED), "keywordSearchMode": "exact"})
    planned.append({**frame, "keyword": list(dict.fromkeys(planned[7]["keyword"]))})
    planned.append({**frame, "keyword": "(persoonsgegevens OR klantgegevens OR patiëntgegevens OR medische gegevens) NEAR/15 (gelekt OR gestolen OR openbaar OR onbevoegd)", "keywordSearchMode": "exact"})
    planned.append({"endpointVariant": "service_status"})
    return planned


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--index", type=int)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--append-account", action="store_true")
    parser.add_argument("--append-idframe", action="store_true")
    parser.add_argument("--append-equivalence", action="store_true")
    parser.add_argument("--append-proximity", action="store_true")
    parser.add_argument("--append-status", action="store_true")
    args = parser.parse_args()
    workspace = default_workspace().parent / "research-nl-cyber-20261015"
    engine = Research(workspace, config=Config(offline=not args.execute))
    path = workspace / "pilot-context.json"
    try:
        versions = json.loads(path.read_text(encoding="utf-8"))
        if args.append_status:
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "service_diagnostic": "Official SDK getServiceStatus endpoint: distinguish service availability from query/access problems. No article search; full 20-token reservation absent an explicit receipt; same budget."}
                if kind == "policy":
                    new["requests"] = old["requests"] + [planned_requests()[15]]
                registered = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1", "content": new,
                    "supersedes": versions[kind], "reason": "Register read-only provider service-health diagnostic before dispatch under original cap"}, objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = registered["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
            print("Provider service diagnostic registered; no network call")
            return
        if args.append_proximity:
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "proximity_supplement": planned_requests()[14],
                       "proximity_method": "Supplementary data exposure wording within 15 words. Compare exact URI set union with expanded phrase frame. No automatic exclusion or relevance claim; independent review remains needed."}
                if kind == "policy":
                    new["requests"] = old["requests"] + [planned_requests()[14]]
                registered = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1", "content": new,
                    "supersedes": versions[kind], "reason": "Register documented exact-mode NEAR/15 supplement before dispatch, preserving same 200-token cap"}, objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = registered["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
            print("Proximity supplement registered; no network call")
            return
        if args.append_equivalence:
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "equivalence_diagnostics": planned_requests()[10:14],
                       "comparison_method": "Exact article URI set equality and directional differences against the direct phrase ID frame. Counts are complete only if returned ID count equals provider total. No relevance labels or recall inference.",
                       "search_method_reference": "https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04"}
                if kind == "policy":
                    new["requests"] = old["requests"] + planned_requests()[10:14]
                registered = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1", "content": new,
                    "supersedes": versions[kind], "reason": "Register direct/complex/default/Boolean query equivalence and additional-keyword ID comparisons before dispatch; original 200-token bound retained"}, objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = registered["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
            print("Equivalence and lexical expansion diagnostics registered; no network call")
            return
        if args.append_idframe:
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "identifier_frame_diagnostic": "Official RequestArticlesUriWgtList, 10000 identifiers maximum. 2026 single-calendar-year bound, phrase OR terms. No article text requested. Preserve exact ID response and receipt; same 200-token cap. Counts and ID overlap are retrieval diagnostics, not relevance or incident measurements.",
                       "identifier_reference": "https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py"}
                if kind == "policy":
                    new["requests"] = old["requests"] + [planned_requests()[9]]
                registered = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1", "content": new,
                    "supersedes": versions[kind], "reason": "Register complete identifier-list diagnostic instead of repeated article-text samples; no new budget or automatic retry"}, objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = registered["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
            print("Identifier frame diagnostic registered; no network call")
            return
        if args.append_account:
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                new = {**old, "account_diagnostic": "Official SDK getUsageInfo endpoint; technical quota/access diagnosis, no article retrieval or model call; full reservation until explicit receipt"}
                if kind == "policy":
                    new["requests"] = old["requests"] + [{"endpointVariant": "usage"}]
                registered = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1", "content": new,
                    "supersedes": versions[kind], "reason": "Register official account usage diagnostic to investigate archive access under the same reconciled 200-token cap"}, objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = registered["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
            print("Account diagnostic registered; no network call")
            return
        if args.prepare:
            result = engine.execute("newsapi_overview", objective="Reconcile confirmed receipts while retaining all unknown request charges", actor=ACTOR, versions=versions)
            receipts = result["budget_reconciliation"]
            for kind in ["protocol", "selection", "policy"]:
                old = engine.ledger.get(versions[kind], kind)["content"]
                if kind == "policy":
                    new = {**old, "method": "newsapi-probe-approval-v2",
                           "budget_accounting": "confirmed-costs-plus-unresolved-reservations-v1",
                           "requests": old["requests"] + planned_requests(),
                           "continuation_instruction": "Search online for techniques, search newsapi. Ai docs for strategy. Do some new tests and keep going until you have a sound strategy",
                           "reconciliation_result": result["id"]}
                else:
                    new = {**old, "continuation_requests": planned_requests(), "reconciliation_result": result["id"],
                           "continuation_method": "Use immutable req-tokens receipts only to release proven over-reservations; retain 20 for each unavailable/unknown charge. Same original 200 cap and authorization identity. Compare official SDK route, oldest-first dates, phrase/Boolean and geographic branches. No relevance or recall claim without independent review.",
                           "technical_references": ["https://newsapi.ai/blog/different-ways-of-searching-using-keywords/",
                               "https://github.com/EventRegistry/event-registry-python/wiki/Searching-for-articles",
                               "https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/EventRegistry.py"],
                           "references_consulted_on": "2026-10-15"}
                registered = engine.execute("version", {"kind": kind, "key": "nl-cyber-search-pilot-v1", "content": new,
                    "supersedes": versions[kind], "reason": "User requested continued tests; reconcile confirmed charges, preserving every unknown at its original upper bound and the same 200-token cap"},
                    objective=OBJECTIVE, actor=ACTOR)
                versions[kind] = registered["id"]
            path.write_text(json.dumps(versions), encoding="utf-8")
            text = (f"Budget reconciliation: {len(receipts['entries'])} prior dispatches; confirmed receipts plus unchanged unknown-charge reservations total "
                    f"**{receipts['upper_bound_tokens']:g}/200 tokens**. **{200-receipts['upper_bound_tokens']:g} tokens of conservative headroom** remain under the original cap. "
                    "This releases only documented over-reservations; no unknown charge was reduced. No new live request has run in this step.")
            captured = engine.execute("record_presentation", {"results": [{"kind": "newsapi_overview", "id": result["id"]}], "markdown": text, "destination": "codex_chat"},
                                      objective=OBJECTIVE, actor=ACTOR, versions=result["versions"])
            print(json.dumps({"presentation": captured["id"], "markdown": text}))
            return
        if not args.execute or args.index is None or not 0 <= args.index < len(planned_requests()):
            raise RuntimeError("An explicit approved test index and execution are required")
        p = planned_requests()[args.index]
        result = engine.execute("newsapi_probe", {"execute": True, "parameters": p}, objective=OBJECTIVE, actor=ACTOR, versions=versions)
        if p.get("endpointVariant") in {"usage", "service_status"}:
            endpoint = "/api/v1/usage" if p["endpointVariant"] == "usage" else "/api/v1/getServiceStatus"
            text = (f"Provider diagnostic `{endpoint}`: HTTP {result['http_status']}, {result['status']}. "
                    f"Provider response: `{json.dumps(result['provider_notes'], ensure_ascii=True, sort_keys=True)}`. "
                    f"Headers: `{json.dumps(result['headers'], sort_keys=True)}`. "
                    f"Conservative upper bound including this request's reservation: {result['accounted_upper_bound_after_dispatch']:g}/200. "
                    "No article search, relevance scoring, or model inference occurred in this diagnostic.")
            capture = engine.execute("record_presentation", {"results": [{"kind": "newsapi_probe", "id": result["id"]}], "markdown": text, "destination": "codex_chat"}, objective=OBJECTIVE, actor=ACTOR, versions=versions)
            print(json.dumps({"result": result["id"], "presentation": capture["id"], "markdown": text}, ensure_ascii=True))
            return
        if p.get("resultType") == "uriWgtList":
            search = json.loads(p["query"])["$query"] if "query" in p else p
            raw_terms = search["keyword"]
            terms = raw_terms.get("$or", []) if isinstance(raw_terms, dict) else raw_terms
            expression = " OR ".join(terms) if isinstance(terms, list) else terms
            text = (f"Identifier-frame test {args.index}: `{expression}`; Dutch, {search['dateStart']} through {search['dateEnd']}, "
                    f"mode `{search.get('keywordSearchMode', 'provider default')}`, {'complex' if 'query' in p else 'direct'} query, titles/bodies, SDK route, date ascending, up to 10000 IDs.\n\n"
                    f"Status {result['status']}; HTTP {result['http_status']}; provider total {result['provider_total']}; returned {result['returned']} article identifiers; scored 0. "
                    f"Headers: `{json.dumps(result['headers'], sort_keys=True)}`. Conservative upper bound including full new reservation: {result['accounted_upper_bound_after_dispatch']:g}/200 tokens.\n\n"
                    "This request retrieved IDs rather than article text. Titles, source links and incident assessments are unavailable from this response. "
                    "No relevance cutoff or yes/no labels were applied. Archive non-use would prevent claiming full-year coverage; provider totals are not incident counts.")
            capture = engine.execute("record_presentation", {"results": [{"kind": "newsapi_probe", "id": result["id"]}], "markdown": text, "destination": "codex_chat"}, objective=OBJECTIVE, actor=ACTOR, versions=versions)
            print(json.dumps({"result": result["id"], "presentation": capture["id"], "markdown": text}, ensure_ascii=True))
            return
        keywords = p["keyword"] if isinstance(p["keyword"], str) else " OR ".join(p["keyword"])
        text = (f"Continuation test {args.index + 1}: `{keywords}`; Dutch (`nld`), {p['dateStart']} through {p['dateEnd']}, "
                f"{p['keywordSearchMode']} matching in {p['keywordLoc']}; SDK article route; date ascending; page 1, up to 100. "
                f"Geographic condition: `{p.get('locationUri', p.get('conceptUri', 'none'))}` (field: "
                f"`{'locationUri' if 'locationUri' in p else 'conceptUri' if 'conceptUri' in p else 'none'}`).\n\n"
                f"Status **{result['status']}** (HTTP {result['http_status']}); provider matches **{result['provider_total']}**; returned **{result['returned']}**; scored **0**. "
                f"Provider headers: `{json.dumps(result['headers'], ensure_ascii=True, sort_keys=True)}`. "
                f"Conservative bound including this dispatch's full reservation: **{result['accounted_upper_bound_after_dispatch']:g}/200 tokens**.\n\n")
        if result["provider_notes"]:
            text += f"Provider diagnostics: `{json.dumps(result['provider_notes'], ensure_ascii=True)}`.\n\n"
        dates = sorted({a.get("date", "") for a in result["articles"]})
        if dates:
            text += f"Returned publication-date range: {dates[0]} through {dates[-1]}. First returned examples:\n\n"
            for i, article in enumerate(result["articles"][:3], 1):
                text += f"{i}. [{article.get('title')}]({article.get('url')}) - {article.get('date')}\n"
        else:
            text += "No articles returned; a failed or archive-disabled request does not establish historical absence.\n"
        pending = max((result["provider_total"] or 0) - result["returned"], 0)
        text += (f"\nUncollected provider matches: {pending}; page 1 only. "
                 "Provider matching/order is unvalidated; no relevance cutoff, yes/no labels, model judging, or incident count.")
        captured = engine.execute("record_presentation", {"results": [{"kind": "newsapi_probe", "id": result["id"]}], "markdown": text, "destination": "codex_chat"},
                                  objective=OBJECTIVE, actor=ACTOR, versions=versions)
        print(json.dumps({"result": result["id"], "presentation": captured["id"], "markdown": text}, ensure_ascii=True))
    finally:
        os.environ.pop("EVENTREGISTRY_API_KEY", None)
        engine.close()


if __name__ == "__main__":
    main()
