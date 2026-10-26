"""Synthetic tests only: exact cap, blind requests, holds and paired metrics."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import sys

import pytest

from newsresearch.common import Config, ResearchError, digest
import test_luna_speed_workflow as prior

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_paired_fast_ten as paired
finally:
    sys.path.pop(0)


class FixturePaired(paired.PairedResearch):
    def load_inputs(self, session, data):
        packet, output = paired.contract.fictional_example()
        rows = []
        for index in range(10):
            variant = paired.contract.build_input({"title": packet["source_map"]["source_fields"]["title"]["text"],
                "body": packet["source_map"]["source_fields"]["body"]["text"] + f"\nFictional fixture {index}."})
            assert paired.contract.validate_output(output, variant) == []
            rows.append({"source_version": digest(index), "custom_id": str(index), "packet": variant,
                "title": f"Fictional {index}", "url": "https://example.invalid/fictional", "batch_output": deepcopy(output),
                "batch_status": "valid", "batch_errors": [], "batch_assessment": digest(["baseline", index]),
                "original_packet_ref": digest(variant)})
        executable = self.ledger.root / "fictional-codex.exe"
        executable.write_bytes(b"non-executable synthetic test fixture")
        return rows, {"codex_executable": str(executable), "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest()}, {"synthetic": True}


@pytest.mark.parametrize("unknown", [False, True])
def test_ten_cap_blinding_append_only_and_no_restart(tmp_path, monkeypatch, unknown):
    for variable in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(variable, raising=False)
    engine = FixturePaired(tmp_path / "private", config=Config(offline=True))
    seen = prior.mock_runner(monkeypatch, unknown=unknown)
    try:
        plan = prior.call(engine, "status", {"phase": "prepare"})
        assert plan["model_calls"] == 0 and plan["articles"] == 10
        engine.config = replace(engine.config, offline=False)
        payload = {"phase": "run", "plan": plan["id"], "authorization_text": "Ten synthetic calls only"}
        result = prior.call(engine, "status", payload)
        assert len(seen) <= 10
        assert all('"batch_output"' not in item["input"] and '"batch_assessment"' not in item["input"] for item in seen)
        if unknown:
            assert result["unattempted"] > 0 and result["fast_raw_valid"] == 0
            assert engine.ledger.unresolved and result["timing"]["stop_reason"] == "transport_or_unknown_stop"
        else:
            assert len(seen) == 10 and result["attempted"] == 10 and result["unattempted"] == 0
            assert result["fast_counts"] == {"valid": 10}
            assert result["batch_raw_valid"] == result["fast_raw_valid"] == result["focus_agreements"] == 10
            assert result["timing"]["peak_in_flight"] <= 4
        with pytest.raises(ResearchError, match="spent_no_restart"):
            prior.call(engine, "status", payload)
        assert not result["semantic_accuracy_confirmed"] and not result["original_batch_records_changed"]
        engine.ledger.verify()
    finally:
        engine.close()


def test_selection_is_seeded_unique_completed_and_development_only():
    requests, results = {}, {}
    for index in range(13):
        key = str(index)
        requests[key] = {"corpus_id": "incident-reports", "descriptor": {"retained_body_sha256": str(index % 12)}}
        results[key] = {"status": "valid"}
    results["11"] = {"status": "unknown"}
    selected, _ = paired.choose_pairs(requests, results, {str(index) for index in range(10)})
    assert len(selected) == 10
    assert len({requests[key]["descriptor"]["retained_body_sha256"] for key in selected}) == 10
    assert "10" not in selected and "11" not in selected
    assert selected == paired.choose_pairs(dict(reversed(list(requests.items()))), results, {str(i) for i in range(10)})[0]


def test_agreement_is_not_accuracy_and_missing_is_not_agreement():
    _, output = paired.contract.fictional_example()
    changed = deepcopy(output)
    changed["event"]["action"]["surface"] = "different literal"
    result = paired.pair_metrics(output, changed)
    assert result["focus_agrees"] and not result["exact_json_equal"] and not result["action_literal_agrees"]
    assert paired.pair_metrics(None, None)["focus_agrees"] is False
