"""Synthetic fixed-frame projection tests; no production owner or model reads."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import inspect_summary_fidelity_results_v2 as view  # noqa: E402
from newsresearch.common import AuditError, Config, digest  # noqa: E402
from newsresearch.runtime import Research, audited_handler  # noqa: E402


def seal(kind, key, value):
    return {**value, "_logical_key": key,
            "_record_id": digest({"kind": kind, "key": key, "payload": digest(value), "supersedes": None})}


def frame(record=seal, put=digest):
    tasks = [{"selection": {"summary_version": f"v{i}", "summary_record": f"s{i}",
               "stratum": "weak" if i < 6 else "usable_control", "grounding_probabilities": {"supported": .8}},
              "task_key": f"old-task-{i}", "packet": f"old-packet-{i}"} for i in range(12)]
    shared = {"execution_amendment": "dossier-v3", "original_deadline": "2026-10-24T12:55:27Z"}
    parent = record("cyber_summary_fidelity_diagnostic_plan", view.diagnostic.original.METHOD,
                    {**shared, "parent_plan": "dossier-plan", "implementation": {"old": "hash"}, "tasks": tasks})
    old = [{"selection": deepcopy(t["selection"]), "response_record": f"response-{i}" if i < 3 else None,
            "unresolved_attempt": f"hold-{i}" if i < 3 else None,
            "outcome": "unknown_hold" if i < 3 else "not_attempted", "parsed": None,
            "validation_error": "schema-http400" if i < 3 else None} for i, t in enumerate(tasks)]

    def report(kind, rows, extras):
        counts = {}
        for row in rows:
            counts.setdefault(row["selection"]["stratum"], Counter())[row["outcome"]] += 1
        value = {**shared, "plan": "dossier-plan", "at": "2026-10-23T14:00:00Z", "selected": len(rows),
                 "stratum_labels": {k: dict(v) for k, v in counts.items()}, "details_artifact": put(rows),
                 "stored_diagnostic_responses": sum(r["response_record"] is not None for r in rows),
                 "attempted_diagnostic_tasks": sum(r["outcome"] != "not_attempted" for r in rows), **extras}
        return record(kind, digest(value), value)

    prior = report("cyber_summary_fidelity_diagnostic_report", old, {"diagnostic_plan": parent["_record_id"]})
    remaining = [{"selection": t["selection"], "original_task_key": t["task_key"], "original_packet": t["packet"],
                  "task_key": f"new-{i}", "packet": f"new-packet-{i}"} for i, t in enumerate(tasks) if i >= 3]
    amendment = record(view.PLAN_KIND, view.diagnostic.METHOD, {
        **shared, "parent_plan": "dossier-plan", "implementation": {"new": "hash"},
        "parent_implementation": parent["implementation"], "parent_diagnostic_plan": parent["_record_id"],
        "parent_diagnostic_report": prior["_record_id"], "original_tasks": tasks, "tasks": remaining,
        "required_parent_hold_attempts": [f"hold-{i}" for i in range(3)],
        "excluded_attempts": [{"summary_version": f"v{i}", "attempt": f"hold-{i}",
            "original_task_key": f"old-task-{i}", "reason": "prior_attempt_never_retried"} for i in range(3)]})
    rows = deepcopy(old)
    for i, row in enumerate(rows[3:7], 3):
        label = ("supported", "unsupported", "identity_missing", "uncertain")[i-3]
        row.update(outcome=label, response_record=f"repair-response-{i}", parsed={
            "status": "valid", "label": label, "reason": "r" * 2001, "claim_paths": ["/overview"],
            "affected_claims": [{"path": "/overview", "value_sha256": "claim-hash", "value": "PRIVATE CLAIM"}],
            "selected_passage_locations": [{"document_id": "article-id", "field": "body", "start": 12, "end": 24,
                "text_sha256": "quote-hash", "quote": "PRIVATE QUOTE"}], "citations": [{"quote": "PRIVATE QUOTE"}]})
    repaired = report(view.REPORT_KIND, rows, {"diagnostic_plan": amendment["_record_id"],
        "parent_diagnostic_plan": parent["_record_id"], "repair_selected": 9, "repair_stored_responses": 4,
        "old_gates_modified": False, "summaries_regenerated": 0, "human_validated": False,
        "population_accuracy_estimate": False})
    return parent, prior, old, amendment, repaired, rows


@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setattr(view.diagnostic.original, "implementation", lambda: {"old": "hash"})
    monkeypatch.setattr(view.diagnostic, "implementation", lambda: {"new": "hash"})
    values = frame()
    monkeypatch.setattr(view.diagnostic, "PARENT_PLAN", values[0]["_record_id"])
    monkeypatch.setattr(view.diagnostic, "PARENT_REPORT", values[1]["_record_id"])
    return values


def test_exact_safe_helper_and_full_partial_denominator(fixture):
    assert view.project is view.previous.project
    result = view.validate_lineage(*fixture)
    assert result == {"fixed_original_denominator": 12, "preserved_parent_holds": 3, "repair_selected": 9}
    rows = view.project(fixture[-1])
    assert len(rows) == 12 and [r["outcome"] for r in rows[:3]] == ["unknown_hold"] * 3
    assert rows[3]["model_reason_truncated"] and len(rows[3]["model_reason"]) == 2000
    assert "PRIVATE" not in json.dumps(rows)
    assert rows[4]["outcome"] == "unsupported" and rows[6]["outcome"] == "uncertain"
    assert {Path(p).name for p in view.implementation()} == {
        "inspect_summary_fidelity_results_v2.py", "inspect_summary_fidelity_results.py"}


@pytest.mark.parametrize("mutation,expected", [
    (lambda f: f[3].update(parent_diagnostic_report="wrong"), "repair_lineage_changed"),
    (lambda f: f[3]["implementation"].update(extra="changed"), "implementation_changed"),
    (lambda f: f[4].update(selected=11), "report_digest_changed"),
    (lambda f: f[3]["tasks"].pop(), "repair_frame_changed"),
    (lambda f: f[3]["excluded_attempts"][0].update(attempt="replacement"), "excluded_identity_changed"),
    (lambda f: f[5][0].update(response_record="retry-response"), "old_hold_rewritten"),
    (lambda f: f[5][3]["parsed"].update(label="unsupported"), "outcome_parse_disagrees"),
    (lambda f: f[5][11]["selection"].update(summary_version="replacement"), "selection_changed"),
])
def test_mismatched_lineage_digests_frame_holds_and_labels_fail(fixture, mutation, expected):
    value = deepcopy(fixture)
    mutation(value)
    with pytest.raises(AuditError, match=expected):
        view.validate_lineage(*value)


class SourceFixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        def record(kind, key, value):
            identifier = self.ledger.record(session, kind, key, value)
            return {**value, "_record_id": identifier, "_logical_key": key}
        values = frame(record, self.ledger.artifacts.put)
        return {"parent": values[0]["_record_id"], "report": values[1]["_record_id"]}


def test_registered_projection_separate_readonly_owner_and_fresh_head(tmp_path, monkeypatch, fixture):
    active = tmp_path / "synthetic-source"
    source = SourceFixture(active, config=Config(offline=True))
    try:
        ids = source.execute("status", {}, objective="Create synthetic fixed diagnostic report", actor="test:projection")
    finally:
        source.close()
    monkeypatch.setattr(view, "ACTIVE_OWNER", active)
    monkeypatch.setattr(view.diagnostic, "PARENT_PLAN", ids["parent"])
    monkeypatch.setattr(view.diagnostic, "PARENT_REPORT", ids["report"])
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        view.Study(active, config=Config(offline=True))
    reader = view.Source(active)
    before = reader.head()
    try:
        with pytest.raises(AuditError, match="source_changed"):
            view.read_projection(reader, lambda: [before[0] + 1, "changed"])
    finally:
        reader.close()
    opened = []
    real_source = view.Source

    def observing_source(owner):
        opened.append(owner)
        return real_source(owner)

    monkeypatch.setattr(view, "Source", observing_source)
    study = view.Study(tmp_path / "reader", config=Config(offline=True))
    try:
        result = study.execute("status", {}, objective="Project saved synthetic reasons", actor="test:projection")
        assert result["selected"] == 12 and result["preserved_parent_holds"] == 3
        assert result["source_head_stable"] and len(opened) == 2
        assert result["new_model_calls"] == result["worker_mutations"] == result["new_substantive_labels"] == 0
        assert "PRIVATE" not in json.dumps(result)
        assert study.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
        assert study.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='cyber_summary_fidelity_reason_view_v2'").fetchone()[0] == 1
    finally:
        study.close()
    final = real_source(active)
    try:
        assert final.head() == before
    finally:
        final.close()
