# Screening boundary cases

23 October 2026. Authored specification review of invented examples. The outcomes
below express the intended rules; no model was asked to classify these examples
and they are not accuracy evidence. The exact executable question text is in
[the screening contract](runtime/screening_contract.py).

| Invented article focus | Cybercrime | Event scope | Netherlands nexus | Intended route |
| --- | --- | --- | --- | --- |
| One authorized penetration test at an explicitly Netherlands hospital; no misuse | no | single_event | direct | exclude |
| A clearly accidental exposure of files at an explicitly Netherlands school | no | single_event | direct | exclude |
| One Netherlands firm's data leak; article cannot establish accidental versus malicious cause | uncertain | single_event | direct | review |
| An identified ransomware attempt against a Netherlands hospital, blocked before damage | yes | single_event | direct | keep |
| Dutch-language reporting on one attack explicitly confined to a Canadian victim and systems | yes | single_event | none | exclude |
| Attack explicitly confined to a firm's Brazilian subsidiary; Dutch headquarters is the only Dutch link | yes | single_event | other_only | exclude |
| A specific ransomware episode, with no established victim location or geography | yes | single_event | uncertain | review |
| Two independent Netherlands attacks receive equal focal coverage | yes | multiple_events | direct | exclude |
| A new Netherlands arrest is the focal action; a foreign attack is background | no | single_event | direct | exclude |
| Reconstruction centered on one Netherlands attack, with a later arrest mentioned as background | yes | single_event | direct | keep |
| A correction updates affected records for one identified Netherlands intrusion, with no new focal action | yes | single_event | direct | keep |
| A broad cyber-risk advice article with examples and no focal occurrence or geographic claim | no | no_event | uncertain | exclude |
| Reports of related attacks do not settle whether they form one continuing episode or separate focal occurrences | yes | uncertain | direct when explicitly supported | review |
| One reported digital extortion episode against an explicitly Netherlands victim, allegations attributed | yes | single_event | direct | keep |

These examples check intended distinctions: actual malicious attempts can qualify
without successful harm; Dutch-language reporting is insufficient; procedural
events remain distinct from attacks; unknown cause or scope is not forced into
a positive label. Background references and changed counts do not automatically
create multiple focal events.

The Netherlands question is independent: an arrest in the Netherlands may be a
directly located event while failing the cybercrime-occurrence question. An
explicitly negative criterion determines exclusion even if another criterion
is uncertain; all individual labels remain visible. Here `keep` means the
provisional `candidate_keep` described in [SCREENING.md](SCREENING.md).

Actual model behavior, geography accuracy, exclusion losses and the reliability
of the clear-case choice remain to be evaluated against source-based references.
