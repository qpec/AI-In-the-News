"""Register and execute the user-requested 500-query minimum public news diagnostic."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from newsresearch.common import Config, default_workspace
from newsresearch.keyword_study import METHOD, manifest
from newsresearch.runtime import Research

ACTOR = "codex:operator-for-user"
OBJECTIVE = "Compare common Dutch cyber-news keywords using at least 500 actual free searches"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    workspace = default_workspace().parent / "research-nl-cyber-keywords-500-20261016"
    engine = Research(workspace, config=Config(offline=not args.execute))
    def execute(operation, payload, versions=None):
        return engine.execute(operation, payload, objective=OBJECTIVE, actor=ACTOR, versions=versions)
    try:
        context_path = workspace / "context.json"
        if context_path.exists():
            versions = json.loads(context_path.read_text(encoding="utf-8"))
        else:
            requests = manifest()
            content = {
                "protocol": {"method": METHOD, "authorization_basis": "User requested at least 500 searches, 2026-10-16",
                    "frame": "10 literal Dutch terms x 10 purposively selected publishers x 5 equal date strata; plus 50 OR controls",
                    "dates": "2023-10-15 through 2026-10-15 inclusive, UTC publication dates; RSS bounds expanded one day then filtered",
                    "retention": "Public RSS metadata and permitted exact response bytes only; never publisher bodies. Credential-pattern responses retain hash only; flagged items excluded with count, no replacement",
                    "dispatch": "Fixed seed 20261016 interleaving; single writer; 0.9s pacing; 25s timeout; no automatic retries; 403/429/503 stops batch",
                    "analysis": "Distinct RSS GUID/link identity; title+publisher sensitivity count; exact Unicode casefold title tokens. Marginal term contribution against other nine. Exhaustive size1..6 subset maximizes pooled first4period retrieval; period5 held out. Denominator is discovered union INCLUDING OR control in complete strata only",
                    "limitations": "Exploratory retrieval diagnostics, not relevance, precision, incident counts or population frequency. Google RSS undocumented cap100; cap flags unresolved, search matching not exact, language not validated. Dutch publisher does not imply Netherlands incident. Retrospective Google index and selection biases; one heldout period no human gold. No model calls or paid APIs",
                    "sources": ["https://support.google.com/google-ads/answer/3022575?hl=en-2",
                                "https://support.google.com/google-ads/answer/7337243?hl=en-gb"],
                    "method_lookup": "Google official technical docs searched externally before registration; not automatically research-audited. Keyword Planner measures user searches including close variants, not newsroom word frequencies"},
                "question": {"text": "Which small subset of ten common Dutch cyber-news terms retrieves most of the discovered three-year publisher/date-frame pool?"},
                "selection": {"rules": requests},
                "profile": {"mode": "exploratory", "population_estimate": False,
                            "method": "Exact registered deterministic retrieval diagnostics; held-out chronological subset check"},
                "policy": {"method": METHOD, "requests": requests, "max_dispatches": 550,
                           "paid_calls": 0, "model_calls": 0, "approval_basis": "Explicit request for 500 or more searches"},
            }
            versions = {kind: execute("version", {"kind": kind, "key": METHOD, "content": body})["id"]
                        for kind, body in content.items()}
            context_path.write_text(json.dumps(versions), encoding="utf-8")
        sensitivity_path = workspace / "sensitivity-profile.json"
        if not sensitivity_path.exists():
            from newsresearch.keyword_sensitivity import METHOD as SENSITIVITY

            profile = execute("version", {"kind": "retrieval_profile", "key": SENSITIVITY,
                "content": {"method": SENSITIVITY, "mode": "exploratory", "population_estimate": False,
                    "registered_during": "Collection, before final sensitivity calculations; extension motivated by observed RSS caps",
                    "calculations": "Compare original5, common4families8forms, all10; per-publisher and cap-free whole-stratum sensitivity. Exact title-word counts in discovered union. Singular/plural pair overlap. Exhaustive size1..10 best first4period subset, lexicographic ties; freeze and test period5. Smallest train95percent subset is an exploratory operating candidate; heldout95percent is retrieval-only check, never gold recall or relevance validation",
                    "missingness": "Use complete 11-query cells; exclude entire capped cells for cap-free sensitivity; empty denominators remain null",
                    "limitations": "No new searches, semantic inference or incident counts. Broad Google matching and caps; selection bias remains. No population confidence interval or NewsAPI transfer claim"}})
            sensitivity_path.write_text(json.dumps({"retrieval_profile": profile["id"]}), encoding="utf-8")
        result = execute("keyword_study", {"action": "report" if args.report or not args.execute else "run",
                         "execute": args.execute, "limit": args.limit}, versions)
        output = workspace / "latest-result.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = presentation(result, workspace)
        captured = execute("record_presentation", {"results": [{"kind": "keyword_study", "id": result["id"]}],
                           "markdown": text, "destination": "codex_chat"}, versions)
        (workspace / "latest-presentation.md").write_text(text, encoding="utf-8")
        print(json.dumps({"overview": text, "presentation_id": captured["id"], "workspace": str(workspace)}, ensure_ascii=False), flush=True)
    finally:
        engine.close()


def presentation(r: dict, workspace: Path) -> str:
    if r["pending"]:
        text = (f"**{r['completed']}/550 zoekopdrachten geslaagd**; {r['failed']} mislukt, {r['unknown']} onbekend, "
                f"{r['pending']} nog niet uitgevoerd. Er zijn {r['unique_records']} unieke RSS-records binnen 15-10-2023 t/m 15-10-2026; "
                f"{r['possibly_capped']} antwoorden raken de vermoedelijke limiet van 100. "
                f"Buiten datumgrenzen: {r['counts'].get('outside_window', 0)}; ontbrekende datums: {r['counts'].get('missing_dates', 0)}; "
                f"quarantaine: {r['counts'].get('quarantined', 0)}.\n\n"
                "Zoekpatroon: `TERM site:BRON after:START before:EIND`, plus OR-controles; tien termen, tien Nederlandse bronnen en vijf perioden. "
                "Bronvolgorde, geen relevantiescores of cutoff; overlapvergelijking nog onvolledig. Geen incidenttellingen; 0 NewsAPI.ai-aanvragen.\n\n")
        if r["examples"]:
            item = r["examples"][0]
            text += f"Voorbeeld: [{item['title']}]({item['link']}).\n\n"
        return text + f"[Exacte zoekstrings en uitkomsten per zoekactie](<{workspace / 'latest-result.json'}>)."
    text = (f"Google News RSS: **{r['completed']}/{r['planned']} zoekopdrachten geslaagd**, "
            f"{r['failed']} mislukt, {r['unknown']} onbekend en {r['pending']} nog niet uitgevoerd. "
            f"Bereik: tien termen × tien bronnen × vijf perioden (15-10-2023 t/m 15-10-2026), plus 50 OR-controles. "
            f"{r['counts'].get('returned', 0)} teruggegeven vermeldingen; **{r['unique_records']} unieke RSS-records** binnen de datumgrenzen. "
            f"{r['possibly_capped']} antwoorden raken de vermoedelijke limiet van 100; "
            f"{r['counts'].get('missing_dates', 0)} datums ontbreken, {r['counts'].get('outside_window', 0)} vermeldingen vallen buiten de exacte grenzen en "
            f"{r['counts'].get('quarantined', 0)} vermeldingen zijn in quarantaine. Geen relevantiescores, cutoff of incidenttellingen; 0 NewsAPI.ai-aanvragen.\n\n")
    text += "| Term | Geslaagde zoekopdrachten | Unieke records | Alleen via deze term* |\n|---|---:|---:|---:|\n"
    for row in r["terms"]:
        text += f"| {row['term']} | {row['successful_queries']} | {row['unique_records']} | {row['exclusive_vs_other_terms']} |\n"
    text += "\n*Voorlopige overlap binnen de uitgevoerde zoekacties; onvolledige dekking kan dit sterk vertekenen.\n\n"
    if r["examples"]:
        text += "Voorbeelden, in verwerkingsvolgorde, zonder relevantiescore (links zijn Google News-verwijzingen):\n\n"
        for item in r["examples"][:3]:
            title = (item["title"] or "Zonder titel").replace("[", "(").replace("]", ")")
            text += f"- [{title}]({item['link']})\n"
    text += (f"\n[Alle uitgevoerde zoekstrings, resultaten per zoekactie en ontbrekende verwerking](<{workspace / 'latest-result.json'}>). "
             "Dit is vindbaarheid binnen de gekozen Google-index en bronnen, geen gevalideerde volledigheid of frequentie van Nederlandse cyberincidenten.")
    return text


if __name__ == "__main__":
    main()
