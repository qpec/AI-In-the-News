# Adaptieve cutoff met Codex-agentbeoordelingen

Method ID: `adaptive-llm-cutoff-v3`. Status: **uitvoeringsadapter geïmplementeerd voor de bestaande letterlijke query; werkelijk gebruik en softwaretests worden afzonderlijk gerapporteerd**. De gebruiker heeft **Codex-agents als artikelbeoordelaar** gekozen en uitvoering gevraagd. De [v3-specificatie](../methods/adaptive-llm-cutoff-v3.json) wordt vóór de beoordelingen geregistreerd en bewaart het [v2-ontwerp](../methods/adaptive-llm-cutoff-v2.json) als voorganger; ook het [v1-ontwerp](../methods/adaptive-llm-cutoff-v1.json) blijft behouden. Een registratie, implementatie of geslaagde test is geen uitgevoerde kalibratie en levert op zichzelf geen nieuwe cutoff op.

Een Codex-agent beoordeelt de **inclusie van artikelen** volgens één vast criterium. De onderzoeksruntime berekent vervolgens welke cosinusgrens die beoordelingen het beste benadert, met voorkeur voor recall. De agent krijgt geen opdracht een getal voor de cutoff te verzinnen. De uitkomst heet een **LLM-gekalibreerde voorlopige cutoff**, met transport `codex_cli`; overeenstemming met een model is geen menselijke gouden standaard of bevestiging van incidenten. De Responses-API-artikelbeoordelaar is niet de gekozen uitvoeringsroute. De letterlijke variant hergebruikt de bestaande queryembedding; een inhoudelijk gewijzigde query blijft een afzonderlijke stap.

## Gekozen uitvoering: Codex-agent via de gateway

De [Codex-beoordelingsroute](CODEX_JUDGE_TRANSPORT.md) is geïmplementeerd via `Gateway.adaptive_cutoff` en `Gateway.codex_dispatch` binnen één `Research.execute()` met volledige preflight. Eerst worden het bevroren bewijs, de poging en de exacte dispatchinvoer duurzaam opgeslagen. Daarna start per artikel een nieuw tijdelijk Codex CLI-proces in een beschermde werkmap, zonder gespreksgeschiedenis, score, cutoff of andere labels. De ingestelde modelalias wordt in `codex_model` vastgezet. Het proces gebruikt de bestaande ChatGPT-accountauthenticatie; er is geen terugval op de opgeslagen API-sleutel. Maximaal vier providerprocessen werken tegelijk; de coördinator blijft de enige SQLite-schrijver.

Een direct `spawn_agent` met echte artikeltekst vanuit deze chat is geen vervanging voor deze gatewayroute. De CLI krijgt een read-only sandboxkeuze en instructies tegen tools, aanvullende retrieval en delegatie. Een verse context en die instructies bewijzen geen technisch afgedwongen bestandsscheiding. De adapter registreert deze beperking; een plan dat bewezen isolatie vereist mag deze route niet gebruiken. Een onbekende overdrachtsuitkomst blijft verbruikt en blokkeert automatisch opnieuw aanbieden van die bron binnen dezelfde autorisatie, ook met een gewijzigde taakidentiteit.

Bewaar de exacte applicatie-instructies en aangeboden tekst, agenthandle, zichtbare respons, waarneembare tijden en validatie. Interne Codex-instructies, verborgen redenering, feitelijke modelidentiteit, provider-request-ID, tokens en facturatie zijn mogelijk niet beschikbaar en blijven dan null met een reden. Een ingesteld modelprofiel is niet automatisch een waargenomen model-ID. Codex-gebruik wordt niet als gratis of als volledig intern gelogd gepresenteerd. De gateway mag geen harde provider-token- of geldlimiet claimen die deze route niet kan waarnemen of afdwingen.

## Eén inclusie-instructie voor zoeken en beoordelen

Registreer een canoniek inclusieblok als versie van een `codebook` en bewaar de exact gerenderde UTF-8 tekst en hash. Voor een nieuwe inhoudelijke zoekopdracht horen de operationele definitie, inclusies, exclusies, grensgevallen en omgang met ontbrekende informatie in dat blok. Voorbeelden mogen geen validatieartikelen onthullen. Voeg zulke inhoudelijke criteria nooit alleen aan de beoordelaar toe terwijl de queryembedding een kortere instructie gebruikt.

Gebruik **exact hetzelfde ongewijzigde inclusieblok** in de queryembedding, het LLM-beoordelingsprompt en de definitie van de uiteindelijke tag. De vaste omhulling voor transport, bronveiligheid en uitvoerschema mag per taak verschillen; de criteria niet. Bewaar in iedere request en tag de `inclusion_spec_version` en `inclusion_text_sha256`, en controleer hun gelijkheid vóór uitvoering.

De geïmplementeerde v3-variant controleert de exacte oorspronkelijke queryembeddingrequest en hergebruikt uitsluitend deze bytes als canoniek inclusieblok:

```text
Query: This article is about an incident related to AI.
Question: Is this article about an incident related to AI?
```

Dit is een **achteraf geregistreerd letterlijk criterium** voor de al verkende query, zonder aanvullende operationele inclusies of exclusies. Onduidelijkheid over deze korte instructie blijft `uncertain`. Daardoor kan dezelfde bestaande scoreframe zonder nieuwe betaalde embedding worden gekalibreerd; de adapter controleert tekstgelijkheid en hash. Een inhoudelijk nieuw of uitgebreider inclusieblok vereist nog steeds een **nieuwe queryembedding en volledige lokale herscoring**. De bestaande artikelvectoren mogen expliciet worden hergebruikt als model, dimensies en bronversies overeenkomen. De oude scores worden nooit achteraf als scores voor uitgebreidere criteria gepresenteerd.

## Leesbudget

| Profiel | Ontwikkeltrekkingen | Onaangeroerde toetsartikelen | Reserve voor herlezing/retry | Maximum artikelpogingen |
| --- | ---: | ---: | ---: | ---: |
| Standaard | 40 + 3 × 20 = 100 | 80 | 20 | 200 |
| Compact | 20 + 2 × 15 = 50 | 40 | 10 | 100 |

Een ontwikkeltrekking kan een al beoordeeld artikel aanwijzen. Dan wordt het bevroren label expliciet hergebruikt, zonder opnieuw te lezen. Standaard worden dus maximaal 180 **unieke** artikelen aangeboden en maximaal 200 bewijsdragende artikelopdrachten verstuurd. Compact zijn dat maximaal 90 unieke artikelen en 100 pogingen. Bij Codex telt iedere waarneembare bewijsdragende overdracht, retry of herbeoordeling als artikelpoging; interne modelrequests of intern herlezen zijn niet afzonderlijk waarneembaar. Het budget bewijst dus geen maximum aan interne Codex-aanroepen of werkelijke leesbeurten. Ongebruikte plaatsen door hergebruik worden niet stilzwijgend aangevuld totdat toch 100 unieke ontwikkelartikelen zijn bereikt: dat zou het vastgelegde trekkingsschema veranderen.

Een tweede oordeel, retry of onbekende uitkomst waarbij artikeltekst aangeboden kan zijn telt opnieuw mee. De reserve is geen toestemming voor overschrijding of automatische herlezing: een technische fout stopt verdere dispatch en levert een partieel resultaat; herstel gebruikt dezelfde autorisatiesleutel en teller. Een modeltaak moet het volledige toegestane artikel kunnen ontvangen. Te lange, ontbrekende, geweigerde of onvolledig verwerkte teksten blijven expliciet onverwerkt; geen stilzwijgende afkapping tot alleen titel of best scorende passage. Modelaandacht is niet waarneembaar, ook als het systeem de volledige aangeleverde tekstdekking controleert. Een nieuwe queryembedding heeft een eigen budget. Registreer daarnaast welke token- en geldgrenzen het transport werkelijk kan afdwingen; het artikelaantal alleen begrenst de kosten niet.

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

De Codex-agent ziet het inclusieblok en de volledige toegestane artikeltekst, maar **geen cosinescore, huidige cutoff, zoekrang, eerdere labels of gewenste uitkomst**. Ieder artikel krijgt een aparte taak met verse context onder hetzelfde vastgezette modelprofiel/prompt/schema. Modeldrift die de host niet kan uitsluiten blijft een expliciete beperking; rapporteer de ingestelde en waargenomen identiteit afzonderlijk.

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

De v3-selectie maximaliseert de gewogen ontwikkel-F2 onder een pessimistisch punt-recall-doel van **0,95**, met minimaal vijf unieke duidelijke positieve én vijf negatieve modelreferenties. Onder recall-geschikte kandidaten binnen **0,01 F2** van het maximum kiest de runtime de lagere grens. Deze regels staan vóór de labels vast in de methode en het concrete plan. Rapporteer ook hoeveel artikelen onder nabije grenzen van tag veranderen.

Onzekere en onvolledig beoordeelde referenties blijven in alle trekkingen zichtbaar. Toon pessimistische en optimistische gevoeligheidsgrenzen: in het ongunstige geval tellen zulke referenties boven t als mogelijke FP en onder t als mogelijke FN; gunstig is het omgekeerde. Een eventuele succesregel moet onder de geregistreerde ongunstige behandeling standhouden. Dat is een gevoeligheidsanalyse, geen uitgevonden gouden label.

Rond alle vastgelegde ontwikkeltrekkingen af vóór successelectie; stop niet willekeurig zodra een prettig getal verschijnt. Technisch afbreken of wegens onvoldoende onderscheid stoppen mag, maar levert een onvolledig/verkennend resultaat op. Als geen enkele grens aan de doelen kan voldoen, rapporteer **geen bruikbare enkele cutoff**. Verruim dan niet stilzwijgend het leesbudget of de inclusie-instructie.

## 5. Eén bevroren kandidaat toetsen

Bevries de kandidaat, ontwikkelcurve en labelset vóór het openen van de 80 toetsbeoordelingen. Pas exact dezelfde scoreblinde LLM-instructie toe. Gebruik de toetslabels één keer voor de geregistreerde precisie, recall, F2, verwarringsmatrix, onzekerheid en ontbrekende verwerking. Dit zijn prestaties tegenover de **LLM-referentie**, geen gemeten inhoudelijke juistheid tegenover onafhankelijke mensen.

De v3-toetsregels staan vóór uitvoering vast: minimaal vijf duidelijke referenties per klasse, maximaal 0,10 onzekere/ontbrekende referenties, pessimistische punt-recall minimaal **0,95**, en een recallintervalbreedte van maximaal **0,50**. De runtime berekent tweezijdige **95%-Clopper–Pearson-intervallen** voor precisie en recall, onder een vaste referentie en cutoff en een conservatieve binomiale benadering zonder eindigepopulatiecorrectie. Er is geen geregistreerd F2-interval, simultane dekking of correctie voor modelvergissingen. De succesregel vereist **geen recall-ondergrens van 95%** en bewijst die ook niet. Weinig positieve toetsgevallen kunnen de uitkomst onbeslist laten; 100–200 artikelpogingen garanderen geen aantoonbare recall van 95%.

Pas de cutoff niet aan na inzage van deze toetslabels om vervolgens dezelfde set nog onafhankelijk te noemen. Mislukken de doelen, zijn de intervallen te breed of is er te veel onzekerheid, dan is de uitkomst `inconclusive` of `failed` met behoud van alle eerdere resultaten. Een nieuwe iteratie heeft een nieuw vastgezet plan en een nieuwe onaangeroerde toetsset nodig. Een eventueel behouden oude cutoff van 0,30 blijft uitsluitend de voorlopige regel van de oude criterium/queryrun; geen bewijs dat de nieuwe instructie daarmee is gekalibreerd.

## 6. Taggen, menselijke controle en audit

Alleen bij status **`passed_model_reference`** past de runtime de grens lokaal op **alle geldig gescoorde artikelen** van de exact gebonden run toe. Bij `inconclusive`, `failed` of `partial` toont hij de eventuele kandidaat en de ontbrekende toetsing, zonder nieuwe tags toe te passen. Bewaar originele scores en eerdere tags en voeg nieuwe ja/nee/null-regels toe. Scheid `retrieval_answer` van `llm_reference_label` en van processingstatus; een onzekere modelreferentie mag niet als negatieve trainingswaarheid verdwijnen. Ontbrekende vectors blijven null. Een LLM-gestuurde cutoff heeft altijd `human_validated: false`; hij kan niet via vervalste `reviewer_type: human`-labels door de bestaande menselijke kalibratiepoort gaan.

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

De v3-adapter implementeert de gedeelde-instructiecontrole voor de letterlijke query, Codex-gatewayoverdracht en antwoordvalidatie, adaptieve rondeplanning, exacte trekkingskansen, gewogen rekenroute, gesloten toets, autorisatiebrede budgetteller en expliciet versiegebonden labelhergebruik. De bestaande `tag_retrieve`/`plan_tags`-route blijft corpusbreed en mag **niet** als een 200-artikelenroute worden gebruikt. Ook de menselijke kalibratiepoort wordt niet versoepeld om modeloordelen als menselijke labels te accepteren. Softwaretests en werkelijke modeluitvoering worden apart in [VERIFICATION](VERIFICATION.md) vermeld; deze methodetekst zelf meldt geen nieuwe onderzoeksuitkomst.

Registreer vóór een echte run een concreet workflowplan met frame, criteria, Codex-modelprofiel en host/transport, bronretentie/externe verwerking, ronderegels, maximale 200 bewijsdragende artikeloverdrachten, afdwingbare invoergrenzen en expiry. Vermeld apart welke token-/kosteninformatie en uitvoer-/tijdcontroles beschikbaar zijn. Een lokale timeout of te groot antwoord afwijzen begrenst acceptatie, niet noodzakelijk de modelgeneratie. Als een vereiste provider-token-, geld-, uitvoer- of tijdgrens niet afdwingbaar is, blokkeert dat een plan dat die harde garantie vereist; vul onbekend gebruik niet met nul. Adaptieve kindmanifests moeten binnen die workflow blijven en vóór iedere batch duurzaam bestaan. De gateway moet de gezamenlijke pogingtellers afdwingen, ook bij retries, herstart en onbekende uitkomsten. De keuze voor Codex is vastgelegd; daarvoor hoeft niet opnieuw een keuzevraag te worden gesteld. Een afzonderlijke betaalde API-run blijft concreet plan-gebonden en mag niet stilzwijgend de Codex-route vervangen.

De methode afzonderlijk registreren kan offline:

```powershell
uv run --frozen newsresearch --objective "Register the bounded literal-query Codex cutoff method without inference" --actor codex:method-design run version --input methods/adaptive-llm-cutoff-v3.json
```

Dit voert geen queryembedding, artikelbeoordeling, steekproeftrekking of wijziging van bestaande tags uit.

De operatie `adaptive_cutoff` gebruikt de oorspronkelijke scorecontext met `scores`, een stabiele autorisatie-/workflow-`key`, `budget` (`default_200` of `compact_100`), vaste `seed`, `codex_model`, expliciete `reuse_cache` en maximaal vier `workers`. Een concrete `run_approval` bindt de opdracht, autoriserende actor, externe verwerking, Codex-accountgebruik, poginglimiet en timezone-aware vervaltijd. `execute: true` vereist proceslokaal ingeschakelde online uitvoering; zonder die vlag wordt alleen een duurzaam plan met presentatie gemaakt. De volledige uitvoering gebruikt één `Research.execute()` en één volledige preflight. De reserve wordt niet automatisch aangevuld of verbruikt; technische onderbreking bewaart gedeeltelijke resultaten en onbekende blootstellingen.

De launcher schakelt uitsluitend voor de expliciet geautoriseerde uitvoering online modus in; globale instellingen blijven behouden. Invoer, oorspronkelijke versiecontext en uitvoer horen in beschermde opslag:

```powershell
uv run --frozen python scripts/run_codex_cutoff.py --input C:/protected/codex-run.json --versions C:/protected/query-context.json --output C:/protected/codex-result.json
```

Binnen de reeds geautoriseerde opdracht voert de assistent deze methode uit zodra de benodigde implementatie en controles dat toelaten; hij stopt niet bij alleen een ontwerp of registratie. Na iedere afgeronde stap toont hij de feitelijke dekking, kandidaat-cutoff, toetsuitkomst, eventuele toegepaste ja/nee/null-totalen en voorbeelden met bronlinks. `adaptive_cutoff_plan` en `adaptive_cutoff_result` zijn ondersteunde soorten voor exacte `record_presentation`-vastlegging; de opgeslagen presentatie wordt ongewijzigd in de chat getoond.
