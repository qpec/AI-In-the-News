"""Exact stored-packet order repair and immutable local response revalidation."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v8 as runner  # noqa: E402
import test_cybercrime_dossier_runtime_v6 as prior  # noqa: E402
import test_cybercrime_dossier_runtime_v2 as legacy_fixture  # noqa: E402
from test_dossier_seed_v7_diagnostic import packet_and_reply, row  # noqa: E402
from test_cybercrime_dossier_runtime_v7 import call  # noqa: E402


@pytest.mark.parametrize("n", range(2, 9))
def test_order_copy_preserves_every_byte_and_existing_frozen_checks(n):
    packet, payload = packet_and_reply(n)
    before = canonical(packet)
    old_order = list(packet["question_map"])
    normalized = runner.normalize_seed_packet(packet)
    assert canonical(normalized) == before and canonical(normalized["request"]) == canonical(packet["request"])
    assert list(packet["question_map"]) == old_order and normalized["question_map"] == packet["question_map"]
    assert normalized is not packet and normalized["question_map"] is not packet["question_map"]
    assert list(normalized["question_map"]) == [q["name"] for q in packet["request"]["questions"]]
    assert runner.BASE.contract.parse_decisions(normalized, payload)["status"] == "valid"
    if n >= 6:
        with pytest.raises(ResearchError, match="binding_mismatch"):
            runner.BASE.contract.parse_decisions(packet, payload)


def test_malformed_names_request_and_tampered_pair_binding_still_fail():
    packet, payload = packet_and_reply(8)
    broken = deepcopy(packet)
    broken["request"]["questions"][1]["name"] = broken["request"]["questions"][0]["name"]
    with pytest.raises(AuditError, match="question_name_coverage"):
        runner.normalize_seed_packet(broken)
    broken = deepcopy(packet)
    broken["request"]["questions"][0]["instructions"] += "tampered"
    with pytest.raises(AuditError, match="canonical_identity_changed"):
        runner.normalize_seed_packet(broken)
    broken = deepcopy(packet)
    broken["question_map"]["pair_0"]["left"] = "tampered"
    with pytest.raises(ResearchError, match="dossier_pair_not_in_packet_or_repeated"):
        runner.BASE.contract.parse_decisions(runner.normalize_seed_packet(broken), payload)


@pytest.mark.parametrize("change", ["hold", "parsed", "http", "error", "request", "model", "probability"])
def test_derived_revalidation_never_repairs_other_faults(change):
    packet, payload = packet_and_reply(8)
    original = deepcopy(packet["request"])
    item = row(8)
    if change == "hold":
        item["hold"] = True
    elif change == "parsed":
        item["parsed"] = "already-valid"
    elif change == "http":
        item["http_status"] = 400
    elif change == "error":
        item["validation_error"] = "ResearchError:dossier_probability_invalid"
    elif change == "request":
        original["input"] += "changed"
    elif change == "model":
        payload["model"] = "wrong-model"
    else:
        payload["answers"][0]["probabilities"][0]["probability"] = .5
    with pytest.raises((AuditError, ResearchError)):
        runner.revalidate_retained(item, packet, {"payload": payload}, original)


def test_derived_valid_uses_untouched_provider_payload_and_zero_retry_lookup():
    packet, payload = packet_and_reply(8)
    before = canonical(payload)
    normalized, parsed = runner.revalidate_retained(row(8), packet, {"payload": payload}, packet["request"])
    assert parsed["status"] == "valid" and canonical(payload) == before and digest(normalized) == digest(packet)
    study = object.__new__(runner.Study)
    study.plan = {"_record_id": "plan"}
    study.derived_parsed = {study.task_key(packet): parsed}
    study.results = {study.task_key(packet): {"parsed": None, "hold": False}}
    study.ledger = SimpleNamespace(artifacts=SimpleNamespace(read=lambda _: pytest.fail("no original parse replacement")))
    assert study.parsed(packet) == parsed


def test_registered_repair_then_real_full_roundtrip_dispatch_and_resume(tmp_path, monkeypatch):
    # Preserve existing historical fixtures and add enough actual eight-source
    # seed packets for both three old failures and future untouched dispatch.
    extra = [{"document_id": f"extra-{i:03}", "title": f"Synthetic extra source {i}",
              "body": "Complete synthetic article paragraph one.\n\nComplete paragraph two."} for i in range(80)]
    monkeypatch.setattr(legacy_fixture, "DOCS", legacy_fixture.DOCS + extra)
    monkeypatch.setattr(legacy_fixture, "PACKETS", legacy_fixture.PACKETS + [
        {"document_ids": [d["document_id"] for d in extra[i:i+8]]} for i in range(0, len(extra), 8)])
    owner, _, deadline, _ = prior.setup(tmp_path, monkeypatch)
    v6 = runner.parent.parent.Study(owner, config=Config(offline=False))
    try:
        passed = call(v6, "pilot", allow_paid_execution=True)
        assert passed["pilot_gate"]["passed"]
        stopped_v6 = call(v6, "report")
        v6_id = v6.one("cyber_dossier_execution_amendment_v6")["_record_id"]
    finally:
        v6.close()
    for key, value in {"PARENT_AMENDMENT": v6_id, "PARENT_REPORT": stopped_v6["id"], "PASSED_REPORT": passed["id"]}.items():
        monkeypatch.setattr(runner.parent, key, value)
    monkeypatch.setattr(runner.parent, "implementation", lambda: {**runner.parent.parent.implementation(), "v7": "synthetic"})
    v7 = runner.parent.Study(owner, config=Config(offline=True))
    try:
        prepared_v7 = call(v7, "amend")
    finally:
        v7.close()
    original_full = runner.parent.Study.full_pipeline
    def reproduce_three_stored_failures(self, session):
        entries = self.ledger.artifacts.read(self.amendment["seed_packet_plan_artifact"])
        pending = [self.ledger.artifacts.read(r["packet_artifact"]) for r in entries
                   if r["state"] == "untouched_request_fits" and len(r["document_ids"]) == 8]
        assert len(pending) >= 4
        self.current_phase = "synthetic_first_three_stored_seeds"
        self.calls(session, pending[:3])
        pytest.fail("the frozen parser must trigger its three-failure breaker")
    monkeypatch.setattr(runner.parent.Study, "full_pipeline", reproduce_three_stored_failures)
    v7 = runner.parent.Study(owner, config=Config(offline=False))
    try:
        stopped = call(v7, "run", allow_paid_execution=True)
        assert v7.rows("cyber_dossier_stopped")[-1]["reason"] == "repeated_provider_or_validation_failure"
        failed = [r for r in v7.rows("cyber_dossier_response") if r.get("execution_amendment") == prepared_v7["id"]]
        assert len(failed) == 3 and all(r["validation_error"] == runner.ERROR and not r["hold"] for r in failed)
        responses_before = len(v7.results)
        attempts_before = v7.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
    finally:
        v7.close()
    monkeypatch.setattr(runner.parent.Study, "full_pipeline", original_full)
    for key, value in {"PARENT_AMENDMENT": prepared_v7["id"], "PARENT_REPORT": stopped["id"],
                       "SOURCE_RESPONSES": tuple(r["_record_id"] for r in failed)}.items():
        monkeypatch.setattr(runner, key, value)
    monkeypatch.setattr(runner, "implementation", lambda: {**runner.parent.implementation(), "v8": "synthetic"})
    monkeypatch.setattr(runner.Study, "diagnostic_binding", lambda self: {"owner": "synthetic", "record_id": runner.DIAGNOSTIC})
    study = runner.Study(owner, config=Config(offline=True))
    try:
        prepared = call(study, "amend")
        assert prepared["paid_calls"] == 0 and prepared["seed_revalidation"]["valid"] == 3
        assert len(study.results) == responses_before and prepared["legacy_budget"]["committed_nanousd"] == stopped["committed_nanousd"]
        assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == attempts_before
        assert prepared["seed_order_integrity"]["checked_packets"] == prepared_v7["seed_capacity_census"]["proposed_packets"]
        assert prepared["seed_order_integrity"]["canonical_packet_changes"] == prepared["seed_order_integrity"]["request_changes"] == 0
        assert all(study.ledger.get(r["_record_id"], "cyber_dossier_response") == {k: v for k, v in r.items() if not k.startswith("_")} for r in failed)
    finally:
        study.close()
    study = runner.Study(owner, config=Config(offline=False))
    try:
        report = call(study, "run", allow_paid_execution=True)
        assert report["pipeline_processing_complete"] and report["technical_extension_version"] == 8
        assert report["seed_revalidation"]["valid"] == 3 and report["seed_revalidation"]["model_calls"] == 0
        assert report["held_nanousd"] == stopped["held_nanousd"] and report["unresolved_holds"] == 4
        assert study.one("cyber_dossier_first_launch")["deadline"] == deadline
        new_seed = [r for r in study.rows("cyber_dossier_response") if r.get("execution_amendment") == prepared["id"] and r["phase"] == "seed"]
        large = [r for r in new_seed if len(study.ledger.artifacts.read(r["packet"])["document_ids"]) == 8]
        assert large and all(r["parsed"] and not r["validation_error"] and not r["hold"] for r in large)
        assert len(study.rows("cyber_dossier_seed_revalidation")) == 3
        for old in failed:
            assert study.results[old["task_key"]]["parsed"] is None
            assert study.results[old["task_key"]]["validation_error"] == runner.ERROR
            packet = study.ledger.artifacts.read(old["packet"])
            assert study.parsed(packet)["status"] == "valid"
        after = len(study.results)
        attempts_after = study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
        repeated = call(study, "run", allow_paid_execution=True)
        assert len(study.results) == after and repeated["committed_nanousd"] == report["committed_nanousd"]
        assert repeated["seed_revalidation"] == report["seed_revalidation"]
        assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == attempts_after
    finally:
        study.close()
