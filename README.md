# AI In the News

A project for collecting and exploring news coverage of artificial intelligence.

## Repositories

| Repository | Purpose | Visibility |
| --- | --- | --- |
| [AI-In-the-News](https://github.com/qpec/AI-In-the-News) | Project code, collection tools and documentation | Public |
| [AI-In-the-News-Data](https://github.com/qpec/AI-In-the-News-Data) | Collected data and derived datasets | Private |

Collected data belongs in the private data repository. This public repository is the home for the tools and documentation used to work with it.

## Research workflow

Keep the two repositories next to each other. Source exports and research outputs belong in the private repository; reusable code and methods belong here.

With Python 3.11 or newer, verify the private source files and article bundles:

```sh
python scripts/verify_sources.py --data-root ../AI-In-the-News-Data
```

The verifier checks file sizes and SHA-256 hashes, reads the article bundles directly from ZIP, and checks record counts, text availability and duplicate article IDs. It writes its report to `metadata/validation.json` in the private repository. It does not call any external API.

The [research plan](docs/research-plan.md) describes the workflow and the decisions to make before substantive analysis.
