# Shared research infrastructure

Study-specific choices and evidence belong under [the investigations](../../README.md).
Use one implementation of the audited runtime, gateways, source storage and vector
primitives; do not fork these per investigation.

| Component | Existing entry point | Responsibility |
| --- | --- | --- |
| Research contract | [Protocol](../../../docs/RESEARCH_PROTOCOL.md), [auditability](../../../docs/AUDITABILITY.md) | Register methods before execution; protected storage; immutable attempts and results |
| Runtime | [runtime.py](../../../src/newsresearch/runtime.py), [CLI](../../../src/newsresearch/cli.py) | All source inspection, measurement and model research through `Research.execute()` / `newsresearch` |
| Embeddings | [OpenAI embedding method](evidence/docs/OPENAI_EMBEDDINGS.md) | Versioned embedding profile, request/usage records and authorization |
| Vector indexes | [Full-corpus index](evidence/docs/FULL_CORPUS_VECTOR_STORE.md), [retrieval](evidence/docs/EVENT_RAG_RETRIEVAL.md) | Candidate retrieval with source/passage lineage; no implicit event identity |
| Candidate methods | [Local candidate search](evidence/docs/LOCAL_CANDIDATE_SEARCH.md), [vector mapping](evidence/docs/FAST_GROUP_VECTOR_MAPPING.md) | Complementary candidate discovery and numerical checks |
| Prototype assignment | [luna_dossier_assignment.py](../../../src/newsresearch/luna_dossier_assignment.py) | Earlier full-article prototype; not the complete summary workflow |
| Proportionate software checks | [Testing policy](../../../docs/TESTING.md) | Distinguish synthetic behavior checks from research validity |
| Conversation record | [Journal](../../../workbench/README.md) | Private visible-transcript capture and daily methodology reporting |

Each investigation needs its own frozen source manifest, method/version bindings,
protected owner, budget ledger, attempted-work identities, outputs and report.
Never reuse another study's labels solely because an article occurs in both.
An article hash can support transparent source/vector reuse; it cannot make
different research questions interchangeable.

Legacy data archives are historical evidence, not the live protected workspace.
Keep raw article bodies, per-article judgments, credentials and transcripts outside
Git. Historical controller STOP files, costs and unknown holds remain intact.
Documentation snapshots are navigation/provenance aids, not launch instructions.
