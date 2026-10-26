"""Prospective diagnostic bounds; real selected readers, synthetic owners only."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import time

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_recall_source_v2 as subject
import test_luna_recall_source as original_tests
from test_final_validation_inventory import bytes_snapshot

retained = original_tests.retained


class Consumer(Research):
    imported = None

    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(), "binding": data["binding"]}})
        self.imported = subject.collect(self, session, **data, deadline_monotonic=time.monotonic() + 1200)
        return {"artifact": self.ledger.artifacts.put(self.imported)}


def test_actual_retained_import_required_history_before_optional_diagnostics(tmp_path, retained, monkeypatch):
    data, source, _ = retained
    owners = [Path(data["audit_owner"]), Path(source["provenance"]["source_owner"])]
    before = [bytes_snapshot(p) for p in owners]
    original = subject._optional_phases
    checked = []

    def after_required(reader, report):
        intended = [subject.json.loads(r[0]) for r in reader.db.execute(
            "SELECT payload FROM events WHERE kind='model.attempt.intended'")]
        responses = reader.rows("cyber_dossier_response")
        required = {r["parsed"] for r in responses if r.get("parsed")}
        required.update(r["packet"] for r in intended if r["phase"] in {"seed", "audit", "summary"})
        assert required <= set(reader.copied)
        checked.append(len(intended))
        return original(reader, report)

    monkeypatch.setattr(subject, "_optional_phases", after_required)
    monkeypatch.setattr(subject.frozen, "load_frozen", lambda *a, **k: pytest.fail("old source rescan"))
    engine = Consumer(tmp_path / "consumer", config=Config(offline=True))
    try:
        engine.execute("status", data, objective="Synthetic v2 retained import", actor="test")
        loaded = engine.imported
        assert loaded["documents"] == source["documents"]
        history = loaded["prior_history"]
        assert checked == [4] and len(history["attempts"]) == 4
        assert len(history["membership_attempts"]) == 2 and any(r["hold"] for r in history["membership_attempts"])
        assert history["cards"]["g"][0]["document_ids"] == ["d000", "d001"]
        assert loaded["precheck"]["matched_observations"] >= 1
        assert history["phase_refs"]["full_v6_outcome"]["unavailable_reason"] == "native_phase_unused_duplicate"
        assert "full_v6_outcome" not in history["native_phases"]
        assert loaded["diagnostic"]["recorded_reason_counts"]["multiple_positive_targets"] == 2
        assert not loaded["diagnostic"]["causal_attribution_claimed"]
        assert before == [bytes_snapshot(p) for p in owners]
    finally:
        engine.close()


class PhaseSource(Research):
    @audited_handler
    def _status(self, session, context, data):
        refs = {}
        for name, payload in data.items():
            reference = self.ledger.artifacts.put(payload)
            row = self.ledger.record(session, "cyber_dossier_phase", name,
                {"plan": "a" * 64, "name": name, "artifact": reference})
            refs[name] = {"record": row, "artifact": reference}
        return refs


class PhaseConsumer(Research):
    result = None
    reserve = 0

    @audited_handler
    def _status(self, session, context, data):
        reader = subject.Reader(self, session, data["owner"], deadline=time.monotonic() + 1200)
        try:
            reader.unique_bytes = self.reserve
            phases, refs, gaps = subject._optional_phases(reader, {"plan": "a" * 64})
            self.result = {"phases": phases, "refs": refs, "gaps": gaps, "copied": dict(reader.copied), "bytes": reader.unique_bytes}
            return {"artifact": self.ledger.artifacts.put(self.result)}
        finally:
            reader.close()


def phase_owner(tmp_path, values):
    engine = PhaseSource(tmp_path / "source", config=Config(offline=True))
    try:
        return engine.ledger.root, engine.execute("status", values, objective="Synthetic phase metadata", actor="test")
    finally:
        engine.close()


def phase_import(tmp_path, owner, reserve=0):
    engine = PhaseConsumer(tmp_path / "consumer", config=Config(offline=True))
    engine.reserve = reserve
    try:
        engine.execute("status", {"owner": str(owner)}, objective="Synthetic optional trace", actor="test")
        return engine.result
    finally:
        engine.close()


def test_exact_prospective_caps_and_v1_unchanged():
    assert subject.POLICY["maximum_selected_bytes"] == 1024**3
    assert subject.POLICY["maximum_optional_phase_bytes"] == 128 * 1024**2
    assert subject.POLICY["maximum_optional_diagnostic_bytes"] == 256 * 1024**2
    original = Path(subject.__file__).with_name("luna_recall_source.py")
    assert hashlib.sha256(original.read_bytes()).hexdigest() == "296b993529c27b87c2cdce877f46e2eb6a0a95618d9b8851cc13c3202d1209a7"


@pytest.mark.parametrize("mode", ["per_artifact", "aggregate", "remaining", "unused"])
def test_optional_body_skipped_before_read_with_exact_ref_and_size(tmp_path, monkeypatch, mode):
    name = "full_v6_outcome" if mode == "unused" else "full_v6_seed_assignments"
    values = {name: {"unresolved": {"d000": "x" * 100}}}
    owner, refs = phase_owner(tmp_path, values)
    reference = refs[name]["artifact"]
    size = (owner / "objects" / reference).stat().st_size
    policy = deepcopy(subject.POLICY)
    if mode == "per_artifact":
        policy["maximum_optional_phase_bytes"] = size - 1
    elif mode == "aggregate":
        policy["maximum_optional_diagnostic_bytes"] = size - 1
    reserve = 0
    if mode == "remaining":
        policy["maximum_selected_bytes"] = 10_000
        metadata_ref = digest({"plan": "a" * 64, "name": name, "artifact": reference})
        reserve = 10_000 - (owner / "objects" / metadata_ref).stat().st_size - size + 1
    monkeypatch.setattr(subject, "POLICY", policy)
    original = subject.Reader.artifact_bytes

    def no_body(self, ref):
        assert ref != reference, "skipped optional bytes were read"
        return original(self, ref)

    monkeypatch.setattr(subject.Reader, "artifact_bytes", no_body)
    result = phase_import(tmp_path, owner, reserve)
    fact = result["refs"][name]
    assert fact["record"] == refs[name]["record"] and fact["artifact"] == reference
    assert fact["observed_bytes"] == size and not fact["payload_hash_verified"] and not fact["payload_imported"]
    assert reference not in result["copied"] and name not in result["phases"]
    assert any(g.get("phase") == name and g.get("artifact") == reference for g in result["gaps"])
    source = {"groups": {"g": ["d000"], "h": ["d001"]}, "accepted_group_ids": ["g", "h"],
        "audit": {"labels": {digest(["d000", "d001"]): "same_event"},
            "source_pairs": {digest(["d000", "d001"]): ["d000", "d001"]}},
        "prior_history": {"native_phases": result["phases"], "gaps": result["gaps"]}}
    diagnosis = subject.diagnose(source)
    assert diagnosis["unattributed_misses"] == 1 and not diagnosis["causal_attribution_claimed"]


def test_optional_total_budget_is_cumulative_and_exact_boundary_imports(tmp_path, monkeypatch):
    values = {"full_v6_seed_assignments": {"unresolved": {"d000": "first"}},
        "full_v6_recovery_assignments": {"unresolved": {"d001": "other"}}}
    owner, refs = phase_owner(tmp_path, values)
    first = refs["full_v6_seed_assignments"]["artifact"]
    size = (owner / "objects" / first).stat().st_size
    monkeypatch.setattr(subject, "POLICY", {**subject.POLICY,
        "maximum_optional_phase_bytes": size, "maximum_optional_diagnostic_bytes": size})
    result = phase_import(tmp_path, owner)
    assert result["phases"] == {"full_v6_seed_assignments": values["full_v6_seed_assignments"]}
    assert result["refs"]["full_v6_seed_assignments"]["payload_hash_verified"]
    assert not result["refs"]["full_v6_recovery_assignments"]["payload_imported"]
    assert result["refs"]["full_v6_recovery_assignments"]["unavailable_reason"] == "native_phase_diagnostic_byte_limit"


def test_all_phase_metadata_precedes_optional_payload_at_reader_cap(tmp_path, monkeypatch):
    values = {"full_v6_seed_assignments": {"unresolved": {"d000": "first"}},
        "full_v6_recovery_assignments": {"unresolved": {"d001": "other"}}}
    owner, refs = phase_owner(tmp_path, values)
    first = refs["full_v6_seed_assignments"]["artifact"]
    metadata = [digest({"plan": "a" * 64, "name": name, "artifact": ref["artifact"]}) for name, ref in refs.items()]
    cap = sum((owner / "objects" / ref).stat().st_size for ref in metadata) + (owner / "objects" / first).stat().st_size
    monkeypatch.setattr(subject, "POLICY", {**subject.POLICY, "maximum_selected_bytes": cap})
    result = phase_import(tmp_path, owner)
    assert result["bytes"] == cap and set(result["refs"]) == set(refs)
    assert result["refs"]["full_v6_seed_assignments"]["payload_imported"]
    assert result["refs"]["full_v6_recovery_assignments"]["unavailable_reason"] == "native_phase_diagnostic_byte_limit"


@pytest.mark.parametrize("fault", ["hash", "acl", "link", "size_drift"])
def test_optional_integrity_or_permission_failure_is_not_an_unavailable_trace(tmp_path, monkeypatch, fault):
    owner, refs = phase_owner(tmp_path, {"full_v6_seed_assignments": {"unresolved": {}}})
    reference = refs["full_v6_seed_assignments"]["artifact"]
    path = owner / "objects" / reference
    if fault == "hash":
        path.write_bytes(b'{"changed":true}')
    elif fault == "acl":
        original = subject.check_permissions
        def denied(target, *args, **kwargs):
            if target == path:
                raise AuditError("synthetic ACL refusal")
            return original(target, *args, **kwargs)
        monkeypatch.setattr(subject, "check_permissions", denied)
    elif fault == "link":
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: True if p == path else original(p))
    else:
        original = subject.Reader.artifact_size
        monkeypatch.setattr(subject.Reader, "artifact_size", lambda self, ref: original(self, ref) + 1)
    with pytest.raises(AuditError):
        phase_import(tmp_path, owner)


def test_required_import_still_fails_closed_at_same_reader_limit(tmp_path, retained, monkeypatch):
    monkeypatch.setattr(subject, "POLICY", {**subject.POLICY, "maximum_selected_bytes": 1})
    monkeypatch.setattr(subject, "_optional_phases", lambda *a: pytest.fail("optional processing preceded required import"))
    engine = Consumer(tmp_path / "consumer", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="selected_byte_limit"):
            engine.execute("status", retained[0], objective="Synthetic required bound", actor="test")
        assert engine.imported is None
    finally:
        engine.close()
