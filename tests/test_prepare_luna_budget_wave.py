"""Synthetic rolling-wave gates; no production archive or network activity."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, ResearchError, digest
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, UsageReceipt
from newsresearch.runtime import audited_handler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import prepare_luna_budget_wave as runner
    import prepare_luna_budget_execution as preparation
finally:
    sys.path.pop(0)

SPEC = importlib.util.spec_from_file_location("budget_preparation_test_fixture", ROOT / "tests/test_prepare_luna_budget_execution.py")
assert SPEC and SPEC.loader
fixture_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture_module)


def gate_fixture():
    plan_id = "f" * 64
    price = preparation.price_policy()
    book = BudgetBook(price, runner.STUDY, ceiling_nanousd=150_000_000_000,
                      operational_limit_nanousd=120_000_000_000)
    tasks, assessments = [], []
    for corpus in runner.CORPORA:
        for number in range(8):
            custom = f"{corpus}-{number}"
            body_ref = digest({"synthetic": custom})
            tasks.append({"corpus_id": corpus, "custom_id": custom, "request_body_ref": body_ref})
            receipt = InputTokenReceipt(1000, price.model, body_ref, "a" * 64, "provider_responses_input_tokens")
            book.reserve(request_id=custom, task_id=custom, corpus_id=corpus, plan_id=plan_id,
                request_sha256=body_ref, input_count=receipt, max_output_tokens=4096, price_fingerprint=price.fingerprint)
            book.settle(custom, UsageReceipt(1000, 200, price.model, body_ref, "b" * 64, True))
            assessments.append({"plan": plan_id, "custom_id": custom, "status": "valid" if number == 0 else "invalid"})
    plan = {"canary_tasks": tasks, "price_fingerprint": price.fingerprint,
            "ceiling_nanousd": book.ceiling_nanousd, "operational_limit_nanousd": book.operational_limit_nanousd}
    return plan_id, plan, assessments, book


def test_completed_accounted_canaries_allow_bounded_wave_without_quality_claim():
    result = runner.canary_gate(*gate_fixture())
    assert result["allowed"]
    assert result["completed_canaries"] == result["accounted_canaries"] == 16
    assert result["invalid_canaries"] == 14
    assert result["valid_by_corpus"] == {corpus: 1 for corpus in runner.CORPORA}
    assert result["semantic_quality_validated"] is False


@pytest.mark.parametrize("mutation,blocker", [
    ("missing", "canary_assessment_missing"), ("duplicate", "canary_assessment_duplicate"),
    ("unknown", "canary_technical_or_unknown"), ("technical", "canary_technical_or_unknown"),
    ("error", "prior_technical_or_unknown_assessment"), ("all_invalid", "canary_no_valid_output_in_one_or_more_corpora"),
])
def test_canary_gate_rejects_missing_unknown_technical_and_no_valid(mutation, blocker):
    plan_id, plan, assessments, book = gate_fixture()
    if mutation == "missing":
        assessments.pop()
    elif mutation == "duplicate":
        assessments.append(deepcopy(assessments[0]))
    elif mutation == "unknown":
        assessments[0]["unknown"] = True
    elif mutation == "technical":
        assessments[0]["technical_failure"] = True
    elif mutation == "error":
        assessments[0]["status"] = "error"
    else:
        for row in assessments:
            row["status"] = "invalid"
    result = runner.canary_gate(plan_id, plan, assessments, book)
    assert not result["allowed"]
    assert blocker in result["blockers"]


def test_complete_outputs_without_charge_accounting_are_blocked():
    plan_id, plan, assessments, settled = gate_fixture()
    empty = BudgetBook(settled.price_policy, runner.STUDY, ceiling_nanousd=settled.ceiling_nanousd,
                       operational_limit_nanousd=settled.operational_limit_nanousd)
    result = runner.canary_gate(plan_id, plan, assessments, empty)
    assert not result["allowed"]
    assert result["accounted_canaries"] == 0
    assert "canary_charge_unaccounted" in result["blockers"]


def test_unknown_other_charge_blocks_new_wave():
    plan_id, plan, assessments, book = gate_fixture()
    receipt = InputTokenReceipt(1000, book.price_policy.model, "c" * 64, "d" * 64, "provider_responses_input_tokens")
    book.reserve(request_id="other", task_id="other", corpus_id="cybercrime", plan_id=plan_id,
                 request_sha256="c" * 64, input_count=receipt, max_output_tokens=4096,
                 price_fingerprint=book.price_policy.fingerprint)
    book.settle("other", None)
    result = runner.canary_gate(plan_id, plan, assessments, book)
    assert not result["allowed"]
    assert "shared_budget_unknown_or_unresolved_charge" in result["blockers"]


def test_price_or_accounting_binding_cannot_be_reset():
    plan_id, plan, assessments, book = gate_fixture()
    plan["ceiling_nanousd"] = 300_000_000_000
    with pytest.raises(AuditError, match="accounting_binding_changed"):
        runner.canary_gate(plan_id, plan, assessments, book)


def queue_fixture():
    items = [{"row_id": digest({"row": number}), "custom_id": str(number)} for number in range(600)]
    items.sort(key=lambda item: (digest({"seed": runner.SEED, "row_id": item["row_id"]}), item["row_id"]))
    return {"seed": runner.SEED, "items": items}


def test_next_wave_skips_all_manifested_ids_but_preserves_original_order():
    queue = queue_fixture()
    manifested = {row["custom_id"] for row in queue["items"][:13]}
    assert runner.choose_next(queue, manifested, 250) == queue["items"][13:263]


@pytest.mark.parametrize("limit", [0, 251, True, 1.5])
def test_limits_are_bounded(limit):
    with pytest.raises(ResearchError, match="one_to_250"):
        runner.choose_next(queue_fixture(), set(), limit)


def test_reordered_queue_is_not_silently_repaired():
    queue = queue_fixture()
    queue["items"].reverse()
    with pytest.raises(AuditError, match="order_changed"):
        runner.choose_next(queue, set(), 250)


class SeededWaveResearch(runner.WaveResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data.get("seed"):
            plan = self.ledger.get(data["plan"], "luna_budget_execution_plan")
            price = preparation.PricePolicy(**plan["price_policy"])
            book = BudgetBook(price, runner.STUDY, ceiling_nanousd=plan["ceiling_nanousd"],
                              operational_limit_nanousd=plan["operational_limit_nanousd"])
            state = self.gateway.save_book(session, book)
            for corpus in runner.CORPORA:
                tasks = [task for task in plan["canary_tasks"] if task["corpus_id"] == corpus]
                self.ledger.record(session, runner.MANIFEST_KIND, data["plan"] + ":canary:" + corpus,
                    {"plan": data["plan"], "corpus_id": corpus, "phase": "canary", "tasks": tasks})
                for task in tasks:
                    receipt = InputTokenReceipt(1000, price.model, task["request_body_ref"], "a" * 64, "provider_responses_input_tokens")
                    book.reserve(request_id=task["custom_id"], task_id=task["custom_id"], corpus_id=corpus, plan_id=data["plan"],
                        request_sha256=task["request_body_ref"], input_count=receipt, max_output_tokens=4096, price_fingerprint=price.fingerprint)
                    book.settle(task["custom_id"], UsageReceipt(1000, 200, price.model, task["request_body_ref"], "b" * 64, True))
                    self.ledger.record(session, runner.ASSESSMENT_KIND, task["custom_id"],
                        {"plan": data["plan"], "custom_id": task["custom_id"], "status": "valid"})
            self.gateway.save_book(session, book, state)
            return {"synthetic_seed": True}
        return super()._status(session, context, data)


def prepared_fixture(tmp_path, monkeypatch):
    owner, data, _, partitions = fixture_module.fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "OWNER", owner)
    monkeypatch.setattr(runner, "read_partition", lambda root, corpus: deepcopy(partitions[corpus]))
    monkeypatch.setattr(runner, "offline_tokenizer", fixture_module.SyntheticEncoder)
    engine = preparation.PreparationResearch(owner)
    try:
        result = fixture_module.execute(engine, data)
    finally:
        engine.close()
    return owner, result


def test_audited_wave_blocks_without_canary_accounting_and_reads_no_sources(tmp_path, monkeypatch):
    owner, plan = prepared_fixture(tmp_path, monkeypatch)
    called = []
    monkeypatch.setattr(runner, "materialize_tasks", lambda *args: called.append(True))
    engine = runner.WaveResearch(owner)
    try:
        result = engine.execute("status", {"plan": plan["id"], "max_per_corpus": 250},
            objective="Test synthetic missing-canary block", actor="test:software")
        assert result["status"] == "blocked"
        assert result["source_reads"] == result["new_requests_staged"] == 0
        assert not called
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind=?", (runner.MANIFEST_KIND,)).fetchone()[0] == 0
    finally:
        engine.close()


def test_audited_wave_stages_only_unmanifested_records_and_never_repeats(tmp_path, monkeypatch):
    owner, plan = prepared_fixture(tmp_path, monkeypatch)
    engine = SeededWaveResearch(owner)
    try:
        engine.execute("status", {"seed": True, "plan": plan["id"]}, objective="Seed synthetic canary records", actor="test:software")
        result = engine.execute("status", {"plan": plan["id"], "max_per_corpus": 250},
            objective="Test synthetic bounded wave stage", actor="test:software")
        assert result["status"] == "staged"
        assert result["new_requests_staged"] == 4
        assert len(result["manifests"]) == 2
        canary_ids = {task["custom_id"] for task in plan["canary_tasks"]}
        for reference in result["manifests"]:
            manifest = engine.ledger.get(reference["manifest"], runner.MANIFEST_KIND)
            assert manifest["phase"] == "bulk"
            assert len(manifest["tasks"]) == len(manifest["attempt_ids"]) == 2
            assert not canary_ids & {task["custom_id"] for task in manifest["tasks"]}
            assert len(engine.ledger.artifacts.read_bytes(manifest["jsonl_ref"]).splitlines()) == 2
        next_result = engine.execute("status", {"plan": plan["id"], "max_per_corpus": 250},
            objective="Test synthetic exhausted wave stage", actor="test:software")
        assert next_result["status"] == "queue_exhausted"
        assert next_result["new_requests_staged"] == 0
        assert result["model_calls"] == result["uploads"] == result["budget_reservations_created"] == 0
    finally:
        engine.close()


def test_wrong_owner_and_online_wave_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "OWNER", tmp_path / "expected")
    with pytest.raises(ResearchError, match="fixed_offline_owner"):
        runner.WaveResearch(tmp_path / "wrong")
    with pytest.raises(ResearchError, match="fixed_offline_owner"):
        runner.WaveResearch(tmp_path / "expected", config=Config(offline=False))
