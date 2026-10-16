"""Move one frozen Luna execution into a complete, bounded protected workspace.

The original store remains the historical authority. This transfers execution
ownership, not history ownership, and never synthesizes prior model dispatches.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterator
import uuid

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, utc
from .storage import Artifacts, check_permissions, prepare_root

METHOD = "luna-bounded-study-transfer-v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
LINK_FIELDS = ("plan", "original_result", "approval_policy", "batch", "assessment",
               "revalidation", "control_amendment")
LOCAL_ARTIFACT_FIELDS = {
    "session.started": ("identity",), "operation.intended": ("input",),
    "operation.completed": ("result",), "record.created": ("artifact",),
    "sources.imported": ("raw_ref",), "model.attempt.intended": ("request", "dispatch"),
    "model.attempt.completed": ("response",), "export.write_intended": ("artifact",),
    "preparation.artifact.saved": ("artifact",), "embedding.request.prepared": ("request", "wire_body"),
    "embedding.context.saved": ("artifact",), "embedding.response.received": ("artifact",),
    "retrieval.artifact.saved": ("artifact",), "tagging.artifact.saved": ("artifact",),
    "presentation.artifact.saved": ("artifact",), "codex.response.received": ("artifact",),
}


def _hashes(value: Any) -> Iterator[str]:
    if isinstance(value, str) and HEX.fullmatch(value):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _hashes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _hashes(child)


def _spend(attempts: list[Json]) -> tuple[int, int]:
    seen: set[str] = set()
    exposures = 0
    for item in attempts:
        intended = item["original_intended"]
        count = intended["article_exposures"]
        if (item["original_attempt"] in seen or type(count) is not int or count < 1
                or item["original_attempt"] != intended["attempt"]):
            raise AuditError("luna_transfer_budget_history_invalid")
        seen.add(item["original_attempt"])
        exposures += count
    if len(seen) > 400 or exposures > 6000:
        raise AuditError("luna_transfer_budget_history_invalid")
    return len(seen), exposures


def _event(ledger: Any, number: int) -> Json:
    row = ledger.db.execute("SELECT * FROM events WHERE seq=?", (number,)).fetchone()
    if row is None:
        raise AuditError("luna_transfer_missing_provenance_event")
    event = dict(row)
    event["payload"] = json.loads(event["payload"])
    expected = event.pop("event_hash")
    if digest(event) != expected:
        raise AuditError("luna_transfer_provenance_event_changed")
    return {**event, "event_hash": expected}


def _record_spec(ledger: Any, identifier: str) -> Json:
    row = ledger.db.execute("SELECT * FROM records WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise AuditError("luna_transfer_missing_required_record")
    return {"id": identifier, "kind": row["kind"], "logical_key": row["logical_key"],
            "artifact": row["artifact"], "supersedes": row["supersedes"],
            "original_event": _event(ledger, row["created_event"])}


def _records(ledger: Any, seeds: list[str]) -> list[Json]:
    """Deliberate record closure; opaque historical group/index links stay external."""
    found: dict[str, Json] = {}
    pending = list(seeds)
    while pending:
        identifier = pending.pop()
        if identifier in found:
            continue
        spec = _record_spec(ledger, identifier)
        found[identifier] = spec
        payload = ledger.get(identifier, spec["kind"])
        if spec["supersedes"]:
            pending.append(spec["supersedes"])
        pending.extend(value for value in payload.get("versions", {}).values() if isinstance(value, str))
        if spec["kind"].startswith("luna_"):
            for key in LINK_FIELDS:
                value = payload.get(key)
                if isinstance(value, str) and ledger.db.execute(
                        "SELECT 1 FROM records WHERE id=?", (value,)).fetchone():
                    pending.append(value)
            for outcome in payload.get("outcomes", {}).values():
                pending.extend(outcome[key] for key in ("assessment", "revalidation") if outcome.get(key))
            diagnostic = payload.get("diagnostic")
            if isinstance(diagnostic, dict) and diagnostic.get("id"):
                pending.append(diagnostic["id"])
    return sorted(found.values(), key=lambda item: item["original_event"]["seq"])


def _copy_closure(engine: Any, session: str, destination: Path, roots: set[str]) -> list[Json]:
    """Copy and hash each selected parent file once; inspect copied JSON for links."""
    incoming = engine.ledger.artifacts.root
    staging = prepare_root(destination.parent / "transfer-staging")
    available = {path.name for path in incoming.iterdir()}
    copied: dict[str, Json] = {}
    pending = list(roots)
    while pending:
        reference = pending.pop()
        if reference in copied:
            continue
        if not HEX.fullmatch(reference) or reference not in available:
            raise AuditError("luna_transfer_required_artifact_missing")
        source, target = incoming / reference, destination / reference
        check_permissions(source)
        size = 0
        if target.exists():
            check_permissions(target)
            with target.open("rb") as reader:
                if hashlib.file_digest(reader, "sha256").hexdigest() != reference:
                    raise AuditError("luna_transfer_existing_artifact_hash_mismatch")
            size = target.stat().st_size
        else:
            temporary = staging / (reference + "." + uuid.uuid4().hex + ".partial")
            hasher = hashlib.sha256()
            with source.open("rb") as reader, temporary.open("xb") as writer:
                if os.name != "nt":
                    temporary.chmod(0o600)
                while chunk := reader.read(1024 * 1024):
                    hasher.update(chunk)
                    size += len(chunk)
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            if hasher.hexdigest() != reference:
                raise AuditError("luna_transfer_artifact_hash_mismatch")
            # An interrupted copy cannot leave a partial content-addressed file.
            # link() creates the final name without replacing an existing file.
            os.link(temporary, target)
            temporary.unlink()  # Only this invocation's known completed staging file.
        check_permissions(target)
        copied[reference] = {"sha256": reference, "bytes": size}
        # Read the already hash-verified child copy, not the parent, for closure.
        with target.open("rb") as stream:
            first = stream.read(1)
            while first and first in b" \t\r\n":
                first = stream.read(1)
            if first in (b"{", b"["):
                stream.seek(0)
                try:
                    value = json.load(stream)
                except (ValueError, UnicodeError):
                    pass  # A binary artifact can coincidentally start with '['.
                else:
                    pending.extend(set(_hashes(value)) & available - copied.keys())
    engine.ledger.append(session, "luna.study.transfer.artifacts.copied", {
        "artifacts": len(copied), "bytes": sum(item["bytes"] for item in copied.values()),
        "destination": str(destination.parent), "full_content_hashes_verified": True})
    return sorted(copied.values(), key=lambda item: item["sha256"])


def _present(engine: Any, session: str, context: Context, result: Json) -> Json:
    identifier = engine.ledger.record(session, "luna_study_transfer_result", digest(result), result)
    markdown = (f"Luna bounded-workspace transfer: {result['state']}.\n\n"
        f"Study {result['study_key']}: {result['sources']} complete source versions; "
        f"{result['passages']} exact passages; {result['records']} immutable records; "
        f"{result['artifacts']} artifacts / {result['artifact_bytes']:,} bytes. "
        f"Prior spend retained: {result['prior_attempts']}/400 attempts and "
        f"{result['prior_article_exposures']}/6,000 article exposures. No retries or new models.\n\n"
        f"Target: {result['child_workspace']}. Parent head: {result['parent_head_hash']}. "
        "The parent history remains retained. The bounded workspace verifies its complete own contents; "
        "it does not reverify omitted parent embedding history. Group memberships remain unchanged.")
    presentation = engine._record_presentation(session, context, {
        "results": [{"kind": "luna_study_transfer_result", "id": identifier}],
        "markdown": markdown, "destination": "codex_chat", "status": "prepared_for_delivery"})
    return {"id": identifier, **result, "presentation": presentation}


def export(engine: Any, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    study, original_result = data["study_key"], data["original_result"]
    instruction = data["authorization_instruction"]
    if any(not isinstance(value, str) or not value.strip() for value in (study, original_result, instruction)):
        raise ResearchError("luna_transfer_concrete_authorization_required")
    child = Path(data["child_workspace"]).expanduser().absolute()
    parent = engine.ledger.root
    previous = engine.ledger.db.execute("SELECT id FROM records WHERE kind='study_execution_ownership' "
        "AND logical_key=? ORDER BY created_event DESC LIMIT 1", (study,)).fetchone()
    resumed: Json | None = None
    initial_seal: str | None = None
    if previous:
        resumed = engine.ledger.get(previous[0], "study_execution_ownership")
        if (data.get("resume_transfer") is not True or resumed["status"] != "transferred_away"
                or Path(resumed["owner_workspace"]).absolute() != child
                or resumed["original_result"] != original_result
                or resumed["parent_provenance"]["workspace"] != str(parent)):
            raise ResearchError("luna_transfer_ownership_already_assigned")
        initial_seal = resumed.get("initial_ownership", previous[0])
        if resumed.get("copy_complete") is True:
            row = engine.ledger.db.execute("SELECT id FROM records WHERE kind='luna_study_transfer_result' "
                "AND json_extract(payload,'$.transfer_id')=? AND json_extract(payload,'$.state')=? "
                "ORDER BY created_event DESC LIMIT 1", (resumed["transfer_id"], "exported_parent_execution_sealed")).fetchone()
            if row:
                result = engine.ledger.get(row[0], "luna_study_transfer_result")
                bound = Context(context.objective, context.actor, result["versions"])
                return _present(engine, session, bound, result)
    if ((child.exists() and resumed is None) or child == parent
            or child in parent.parents or parent in child.parents):
        raise ResearchError("luna_transfer_destination_must_be_new_and_disjoint")
    code = Path(__file__).read_bytes()
    method = engine._version(session, context, {"kind": "protocol", "key": study + "-bounded-transfer",
        "content": {"method": METHOD, "authorization_instruction": instruction,
            "implementation_sha256": hashlib.sha256(code).hexdigest(), "implementation_source": code.decode(),
            "max_requests": 400, "max_article_exposures": 6000, "automatic_retries": 0,
            "parent_retained": True, "all_child_contents_verified": True,
            "omitted_parent_history_reverified_in_child": False}})["id"]
    old = engine.ledger.get(original_result, "luna_group_validation_result")
    plan_id = old["plan"]
    plan = engine.ledger.get(plan_id, "luna_group_validation_plan")
    if old["study_key"] != study or plan["study_key"] != study or old["versions"] != plan["versions"]:
        raise ResearchError("luna_transfer_plan_study_mismatch")
    bound = Context(context.objective, context.actor, plan["versions"])
    authorizations = [_event(engine.ledger, row[0]) for row in engine.ledger.db.execute(
        "SELECT seq FROM events WHERE kind='luna.validation.authorization.bound' "
        "AND json_extract(payload,'$.study_key')=?", (study,))]
    if not authorizations or any(item["payload"]["binding"] != authorizations[0]["payload"]["binding"]
                                 for item in authorizations):
        raise ResearchError("luna_transfer_original_authorization_missing_or_changed")
    binding = authorizations[0]["payload"]["binding"]
    if binding["plan"] != plan_id or binding["versions"] != plan["versions"]:
        raise ResearchError("luna_transfer_authorization_binding_mismatch")
    if resumed is not None:
        if resumed["plan"] != plan_id:
            raise ResearchError("luna_transfer_resume_plan_changed")
        method = resumed["protocol"]
    seeds = [method, original_result, plan_id, binding["approval_policy"], *plan["versions"].values()]
    seeds.extend(item["payload"]["record"] for item in authorizations if item["payload"].get("record"))
    attempts = []
    for row in engine.ledger.db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.intended' "
            "AND json_extract(payload,'$.luna_validation_study')=?", (study,)):
        intended = json.loads(row["payload"])
        status_row = engine.ledger.db.execute("SELECT status,result_id FROM attempts WHERE id=?", (intended["attempt"],)).fetchone()
        status, assessment = (status_row[0], status_row[1]) if status_row else ("unknown", None)
        if assessment:
            seeds.append(assessment)
        seeds.append(intended["batch"])
        attempts.append({"study_key": study, "original_attempt": intended["attempt"],
            "original_intended": intended, "status": status, "assessment": assessment,
            "parent_provenance": {"workspace": str(parent), "original_event": _event(engine.ledger, row["seq"])}})
    spent, exposures = _spend(attempts)
    if spent != old["workflow_model_attempts"] or exposures != old["workflow_article_exposures"]:
        raise ResearchError("luna_transfer_budget_history_mismatch")
    records = _records(engine.ledger, seeds)
    dataset = engine.ledger.get(plan["versions"]["dataset"], "dataset")
    source_ids = dataset["source_versions"]
    if not source_ids or len(source_ids) > engine.config.max_articles or len(set(source_ids)) != len(source_ids):
        raise ResearchError("luna_transfer_dataset_frame_invalid")
    sources: list[Json] = []
    passages: list[Json] = []
    source_events: dict[str, Json] = {}
    roots = {item["artifact"] for item in records}
    roots.update(task["request_ref"] for task in plan["tasks"] if task.get("request_ref"))
    if plan.get("retrieval_artifact"):
        roots.add(plan["retrieval_artifact"])
    for spec in records:
        if spec["kind"] in {"luna_lead_assessment", "luna_lead_revalidation", "luna_validation_batch",
                            "luna_group_validation_result"}:
            value = engine.ledger.get(spec["id"], spec["kind"])
            roots.update(value[key] for key in ("request", "response", "manifest") if value.get(key))
    for source_id in source_ids:
        row = engine.ledger.db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise AuditError("luna_transfer_dataset_source_missing")
        event_key = str(row["created_event"])
        if event_key not in source_events:
            source_events[event_key] = _event(engine.ledger, row["created_event"])
        sources.append({"id": row["id"], "source_key": row["source_key"], "raw_ref": row["raw_ref"],
            "raw_index": row["raw_index"], "original_event_seq": row["created_event"]})
        roots.add(row["raw_ref"])
        original = json.loads(row["payload"])
        if original.get("original_artifact"):
            roots.add(original["original_artifact"])
        passages.extend(dict(item) for item in engine.ledger.db.execute(
            "SELECT id,source_id,start,end,text_hash FROM passages WHERE source_id=? ORDER BY start,id", (source_id,)))
    for item in attempts:
        roots.update(item["original_intended"][key] for key in ("request", "dispatch"))
    head = engine.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    nonce = resumed["transfer_nonce"] if resumed is not None else uuid.uuid4().hex
    transfer_id = resumed["transfer_id"] if resumed is not None else digest({
        "study": study, "parent": str(parent), "head": head[1], "child": str(child), "nonce": nonce})
    provenance = resumed["parent_provenance"] if resumed is not None else {
        "workspace": str(parent), "head_seq": head[0], "head_hash": head[1],
        "export_session": session, "observed_at": utc(), "full_parent_preflight_performed": True}
    holdout_events = [_event(engine.ledger, row[0]) for row in engine.ledger.db.execute(
        "SELECT seq FROM events WHERE kind='luna.validation.holdout.opened' AND json_extract(payload,'$.study_key')=?", (study,))]
    # This immutable seal precedes any child write. Any later failure leaves the
    # parent execution blocked; recovery cannot silently create another owner.
    ownership = {"study_key": study, "status": "transferred_away", "owner_workspace": str(child),
        "child_workspace": str(child), "allowed_operations": ["luna_group_validation_continue"],
        "transfer_id": transfer_id, "transfer_nonce": nonce, "nonce": nonce,
        "original_result": original_result, "plan": plan_id, "parent_provenance": provenance,
        "protocol": method}
    seal = initial_seal or engine.ledger.record(session, "study_execution_ownership", study, ownership)
    engine.ledger.append(session, "luna.study.transfer.intended", {**ownership, "ownership_record": seal})
    child = prepare_root(child)
    child_artifacts = Artifacts(child)
    artifacts = _copy_closure(engine, session, child_artifacts.root, roots)
    package = {"method": METHOD, "transfer_id": transfer_id, "transfer_nonce": nonce,
        "study_key": study, "original_result": original_result, "plan": plan_id,
        "child_workspace": str(child), "parent_provenance": provenance, "parent_ownership": seal,
        "versions": plan["versions"], "records": records, "sources": sources, "source_events": source_events,
        "passages": passages,
        "prior_attempts": attempts, "authorizations": authorizations, "holdout_events": holdout_events,
        "artifacts": artifacts, "prior_spend": {"attempts": len(attempts), "article_exposures": exposures},
        "limits": {"attempts": 400, "article_exposures": 6000, "automatic_retries": 0},
        "opaque_parent_ancestry": "Parent group/vector ancestry remains in retained parent; not reverified here"}
    manifest = engine.ledger.artifacts.put(package)
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": manifest, "purpose": METHOD})
    if child_artifacts.put(package) != manifest:
        raise AuditError("luna_transfer_manifest_copy_mismatch")
    completed_seal = engine.ledger.record(session, "study_execution_ownership", study,
        {**ownership, "manifest": manifest, "copy_complete": True, "initial_ownership": seal}, supersedes=seal)
    summary = {"state": "exported_parent_execution_sealed", "study_key": study, "versions": plan["versions"],
        "child_workspace": str(child), "manifest": manifest, "transfer_id": transfer_id, "transfer_nonce": nonce,
        "parent_ownership": completed_seal, "parent_head_hash": provenance["head_hash"],
        "sources": len(sources), "passages": len(passages), "records": len(records),
        "artifacts": len(artifacts), "artifact_bytes": sum(item["bytes"] for item in artifacts),
        "prior_attempts": len(attempts), "prior_article_exposures": exposures,
        "new_model_calls": 0, "membership_changes": 0,
        "import_input": {"manifest": manifest, "study_key": study, "transfer_nonce": nonce}}
    return _present(engine, session, bound, summary)


def import_into(engine: Any, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    ledger = engine.ledger
    if (not isinstance(data.get("study_key"), str) or not data["study_key"].strip()
            or not isinstance(data.get("manifest"), str) or not HEX.fullmatch(data["manifest"])
            or not isinstance(data.get("transfer_nonce"), str) or not data["transfer_nonce"].strip()):
        raise ResearchError("luna_transfer_import_binding_missing")
    prior = ledger.db.execute("SELECT id FROM records WHERE kind='study_execution_ownership' "
        "AND logical_key=? ORDER BY created_event DESC LIMIT 1", (data["study_key"],)).fetchone()
    if prior:
        owner = ledger.get(prior[0], "study_execution_ownership")
        if (owner["status"] not in {"import_pending", "imported_owner"}
                or owner["manifest"] != data["manifest"] or owner["transfer_nonce"] != data["transfer_nonce"]
                or Path(owner["owner_workspace"]).resolve() != ledger.root.resolve()):
            raise ResearchError("luna_transfer_import_ownership_mismatch")
        if owner["status"] == "imported_owner":
            saved = ledger.db.execute("SELECT id FROM records WHERE kind='luna_study_transfer_result' "
                "AND json_extract(payload,'$.manifest')=? AND json_extract(payload,'$.state')=? "
                "AND json_extract(payload,'$.study_key')=? ORDER BY created_event DESC LIMIT 1",
                (data["manifest"], "imported_verified_owner", data["study_key"])).fetchone()
            if saved:
                result = ledger.get(saved[0], "luna_study_transfer_result")
                return _present(engine, session, Context(context.objective, context.actor, result["versions"]), result)
    elif ledger.db.execute("SELECT 1 FROM sources LIMIT 1").fetchone() or ledger.db.execute("SELECT 1 FROM records LIMIT 1").fetchone():
        raise ResearchError("luna_transfer_import_requires_empty_research_store")
    else:
        ledger.record(session, "study_execution_ownership", data["study_key"], {
            "study_key": data["study_key"], "status": "import_pending", "owner_workspace": str(ledger.root),
            "manifest": data["manifest"], "transfer_nonce": data["transfer_nonce"],
            "allowed_operations": [], "observation": "Import pending; no model execution authorized"})
    # Register the local implementation before opening any package evidence.
    code = Path(__file__).read_bytes()
    engine._version(session, context, {"kind": "protocol", "key": data["study_key"] + "-bounded-import",
        "content": {"method": METHOD + "-import", "implementation_sha256": hashlib.sha256(code).hexdigest(),
            "implementation_source": code.decode(), "manifest": data["manifest"],
            "no_model_calls": True, "same_manifest_resume_only": True}})
    package = ledger.artifacts.read(data["manifest"])
    if (package["method"] != METHOD or package["study_key"] != data["study_key"]
            or package["transfer_nonce"] != data["transfer_nonce"]
            or Path(package["child_workspace"]).resolve() != ledger.root.resolve()
            or package["limits"] != {"attempts": 400, "article_exposures": 6000, "automatic_retries": 0}):
        raise ResearchError("luna_transfer_manifest_target_or_budget_mismatch")
    expected = {item["sha256"] for item in package["artifacts"]} | {data["manifest"]}
    if {item.name for item in ledger.artifacts.root.iterdir()} - expected:
        # Runtime's own identity and input artifacts may already exist locally.
        local: set[str] = set()
        for row in ledger.db.execute("SELECT kind,payload FROM events"):
            payload = json.loads(row["payload"])
            local.update(payload[key] for key in LOCAL_ARTIFACT_FIELDS.get(row["kind"], ())
                         if isinstance(payload.get(key), str))
        local.update(row[0] for row in ledger.db.execute("SELECT artifact FROM records"))
        if {item.name for item in ledger.artifacts.root.iterdir()} - expected - local:
            raise AuditError("luna_transfer_unexpected_child_artifact")
    for item in package["artifacts"]:
        path = ledger.artifacts.verified_path(item["sha256"])
        if path.stat().st_size != item["bytes"]:
            raise AuditError("luna_transfer_artifact_size_mismatch")
    provenance = {"transfer_id": package["transfer_id"], "manifest": data["manifest"],
        "parent": package["parent_provenance"], "import_session": session, "import_observed_at": utc()}
    for spec in package["records"]:
        payload = ledger.artifacts.read(spec["artifact"])
        identifier = ledger.record(session, spec["kind"], spec["logical_key"], payload, spec["supersedes"])
        if identifier != spec["id"]:
            raise AuditError("luna_transfer_record_identity_changed")
        ledger.append(session, "luna.study.record.imported", {"record": identifier, **provenance,
            "original_event": spec["original_event"]})
    dataset = ledger.get(package["versions"]["dataset"], "dataset")
    source_ids = [source["id"] for source in package["sources"]]
    source_set = set(source_ids)
    if (len(source_set) != len(source_ids) or source_set != set(dataset["source_versions"])
            or any(passage["source_id"] not in source_set for passage in package["passages"])):
        raise AuditError("luna_transfer_complete_dataset_coverage_required")
    by_raw: dict[str, list[Json]] = {}
    for source in package["sources"]:
        by_raw.setdefault(source["raw_ref"], []).append(source)
    by_source: dict[str, list[Json]] = {}
    for passage in package["passages"]:
        by_source.setdefault(passage["source_id"], []).append(passage)
    for raw_ref, sources in by_raw.items():
        raw = ledger.artifacts.read(raw_ref)
        existing = [ledger.db.execute("SELECT * FROM sources WHERE id=?", (source["id"],)).fetchone()
                    for source in sources]
        if any(row is not None for row in existing):
            if not all(row is not None for row in existing):
                raise AuditError("luna_transfer_partial_source_group")
            for source, row in zip(sources, existing, strict=True):
                original = raw[source["raw_index"]]
                if (row["payload"] != canonical(original) or row["raw_ref"] != raw_ref
                        or row["raw_index"] != source["raw_index"] or row["source_key"] != source["source_key"]):
                    raise AuditError("luna_transfer_existing_source_changed")
            continue
        def projection(event: int) -> None:
            for source in sources:
                original = raw[source["raw_index"]]
                if digest(original) != source["id"] or original["source_key"] != source["source_key"]:
                    raise AuditError("luna_transfer_source_identity_changed")
                ledger.db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?)", (source["id"], source["source_key"],
                    canonical(original), raw_ref, source["raw_index"], event))
                for passage in by_source.get(source["id"], []):
                    text = original["body"][passage["start"]:passage["end"]]
                    expected = digest({"source": source["id"], "start": passage["start"], "end": passage["end"],
                        "sha256": hashlib.sha256(text.encode()).hexdigest()})
                    if expected != passage["id"] or hashlib.sha256(text.encode()).hexdigest() != passage["text_hash"]:
                        raise AuditError("luna_transfer_passage_identity_changed")
                    ledger.db.execute("INSERT INTO passages VALUES (?,?,?,?,?,?)", (passage["id"], passage["source_id"],
                        passage["start"], passage["end"], text, passage["text_hash"]))
                    ledger.db.execute("INSERT INTO passage_fts VALUES (?,?)", (passage["id"], text))
        ledger.append(session, "sources.imported", {"raw_ref": raw_ref,
            "source_versions": [source["id"] for source in sources], "versions": package["versions"],
            "import_provenance": provenance,
            "original_events": [package["source_events"][str(number)]
                                for number in sorted({source["original_event_seq"] for source in sources})]}, projection)
    for attempt in package["prior_attempts"]:
        if (attempt["study_key"] != package["study_key"] or attempt["original_attempt"] != attempt["original_intended"]["attempt"]
                or attempt["original_intended"]["luna_validation_study"] != package["study_key"]
                or attempt["status"] not in {"valid", "invalid", "unknown"}):
            raise AuditError("luna_transfer_prior_attempt_binding_invalid")
        ledger.record(session, "study_prior_model_attempt", attempt["original_attempt"], attempt)
    for event in package["authorizations"] + package["holdout_events"]:
        if ledger.db.execute("SELECT 1 FROM events WHERE kind=? AND "
                "json_extract(payload,'$.import_provenance.original_event.event_hash')=? AND "
                "json_extract(payload,'$.import_provenance.manifest')=? LIMIT 1",
                (event["kind"], event["event_hash"], data["manifest"])).fetchone():
            continue
        ledger.append(session, event["kind"], {**event["payload"], "import_provenance": {
            **provenance, "original_event": event, "observation": "Imported prior observation; not a new dispatch"}})
    attempts = package["prior_attempts"]
    spent, exposures = _spend(attempts)
    if spent != package["prior_spend"]["attempts"] or exposures != package["prior_spend"]["article_exposures"]:
        raise AuditError("luna_transfer_imported_budget_changed")
    verified = ledger.verify()
    ownership = {"study_key": package["study_key"], "status": "imported_owner",
        "owner_workspace": str(ledger.root), "child_workspace": str(ledger.root),
        "allowed_operations": ["luna_group_validation_continue"], "manifest": data["manifest"],
        "transfer_id": package["transfer_id"], "transfer_nonce": package["transfer_nonce"], "nonce": package["transfer_nonce"],
        "parent_provenance": package["parent_provenance"], "parent_ownership": package["parent_ownership"],
        "original_result": package["original_result"], "plan": package["plan"], "verified_import_head": verified["head_hash"]}
    ledger.record(session, "study_execution_ownership", package["study_key"], ownership)
    summary = {"state": "imported_verified_owner", "study_key": package["study_key"], "versions": package["versions"],
        "child_workspace": str(ledger.root), "manifest": data["manifest"], "transfer_id": package["transfer_id"],
        "transfer_nonce": package["transfer_nonce"], "parent_head_hash": package["parent_provenance"]["head_hash"],
        "sources": len(package["sources"]), "passages": len(package["passages"]), "records": len(package["records"]),
        "artifacts": len(package["artifacts"]), "artifact_bytes": sum(item["bytes"] for item in package["artifacts"]),
        "prior_attempts": len(attempts), "prior_article_exposures": package["prior_spend"]["article_exposures"],
        "new_model_calls": 0, "membership_changes": 0, "complete_own_store_verification": True}
    return _present(engine, session, Context(context.objective, context.actor, package["versions"]), summary)
