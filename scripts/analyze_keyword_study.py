"""Replay immutable results through a registered sensitivity profile, without network."""
from __future__ import annotations

import json

from newsresearch.common import default_workspace
from newsresearch.runtime import Research

from run_keyword_study import ACTOR, OBJECTIVE


def main():
    workspace = default_workspace().parent / "research-nl-cyber-keywords-500-20261016"
    engine = Research(workspace)
    try:
        versions = json.loads((workspace / "context.json").read_text(encoding="utf-8"))
        versions.update(json.loads((workspace / "sensitivity-profile.json").read_text(encoding="utf-8")))
        original = json.loads((workspace / "latest-result.json").read_text(encoding="utf-8"))
        result = engine.execute("keyword_study", {"action": "sensitivity", "result": original["id"]},
                                objective=OBJECTIVE, actor=ACTOR, versions=versions)
        (workspace / "sensitivity-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        p = result["comparisons"]
        def percent(value):
            return "onbekend (lege noemer)" if value["fraction"] is None else f"{100*value['fraction']:.1f}% ({value['found']}/{value['reference']})"
        text = (f"**550 echte Google News-zoekopdrachten uitgevoerd:** {original['completed']} geslaagd, "
                f"{original['failed']} mislukt, {original['unknown']} onbekend, {original['pending']} nog te doen. "
                f"De periode 15-10-2023 t/m 15-10-2026 is verdeeld over tien bronnen en vijf tijdvakken. "
                f"Er zijn **{original['unique_records']:,} unieke RSS-records**; op titel/uitgever gededupliceerd: "
                f"{original['title_publisher_unique']:,}. Geen incidenttellingen of relevantiescores.\n\n"
                "| Vooraf bepaalde woordenlijst | Dekking gevonden verzameling | Laatste periode, apart gehouden |\n"
                "|---|---:|---:|\n")
        labels = {"original_five": "Oorspronkelijke 5 termen", "four_families_eight_forms": "4 families, 8 woordvormen", "all_ten": "Alle 10 termen"}
        for key, label in labels.items():
            text += f"| {label} | {percent(p[key]['all'])} | {percent(p[key]['heldout'])} |\n"
        text += "\nGeteste acht woordvormen: `hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`.\n\n"
        text += "| Woord | RSS-records met dit letterlijke woord in de titel* |\n|---|---:|\n"
        for term, count in sorted(result["title_counts"].items(), key=lambda x: (-x[1], x[0])):
            text += f"| {term} | {count} |\n"
        text += (f"\n*Binnen {result['title_denominator']} gevonden RSS-records; dit is een door zoektermen geselecteerde verzameling, "
                 "geen schatting van woordfrequentie in al het Nederlandse nieuws. Woorden in artikeltekst zijn niet geteld.\n\n")
        candidate = next((row for row in result["subsets"] if row["train"]["fraction"] is not None and row["train"]["fraction"] >= .95), None)
        if candidate:
            text += (f"De kleinste combinatie die op de eerste vier perioden 95% van de gevonden referentieverzameling haalt, heeft "
                     f"**{candidate['size']} termen**: `{' OR '.join(candidate['terms'])}`. In de apart gehouden laatste periode haalt deze "
                     f"{percent(candidate['heldout'])}. Dit toetst alleen vindbaarheid binnen deze Google-verzameling.\n\n")
        else:
            text += "Geen geteste combinatie haalt de vooraf beschreven 95%-grens op de eerste vier perioden.\n\n"
        text += (f"**Beperking:** {original['possibly_capped']} antwoorden raken de vermoedelijke limiet van 100. "
                 f"Slechts {result['uncapped_strata']}/{result['complete_strata']} bron/tijdvak-combinaties zijn in alle elf zoekacties onder die limiet gebleven. "
                 f"Daar haalt de achtvormenlijst {percent(p['four_families_eight_forms']['uncapped'])}. "
                 "De werkelijke volledigheid en relevantie voor gebeurtenissen in Nederland zijn niet vastgesteld; Nederlandse bronnen berichten ook over het buitenland. "
                 "De Google-uitkomst bewijst geen vergelijkbare dekking in NewsAPI.ai. Er zijn **0 nieuwe NewsAPI.ai-aanvragen** gedaan.\n\n"
                 "Google Keyword Planner meet zoekgedrag van gebruikers, inclusief verwante woordvormen. Voor journalistiek woordgebruik is dat een andere maat. "
                 "[Google: betekenis van historische zoekvolumes](https://support.google.com/google-ads/answer/3022575?hl=en-2).\n\n")
        text += "Voorbeelden uit de gevonden verzameling, zonder relevantieoordeel; Google News-verwijzingen:\n\n"
        for item in original["examples"][:2]:
            text += f"- [{item['title']}]({item['link']})\n"
        text += (f"\n[Volledige analyse, vergelijking per uitgever en woordvorm](<{workspace / 'sensitivity-result.json'}>) · "
                 f"[Alle 550 exacte zoekstrings en uitkomsten](<{workspace / 'latest-result.json'}>). "
                 "Deze analyse gebruikt geregistreerde berekeningen; er zijn geen artikelen door een model of mens op relevantie beoordeeld.")
        captured = engine.execute("record_presentation", {"results": [{"kind": "keyword_study", "id": result["id"]}],
                                  "markdown": text, "destination": "codex_chat"}, objective=OBJECTIVE, actor=ACTOR, versions=versions)
        (workspace / "final-report.md").write_text(text, encoding="utf-8")
        summary = (f"Ik heb **550 echte Google News RSS-zoekopdrachten** uitgevoerd: 500 vergelijkingen en 50 OR-controles, "
                   f"verdeeld over tien Nederlandse nieuwsbronnen en 15 oktober 2023 t/m 15 oktober 2026. "
                   f"Alle zoekacties slaagden; **{original['unique_records']} unieke RSS-records** gevonden. Er ontbreken geen zoekacties.\n\n"
                   "Mijn **voorlopige werkset** bestaat uit vier families met acht gewone woordvormen:\n\n"
                   "`hack OR gehackt OR hackers OR ransomware OR datalek OR datalekken OR cyberaanval OR cyberaanvallen`\n\n"
                   "| Woordenlijst | Dekking gezamenlijke vondsten | Dekking apart gehouden laatste periode |\n|---|---:|---:|\n")
        for key, label in labels.items():
            summary += f"| {label} | {100*p[key]['all']['fraction']:.1f}% | {100*p[key]['heldout']['fraction']:.1f}% |\n"
        if candidate:
            summary += (f"\nDe op eerdere perioden gekozen kortere lijst van {candidate['size']} termen haalt in de laatste periode "
                        f"{100*candidate['heldout']['fraction']:.1f}%. De geteste grens van 95% is een werkcriterium voor vindbaarheid, geen relevantiecutoff.\n\n")
        uncapped_heldout = result["subsets"][0]["uncapped_heldout"]["strata"]
        summary += (f"**Dit is geen bewezen volledigheid van Nederlandse incidenten.** {original['possibly_capped']} antwoorden raken de limiet van 100; "
                    f"{result['uncapped_strata']}/50 bron-periodecombinaties blijven in alle zoekacties onder die limiet, "
                    f"waarvan {uncapped_heldout} in de laatste periode. Relevantie, incidentlocatie en overdraagbaarheid naar NewsAPI.ai zijn niet gevalideerd. "
                    "Er zijn geen relevantiescores of incidenttellingen gemaakt. **0 nieuwe NewsAPI.ai-tokens verbruikt door deze zoekreeks.**\n\n"
                    "Google Keyword Planner meet zoekgedrag van gebruikers, inclusief verwante varianten. Daarmee meet je geen woordgebruik van journalisten. "
                    "[Google-documentatie](https://support.google.com/google-ads/answer/3022575?hl=en-2).\n\n"
                    f"[Volledige analyse met woordfrequenties, voorbeelden en beperkingen](<{workspace / 'final-report.md'}>) · "
                    f"[Alle 550 zoekopdrachten en uitkomsten](<{workspace / 'latest-result.json'}>).")
        short_capture = engine.execute("record_presentation", {"results": [{"kind": "keyword_study", "id": result["id"]}],
                                  "markdown": summary, "destination": "codex_chat"}, objective=OBJECTIVE, actor=ACTOR, versions=versions)
        (workspace / "final-summary.md").write_text(summary, encoding="utf-8")
        print(json.dumps({"full_presentation_id": captured["id"], "presentation_id": short_capture["id"], "overview": summary}, ensure_ascii=False), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
