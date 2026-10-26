"""One-owner retained recall-v2 import for the separately authorized snippet pilot.

This is an offline capability, not a research entry point. The calling registered
Research operation owns its new intent and must retain the returned immutable
value before any new model admission. No historical source owner is reopened.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import time

import luna_recall_run_v2 as recall
import luna_recall_source_v2 as retained
from newsresearch.common import AuditError, digest, require_active
from newsresearch.embeddings import offline_tokenizer
from newsresearch.storage import check_permissions

ROOT = Path(__file__).resolve().parents[3]
METHOD = "cybercrime-luna-snippet-retained-recall-v1"
OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-recall-upgrade-20261024-v2")
PLAN = "bc14bc580c854aeef607ef64c8a89c438e36af2f7c09152ef13c2395ae88401a"
REPORT = "708df59703ad4e948f7805df87b106c8c50a0de4f73dff5b3041ed4eb8bfbb4a"
FREEZE = "ba180579be71f23f81028bcadb8570ee935a7a5c673924f0675ea474b905d1ea"
SUCCESSOR = "c34ea6d3a7881095ce452a77b62df63ae4fdfadf02adf1c083640f78db460fa3"
PRIOR_COMMITMENT = 3_605_901_656
POLICY = {"maximum_seconds": 900, "maximum_selected_bytes": 1024**3,
    "owners": 1, "model_calls": 0, "old_owner_mutations": 0,
    "prepared_only_is_attempt": False, "historical_stop_is_active_stop": False,
    "historical_failed_or_held_membership_blocked": True,
    "global_history_complete": False, "cost_is_conservative_estimate_not_invoice": True}
QA_PHASES = {"summary_quality", "summary_quality_audit", "card_quality", "card_quality_audit"}


def require(value, reason):
    if not value:
        raise AuditError("luna_snippet_source_" + reason)


def implementation():
    return {**recall.implementation(),
        Path(__file__).relative_to(ROOT).as_posix(): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class Reader(retained.Reader):
    def artifact_bytes(self, reference):
        self._active()
        if reference not in self.copied:
            require(self.unique_bytes + self.artifact_size(reference) <= POLICY["maximum_selected_bytes"], "selected_byte_limit")
        return super().artifact_bytes(reference)


def plain(row):
    return {k: v for k, v in row.items() if not k.startswith("_")}


def keyed(reader, row, key):
    raw = reader.db.execute("SELECT logical_key,supersedes FROM records WHERE id=?", (row["_record_id"],)).fetchone()
    require(raw is not None and raw[0] == key and raw[1] is None, "record_key")


def one(reader, kind, identity=None):
    rows = reader.rows(kind)
    require(len(rows) == 1 and (identity is None or rows[0]["_record_id"] == identity), "unique_record")
    return rows[0]


def session_prefix(reader, sequence, code, expected):
    event = reader.db.execute("SELECT session_id FROM events WHERE seq=?", (sequence,)).fetchone()
    require(event is not None, "producer_event")
    rows = list(reader.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (event[0],)))
    starts = [r for r in rows if r["kind"] == "session.started"]
    inputs = [r for r in rows if r["kind"] == "operation.intended"]
    require(len(starts) == len(inputs) == 1 and starts[0]["seq"] < inputs[0]["seq"] < sequence, "producer_prefix")
    start, incoming = json.loads(starts[0]["payload"]), json.loads(inputs[0]["payload"])
    identity = reader.artifact(start["identity"])
    require(all(identity["code_files"].get(p) == h for p, h in code.items() if p.startswith("src/") and p.endswith(".py")), "producer_code")
    require(incoming["operation"] == "status" and digest(reader.artifact(incoming["input"])) == digest(expected), "producer_input")
    return rows, {"session": event[0], "identity": start["identity"], "input": incoming["input"]}


def prepare_completed(reader, plan):
    expected = {"action": "prepare", **{k: plan[k] for k in ("audit_owner", "binding", "seed", "approval")}}
    rows, proof = session_prefix(reader, plan["_created_event"], plan["implementation"], expected)
    done = [r for r in rows if r["kind"] == "operation.completed"]
    ended = [r for r in rows if r["kind"] == "session.ended"]
    require(len(done) == len(ended) == 1 and not any(r["kind"] == "operation.failed" for r in rows)
        and plan["_created_event"] < done[0]["seq"] < ended[0]["seq"]
        and json.loads(ended[0]["payload"]) == {"status": "completed"}, "prepare_completion")
    output = json.loads(done[0]["payload"])
    result = reader.artifact(output["result"])
    require(output["operation"] == "status" and result.get("plan") == plan["_record_id"]
        and result.get("method") == recall.METHOD, "prepare_output")
    result_row = reader.record(result["id"], recall.REPORT)
    require(digest(result) == digest({"id": result_row["_record_id"], **plain(result_row)})
        and plan["_created_event"] < result_row["_created_event"] < done[0]["seq"], "prepare_report")
    return {**proof, "output": output["result"], "completed_event": done[0]["seq"]}


def authority(reader):
    plan, intent, saved = one(reader, recall.PLAN, PLAN), one(reader, recall.INTENT), one(reader, recall.SOURCE)
    report = reader.record(REPORT, recall.REPORT)
    reader.ensure_report_last(report)
    require(reader.rows(recall.REPORT)[-1]["_record_id"] == REPORT, "final_report")
    desired = plain(intent)
    code = recall.implementation()
    require(plan["method"] == report["method"] == recall.METHOD and plan["implementation"] == code
        and digest(plan["policy"]) == digest(recall.POLICY) and report["policy"] == recall.POLICY
        and plan["approval"] == {**recall.APPROVAL, "method_sha256": hashlib.sha256(recall.SPEC.read_bytes()).hexdigest()}
        and plan["intent"] == intent["_record_id"]
        and all(digest(plan.get(k)) == digest(v) for k, v in desired.items()), "plan_authority")
    for row, key in ((intent, recall.METHOD), (saved, plan["intent"]), (plan, plan["intent"]), (report, digest(plain(report)))):
        keyed(reader, row, key)
    expected = recall.versions(desired)
    require(set(plan["versions"]) == set(expected), "versions")
    for kind, content in expected.items():
        ids = [r[0] for r in reader.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, recall.METHOD))]
        require(ids == [plan["versions"][kind]], "version_identity")
        version = reader.record(ids[0], kind)
        keyed(reader, version, recall.METHOD)
        require(digest(version["content"]) == digest(content) and version["reason"] is None and version["branch"] == "main"
            and intent["_created_event"] < version["_created_event"] < plan["_created_event"], "version_binding")
    proofs = [prepare_completed(reader, plan), retained.completed(reader, report, code)]
    require(saved["intent"] == plan["intent"] and saved["artifact"] == plan["source_artifact"]
        and intent["_created_event"] < saved["_created_event"] < plan["_created_event"]
        and report["plan"] == PLAN and report["source_artifact"] == plan["source_artifact"], "source_checkpoint")
    source = reader.artifact(plan["source_artifact"])
    recall.Recall.verify_source(None, source, plan)
    require(digest(report["source_provenance"]) == digest(source["recall_provenance"]), "source_provenance")
    require(report["frozen_record"] == FREEZE, "freeze_identity")
    frozen = one(reader, recall.FREEZE, FREEZE)
    keyed(reader, frozen, PLAN)
    require(frozen["plan"] == PLAN and frozen["frozen_before_final_reference"] is True
        and frozen["state_artifact"] == report["successor_artifact"] == SUCCESSOR
        and plan["_created_event"] < frozen["_created_event"] < report["_created_event"]
        and report["analysis"] is not None, "successor_binding")
    checkpoints = [r for r in reader.db.execute("SELECT * FROM records WHERE kind=? AND logical_key=?", (recall.CHECKPOINT, "successor-before-draw"))]
    require(len(checkpoints) == 1, "successor_scope")
    scope = reader._row(checkpoints[0])
    keyed(reader, scope, "successor-before-draw")
    require(scope["plan"] == PLAN and scope["source_artifact"] == plan["source_artifact"]
        and scope["seed"] == plan["seed"] and scope["state_artifact"] == SUCCESSOR
        and scope["design_method"] == recall.design_module.METHOD
        and digest(scope["exposed_documents"]) == digest(frozen["exposed_documents"])
        and digest(scope["risk_pairs"]) == digest(frozen["risk_pairs"])
        and plan["_created_event"] < scope["_created_event"] < frozen["_created_event"], "successor_scope_binding")
    state = reader.artifact(SUCCESSOR)
    members = [i for group in state["groups"].values() for i in group]
    unresolved = state["unresolved_ids"]
    require(len(members) == len(set(members)) and len(unresolved) == len(set(unresolved))
        and not set(members).intersection(unresolved) and set(members) | set(unresolved) == set(source["documents"])
        and set(state["accepted_group_ids"]) <= set(state["groups"]), "successor_partition")
    require(all(digest({k: d[k] for k in ("title", "body")}) == d["input_sha256"] for d in source["documents"].values()), "full_input_hash")
    return plan, report, source, state, {"producer_completions": proofs,
        "source_record": saved["_record_id"], "freeze_record": frozen["_record_id"],
        "successor_scope_record": scope["_record_id"], "design_artifact_not_recomputed": frozen["design_artifact"]}


def membership_history(reader, source, census, head):
    result, prepared, attempts = {}, [], []
    pairs = recall.repair.compatible_prior(source)
    baseline = source["prior_history"]
    def entry(members, revision):
        require(members == sorted(set(members)) and set(members) <= set(source["documents"])
            and digest(members) == revision, "membership_identity")
        return result.setdefault(revision, {"members": members, "member_attempted": False, "card_attempted": False,
            "member_supported": False, "card_supported": False, "blocked": False,
            "member_result_ref": None, "card_result_ref": None, "card": None, "provenance": []})
    for row in baseline.get("membership_attempts", []):
        if row.get("phase") not in QA_PHASES:
            continue  # Successful summary construction is not a membership QA attempt.
        item = entry(row["document_ids"], row["membership_revision"])
        item["card_attempted"] = True
        # These older summaries/cards are not this exact new full-member/card
        # contract. Preserve their attempt, never repeat or invent reusable QA.
        item["blocked"] = True
        item["provenance"].append({"origin": "retained_baseline", "attempt": row,
            "reuse": "unverified_under_exact_current_card_contract"})
    encoder = offline_tokenizer()
    def count(text):
        return len(encoder.encode(text, disallowed_special=()))
    for key, packet in census["packets"].items():
        intended = census["intents"].get(key)
        row = census["responses"].get(key)
        if not intended:
            prepared.append({"task_key": key, "role": packet["role"], "membership_revision": packet.get("membership_revision"),
                "queue_record": census["queues"][key]["id"], "attempted": False})
            continue
        done = intended["attempt"] in census["completed"]
        refs = {k: intended[k] for k in ("request", "packet", "dispatch")}
        if row:
            refs.update(response_record=row["id"], response=row["response"], parsed=row["parsed"])
            if row["parsed"]:
                reader.artifact_bytes(row["parsed"])
        fact = {"owner": str(reader.owner), "head": head, "physical_attempt": intended["attempt"],
            "task_key": key, "role": packet["role"], "completed": done, "hold": not done,
            "usable": bool(done and row and row["usable"]), "artifact_refs": refs}
        attempts.append(fact)
        if done and row and row["usable"]:
            pairs.extend({**observation, "physical_attempt": intended["attempt"], "task_key": key,
                "artifact_refs": refs} for observation in row["observations"])
        if packet["role"] not in {"group_membership", "group_quality"}:
            continue
        item = entry(packet["members"], packet["membership_revision"])
        builder = recall.contract.member_packet if packet["role"] == "group_membership" else recall.contract.group_packet
        require(digest(packet) == digest(builder(source, packet["members"], count)), "membership_full_packet")
        stage = "member" if packet["role"] == "group_membership" else "card"
        require(not any(p.get("stage") == stage for p in item["provenance"]), "duplicate_membership_stage")
        supported = bool(done and row and row["usable"] and row["members_supported" if stage == "member" else "group_supported"])
        item[stage + "_attempted"] = True
        item[stage + "_supported"] = supported
        item[stage + "_result_ref"] = row["id"] if row else None
        item["blocked"] |= not supported
        if stage == "card" and supported:
            item["card"] = packet["card"]
        item["provenance"].append({**fact, "stage": stage, "supported": supported})
    return {"membership_attempts": result, "prepared_only": prepared, "physical_attempts": attempts,
        "pair_observations": pairs,
        "baseline": baseline, "gaps": baseline.get("gaps", []),
        "historical_response_health": census["health"], "historical_unknown_holds": census["unknown_holds"],
        "historical_settled_nanousd": census["settled_nanousd"], "historical_held_nanousd": census["held_nanousd"],
        "active_stop_inherited": False, "global_history_complete": False}


def collect(engine, session, *, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "offline_only")
    start = time.monotonic()
    deadline = start + POLICY["maximum_seconds"] if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (float, int)) and math.isfinite(deadline)
        and 0 < deadline-start <= POLICY["maximum_seconds"], "bounded_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    observations = []
    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-start, 3), **values})
    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        progress("snippet_opening_retained_recall")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        plan, report, source, state, proof = authority(reader)
        progress("snippet_replaying_retained_attempts", metadata_events=len(metadata["events"]))
        census = recall.Recall.census(retained.AuditView(reader), {"id": PLAN, **plain(plan)})
        expected = {"attempted_requests": len(census["intents"]), "returned_requests": census["returned_requests"],
            "queued_requests": len(census["packets"]), "unattempted_requests": len(census["packets"])-len(census["intents"]),
            **{k: census[k] for k in ("settled_nanousd", "held_nanousd", "unknown_holds")},
            "category_commitments_nanousd": dict(census["by_category"]), "response_health": census["health"],
            "prior_audit_commitment_nanousd": recall.PRIOR_COMMITMENT,
            "committed_including_prior_nanousd": recall.PRIOR_COMMITMENT+census["settled_nanousd"]+census["held_nanousd"]}
        require(all(digest(report[k]) == digest(v) for k, v in expected.items())
            and report["committed_including_prior_nanousd"] == PRIOR_COMMITMENT, "report_cost_census")
        queue_rows = {r["_record_id"]: r for r in reader.rows(recall.QUEUE)}
        for event in reader.db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
            intended = json.loads(event["payload"])
            require(plan["_created_event"] < queue_rows[intended["queue"]]["_created_event"] < event["seq"] < report["_created_event"], "attempt_chronology")
            session_prefix(reader, event["seq"], plan["implementation"], {"action": "run", "allow_paid_execution": True})
            packet = census["packets"][intended["task_key"]]
            require(digest(reader.artifact(intended["packet"])) == digest(packet)
                and digest(reader.artifact(intended["request"])) == digest(packet["request"]), "attempt_artifacts")
        history = membership_history(reader, source, census, head)
        reader._active()
        check_permissions(owner, root=True)
        check_permissions(owner / "objects")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "source_changed")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "implementation_changed")
        progress("snippet_source_complete", physical_attempts=len(census["intents"]),
            unique_source_artifact_bytes_read=reader.unique_bytes)
        return {"source": source, "state": state, "history": history,
            "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY,
                "owner": str(owner), "head": head, "plan_record": PLAN, "plan_artifact": plan["_artifact"],
                "report_record": REPORT, "report_artifact": report["_artifact"], "state_artifact": SUCCESSOR,
                "source_artifact": plan["source_artifact"], **proof,
                "metadata_census_artifact": engine.ledger.artifacts.put(metadata),
                "copied_artifacts": dict(reader.copied), "unique_source_artifact_bytes_read": reader.unique_bytes,
                "liveness": observations, "historical_stop": stop, "source_head_unchanged": True,
                "elapsed_seconds": round(time.monotonic()-start, 3)}}
