"""Synthetic evidence and audited pilot lifecycle checks; no real model calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

from newsresearch import luna_incident_screening as core
from newsresearch.common import AuditError, Config, ResearchError, digest
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench"))
import run_luna_incident_screening as adapter  # noqa: E402


def response(scope="single_event", incident="yes"):
    return {"model": "gpt-6-luna", "answers": [
        {"name": name, "type": "choice", "choice": choice, "confidence": .8,
         "probabilities": [{"value": label, "probability": .7 if label == choice else .3 / (len(labels) - 1)}
                           for label in labels]}
        for (name, labels), choice in zip(core.LABELS.items(), (scope, incident), strict=True)]}


def call(engine, action, **data):
    return engine.execute("status", {"action": action, **data}, objective="Verify synthetic incident screening workflow",
                          actor="test:synthetic")


def test_input_isolation_and_uncertainty_contract():
    body = "Fictional report.\r\n\r\nKeep every character é 😀.  "
    request = core.request("Fictional title", body)
    assert json.loads(request["input"]) == {"title": "Fictional title", "body": body}
    assert request["questions"] == core.QUESTIONS and len(request["questions"]) == 2
    for scope in core.LABELS["event_scope"]:
        for incident in core.LABELS["ai_incident"]:
            result = core.parse_response(response(scope, incident))
            expected = "exclude" if scope in {"multiple_events", "no_event"} or incident == "no" else (
                "keep" if scope == "single_event" and incident == "yes" else "review")
            assert result["route"] == expected
            assert result["probability_threshold"] is None and not result["human_validated"]
    value = response(incident="no")
    value["answers"][0] = {"name": "event_scope", "type": "refusal"}
    assert core.parse_response(value)["route"] == "review"
    assert core.describe([{"decision": None}])["valid_articles"] == 0
    with pytest.raises(ResearchError, match="byte_cap"):
        core.request("Fictional", "x" * 65000)
    with pytest.raises(ResearchError, match="body_unavailable"):
        core.request("Fictional", " ")
    with pytest.raises(ResearchError, match="Credential-like"):
        core.request("Fictional", "sk-" + "x" * 20)
    for mutate in (
        lambda v: v.update(model="different-model"),
        lambda v: v["answers"].reverse(),
        lambda v: v["answers"][0].update(confidence=float("nan")),
        lambda v: v["answers"][0]["probabilities"][0].update(probability=True),
        lambda v: v["answers"][0]["probabilities"][0].update(value="multiple_events"),
    ):
        value = response()
        mutate(value)
        with pytest.raises(ResearchError):
            core.parse_response(value)


def test_sampling_reproducibility_and_frame_identity():
    queues = {name: [{"corpus_id": name, "custom_id": name + str(i), "source_sha256": digest([name, i])}
                     for i in range(15)] for name in ("first", "second")}
    chosen = core.select_sample(queues, 12)
    assert chosen == core.select_sample({k: list(reversed(v)) for k, v in reversed(queues.items())}, 12)
    assert len({r["custom_id"] for r in chosen}) == 12
    for count in (0, 31, 1001, True):
        with pytest.raises(ResearchError):
            core.select_sample(queues, count)
    bad = deepcopy(queues)
    bad["first"].append(bad["first"][0])
    with pytest.raises(ResearchError, match="identity"):
        core.select_sample(bad, 12)


class SyntheticParent(Research):
    @audited_handler
    def _status(self, session, context, data):
        part = data["part"]
        if part in {"pilot", "comparison"}:
            kind, key = (("luna_matching_pilot_decision", "cost_nanousd_with_regional_margin") if part == "pilot"
                         else ("representation_decision", "cost_nanousd"))
            self.ledger.record(session, kind, "synthetic", {
                "unknown_or_billing_hold": False, "reserved_nanousd": 0, key: 100})
            return {}
        queues, corpora = {}, {}
        snapshot = adapter.materializer.core.load_contract_snapshot()
        archive_root = self.ledger.root / "synthetic-archives"
        archive_root.mkdir()
        for corpus in ("incident-reports", "cybercrime"):
            raw_rows, articles = [], []
            for number in range(1, 5):
                body = f"Fictional {corpus} event {number}.\r\n\r\nExact retained body é 😀.  "
                if data.get("oversized") and corpus == "cybercrime" and number == 4:
                    body += "x" * 65000
                article = {"uri": f"synthetic:{corpus}:{number}", "title": f"Fictional title {number}",
                           "body": body, "lang": "eng", "date": "2026-01-01",
                           "source": {"uri": "fictional.example"}}
                articles.append(article)
                raw_rows.append((json.dumps({"article": article}, ensure_ascii=False) + "\n").encode("utf-8"))
            path = archive_root / (corpus + ".zip")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("artikelen.jsonl", b"".join(raw_rows))
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_sha = digest([corpus, sha])
            partition = {"corpus_id": corpus, "resolved_root": str(archive_root), "manifest_sha256": manifest_sha,
                         "manifest": {"bundles": [{"path": path.name, "sha256": sha}]}}
            descriptors = []
            for number, (raw, article) in enumerate(zip(raw_rows, articles, strict=True), 1):
                locator = {"archive_path": path.name, "archive_sha256": sha, "stream": "artikelen.jsonl",
                           "line": number, "row_bytes_sha256": hashlib.sha256(raw).hexdigest()}
                normalized, availability = adapter.materializer.materialize.normalize_context(article)
                record = adapter.materializer.core.build_request_record(normalized, corpus_id=corpus,
                    manifest_sha256=manifest_sha, source_locator=locator, source_sha256=digest(article),
                    count_tokens=len, token_proxy_method="cl100k_base_serialized_body_plus_32",
                    context_availability=availability, contract_snapshot=snapshot)
                descriptors.append(record["descriptor"])
            queues[corpus] = self.ledger.artifacts.put(descriptors)
            corpora[corpus] = {"partition": partition}
        self.ledger.record(session, "luna_standard_plan", "synthetic", {"queues": queues, "corpora": corpora})
        (self.ledger.root / "STOP").write_text("Synthetic stopped owner", encoding="utf-8")
        return {}


def parents(tmp_path, oversized=False):
    for name, part in ((adapter.STANDARD, "standard"), (adapter.PILOT, "pilot"), (adapter.COMPARISON, "comparison")):
        parent = SyntheticParent(tmp_path / name, config=Config(offline=True))
        try:
            call(parent, "seed", part=part, oversized=oversized)
        finally:
            parent.close()


class Fake:
    calls = []
    mode = "valid"

    def complete_prepared(self, invocation):
        self.calls.append(invocation)
        if self.mode == "unknown":
            return ProviderResponse(None, "openai-decisions", None, raw_response={"unknown_outcome": True})
        payload = response()
        if self.mode == "invalid":
            payload["answers"][0]["probabilities"] = []
        if self.mode == "refusal":
            payload["answers"][1] = {"name": "ai_incident", "type": "refusal"}
        return ProviderResponse(payload, "openai-decisions", "gpt-6-luna",
            usage={"input_tokens": 1000}, raw_response={"http_status": 200})


@pytest.fixture
def fake(monkeypatch):
    Fake.calls, Fake.mode = [], "valid"
    monkeypatch.setattr(adapter.transport, "DecisionsTransport", Fake)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    return Fake


def test_full_registered_lifecycle_preserves_source_and_missingness(tmp_path, fake):
    parents(tmp_path, oversized=True)
    study = adapter.Study(tmp_path / "screen", config=Config(offline=False))
    try:
        plan = call(study, "prepare", base=str(tmp_path), count=8)
        assert plan["selected_articles"] == 8 and plan["planned_requests"] == 7
        assert plan["dispositions"] == {"ready": 7, "screen_request_exceeds_byte_cap": 1}
        assert plan["prior_cost_usd"] == 200 / 1e9 and not fake.calls
        frozen = study.one("incident_screen_plan")
        tasks = study.ledger.artifacts.read(frozen["manifest"])
        for task in tasks:
            if task["disposition"] != "ready":
                assert task["source"] is None and task["request"] is None
                continue
            source = study.ledger.artifacts.read(task["source"])
            evidence = json.loads(study.ledger.artifacts.read(task["request"])["input"])
            assert evidence["body"] == source["packet"]["source_map"]["source_fields"]["body"]["text"]
            assert set(evidence) == {"title", "body"}
        with pytest.raises(AuditError, match="explicit_online"):
            call(study, "run", allow_paid_execution=False)
        result = call(study, "run", allow_paid_execution=True)
        assert result["stored_responses"] == 7 and not study.ledger.unresolved
        with pytest.raises(AuditError, match="already_started_no_retry"):
            call(study, "run", allow_paid_execution=True)
        report = call(study, "report")
        assert report["dispatch_complete"] and not report["complete"]
        assert report["labels"]["routes"] == {"keep": 7, "exclude": 0, "review": 0}
        assert report["cost_usd_with_margin"] == pytest.approx(.00077)
        assert report["held_reservations_usd"] == 0 and not report["accuracy_measured"]
        assert sum(v["coverage"]["selected"] for v in report["by_corpus"].values()) == 8
        assert len(fake.calls) == 7
        assert study.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 7
    finally:
        study.close()


@pytest.mark.parametrize("mode,expected_calls,hold,refusals", [
    ("unknown", 1, .25, 0), ("invalid", 1, 0, 0), ("refusal", 4, 0, 4)])
def test_failure_or_refusal_never_becomes_negative_or_retry(tmp_path, fake, mode, expected_calls, hold, refusals):
    parents(tmp_path)
    study = adapter.Study(tmp_path / "screen", config=Config(offline=False))
    try:
        call(study, "prepare", base=str(tmp_path), count=4)
        fake.mode = mode
        call(study, "run", allow_paid_execution=True)
        report = call(study, "report")
        assert len(fake.calls) == expected_calls
        assert report["held_reservations_usd"] == hold
        assert report["coverage"]["refusals"] == refusals
        assert report["labels"]["routes"]["exclude"] == 0
        assert report["coverage"]["not_attempted"] == 4 - expected_calls
        with pytest.raises(AuditError, match="no_retry"):
            call(study, "run", allow_paid_execution=True)
        assert len(fake.calls) == expected_calls
    finally:
        study.close()


def test_budget_and_source_integrity_block_dispatch(tmp_path, fake, monkeypatch):
    parents(tmp_path)
    monkeypatch.setattr(adapter, "STUDY_BUDGET", adapter.transport.RESERVATION_NANOUSD - 1)
    study = adapter.Study(tmp_path / "screen", config=Config(offline=False))
    try:
        call(study, "prepare", base=str(tmp_path), count=4)
        result = call(study, "run", allow_paid_execution=True)
        assert result["stop_reason"] == "budget_bound" and not fake.calls
        report = call(study, "report")
        assert report["coverage"]["not_attempted"] == 4 and not report["complete"]
    finally:
        study.close()
    archive = tmp_path / adapter.STANDARD / "synthetic-archives/incident-reports.zip"
    archive.write_bytes(archive.read_bytes() + b"synthetic tampering")
    broken = adapter.Study(tmp_path / "broken", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="archive_hash_mismatch"):
            call(broken, "prepare", base=str(tmp_path), count=8)
        assert not broken.rows("incident_screen_plan") and not fake.calls
    finally:
        broken.close()
