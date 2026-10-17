# Methode: van nieuwsartikelen naar incidentdossiers

**Current direction, 2026-10-15:** the primary unit is now **an event dossier: reporting on the same real-world event**, without requiring an incident or harm. The original Dutch method below remains verbatim as history. Its broader incident container is not the current counting unit. See [the revised scope](#current-scope-event-dossiers--2026-10-15).

Onderstaande methode is op 14 oktober 2026 door de gebruiker aangeleverd en woordelijk vastgelegd. Status: te ontwikkelen; de gegevensvoorbereiding voert de vier onderzoeksstappen nog niet uit.

| Stap                                  | Techniek                     | Werkwijze                                                                                                                                                                                                                          |
| ------------------------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Kandidaten vinden**              | Embeddings + vector search   | Bereken embeddings per tekstpassage en zoek mogelijk bij elkaar horende artikelen. Semantische overeenkomst is een **zoeksignaal**, geen bewijs voor dezelfde gebeurtenis.                                                         |
| **2. Gebeurtenissen beschrijven**     | Entiteits- en eventextractie | Extraheer per gebeurtenis betrokkenen, handeling, locatie en gebeurtenisdatum, met bijbehorende bronpassages. Onderscheid gebeurtenisdatum van publicatiedatum; één artikel kan meerdere gebeurtenissen beschrijven.               |
| **3. Dezelfde gebeurtenis herkennen** | Event coreference classifier | Beoordeel kandidaten op basis van de tekst: **dezelfde gebeurtenis, verschillende gebeurtenissen of onzeker**. Cluster bevestigde overeenkomsten en controleer het gehele cluster op tegenstrijdigheden.                           |
| **4. Dossiers vormen**                | Dossierkoppeling             | Verbind verschillende gebeurtenissen alleen bij onderbouwde samenhang met **hetzelfde onderliggende incident**. Bewaar bijvoorbeeld incident, rechtszaak en uitspraak als afzonderlijke gebeurtenissen binnen één dossiertijdlijn. |

## Uitwerkingsafspraken — aanvullend op de exacte methode

The following older incident-specific agreements remain historical where they conflict with the revised event scope below.

Deze afspraken expliciteren het datacontract en veranderen de vier stappen hierboven niet. Wijzigingen worden als een nieuwe protocolversie met reden geregistreerd; oude versies blijven beschikbaar.

- **Bronartikel → bronpassages → gebeurtenisvermeldingen → gebeurtenissen → incidentdossiers.** Een bronartikel mag meerdere gebeurtenisvermeldingen leveren. Een gebeurtenis kan door meerdere artikelen worden beschreven. Een incidentdossier kan meerdere afzonderlijke gebeurtenissen bevatten.
- **Bronverwijzing per bewering.** Betrokkenen, handeling, locatie en gebeurtenisdatum krijgen afzonderlijke passageverwijzingen, exacte citaten, bronversie en Unicode-tekenposities. Ontbrekende of tegenstrijdige informatie blijft expliciet zichtbaar. Een onbekende gebeurtenisdatum wordt niet ingevuld met de publicatie- of ophaaldatum. Datumbereik, precisie en onzekerheid blijven behouden.
- **Zoekresultaten zijn kandidaten.** Bewaar embeddingmodel en versie, passage-/chunkversie, zoekparameters, filters, scores, zoekresultaten en niet-verwerkte bronnen. Provider `eventUri`, herhaalde tekst en semantische overeenkomst mogen kandidaten opleveren, maar vormen geen automatisch bewijs van gebeurtenisidentiteit of dossierlidmaatschap.
- **Coreferentie kent drie uitkomsten.** Bewaar `same_event`, `different_event` en `uncertain`, met bewijs en review. Leg ook negatieve en onzekere relaties vast. Een positieve keten A–B–C is op zichzelf onvoldoende voor een bevestigd cluster: controleer het gehele cluster op tegenstrijdigheden en laat conflicten open voor beoordeling.
- **Dossierkoppeling is een aparte relatie.** Bewijs voor hetzelfde onderliggende incident is iets anders dan bewijs voor dezelfde gebeurtenis. Een incident, rechtszaak en uitspraak behouden afzonderlijke gebeurtenis-ID's, relaties en tijdlijnposities. Bewaar onzekere koppelingen en merge-/splitgeschiedenis; tel pas beoordeelde dossiers als dossiers.
- **Evaluatie vóór inhoudelijke verwerking.** Reserveer een afzonderlijke, menselijk geannoteerde evaluatieset vóór modelkeuze en tuning. Leg richtlijnen, beoordelaars, meningsverschillen en adjudicatie vast. Evalueer kandidatenbereik, extractie, coreferentie en dossierkoppeling afzonderlijk. Houd verwante artikelen/gebeurtenissen bij elkaar bij de uiteindelijke splitsing om lekkage te beperken; een artikelsplitsing alleen is onvoldoende.
- **Gedeelde auditgrens.** Embeddings, extractie, classificatie en modelmatige dossierkoppeling moeten via een daarvoor uitgebreide gedeelde gateway lopen. Bewaar manifests vóór uitvoering, exacte toegestane inputs/outputs, modelidentiteit, parameters, retries, kosten/usage voor zover waargenomen, validatie en review. De [OpenAI-embeddingadapter](OPENAI_EMBEDDINGS.md) is geïmplementeerd met een offline kostenplan en afzonderlijke toestemming per run. [Lokale vector search](LOCAL_CANDIDATE_SEARCH.md) hergebruikt de opgeslagen embeddings via de gecontroleerde runtime; inhoudelijke modelproviders zijn nog niet geïmplementeerd. Live collectie of betaalde inference vereist toestemming voor de concrete run.

## Current scope: event dossiers — 2026-10-15

The latest correction is **“not incident per se, should be event, reporting on the same thing.”** This supersedes the preceding incident-with-timeline choice. One dossier represents one event across sources and publication times. A launch, policy decision, research announcement or harmful occurrence can each qualify. An organization, theme or technology is not itself an event. A dossier groups reporting about a proposed event; it does not independently verify every source claim.

Represent **article → event mention → event dossier**. One article may describe several events; one event may have many reports. Retrospective reporting, corrections and additional details about the original event can join its dossier. A genuinely distinct later action is a separate event, optionally linked to the first. Publication time alone neither splits nor merges events. Preserve event date/range, uncertainty and conflicting claims separately; do not fill missing event time with publication time.

### Proposed workflow — not an executed research result

The later [excerpt-first mapping design and picture](EVENT_MAPPING_METHOD_V1.md)
adds read-once event extraction, provisional unmatched states, progressive
evidence reading and staged group updates. It is a design proposal; it does not
adopt new memberships or establish a quality target.

1. **Find candidates with saved embeddings.** Compare stored article passage vectors through audited vector search; no new question embedding is needed. The existing implementation returns up to 20 article candidates after passage search and reranking. This is a starting workload setting, not a validated semantic boundary. Provider `eventUri`, repeated reporting and entity/date matches can supply separate candidate signals; none proves identity. Keep no-match and text-unavailable articles explicit.
2. **Describe event mentions with evidence.** For plausible candidates, identify actors, specific action/occurrence, affected object, event date/range and location when available, with source passages. Do not rely solely on a generic AI-related matching paragraph. Missing names or dates are not automatic exclusions. Model extraction would require a separately implemented and authorized gateway workflow; human review can establish an initial reference set.
3. **Decide identity:** `same_event`, `different_event` or `uncertain`. Shared company/topic is insufficient; different publication dates do not establish different events. Missing evidence remains uncertain. No universal cosine cutoff or LLM-estimated query-relevance cutoff determines dossier membership.
4. **Review whole proposed clusters.** Neighbor edges propose groups; arbitrary connected components do not establish events. A roundup article can bridge separate events. Check each proposed addition against the event and contradictory evidence, retain negative/uncertain links and merge/split history, and permit articles to link to multiple event dossiers through distinct mentions.
5. **Count reviewed event dossiers.** Article totals describe reporting volume. Show unresolved mentions, uncertain memberships and unprocessed sources beside event totals. These are events represented and reviewed in the selected corpus, not all real-world events or independently verified incidents.

### First proposed evaluation

Use approximately 100–150 human-grouped articles, covering multi-source same-event reports, long publication gaps, retrospective accounts, multi-event roundups, same-topic/different-event cases and singletons. This is a proposed size, not existing coverage. Include known same-event reports selected independently of the embeddings being tested; evaluating only successfully retrieved neighbors hides misses. Define event granularity before annotation, preserve reviewer disagreements/adjudication and freeze event-linked development/held-out partitions before tuning. Reprints, the same event and connected multi-event reporting must not leak across splits.

Measure candidate recovery of known same-event links, false merges, false splits, unresolved cases and event-count error within the annotated reference frame. A top-k cap limits recovery for large event groups; measure that limit and consider bounded expansion. Reference-set performance does not establish corpus-wide recall. Prefer broad candidate discovery and cautious confirmed merges: a wrong merge hides distinct events, while uncertain links can stay open.

The existing code implements candidate retrieval, not a complete substantive event-identity pipeline. Its confirmed source-to-dossier exclusivity prevents one article joining multiple active dossiers; event-mention records and membership support need implementation. Current exact-neighbor checks measure numerical vector retrieval, not semantic/event recall. No corpus search, event extraction, clustering or model run was executed for this design.

**Implementation update, 2026-10-17:** the separate [saved-text extraction pilot](EVENT_EXTRACTION_PILOT.md)
now implements source-level event-mention packets, an evidence-grounded schema,
provisional mention records and a bounded audited Codex executor without
re-embedding. The earlier paragraph describes the original design checkpoint.
Model execution still needs concrete plan-bound permission. This addition does
not complete event coreference, multi-event dossier membership or human validation.

Primary research supports considering [entity/event context](https://aclanthology.org/P19-1409/) and [document structure and cluster consistency](https://aclanthology.org/2021.acl-long.374/). The workflow above is a project proposal, not a reproduction or validated application of those systems.

## Gegevensvoorbereiding v2

De eerste voorbereidingsrun is een offline pilot van maximaal 20.000 artikelen uit het bestaande archief. De selectie is deterministisch en gestratificeerd naar `collection_cohort`: verdeel de pilotomvang proportioneel met de grootste-restmethode, rangschik per cohort op SHA-256 van een geregistreerde seed en `article.uri`, en leg alle geselecteerde en uitgesloten recordverwijzingen vast. Dit is een verkennende ontwikkelset, geen gevalideerde steekproef voor populatieschattingen of inhoudelijke evaluatie. Artikelen zonder tekst blijven in het selectiekader en krijgen een expliciete ontbrekende-tekststatus.

Bewaar oorspronkelijke geselecteerde JSONL-regels, bundelhash, regelnummer, artikel-ID, cohort, providerrecord, publicatiemetadata en `eventUri` in beschermde opslag buiten Git. Historische ophaaltijden en parameters worden niet uit archief- of voorbereidingstijden afgeleid; zolang ze niet onafhankelijk zijn gekoppeld, blijven ze onbekend met een expliciete reden. Bewaar de voorbereidingstijd apart.

Amendement v2: als de bestaande credentialcontrole een geselecteerd record blokkeert, blijft het artikel als metadata-only plaatsaanduiding in de selectie. Bewaar uitsluitend de eerder gevalideerde artikel-/bundel-/regelverwijzing en hash, met reden `credential_like_content` en reviewstatus. Bewaar geen gematchte waarde, bronpassage, providerrecord of originele regelbytes van dat record in de nieuwe werkopslag. Vervang het artikel niet door een ander artikel. Rapporteer deze quarantaine afzonderlijk van werkelijk ontbrekende tekst en van niet-beoordeelde `eventUri`-metadata. Dit is een opslagbeperking, geen inhoudelijk oordeel; inhoudelijke verwerking blijft voor deze records onvolledig. Het legacy-archief wordt niet gewijzigd.

Bronpassages behouden de bestaande exacte paragraafsegmentatie en stabiele offsets. Voor toekomstige embeddings worden daaruit deterministische tekstchunks gemaakt van maximaal 1.600 Unicode-tekens met 200 tekens overlap, zonder tekstnormalisatie, vertaling of samenvatting. Iedere chunk verwijst naar de bronversie, paragraaf en exacte begin-/eindposities en teksthash. Dit is een eerste chunkmethode om later te evalueren; tekengrenzen zijn geen gegarandeerde zins- of tokengrenzen. Chunks zijn nog geen embeddings, gebeurtenisvermeldingen of dossierbevindingen.

## Verschil met de huidige software

De bestaande runtime bewaart onveranderlijke bronnen, passages, dossiergroeperingen en auditgegevens. De huidige dossiergroepering verbiedt bevestigde toewijzing van één bronartikel aan meerdere dossiers; dat model is onvoldoende voor deze methode. Er moeten afzonderlijke, versiegebonden gebeurtenisvermeldingen, gebeurtenisidentiteiten, coreferentierelaties, clustercontroles en incidentkoppelingen worden toegevoegd. Ook vereist de huidige modelgateway al dossiers als input; de toekomstige extractie- en coreferentietaken moeten op bronnen/passages en gebeurtenisvermeldingen kunnen werken voordat dossiers bestaan. Voorbereide artikelen worden daarom nog niet als bevestigde gebeurtenissen of dossiers geregistreerd.

Deze methode definieert de werkwijze, maar nog geen volledige inhoudelijke afbakening van een AI-incident. Die definitie, inclusie-/exclusieregels, beoordelingscodeboek, prompts, evaluatiecriteria en acceptatiedrempels worden afzonderlijk vastgesteld en versiegebonden vóór inhoudelijke uitvoering.
