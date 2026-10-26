"""Synthetic separate-owner, accounting and source-preservation integration tests."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import hashlib
import zipfile
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, ResearchError, digest
from newsresearch.runtime import Research, audited_handler
from newsresearch.gateway import ProviderResponse
import test_luna_incident_screening as fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_screening as adapter  # noqa: E402
import screening_contract as core  # noqa: E402


def response(scope="single_event", crime="yes", nexus="direct"):
    return {"model": "gpt-6-luna", "answers": [
        {"name": name, "type": "choice", "choice": choice, "confidence": .8,
         "probabilities": [{"value": label, "probability": .7 if label == choice else .3 / (len(labels) - 1)} for label in labels]}
        for (name, labels), choice in zip(core.LABELS.items(), (scope, crime, nexus), strict=True)]}


class Fake:
    calls = []
    mode = "valid"

    def complete_prepared(self, invocation):
        self.calls.append(invocation)
        assert "cybercrime" in json.loads(invocation.request["input"])["body"]
        if self.mode == "unknown":
            return ProviderResponse(None, "openai-decisions", None, raw_response={"unknown_outcome": True})
        payload = response()
        if self.mode == "invalid":
            payload["answers"].reverse()
        return ProviderResponse(payload, "openai-decisions", "gpt-6-luna", usage={"input_tokens": 1000}, raw_response={"http_status": 200})


class SyntheticPreparation(Research):
    @audited_handler
    def _status(self, session, context, data):
        if data.get("sealed") is not None:
            ref = self.ledger.artifacts.put({"sealed_body_hashes": data["sealed"]})
            self.ledger.record(session, "luna_batch_eligibility_export", "fixture", {"export": ref})
            return {}
        source = adapter.base.pilot.Source(data["standard"])
        try:
            original = source.one("luna_standard_plan")
            descriptors = source.artifacts.json(original["queues"]["cybercrime"])
            partition = original["corpora"]["cybercrime"]["partition"]
        finally:
            source.close()
        if data.get("alias"):
            # Different source/date metadata, identical exact title/body model input.
            original_path = Path(partition["resolved_root"]) / partition["manifest"]["bundles"][0]["path"]
            with zipfile.ZipFile(original_path) as archive:
                contents = [json.loads(line) for line in archive.read("artikelen.jsonl").splitlines()]
            contents[-1]["article"]["title"] = contents[0]["article"]["title"]
            contents[-1]["article"]["body"] = contents[0]["article"]["body"]
            contents[-1]["article"]["date"] = "2026-02-01"
            raw_rows = [(json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8") for row in contents]
            archive_root = self.ledger.root / "source-fixture"
            archive_root.mkdir()
            path = archive_root / "cybercrime.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("artikelen.jsonl", b"".join(raw_rows))
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            partition = {"corpus_id": "cybercrime", "resolved_root": str(archive_root),
                         "manifest": {"bundles": [{"path": path.name, "sha256": sha}]}, "manifest_sha256": digest([sha])}
            descriptors = []
            snapshot = adapter.base.pilot.materializer.core.load_contract_snapshot()
            for number, (raw, row) in enumerate(zip(raw_rows, contents, strict=True), 1):
                article = row["article"]
                normalized, availability = adapter.base.pilot.materializer.materialize.normalize_context(article)
                locator = {"archive_path": path.name, "archive_sha256": sha, "stream": "artikelen.jsonl", "line": number,
                           "row_bytes_sha256": hashlib.sha256(raw).hexdigest()}
                record = adapter.base.pilot.materializer.core.build_request_record(normalized, corpus_id="cybercrime",
                    manifest_sha256=partition["manifest_sha256"], source_locator=locator, source_sha256=digest(article),
                    count_tokens=len, token_proxy_method="cl100k_base_serialized_body_plus_32",
                    context_availability=availability, contract_snapshot=snapshot)
                descriptors.append(record["descriptor"])
        partition["manifest"]["summary"] = {"bundles": 1, "declared_article_records": len(descriptors)}
        partition["registry_sha256"] = digest(["synthetic registry"])
        rows = [{"id": digest([d["custom_id"]]), "corpus_id": "cybercrime", "source_locator": d["source_locator"],
                 "descriptor": d, "state": "ready"} for d in descriptors]
        snapshot = adapter.base.pilot.materializer.core.load_contract_snapshot()
        binding = {"partition": partition, "contract_sha256": snapshot.contract_sha256,
                   "model": "gpt-6-luna", "max_output_tokens": 4096, "reasoning_effort": "none"}
        chunks = [{"artifact": self.ledger.artifacts.put({"rows": rows}), "rows": len(rows),
                   "archive_path": rows[0]["source_locator"]["archive_path"]}]
        shard = self.ledger.artifacts.put({"synthetic": True})
        manifest = {"corpus_id": "cybercrime", "manifest_sha256": partition["manifest_sha256"],
                    "binding_sha256": digest(binding), "versions": {}, "descriptor_chunks": chunks,
                    "shard_plan_artifact": shard, "prospective_request_count": len(rows)}
        result = {"corpus_id": "cybercrime", "binding": binding, "binding_sha256": digest(binding),
                  "manifest_artifact": self.ledger.artifacts.put(manifest), "versions": {},
                  "shard_plan_artifact": shard, "totals": {"requests": len(rows), "rows": len(rows)}}
        self._version(session, context, {"kind": "note", "key": "fixture", "content": result})
        return {"hashes": [d["retained_body_sha256"] for d in descriptors]}


def prepare(tmp_path, monkeypatch, sealed=False, alias=False):
    fixture.parents(tmp_path)
    parent_path = tmp_path / "parent"
    old = SyntheticPreparation(parent_path, config=Config(offline=True))
    try:
        prepared_source = fixture.call(old, "seed", standard=str(tmp_path / adapter.base.pilot.STANDARD), alias=alias)
    finally:
        old.close()
    seal = SyntheticPreparation(tmp_path / "sealed", config=Config(offline=True))
    try:
        fixture.call(seal, "seed", sealed=prepared_source["hashes"][:1] if sealed else [])
    finally:
        seal.close()
    Fake.calls, Fake.mode = [], "valid"
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    monkeypatch.setattr(adapter.paced, "ORIGINAL_TRANSPORT", Fake)
    monkeypatch.setattr(adapter.paced.Pacer, "acquire", lambda self, request: 1000)
    monkeypatch.setattr(adapter, "OPERATIONAL_COUNT", 2)
    study = adapter.Study(tmp_path / "cyber", config=Config(offline=False))
    prepared = fixture.call(study, "prepare", parent=str(parent_path), sealed_owner=str(tmp_path / "sealed"))
    return study, prepared


def test_full_input_independent_axes_refusals_and_cost_bounds():
    body = "Every retained character ÃƒÂ© Ã°Å¸Ëœâ‚¬.\r\n" * 3000
    request = core.request_for("Fictional title", body)
    assert json.loads(request["input"]) == {"title": "Fictional title", "body": body}
    assert request["prompt_cache_options"] == {"mode": "explicit"}
    for scope in core.LABELS["event_scope"]:
        for crime in core.LABELS["cybercrime_incident"]:
            for nexus in core.LABELS["netherlands_nexus"]:
                value = core.parse_response(response(scope, crime, nexus))
                expected = "exclude" if scope in {"multiple_events", "no_event"} or crime == "no" or nexus in {"other_only", "none"} else (
                    "keep" if (scope, crime, nexus) == ("single_event", "yes", "direct") else "review")
                assert value["route"] == expected
    refused = response(crime="no")
    refused["answers"][2] = {"name": "netherlands_nexus", "type": "refusal"}
    assert core.parse_response(refused)["route"] == "review"
    for mutate in (lambda p: p["answers"].reverse(), lambda p: p["answers"][0].update(confidence=float("nan")),
                   lambda p: p["answers"][1]["probabilities"][0].update(probability=True)):
        bad = deepcopy(response())
        mutate(bad)
        with pytest.raises(ResearchError):
            core.parse_response(bad)
    assert core.observed_cost({"input_tokens": 1000}) == 110_000
    assert core.observed_cost({"input_tokens": 1_050_000, "input_tokens_details": {"cache_write_tokens": 1_050_000}}) == 577_500_000
    assert core.observed_cost({"input_tokens": 1_050_001}) is None
    assert core.observed_cost({"input_tokens": 1000, "input_tokens_details": {"cache_write_tokens": -1}}) is None
    assert core.RESERVATION_NANOUSD > 577_500_000


def test_separate_frame_operational_gate_and_no_retries(tmp_path, monkeypatch):
    study, prepared = prepare(tmp_path, monkeypatch)
    try:
        assert prepared["selected_articles"] == 4 and prepared["dispositions"] == {"ready": 4}
        assert prepared["budget_usd"] == 20 and not Fake.calls
        plan = study.one("cyber_screen_plan")
        assert all(t["corpus"] == "cybercrime" and t["request"]["questions"] == core.QUESTIONS for t in study.tasks(plan))
        with pytest.raises(AuditError, match="one_record"):
            fixture.call(study, "run", allow_paid_execution=True)
        check = fixture.call(study, "operational", allow_paid_execution=True)
        assert check["new_responses"] == 2 and check["labels"]["routes"] == {"keep": 2}
        assert check["total_budget_committed_usd"] == .00022
        first_deadline = study.rows("cyber_screen_launch")[0]["expires_at"]
        fixture.call(study, "approve-operational")
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert result["dispatch_complete"] and result["all_outcomes_resolved"] and len(Fake.calls) == 4
        assert result["total_budget_committed_usd"] == .00044
        assert all(r["expires_at"] == first_deadline for r in study.rows("cyber_screen_launch"))
        exported = [json.loads(x) for x in (study.ledger.root / "article-decisions.jsonl").read_text().splitlines()]
        assert len(exported) == 4 and all(x["corpus"] == "cybercrime" for x in exported)
        assert all("body" not in x and "title" not in x for x in exported)
        assert (tmp_path / adapter.base.pilot.STANDARD / "STOP").exists()
    finally:
        study.close()
    study = adapter.Study(tmp_path / "cyber", config=Config(offline=False))
    try:
        fixture.call(study, "run", allow_paid_execution=True)
        assert len(Fake.calls) == 4
    finally:
        study.close()


@pytest.mark.parametrize("mode", ["unknown", "invalid"])
def test_bad_operational_response_blocks_gate_and_keeps_holds(tmp_path, monkeypatch, mode):
    study, _ = prepare(tmp_path, monkeypatch)
    Fake.mode = mode
    try:
        result = fixture.call(study, "operational", allow_paid_execution=True)
        assert result["new_responses"] == 2 and not result["labels"]["valid_articles"]
        assert result["run_end"][-1]["stop_reason"] == "operational_failure"
        assert result["held_reservations_usd"] == (1.2 if mode == "unknown" else 0)
        with pytest.raises(AuditError, match="gate_not_clean"):
            fixture.call(study, "approve-operational")
        fixture.call(study, "operational", allow_paid_execution=True)
        assert len(Fake.calls) == 2
    finally:
        study.close()


def test_budget_stop_deadline_and_implementation_fail_closed(tmp_path, monkeypatch):
    study, _ = prepare(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(adapter, "CAP", 1)
        result = fixture.call(study, "operational", allow_paid_execution=True)
        assert result["run_end"][-1]["stop_reason"] == "budget_bound" and not Fake.calls
        monkeypatch.setattr(adapter, "CAP", 20_000_000_000)
        deadline = study.rows("cyber_screen_launch")[0]["expires_at"]
        class ExpiredClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromisoformat(deadline) + timedelta(seconds=1)
        monkeypatch.setattr(adapter, "datetime", ExpiredClock)
        with pytest.raises(AuditError, match="stopped_or_expired"):
            fixture.call(study, "operational", allow_paid_execution=True)
        monkeypatch.setattr(adapter, "datetime", datetime)
        (study.ledger.root / "STOP").write_text("Synthetic stop", encoding="utf-8")
        with pytest.raises(AuditError, match="stopped_or_expired"):
            fixture.call(study, "operational", allow_paid_execution=True)
        monkeypatch.setattr(adapter, "implementation", lambda: {"changed": "hash"})
        with pytest.raises(AuditError, match="implementation_changed"):
            fixture.call(study, "report")
        assert not Fake.calls
    finally:
        study.close()


def test_sealed_frame_stays_unprocessed_and_archive_tamper_blocks_new_preparation(tmp_path, monkeypatch):
    study, prepared = prepare(tmp_path, monkeypatch, sealed=True)
    try:
        assert prepared["selected_articles"] == 4
        assert prepared["dispositions"] == {"sealed_validation": 1, "ready": 3}
        with pytest.raises(AuditError, match="explicit_online"):
            fixture.call(study, "operational", allow_paid_execution=False)
        fixture.call(study, "operational", allow_paid_execution=True)
        fixture.call(study, "approve-operational")
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert len(Fake.calls) == 3 and result["coverage"] == {"valid": 3, "sealed_validation": 1}
        assert result["dispatch_complete"] and result["selected_articles"] == 4
        assert (tmp_path / adapter.base.pilot.STANDARD / "STOP").is_file()
    finally:
        study.close()
    archive = tmp_path / adapter.base.pilot.STANDARD / "synthetic-archives/cybercrime.zip"
    archive.write_bytes(archive.read_bytes() + b"synthetic archive tamper")
    study = adapter.Study(tmp_path / "blocked", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="archive_hash_mismatch"):
            fixture.call(study, "prepare", parent=str(tmp_path / "parent"), sealed_owner=str(tmp_path / "sealed"))
        assert len(Fake.calls) == 3
    finally:
        study.close()


def test_exact_input_alias_reuses_only_new_study_response(tmp_path, monkeypatch):
    study, prepared = prepare(tmp_path, monkeypatch, alias=True)
    try:
        assert prepared["selected_articles"] == 4
        assert prepared["dispositions"] == {"ready": 3, "exact_input_alias": 1}
        fixture.call(study, "operational", allow_paid_execution=True)
        fixture.call(study, "approve-operational")
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert len(Fake.calls) == result["new_responses"] == 3
        assert result["coverage"] == {"valid": 4}
        assert result["labels"]["valid_articles"] == 3
        assert result["article_labels_including_exact_input_aliases"]["valid_articles"] == 4
        exported = [json.loads(x) for x in (study.ledger.root / "article-decisions.jsonl").read_text().splitlines()]
        alias = next(r for r in exported if r["exact_input_reuse"])
        original = next(r for r in exported if r["custom_id"] == alias["canonical_custom_id"])
        assert original["request_hash"] == alias["request_hash"]
        assert original["record_id"] == alias["record_id"]
        assert original["custom_id"] != alias["custom_id"]
        assert original["source_locator"] != alias["source_locator"]
    finally:
        study.close()
