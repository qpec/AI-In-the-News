import copy
import io
from types import SimpleNamespace
import zipfile

import pytest

from newsresearch import newsapi_id_manifest as dispatch_module
from newsresearch import newsapi_id_manifest_resolution_run as module
from newsresearch.common import AuditError, Context, ResearchError, canonical
from test_newsapi_id_manifest_resolution import IDS, CONTROL, article, info, listing, receipt


def package():
    preparation = {"id": "prepared", "metadata_ids": IDS, "control_uri": CONTROL, "source_audit": "source"}
    planned = module.helpers.templates(IDS, CONTROL)
    errors = {uri: {"error": f"Invalid article uri ('{uri}') was provided."} for uri in IDS}
    sdk_response = {**errors, **info([CONTROL])}
    list_response = listing([CONTROL])
    block = {"windows": [{"ascending": {"ids": ["earlier-1"]}}, {"ascending": {"ids": ["earlier-2"]}}]}
    saved = ["earlier-1", "earlier-2", CONTROL]
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("years/2026/saved-ids.txt", "\n".join(saved))
        archive.writestr("source-block-proof.json", canonical(block))
    page = receipt(1, [CONTROL], 1)
    page["id"] = "page"
    controls = module.helpers.parse_controls(sdk_response, list_response, IDS, CONTROL, errors)
    enumeration = module.helpers.validate_enumeration([page], [CONTROL])
    summary = module._reconcile({"_proof_bytes": inner.getvalue()}, preparation, controls, enumeration)
    docs = {
        "resolution-verification.json": {"preparation": preparation, "lookups": {"sdk": "sdk", "list": "list"}, "pages": ["page"]},
        "versions/policy.json": {"content": {"resolution_method": module.RESOLUTION_METHOD, "resolution_templates": planned["all"], "resolution_preparation": "prepared", "resolution_source": "source", "authorization_id": module.AUTH_ID, "max_tokens": 583}},
        "prior-final-audit.json": {"id": "source", "metadata_ids": IDS, "metadata_receipts": ["old"]},
        "years/2026/saved-ids.txt": "\n".join(saved), "source-block-proof.json": block,
    }
    for name, parameters, response in (("old", {}, errors), ("sdk", planned["control_sdk"], sdk_response),
            ("list", planned["control_list"], list_response), ("page", module.helpers.enumeration(1), page["response"])):
        docs[f"receipts/{name}.json"] = {"id": name, "parameters": parameters, "outcome": "received", "http_status": 200,
            "headers": {"req-archive": "1"}, "response": response, "raw_response": "retained"}
        docs[f"responses/{name}.json"] = response
    class Archive:
        def __init__(self, values):
            self.values = values
        def read(self, name):
            value = self.values[name]
            return value.encode() if isinstance(value, str) else canonical(value).encode()
    return docs, Archive, {"resolution_summary": summary, "prior_final_audit": "source"}


def test_resolution_replays_lookup_errors_and_complete_metadata_population():
    docs, archive_type, comparison = package()
    checked = module.verify_resolution_package(archive_type(docs), comparison)
    assert checked["metadata_enumeration_complete"] and checked["retrievable_2026_complete"]
    summary = comparison["resolution_summary"]
    assert summary["retrievable_2026_count"] == 3
    assert summary["retrievable_2026_saved_coverage_percent"] == 100
    assert summary["candidate_resolution"]["provider_unresolvable_ids"] == IDS
    assert not summary["candidate_resolution"]["raw_uri_disagreement_resolved"]
    for target in ("responses/sdk.json", "responses/old.json"):
        changed = copy.deepcopy(docs)
        changed[target][IDS[0]]["error"] = "Unknown provider error"
        with pytest.raises(AuditError, match="reproduce"):
            module.verify_resolution_package(archive_type(changed), comparison)
    changed = copy.deepcopy(docs)
    changed["responses/page.json"]["articles"]["results"].append(article(IDS[0]))
    with pytest.raises(AuditError, match="reproduce"):
        module.verify_resolution_package(archive_type(changed), comparison)


def test_resolution_dispatch_cannot_bypass_shared_cap_or_template_registration(monkeypatch):
    parameters = module.helpers.templates(IDS, CONTROL)["control_sdk"]
    policy = {"authorization_id": module.AUTH_ID, "max_tokens": 583, "resolution_method": module.RESOLUTION_METHOD, "resolution_templates": []}
    engine = SimpleNamespace(_active={"session"}, ledger=SimpleNamespace(get=lambda *args: {"content": policy}))
    context = Context("Validate budget", "test", {"policy": "p"})
    with pytest.raises(ResearchError, match="exact registered"):
        dispatch_module.dispatch(engine, "session", context, parameters, "resolution_sdk_control")
    policy["resolution_templates"] = [parameters]
    monkeypatch.setattr(dispatch_module, "records", lambda engine, kind: [{"attempt": "reserved", "reserved_tokens": 580}] if kind == "newsapi_id_intent" else [])
    with pytest.raises(ResearchError, match="budget"):
        dispatch_module.dispatch(engine, "session", context, parameters, "resolution_sdk_control")


def test_audit_failure_stops_resolution_without_usage_or_proof_followups(monkeypatch):
    versions = {"policy": "p", "protocol": "r", "question": "q", "selection": "s", "profile": "f"}
    prepared = {"source_audit": "source", "metadata_ids": IDS, "control_uri": CONTROL}
    policy = {"authorization_id": module.AUTH_ID, "max_tokens": 583, "resolution_method": module.RESOLUTION_METHOD,
        "resolution_source": "source", "resolution_preparation": "prep", "resolution_templates": module.helpers.templates(IDS, CONTROL)["all"]}
    values = {"p": {"content": policy}, "prep": prepared, "source": {"versions": versions}}
    engine = SimpleNamespace(_active={"session"}, _require=lambda *args: None,
        config=SimpleNamespace(offline=False), ledger=SimpleNamespace(get=lambda identifier, kind: values[identifier]))
    monkeypatch.setattr(module, "records", lambda *args: [])
    def fail(*args):
        raise AuditError("Storage failed")
    monkeypatch.setattr(module, "dispatch", fail)
    with pytest.raises(AuditError, match="Storage failed"):
        module.run(engine, "session", Context("Validate failure stop", "test", versions), {"execute": True})
