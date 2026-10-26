"""Selection, weighting, blinded inputs, exact evidence and no-repeat lifecycle."""
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

import pytest

from newsresearch import astra_incident_validation as method
from newsresearch.common import AuditError, Config, ResearchError, canonical, digest
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workbench"))
import validate_incident_decisions_astra as runner  # noqa: E402


def ref(route, ambiguous=False):
    return {"route": route, "boundary_ambiguous": ambiguous}


def test_weighting_uncertainty_intervals_and_reproducible_strata():
    frame = [{"custom_id": str(i), "request_hash": digest(i), "status": "valid",
              "decision": {"route": "keep" if i < 12 else "exclude"}} for i in range(40)]
    first, sizes = method.select_sample(frame, 5)
    second, _ = method.select_sample(list(reversed(frame)), 5)
    assert first == second and sizes == {"keep": 12, "exclude": 28}
    assert Counter(r["stratum"] for r in first) == {"keep": 5, "exclude": 5}
    with pytest.raises(ResearchError, match="duplicate"):
        method.select_sample(frame + [frame[0]], 5)
    cases = [{"stratum": "keep", "reference": ref("keep")}] * 8 + [{"stratum": "keep", "reference": ref("exclude")}] * 2
    cases += [{"stratum": "exclude", "reference": ref("exclude")}] * 7
    cases += [{"stratum": "exclude", "reference": ref("keep")}, {"stratum": "exclude", "reference": ref("keep", True)}, {"stratum": "exclude", "reference": None}]
    out = method.metrics(cases, {"keep": 100, "exclude": 1000})
    assert out["confusion_against_astra_clear_references"] == {"TP": 8, "FP": 2, "unresolved_keep": 0, "FN": 1, "TN": 7, "unresolved_exclude": 2}
    assert out["weighted_article_counts"]["FN"] == 100
    assert out["weighted_recall_among_determinate_reference_mass"] == pytest.approx(80 / 180)
    assert method.wilson(0, 50)[1] > .05
    assert method.wilson(225, 450)[1] - .5 < .05
    assert out["strata"]["exclude"]["uncertainty_inclusive_95_bounds"][1] > .3


def test_blinding_quote_coverage_and_transport_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    items = [{"article_id": "opaque", "title": "A synthetic title", "body": "The complete synthetic original article."}]
    request = method.request_for(items, [{"name": "synthetic"}])
    assert set(request) == {"inclusion", "evidence", "schema"}
    provider = method.AstraProvider(tmp_path / "workers", executable="fake", model=method.MODEL)
    prepared = provider.prepare(request)
    provider._validate_prepared(prepared)
    assert "gpt-6-astra" in prepared.command
    with pytest.raises(ResearchError, match="changed"):
        provider._validate_prepared(replace(prepared, stdin="changed"))
    judgment = {"article_id": "opaque", "event_scope": "single_event", "ai_incident": "yes",
                "scope_rationale": "Synthetic scope supported", "incident_rationale": "Synthetic harm supported",
                "scope_quote": items[0]["title"], "incident_quote": items[0]["body"], "boundary_ambiguous": False}
    assert method.validate_references(request, {"judgments": [judgment]})[0]["route"] == "keep"
    with pytest.raises(ResearchError, match="coverage"):
        method.validate_references(request, {"judgments": [judgment, judgment]})
    wrong = {**judgment, "incident_quote": "Fabricated unsupported quotation"}
    with pytest.raises(ResearchError, match="quote"):
        method.validate_references(request, {"judgments": [wrong]})
    response = ProviderResponse({"judgments": [judgment]}, "codex-cli", "gpt-6-luna", raw_response={"events": []})
    assert method.terminal_response(response).payload is None


class Parent(Research):
    @audited_handler
    def _status(self, session, context, data):
        tasks, rows = [], []
        for i in range(12):
            title, body = f"Synthetic article {i}", f"Complete original synthetic body number {i} with enough evidence."
            request = {"model": "gpt-6-luna", "input": canonical({"title": title, "body": body}), "questions": [{"name": "synthetic"}]}
            tasks.append({"custom_id": str(i), "corpus": "incident-reports", "request": request, "request_hash": digest(request),
                          "descriptor": {"retained_body_sha256": hashlib.sha256(body.encode()).hexdigest()}})
            rows.append({"custom_id": str(i), "corpus": "incident-reports", "status": "valid", "request_hash": digest(request),
                         "decision": {"route": "keep" if i < 6 else "exclude"}, "source_locator": {}, "record_id": digest(["row", i])})
        plan = self.ledger.record(session, "full_screen_plan", "synthetic", {"chunks": [{"artifact": self.ledger.artifacts.put(tasks), "count": len(tasks)}]})
        report = self.ledger.record(session, "full_screen_report", "synthetic", {"selected_articles": len(rows),
            "article_results_artifact": self.ledger.artifacts.put_bytes(("\n".join(canonical(r) for r in rows) + "\n").encode())})
        return {"plan": plan, "report": report}


class Fake(method.AstraProvider):
    calls = 0
    fail = False

    def complete_prepared(self, prepared):
        Fake.calls += 1
        if Fake.fail:
            return ProviderResponse(None, "codex-cli", method.MODEL, raw_response={"unknown_outcome": True, "failure": "synthetic_timeout"})
        values = []
        for item in prepared.request["evidence"]:
            article = json.loads(item["text"])
            values.append({"article_id": item["id"], "event_scope": "single_event", "ai_incident": "yes",
                "scope_rationale": "Synthetic scope judgment", "incident_rationale": "Synthetic harm judgment",
                "scope_quote": article["title"], "incident_quote": article["body"], "boundary_ambiguous": False})
        return ProviderResponse({"judgments": values}, "codex-cli", method.MODEL, usage={"input_tokens": 10}, raw_response={"unknown_outcome": False})


def call(study, action, **kwargs):
    return study.execute("status", {"action": action, **kwargs}, objective="Synthetic Astra validation lifecycle", actor="tests")


def test_registered_lifecycle_freeze_and_preserve_unknown_no_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(method, "PILOT_PER_STRATUM", 2)
    monkeypatch.setattr(method, "AstraProvider", Fake)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    parent = Parent(tmp_path / "parent", config=Config(offline=True))
    try:
        original = call(parent, "prepare")
    finally:
        parent.close()
    binary = tmp_path / "fake.exe"
    binary.write_bytes(b"synthetic binary")
    reviewer = runner.Study(tmp_path / "review", config=Config(offline=False))
    Fake.calls, Fake.fail = 0, False
    try:
        result = call(reviewer, "prepare", parent=str(tmp_path / "parent"), expected_plan=original["plan"], expected_report=original["report"], per_stratum=3, codex_executable=str(binary))
        assert result["selected"] == 6 and result["pilot"] == 4
        with pytest.raises(AuditError, match="all_selected_attempts"):
            call(reviewer, "report", phase="pilot")
        call(reviewer, "run", phase="pilot", allow_codex_execution=True)
        report = call(reviewer, "report", phase="pilot")
        assert report["metrics"]["confusion_against_astra_clear_references"]["TP"] == 2
        assert report["metrics"]["confusion_against_astra_clear_references"]["FN"] == 2
        prior = Fake.calls
        call(reviewer, "run", phase="pilot", allow_codex_execution=True)
        assert Fake.calls == prior
        Fake.fail = True
        call(reviewer, "run", phase="extension", allow_codex_execution=True)
        assert len(reviewer.ledger.unresolved) == 1
        prior = Fake.calls
        call(reviewer, "run", phase="extension", allow_codex_execution=True)
        assert Fake.calls == prior
        report = call(reviewer, "report", phase="all")
        assert report["metrics"]["sample_size"] == 6
        assert sum(report["metrics"]["confusion_against_astra_clear_references"][k] for k in ("unresolved_keep", "unresolved_exclude")) == 2
    finally:
        reviewer.close()
