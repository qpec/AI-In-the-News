"""Synthetic scheduling/format checks; no corpus reads or model requests."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import luna_multibatch as batch
finally:
    sys.path.pop(0)


def request(**changes):
    kwargs = {
        "article": {"title": "Fictional café launch 🐈", "body": "City launched Café.\r\n\r\nFull 尾 text.\n",
                    "lang": "eng", "dateTimePub": "2026-10-17T09:00:00Z",
                    "source": {"uri": "fictional.example", "title": "Fictional Gazette"}},
        "corpus_id": "incident-reports", "manifest_sha256": "a" * 64,
        "source_locator": {"archive_path": "fictional.zip", "row_index": 7, "row_sha256": "c" * 64},
        "source_sha256": "b" * 64, "count_tokens": lambda text: len(text),
        "token_proxy_method": "synthetic_character_count_plus_32",
    }
    kwargs.update(changes)
    return batch.build_request_record(**kwargs)


def descriptor(custom_id, corpus="incident-reports", *, line_bytes=10, tokens=10, manifest="a" * 64):
    return {"custom_id": custom_id, "corpus_id": corpus, "manifest_sha256": manifest,
            "line_bytes": line_bytes, "input_tokens_proxy": tokens, "model": batch.MODEL}


def shard(shard_id, corpus="incident-reports", tokens=10, state="READY"):
    return {"shard_id": shard_id, "corpus_id": corpus, "input_tokens_proxy": tokens,
            "model": batch.MODEL, "state": state}


def completed(custom_id, text='{"focus":"none"}'):
    return {"custom_id": custom_id, "error": None,
            "response": {"status_code": 200, "request_id": "synthetic-request",
                         "body": {"id": "synthetic-response", "model": batch.MODEL, "status": "completed",
                                  "usage": {"input_tokens": 123, "output_tokens": 12},
                                  "output": [{"type": "message", "status": "completed", "content": [
                                      {"type": "output_text", "text": text}]}]}}}


def test_full_retained_request_has_exact_prompt_once_and_one_article():
    built = request()
    row = built["request"]
    body = row["body"]
    assert row["method"] == "POST" and row["url"] == "/v1/responses"
    assert body["model"] == "gpt-6-luna"
    assert body["reasoning"] == {"effort": "none"}
    assert body["store"] is False and body["max_output_tokens"] == 4096
    assert "tools" not in body and "stream" not in body
    assert body["instructions"] == batch.contract.load_prompt()
    assert len(body["input"]) == len(body["input"][0]["content"]) == 1
    user_input = json.loads(body["input"][0]["content"][0]["text"])
    assert "instructions" not in user_input
    assert set(user_input) == set(built["packet"]["model_input"]) - {"instructions"}
    for key in user_input:
        assert user_input[key] == built["packet"]["model_input"][key]
    assert "".join(p["text"] for p in user_input["evidence"]["paragraphs"]) == "City launched Café.\r\n\r\nFull 尾 text.\n"
    assert body["text"]["format"] == {"type": "json_schema", "name": "luna_event_v2",
                                       "strict": True, "schema": batch.contract.load_schema()}
    assert batch.contract.validate_packet(built["packet"]) == []


def test_tokenizer_called_once_on_exact_body_and_missing_proxy_stays_unknown():
    inputs = []
    built = request(count_tokens=lambda value: inputs.append(value) or 200)
    assert inputs == [batch.canonical_json(built["request"]["body"])]
    assert built["descriptor"]["input_tokens_proxy"] == 232
    assert built["descriptor"]["input_tokens_exact"] is None
    assert built["descriptor"]["token_proxy_validated_for_luna"] is False
    unknown = request(count_tokens=None)
    assert unknown["descriptor"]["input_tokens_proxy"] is None
    assert unknown["descriptor"]["input_token_proxy_method"] is None
    [event] = batch.iter_shards([unknown["descriptor"]])
    assert event["state"] == "UNPLANNABLE"
    assert event["reasons"] == ["input_token_proxy_unavailable"]


def test_unicode_line_size_hash_and_final_newline_are_exact():
    built = request()
    line = built["jsonl_line"]
    assert line.endswith(b"\n") and not line.endswith(b"\r\n")
    assert line.count(b"\n") == 1
    assert "🐈".encode() in line and "尾".encode() in line
    assert built["descriptor"]["line_bytes"] == len(line) > len(line.decode("utf-8"))
    assert built["descriptor"]["line_sha256"] == hashlib.sha256(line).hexdigest()
    assert json.loads(line) == built["request"]
    assert built["descriptor"]["source_map_sha256"] == built["packet"]["source_map"]["sha256"]
    assert built["descriptor"]["request_sha256"] == hashlib.sha256(line[:-1]).hexdigest()
    assert built["descriptor"]["request_body_sha256"] == hashlib.sha256(
        batch.canonical_json(built["request"]["body"]).encode("utf-8")).hexdigest()


def test_context_availability_is_allowlisted_and_bound_into_exact_input():
    states = {"title": "absent", "dateTimePub": "nontext", "source": "nonobject", "source.title": "absent"}
    built = request(context_availability=states)
    actual = json.loads(built["request"]["body"]["input"][0]["content"][0]["text"])
    assert actual["context"]["availability"] == states
    assert built["descriptor"]["context_availability"] == states
    assert built["request"]["custom_id"] != request()["request"]["custom_id"]
    assert batch.contract.validate_packet(built["packet"]) == []
    with pytest.raises(ValueError, match="context_availability"):
        request(context_availability={"source.title": "unrestricted source text"})
    with pytest.raises(ValueError, match="context_availability"):
        request(context_availability={"unknown_context": "available"})


def test_explicit_immutable_snapshot_is_byte_equivalent_without_repeated_file_reads(monkeypatch):
    default = request()
    snapshot = batch.load_contract_snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.prompt = "changed"
    def forbidden():
        raise AssertionError("contract file was reread")
    monkeypatch.setattr(batch.contract, "load_prompt", forbidden)
    monkeypatch.setattr(batch.contract, "load_schema", forbidden)
    monkeypatch.setattr(batch, "contract_digest", forbidden)
    frozen = request(contract_snapshot=snapshot)
    assert frozen["jsonl_line"] == default["jsonl_line"]
    assert frozen["descriptor"] == default["descriptor"]
    assert frozen["packet"] == default["packet"]
    # Each returned object has independent mutable schema/codebook containers.
    frozen["request"]["body"]["text"]["format"]["schema"]["synthetic_mutation"] = True
    assert "synthetic_mutation" not in request(contract_snapshot=snapshot)["request"]["body"]["text"]["format"]["schema"]


@pytest.mark.parametrize("changes", [
    {"corpus_id": "cybercrime"}, {"manifest_sha256": "d" * 64},
    {"source_sha256": "e" * 64}, {"source_locator": {"archive_path": "fictional.zip", "row_index": 8}},
    {"max_output_tokens": 2048}, {"article": {"title": "Different", "body": "A different complete article."}},
])
def test_custom_ids_bind_partition_source_parameters_and_exact_request(changes):
    original = request()
    assert request()["jsonl_line"] == original["jsonl_line"]
    assert request(**changes)["request"]["custom_id"] != original["request"]["custom_id"]


def test_custom_id_binds_contract_digest_and_canonicalizes_locator_key_order(monkeypatch):
    original = request()
    assert request(source_locator={"row_sha256": "c" * 64, "row_index": 7,
                                   "archive_path": "fictional.zip"})["jsonl_line"] == original["jsonl_line"]
    monkeypatch.setattr(batch, "contract_digest", lambda: "f" * 64)
    assert request()["request"]["custom_id"] != original["request"]["custom_id"]


def test_build_does_not_mutate_supplied_article_or_locator_and_rejects_missing_body():
    article = {"title": "Fictional", "body": "Full text.", "source": {"title": "Fictional publisher"}}
    locator = {"archive": "fictional.zip", "row": 1}
    article_before, locator_before = deepcopy(article), deepcopy(locator)
    request(article=article, source_locator=locator)
    assert article == article_before and locator == locator_before
    with pytest.raises(ValueError, match="unavailable"):
        request(article={"title": "Fictional", "body": "\n "})


def test_streaming_packer_is_partitioned_by_corpus_and_manifest_and_deterministic():
    rows = [descriptor("i1"), descriptor("c1", "cybercrime"), descriptor("i2"),
            descriptor("c2", "cybercrime"), descriptor("new", manifest="b" * 64)]
    planned = list(batch.iter_shards(iter(rows), batch.ShardLimits(max_requests=2)))
    assert planned == list(batch.iter_shards(iter(rows), batch.ShardLimits(max_requests=2)))
    assert sum(item["request_count"] for item in planned) == 5
    assert len(planned) == 3
    for item in planned:
        assert item["state"] == "READY"
        assert {(row["corpus_id"], row["manifest_sha256"]) for row in item["records"]} == {
            (item["corpus_id"], item["manifest_sha256"])}
    assert [r["custom_id"] for r in planned[0]["records"]] == ["i1", "i2"]


@pytest.mark.parametrize("limits,rows", [
    (batch.ShardLimits(max_requests=2), [descriptor(str(i)) for i in range(3)]),
    (batch.ShardLimits(max_bytes=20), [descriptor(str(i), line_bytes=10) for i in range(3)]),
    (batch.ShardLimits(target_input_tokens=20), [descriptor(str(i), tokens=10) for i in range(3)]),
])
def test_shard_operational_limits_allow_exact_boundary_and_split_next(limits, rows):
    planned = list(batch.iter_shards(rows, limits))
    assert [item["request_count"] for item in planned] == [2, 1]
    for item in planned:
        assert item["line_bytes"] <= limits.max_bytes
        assert item["input_tokens_proxy"] <= limits.target_input_tokens


def test_provider_byte_and_request_ceilings_are_enforced_without_large_allocation():
    max_bytes = batch.PROVIDER_BYTE_CEILING_EXCLUSIVE - 1
    limits = batch.ShardLimits(max_requests=50_000, max_bytes=max_bytes, target_input_tokens=100_000)
    [at_limit] = batch.iter_shards([descriptor("one", line_bytes=max_bytes)], limits)
    assert at_limit["state"] == "READY" and at_limit["line_bytes"] == 199_999_999
    [too_large] = batch.iter_shards([descriptor("one", line_bytes=max_bytes + 1)], limits)
    assert too_large["state"] == "OVERSIZED"
    planned = list(batch.iter_shards((descriptor(str(i), line_bytes=1, tokens=1)
                                     for i in range(50_001)), limits))
    assert [item["request_count"] for item in planned] == [50_000, 1]
    with pytest.raises(ValueError, match="provider_ceiling"):
        batch.ShardLimits(max_requests=50_001)
    with pytest.raises(ValueError, match="provider_ceiling"):
        batch.ShardLimits(max_bytes=200_000_000)


def test_oversized_row_is_explicit_unmodified_and_other_rows_still_pack():
    large = descriptor("large", line_bytes=30, tokens=30)
    limits = batch.ShardLimits(max_bytes=20, target_input_tokens=20)
    planned = list(batch.iter_shards([descriptor("good"), large, descriptor("good2")], limits))
    assert planned[0]["state"] == "OVERSIZED"
    assert planned[0]["record"] == large
    assert planned[0]["reasons"] == ["record_exceeds_shard_byte_limit", "record_exceeds_shard_token_proxy_target"]
    assert planned[1]["request_count"] == 2
    assert large["line_bytes"] == large["input_tokens_proxy"] == 30


def test_stream_packer_yields_before_exhausting_input_and_rejects_duplicate_ids():
    consumed = []
    def rows():
        for i in range(100):
            consumed.append(i)
            yield descriptor(str(i))
    generator = batch.iter_shards(rows(), batch.ShardLimits(max_requests=2))
    assert next(generator)["request_count"] == 2
    assert consumed == [0, 1, 2]
    with pytest.raises(ValueError, match="duplicate_request_custom_id"):
        list(batch.iter_shards([descriptor("duplicate"), descriptor("duplicate", "cybercrime")]))


def test_adaptive_targets_and_decimal_reservations_are_explicit_proxies():
    assert batch.adaptive_shard_token_target(None) == 2_000_000
    assert batch.adaptive_shard_token_target(10_000_000) == 1_000_000
    assert batch.adaptive_shard_token_target(300_000_000) == 10_000_000
    assert batch.adaptive_shard_token_target(0) == 0
    assert batch.reserved_input_tokens(3, 1.1) == 4
    assert batch.reserved_input_tokens(100, 1.1) == 110
    for invalid in (0.99, float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="reserve_multiplier"):
            batch.reserved_input_tokens(1, invalid)


def test_scheduler_accounts_for_both_corpora_cushion_and_configured_remote_slots():
    ready = [shard("i2"), shard("i1"), shard("c1", "cybercrime"), shard("c2", "cybercrime")]
    result = batch.schedule_ready_shards(ready, queue_token_allowance=100,
        existing_inflight=[{"shard_id": "old-i", "corpus_id": "incident-reports", "reserved_input_tokens": 15},
                           {"shard_id": "old-c", "corpus_id": "cybercrime", "reserved_input_tokens": 20}],
        queue_cushion_tokens=5, max_active_remote_jobs=5)
    assert result["existing_inflight_reserved_tokens"] == 35
    assert result["available_before_selection"] == 60
    assert [s["shard_id"] for s in result["selected"]] == ["c1", "i1", "c2"]
    assert result["selected_reserved_tokens"] == 39
    assert result["remaining_queue_tokens"] == 21
    assert result["blocked"] == [{"shard_id": "i2", "corpus_id": "incident-reports",
                                  "reserved_input_tokens": 13, "reason": "remote_job_slots_exhausted"}]
    assert result["provider_limit_verified"] is False


def test_scheduler_has_no_implicit_four_remote_job_limit_and_fills_capacity_fairly():
    ready = [shard(f"i{i}", tokens=10) for i in range(6)] + [shard(f"c{i}", "cybercrime", 10) for i in range(6)]
    result = batch.schedule_ready_shards(reversed(ready), queue_token_allowance=104)
    assert len(result["selected"]) == 8
    assert [s["corpus_id"] for s in result["selected"]] == ["cybercrime", "incident-reports"] * 4
    assert result["remaining_queue_tokens"] == 0
    assert result == batch.schedule_ready_shards(ready, queue_token_allowance=104)
    rotated = batch.schedule_ready_shards(ready, queue_token_allowance=13, last_dispatched_corpus_id="cybercrime")
    assert rotated["selected"][0]["corpus_id"] == "incident-reports"


def test_scheduler_skips_too_large_shards_and_never_exceeds_remaining_capacity():
    result = batch.schedule_ready_shards([shard("a-large", tokens=100), shard("b-small", tokens=5),
                                         shard("c-small", "cybercrime", 3)], queue_token_allowance=10)
    assert [s["shard_id"] for s in result["selected"]] == ["c-small"]
    assert result["remaining_queue_tokens"] == 6  # ceil(5 * 1.25) = 7, so it cannot fit.
    result = batch.schedule_ready_shards([shard("a-large", tokens=100), shard("b-small", tokens=5)],
                                         queue_token_allowance=7)
    assert [s["shard_id"] for s in result["selected"]] == ["b-small"]


@pytest.mark.parametrize("allowance,inflight,reason", [
    (None, [], "queue_token_allowance_unknown"),
    (100, [{"shard_id": "unknown"}], "inflight_token_reservation_unknown"),
])
def test_scheduler_fails_closed_on_unknown_capacity_or_unknown_spent_reservation(allowance, inflight, reason):
    result = batch.schedule_ready_shards([shard("one")], queue_token_allowance=allowance, existing_inflight=inflight)
    assert result["state"] == "BLOCKED" and result["selected"] == []
    assert result["blocked"][0]["reason"] == reason
    assert result["remaining_queue_tokens"] is None


def test_scheduler_keeps_unknown_proxy_and_not_ready_separate_and_rejects_double_dispatch():
    result = batch.schedule_ready_shards([shard("unknown", tokens=None), shard("valid"),
                                         shard("busy", state="INFLIGHT")], queue_token_allowance=20)
    assert [s["shard_id"] for s in result["selected"]] == ["valid"]
    assert result["blocked"][0]["reason"] == "input_token_proxy_unavailable"
    assert result["ignored"] == [{"shard_id": "busy", "state": "INFLIGHT", "reason": "not_ready"}]
    with pytest.raises(ValueError, match="also_supplied"):
        batch.schedule_ready_shards([shard("busy")], queue_token_allowance=100,
                                    existing_inflight=[{"shard_id": "busy", "reserved_input_tokens": 5}])


def test_unordered_outputs_join_by_id_with_missing_errors_duplicates_and_foreign_preserved():
    expected = [descriptor(name) for name in ("a", "b", "c", "d", "e")]
    error = {"custom_id": "c", "error": {"code": "synthetic_error"}, "response": None}
    incomplete = completed("d")
    incomplete["response"]["body"].update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    rows = [completed("e"), completed("foreign"), incomplete, completed("a"), error, completed("e"), {"response": None}]
    result = batch.reconcile_outputs(expected, rows)
    assert result["expected_count"] == 5 and result["observed_row_count"] == 7
    assert [row["state"] for row in result["results"]] == ["CANDIDATE", "MISSING", "ERROR", "INCOMPLETE", "DUPLICATE"]
    assert [row["custom_id"] for row in result["candidates"]] == ["a"]
    assert result["foreign"][0]["custom_id"] == "foreign"
    assert len(result["malformed"]) == 1 and result["accepted_count"] == 0
    for row in result["results"]:
        assert row["accepted"] is False and row["validation_required"] is True
        if row["state"] != "CANDIDATE":
            assert row["parsed_output"] is None
    candidate = result["candidates"][0]
    assert candidate["parsed_output"] == {"focus": "none"}
    # Syntactic extraction is not the original event contract's validation.
    assert candidate["reason"] == "requires_contract_and_gateway_validation"
    assert candidate["usage"] == {"input_tokens": 123, "output_tokens": 12}


@pytest.mark.parametrize("text", ["{", '{"focus":"none","focus":"single"}', '{"value":NaN}', "```json\n{}\n```"])
def test_truncated_duplicate_key_nonfinite_or_fenced_json_is_not_candidate(text):
    result = batch.reconcile_outputs([descriptor("one")], [completed("one", text)])
    assert result["counts"]["INVALID_JSON"] == 1 and result["candidates"] == []


@pytest.mark.parametrize("mutation,state,reason", [
    (lambda row: row["response"].update(status_code=429), "ERROR", "response_missing_or_non_200"),
    (lambda row: row["response"]["body"].pop("status"), "INCOMPLETE", "response_not_completed"),
    (lambda row: row["response"]["body"].update(model="other-model"), "ERROR", "response_model_mismatch"),
    (lambda row: row["response"]["body"].update(incomplete_details={"reason": "max_output_tokens"}),
     "INCOMPLETE", "response_not_completed"),
    (lambda row: row["response"]["body"]["output"][0].update(status="incomplete"),
     "INCOMPLETE", "response_message_not_completed"),
    (lambda row: row["response"]["body"]["output"][0].update(content=[{"type": "refusal", "refusal": "Synthetic"}]),
     "REFUSAL", "response_refusal"),
    (lambda row: row["response"]["body"].update(output=[{"type": "function_call"}]),
     "ERROR", "unexpected_response_output_type"),
])
def test_response_failures_never_become_successful_or_negative_findings(mutation, state, reason):
    row = completed("one")
    mutation(row)
    result = batch.reconcile_outputs([descriptor("one")], [row])
    assert result["candidates"] == []
    assert result["results"][0]["state"] == state
    assert result["results"][0]["reason"] == reason
    assert result["results"][0]["parsed_output"] is None


def test_unavailable_observability_stays_null_and_no_contract_validation_is_claimed():
    row = completed("one", "null")
    for name in ("model", "usage", "id"):
        row["response"]["body"].pop(name)
    row["response"].pop("request_id")
    result = batch.reconcile_outputs([descriptor("one")], [row])
    candidate = result["candidates"][0]
    assert candidate["parsed_output"] is None
    assert candidate["state"] == "CANDIDATE" and candidate["accepted"] is False
    assert all(candidate[name] is None for name in ("observed_model", "usage", "response_id", "request_id"))
    with pytest.raises(ValueError, match="duplicate_expected_custom_id"):
        batch.reconcile_outputs([descriptor("same"), descriptor("same")], [])
