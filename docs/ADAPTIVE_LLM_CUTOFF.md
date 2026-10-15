# Adaptieve cutoff met LLM-beoordelingen

Method ID: `adaptive-llm-cutoff-v1`. Status: **geregistreerd methodeontwerp; de uitvoeringsadapter is nog niet gebouwd**. Dit document en [de registreerbare specificatie](../methods/adaptive-llm-cutoff-v1.json) voegen een methode toe, geen betaalde uitvoering of nieuw resultaat. De bestaande voorlopige cutoff en eerdere onderzoeksresultaten worden niet gewijzigd.

Het LLM beoordeelt de **inclusie van artikelen** volgens één vast criterium. De onderzoeksruntime berekent vervolgens welke cosinusgrens die beoordelingen het beste benadert, met voorkeur voor recall. Het LLM krijgt geen opdracht een getal voor de cutoff te verzinnen. De uitkomst heet een **LLM-gekalibreerde voorlopige cutoff**; overeenstemming met een model is geen menselijke gouden standaard of bevestiging van incidenten.

## Eén inclusie-instructie voor zoeken en beoordelen

Registreer een canoniek inclusieblok als versie van een `codebook`, met de vraag, operationele definitie, inclusies, exclusies, grensgevallen en omgang met ontbrekende of tegenstrijdige informatie. Bewaar de exact gerenderde UTF-8 tekst en hash; voorbeelden mogen geen validatieartikelen onthullen. Een domeinvoorbeeld kan echte gebeurtenissen onderscheiden van alleen algemene risico's, hypothetische scenario's en gecontroleerde demonstraties, maar de concrete grens hoort in het vastgezette criterium, niet in stilzwijgende aannames van de beoordelaar.

Gebruik **exact hetzelfde ongewijzigde inclusieblok** in de queryembedding, het LLM-beoordelingsprompt en de definitie van de uiteindelijke tag. De vaste omhulling voor transport, bronveiligheid en uitvoerschema mag per taak verschillen; de criteria niet. Bewaar in iedere request en tag de `inclusion_spec_version` en `inclusion_text_sha256`, en controleer hun gelijkheid vóór uitvoering.

De huidige queryplanner gebruikt alleen query en vraag; de bestaande artikelbeoordelaar heeft daarnaast een aparte definitie en instructie. Dat is nog geen afgedwongen gedeeld inclusieblok. Deze brug moet dus eerst worden geïmplementeerd. Een inhoudelijk nieuw inclusieblok vereist een **nieuwe queryembedding en volledige lokale herscoring**. De bestaande artikelvectoren mogen expliciet worden hergebruikt als model, dimensies en bronversies overeenkomen. De oude scores van de korte incidentquery mogen niet achteraf als scores voor uitgebreidere criteria worden gepresenteerd.

## Leesbudget

| Profiel | Ontwikkeltrekkingen | Onaangeroerde toetsartikelen | Reserve voor herlezing/retry | Maximum artikelpogingen |
| --- | ---: | ---: | ---: | ---: |
| Standaard | 40 + 3 × 20 = 100 | 80 | 20 | 200 |
| Compact | 20 + 2 × 15 = 50 | 40 | 10 | 100 |

Een ontwikkeltrekking kan een al beoordeeld artikel aanwijzen. Dan wordt het bevroren label expliciet hergebruikt, zonder opnieuw te lezen. Standaard worden dus maximaal 180 **unieke** artikelen gelezen en maximaal 200 bewijsdragende modelpogingen uitgevoerd. Compact zijn dat maximaal 90 unieke artikelen en 100 pogingen. Ongebruikte plaatsen door hergebruik worden niet stilzwijgend aangevuld totdat toch 100 unieke ontwikkelartikelen zijn bereikt: dat zou het vastgelegde trekkingsschema veranderen.

Een tweede oordeel, retry of onbekende uitkomst waarbij artikeltekst aangeboden kan zijn telt opnieuw mee. De reserve is geen toestemming voor overschrijding. Een modeltaak moet het volledige toegestane artikel kunnen ontvangen. Te lange, ontbrekende, geweigerde of onvolledig verwerkte teksten blijven expliciet onverwerkt; geen stilzwijgende afkapping tot alleen titel of best scorende passage. Modelaandacht is niet waarneembaar, ook als het systeem de volledige aangeleverde tekstdekking controleert. Queryembedding, tokenlimieten en geldbudget worden daarnaast afzonderlijk begrensd; het artikelaantal alleen begrenst de kosten niet.

## 1. Frame en toetsset vastzetten

Leg eerst dataset, brontekstversies, inclusieblok, model/prompt/schema, queryembedding, complete scorerun, RNG/seed, budgetprofiel, kandidaatgrenzen en beslisregels vast. Alle artikelen met geldige scores vormen het technische doelframe. Artikelen zonder score blijven afzonderlijk in de oorspronkelijke datasetnoemer staan.

Trek vóór de eerste ontwikkelbeoordeling aselect zonder teruglegging 80 toetsartikelen (compact: 40) uit het geregistreerde toetsframe. De labels blijven gesloten tot de kandidaat-cutoff is vastgezet. Ontwikkel- en toetsartikelen mogen geen bevroren groep van gerelateerde of identieke verslaggeving delen: verwijder alle groepen van toetsartikelen uit het ontwikkelframe. Leg die extra ontwikkeluitsluitingen vast; pas de toetssteekproef niet achteraf aan om beter passende artikelen te krijgen.

Groepering op provider-ID en exacte duplicaten is slechts een beschreven lekkagecontrole, geen bewezen event coreference. Onvolledige groepskennis blijft een beperking. Documenteer eerdere blootstelling aan labels en bronnen. Is alleen een eerder onbeoordeeld deel geschikt voor toetsing, dan moet dat beperkte toetsframe expliciet zijn; rapporteer de prestatie niet als geldend voor een ongemerkt groter frame. De huidige incidentquery is al verkend en krijgt geen achteraf verzonnen preregistratie.

## 2. Breed beginnen, daarna dichter bij de grens

Standaard: trek eerst **40 keer uniform met teruglegging** uit het volledige ontwikkelframe. Bereken daarna een eerste kandidaatgrens. Doe vervolgens drie rondes van twintig trekkingen. Zet vóór iedere ronde het grensgebied en alle trekkingskansen vast op basis van alleen eerdere ontwikkelresultaten.

Het grensgebied bevat achtereenvolgens maximaal **1.000, 500 en 250** artikelen die qua score het dichtst bij de huidige kandidaat-cutoff liggen. Dit zijn scorelijsten, geen duizend door het LLM gelezen artikelen. Gelijke afstanden breken op bronversie-ID. Beide zijden blijven beschikbaar; als de kandidaat verschuift, verschuift het gebied mee. Compact gebruikt 1.000 en 500. De omvang wordt begrensd door het beschikbare ontwikkelframe.

Per adaptieve trekking komt 50% van de kans uit het volledige ontwikkelframe en 50% uit het grensgebied. Met N ontwikkelartikelen en W artikelen in het grensgebied:

```text
q_j(i) = 0,5/N + 0,5 × I(i behoort tot het grensgebied) / W
```

Bij een leeg grensgebied is de trekking volledig uniform. Ieder artikel houdt dus een positieve kans, ook ver onder de cutoff en ook als het al eerder is beoordeeld. Trek met teruglegging; geen ongemerkte verwijdering van reeds getrokken artikelen. Bewaar voor iedere trekking de **marginale mengkans** q, niet alleen de kans binnen het gekozen mengcomponent. Leg N, W, mengverhouding, bronvolgorde, RNG-versie en seed vast. Het voorstel gebruikt `numpy.random.Generator(PCG64(seed))`, met de concrete bibliotheek- en codeversie geregistreerd bij uitvoering.

De blijvende brede helft zoekt inclusies die een uitsluitend lokale zoekactie zou missen. Dit is geen binaire zoekprocedure: een lage score kan inclusief zijn en een hoge score exclusief. We nemen geen perfecte monotone score-labelrelatie aan.

## 3. Beoordelen zonder de gewenste uitkomst te verklappen

Het LLM ziet het inclusieblok en de volledige toegestane artikeltekst, maar **geen cosinescore, huidige cutoff, zoekrang, eerdere labels of gewenste uitkomst**. Ieder artikel krijgt een aparte stateloze taak onder hetzelfde vastgezette model/prompt/schema.

De gestructureerde uitkomst bevat `yes`, `no` of `uncertain`, criterium-ID's, een korte bewijsgerichte toelichting en controleerbare bronpassages met offsets/hashes. Bij afwezigheid van ondersteunende tekst na volledige aangeleverde dekking mag een nee geen verzonnen citaat krijgen; bewaar expliciet de grond voor die afwezigheidsbeoordeling. Onvolledige bron of verwerking is een aparte processingstatus, geen nee. Vraag geen verborgen redeneerstappen op.

Bevries het eerste geldige primaire oordeel per exact gebonden bron/criterium/model/prompt. Herhaalde ontwikkeltrekkingen verwijzen naar datzelfde oordeel. Een tweede oordeel gebruikt een afzonderlijk, vooraf gedefinieerd replicaat en blijft naast het eerste staan; geen selectie van de prettigste respons. Reservegevallen omvatten onzekerheid, een vooraf vastgelegde willekeurige controle en technische retries. Een tweede model is alleen toegestaan als het concrete modelprofiel en budget dat vooraf omvatten. Overeenstemming tussen modellen blijft geen waarheidstoets.

## 4. De cutoff berekenen met de trekkingskansen

Leg vóór de beoordelingen alle kandidaatgrenzen vast op de unieke scores van het geregistreerde scorerun-frame. Gebruik `score >= cutoff`. Ontbreken voldoende duidelijke inclusies of exclusies, dan levert de methode geen betrouwbare kandidaat op. Er wordt geen recall van 100% afgeleid uit nul beoordeelde positieven.

Bereken op de vaste checkpoints na 40, 60, 80 en 100 trekkingen de gewogen TP-, FP- en FN-totalen. Voor een vooraf mogelijke grens t, een vaste referentie-uitkomstfunctie g en m trekkingen:

```text
T_hat(t) = (1/m) × som_j [ g_t(i_j) / q_j(i_j) ]
```

Waarom de mengkans nodig is: conditioneel op de eerdere rondes geldt per trekking `E[g(i)/q(i)] = som_i q(i)g(i)/q(i) = som_i g(i)`. Dit geldt voor een vaste grens en het beschreven frame. Het geldt niet als kansen achteraf worden verzonnen, herhalingen worden weggegooid of onzekere/ontbrekende labels worden weggelaten en opnieuw genormaliseerd. De modelreferentie veronderstelt het vastgezette, scoreblinde beoordelingsproces; modeldrift en oordeelfouten blijven afzonderlijke beperkingen.

Bereken uit deze totalen de **ontwikkel-F2**: `5 TP / (5 TP + 4 FN + FP)`. De ratio zelf is niet exact onbevooroordeeld; het hoogste resultaat kiezen introduceert bovendien selectiebias. Deze ontwikkelcijfers zijn geen onafhankelijke validatie en geen incidentprevalentie. Gebruik geen gewone bootstrap van de adaptieve steekproef als bewijs van onafhankelijke onzekerheidsdekking.

De voorgestelde selectie is: maximaliseer de gewogen ontwikkel-F2 onder een vooraf gekozen recall-doel (voorstel: 0,95). Bij een vooraf vastgelegde praktische gelijkwaardigheid, bijvoorbeeld F2 binnen 0,01 van het maximum, kies de lagere grens. Die tolerantie en minimumaantallen per referentieklasse moeten in het concrete plan staan, niet na het zien van de uitkomst worden gekozen. Rapporteer ook hoeveel artikelen onder nabije grenzen van tag veranderen.

Onzekere en onvolledig beoordeelde referenties blijven in alle trekkingen zichtbaar. Toon pessimistische en optimistische gevoeligheidsgrenzen: in het ongunstige geval tellen zulke referenties boven t als mogelijke FP en onder t als mogelijke FN; gunstig is het omgekeerde. Een eventuele succesregel moet onder de geregistreerde ongunstige behandeling standhouden. Dat is een gevoeligheidsanalyse, geen uitgevonden gouden label.

Rond alle vastgelegde ontwikkeltrekkingen af vóór successelectie; stop niet willekeurig zodra een prettig getal verschijnt. Technisch afbreken of wegens onvoldoende onderscheid stoppen mag, maar levert een onvolledig/verkennend resultaat op. Als geen enkele grens aan de doelen kan voldoen, rapporteer **geen bruikbare enkele cutoff**. Verruim dan niet stilzwijgend het leesbudget of de inclusie-instructie.

## 5. Eén bevroren kandidaat toetsen

Bevries de kandidaat, ontwikkelcurve en labelset vóór het openen van de 80 toetsbeoordelingen. Pas exact dezelfde scoreblinde LLM-instructie toe. Gebruik de toetslabels één keer voor de geregistreerde precisie, recall, F2, verwarringsmatrix, onzekerheid en ontbrekende verwerking. Dit zijn prestaties tegenover de **LLM-referentie**, geen gemeten inhoudelijke juistheid tegenover onafhankelijke mensen.

Leg concrete succescriteria, betrouwbaarheidsniveau en intervalmethode vóór uitvoering vast. Bij een aselect toetsontwerp zijn exacte/conservatieve proportie-intervallen mogelijk onder hun expliciete aannames; hou rekening met het steekproefontwerp, vaste referentiedefinitie en groepsbeperkingen. Een uitvoeringsadapter mag geen ongeregistreerde intervallen produceren. Weinig positieve toetsgevallen geven brede recall-onzekerheid: 100–200 leesbeurten garanderen geen aantoonbare recall van 95%.

Pas de cutoff niet aan na inzage van deze toetslabels om vervolgens dezelfde set nog onafhankelijk te noemen. Mislukken de doelen, zijn de intervallen te breed of is er te veel onzekerheid, dan is de uitkomst `inconclusive` of `failed` met behoud van alle eerdere resultaten. Een nieuwe iteratie heeft een nieuw vastgezet plan en een nieuwe onaangeroerde toetsset nodig. Een eventueel behouden oude cutoff van 0,30 blijft uitsluitend de voorlopige regel van de oude criterium/queryrun; geen bewijs dat de nieuwe instructie daarmee is gekalibreerd.

## 6. Taggen, menselijke controle en audit

Bij een bruikbare kandidaat past de runtime de grens lokaal op **alle geldig gescoorde artikelen** van de exact gebonden run toe. Bewaar originele scores en eerdere tags en voeg nieuwe ja/nee/null-regels toe. Scheid `retrieval_answer` van `llm_reference_label` en van processingstatus; een onzekere modelreferentie mag niet als negatieve trainingswaarheid verdwijnen. Ontbrekende vectors blijven null. Een LLM-gestuurde cutoff heeft altijd `human_validated: false`; hij kan niet via vervalste `reviewer_type: human`-labels door de bestaande menselijke kalibratiepoort gaan.

Plan daarnaast menselijke controle van onzekere/tegenstrijdige beoordelingen en een vooraf vastgezette willekeurige deelset. Bewaar revieweridentiteit, verschillen en adjudicatie. Gerichte menselijke controles alleen leveren geen onbevooroordeelde gouden validatie op. Gevalideerde inhoudelijke classificatie vereist een onafhankelijk en passend menselijk evaluatieontwerp. Dossierbevindingen blijven een apart onderzoeksobject; aantallen ja-tags zijn geen incidentaantallen.

Bewaar in beschermde SQL/artifactopslag:

- inclusieversie en exacte tekst/hash in beide requesttypen; dataset, scorerun, bronversies en selectie-/groepsexclusies;
- workflow-/ronde-/toetsmanifests vóór uitvoering, iedere trekking inclusief hergebruik, q, seed, grensgebied en selectievolgorde;
- iedere poging, exact toegestaan prompt/bewijs/schema/parameters, waarneembare model/request-identiteit, tijden, gebruik, kostenreserveringen, fouten en retries;
- primaire en tweede oordelen met referentietype `model`, bewijsvalidatie, processingdekking en onzekerheid;
- volledige gewogen kandidaatcurve, gevoeligheidsgrenzen, bevroren keuze, ongeopende/geopende toetsstatus en toetsuitkomsten;
- lees-/request-/token-/geldbudget gepland en besteed, inclusief onbekende pogingen;
- cutoffbeleid, per-artikel parentlinks/antwoorden en het exacte getoonde resultatenoverzicht via `record_presentation`.

## Implementatie en toestemming

De uitvoeringsadapter moet nog de gedeelde-instructiecontrole, adaptieve rondeplanning, exacte trekkingskansen, gewogen rekenroute, geblindeerde toets, budgetteller en hun integratietests implementeren. De bestaande `tag_retrieve`/`plan_tags`-route is corpusbreed en mag **niet** als een al werkende 200-artikelenroute worden gepresenteerd. Ook de oude menselijke kalibratiepoort wordt niet versoepeld om modeloordelen als menselijke labels te accepteren.

Registreer vóór een echte run een concreet workflowplan met frame, criteria, modelprofielen, prijsbasis, bronretentie/externe verwerking, ronderegels, maximale 200 bewijsdragende pogingen, afzonderlijke token-/kostengrenzen en expiry. Adaptieve kindmanifests moeten binnen die vooraf goedgekeurde workflow blijven en vóór iedere batch duurzaam bestaan. De gateway moet de gezamenlijke tellers afdwingen, ook bij retries, herstart en onbekende uitkomsten. De bestaande plan-specifieke betaaltoestemming mag niet ongemerkt worden verbreed naar onbekende vervolgplannen. Eerst die handhaving bouwen en testen; daarna pas de concrete run laten autoriseren.

Alleen de methode registreren kan nu al offline:

```powershell
uv run --frozen newsresearch --objective "Register the adaptive LLM cutoff method design without inference" --actor codex:method-design run version --input methods/adaptive-llm-cutoff-v1.json
```

Dit voert geen queryembedding, artikelbeoordeling, steekproeftrekking of wijziging van bestaande tags uit.
