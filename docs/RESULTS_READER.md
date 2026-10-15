# Local results reader

Browse an existing, completed RAG result without rerunning retrieval or inference:

```powershell
uv run --frozen python scripts/serve_rag_results.py --result C:/protected/run/result.json
```

Open the printed localhost URL (normally `http://127.0.0.1:8787/`). Keep the server running while reading; Ctrl+C stops it. Use `--port` to choose another local port. The command can be rerun with the same saved result after a restart.

The reading room opens on supported model examples. Select **All** to browse every saved answer, or filter insufficient and uncertain answers. Search titles, organizations, decisions and answer text within the loaded result. Each article shows its original retrieval rank and similarity, model answer, extracted details, expandable source quotations, original publisher link and version identifiers. Similarity is not a probability, and this RAG workflow applies no binary relevance cutoff or new tags. Model answers remain provisional and article totals are not incident totals.

**Save** and **Mark read** remember reading progress in this browser, keyed to the result set. Saved and unread filters help continue later. J/K navigate, S saves, R marks read, and / focuses search when focus is outside a form control. These are personal browsing markers, not accepted findings or audited research reviews; they are not written to SQL. Formal selections, reviews, exports and new research must still use `newsresearch` / `Research.execute()`.

The server reads one already-produced result document into memory and serves its exact original JSON bytes. It never opens the research database, runs storage-wide preflight, calls a model, retrieves sources or creates a research result. It checks the file's protected permissions and rejects Git locations, symlinks and junctions. Only three generic assets and the selected document have routes. The server binds to loopback, rejects unexpected Host/Origin and cross-site API requests, disables caching, and supplies a restrictive content security policy. It has no third-party assets, analytics or network requests; publisher links open only when clicked.

Keep result JSON, source quotations and screenshots in protected storage outside Git. Commit only the generic viewer, tests and documentation. This local reader is intended for the same computer; it is not a hosted or shared research application, and it does not provide an authenticated multi-user review workflow.
