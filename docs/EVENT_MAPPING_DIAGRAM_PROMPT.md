# Exact infographic generation prompt

Built-in image generation, 2026-10-17. Fictional illustration, no source inputs.
Saved asset: `assets/event-dossier-excerpt-method-v1.png`.

```text
Use case: infographic-diagram.
Create a polished, exceptionally clear explanatory picture for a news research project: how saved embeddings and a cheap LLM can map news articles into dossiers for the SAME SPECIFIC REAL-WORLD EVENT. This is a proposed method, not a claim of tested accuracy.
Asset: wide landscape infographic, high resolution, white/off-white background, dark navy readable sans-serif typography, teal for retrieval, violet for LLM reasoning, amber for uncertainty, green for consistent provisional matches. Flat editorial illustration with article sheets, event cards, vector dots and dossier folders; restrained professional design, generous whitespace. All text must be legible, exact, and not tiny. Do not include pricing, accuracy percentages, brand logos or fake metrics.

Title at top, exact: "FROM ARTICLES TO EVENT DOSSIERS"
Subtitle: "Read once. Retrieve candidates. Verify the event."
Small clearly visible badge: "PROPOSED METHOD · NOT YET VALIDATED"

Main process: six numbered panels in two rows of three. Read panel 1→2→3 across the top, a clear arrow down to panel 4 at bottom right, then 4→5→6 across the bottom right to left. Use clear numbered arrows to make direction unmistakable.
Panel 1 top left:
"1  PREPARE ONCE"
"Title + first / last paragraphs"
"Reuse identical text; retain every source"
Illustrate source articles and highlighted opening/closing text.

Panel 2 top center:
"2  EXTRACT EVENT CARDS"
"Who · action · object · date · place"
"Evidence references for each fact"
"One article can describe several events"
Illustrate one article producing two separate event cards. No filling missing event dates with publication dates.

Panel 3 top right:
"3  FIND CANDIDATES"
"Saved article + group vectors"
"Names, action and dates add clues"
"Similarity proposes; it does not prove"
Illustrate vector-neighbor dots feeding a SHORTLIST of three dossiers.

Panel 4 bottom right:
"4  COMPARE THE EVIDENCE"
"Luna: same / different / uncertain"
"Same topic is not the same event"
Illustrate side-by-side event cards. A visible amber loop from this panel to a small side box, then back, labeled:
"NEED MORE EVIDENCE?"
"Relevant passages → stronger / human review"
Keep this side loop visually distinct from the main process and do not overlap labels.

Panel 5 bottom center:
"5  CHECK THE WHOLE DOSSIER"
"Check facts and conflicting evidence"
"Stage additions before updating vectors"
"No chain-only merges"
Illustrate a gate protecting a dossier from a contradictory card.

Panel 6 bottom left:
"6  SAVE PROVISIONAL RESULTS"
Three compact branches clearly labeled:
"Join existing dossier"
"New / unmatched → reconcile"
"Unresolved"
Illustrate green folder, teal provisional folder, amber waiting tray. Reconciliation means later checking whether a provisional new dossier is actually an existing event; never assert no retrieved candidate proves a new event.

Below the main process, a simple full-width independent-validation strip:
"QUALITY CHECK BEFORE ADOPTION"
"Frozen human-reviewed sample · Precision · Missed links / recall · Group purity · Unresolved coverage"
A thin continuous audit strip beneath it:
"AUDIT THROUGHOUT: source references · exact model inputs / outputs · decisions · versions · merge / split history"

At the bottom, a small easy illustrative example labeled "FICTIONAL EXAMPLE":
Two tiny article sheets labeled "Tool launch: source A" and "Same launch: source B" feed one folder "EVENT A: LAUNCH".
A third sheet "Later lawsuit about the tool" feeds a DIFFERENT folder "EVENT B: LAWSUIT".
Join the two folders with a dotted line labeled "Related events, separate dossiers".
Small footnote: "Current seven-day groups stay unchanged; cross-window links need separate checks."
Constraints: accurate arrows, no accidental joins between the example launch and lawsuit, do not depict all articles compared against all others, no claim of 90% accuracy, no claim the entire archive is already embedded. No actual news source text. Deliver one finished infographic, not mockup devices.
```

