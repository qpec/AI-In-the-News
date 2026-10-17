"""Register and retain a bounded official-documentation lookup, with no model calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.error
import urllib.request

from newsresearch.common import Config, Context, Json, ResearchError
from newsresearch.runtime import Research, audited_handler

OWNER = "entity-design-library-docs-20261017-v1"
URLS = [
    "https://spacy.io/models/en",
    "https://spacy.io/models/nl",
    "https://stanfordnlp.github.io/stanza/ner_models.html",
    "https://huggingface.co/docs/transformers/tasks/token_classification",
    "https://spacy.io/api/entityrecognizer",
    "https://spacy.io/api/entityruler",
]
MODEL_URLS = [
    "https://raw.githubusercontent.com/explosion/spacy-models/master/meta/en_core_web_sm-3.8.0.json",
    "https://raw.githubusercontent.com/explosion/spacy-models/master/meta/nl_core_news_sm-3.8.0.json",
]
MAX_BYTES = 2 * 1024 * 1024


class NoDocumentationRedirects(urllib.request.HTTPRedirectHandler):
    """A fixed-URL lookup never follows an unregistered redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.URLError("documentation_redirect_not_permitted")


def open_fixed_document(url: str):  # type: ignore[no-untyped-def]
    if url not in URLS + MODEL_URLS:
        raise ResearchError("documentation_url_outside_fixed_scope")
    request = urllib.request.Request(url, headers={"User-Agent": "AI-In-the-News-method-audit/1.0"})
    return urllib.request.build_opener(NoDocumentationRedirects()).open(request, timeout=20)


def model_metadata(raw: bytes) -> Json:
    """Project only exact required strings/labels; do not invent missing data."""
    try:
        metadata = json.loads(raw)
        result = {"name": metadata["name"], "version": metadata["version"],
                  "language": metadata["lang"], "ner_labels": metadata["labels"]["ner"]}
        if (any(not isinstance(result[key], str) or not result[key].strip()
                for key in ("name", "version", "language"))
                or not isinstance(result["ner_labels"], list)
                or not result["ner_labels"]
                or any(not isinstance(label, str) or not label.strip() for label in result["ner_labels"])):
            raise ValueError("documentation_model_metadata_invalid")
        return result
    except (KeyError, TypeError) as error:
        raise ValueError("documentation_model_metadata_invalid") from error


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


class DocumentationResearch(Research):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if data not in ({}, {"supplement": True}) or self.config.offline or self.ledger.root.name != OWNER:
            raise ResearchError("documentation_exact_online_scope_required")
        urls = MODEL_URLS if data else URLS
        key = OWNER + ("-model-metadata" if data else "")
        protocol = self._version(session, context, {"kind": "protocol", "key": key,
            "content": {"method": "official-ner-documentation-v1", "urls": urls,
                "user_scope": "User explicitly requested online checks of prominent NLP libraries.",
                "procedure": "Fetch each fixed official URL once without following redirects; retain exact permitted response bytes before parsing, URL, time, status, explicit SHA256 and visible text; report failures without substitution. No model inference or corpus processing.",
                "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "limits": f"{len(urls)} pages, maximum 2MiB each, 20-second network timeout, no automatic retries; fetched documentation is not dataset performance evidence."}})["id"]
        bound = Context(context.objective, context.actor, {"protocol": protocol})
        results = []
        for url in urls:
            self.ledger.append(session, "ner.documentation.fetch.intended", {"url": url, "protocol": protocol})
            item: Json = {"url": url, "started_at": datetime.now(timezone.utc).isoformat()}
            try:
                with open_fixed_document(url) as response:
                    item.update({"status": response.status, "final_url": response.url,
                                 "content_type": response.headers.get("Content-Type")})
                    if response.url != url:
                        raise ValueError("documentation_final_url_mismatch")
                    raw = response.read(MAX_BYTES + 1)
                    if len(raw) > MAX_BYTES:
                        raise ValueError("documentation_response_exceeds_registered_limit")
                item.update({"bytes": len(raw), "raw_artifact": self.ledger.artifacts.put_bytes(raw),
                             "raw_sha256": hashlib.sha256(raw).hexdigest()})
                if item["status"] != 200:
                    raise ValueError("documentation_http_status_not_successful")
                parser = VisibleText()
                parser.feed(raw.decode("utf-8", errors="replace"))
                visible = "\n".join(parser.parts)
                item.update({"state": "retrieved",
                             "text_artifact": self.ledger.artifacts.put_bytes(visible.encode("utf-8"))})
                # Deterministic lexical contexts, not model summaries or findings.
                lines = visible.splitlines()
                matches = [i for i, line in enumerate(lines) if any(term in line for term in (
                    "CARDINAL", "PERSON", "NORP", "CoNLL", "OntoNotes", "WikiANN", "B-ORG", "B-PER", "PER,", "non-overlapping", "whole entity", "patterns"))]
                indices = sorted({j for i in matches[:25] for j in range(max(0, i-1), min(len(lines), i+3))})
                item["literal_contexts"] = [lines[i] for i in indices]
                if url in MODEL_URLS:
                    item["model_metadata"] = model_metadata(raw)
            except urllib.error.HTTPError as error:
                item.update({"state": "failed", "error_type": type(error).__name__,
                             "status": error.code, "final_url": error.url,
                             "content_type": error.headers.get("Content-Type") if error.headers else None})
                try:
                    raw_error = error.read(MAX_BYTES + 1)
                    if len(raw_error) <= MAX_BYTES:
                        item.update({"bytes": len(raw_error),
                                     "raw_artifact": self.ledger.artifacts.put_bytes(raw_error),
                                     "raw_sha256": hashlib.sha256(raw_error).hexdigest()})
                    else:
                        item["response_exceeds_limit"] = True
                finally:
                    error.close()
            except (urllib.error.URLError, ValueError, TimeoutError) as error:
                item.update({"state": "failed", "error_type": type(error).__name__})
            item["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.ledger.append(session, "ner.documentation.fetch.completed", item)
            results.append(item)
        result = {"protocol": protocol, "documents": results, "model_calls": 0,
                  "retrieved": sum(row["state"] == "retrieved" for row in results),
                  "failed": sum(row["state"] == "failed" for row in results), "pending": 0,
                  "record_presentation_supported": False}
        identifier = self._version(session, bound, {"kind": "note", "key": key + "-result", "content": result})["id"]
        return {"id": identifier, **result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--supplement", action="store_true")
    args = parser.parse_args()
    engine = DocumentationResearch(args.workspace, config=Config(offline=False))
    try:
        result = engine.execute("status", {"supplement": True} if args.supplement else {}, objective="Check official NLP library entity taxonomies for event-method design", actor="codex:entity-library-documentation")
        print(json.dumps(result, ensure_ascii=True, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
