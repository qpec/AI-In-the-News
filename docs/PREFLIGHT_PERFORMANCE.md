# Complete preflight performance

The optimized verifier still checks the whole journal, projections, source/passage coverage, FTS index, required artifacts and actual artifact contents/permissions on every call. It does not reuse a previous successful verification or trust file size/timestamps. Session provenance, durable input/intent/result writes, unknown model outcomes and fail-closed behavior are unchanged. See [auditability](AUDITABILITY.md).

The implementation reduces repeated work:

- Hash record projection bytes against the content-addressed reference, then fully hash/check the actual artifact in the final sweep. This supplies the same byte-identity assurance without a second file read and ACL query per record.
- Reuse a parsed, verified raw source entry only after canonical byte equality with its immutable source projection and source hash. Ordered indexed source/passage cursors validate each paragraph against that source body; full source JSON no longer appears in every joined passage row. The per-source expected-passage set also detects missing or misbound paragraphs, and orphan passage rows are rejected.
- Reuse Windows API function bindings, while reading every ACL and making every permission decision afresh. POSIX permission checks reuse one stat result within that check.
- Inventory the artifact directory once. Every artifact, including unreferenced objects and raw imports already read earlier, still receives the final full streaming hash and permission check.

## Reproduce with synthetic data only

`scripts/benchmark_preflight.py` creates its deterministic fictional fixture through a registered `Research.execute()` benchmark handler. It never opens the default research store and makes zero model/network calls. Databases, manifests, timing reports, profiles and the original verifier snapshot belong in protected engineering storage outside Git. The script rejects an existing fixture overwrite, checks a frozen database hash before/after workers and verifies the same journal event count/head each time.

```powershell
uv run --frozen python scripts/benchmark_preflight.py create --root C:/protected/engineering/new-preflight-fixture --sources 2000 --paragraphs 12 --paragraph-chars 640 --records 4000
uv run --frozen python scripts/benchmark_preflight.py compare --root C:/protected/engineering/new-preflight-fixture --snapshot C:/protected/engineering/storage-baseline.py --repeats 3 --order baseline,current,current,baseline --no-profile
```

Choose a fresh protected root and the explicitly saved original implementation snapshot. Omitting `--no-profile` adds a separate cProfile verification for call counts; profiled runs are excluded from elapsed-time samples. Worker processes run sequentially in the specified order, with one first call and subsequent warm repeats each. OS caches are uncontrolled: a fresh process is not a cold-disk measurement. This measures `Ledger.verify()`, excluding fixture construction, process startup and ledger construction; it does not measure an entire research command or scientific accuracy.

## Observed results

The engineering workload contains 2,000 synthetic sources, 24,000 passages, 4,004 immutable records, 4,010 journal events and 4,008 artifacts. After the full test suite finished, a final unprofiled ABBA comparison ran four fresh workers (baseline, current, current, baseline), with three complete verifications each. Both implementations returned the same journal count/head, and the database hash remained unchanged.

| Elapsed `Ledger.verify()` time | Original | Optimized | Speedup |
| --- | ---: | ---: | ---: |
| Median of each worker's first call | 6.117 s | 2.906 s | 2.105× |
| Median of four subsequent warm calls per implementation | 5.829 s | 2.772 s | 2.103× |

Warm elapsed time fell by **52.44%**. Across all six calls per implementation, baseline times ranged from 5.754 to 6.329 seconds and optimized times from 2.759 to 3.074 seconds. The first call in a worker is not a cold-disk test. No confidence interval or production extrapolation is claimed. The original implementation was saved before editing; optimization checkpoint `599e067` contains the measured code. Exact implementation hashes and the protected report's timing observations are summarized in [verification](VERIFICATION.md).

A separate full-verification profile observed these call counts:

| Work per complete verification | Original | Optimized |
| --- | ---: | ---: |
| Artifact `read_bytes` calls | 4,005 | 1 |
| Final artifact streaming verification calls | 4,008 | 4,008 |
| Permission/Windows ACL checks | 8,018 | 4,014 |
| JSON parsing calls | 32,011 | 4,011 |
| SQLite execute calls | 12 | 12 |

The SQL improvement reduces transferred/parsed source payloads rather than the statement count. Full artifact I/O remains a lower bound, and time continues to grow with accumulated data and audit history. Neither these synthetic timings nor an uncontrolled first-call timing establishes a speedup for the production archive. No production preflight or new research inference was run for this benchmark.
