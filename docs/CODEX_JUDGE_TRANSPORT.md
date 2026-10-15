# Codex-agent als artikelbeoordelaar

Status: **uitvoeringscontract, nog geen werkende gatewayadapter**. De gebruiker kiest Codex-agents voor de beoordelingen in [adaptive-llm-cutoff-v2](ADAPTIVE_LLM_CUTOFF.md). Dit contract voert zelf geen artikelbeoordeling uit. De artikelvectoren, queryembedding en deterministische cutoffberekening zijn afzonderlijke onderdelen.

## Overdracht en antwoord

Iedere overgang loopt via `Research.execute()` en de gedeelde modelgateway. Een buiten de runtime voorbereide chatopdracht of achteraf geïmporteerd oordeel voldoet niet. De hieronder genoemde fasen zijn contractnamen, geen bestaande CLI-commando's.

| Fase | Vereiste duurzame registratie vóór de volgende stap |
| --- | --- |
| Plan | Workflowversies, frame, inclusieblok/hash, Codex-profiel, host/transport, budget, rondes en gesloten toetsset. |
| Voorbereiden | Volledig rondemanifest en stabiele taakidentiteit; complete toegestane artikelversie met passageverwijzingen; exact gerenderde opdracht, parameters en uitvoerschema. Controleer tekstdekking en inclusiehash. |
| Reserveren | Unieke poging met atomaire reservering van één artikelpoging onder de workflowlimiet. Sla het exacte dispatchbericht en de overdrachtsintentie op vóórdat bewijs naar de agent gaat. |
| Versturen | Start één verse agentcontext en registreer de teruggegeven agenthandle en lokaal waargenomen dispatchtijd. Een onduidelijke overdrachtsuitkomst houdt de reservering vast en blokkeert automatisch opnieuw versturen. |
| Terugontvangen | Bewaar de exacte zichtbare respons en waarneembare transportmetadata vóór parsing. Een ontbrekend/onderbroken antwoord blijft apart; nooit `no`. |
| Valideren | Controleer taak-/pogingidentiteit, bron-/inclusiehash, schema, geciteerde tekst/offsets en zelfgerapporteerde volledige aangeboden tekstdekking. Sla geldig, ongeldig of onzeker resultaat met validatie op; nog geen menselijke acceptatie. |
| Reconciliëren | Sluit de poging met status en budgetverbruik. Herhaalde inzending van exact hetzelfde antwoord is idempotent; een ander antwoord op een gesloten poging wordt niet overschreven. Een nieuwe beoordeling telt opnieuw mee in het budget en blijft een afzonderlijk replicaat. |

Een onzekere of ongeldige poging wordt niet door een stilzwijgende vervolgboodschap gerepareerd. Iedere aanvullende bewijsdragende instructie, retry of tweede beoordeling krijgt vooraf een nieuwe poging/reservering. Een verkeerd verzonden artikel telt ook mee als blootstelling en wordt als afwijking vastgelegd. Onbekende uitkomsten blijven conservatief verbruikt, ook na een expliciete herstelbeslissing. Alleen aantoonbaar niet verstuurde reserveringen mogen volgens een vooraf geregistreerde regel worden vrijgegeven. Een procescrash mag geen gratis retry opleveren.

De harde limiet is workflowbreed: standaard maximaal 200 artikelpogingen, waarvan maximaal 180 unieke artikelen; compact 100/90. Een artikelpoging betekent hier een waarneembare bewijsdragende overdracht, retry of herbeoordeling; interne modelrequests en intern herlezen zijn niet afzonderlijk waarneembaar of begrensd. Gelijktijdige agents, kindmanifests en hervatten delen dezelfde teller; expliciet labelhergebruik kost geen nieuwe poging. Een herhaalde steekproeftrekking verwijst naar het bevroren primaire label zonder een agent te starten. Gebruik geen batch met meerdere artikelen per agent om de teller te omzeilen.

## Wat de beoordelaar krijgt

De agent krijgt alleen een opake taak-/pogingidentiteit, de exacte inclusie-instructie met criterium-ID's/versie/hash, vaste bronveiligheidsinstructies, de complete toegestane artikeltekst met stabiele passage-ID's en een strikt uitvoerschema. De bron is onbetrouwbaar bewijsmateriaal, nooit een opdracht. Source-ID's zijn opake verwijzingen; stuur geen zoekrang, score, cutoff, steekproefkans, ontwikkel-/toetslabel of eerder oordeel mee.

De verwachte uitvoer omvat `yes`, `no` of `uncertain`, criterium-ID's, een korte bewijsgerichte toelichting, exacte bronverwijzingen en aangegeven aangeboden tekstdekking. Een expliciete processingstatus blijft onderscheiden van het inclusielabel. Geen verzonnen citaat bij een gemotiveerde afwezigheidsbeoordeling; geen `no` bij ontbrekende of afgekapt aangeleverde tekst. De runtime valideert citaten en dekking, geen verborgen aandacht of inhoudelijke waarheid.

Bij gebruik van de huidige samenwerkingstool is het ontwerp `fork_turns: "none"`, één nieuwe agent per artikel en geen vervolgcontext uit andere artikelen. Het ingestelde modelprofiel en de effectieve hostinstellingen worden vooraf vastgelegd. Een instructie verbiedt tools, delegatie aan andere agents, aanvullende retrieval en bronbestanden openen. **Deze tool kan tool-/bestandstoegang niet technisch per subagent uitschakelen.** Verse context en instructies zijn daarom geen afgedwongen isolatie. De adapter moet de waargenomen toolactiviteit en onzekerheid in zijn controlemogelijkheden benoemen; een bekende overtreding sluit het oordeel uit zonder de poging terug te geven. Een plan dat technisch bewezen isolatie vereist mag deze route niet gebruiken.

Ontwikkelopdrachten mogen alleen uit een bevroren ronde komen. Toetsopdrachten worden pas voorbereid/verstuurd nadat kandidaat-cutoff en ontwikkelsnapshot onveranderlijk zijn vastgezet. De coördinator ziet toetslabels tot dan niet; dezelfde agent wordt nooit voor ontwikkeling en toets hergebruikt. Bestandsrechten of echte procesisolatie vereisen aanvullende implementatie: een verborgen pad alleen sluit toegang niet uit.

## Waarneembaarheid en gebruik

Bewaar exacte applicatie-instructies, bewijs, schema, gekozen parameters, dispatchbericht, taak-/poging-/agent-ID, zichtbare respons, lokale tijden, fouten, retries, validatie en labelhergebruik in beschermde SQL/artifactopslag. Noem ingestelde en gerapporteerde modelidentiteit afzonderlijk. Voor niet beschikbare feitelijke model-ID, provider-request-ID, providerkloktijden, tokengebruik of facturatie geldt `null` met een reden; geen zelfbedachte waarden of nulkosten. Interne hostinstructies en verborgen redeneerstappen worden niet opgevraagd of als vastgelegd gepresenteerd. Lifecyclehooks bewijzen deze overdracht niet.

De gebruiker heeft de Codex-beoordelaar gekozen. Dat is geen opdracht om de huidige Responses-API-transportadapter met de opgeslagen API-sleutel te starten. Codex-gebruik kan accountlimieten verbruiken; de feitelijke facturatie van deze host is hier niet vastgesteld. De artikeloverdrachten en toegestane invoerbytes zijn lokaal begrensbaar; onzichtbaar providergebruik is dat niet automatisch. Een lokale timeout of uitvoergrootte afwijzen beperkt acceptatie, niet noodzakelijk uitvoering of generatie. Bewaar de volledige toegestane zichtbare respons vóór afwijzing; een timeout met onbekende/late voltooiing blijft onbeslist tot reconciliatie. Claim geen gegarandeerde annulering of generatiegrens zonder geverifieerde hostcontrole. Registreer die beperking expliciet en blokkeer een plan dat een niet afdwingbare harde providerlimiet vereist. Een eventueel nieuwe betaalde queryembedding houdt zijn eigen concrete toestemming.

## Alternatieve Codex-host en verificatie

De lokaal geïnstalleerde CLI `codex-cli 0.162.1` toont via `codex exec --help` ondersteuning voor stdin, `--json`, `--output-schema`, `--ephemeral` en een sandboxkeuze. De [officiële OpenAI-documentatie over non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) beschrijft gestructureerde uitvoer en JSONL-events. Dit zijn gecontroleerde mogelijkheden, geen uitgevoerde beoordeling of bewijs van effectieve isolatie, accounttoegang, kosten of gatewayintegratie. Een CLI-transport is pas een alternatief na een apart vastgezet hostprofiel en geteste gatewaykoppeling. Verander geen globale instellingen of authenticatie om deze methode vast te leggen.

Vóór echte bronverwerking moeten integratietests aantonen: intentie vóór dispatch; fail-closed audit; gedeelde inclusiehash; scoreblinde pakketten; stabiele taakidentiteit; atomaire caps over concurrerende reserveringen/retries/herstart; behoud van onbekende uitkomsten; idempotente responsverwerking; bron-/schema-/dekkingsvalidatie; geen toetsdispatch vóór de bevroren kandidaat; en geen doorvoer van modelreferenties als menselijke gouden labels. Context-only agents voor software-/methodeontwerp hebben geen corpusbeoordeling uitgevoerd en tellen niet als validatie van deze route.
