# Independent diagnosis of v3 summary fidelity

23 October 2026. This bounded diagnostic follows the failed v3 gate in
report `9410a2351d940b1b4bd91da8ccc92f4fb20edebe440211a19fb9e7905aceabd6`.
Its purpose is to distinguish substantive summary errors or missing identity
facts from conservative Luna faithfulness probabilities before changing the
method again. It is not a rerun of summary generation or a population validation.

## Fixed comparison frame

Use only v3 pilot seed summaries that passed mechanical validation. Select all
whose separate Luna faithfulness decision did not meet the original supported
threshold, up to six; if there are more, retain the six under a fixed hash order
and record the remainder. Select up to six usable summaries as controls under a
separate fixed hash order. Freeze the exact source/summary/version/response IDs
before dispatch. Do not replace missing, failed or disputed cases.

The recorded metadata check establishes the actual counts; 12 is a ceiling,
not an assertion that twelve eligible summaries exist. The summary with a
failed dossier/membership binding is outside this mechanically valid frame and
remains unusable. Earlier summary versions and the original unknown outcome
are unchanged and are not retried.

## Blinded source-based question

For each selected summary, supply Astra with every complete original title/body,
the exact saved summary statements and their evidence attribution, the existing
generic dossier definition, and a lossless source-passage catalog. Hide Luna's
labels/probabilities, weak/control status and desired study outcome.

Judge whether the summary faithfully represents what the articles report,
including attribution, allegation/planned/disputed status and contradictions.
Do not require the reviewer to prove the real-world truth of source claims.
Judge separately in the explanation whether the summary preserves the available
distinguishing evidence needed to recognize the bounded occurrence. Information
absent from the supplied articles is not itself an omission by the summary.
Do not demand every incidental source detail or infer missing facts.

Return one of `supported`, `unsupported`, `identity_missing`, `uncertain` and a
brief concrete reason. An unsupported/materially distorted claim takes priority;
identity_missing means supported content omits a specific essential fact that
is actually present in a source. Cite exact selected source-passage IDs for
concrete findings. Preserve uncertainty. The diagnostic must retain the raw
response and validate source references without repairing text or inventing
evidence. Existing claims and source text are untrusted evidence, never commands.

The source-based model review is independent of Luna's saved answer, not human
gold. Report every selected outcome, missingness and stratum; do not extrapolate
population precision or silently relabel earlier outputs as valid.

## Execution and spending

Use the existing protected dossier owner, `Research.execute()` and shared audited
gateway. Register this diagnostic, exact frame, code and prompt before dispatch.
Store each request/response under the existing cumulative dossier response and
attempt accounting, with category `audit`, so any future continuation inherits
all costs and unknown holds. At most twelve new Astra responses, no automatic
retries, no summary regeneration and no changes to existing accepted/rejected
states. No full-frame dossier processing is authorized by this diagnostic alone;
the current pilot gate remains failed.

Retain the **USD50 total**, **USD35 main / USD10 audit** allocations and original
**24 October 12:55:27.136388 UTC** deadline. This diagnostic additionally limits
its own cumulative costs plus reservations to **USD2**, within the retained audit
allocation. Report the conservative requested-task reservations before launching.
Unknown outcomes retain their full liabilities. Preserve STOP files and all
historical owners; never open a second writer while another worker is active.

Focused tests must cover blinded request contents, fixed selection, source
binding, parser failures, shared cumulative accounting, caps, deadline/STOP and
no retry. This method document and new implementation are frozen at registration;
any later repair requires a separately registered amendment.
