# Auditability and enforcement

## Enforced boundary

Every supported research command enters `Research.execute()`, whether launched by Codex, a terminal, a script or the Python API. The old source verifier also enters this runtime. There is no trusted `--no-audit` research mode. Hooks add lifecycle observations; disabling or omitting Codex does not disable the research journal.

The enforcement sequence is:

1. Validate objective, actor and credentials policy; verify workspace permissions, SQLite integrity, immutable protections, hash chain, artifacts, sources, stable passages and projections. Validate referenced versions and dataset/dossier consistency.
2. Persist session identity and intent: Git HEAD, hashes of working code/docs/config/skills/lockfile, Python/platform/SQLite/library identity, resolved research configuration, exact objective/actor/version bindings and preflight journal head.
3. Save the permitted operation input and durable intent before executing its handler. Method registration precedes dependent processing.
4. For model batches, persist the complete work-item manifest before the first call. Persist each exact request and attempt intent before invoking the provider. Persist permitted response bytes/structure, parsed result and validation before completing the attempt.
5. Commit review and acceptance only after a durable successful attempt, valid evidence and complete coverage. Unique claim/revision constraints and explicit corrections prevent duplicate acceptance.
6. Persist operation result and successful session end. Failures record their observable type when durable storage still works. A logging failure raises and stops the operation; it cannot be "handled" by accepting an unlogged output.

An attempt intent without completion remains an unknown outcome and blocks automatic resume for that task until an explicit resolution record. A crash after a valid result but before the outer operation completion can leave a usable durable result; recovery relies on manifest/task identities and persisted records, not on assuming the whole command failed or succeeded. Source imports and immutable record projections commit with their journal events in SQLite transactions. External artifact writes precede referencing commits, so an interrupted write may leave an unreferenced artifact; no automatic history deletion occurs.

There is one workspace writer at a time, enforced with an OS file lock. This foundation is a local, single-operator environment, not a concurrent multi-user service.

## Stored evidence and model observability

| Information | How it is preserved |
| --- | --- |
| Original sources | Permitted original bytes for stored-response imports; content hash, normalized immutable source, provider fields, actual retrieval metadata |
| Stable evidence | Source-version hash, paragraph ID/hash, Unicode character offsets, exact quote and source offsets |
| Research methods | Immutable question/protocol/selection/dossier-definition/codebook/prompt/profile/policy/evaluation records, amendments and branch names |
| Request | Exact application-controlled instructions, boundary instructions, full supplied evidence, task type, parameters, schema, provider/model identity and input versions |
| Attempt | Stable task key, attempt UUID/number, prior manifest, local start/end times, observable errors/retries and status |
| Response | Permitted provider response object/raw payload, returned provider/model/request ID/usage when available; parsed result and validation |
| Interpretation/review | Model interpretation separate from source claims; exact citations, review decision/rationale/identity or policy, accepted immutable revision |
| Analysis | Frozen SQL/parameters/rows, versions, frame/included IDs, denominator, exclusions, missingness, uncertainty and calculation digest |
| Visualization | PNG artifact and immutable link to its table/digest/calculation |
| Codex hooks | Allowlisted event/session/turn/tool-use/tool-name/model metadata, separate protected lifecycle journal |

Unavailable request IDs, usage or model metadata remain null. Local timestamps are observations, not provider clock times. Error messages are not stored verbatim because provider exception text can expose secrets; types and safe validation reason codes are retained. Hidden reasoning, provider internals and a model's actual attention are not observable and are never fabricated. Original payload fidelity is conditional on retention permission; prohibited payloads must not be sent through an adapter that cannot meet the declared policy.

Credential fields and recognizable secret formats are rejected, rather than silently redacting and misrepresenting a request as exact. No environment dump, auth files, transcripts or provider credentials are logged. Pattern detection cannot recognize every possible secret: keep credentials outside research payloads. No credential-bearing live adapter is shipped.

## Storage and local tamper detection

Working data live outside Git. New Windows roots remove inherited broad grants and use the current user's SID plus SYSTEM; local Administrators/owner rights can remain. Preflight rejects broad ACLs and links/junctions. POSIX roots require owner-only permissions. Artifact names are SHA-256 of their bytes. Files are flushed and fsynced; SQLite uses WAL, `synchronous=FULL`, foreign keys and append-only UPDATE/DELETE triggers for evidence/audit tables. Schema changes are not automatically repaired.

The journal is the append-only `events` table in `research.sqlite3`, linked by SHA-256 over each canonical event and its previous hash. Immutable projections reference their creating event and content-addressed artifact. Preflight verifies journal continuity, required artifacts, source/paragraph integrity and index coverage; SQL cannot ordinarily update or delete historical records. The FTS index is derived and checked against evidence.

These measures detect accidental corruption and many partial modifications. **They do not establish adversarial tamper-proof storage.** An administrator or owner who controls code, database and artifacts can remove triggers, rewrite an entire chain, falsify identities or restore a consistent earlier backup. No external checkpoint, trusted clock, signature service, WORM store, remote attestation or rollback detector is installed. Local ACLs do not encrypt data or protect it from the same logged-in user, malware, administrators, backups or synchronization software. Filesystem/hardware power-loss guarantees and Windows directory metadata durability are platform-dependent. For stronger assurance, add an independently controlled append-only checkpoint/backup service; do not present the current hash chain as proof against its owner.

## Codex project integration

`.codex/config.toml` uses supported project-local `features.hooks`, `project_doc_max_bytes` and inline command hooks for SessionStart, PreToolUse, PostToolUse and Stop. `.agents/skills/` supplies reusable research operations, review and measurement workflows. `AGENTS.md` contains mandatory rules and references this document and the research protocol.

The hooks invoke `uv run --offline --frozen python -m newsresearch.hooks`. Run `uv sync --frozen` first. `uv` locates the project from a repository subdirectory. Hook payloads are reduced to a small metadata allowlist before entering the runtime. The hook journal defaults to a sibling `codex-hooks` protected directory so a long research process cannot block lifecycle logging on the research workspace lock. Tests can override it with process-local `NEWSRESEARCH_HOOK_WORKSPACE`.

Project configuration requires a trusted project. Local command hooks also require Codex's explicit hash-based review in `/hooks`; project trust alone does not approve them. This implementation does not write global settings or approve its own hooks. On an observed audit failure the PreToolUse handler returns a supported explicit denial. A callback that never starts, times out, emits invalid output or is unsupported by the current host can fail open, so the runtime remains mandatory. SessionEnd is not configured because its short timeout is unsuitable for durable full preflight. Existing sessions may require a new project session/reload to discover configuration and skills.

Compatibility is verified against the installed CLI, not inferred from documentation alone; see [VERIFICATION](VERIFICATION.md) for the exact version and observed discovery/trust state. No model turn is needed to inspect configuration, hooks and skills. The same hooks may not be available in a cloud-orchestrated host even when tools execute locally.

Official references: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [advanced configuration](https://developers.openai.com/codex/config-advanced/), [configuration reference](https://developers.openai.com/codex/config-reference/), [skills](https://developers.openai.com/codex/skills).

## Coverage limitations

- The boundary covers the shipped CLI/API and providers routed through its gateway. A local user can run arbitrary Python, SQL, shell tools, network clients or direct provider SDKs outside it. Neither Python encapsulation nor Codex instructions are an OS sandbox. Such activity is outside the audit; it must not be incorporated as accepted research without recorded provenance.
- Codex's own conversational inference, system/developer instructions, hidden reasoning, hosted web/image tools, arbitrary external browsing and human work are not gateway-observed. Do not claim that all Codex token usage or thought is captured. Research judgements must be executed through an approved gateway transport; presently only the offline mock is implemented.
- Hooks omit tool inputs/outputs, prompts, transcript content and environment variables by design. Hosted tools can bypass local hooks; `write_stdin` continuations do not receive a new PreToolUse check; some specialized paths opt out. This is lifecycle coverage, not a transcript or provider audit.
- Failures before argument parsing, workspace availability, preflight or a successful first durable write cannot be recorded in that failed workspace. The CLI stops and reports an error. A missing session-end record indicates interruption, not proof that no work occurred.
- Inspect/search logs show passages returned, not what a person read. Model inspection is self-declared. Quote matching does not validate truth, entailment, bias, dossier quality or scientific usefulness.
- Export allowlists and minimum cells reduce accidental leakage but do not implement differential privacy, repeated-query controls, all disclosure-risk checks or publication-rights review. CLI stdout is private when it contains evidence; shell redirection and external copying are outside export enforcement.
- The older private Git data archive remains preserved. It predates the outside-Git policy and has not been purged from history. Future restricted working data use the protected store.

## Unfinished integrations

Live NewsAPI.ai/Event Registry pagination, rate limits, collection authorization and credentials; real model transports and payload-retention negotiation; semantic retrieval and useful learned grouping; authenticated multi-user review; independent human gold labels and scientific evaluation; sampling-weighted population estimators; secure off-device backups/checkpoints and encryption management; general-purpose statistical/visualization plugins; and publication-grade privacy controls remain unfinished. `collect` and live model providers fail closed. The offline ingestion, audit, grouping proposals, retrieval, mock processing, review, dossier counts, charting, replay and safe aggregate projection are working implementations.
