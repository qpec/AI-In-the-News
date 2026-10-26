"""Incremental, offline Research replay of the new API Batch handoff only."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import sqlite3

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

import lean_luna_state as state
import luna_batch_remainder as handoff
import luna_standard_finish_v2 as finish
import luna_standard_finish as previous_finish

METHOD = "luna-standard-finish-integrity-v2"
CHECKPOINT = "luna_standard_finish_integrity_checkpoint"


def require(condition, name):
    if not condition:
        raise AuditError("batch_integrity_" + name)


def operational_snapshot(path):
    """Copy one consistent view, then release the live reader before replay."""
    live = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, isolation_level=None)
    snapshot = sqlite3.connect(":memory:", isolation_level=None)
    try:
        live.execute("PRAGMA query_only=ON")
        live.execute("BEGIN")
        live.execute("SELECT COUNT(*) FROM sqlite_schema").fetchone()
        # Hash the original view: SQLite backup changes database-header counters.
        state_sha256 = handoff.state_hash(live)
        live.backup(snapshot)
        snapshot.row_factory = sqlite3.Row
        snapshot.execute("PRAGMA query_only=ON")
        return snapshot, state_sha256
    except BaseException:
        snapshot.close()
        raise
    finally:
        live.close()


def replay_manifest(value, artifacts, allowed, snapshot, cache=None):
    # Each map belongs to one pinned inspection. Values are immutable source
    # records retained by the manifests map for this entire replay.
    if cache is not None and id(value) in cache:
        return cache[id(value)]
    raw = artifacts.read(value["jsonl_ref"])
    require(hashlib.sha256(raw).hexdigest() == value["manifest_id"], "manifest_hash")
    lines = raw.splitlines(keepends=True)
    require(len(lines) == len(value["members"]), "manifest_coverage")
    tasks, offset = {}, 0
    for member, line in zip(value["members"], lines, strict=True):
        row = json.loads(line)
        custom, descriptor = member["custom_id"], member["descriptor"]
        require(custom not in tasks and allowed.get(custom) == descriptor, "duplicate_or_foreign_article")
        require(descriptor["corpus_id"] == value["corpus_id"] and row["custom_id"] == custom
            and row["method"] == "POST" and row["url"] == "/v1/responses"
            and member["offset"] == offset and member["length"] == len(line)
            and descriptor["line_sha256"] == hashlib.sha256(line).hexdigest()
            and descriptor["line_bytes"] == len(line) and digest(row) == descriptor["request_sha256"]
            and member["request_body_sha256"] == digest(row["body"]), "packet_corpus_binding")
        packet = handoff.batch.packet_from_prompt(row["body"], descriptor, snapshot)
        tasks[custom] = {"body": row["body"], "packet": packet,
            "source_refs": descriptor["source_locator"], "request_ref": member["request_body_sha256"],
            "packet_ref": descriptor["packet_sha256"]}
        offset += len(line)
    if cache is not None:
        cache[id(value)] = tasks
    return tasks


def replay_file(value, manifest, artifacts, allowed, snapshot, database, price, cache=None):
    tasks = replay_manifest(manifest, artifacts, allowed, snapshot, cache)
    require(value["corpus_id"] == manifest["corpus_id"], "result_corpus")
    files = [artifacts.read(value["raw_files"][field]) if value["raw_files"][field] else None
        for field in ("output_file_id", "error_file_id")]
    parsed = handoff.batch.parse_batch_results_phase_aware(files[0], files[1], tasks)
    rows = {row["custom_id"]: row for raw in files if raw for row in map(json.loads, raw.splitlines()) if row}
    saved = artifacts.json(value["results_ref"])
    costs = artifacts.json(value["costs_ref"])
    require(len(costs) == len(tasks) and len(saved) == len(tasks), "result_coverage")
    by_custom = {item["request"]["request_id"]: item for item in costs}
    require(set(by_custom) == set(tasks), "cost_coverage")
    replayed = []
    for item in parsed["items"]:
        custom = item["custom_id"]
        entry = by_custom[custom]
        reservation = state.cost(price, entry["request"]["input_count"]["input_tokens"], 4096)
        status, charge, reserved = "unknown", 0, reservation
        usage = item.get("usage")
        if item.get("usage_complete") is True and usage is not None:
            if item.get("observed_model") != "gpt-6-luna":
                status = "frozen"
            else:
                amount = state.cost(price, usage["input_tokens"], usage["output_tokens"])
                if amount > reservation:
                    status, charge, reserved = "overrun", amount, 0
                elif (usage["input_tokens"] != entry["request"]["input_count"]["input_tokens"]
                        or usage["output_tokens"] > 4096):
                    status = "frozen"
                else:
                    status, charge, reserved = "settled", amount, 0
        require((entry["status"], entry["charged_nanousd"], entry["reserved_nanousd"], entry["settlement"])
            == (status, charge, reserved, usage), "settlement_replay")
        result = {**item, "lean_new_result": True,
            "lean_qualifying_truncation": handoff.batch.qualifying_truncation(item, rows.get(custom)) and status == "settled"}
        replayed.append(result)
        current = database.execute("SELECT payload FROM results WHERE custom_id=?", (custom,)).fetchone()
        cost = database.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
        require(current is not None and json.loads(current[0]) == result
            and cost is not None and json.loads(cost[0]) == entry, "saved_projection")
    require(saved == replayed and value["returned"] == len(saved)
        and value["raw_counts"] == dict(Counter(item["status"] for item in saved)), "validation_replay")
    # The runner's historical raw_counts field actually counts phase-aware
    # statuses. Report the original and derived interpretations separately.
    return Counter(item["raw_status"] for item in saved), Counter(item["status"] for item in saved)


def replay_standard(saved, manifest, artifacts, allowed, snapshot, database, plan, receipt_record, cache=None):
    import luna_standard_api as standard
    tasks = replay_manifest(manifest, artifacts, allowed, snapshot, cache)
    custom = saved["custom_id"]
    member = next(m for m in manifest["members"] if m["custom_id"] == custom)
    task = {"custom_id": custom, "descriptor": member["descriptor"], "request_body_ref": member["request_body_sha256"]}
    value = dict(saved["receipt"])
    raw = artifacts.read(value.pop("body_ref")) if value.get("body_ref") else None
    value.pop("body_ref", None)
    recorded = artifacts.read(receipt_record["raw_body_ref"]) if receipt_record.get("raw_body_ref") else receipt_record.get("raw_body_utf8", "").encode() if "raw_body_utf8" in receipt_record else None
    require(raw == recorded, "standard_receipt_source")
    for key, val in value.items():
        if key != "body_sha256":
            require(receipt_record.get(key) == val, "standard_receipt_metadata")
    receipt = standard.http.BatchReceipt(body=raw, **value)
    parsed, envelope = standard.parse_standard(task, tasks[custom]["body"], receipt, snapshot)
    cost = saved["cost"]
    count = database.execute("SELECT input_tokens,payload FROM counts WHERE custom_id=?", (custom,)).fetchone()
    require(count and json.loads(count[1])["request_body_ref"] == task["request_body_ref"]
        and cost["request"]["input_count"]["input_tokens"] == count[0]
        and cost["request"]["request_sha256"] == task["request_body_ref"]
        and cost["price_policy"] == standard.standard_price(plan), "standard_cost_binding")
    original = {**cost, "status": "reserved", "charged_nanousd": 0,
        "reserved_nanousd": state.cost(standard.standard_price(plan), count[0], 4096)}
    original.pop("settlement", None)
    item, replayed_cost = standard.settle_standard(plan, original, parsed, envelope)
    require(item == saved["item"] and replayed_cost == cost, "standard_validation_settlement_replay")
    projected = database.execute("SELECT payload FROM results WHERE custom_id=?", (custom,)).fetchone()
    projected_cost = database.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
    require(projected and json.loads(projected[0]) == item and projected_cost and json.loads(projected_cost[0]) == cost,
        "standard_saved_projection")
    return manifest["corpus_id"], item["raw_status"], item["status"]


class BatchIntegrity(Research):
    @audited_handler
    def _status(self, session, context, data):
        owner = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Incremental new-owner journal and artifact hashes; frozen selection, full-text packet/corpus bindings; duplicate HTTP and article-create intents; raw output validation and cost settlement replay; preserved imported unknown liabilities. No provider calls or source inference.",
            "limits": "Mechanical integrity only. No semantic correctness claim, unrelated historical replay, or adversarial rollback protection. Mutable live progress is a cache; live state need not match an earlier checkpoint during writes."}})["id"]
        previous_row = self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1", (CHECKPOINT, str(owner))).fetchone()
        previous = self.ledger.get(previous_row[0], CHECKPOINT) if previous_row else None
        start = previous["head_seq"] if previous else 0
        previous_hash = previous["head_hash"] if previous else "0" * 64
        artifacts = state.SelectedArtifacts(owner)
        source = state.read_only_database(owner)
        operational = None
        # Pin source first. Operational projections are append-only for finalized
        # files, so a slightly newer operational snapshot remains comparable.
        try:
            finish_row = source.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (finish.AMENDMENT,)).fetchone()
            require(finish_row is not None, "finish_amendment_missing")
            finishing = state.row_value(finish_row, finish.AMENDMENT)
            require(finishing["implementation"] == finish.implementation() and finishing["plan"] == data["plan"], "finish_code_or_plan_changed")
            finish.parallel.verify_parent_seal(finishing)
            finish_ids = set()
            for prior_row in source.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (finish.AMENDMENT,)):
                prior = state.row_value(prior_row, finish.AMENDMENT)
                expected = finish.implementation() if prior["method"] == finish.METHOD else previous_finish.implementation()
                require(prior["implementation"] == expected and prior["plan"] == data["plan"], "finish_lineage_binding")
                finish.parallel.verify_parent_seal(prior)
                finish_ids.add(prior["_record_id"])
            if previous is None:
                previous = finishing["parent_integrity"]
                require(previous["integrity_passed"] and [previous["head_seq"], previous["head_hash"]] == finishing["parent_head"], "parent_integrity_binding")
                start, previous_hash = previous["head_seq"], previous["head_hash"]
            plan = state.row_value(source.execute("SELECT * FROM records WHERE id=?", (data["plan"],)).fetchone(), handoff.PLAN)
            require(plan["implementation"] == handoff.implementation(), "implementation_changed")
            require(finishing["deadline_epoch"] == plan["deadline_epoch"] and finishing["tpm"] == 2000000
                and finishing["rpm"] == 5000 and finishing["max_workers"] == 64
                and finishing["hard_cap_usd"] == 150 and finishing["operating_cap_usd"] == 120, "finish_scope_changed")
            handoff.verify_codex_seal(plan)
            amendment_row = source.execute("SELECT * FROM records WHERE kind='luna_batch_parallel_amendment' ORDER BY created_event DESC LIMIT 1").fetchone()
            if amendment_row:
                import luna_batch_parallel as parallel
                amendment = state.row_value(amendment_row, parallel.AMENDMENT)
                artifacts.check(amendment_row["artifact"])
                require(amendment["implementation"] == parallel.implementation()
                    and amendment["plan"] == data["plan"] and amendment["deadline_epoch"] == plan["deadline_epoch"], "scheduler_amendment_changed")
                parallel.verify_parent_seal(amendment)
            combined_row = source.execute("SELECT * FROM records WHERE kind='luna_all_routes_amendment' ORDER BY created_event DESC LIMIT 1").fetchone()
            standard_row = combined_row or source.execute("SELECT * FROM records WHERE kind='luna_standard_api_amendment' ORDER BY created_event DESC LIMIT 1").fetchone()
            if standard_row:
                import luna_standard_api as standard
                binding_module = standard
                if combined_row:
                    import luna_all_routes as combined
                    binding_module = combined
                standard_amendment = state.row_value(standard_row, binding_module.AMENDMENT)
                artifacts.check(standard_row["artifact"])
                require(standard_amendment["implementation"] == binding_module.implementation()
                    and standard_amendment["plan"] == data["plan"]
                    and standard_amendment["deadline_epoch"] == plan["deadline_epoch"]
                    and standard_amendment["tpm"] == standard.TPM and standard_amendment["rpm"] == standard.RPM,
                    "standard_amendment_changed")
                standard.parallel.verify_parent_seal(standard_amendment)
            operational, operational_sha256 = operational_snapshot(owner / "state.sqlite3")
            allowed = {d["custom_id"]: d for ref in plan["queues"].values() for d in artifacts.json(ref)}
            require(len(allowed) == plan["count_cap"], "selection_count")
            head = source.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            require(head is not None and head[0] >= start, "source_rollback")
            if start:
                require(source.execute("SELECT event_hash FROM events WHERE seq=?", (start,)).fetchone()[0] == previous_hash, "previous_head_changed")
            required = {"session.started": ("identity",), "operation.intended": ("input",),
                "operation.completed": ("result",), "record.created": ("artifact",),
                "preparation.artifact.saved": ("artifact",)}
            seq = start
            for row in source.execute("SELECT * FROM events WHERE seq>? ORDER BY seq", (start,)):
                item = dict(row)
                current_hash = item.pop("event_hash")
                item["payload"] = json.loads(item["payload"])
                seq += 1
                require(item["seq"] == seq and item["previous_hash"] == previous_hash
                    and digest(item) == current_hash, "journal_chain")
                for key in required.get(item["kind"], ()):
                    if item["payload"].get(key):
                        artifacts.check(item["payload"][key])
                previous_hash = current_hash
            require((seq, previous_hash) == tuple(head), "snapshot_head")
            manifest_cache = {}
            manifests, intents, receipts, created, saved_jobs = {}, {}, set(), set(), set()
            standard_intents, standard_receipts, standard_saved, rate_window = {}, {}, set(), deque()
            codex_intents, codex_saved, route_assignments = {}, set(), {}
            previous_admission_deadline = 0
            snapshot = handoff.batch.core.load_contract_snapshot()
            new_raw, new_derived, files_checked = Counter(), Counter(), 0
            total_raw = Counter({(r["corpus"], r["status"]): r["count"] for r in (previous or {}).get("total_raw_counts", [])})
            total_derived = Counter({(r["corpus"], r["status"]): r["count"] for r in (previous or {}).get("total_derived_counts", [])})
            for row in source.execute("SELECT * FROM records ORDER BY created_event"):
                # Prior immutable records supply bindings and duplicate detection;
                # only records/artifacts newer than the verified head are replayed.
                new = row["created_event"] > start
                value = state.row_value(row) if new else json.loads(row["payload"])
                if new:
                    artifacts.check(row["artifact"])
                if row["kind"] == handoff.lean.MANIFEST:
                    require(value["baseline"] == data["plan"], "manifest_plan")
                    manifests[row["id"]] = value
                    if new:
                        replay_manifest(value, artifacts, allowed, snapshot, manifest_cache)
                elif row["kind"] == finish.ASSIGNMENT:
                    require(value["plan"] == data["plan"] and value["amendment"] in finish_ids
                        and value["manifest"] in manifests and value["manifest"] not in route_assignments
                        and value["route"] == "standard", "finish_assignment_binding")
                    ids = {m["custom_id"] for m in manifests[value["manifest"]]["members"]}
                    require(ids == set(value["request_ids"]) and not ids.intersection(created)
                        and not ids.intersection(finishing["quarantined_custom_ids"]), "finish_prior_identity_overlap")
                    route_assignments[value["manifest"]] = "standard"
                    for custom, old in value["prior_unsubmitted_bindings"].items():
                        require(custom in ids, "finish_rebind_membership")
                        original = next((m for m in manifests.values() if m["manifest_id"] == old["manifest_id"]), None)
                        require(original and any(m["custom_id"] == custom for m in original["members"]), "finish_original_manifest_binding")
                elif row["kind"] == "luna_all_routes_assignment":
                    require(combined_row and value["amendment"] == standard_amendment["_record_id"]
                        and value["plan"] == data["plan"] and value["manifest"] in manifests
                        and value["manifest"] not in route_assignments and value["route"] in combined.ROUTE_SIZES,
                        "route_assignment_binding")
                    route_assignments[value["manifest"]] = value["route"]
                elif row["kind"] == "luna_all_routes_codex_intent":
                    custom, attempt = value["custom_id"], value["attempt"]
                    require(combined_row and value["plan"] == data["plan"]
                        and value["amendment"] == standard_amendment["_record_id"]
                        and value["manifest"] in manifests and route_assignments.get(value["manifest"]) == "codex"
                        and custom in allowed and custom not in created and attempt not in codex_intents
                        and value["intended_epoch"] < plan["deadline_epoch"], "codex_duplicate_or_binding")
                    created.add(custom)
                    codex_intents[attempt] = value
                    if new:
                        tasks = replay_manifest(manifests[value["manifest"]], artifacts, allowed, snapshot, manifest_cache)
                        request, dispatch = artifacts.json(value["request"]), artifacts.json(value["dispatch"])
                        from newsresearch.luna_standard_provider import build_prompt
                        from newsresearch.luna_speed_provider import validate_request
                        validate_request(request)
                        configured = combined.StandardProvider(owner / "workers", executable=standard_amendment["codex_executable"],
                            timeout_seconds=180, max_input_bytes=1_000_000, max_output_bytes=262144)
                        require(custom in tasks and request["packet"] == tasks[custom]["packet"]
                            and json.loads(dispatch["stdin"]) == json.loads(build_prompt(request))
                            and dispatch["stdin_sha256"] == hashlib.sha256(dispatch["stdin"].encode()).hexdigest()
                            and dispatch["command"] == list(configured._command(Path(dispatch["cwd"])))
                            and dispatch["configured_model"] == "gpt-6-luna"
                            and dispatch["configured_service_tier"] == "standard" and dispatch["fast_mode"] is False,
                            "codex_exact_invocation")
                elif row["kind"] == "luna_all_routes_codex_result":
                    attempt, custom = value["attempt"], value["custom_id"]
                    require(attempt in codex_intents and custom == codex_intents[attempt]["custom_id"]
                        and attempt not in codex_saved and value["amendment"] == standard_amendment["_record_id"], "codex_result_binding")
                    codex_saved.add(attempt)
                    if new:
                        intended = codex_intents[attempt]
                        response = combined.ProviderResponse(**artifacts.json(value["response"]))
                        request = artifacts.json(intended["request"])
                        item = combined.assess_codex(custom, request["packet"], response)
                        projected = operational.execute("SELECT payload FROM results WHERE custom_id=?", (custom,)).fetchone()
                        require(item == value["item"] and projected and json.loads(projected[0]) == item,
                            "codex_validation_replay")
                        require(not operational.execute("SELECT 1 FROM budget_entries WHERE custom_id=?", (custom,)).fetchone(),
                            "codex_api_cost_overlap")
                        new_raw[(value["corpus_id"], item["raw_status"])] += 1
                        new_derived[(value["corpus_id"], item["status"])] += 1
                elif row["kind"] == handoff.lean.INTENT:
                    require(value["baseline"] == data["plan"], "intent_plan")
                    for member in value["members"]:
                        action = member["action_id"]
                        require(action not in intents, "duplicate_http_intent")
                        intents[action] = row["id"]
                        if member["request"]["path"] == "/v1/batches" and member["request"]["method"] == "POST":
                            manifest = manifests[value["manifest"]]
                            ids = {m["custom_id"] for m in manifest["members"]}
                            require(not created.intersection(ids), "duplicate_article_create")
                            created.update(ids)
                            if combined_row and row["created_event"] > combined_row["created_event"]:
                                require(route_assignments.get(value["manifest"]) == "batch", "batch_route_overlap")
                        elif member["request"] == {"method": "POST", "path": "/v1/responses"}:
                            require(standard_row is not None, "unregistered_standard_intent")
                            custom = member["standard_custom_id"]
                            manifest = manifests[value["manifest"]]
                            task = next((m for m in manifest["members"] if m["custom_id"] == custom), None)
                            require(task and custom not in created and custom in allowed, "duplicate_standard_article")
                            created.add(custom)
                            standard_intents[action] = (custom, manifest)
                            if combined_row:
                                require(route_assignments.get(value["manifest"]) == "standard", "standard_route_overlap")
                            rate = member["standard_rate"]
                            while rate_window and rate_window[0][0] <= rate["epoch"] - 60:
                                rate_window.popleft()
                            require(rate["epoch"] >= previous_admission_deadline
                                and rate["epoch"] < plan["deadline_epoch"]
                                and 0 < rate["tpm"] <= standard.TPM and 0 < rate["rpm"] <= standard.RPM
                                and len(rate_window) + 1 <= rate["rpm"]
                                and sum(r[1] for r in rate_window) + rate["tokens"] <= rate["tpm"], "standard_rate_exceeded")
                            rate_window.append((rate["epoch"], rate["tokens"]))
                            previous_admission_deadline = rate["next_admission"]
                            require(previous_admission_deadline >= rate["epoch"] + max(60 * rate["tokens"] / rate["tpm"], 60 / rate["rpm"]) - 0.001,
                                "standard_pacing_changed")
                            if new:
                                original = artifacts.read(member["body_ref"])
                                wire = standard.prepare_standard(original, action)
                                count = operational.execute("SELECT input_tokens FROM counts WHERE custom_id=?", (custom,)).fetchone()
                                require(digest(json.loads(original)) == task["request_body_sha256"]
                                    and hashlib.sha256(original).hexdigest() == member["body_sha256"]
                                    and hashlib.sha256(wire.body).hexdigest() == member["wire_body_sha256"]
                                    and count and rate["tokens"] == count[0] + 4096, "standard_wire_or_rate_binding")
                        if new and member.get("body_ref"):
                            artifacts.check(member["body_ref"])
                        if new and member.get("body") is not None:
                            require(hashlib.sha256(state.canonical(member["body"]).encode()).hexdigest() == member["body_sha256"], "http_body_hash")
                elif row["kind"] == handoff.lean.RECEIPT:
                    for member in value["members"]:
                        action = member["action_id"]
                        require(action not in receipts and intents.get(action) == member["intent"], "receipt_without_single_intent")
                        receipts.add(action)
                        if action in standard_intents:
                            standard_receipts[action] = member
                        if new:
                            raw = artifacts.read(member["raw_body_ref"]) if member.get("raw_body_ref") else member.get("raw_body_utf8", "").encode() if "raw_body_utf8" in member else None
                            if raw is not None:
                                require(hashlib.sha256(raw).hexdigest() == member["body_sha256"], "receipt_hash")
                elif row["kind"] == "luna_batch_remainder_file_result":
                    require(value["plan"] == data["plan"] and value["job_id"] not in saved_jobs, "duplicate_file_result")
                    saved_jobs.add(value["job_id"])
                    if new:
                        manifest = next(m for m in manifests.values() if m["manifest_id"] == value["manifest_id"])
                        raw_counts, derived_counts = replay_file(value, manifest, artifacts, allowed, snapshot, operational, plan["budget_config"]["price_policy"], manifest_cache)
                        new_raw.update({(value["corpus_id"], k): v for k, v in raw_counts.items()})
                        new_derived.update({(value["corpus_id"], k): v for k, v in derived_counts.items()})
                        files_checked += 1
                elif row["kind"] == "luna_standard_api_result_bundle":
                    require(standard_row and value["amendment"] in ({standard_amendment["_record_id"]} | finish_ids)
                        and value["plan"] == data["plan"], "standard_result_plan")
                    for saved in value["items"]:
                        action, custom = saved["action_id"], saved["custom_id"]
                        require(action in standard_intents and standard_intents[action][0] == custom
                            and action in standard_receipts and custom not in standard_saved, "standard_result_identity")
                        standard_saved.add(custom)
                        if new:
                            corpus, raw, derived = replay_standard(saved, standard_intents[action][1], artifacts,
                                allowed, snapshot, operational, plan, standard_receipts[action], manifest_cache)
                            new_raw[(corpus, raw)] += 1
                            new_derived[(corpus, derived)] += 1
                elif row["kind"] == "luna_batch_manifest_split" and new:
                    original = artifacts.read(value["original_jsonl"])
                    parts = [artifacts.read(p["jsonl"]) for p in value["parts"]]
                    require(value["plan"] == data["plan"] and b"".join(parts) == original
                        and hashlib.sha256(original).hexdigest() == value["original_manifest"], "split_bytes_changed")
                    for part, raw in zip(value["parts"], parts, strict=True):
                        require(hashlib.sha256(raw).hexdigest() == part["manifest"]
                            and [json.loads(line)["custom_id"] for line in raw.splitlines()] == part["request_ids"], "split_coverage_changed")
            total_raw.update(new_raw)
            total_derived.update(new_derived)
            for custom, expected in plan["imported_unknown_entry_hashes"].items():
                row = operational.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
                require(row is not None and digest(json.loads(row[0])) == expected, "imported_hold_changed")
            held = {r["action_id"]: finish.digest(dict(r)) for r in operational.execute("SELECT * FROM actions WHERE status!='complete'")
                if r["action_id"] in finishing["held_actions"]}
            require(held == finishing["held_actions"], "finish_count_hold_changed")
            for custom in finishing["quarantined_custom_ids"]:
                q = operational.execute("SELECT submitted FROM requests WHERE custom_id=?", (custom,)).fetchone()
                require(q and not q[0] and custom not in created, "finish_quarantined_article_dispatched")
            charges, reserves = operational.execute("SELECT COALESCE(SUM(charged_nanousd),0),COALESCE(SUM(reserved_nanousd),0) FROM budget_entries").fetchone()
            require(charges >= plan["initial_totals"]["charged_nanousd"] and charges + reserves <= state.HARD_CAP, "shared_budget_changed_or_exceeded")
            require(len(created) <= plan["count_cap"] and created.issubset(allowed), "queue_cap")
            latest = source.execute("SELECT payload FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (handoff.CHECKPOINT,)).fetchone()
            # A mismatch is expected while the live runner has uncheckpointed work.
            checkpoint_matches = bool(latest and json.loads(latest[0])["state_sha256"] == operational_sha256)
            if checkpoint_matches and standard_row:
                if operational.execute("SELECT 1 FROM sqlite_master WHERE name='standard_attempts'").fetchone():
                    require({r[0] for r in operational.execute("SELECT custom_id FROM standard_attempts WHERE status='saved'")} == standard_saved,
                        "standard_result_checkpoint_coverage")
                if combined_row and operational.execute("SELECT 1 FROM sqlite_master WHERE name='codex_attempts'").fetchone():
                    require({r[0] for r in operational.execute("SELECT attempt FROM codex_attempts WHERE status='saved'")} == codex_saved,
                        "codex_result_checkpoint_coverage")
            value = {"source_owner": str(owner), "plan": data["plan"], "head_seq": head[0], "head_hash": head[1],
                "previous_head_seq": start, "new_events_verified": head[0] - start, "artifacts_hashed": len(artifacts.checked),
                "new_files_replayed": files_checked, "new_results_replayed": sum(new_raw.values()),
                "new_raw_counts": [{"corpus": k[0], "status": k[1], "count": v} for k, v in sorted(new_raw.items())],
                "new_derived_counts": [{"corpus": k[0], "status": k[1], "count": v} for k, v in sorted(new_derived.items())],
                "total_raw_counts": [{"corpus": k[0], "status": k[1], "count": v} for k, v in sorted(total_raw.items())],
                "total_derived_counts": [{"corpus": k[0], "status": k[1], "count": v} for k, v in sorted(total_derived.items())],
                "created_article_intents": len(created), "http_intents": len(intents), "http_receipts": len(receipts),
                "unresolved_including_inflight": len(intents) - len(receipts), "charged_nanousd": charges, "reserved_nanousd": reserves,
                "codex_intents": len(codex_intents), "codex_saved": len(codex_saved),
                "codex_inflight_without_saved_response": len(codex_intents) - len(codex_saved),
                "operational_state_matches_latest_checkpoint": checkpoint_matches,
                "integrity_passed": True, "semantic_accuracy_confirmed": False, "checked_at": utc(), "protocol": protocol}
        finally:
            source.close()
            if operational is not None:
                operational.close()
        identifier = self.ledger.record(session, CHECKPOINT, str(owner), value)
        handoff.atomic_json(self.ledger.root / "latest-integrity.json", {"id": identifier, **value})
        return {"id": identifier, **value}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path, required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    engine = BatchIntegrity(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"source_owner": str(args.source_owner), "plan": args.plan},
            objective="Check incremental API Batch integrity and validation without changing the worker", actor="codex:batch-integrity")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        stop = args.source_owner / "STOP"
        if not stop.exists():
            stop.write_text("Batch integrity check failed: " + type(error).__name__ + "\n", encoding="utf-8")
        raise
    finally:
        engine.close()


if __name__ == "__main__":
    main()
