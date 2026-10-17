"""Synthetic excerpt invariants; no corpus processing or quality evaluation."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("luna_excerpt_windows",
    Path(__file__).resolve().parents[1] / "scripts/luna_excerpt_windows.py")
assert SPEC is not None and SPEC.loader is not None
windows = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(windows)


def words(count: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(count))


@pytest.mark.parametrize("variant", windows.VARIANTS)
@pytest.mark.parametrize("body", ["", " \t\r\n\r\n  ", "\u00a0\u2003"])
def test_empty_body_is_explicitly_unusable_despite_vacuous_coverage(variant, body):
    result = windows.build_excerpt(body, variant)
    assert result["spans"] == []
    assert result["has_body_text"] is False
    assert result["word_count"] == result["visible_word_count"] == result["paragraph_count"] == 0
    assert result["all_nonwhitespace_body_covered"] is True


@pytest.mark.parametrize("count", [1, 299, 300, 301, 599, 600])
def test_word_windows_short_body_retains_every_character_once(count):
    body = "  " + words(count) + "\r\n"
    result = windows.build_excerpt(body, "word_windows")
    assert result["spans"] == [{"span_id": "body-1", "start": 0, "end": len(body), "text": body}]
    assert result["visible_word_count"] == count
    assert result["all_nonwhitespace_body_covered"] is True


def test_word_windows_cap_excludes_middle_and_never_reconstructs_text():
    body = " " + words(601) + " \t"
    result = windows.build_excerpt(body, "word_windows")
    assert result["visible_word_count"] == 600
    assert result["omitted_word_count"] == 1
    assert result["spans"][0]["text"].endswith("w299")
    assert result["spans"][1]["text"].startswith("w301")
    assert result["all_nonwhitespace_body_covered"] is False
    for span in result["spans"]:
        assert body[span["start"]:span["end"]] == span["text"]


@pytest.mark.parametrize("count", [1, 299, 300, 301, 599, 600])
def test_same_paragraph_overlap_and_whitespace_adjacency_merge(count):
    body = words(count)
    result = windows.build_excerpt(body, "paragraph_caps")
    assert len(result["spans"]) == 1
    assert result["visible_word_count"] == count
    assert result["spans"][0]["text"] == body


def test_same_long_paragraph_keeps_first_and_last_words():
    body = words(1000)
    result = windows.build_excerpt(body, "paragraph_caps")
    assert result["visible_word_count"] == 600
    assert result["omitted_word_count"] == 400
    assert result["spans"][1]["text"] == words(1000).split("w699 ")[1]


@pytest.mark.parametrize("separator", ["\n\n", "\r\n\r\n", "\r\r", "\r\n \t\r\n", "\n\n\n"])
def test_paragraph_caps_omit_interior_paragraph_even_when_short(separator):
    body = f"first paragraph{separator}middle omitted{separator}last paragraph"
    result = windows.build_excerpt(body, "paragraph_caps")
    assert result["paragraph_count"] == 3
    assert [s["text"] for s in result["spans"]] == ["first paragraph", "last paragraph"]
    assert result["visible_word_count"] == 4
    assert result["omitted_word_count"] == 2
    assert result["all_nonwhitespace_body_covered"] is False
    assert windows.build_excerpt(body, "word_windows")["spans"][0]["text"] == body


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r"])
def test_single_line_break_is_not_a_blank_line(separator):
    body = f"first line{separator}second line{separator}last line"
    result = windows.build_excerpt(body, "paragraph_caps")
    assert result["paragraph_count"] == 1
    assert result["spans"][0]["text"] == body


def test_two_short_paragraphs_merge_across_only_whitespace():
    body = "  first\r\n\r\nsecond \t"
    result = windows.build_excerpt(body, "paragraph_caps")
    assert result["paragraph_count"] == 2
    assert result["spans"] == [{"span_id": "body-1", "start": 2, "end": 17, "text": "first\r\n\r\nsecond"}]
    assert result["all_nonwhitespace_body_covered"] is True


def test_last_paragraph_uses_suffix_not_prefix():
    body = "first\n\n" + words(5, "last")
    result = windows.build_excerpt(body, "paragraph_caps", cap=2)
    assert [s["text"] for s in result["spans"]] == ["first", "last3 last4"]


def test_unicode_offsets_are_codepoints_and_repeated_strings_remain_distinct():
    body = " 🌍 café\u00a0東京\n\nMIDDLE\n\n🌍 café\u00a0東京 "
    result = windows.build_excerpt(body, "paragraph_caps", cap=2)
    assert [s["text"] for s in result["spans"]] == ["🌍 café", "café\u00a0東京"]
    assert result["word_count"] == 7
    assert result["visible_word_count"] == 4
    assert result["spans"][1]["start"] == body.rindex("café")
    assert result["omitted_nonwhitespace_characters"] == len("東京MIDDLE🌍")
    for span in result["spans"]:
        assert body[span["start"]:span["end"]] == span["text"]


@pytest.mark.parametrize("variant", windows.VARIANTS)
def test_whitespace_token_rule_retains_hyphenated_identifiers_as_one_word(variant):
    body = "CVE-2026-12345\t€5.4m\u2003Acme-X"
    result = windows.build_excerpt(body, variant, cap=1)
    assert result["word_count"] == 3
    assert result["visible_word_count"] == 2


@pytest.mark.parametrize("cap", [0, -1, True, 1.5, "300", None])
def test_invalid_caps_fail_instead_of_silent_coercion(cap):
    with pytest.raises(ValueError, match="positive integer"):
        windows.build_excerpt("body", "word_windows", cap=cap)


def test_nontext_and_unknown_variants_fail():
    with pytest.raises(TypeError, match="Unicode string"):
        windows.build_excerpt(None, "word_windows")
    with pytest.raises(ValueError, match="unsupported"):
        windows.build_excerpt("body", "unknown")


def test_deterministic_budget_and_exact_slice_invariants_over_synthetic_cases():
    for variant in windows.VARIANTS:
        for cap in [1, 2, 7, 300]:
            for sizes in [(1,), (601,), (4, 5), (301, 100, 302), (0, 7, 0), (2, 3, 1, 4)]:
                body = "\r\n \r\n".join(words(n, f"p{i}-") for i, n in enumerate(sizes))
                result = windows.build_excerpt(body, variant, cap)
                assert result == windows.build_excerpt(body, variant, cap)
                assert result["visible_word_count"] <= min(result["word_count"], cap * 2)
                assert result["word_count"] == result["visible_word_count"] + result["omitted_word_count"]
                assert result["all_nonwhitespace_body_covered"] == (result["omitted_word_count"] == 0)
                previous_end = -1
                for span in result["spans"]:
                    assert previous_end < span["start"] < span["end"]
                    assert span["text"] == body[span["start"]:span["end"]]
                    previous_end = span["end"]
