"""Synthetic retained-record reporting only; no provider or protected owner."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, PricePolicy, UsageReceipt
from newsresearch.event_batch_live_gateway import EventBatchLiveGateway
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import report_luna_budget_progress as reporting
    from report_luna_budget_progress import ProgressResearch, aggregate
finally:
    sys.path.pop(0)


def fixture():
    plan = {"corpora": {"incident-reports": {"summary": {"eligible_requests": 10}},
                        "cybercrime": {"summary": {"eligible_requests": 8}}}}
    rows = {key: [] for key in ("manifests", "jobs", "assessments", "projections", "reconciled", "finishes")}
    entries = []
    for index, (corpus, ids, submitted) in enumerate([
            ("incident-reports", ["a", "b", "c"], True),
            ("cybercrime", ["d", "e", "f"], True),
            ("cybercrime", ["g"], False)]):
        manifest = f"manifest-{index}"
        rows["manifests"].append({"id": manifest, "corpus_id": corpus, "tasks": [{"custom_id": key} for key in ids]})
        if submitted:
            rows["jobs"].append({"manifest": manifest, "corpus_id": corpus, "request_count": len(ids)})
        for key in ids:
            entries.append({"request": {"request_id": key, "corpus_id": corpus}, "status": "unknown" if key == "e" else "settled",
                            "reserved_nanousd": 30 if key in {"e", "f"} else 70 if key == "g" else 0, "charged_nanousd": 1 if key in "abcd" else 0})
            if key not in "abcde":
                continue
            status = {"a": "valid", "b": "invalid", "c": "invalid", "d": "valid", "e": "error"}[key]
            rows["assessments"].append({"id": "assessment-" + key, "custom_id": key, "corpus_id": corpus,
                "manifest": manifest, "status": status, "technical_failure": status == "error", "title": key, "url": "https://example.test/" + key,
                "output": {"focus": "single", "event": {"summary": key}} if status == "valid" else None,
                "usage": {"input_tokens": 2, "output_tokens": 1} if key != "e" else None})
    for key in "ab":
        rows["projections"].append({"original_assessment": "assessment-" + key, "custom_id": key,
            "corpus_id": "incident-reports", "original_status": "valid" if key == "a" else "invalid", "derived_valid": True})
    return plan, rows, entries


def test_union_does_not_double_count_raw_valid_and_missing_projection_is_unresolved():
    plan, rows, entries = fixture()
    result = aggregate(plan, rows, entries)
    incident = result["incident-reports"]
    assert incident["mechanically_usable"] == 2
    assert incident["derived_only_recovered"] == 1
    assert incident["remaining_content_invalid"] == 1
    assert (incident["projection_covered"], incident["projection_uncovered"]) == (2, 1)
    assert incident["raw_valid_focus_counts"] == {"single": 1, "multiple": 0, "none": 0, "uncertain": 0}
    cyber = result["cybercrime"]
    assert (cyber["submitted"], cyber["assessed"], cyber["unassessed"]) == (3, 2, 1)
    assert cyber["projection_uncovered"] == 2
    assert cyber["technical_or_unknown"] == 1
    assert cyber["usage_unavailable_rows"] == 1
    assert cyber["reserved_submitted_unresolved_nanousd"] == 60
    assert cyber["reserved_staged_unsubmitted_nanousd"] == 70
    assert sum(row["charged_nanousd"] for row in result.values()) == 4


@pytest.mark.parametrize("fault", ["duplicate_task", "duplicate_assessment", "foreign_projection", "foreign_budget", "wrong_count"])
def test_identity_errors_fail_closed(fault):
    plan, rows, entries = deepcopy(fixture())
    if fault == "duplicate_task":
        rows["manifests"][0]["tasks"].append({"custom_id": "a"})
    elif fault == "duplicate_assessment":
        rows["assessments"].append(deepcopy(rows["assessments"][0]))
    elif fault == "foreign_projection":
        rows["projections"][0]["corpus_id"] = "cybercrime"
    elif fault == "foreign_budget":
        entries[0]["request"]["request_id"] = "foreign"
    else:
        rows["jobs"][0]["request_count"] = 99
    with pytest.raises(AuditError):
        aggregate(plan, rows, entries)


@pytest.mark.parametrize("oversized", [False, True])
def test_retained_provider_metadata_reads_receipt_values_and_bounds_output(oversized):
    saved = {"parse": {"download_receipts": {"output_file_id": "receipt"}}, "receipt": {"body_ref": "file"}}
    raw = {"custom_id": "a", "response": {"status_code": 200, "body": {
        "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
        "model": "gpt-6-luna", "output": [{"type": "message", "content": [{"type": "output_text",
            "text": "SYNTHETIC PREVIEW " * (400 if oversized else 1)}]}]}}}
    intents = []
    fake = SimpleNamespace(ledger=SimpleNamespace(
        append=lambda *args: intents.append(args),
        db=SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchone=lambda: {"id": "parse"})),
        get=lambda key, kind: saved[key],
        artifacts=SimpleNamespace(read_bytes=lambda key: json.dumps(raw).encode())))
    result = ProgressResearch.technical_metadata(fake, "session", {"manifest": "manifest", "custom_id": "a"})
    assert result["incomplete_details"] == {"reason": "max_output_tokens"}
    assert result["receipt"] == "receipt"
    assert result["output_display_omitted"] is oversized
    assert result["retained_output"] == (None if oversized else raw["response"]["body"]["output"])
    assert len(intents) == 2


class SeededProgressResearch(ProgressResearch):
    @audited_handler
    def _status(self, session, context, data):
        if not data.get("seed"):
            return super()._status(session, context, data)
        protocol = self._version(session, context, {"kind": "protocol", "key": "software-report-fixture",
            "content": {"method": "synthetic-retained-progress-fixture", "rules": "Software-only records; no research sources, model calls or network."}})["id"]
        plan, rows, _ = fixture()
        plan.update(authorization_id=reporting.STUDY, contract_sha256=reporting.contract_digest(), versions={"protocol": protocol})
        plan_id = self.ledger.record(session, "luna_budget_execution_plan", "synthetic-plan", plan)
        ids = {}
        for row in rows["manifests"]:
            old = row.pop("id")
            ids[old] = self.ledger.record(session, reporting.KINDS["manifests"], old, {"plan": plan_id, **row})
        for row in rows["jobs"]:
            row["manifest"] = ids[row["manifest"]]
            self.ledger.record(session, reporting.KINDS["jobs"], row["manifest"], {"plan": plan_id, **row})
            self.ledger.record(session, reporting.KINDS["reconciled"], row["manifest"], {"plan": plan_id, "manifest": row["manifest"]})
        raw = {"custom_id": "e", "response": {"status_code": 200, "body": {
            "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
            "model": "gpt-6-luna", "output": [{"type": "message", "content": [{"type": "output_text",
                "text": "SYNTHETIC OMITTED OUTPUT " * 300}]}]}}}
        file_ref = self.ledger.artifacts.put_bytes(json.dumps(raw).encode())
        receipt = self.ledger.record(session, "event_batch_live_receipt", "synthetic-download", {"body_ref": file_ref})
        self.ledger.record(session, "luna_budget_job_parsed", ids["manifest-1"],
            {"download_receipts": {"output_file_id": receipt}, "plan": plan_id})
        for row in rows["assessments"]:
            old = row.pop("id")
            row["manifest"] = ids[row["manifest"]]
            row["response"] = self.ledger.artifacts.put({"provider_status": "incomplete", "http_status": 200, "usage_complete": False})
            if row["output"]:
                row["output"]["event"]["participants"] = [{"surface": "Synthetic Org", "kind": "organization", "roles": [{"role": "subject"}]}]
            ids[old] = self.ledger.record(session, reporting.KINDS["assessments"], row["custom_id"], {"plan": plan_id, **row})
        for row in rows["projections"]:
            row["original_assessment"] = ids[row["original_assessment"]]
            self.ledger.record(session, reporting.KINDS["projections"], row["custom_id"], {"plan": plan_id, "protocol": protocol, **row})
        self.ledger.record(session, reporting.KINDS["finishes"], "synthetic-finish",
            {"plan": plan_id, "reason": "technical_stop", "ended_at": "2026-01-01T00:00:00Z"})
        policy = PricePolicy("gpt-6-luna", 100000000, 125000000, 500000000,
            (1, 2), (1, 1), (2, 1), (3, 2), 272000, "https://example.test/synthetic-price", "2026-01-01T00:00:00Z")
        book = BudgetBook(policy, reporting.STUDY, operational_limit_nanousd=120_000_000_000)
        gateway = EventBatchLiveGateway(self, self.gateway.provider)
        state = gateway.save_book(session, book)
        for row in rows["manifests"]:
            for task in row["tasks"]:
                custom = task["custom_id"]
                request_ref = digest({"synthetic": custom})
                count = InputTokenReceipt(100, policy.model, request_ref, "a" * 64, "provider_responses_input_tokens")
                book.reserve(request_id=custom, task_id=custom, corpus_id=row["corpus_id"], plan_id=plan_id,
                    request_sha256=request_ref, input_count=count, max_output_tokens=4096, price_fingerprint=policy.fingerprint)
                if custom in "abcd":
                    book.settle(custom, UsageReceipt(100, 10, policy.model, request_ref, "b" * 64, True))
                elif custom == "e":
                    book.settle(custom, None)
        state = gateway.save_book(session, book, state)
        return {"id": plan_id, "budget_state": state, "charge": book.charged_nanousd, "reserved": book.reserved_nanousd}


def test_audited_store_report_registers_loads_budget_renders_and_replays(tmp_path, monkeypatch):
    owner = tmp_path / "synthetic-progress-owner"
    monkeypatch.setattr(reporting, "OWNER", owner)
    engine = SeededProgressResearch(owner, config=Config(offline=True))
    try:
        seeded = engine.execute("status", {"seed": True}, objective="Seed software-only retained progress records", actor="test:software")
        report = engine.execute("status", {"plan": seeded["id"]}, objective="Smoke-test audited retained progress reporting", actor="test:software")
        assert report["budget_state"] == seeded["budget_state"]
        assert report["charged_estimate_usd"] == seeded["charge"] / 1e9
        assert report["reserved_usd"] == seeded["reserved"] / 1e9
        assert report["corpora"]["incident-reports"]["mechanically_usable"] == 2
        assert report["technical_rows"][0]["retained_provider_metadata"]["incomplete_details"] == {"reason": "max_output_tokens"}
        assert "Synthetic Org (organization; subject)" in report["markdown"]
        assert "SYNTHETIC OMITTED OUTPUT" not in json.dumps(report)
        assert engine.ledger.get(report["profile"], "profile")["content"]["mode"] == "exploratory"
        assert engine.ledger.artifacts.read_bytes(report["presentation"]).decode() == report["markdown"]
        repeated = engine.execute("status", {"plan": seeded["id"]}, objective="Smoke-test repeated offline reporting", actor="test:software")
        assert repeated["budget_state"] == report["budget_state"]
        assert repeated["corpora"] == report["corpora"]
        assert report["new_models"] == report["new_projections"] == 0
    finally:
        engine.close()
