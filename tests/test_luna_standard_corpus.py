"""Synthetic standard-tier, full-queue and no-redispatch recovery tests."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.luna_standard_provider import StandardProvider
from newsresearch.luna_speed_provider import contract, validate_response
import test_luna_speed_workflow as prior
from test_luna_speed_provider import ATTEMPT, TASK, stream
from test_luna_fast_v2 import recovered_stream

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_standard_corpus as corpus
finally:
    sys.path.pop(0)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("tier,recover,valid", [(None, False, True), ("default", True, True),
    ("standard", True, True), ("fast", False, False), ("priority", True, False)])
def test_standard_only_with_exact_stream_recovery(tmp_path, tier, recover, valid):
    packet, output = contract.fictional_example()
    events = recovered_stream(output) if recover else [json.loads(line) for line in stream(output).splitlines()]
    if tier is not None:
        events[-1]["service_tier"] = tier
    stdout = "\n".join(json.dumps(e) for e in events)
    calls = []
    def runner(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)
    provider = StandardProvider(tmp_path / "workers", runner=runner)
    invocation = provider.prepare(TASK, ATTEMPT, packet)
    assert "--ignore-user-config" in invocation.command
    assert "features.fast_mode=false" in invocation.command
    assert not any(arg.startswith("service_tier=") for arg in invocation.command)
    assert invocation.manifest()["configured_service_tier"] == "standard"
    response = provider.complete_prepared(invocation)
    assert len(calls) == 1 and response.raw_response["stdout"] == stdout
    assert (validate_response(response, packet) == []) == valid


class FixtureCorpus(corpus.CorpusResearch):
    def read_inputs(self, session, data):
        queues, summaries = {}, {}
        for name in ("incident-reports", "cybercrime"):
            queues[name] = [{"custom_id": f"{name}-{i}", "corpus_id": name,
                "retained_body_sha256": digest([name, i]), "source_sha256": digest(["source", name, i]),
                "source_locator": {"archive_path": "fictional.zip", "line": i + 1}}
                for i in range(6)]
            summaries[name] = {"partition": {}, "selected": 6}
        executable = self.ledger.root / "fictional-codex.exe"
        if not executable.exists():
            executable.write_bytes(b"synthetic fixture, not executable")
        return queues, {}, summaries, {"codex_executable": str(executable)}, {"original_deadline_epoch": 1}

    def packets(self, session, plan, remaining):
        packet, _ = contract.fictional_example()
        for queue in remaining.values():
            for index, descriptor in enumerate(queue):
                yield descriptor, packet, digest(["fictional", index]), index

    @contextmanager
    def source_guard(self, plan):
        yield


@pytest.mark.parametrize("interrupt", [False, True])
def test_complete_or_resume_only_untouched_identities(tmp_path, monkeypatch, interrupt):
    engine = FixtureCorpus(tmp_path / "private", config=Config(offline=True))
    seen = prior.mock_runner(monkeypatch, unknown=interrupt)
    try:
        prepared = prior.call(engine, "status", {"phase": "prepare"})
        plan = engine.ledger.get(prepared["id"], "luna_standard_plan")
        assert plan["deadline_epoch"] is None and plan["original_batch_deadline_epoch"] == 1
        engine.config = replace(engine.config, offline=False)
        payload = {"phase": "run", "plan": prepared["id"], "authorization_text": "Full synthetic queues; continue untouched identities only"}
        first = prior.call(engine, "status", payload)
        if interrupt:
            assert 0 < first["reserved"] < 12 and first["unknown_holds"] > 0
            assert first["stop_reason"] == "transport_or_unknown_stop"
            # Restore a clean transport, then genuinely reopen the owner.
            monkeypatch.undo()
            for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
                monkeypatch.delenv(key, raising=False)
            resumed = prior.mock_runner(monkeypatch)
            engine.close()
            engine = FixtureCorpus(tmp_path / "private", config=Config(offline=False))
            final = prior.call(engine, "status", payload)
            assert len(seen) + len(resumed) == 12
            assert final["unknown_holds"] == first["unknown_holds"]
        else:
            final = first
            assert len(seen) == 12 and final["unknown_holds"] == 0
        assert final["reserved"] == 12 and final["unattempted"] == 0
        repeated = prior.call(engine, "status", payload)
        assert repeated["reserved"] == 12
        rows = [json.loads(r[0]) for r in engine.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'")]
        assert len(rows) == len({r["custom_id"] for r in rows}) == 12
        assert all(r["number"] == 1 for r in rows)
        engine.ledger.verify()
    finally:
        engine.close()


def test_selection_preserves_frozen_order_and_all_prior_exclusions():
    descriptors = [{"custom_id": str(i), "corpus_id": "incident-reports", "retained_body_sha256": body}
        for i, body in enumerate(["reserved-id", "reserved-body", "codex", "new", "new", "other"])]
    rows = [{"id": str(i), "descriptor": d} for i, d in enumerate(descriptors)]
    queue = {"items": [{"chunk_index": 0, "row_index": i, "row_id": str(i), "custom_id": str(i)} for i in range(6)]}
    export = {"chunks": [{"content": {"rows": rows}}]}
    selected, excluded, mappings = corpus.select_queue(queue, export, "incident-reports", {"0"}, {"reserved-body"}, {"codex"})
    assert [d["custom_id"] for d in selected] == ["3", "5"]
    assert excluded == {"batch_reserved_or_attempted": 2, "codex_reserved_or_attempted": 1, "same_body_in_new_queue": 1}
    assert len(mappings) == 4
    rows[3]["descriptor"]["corpus_id"] = "cybercrime"
    with pytest.raises(AuditError, match="binding_changed"):
        corpus.select_queue(queue, export, "incident-reports", set(), set(), set())


def test_real_packet_bundle_preserves_binary_jsonl_as_exact_utf8(tmp_path, monkeypatch):
    engine = FixtureCorpus(tmp_path / "private", config=Config(offline=True))
    packet, _ = contract.fictional_example()
    descriptor = {"custom_id": "fictional", "corpus_id": "incident-reports"}
    record = {"request": {"body": {}}, "descriptor": descriptor, "packet": packet,
        "jsonl_line": b'{"fictional":"exact bytes"}\n'}
    monkeypatch.setattr(corpus.batch.LeanBatch, "materialize", lambda *args: [record])
    monkeypatch.setattr(corpus.batch, "packet_from_prompt", lambda *args: packet)
    # Exercise the actual production bundle path inside a registered operation.
    from newsresearch.runtime import audited_handler
    @audited_handler
    def inspect(self, session, context, data):
        result = list(corpus.CorpusResearch.packets(self, session,
            {"corpora": {"incident-reports": {"partition": {}}}}, {"incident-reports": [descriptor]}))
        retained = self.ledger.artifacts.read(result[0][2])
        assert retained[0]["jsonl_line"].encode("utf-8") == record["jsonl_line"]
        assert result[0][1] == packet
        return {"count": len(result)}
    monkeypatch.setattr(FixtureCorpus, "_status", inspect)
    try:
        assert prior.call(engine, "status", {})["count"] == 1
    finally:
        engine.close()
