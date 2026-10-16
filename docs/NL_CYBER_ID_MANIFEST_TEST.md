# Authorized ID-manifest comparison

User instruction, 2026-10-16: test the ID-manifest approach with at most583 new
NewsAPI tokens, unchanged keywords, compare by year with the saved collection,
and report missing articles and actual costs. No relevance inference, model call,
body collection, public export or subscription change is implied.

`scripts/test_nl_cyber_id_manifest.py` registers immutable protocol, question,
selection, profile and policy before the `newsapi_collection` action
`id_manifest_test`. Baseline IDs come only from the immutable
`newsapi_retrieval_audit` identity manifest. The exact same eight date partitions,
keyword phrases/OR, title/body, Dutch news and keepAll predicates are required.
Only result representation and its pagination parameters change: `uriWgtList`,
initially1,000 IDs/page, ascending date, with raw `URI:weight` entries preserved
and normalized using the official SDK's first-colon rule. No ID-sort or fixed
provider snapshot is claimed.

Public pricing documents five tokens/searched archive year for article search,
but no manifest-specific/count-sensitive tariff. Initially reserve50 tokens per
1,000-ID search (a conservative full-article-equivalent allowance, not a proven
provider tariff) and five per usage check. Persist reservations before dispatch.
Confirmed receipts release unused reservations; unknown charges retain them.
All versions share authorization `nl-cyber-id-manifest-20261016-583` and a583token
cap; account allowance is separately checked against5,000 using fresh usage and
unreflected costs/reservations. No provider-side token-cap guarantee is claimed.
Stop if a charge exceeds its reservation, unknown dispatch remains, audit storage
fails, or the next reservation does not fit. Never invoke SDK automatic retries.

One retry of an explicitly received invalid response per exact request is
registered in advance; valid pages and unknown dispatches cannot be retried.
Complete enumeration requires all expected pages, stable totals, correct sizes,
unique IDs and cardinality equal to provider total. Drift/overlap is explicit,
and partial processing cannot establish absence. Compare both `manifest - saved`
and `saved - manifest`; the latter stays null until enumeration is complete.
Newly observed IDs are current discrepancies, not automatically proof that an
article existed in the original index and was skipped. This is a same-provider
cross-check, not an independent news-universe census or event count.

Every checkpoint preserves raw responses, timestamps, exact parameters, costs,
original and normalized identifiers, immutable baseline/method IDs and result
sets in protected storage outside Git. Exact reports use `record_presentation`.
The protected difference CSV contains all observed differing IDs and completeness
flags; it does not fabricate titles/source URLs when only IDs are returned.

Primary technical references:

- https://newsapi.ai/plans
- https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/QueryArticles.py
- https://github.com/EventRegistry/event-registry-python/blob/master/eventregistry/EventRegistry.py
