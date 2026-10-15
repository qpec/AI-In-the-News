# Local results reader

Browse an existing, completed RAG result without rerunning retrieval or inference:

```powershell
uv run --frozen python scripts/serve_rag_results.py --result C:/protected/run/result.json
```

Open the printed localhost URL (normally `http://127.0.0.1:8787/`). Keep the server running while reading; Ctrl+C stops it. Use `--port` to choose another local port. The command can be rerun with the same saved result after a restart.

The reading room opens on supported model examples. Select **All** to browse every saved answer, or filter insufficient and uncertain answers. Search titles, organizations, decisions and answer text within the loaded result. Each article shows its original retrieval rank and similarity, model answer, extracted details, expandable source quotations, original publisher link and version identifiers. Similarity is not a probability, and this RAG workflow applies no binary relevance cutoff or new tags. Model answers remain provisional and article totals are not incident totals.

**Save** and **Mark read** remember reading progress in this browser, keyed to the result set. Saved and unread filters help continue later. J/K navigate, S saves, R marks read, and / focuses search when focus is outside a form control. These are personal browsing markers, not accepted findings or audited research reviews; they are not written to SQL. Formal selections, reviews, exports and new research must still use `newsresearch` / `Research.execute()`.

The server reads one already-produced result document into memory and serves its exact original JSON bytes. It never opens the research database, runs storage-wide preflight, calls a model, retrieves sources or creates a research result. It checks the file's protected permissions and rejects Git locations, symlinks and junctions. The server binds to loopback by default, rejects unexpected Host/Origin and cross-site requests, disables caching, and supplies a restrictive content security policy. It has no third-party assets or analytics; publisher links open only when clicked.

## Read on a phone on the same network

Use the computer's specific private IPv4 address (RFC1918), rather than `127.0.0.1`:

```powershell
uv run --frozen python scripts/serve_rag_results.py --result C:/protected/run/result.json --listen 192.168.1.233 --port 8787
```

Choose the actual address assigned to this computer. The server prints a **pairing page URL without credentials**. Open that page on the computer, connect the phone to the same trusted Wi-Fi, and scan the QR with the phone camera. The phone receives the saved reader after pairing. The pairing page also has a button to open the reader on the computer. The QR and its helper script are available only when the TCP peer is the host computer itself; forwarded-IP headers are ignored.

Phone mode generates a high-entropy key in memory. The QR uses a URL fragment, which the reader removes before exchanging it in a bounded, exact-origin POST for an HttpOnly, SameSite=Strict session cookie. The server logs no requests or keys and writes no pairing key/QR to disk or Git. Pairing and further data requests expire two hours after server startup; already-loaded answers remain in the browser. Restarting creates a new key and invalidates old cookies. This is a bearer pairing session, not an identified research reviewer. It does not encrypt HTTP traffic: use a trusted home network. The server rejects public, wildcard and link-local listen addresses and never changes firewall, router, network-profile or global settings. Windows firewall or Wi-Fi client isolation may prevent another device from reaching it; phone connectivity must be verified on the actual phone. Access away from the local network requires a separate private connection setup; this mode supplies no public hosting or tunnel.

On narrow screens, use **Articles** and **Read answer** to switch views, or **Previous / Articles / Next** in the fixed bottom bar. Selecting an article opens its answer; returning to the list preserves the browsing position. Controls are sized for touch. Saved/read markers stay in each browser and do not synchronize between devices.

Keep result JSON, source quotations and screenshots in protected storage outside Git. Commit only the generic viewer, tests and documentation. This reader does not provide an authenticated multi-user research review workflow.

## Optional audited follow-up questions

Enable **Ask a follow-up** with `--research-workspace C:/protected/research` and a pinned `--codex-model gpt-6.1-sol`. The store must contain the immutable result identified by the saved JSON. Enabling the panel opens no research store and performs no model call; each submitted form explicitly authorizes one audited Codex account answer. **Current evidence** reuses the latest retrieved passages without a new embedding or corpus scoring. If more evidence is needed, the answer says so. **Search corpus again** explicitly runs local keyword retrieval (up to 20 articles); it is not semantic vector search and needs no embedding or paid API.

Answers show citations, context coverage and exact recorded presentations. Questions, evidence and attempts are retained through `Research.execute()` and the shared gateway; all integrity checks remain in place. GET status/polling and ordinary reading remain free of research execution. See [the conversation method, audit contract and limitations](CONVERSATIONAL_RAG.md).

On Windows, supply `--codex-executable` with the absolute installed native `codex.exe` path when the command on PATH is a PowerShell/npm shim. Keep any machine-specific startup scripts outside Git. The native executable and configured model are recorded with the model attempt.
