"""Pure excerpt workload diagnostics; production rows require audited caller."""
from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any, Callable

from newsresearch.common import Json, ResearchError, digest, require_no_credentials
from luna_excerpt_windows import build_excerpt

VARIANTS = ("word_windows", "paragraph_caps")
OUTPUT_SCENARIOS = (400, 800, 1600)
RATES = {"batch_input_per_million": .05, "batch_output_per_million": .25,
         "standard_input_per_million": .10, "standard_output_per_million": .50}
SIGNALS = {
    "cve_identifier": re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I),
    "numeric_calendar_date": re.compile(r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})\b"),
    "digit_quantity": re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?:\s?%)?(?!\w)"),
}


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def packet(article: Json, excerpt: Json) -> Json:
    source = article.get("source")
    source = source if isinstance(source, dict) else {}
    return {"title": article.get("title") if isinstance(article.get("title"), str) else "",
            "metadata": {key: {"present": key in article, "value": article.get(key)}
                         for key in ("lang", "date", "dateTime", "dateTimePub")},
            "publisher_metadata_not_evidence": {key: source.get(key) for key in ("uri", "title")},
            "spans": excerpt["spans"],
            "body_fully_covered": excerpt["has_body_text"] and excerpt["all_nonwhitespace_body_covered"],
            "body_word_count": excerpt["word_count"],
            "omitted_word_count": excerpt["omitted_word_count"], "excerpt_rule": excerpt["variant"]}


def costs(input_tokens: int, requests: int) -> list[Json]:
    return [{"assumed_output_tokens_per_request": output,
             "batch_usd": (input_tokens * .05 + requests * output * .25) / 1_000_000,
             "standard_usd": (input_tokens * .10 + requests * output * .50) / 1_000_000}
            for output in OUTPUT_SCENARIOS]


class ExcerptCounts:
    def __init__(self, corpus: str, count_tokens: Callable[[str], int], overhead_tokens: int) -> None:
        if corpus not in ("incident-reports", "cybercrime"):
            raise ResearchError("excerpt_corpus_invalid")
        self.corpus = corpus
        self.count_tokens = count_tokens
        self.overhead = overhead_tokens
        self.rows: list[Json] = []
        self.totals: Counter[str] = Counter({key: 0 for key in ("rows", "usable", "retention_unavailable", "body_unavailable")})
        self.concepts: Counter[str] = Counter()
        self.languages: Counter[str] = Counter()
        self.metadata_quality: dict[str, Counter[str]] = {key: Counter() for key in ("title", "lang", "date", "dateTime", "dateTimePub", "source.uri", "eventUri")}
        self.variants: dict[str, Counter[str]] = {name: Counter({"input_tokens_proxy": 0}) for name in (*VARIANTS, "full_text")}
        self.signals: dict[str, dict[str, Counter[str]]] = {name: {signal: Counter({key: 0 for key in (
            "rows_with_full_body_signal", "full_body_distinct_values_summed", "visible_distinct_values_summed", "rows_losing_at_least_one_value")}) for signal in SIGNALS} for name in VARIANTS}
        self._seen: set[str] = set()

    def add(self, row: Json, locator: str) -> None:
        identifier = digest({"corpus": self.corpus, "locator": locator})
        if identifier in self._seen:
            raise ResearchError("excerpt_duplicate_locator")
        self._seen.add(identifier)
        line: Json = {"id": identifier, "row_hash": digest(row), "state": "retention_unavailable"}
        self.rows.append(line)
        self.totals["rows"] += 1
        try:
            require_no_credentials(row)
        except ResearchError:
            self.totals["retention_unavailable"] += 1
            return
        article = row.get("article")
        article = article if isinstance(article, dict) else {}
        if any(obj.get("retention") == "metadata_only" or obj.get("metadata_only") is True
               or obj.get("quarantined") is True for obj in (row, article)):
            self.totals["retention_unavailable"] += 1
            return
        body = article.get("body")
        if not isinstance(body, str) or not body.strip():
            line["state"] = "body_unavailable"
            self.totals["body_unavailable"] += 1
            return
        line["state"] = "usable"
        self.totals["usable"] += 1
        source = article.get("source")
        source = source if isinstance(source, dict) else {}
        for key, counter in self.metadata_quality.items():
            obj, name = (source, "uri") if key == "source.uri" else (article, key)
            value = obj.get(name)
            state = ("absent" if name not in obj else "null" if value is None else "bad_type"
                     if not isinstance(value, str) else "nonblank" if value.strip() else "blank")
            counter[state] += 1
        title = article.get("title")
        self.totals["missing_title"] += not isinstance(title, str) or not title.strip()
        language = article.get("lang")
        language = language if isinstance(language, str) and language in ("eng", "nld") else "other_or_missing"
        self.languages[language] += 1
        concepts = article.get("concepts")
        self.totals["concepts_present_nonempty"] += isinstance(concepts, list) and bool(concepts)
        concept_types = set()
        for concept in concepts if isinstance(concepts, list) else []:
            if isinstance(concept, dict):
                kind = concept.get("type")
                concept_types.add(kind if kind in ("org", "person", "loc", "wiki") else "other_or_missing")
        self.concepts.update(concept_types)
        full_signals = {name: set(regex.findall(body)) for name, regex in SIGNALS.items()}
        line["variants"] = {}
        for variant in VARIANTS:
            excerpt = build_excerpt(body, variant)
            payload = packet(article, excerpt)
            token_count = self.count_tokens(compact(payload)) + self.overhead
            c = self.variants[variant]
            c["input_tokens_proxy"] += token_count
            c["visible_words"] += excerpt["visible_word_count"]
            c["body_words"] += excerpt["word_count"]
            c["fully_covered"] += payload["body_fully_covered"]
            c["partial_body"] += not payload["body_fully_covered"]
            c["one_paragraph"] += excerpt["paragraph_count"] == 1
            c["max_input_tokens_proxy"] = max(c["max_input_tokens_proxy"], token_count)
            c["over_32000_proxy_tokens"] += token_count > 32_000
            line["variants"][variant] = {"packet_hash": digest(payload), "input_tokens_proxy": token_count,
                "visible_words": excerpt["visible_word_count"], "body_words": excerpt["word_count"],
                "fully_covered": payload["body_fully_covered"]}
            for name, regex in SIGNALS.items():
                visible = {value for span in excerpt["spans"] for value in regex.findall(span["text"])}
                counter = self.signals[variant][name]
                counter["rows_with_full_body_signal"] += bool(full_signals[name])
                counter["full_body_distinct_values_summed"] += len(full_signals[name])
                counter["visible_distinct_values_summed"] += len(visible & full_signals[name])
                counter["rows_losing_at_least_one_value"] += bool(full_signals[name] - visible)
        whole = {"spans": [{"span_id": "body-1", "start": 0, "end": len(body), "text": body}],
                 "has_body_text": True, "all_nonwhitespace_body_covered": True,
                 "word_count": excerpt["word_count"], "omitted_word_count": 0, "variant": "full_text"}
        count = self.count_tokens(compact(packet(article, whole))) + self.overhead
        self.variants["full_text"]["input_tokens_proxy"] += count
        self.variants["full_text"]["max_input_tokens_proxy"] = max(self.variants["full_text"]["max_input_tokens_proxy"], count)
        self.variants["full_text"]["over_32000_proxy_tokens"] += count > 32_000
        line["full_input_tokens_proxy"] = count

    def result(self) -> Json:
        n = self.totals["usable"]
        variants = {}
        for name, c in self.variants.items():
            variants[name] = {**dict(c), "mean_input_tokens_proxy": c["input_tokens_proxy"] / n if n else None,
                              "cost_scenarios": costs(c["input_tokens_proxy"], n)}
        return {"totals": dict(self.totals), "language_rows": dict(self.languages),
                "metadata_quality": {key: dict(c) for key, c in self.metadata_quality.items()},
                "provider_concept_type_rows": dict(self.concepts), "variants": variants,
                "lexical_signal_diagnostics": {v: {s: dict(c) for s, c in ss.items()} for v, ss in self.signals.items()},
                "lineage_hash": digest(self.rows), "rates": RATES,
                "tokenizer_limit": "Local proxy, not verified model tokenizer or billed token counts",
                "output_limit": "Assumed averages include all billed output; not measured generation or hard budget caps"}
