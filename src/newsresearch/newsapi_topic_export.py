"""User-authorized copy of a fixed collection to its named private data repo."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING
import uuid
import zipfile

from .common import Context, Json, ResearchError, canonical, require_active, require_no_credentials, utc
from .newsapi_collection import BACKFILL_PERIODS, PERIODS, WORDS, collection_request

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-private-topic-export-v1"
REPOSITORY = "qpec/AI-In-the-News-Data"
TOPIC = "topics/cybercrime-nl"


def csv_bytes(rows: list[Json], fields: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def inspect_bundle(raw: bytes, year: Json) -> list[Json]:
    """Validate copied records and return only locator-level missingness."""
    absent = []
    counts = {"records": 0, "body": 0}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if set(archive.namelist()) != {"artikelen.jsonl", "manifest.json"}:
            raise ResearchError("Unexpected bundle members")
        manifest = json.loads(archive.read("manifest.json"))
        require_no_credentials(manifest)
        if (manifest["date_start"], manifest["date_end"]) != (year["date_start"], year["date_end"]):
            raise ResearchError("Bundle period mismatch")
        with archive.open("artikelen.jsonl") as stream:
            for line in stream:
                row = json.loads(line)
                require_no_credentials(row)
                article = row["article"]
                if hashlib.sha256(canonical(article).encode()).hexdigest() != row["source_hash"]:
                    raise ResearchError("Article materialization hash mismatch")
                if not year["date_start"] <= article.get("date", "") <= year["date_end"] or article.get("lang") != "nld":
                    raise ResearchError("Article outside collection scope")
                counts["records"] += 1
                fields = [field for field in ["uri", "title", "url", "date", "lang", "body"]
                          if not isinstance(article.get(field), str) or not article[field].strip()]
                source = article.get("source") or {}
                fields += ["source." + field for field in ["uri", "title"] if not source.get(field)]
                counts["body"] += "body" in fields
                if fields:
                    absent.append({"year": year["year"], "uri": article.get("uri"), "date": article.get("date"),
                        "url": article.get("url"), "missing_fields": "|".join(fields),
                        "quarantined": article.get("quarantined") is True,
                        "body_missing_reason": ("local_pattern_quarantine" if article.get("quarantined") else "provider_record_blank_or_absent") if "body" in fields else "",
                        "receipt_id": row["receipt_id"], "item_index": row["item_index"],
                        "source_hash": row["source_hash"]})
    if counts != {"records": year["returned"], "body": year.get("missing_body_quarantined", 0) + year.get("missing_body_other", 0)}:
        raise ResearchError("Bundle counts disagree with immutable missingness audit")
    return absent


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"export_policy"})
    policy = engine.ledger.get(context.versions["export_policy"], "export_policy")["content"]
    backfill = data.get("action") == "backfill_topic_export"
    topic = TOPIC + "/extensions/2020-2023" if backfill else TOPIC
    periods = BACKFILL_PERIODS if backfill else PERIODS
    if (policy.get("method") != METHOD or policy.get("repository") != REPOSITORY
            or policy.get("user_authorized_private_dataset_copy") is not True):
        raise ResearchError("Explicit topic-bound private dataset export authorization required")
    if backfill and policy.get("topic") != topic:
        raise ResearchError("Explicit extension-topic copy instruction required")
    original = engine.ledger.get(policy["materialization_result"], "newsapi_collection_materialization")
    missing = engine.ledger.get(policy["missingness_result"], "newsapi_collection_missingness")
    if missing["source_result"] != policy["materialization_result"]:
        raise ResearchError("Missingness and materialization lineage mismatch")
    if original.get("periods", [list(p) for p in PERIODS]) != [list(p) for p in periods]:
        raise ResearchError("Export collection period mismatch")
    if {k: v for k, v in context.versions.items() if k != "export_policy"} != missing["versions"]:
        raise ResearchError("Bind exact original missingness versions")
    repo = Path(data["repository_path"]).resolve(strict=True)
    destination = repo / topic
    if destination.exists():
        raise ResearchError("Topic already exists; preserve existing work")
    remote = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "--push", "origin"], check=True, capture_output=True, text=True).stdout.strip()
    if remote not in {f"https://github.com/{REPOSITORY}.git", f"git@github.com:{REPOSITORY}.git"}:
        raise ResearchError("Unexpected data repository push remote")
    engine.ledger.append(session, "newsapi.topic_export.repository_check.intent", {"repository": REPOSITORY})
    visibility = json.loads(subprocess.run(["gh", "repo", "view", REPOSITORY, "--json", "nameWithOwner,isPrivate"], check=True, capture_output=True, text=True).stdout)
    engine.ledger.append(session, "newsapi.topic_export.repository_check.result", visibility)
    if visibility != {"nameWithOwner": REPOSITORY, "isPrivate": True}:
        raise ResearchError("Named private repository required")
    contents: dict[str, bytes] = {}
    inventory: list[Json] = []
    for bundle, year in zip(original["bundles"], missing["years"], strict=True):
        if bundle["year"] != year["year"]:
            raise ResearchError("Bundle year mismatch")
        raw = (engine.ledger.artifacts.root / bundle["artifact"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != bundle["artifact"]:
            raise ResearchError("Bundle artifact hash mismatch")
        inventory.extend(inspect_bundle(raw, year))
        contents[f"articles/articles-{year['year']}.zip"] = raw
    summary = {key: missing[key] for key in ["total_records", "body_present", "missing_body", "missing_body_percent",
        "missing_fields", "missing_fields_quarantined", "missing_fields_other", "withheld_locator_fields",
        "successful_pages", "raw_response_bytes_unavailable_pages", "nonblank_body_at_most_200_chars", "years"]}
    summary.update({"missing_successful_pages": sum(len(y["missing_page_indices"]) for y in missing["years"]),
        "unretrieved_provider_matches": sum(y["count_gap"] for y in missing["years"]),
        "missing_retrievals_beyond_provider_query": None,
        "coverage_limit": "Provider-query pagination only; total Dutch-news/Netherlands-event recall unknown",
        "costs": {key: original[key] for key in ["reported_collection_cost", "final_observed_used", "allowance", "target_used", "stop_reason"]},
        "provenance": {"materialization_result": policy["materialization_result"], "missingness_result": policy["missingness_result"],
            "method_versions": context.versions}, "exported_at": utc(), "new_newsapi_requests": 0, "new_model_calls": 0})
    summary["costs"]["account_ceiling"] = original.get("account_ceiling", 4000)
    contents["missingness.json"] = (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode()
    year_fields = ["year", "date_start", "date_end", "returned", "body_present", "quarantined", "missing_body_quarantined",
        "missing_body_other", "successful_pages", "provider_pages", "provider_total", "count_gap", "missing_page_indices",
        "failed_attempts", "failed_attempts_with_successful_retry", "raw_response_bytes_unavailable_pages", "unavailable_request_costs"]
    contents["coverage-by-year.csv"] = csv_bytes([{k: y.get(k) for k in year_fields} for y in missing["years"]], year_fields)
    contents["records-with-missing-fields.csv"] = csv_bytes(inventory, ["year", "uri", "date", "url", "missing_fields", "quarantined", "body_missing_reason", "receipt_id", "item_index", "source_hash"])
    method = {"provider": "NewsAPI.ai / Event Registry", "retrieval_date": "2026-10-16",
        "families": {"hacks": WORDS[:3], "ransomware": WORDS[3:4], "data_breaches": WORDS[4:6], "cyberattacks": WORDS[6:]},
        "requests": [collection_request(p, 1) for p in periods],
        "pagination": "articlesPage increments from 1; articlesCount=100; round-robin across years, ascending publication date; stop at provider exhaustion or account budget",
        "archive_gate": "Historical Dutch positive control returned 100 articles for 2024-01-01 through 2024-01-02 after user enabled archive access",
        "representation": "Unchanged private working bundles, not original raw API response bytes; exact duplicate record versions removed within year, changed versions retained",
        "retention": f"{missing['missing_body']} records lack body text; local pattern quarantines retain safe locators and hashes without article text/title/source metadata. Pattern matches may be false positives; non-locator trigger fields were not logged",
        "scope": "Dutch-language keyword candidates; not reviewed Netherlands events or incident counts",
        "score_or_relevance_cutoff": None, "provider_index_recall": None,
        "private_repository_exception": policy["user_instruction"],
        "not_in_repository": "Credentials, working database, audit logs, raw response artifacts and per-request billing log"}
    contents["retrieval-method.json"] = (json.dumps(method, ensure_ascii=False, indent=2) + "\n").encode()
    contents["README.md"] = (backfill_readme(original, missing, len(inventory)) if backfill else README).encode()
    checksums = {name: hashlib.sha256(raw).hexdigest() for name, raw in contents.items()}
    contents["SHA256SUMS.txt"] = "".join(f"{value}  {name}\n" for name, value in sorted(checksums.items())).encode()
    for name in contents:
        if (repo / "topics").is_symlink() or destination.is_symlink():
            raise ResearchError("Linked export destination forbidden")
        if len(contents[name]) > 95_000_000:
            raise ResearchError("File too large for normal Git transfer")
    engine.ledger.record(session, "newsapi_topic_export_intent", str(uuid.uuid4()), {
        "versions": context.versions, "destination": str(destination), "files": checksums,
        "user_instruction": policy["user_instruction"], "repository": REPOSITORY})
    for name, raw in contents.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        if hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(raw).hexdigest():
            raise ResearchError("Export write verification failed")
    result = {"versions": context.versions, "repository": REPOSITORY, "destination": str(destination),
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in contents.items()},
        "records": missing["total_records"], "records_with_missing_fields": len(inventory),
        "missing_body": missing["missing_body"], "missing_successful_pages": summary["missing_successful_pages"],
        "unretrieved_provider_matches": summary["unretrieved_provider_matches"],
        "source_result": policy["materialization_result"], "missingness_result": policy["missingness_result"],
        "new_newsapi_requests": 0, "new_model_calls": 0, "repository_metadata_requests": 1,
        "git_push_status": "not_performed_by_export_operation", "generated_at": utc()}
    identifier = engine.ledger.record(session, "newsapi_topic_export", str(uuid.uuid4()), result)
    return {"id": identifier, **result}


def backfill_readme(original: Json, missing: Json, affected: int) -> str:
    text = ("# Cybercrime NL — extension to 2020\n\n"
        "Publication dates: **1 January 2020 through 14 October 2023**, inclusive.\n"
        "Retrieved on 16 October 2026. This extends the original snapshot without overlapping its dates.\n\n"
        "| Year | Articles / provider matches | Pages / expected | Missing text |\n"
        "|---|---:|---:|---:|\n")
    for y in missing["years"]:
        text += (f"| {y['year']} | {y['returned']:,} / {y['provider_total']:,} | "
                 f"{y['successful_pages']} / {y['provider_pages']} | "
                 f"{y.get('missing_body_quarantined', 0) + y.get('missing_body_other', 0)} |\n")
    pages = sum(len(y["missing_page_indices"]) for y in missing["years"])
    gap = sum(y["count_gap"] for y in missing["years"])
    text += (f"\n**{missing['total_records']:,} article records**, {missing['body_present']:,} with nonblank text, "
        f"**{missing['missing_body']} missing bodies ({missing['missing_body_percent']:.2f}%)**. "
        f"Missing expected pages: **{pages}**; unretrieved provider-reported matches: **{gap}**. "
        f"Final collection stop: `{original['stop_reason']}`.\n\n"
        "## Retrieval method\n\n"
        "Same four families as the original snapshot: hacks (`hack`, `gehackt`, `hackers`), "
        "ransomware (`ransomware`), data breaches (`datalek`, `datalekken`), cyberattacks "
        "(`cyberaanval`, `cyberaanvallen`). All eight are OR phrases in title/body, "
        "`lang=nld`, `dataType=news`, `keepAll`, no Cyber Crime category or geography gate. "
        "Full body requested (`includeArticleBody=true`, `articlesArticleBodyLen=-1`). "
        "Calendar-year pages in ascending publication date; first-page coverage then "
        "round-robin continuation. 100 is the page size, not the collection cap. "
        "Existing successful historical archive control was reused. Returned article "
        "dates and preserved request receipts establish observed year coverage.\n\n"
        "## Files and missingness\n\n"
        "`articles/` contains four unchanged ZIP working bundles with `artikelen.jsonl` "
        "and `manifest.json`. Rows retain safe article data, receipt/item references, "
        "canonical article hash and original response hash. These are not raw API response snapshots. "
        "`retrieval-method.json` contains credential-free request templates: increment "
        "`articlesPage` beyond the illustrative page 1. `SHA256SUMS.txt` inventories this "
        "extension's other files.\n\n"
        "`coverage-by-year.csv` and `missingness.json` distinguish missing pages, provider "
        "count gaps, missing bodies, quarantines, unavailable raw snapshots and failures/retries. "
        f"`records-with-missing-fields.csv` identifies {affected} records with at least one "
        "missing inspected field. Missing bodies are not discarded from the denominator. "
        "Pattern quarantine is local screening, can produce false positives and does not "
        "establish actual credentials. Unrecorded original non-locator triggers remain unknown.\n\n"
        f"Missing fields: `{json.dumps(missing['missing_fields'], sort_keys=True)}`. "
        f"Outside quarantine: `{json.dumps(missing['missing_fields_other'], sort_keys=True)}`. "
        f"Original response bytes are unavailable for {missing['raw_response_bytes_unavailable_pages']} "
        f"of {missing['successful_pages']} successful pages containing screened rows; safe "
        "records and response hashes remain, so this is not loss of every article on those pages. "
        f"There are {missing['nonblank_body_at_most_200_chars']} nonblank bodies of at most "
        "200 characters; short text alone is not evidence of truncation.\n\n"
        "## Actual costs and limits\n\n"
        f"Backfill search requests explicitly reported **{original['reported_collection_cost']:g} tokens**. "
        f"Latest observed account usage: **{original['final_observed_used']:g}/5,000** "
        f"({100*original['final_observed_used']/5000:.2f}%). "
        "The original 80% or more goal has a 4,000 soft utilization target; the explicit "
        "extension uses remaining quota to complete the requested history within a "
        "5,000 hard account ceiling. Collection stops at query exhaustion, not padded "
        "spending. Quota observations are historical, not a live balance.\n\n"
        "Counts describe keyword candidate article records, not reviewed Netherlands "
        "events or incidents. No relevance scoring/cutoff, model article judgement, "
        "event grouping or accepted findings were produced. Complete pagination cannot "
        "establish provider-index recall, all Dutch-news coverage or publisher-text fidelity.\n\n"
        "## Private-copy instruction and audit\n\n"
        "The user requested the dataset in the private data repo and then extended the "
        "same collection back to 2020. This child topic preserves the original snapshot. "
        "The registered copy policy is specific to these safe bundles and method/missingness "
        "summaries in `qpec/AI-In-the-News-Data`. It does not permit public redistribution "
        "or other exports. Credentials, working databases, raw response artifacts, audit "
        "logs and per-request billing logs remain protected outside Git. Retrieval, "
        "materialization, deterministic missingness and copying use `Research.execute()` "
        "with registered methods and immutable source/result/version references. "
        "Copy validation verifies bundle/row hashes, scope, credentials and counts; "
        "version/receipt IDs are references, not copies of audit logs.\n")
    return text


README = """# Cybercrime NL — Dutch-language keyword collection

Collected on 16 October 2026 from NewsAPI.ai / Event Registry. Publication dates:
15 October 2023 through 15 October 2026 inclusive, split by calendar year.
This is a candidate article collection, not a count of incidents or event dossiers.
Dutch language does not establish that the reported event occurred in the Netherlands.

## Files

- `articles/articles-YYYY.zip`: unchanged private working bundles, each containing
  `artikelen.jsonl` (one record per line) and a provenance `manifest.json`.
- `retrieval-method.json`: exact credential-free request templates, four keyword
  families, archive check, pagination, retention and limitations. Increment
  `articlesPage` beyond the illustrative page 1 to reproduce all pages.
- `coverage-by-year.csv`: returned/provider counts, pages, missing text, historical
  failures/retries and unavailable original-response snapshots.
- `missingness.json`: complete aggregate diagnostics and method/result references.
- `records-with-missing-fields.csv`: the 143 records with at least one missing
  inspected field. Includes 141 records without text and two additional records
  without titles. Missing URLs remain blank. No article text is in this inventory.
- `SHA256SUMS.txt`: SHA-256 of every other file in this topic.

## Retrieval and missingness results

| Publication period | Records / provider matches | Pages / expected | Missing text |
| --- | ---: | ---: | ---: |
| 2023-10-15 through 2023-12-31 | 1,507 / 1,507 | 16 / 16 | 2 |
| 2024 | 7,979 / 7,979 | 80 / 80 | 57 |
| 2025 | 8,565 / 8,565 | 86 / 86 | 60 |
| 2026-01-01 through 2026-10-15 | 9,301 / 9,301 | 94 / 94 | 22 |
| Total | 27,352 / 27,352 | 276 / 276 | 141 |

**Missing retrieval pages: 0. Unretrieved matches relative to final provider totals: 0.**
The limit of 100 was per page; collection continued through pages 16/80/86/94.
Provider totals/index caps are not independently verified; real-world recall is unknown.

**Missing article text: 141 / 27,352 (0.52%)**, all due to local credential-pattern
quarantine. Outside quarantine, no bodies are blank/missing. The quarantined rows
remain in the denominator with safe metadata/hashes. Pattern matches can be false
positives and are not findings of actual credentials. Original triggers outside
locator fields were not retained. There are 27,211 nonblank article bodies.

Missing metadata: 143 titles (141 quarantined, 2 otherwise retained), 125 URLs
explicitly withheld, 141 source names and 141 source identifiers. Other inspected
fields have no missing values. The record inventory identifies the affected rows.

Original response bytes are unavailable for 66 of 276 successful pages containing
flagged rows. Safe article records and response hashes remain; those pages' other
articles are not missing. One interrupted request was successfully retried with
identical parameters. Its original response and individual charge are unavailable.

Nineteen nonblank bodies have at most 200 characters; this does not prove truncation.
Full publisher-text fidelity and Netherlands-event relevance have not been reviewed.
The search can miss articles absent from the provider, using other words, in other
languages/types, or outside the publication window. No relevance scores/cutoffs,
model article judgments, event grouping or accepted incident findings are included.

## Method and actual costs

Four families: hacks (`hack`, `gehackt`, `hackers`), ransomware (`ransomware`),
data breaches (`datalek`, `datalekken`), cyberattacks (`cyberaanval`, `cyberaanvallen`).
All eight phrases were combined with OR in title/body, `lang=nld`, `dataType=news`.
The Cyber Crime category tag was not required. Duplicates were requested with
`keepAll`; only exact record-version duplicates were removed from working bundles.
Full body was requested with `includeArticleBody=true`, `articlesArticleBodyLen=-1`.
Requests used ascending publication date and 100-item calendar-year pages, with
round-robin continuation. Archive access was verified by returned historical articles.

The target was 4,000 total account tokens out of 5,000. Query exhaustion stopped
collection first. Latest observed usage was 2,707/5,000 (54.14%); successful
collection requests explicitly reported 1,380 tokens. These differ because account
usage also includes earlier work, controls and an interrupted attempt whose
individual charge is unknown. Quota observations are historical, not a live balance.
This packaging adds no NewsAPI.ai requests or model calls.

## Private-copy authorization and provenance

The user's explicit request on 16 October 2026 to push this dataset into a separate
Cybercrime NL topic authorizes this narrowly scoped copy to the existing private
`qpec/AI-In-the-News-Data` repository, superseding the earlier local-only restriction
for these four safe bundles and the accompanying method/missingness summaries.
This exception does not authorize public distribution or any other dataset export.
Credentials, working databases, audit logs, raw response artifacts and per-request
billing logs remain in protected storage outside Git. The main project's collection
and missingness operations used `Research.execute()` with registered methods;
the copy validates artifact hashes, record hashes, counts and credential screening
before writing. Result/version identifiers are references, not copies of audit logs.
"""
