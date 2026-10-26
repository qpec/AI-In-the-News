"""Synthetic amendment, summary no-retry, liability lineage and pipeline checks."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers as v1  # noqa: E402
import run_dossiers_v2 as runner  # noqa: E402
from test_cybercrime_dossier_runtime import FullPipelineTransport, FakeTransport  # noqa: E402

DOCS = [{"document_id": f"document-{i:02}", "title": f"Synthetic source {i}",
         "body": "Complete synthetic evidence.\r\n\tCafé 𝄞 " * 3} for i in range(40)]
PACKETS = [{"document_ids": [d["document_id"] for d in DOCS[i:i+4]]} for i in range(0, len(DOCS), 4)]
SORTED = sorted(PACKETS, key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
OLD_GROUPS = {digest(["seed", sorted(p["document_ids"])]): sorted(p["document_ids"]) for p in SORTED[:3]}
OLD_IDS = list(OLD_GROUPS)


class SyntheticInputs(Research):
    @audited_handler
    def _status(self, session, context, data):
        rows = [{"document_id": doc["document_id"], "document_artifact": self.ledger.artifacts.put(doc)} for doc in DOCS]
        return self.ledger.record(session, "cyber_dossier_input_manifest", "fixture", {
            "documents_artifact": self.ledger.artifacts.put(rows),
            "articles_artifact": self.ledger.artifacts.put([
                {"custom_id": doc["document_id"], "document_id": doc["document_id"]} for doc in DOCS]),
            "unique_documents": len(DOCS), "eligible_articles": len(DOCS)})


class LegacyTransport(FullPipelineTransport):
    def complete_prepared(self, invocation):
        supplied = json.loads(invocation.request["input"])
        dossier = supplied.get("dossier_id")
        if dossier in OLD_IDS[1:]:
            self.before_dispatch(invocation)
            self.calls.append(invocation)
            if dossier == OLD_IDS[2]:
                return ProviderResponse(None, "synthetic", None, raw_response={"unknown_outcome": True})
            return ProviderResponse({"model": "gpt-6-luna", "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
                "synthetic", "gpt-6-luna", usage={"input_tokens": 100, "output_tokens": 100}, raw_response={"http_status": 200})
        return super().complete_prepared(invocation)


def call(study, action, **kwargs):
    return study.execute("status", {"action": action, **kwargs}, objective="Test versioned dossier continuation", actor="test:dossier-v2")


def setup(tmp_path, monkeypatch):
    owner = tmp_path / "dossiers"
    initial = SyntheticInputs(owner, config=Config(offline=True))
    try:
        initial.execute("status", {}, objective="Create synthetic dossier input", actor="test:dossier-v2")
    finally:
        initial.close()
    # Test-only fixed implementation identity; real paths stay untouched.
    monkeypatch.setattr(v1, "implementation", lambda: {"v1": "immutable"})
    monkeypatch.setattr(runner, "implementation", lambda: {"v1": "immutable", "v2": "extension",
        str(Path(runner.contract.__file__).relative_to(runner.ROOT)): "contract-v2"})
    params = deepcopy(v1.PARAMETERS)
    params.update(dimensions=3, pilot_packets=1, max_seed_size=4, pilot_assignments=2,
                  embedding_tpm=10**10, luna_tpm=10**10, astra_tpm=10**10, rpm=10**10)
    monkeypatch.setattr(v1, "PARAMETERS", params)
    monkeypatch.setattr(runner, "PARAMETERS", deepcopy(params))
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-placeholder")
    monkeypatch.setattr(v1.transport, "UnifiedTransport", LegacyTransport)
    FakeTransport.calls = []
    FullPipelineTransport.reference_clarity = "clear_single_event"

    def old_pipeline(study, session, pilot):
        study.phase(session, "embeddings", {"document_ids": [d["document_id"] for d in DOCS],
                    "vectors": [[1., 0., 0.] for d in DOCS], "missing": []})
        study.phase(session, "seed_proposals", {"packets": PACKETS})
        study.phase(session, "pilot_gate", {"passed": True, "synthetic_old_gate": True})
        packets = [v1.contract.summary_request([study.documents[i] for i in members], dossier,
                   digest(sorted(members)), count_tokens=study.count, max_output_tokens=2720)
                   for dossier, members in OLD_GROUPS.items()]
        study.calls(session, packets)
        study.current_phase = "synthetic_original_stop"

    monkeypatch.setattr(v1.Study, "pipeline", old_pipeline)
    original = v1.Study(owner, config=Config(offline=False))
    try:
        # The original implementation key needed by its registration is supplied only for this step.
        monkeypatch.setattr(v1, "implementation", lambda: {"v1": "immutable",
            str(Path(v1.contract.__file__).relative_to(v1.ROOT)): "contract-v1"})
        prepared = call(original, "prepare")
        monkeypatch.setattr(runner, "PARENT_PLAN", prepared["id"])
        report = call(original, "pilot", allow_paid_execution=True)
        assert report["stored_responses"] == 3 and report["unresolved_holds"] == 1
        deadline = original.one("cyber_dossier_first_launch")["deadline"]
        old_records = original.rows("cyber_dossier_response")
    finally:
        original.close()
    monkeypatch.setattr(runner, "implementation", lambda: {**v1.implementation(), "v2": "extension",
        str(Path(runner.contract.__file__).relative_to(runner.ROOT)): "contract-v2"})
    extension = runner.Study(owner, config=Config(offline=True))
    try:
        amendment = call(extension, "amend")
        assert amendment["legacy_budget"]["committed_nanousd"] == report["committed_nanousd"]
        assert amendment["original_deadline"] == deadline
    finally:
        extension.close()
    monkeypatch.setattr(runner.transport, "UnifiedTransport", FullPipelineTransport)
    return owner, prepared["id"], amendment["id"], deadline, report, old_records


def test_next_pilot_excludes_original_packets_and_previous_summary_sources():
    packets = [{"document_ids": [str(i)]} for i in range(60)]
    ordered = sorted(packets, key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
    extra = ordered[20]["document_ids"]
    selected = runner.next_pilot_packets(packets, extra)
    assert len(selected["packets"]) == 16
    assert not ({i for p in ordered[:16] for i in p["document_ids"]} | set(extra)).intersection(
        i for p in selected["packets"] for i in p["document_ids"])
    assert selected["packets"] == [p for p in ordered[16:] if not set(extra).intersection(p["document_ids"])][:16]


def test_amendment_preserves_liabilities_and_new_pipeline_reuses_prior_summaries(tmp_path, monkeypatch):
    owner, plan, amendment, deadline, previous, old_rows = setup(tmp_path, monkeypatch)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        # A passing old gate must not authorize v2 full continuation.
        blocked = call(study, "run", allow_paid_execution=True)
        assert blocked["stored_responses"] == 3
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "pilot_v2_gate_not_passed"
        result = call(study, "pilot", allow_paid_execution=True)
        assert result["pilot_gate"]["passed"]
        assert result["legacy_unresolved_holds"] == 1 and result["new_unresolved_holds"] == 0
        assert result["held_nanousd"] == previous["held_nanousd"]
        assert result["execution_amendment"] == amendment and result["plan"] == plan
        selection = study.ledger.artifacts.read(study.amendment["pilot_selection_artifact"])
        assert not set(selection["excluded_document_ids"]).intersection(study.phase(None, "pilot_v2_seeds")["covered"])
        full = call(study, "run", allow_paid_execution=True)
        assert full["pipeline_finished"] and not full["four_processes_complete"]  # Two original failed summaries remain unavailable.
        assert full["legacy_unresolved_holds"] == 1 and full["new_unresolved_holds"] == 0
        assert study.one("cyber_dossier_first_launch")["deadline"] == deadline
        assert study.one("cyber_dossier_plan")["_record_id"] == plan
        assert study.rows("cyber_dossier_response")[:3] == old_rows
        versions = study.summary_attempts()
        assert len(versions) == len({key for key in versions})
        for dossier, members in OLD_GROUPS.items():
            old = versions[(dossier, digest(sorted(members)))]
            assert old["response_record"] in {r["_record_id"] for r in old_rows}
        new_rows = study.rows("cyber_dossier_response")[3:]
        assert all(r["execution_amendment"] == amendment for r in new_rows)
        for row in new_rows:
            packet = study.ledger.artifacts.read(row["packet"])
            if row["phase"] == "summary":
                assert packet["request"]["max_output_tokens"] >= 8000
                assert all(d["document_id"].startswith("S") for d in json.loads(packet["request"]["input"])["articles"])
        old_good = OLD_IDS[0]
        changed = runner.contract.summary_request([study.documents[i] for i in OLD_GROUPS[old_good]], old_good,
                    digest(sorted(OLD_GROUPS[old_good])), count_tokens=study.count)
        with pytest.raises(AuditError, match="already_attempted_no_retry"):
            study.calls("not-a-session", [changed])
        committed, sent = full["committed_nanousd"], len(FakeTransport.calls)
    finally:
        study.close()
    study = runner.Study(owner, config=Config(offline=False))
    try:
        result = call(study, "run", allow_paid_execution=True)
        assert result["committed_nanousd"] == committed and len(FakeTransport.calls) == sent
        assert result["held_nanousd"] == previous["held_nanousd"]
    finally:
        study.close()


def test_amendment_guard_deadline_stop_and_budget_are_not_reset(tmp_path, monkeypatch):
    owner, _, _, _, previous, _ = setup(tmp_path, monkeypatch)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        with pytest.raises(AuditError, match="explicit_paid_execution"):
            call(study, "pilot", allow_paid_execution=False)
        (owner / "STOP").write_text("Synthetic user stop", encoding="utf-8")
        stopped = call(study, "pilot", allow_paid_execution=True)
        assert stopped["stored_responses"] == 3
        assert stopped["committed_nanousd"] == previous["committed_nanousd"]
        assert study.rows("cyber_dossier_stopped")[-1]["reason"] == "user_stop"
        monkeypatch.setattr(runner, "implementation", lambda: {"changed": "not-frozen"})
        with pytest.raises(AuditError, match="frozen_amendment_changed"):
            call(study, "report")
    finally:
        study.close()


def test_new_holds_are_distinguished_and_legacy_removal_fails_closed():
    study = object.__new__(runner.Study)
    study.results = {}
    study.amendment = {"legacy_unresolved_attempts": ["old"], "legacy_budget": {"held_nanousd": 10}}
    from types import SimpleNamespace
    study.ledger = SimpleNamespace(unresolved={"old": {"reserved_nanousd": 10}, "new": {"reserved_nanousd": 20}})
    assert study.hold_lineage() == {"legacy_unresolved_holds": 1, "new_unresolved_holds": 1,
                                  "legacy_held_nanousd": 10, "new_held_nanousd": 20}
    study.ledger.unresolved.pop("old")
    with pytest.raises(AuditError, match="legacy_hold_was_removed"):
        study.hold_lineage()
