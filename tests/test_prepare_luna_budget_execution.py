"""Synthetic audited preparation only; no production source or network access."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

from newsresearch.common import AuditError, Config, ResearchError, digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import prepare_luna_budget_execution as runner
finally:
    sys.path.pop(0)


class SyntheticEncoder:
    def encode(self, value, *, disallowed_special):
        assert disallowed_special == ()
        return list(value)


def synthetic_export(root, corpus, count=10):
    raw_rows = []
    for number in range(count):
        article = {"uri": f"fixture:{corpus}:{number}", "title": f"Synthetic {corpus} {number}",
                   "body": f"All full evidence for synthetic {corpus} article {number}.\n\nEntire second paragraph. ",
                   "source": {"uri": f"publisher-{number}.example"}, "date": "2026-01-01", "lang": "eng",
                   "url": f"https://synthetic.example/{corpus}/{number}"}
        raw_rows.append((json.dumps({"article": article}, ensure_ascii=False) + "\n").encode())
    archive = root / (corpus + ".zip")
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("artikelen.jsonl", b"".join(raw_rows))
    archive_hash = runner.sha256(archive)
    manifest_hash = digest({"synthetic": corpus})
    partition = {"corpus_id": corpus, "manifest_sha256": manifest_hash, "resolved_root": str(root),
        "manifest": {"bundles": [{"path": archive.name, "sha256": archive_hash, "declared_records": count}]}}
    snapshot = runner.core.load_contract_snapshot()
    rows = []
    for number, raw in enumerate(raw_rows, 1):
        article = json.loads(raw)["article"]
        locator = {"archive_path": archive.name, "archive_sha256": archive_hash, "stream": "artikelen.jsonl",
                   "line": number, "row_bytes_sha256": hashlib.sha256(raw).hexdigest()}
        normalized, states = runner.materialize.normalize_context(article)
        record = runner.core.build_request_record(normalized, corpus_id=corpus, manifest_sha256=manifest_hash,
            source_locator=locator, source_sha256=digest(article), count_tokens=len,
            token_proxy_method="cl100k_base_serialized_body_plus_32", context_availability=states,
            contract_snapshot=snapshot)
        rows.append({"id": digest({"corpus_id": corpus, "manifest_sha256": manifest_hash, "source_locator": locator}),
            "corpus_id": corpus, "source_locator": locator, "descriptor": record["descriptor"], "state": "ready",
            "canonical_custom_id": record["descriptor"]["custom_id"]})
    content = {"rows": rows}
    chunk = {"artifact": digest(content), "rows": count, "archive_path": archive.name}
    binding = {"partition": partition, "contract_sha256": snapshot.contract_sha256, "model": runner.core.MODEL,
               "reasoning_effort": "none", "max_output_tokens": 4096}
    result = {"binding": binding, "binding_sha256": digest(binding), "corpus_id": corpus,
              "versions": {"protocol": "d" * 64}, "shard_plan_artifact": "f" * 64,
              "totals": {"rows": count, "requests": count}}
    manifest = {"binding_sha256": result["binding_sha256"], "corpus_id": corpus,
                "manifest_sha256": manifest_hash, "versions": result["versions"],
                "shard_plan_artifact": "f" * 64, "prospective_request_count": count,
                "descriptor_chunks": [chunk]}
    return {"result": result, "manifest": manifest, "chunks": [{"descriptor": chunk, "content": content}],
            "source_result": "e" * 64}, partition


def fixture(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    exports, partitions = {}, {}
    for corpus in ("incident-reports", "cybercrime"):
        exports[corpus], partitions[corpus] = synthetic_export(data, corpus)
    categories = ["sealed_body_validation", "stopped_extraction", "prior_speed_attempt", "unresolved_prior_attempt"]
    exports["eligibility"] = {"completed": True, "categories": categories,
        "category_counts": {key: 0 for key in categories}, "rows": [],
        "sealed_body_hashes": [], "sealed_body_hash_count": 0,
        "partition": {"file_sha256": {f"corpora/{corpus}/manifest.json": value["manifest_sha256"]
                                      for corpus, value in partitions.items()}},
        "source_owner": "synthetic-original-owner", "original_result": "a" * 64,
        "protocol": "b" * 64, "created_at": "2026-01-01T00:00:00Z"}
    owner = tmp_path / "protected-owner"
    monkeypatch.setattr(runner, "OWNER", owner)
    monkeypatch.setattr(runner, "offline_tokenizer", SyntheticEncoder)
    monkeypatch.setattr(runner, "read_partition", lambda root, corpus: deepcopy(partitions[corpus]))

    def load(engine, session, name):
        kinds = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM records")}
        assert {"protocol", "question", "selection", "dossier_definition", "codebook", "prompt", "profile", "model_profile"} <= kinds
        engine.ledger.append(session, "test.protected_export.read", {"name": name})
        return deepcopy(exports[name]), runner.save(engine, session, exports[name], "Synthetic original-owner export")

    monkeypatch.setattr(runner, "read_export", load)
    return owner, data, exports, partitions


def execute(engine, data):
    return engine.execute("status", {"data_root": str(data)}, objective="Test synthetic bounded preparation", actor="test:software")


def test_registered_audited_preparation_exact_fulltext_and_no_models(tmp_path, monkeypatch):
    owner, data, _, _ = fixture(tmp_path, monkeypatch)
    engine = runner.PreparationResearch(owner)
    try:
        result = execute(engine, data)
        assert result["pending_requests"] == 20
        assert len(result["canary_tasks"]) == 16
        assert result["model_calls"] == result["uploads"] == result["embeddings"] == 0
        assert result["operational_limit_nanousd"] == 120_000_000_000
        assert result["ceiling_nanousd"] == 150_000_000_000
        assert result["price_policy"]["observed_at"] == "2026-10-17T15:06:17Z"
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
        for task in result["canary_tasks"]:
            request = engine.ledger.artifacts.read(task["request_ref"])
            body = engine.ledger.artifacts.read(task["request_body_ref"])
            packet = engine.ledger.artifacts.read(task["packet_ref"])
            assert body == request["body"]
            assert digest(body) == task["descriptor"]["request_body_sha256"]
            assert digest(packet) == task["descriptor"]["packet_sha256"]
            assert body["max_output_tokens"] == 4096
            assert packet["source_map"]["source_fields"]["body"]["text"].endswith("Entire second paragraph. ")
        for corpus, value in result["corpora"].items():
            queue = engine.ledger.artifacts.read(value["queue_ref"])
            assert queue["corpus_id"] == corpus
            assert len(queue["items"]) == 10
            assert queue["items"] == sorted(queue["items"], key=lambda item: (digest({"seed": runner.SEED, "row_id": item["row_id"]}), item["row_id"]))
        assert "unjudged" in result["markdown"]
        assert "synthetic.example" in result["markdown"]
    finally:
        engine.close()


def test_second_plan_preparation_is_blocked(tmp_path, monkeypatch):
    owner, data, _, _ = fixture(tmp_path, monkeypatch)
    engine = runner.PreparationResearch(owner)
    try:
        execute(engine, data)
        with pytest.raises(ResearchError, match="already_prepared"):
            execute(engine, data)
    finally:
        engine.close()


def test_global_sealed_hash_set_aside_without_losing_denominator(tmp_path, monkeypatch):
    owner, data, exports, _ = fixture(tmp_path, monkeypatch)
    row = exports["cybercrime"]["chunks"][0]["content"]["rows"][0]
    exports["eligibility"]["sealed_body_hashes"] = [row["descriptor"]["retained_body_sha256"]]
    exports["eligibility"]["sealed_body_hash_count"] = 1
    engine = runner.PreparationResearch(owner)
    try:
        result = execute(engine, data)
        assert result["pending_requests"] == 19
        assert result["corpora"]["cybercrime"]["summary"]["archive_rows"] == 10
        assert result["corpora"]["cybercrime"]["summary"]["dispositions"]["set_aside"] == 1
        assert row["descriptor"]["custom_id"] not in {task["custom_id"] for task in result["canary_tasks"]}
    finally:
        engine.close()


def test_descriptor_hash_tampering_stops_before_canary_source_reads(tmp_path, monkeypatch):
    owner, data, exports, _ = fixture(tmp_path, monkeypatch)
    exports["incident-reports"]["chunks"][0]["content"]["rows"][0]["state"] = "alias"
    called = []
    monkeypatch.setattr(runner, "materialize_canaries", lambda *args: called.append(True))
    engine = runner.PreparationResearch(owner)
    try:
        with pytest.raises(AuditError, match="chunk_hash"):
            execute(engine, data)
        assert not called
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='luna_budget_execution_plan'").fetchone()[0] == 0
    finally:
        engine.close()


def test_archive_drift_stops_before_model_dispatch(tmp_path, monkeypatch):
    owner, data, _, _ = fixture(tmp_path, monkeypatch)
    (data / "incident-reports.zip").write_bytes(b"changed synthetic archive")
    engine = runner.PreparationResearch(owner)
    try:
        with pytest.raises(AuditError, match="archive_precheck"):
            execute(engine, data)
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    finally:
        engine.close()


def test_wrong_owner_or_online_config_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "OWNER", tmp_path / "expected")
    with pytest.raises(ResearchError, match="fixed_offline_owner"):
        runner.PreparationResearch(tmp_path / "wrong")
    with pytest.raises(ResearchError, match="fixed_offline_owner"):
        runner.PreparationResearch(tmp_path / "expected", config=Config(offline=False))


def test_queue_lookup_refuses_wrong_custom_id(tmp_path):
    export, _ = synthetic_export(tmp_path, "incident-reports")
    with pytest.raises(AuditError, match="locator_changed"):
        runner.queued_row(export, {"row_id": "x", "custom_id": "y", "chunk_index": 0, "row_index": 0})


def test_frozen_export_hashes_are_valid_sha256():
    assert all(len(value["sha256"]) == 64 and set(value["sha256"]) <= set("0123456789abcdef")
               for value in runner.EXPORTS.values())
