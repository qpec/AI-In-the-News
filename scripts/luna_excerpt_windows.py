"""Pure excerpt construction; production callers must enter Research.execute first.

Words are Unicode whitespace-delimited ``\\S+`` matches, not model tokens or
linguistic words. Paragraphs are separated by a blank line (LF, CRLF, or CR,
optionally containing whitespace). A single newline does not split a paragraph.
This is an explicit excerpt rule, not a change to stored passage segmentation.
No boilerplate detection, source normalization, or semantic inference occurs.
"""
from __future__ import annotations

import re
from typing import Literal, TypedDict


METHOD_VERSION = "exact-head-tail-whitespace-words-v1"
VARIANTS = ("word_windows", "paragraph_caps")
_WORDS = re.compile(r"\S+")
# Do not let regex backtracking interpret one CRLF as two separate line breaks.
_BREAK = r"(?:\r\n|(?<!\r)\n|\r(?!\n))"
_BLANK_LINE = re.compile(_BREAK + r"[^\S\r\n]*" + _BREAK)


class ExcerptSpan(TypedDict):
    span_id: str
    start: int
    end: int
    text: str


class Excerpt(TypedDict):
    method_version: str
    variant: str
    cap: int
    spans: list[ExcerptSpan]
    word_count: int
    visible_word_count: int
    omitted_word_count: int
    body_characters: int
    visible_characters: int
    paragraph_count: int
    has_body_text: bool
    all_nonwhitespace_body_covered: bool
    omitted_nonwhitespace_characters: int


def _trim_range(body: str, start: int, end: int) -> tuple[int, int]:
    while start < end and body[start].isspace():
        start += 1
    while end > start and body[end - 1].isspace():
        end -= 1
    return start, end


def paragraph_ranges(body: str) -> list[tuple[int, int]]:
    """Return exact nonblank paragraph offsets without changing source bytes."""
    if not isinstance(body, str):
        raise TypeError("body must be a Unicode string")
    output: list[tuple[int, int]] = []
    start = 0
    for separator in _BLANK_LINE.finditer(body):
        bounds = _trim_range(body, start, separator.start())
        if bounds[0] < bounds[1]:
            output.append(bounds)
        start = separator.end()
    bounds = _trim_range(body, start, len(body))
    if bounds[0] < bounds[1]:
        output.append(bounds)
    return output


def _merge_ranges(body: str, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlap and whitespace-only gaps, preserving one exact slice."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not merged:
            merged.append((start, end))
            continue
        old_start, old_end = merged[-1]
        if start <= old_end or not body[old_end:start].strip():
            merged[-1] = old_start, max(old_end, end)
        else:
            merged.append((start, end))
    return merged


def build_excerpt(
    body: str, variant: Literal["word_windows", "paragraph_caps"] | str, cap: int = 300,
) -> Excerpt:
    """Build deduplicated head/tail spans with exclusive Unicode end offsets.

    ``word_windows`` supplies the entire body once when it has at most 2*cap
    words; otherwise it supplies the first cap and last cap words. Title and
    metadata are outside this body budget and are not constructed here.

    ``paragraph_caps`` supplies the first cap words of the first nonblank
    paragraph and the last cap words of the last nonblank paragraph. Interior
    paragraphs remain omitted even if the body contains fewer than 2*cap words.
    Overlapping ranges and ranges separated only by whitespace merge. Every
    returned text remains one unchanged slice of the original Unicode body.

    For an empty/whitespace-only body, has_body_text is false and coverage of
    nonwhitespace characters is vacuously true. Coverage never implies usable
    evidence or a valid single-event article.
    """
    if not isinstance(body, str):
        raise TypeError("body must be a Unicode string")
    if variant not in VARIANTS:
        raise ValueError("unsupported excerpt variant")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError("cap must be a positive integer")

    words = list(_WORDS.finditer(body))
    paragraphs = paragraph_ranges(body)
    ranges: list[tuple[int, int]] = []
    if words and variant == "word_windows":
        if len(words) <= 2 * cap:
            ranges = [(0, len(body))]
        else:
            ranges = [(0, words[cap - 1].end()), (words[-cap].start(), len(body))]
    elif words:
        first_start, first_end = paragraphs[0]
        last_start, last_end = paragraphs[-1]
        first_words = list(_WORDS.finditer(body, first_start, first_end))
        last_words = list(_WORDS.finditer(body, last_start, last_end))
        ranges = [
            (first_start, first_words[min(cap, len(first_words)) - 1].end()),
            (last_words[max(0, len(last_words) - cap)].start(), last_end),
        ]
    ranges = _merge_ranges(body, ranges)
    spans: list[ExcerptSpan] = [
        {"span_id": f"body-{i + 1}", "start": start, "end": end, "text": body[start:end]}
        for i, (start, end) in enumerate(ranges)
    ]
    visible_words = sum(len(_WORDS.findall(span["text"])) for span in spans)
    all_nonwhitespace = sum(not c.isspace() for c in body)
    visible_nonwhitespace = sum(sum(not c.isspace() for c in span["text"]) for span in spans)
    omitted_nonwhitespace = all_nonwhitespace - visible_nonwhitespace
    return {
        "method_version": METHOD_VERSION,
        "variant": variant,
        "cap": cap,
        "spans": spans,
        "word_count": len(words),
        "visible_word_count": visible_words,
        "omitted_word_count": len(words) - visible_words,
        "body_characters": len(body),
        "visible_characters": sum(len(span["text"]) for span in spans),
        "paragraph_count": len(paragraphs),
        "has_body_text": bool(words),
        "all_nonwhitespace_body_covered": omitted_nonwhitespace == 0,
        "omitted_nonwhitespace_characters": omitted_nonwhitespace,
    }
