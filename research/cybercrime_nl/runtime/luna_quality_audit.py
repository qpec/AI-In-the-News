"""One bounded full-source Decisions quality audit; all research uses Research.execute."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

import dossier_contract as contract
import dossier_transport as transport
import luna_quality_design as design_module
import luna_quality_source as source_module
from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, require_active, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "research/cybercrime_nl/LUNA_QUALITY_AUDIT.md"
METHOD = "cybercrime-nl-luna-quality-audit-20261024-v1"
OWNER_NAME = "cybercrime-nl-luna-quality-audit-20261024-v1"
INTENT = "luna_quality_preparation_intent"
SOURCE = "luna_quality_frozen_source"
PLAN = "luna_quality_plan"
LAUNCH = "luna_quality_first_admission"
RESPONSE = "luna_quality_response"
REPORT = "luna_quality_report"
END = "luna_quality_run_end"
MAX_WORKERS, RPM, TPM = 8, 500, 800_000
PREPARE_SECONDS, RUN_SECONDS = 1800, 3600
USD_PER_EUR_NANO = 1_119_300_000
CAP = 15 * USD_PER_EUR_NANO
PRICE = {"input_nanousd_per_token": 110, "maximum_nanousd_per_token": 138,
    "output_nanousd_per_token": 0, "long_context_threshold": 272_000, "long_context_multiplier": 2,
    "checked_at": "2026-10-24T18:29:15Z", "source": "https://developers.openai.com/api/docs/guides/decisions",
    "usd_per_eur_nano": USD_PER_EUR_NANO,
    "fx_source": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
    "fx_date": "2026-10-23", "total_eur": 20, "api_eur": 15, "tax_fx_buffer_eur": 5}
APPROVAL = {"instruction": "Implement the proposed plan.", "approval_event": "a5eb74088e52dd482175956c",
    "approval_payload_sha256": "09059157ae3081e1e803b9d37524da41761b205d717b90057d6652f79ee63f9d",
    "budget_event": "b292bfb062a28eae23f79fd2", "budget_payload_sha256": "27e1757a407201312b9b6077f6545be724058fef552582934217b03daaa4367c"}


def require(value, reason):
    if not value:
        raise AuditError("luna_quality_" + reason)


def now():
    return datetime.now(timezone.utc)


def implementation():
    files = [Path(__file__), Path(contract.__file__), Path(transport.__file__), Path(design_module.__file__),
        Path(source_module.__file__), SPEC, Path(__file__).with_name("run_luna_quality_audit_with_key.ps1"),
        ROOT / "src/newsresearch/runtime.py", ROOT / "src/newsresearch/gateway.py",
        ROOT / "src/newsresearch/common.py", ROOT / "src/newsresearch/storage.py",
        ROOT / "src/newsresearch/embeddings.py", Path(__file__).with_name("final_validation_design.py"),
        ROOT / "pyproject.toml", ROOT / "uv.lock"]
    result = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for module in (source_module, design_module):
        if hasattr(module, "implementation"):
            result.update(module.implementation())
    return result


def reservation(packet):
    tokens = packet["wire_bytes"] + 4096
    return tokens * PRICE["maximum_nanousd_per_token"] * (2 if tokens > PRICE["long_context_threshold"] else 1)


def observed_cost(response):
    """Conservative charge estimate, never an invoice or a zero for unknown usage."""
    usage = response.usage
    if response.model != contract.MODEL or not isinstance(usage, dict):
        return None
    tokens = usage.get("input_tokens")
    details = usage.get("input_tokens_details", {})
    if type(tokens) is not int or not 0 <= tokens <= 1_050_000 or not isinstance(details, dict):
        return None
    values = [details.get("cached_tokens", 0), details.get("cache_write_tokens", 0)]
    if any(type(v) is not int or v < 0 for v in values) or sum(values) > tokens:
        return None
    return tokens * PRICE["maximum_nanousd_per_token"] * (2 if tokens > PRICE["long_context_threshold"] else 1)


def packet_labels(packet, payload):
    parsed = contract.parse_decisions(packet, payload)
    answers = parsed["answers"].values()
    clear = {a["document_id"] for a in answers if a["kind"] == "clarity" and a["status"] == "valid"
        and a["label"] == "clear_single_event" and a["probability"] >= .85}
    labels, scores = {}, []
    for answer in answers:
        if answer["kind"] != "pair":
            continue
        key = digest(sorted(packet["source_bindings"][i]["document_id"] for i in (answer["left"], answer["right"])))
        label = "unknown"
        if (answer["status"] == "valid" and {answer["left"], answer["right"]} <= clear
                and answer["probability"] >= .85):
            if answer["label"] == "same_event":
                label = "same_event"
            elif answer["label"] in {"different_event", "related_event"}:
                label = "negative"
        labels[key] = label
        scores.append({"pair_key": key, "label": answer["label"], "chosen_probability": answer["probability"],
            "confidence": answer["confidence"], "resolved_label": label})
    return parsed, labels, scores


def outcome(packet, response):
    raw = response.raw_response or {}
    cost = observed_cost(response)
    parsed = labels = None
    validation_error = None
    if response.payload is not None:
        try:
            parsed, labels, _ = packet_labels(packet, response.payload)
        except (ResearchError, TypeError, KeyError, ValueError, AttributeError) as error:
            validation_error = type(error).__name__
    hold = bool(raw.get("unknown_outcome")) or cost is None or cost > packet["reservation_nanousd"]
    usable = not hold and parsed is not None and response.model == contract.MODEL and raw.get("http_status") == 200
    fatal = None
    if raw.get("http_status") in {400, 401, 403, 404}:
        fatal = "provider_authentication_or_configuration"
    elif raw.get("http_status") == 429:
        fatal = "provider_quota_or_rate_limit"
    elif (raw.get("http_status") == 200 and response.model != contract.MODEL) or raw.get("error_type") in {"AuditError", "ResearchError"}:
        fatal = "model_or_dispatch_integrity"
    elif cost is not None and cost > packet["reservation_nanousd"]:
        fatal = "reservation_breach"
    return {"cost_nanousd": cost, "hold": hold, "usable": usable, "pair_labels": labels if usable else {},
        "validation_error": validation_error, "http_status": raw.get("http_status"), "fatal": fatal}, parsed


def build_packets(source, design, count_tokens):
    documents = source["documents"]
    tasks = design["pair_tasks"]
    require(len({r["pair_key"] for r in tasks}) == len(tasks), "duplicate_pair_tasks")
    packets, unavailable, pairs, ids = [], {}, [], []

    def build(selected_pairs, selected_ids):
        neutral = {identity: f"A{n + 1}" for n, identity in enumerate(selected_ids)}
        full = []
        for identity in selected_ids:
            document = contract.document_evidence({**documents[identity], "document_id": identity})
            full.append({**document, "document_id": neutral[identity]})
        packet = contract.seed_request(full, pairs=[(neutral[a], neutral[b]) for a, b in selected_pairs], count_tokens=count_tokens)
        packet["source_bindings"] = {neutral[i]: {"document_id": i,
            "input_sha256": digest({k: documents[i][k] for k in ("title", "body")})} for i in selected_ids}
        return packet

    def flush():
        nonlocal pairs, ids
        if pairs:
            packet = build(pairs, ids)
            packet["pair_keys"] = [digest(sorted(p)) for p in pairs]
            packet["reservation_nanousd"] = reservation(packet)
            packet["task_key"] = digest([METHOD, packet["request_sha256"], packet["pair_keys"]])
            packets.append(packet)
        pairs, ids = [], []

    for row in tasks:
        left, right = row["left"], row["right"]
        require(left != right and {left, right} <= set(documents) and row["pair_key"] == digest(sorted([left, right])), "pair_source_binding")
        extra = [i for i in (left, right) if i not in ids]
        if len(ids) + len(extra) > contract.MAX_ARTICLES:
            flush()
            extra = [left, right]
        try:
            build([*pairs, (left, right)], [*ids, *extra])
        except ResearchError as error:
            if str(error) != "dossier_packet_capacity":
                raise
            flush()
            try:
                build([(left, right)], [left, right])
            except ResearchError as isolated:
                if str(isolated) != "dossier_packet_capacity":
                    raise
                unavailable[row["pair_key"]] = "complete_pair_exceeds_packet_capacity"
                continue
            extra = [left, right]
        pairs.append((left, right))
        ids.extend(extra)
    flush()
    require({p for packet in packets for p in packet["pair_keys"]} | set(unavailable) == {r["pair_key"] for r in tasks}, "packet_pair_partition")
    require(sum(len(p["pair_keys"]) for p in packets) + len(unavailable) == len(tasks), "packet_pair_duplicates")
    return packets, unavailable


def version_contents(desired):
    return {"protocol": desired, "question": {"text": "Frozen dossier precision, candidate-limited recall and singleton top20 missed matches"},
        "selection": {"rules": "Fixed probability samples and deduplicated execution from the registered frozen source and seed"},
        "dossier_definition": {"unit": "One specific focal occurrence; dependent model-reference audit only"},
        "codebook": {"labels": list(contract.PAIR_LABELS), "threshold": .85},
        "prompt": {"instructions": contract.PAIR_RULES, "clarity": contract.CLARITY_RULES},
        "profile": {"mode": "systematic", "population_estimate": False},
        "policy": {"approval": desired["approval"], "price": PRICE, "api_cap_nanousd": CAP, "new_study_only": True}}


def verify_source_binding(source, desired):
    provenance = source["provenance"]
    require(provenance["method"] == source_module.METHOD
        and provenance["implementation"] == source_module.implementation()
        and digest(provenance["binding"]) == digest(desired["binding"])
        and provenance["source_owner"] == str(Path(desired["source_owner"]).resolve())
        and provenance["snapshot_owner"] == str(Path(desired["snapshot_owner"]).resolve())
        and provenance["source_head"] == desired["binding"]["source_head"]
        and provenance["source_heads_stable_during_copy"] is True
        and provenance["source_quiescence_verified_during_copy"] is True,
        "frozen_source_binding")


def health_state(intents, responses):
    keys = list(intents)
    health = [responses[key]["usable"] if key in responses else False for key in keys[-32:]]
    consecutive = 0
    for good in reversed(health):
        if good:
            break
        consecutive += 1
    fatal = next((r["fatal"] for r in responses.values() if r["fatal"]), None)
    if not fatal and (consecutive >= 8 or sum(not x for x in health) >= 16):
        fatal = "durable_response_health_guard"
    if not fatal and keys and not responses.get(keys[0], {}).get("usable", False):
        fatal = "first_fixed_packet_operational_gate_failed"
    return {"consecutive_failed_or_held": consecutive, "failed_or_held_in_last32": sum(not x for x in health), "stop_reason": fatal}


class Audit(Research):
    def __init__(self, root, *, config=None):
        require(Path(root).name == OWNER_NAME, "separate_owner_required")
        super().__init__(root, config=config or Config(offline=True))
        self._progress_lock = threading.Lock()
        self._progress_state = {}
        self._progress_failures = []
        self._dispatch_stop = threading.Event()

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        require(operation == "status" and not versions, "operation_boundary")
        data = payload or {}
        require(data.get("action") in {"prepare", "run", "status", "report"}, "action")
        fields = {"action", "source_owner", "snapshot_owner", "binding", "seed", "approval"} if data["action"] == "prepare" else {"action", "allow_paid_execution"} if data["action"] == "run" else {"action"}
        require(set(data) == fields, "operation_fields")
        return super().execute(operation, data, objective=objective, actor=actor)

    def rows(self, kind):
        return [{"id": r["id"], **json.loads(r["payload"])} for r in self.ledger.db.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def one(self, kind, optional=False):
        rows = self.rows(kind)
        require(len(rows) <= 1 and (optional or len(rows) == 1), "unique_" + kind)
        return rows[0] if rows else None

    def guard(self, *, deadline=None, code=None):
        require(not (self.ledger.root / "STOP").exists(), "stopped")
        if deadline is not None:
            require(now() < datetime.fromisoformat(deadline), "expired")
        require(not self._progress_failures, "progress_unavailable")
        if code is not None:
            require(implementation() == code, "implementation_changed")

    def progress(self, **values):
        with self._progress_lock:
            self._progress_state.update(values)
            value = {"method": METHOD, "at": utc(), **self._progress_state}
            path = self.ledger.root / "progress.json"
            require(not path.is_symlink() and not path.is_junction(), "progress_link")
            temporary = self.ledger.root / ("progress-" + uuid.uuid4().hex + ".writing")
            try:
                with temporary.open("w", encoding="utf-8") as stream:
                    stream.write(canonical(value))
                    stream.flush()
                    os.fsync(stream.fileno())
                check_permissions(temporary)
                until = time.monotonic() + 5
                while True:
                    try:
                        os.replace(temporary, path)
                        break
                    except PermissionError:
                        if time.monotonic() >= until:
                            raise
                        time.sleep(.05)
            finally:
                if temporary.exists():
                    temporary.unlink()

    def source_progress(self, status):
        self.progress(**status)

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        started = time.monotonic()
        finished = threading.Event()
        self._progress_failures = []
        def heartbeat():
            while not finished.wait(30):
                try:
                    self.progress(elapsed_seconds=round(time.monotonic() - started, 3))
                except Exception as error:
                    self._progress_failures.append(error)
                    break
        self.progress(stage=data["action"], elapsed_seconds=0)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if data["action"] == "prepare":
                result = self.prepare(session, context, data)
            else:
                plan, source, design, packets = self.load_plan()
                if data["action"] == "run":
                    result = self.run(session, plan, source, design, packets, data)
                else:
                    result = self.report(session, plan, source, design, packets)
            if self._progress_failures:
                raise self._progress_failures[0]
            return result
        finally:
            finished.set()
            thread.join(timeout=2)

    def prepare(self, session, context, data):
        self.guard()
        require(self.config.offline, "offline_preparation")
        require(isinstance(data["seed"], str) and 16 <= len(data["seed"]) <= 256, "seed")
        raw_spec = SPEC.read_bytes()
        require(data["approval"] == {**APPROVAL, "method_sha256": hashlib.sha256(raw_spec).hexdigest()}, "approval")
        require(self.ledger.root.resolve() not in {Path(data["source_owner"]).resolve(), Path(data["snapshot_owner"]).resolve()}, "source_owner_isolation")
        prior = self.one(INTENT, optional=True)
        started = prior["prepare_started_at"] if prior else now().isoformat()
        expires = prior["prepare_expires_at"] if prior else (datetime.fromisoformat(started) + timedelta(seconds=PREPARE_SECONDS)).isoformat()
        require(datetime.fromisoformat(expires) - datetime.fromisoformat(started) == timedelta(seconds=PREPARE_SECONDS), "preparation_window")
        desired = {"method": METHOD, "implementation": implementation(), "source_owner": data["source_owner"],
            "snapshot_owner": data["snapshot_owner"], "binding": data["binding"], "seed": data["seed"],
            "approval": data["approval"], "price": PRICE, "api_cap_nanousd": CAP,
            "duration_seconds": RUN_SECONDS, "prepare_seconds": PREPARE_SECONDS,
            "prepare_started_at": started, "prepare_expires_at": expires,
            "maximum_workers": MAX_WORKERS, "requests_per_minute": RPM, "estimated_tokens_per_minute": TPM}
        require(prior is None or {k: v for k, v in prior.items() if k != "id"} == desired, "changed_preparation")
        if self.one(PLAN, optional=True):
            plan, source, design, packets = self.load_plan()
            return self.report(session, plan, source, design, packets)
        self.guard(deadline=expires)
        require(not self.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone(), "preparation_after_model")
        intent = prior["id"] if prior else self.ledger.record(session, INTENT, METHOD, desired)
        require(self.ledger.artifacts.put_bytes(raw_spec) == data["approval"]["method_sha256"], "method_snapshot")
        versions = {}
        for kind, content in version_contents(desired).items():
            existing = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, METHOD)))
            require(len(existing) <= 1, "duplicate_version")
            if existing:
                version = self.ledger.get(existing[0][0], kind)
                require(version["content"] == content and version["reason"] is None and version["branch"] == "main", "version_changed")
                versions[kind] = existing[0][0]
            else:
                versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        deadline = time.monotonic() + max(0, (datetime.fromisoformat(expires) - now()).total_seconds())
        saved = self.one(SOURCE, optional=True)
        if saved:
            require(saved["intent"] == intent, "source_intent")
            source = self.ledger.artifacts.read(saved["artifact"])
            verify_source_binding(source, desired)
        else:
            source = source_module.load_frozen(self, session, source_owner=Path(data["source_owner"]),
                snapshot_owner=Path(data["snapshot_owner"]), binding=data["binding"], deadline_monotonic=deadline)
            self.guard(code=desired["implementation"])
            require(time.monotonic() < deadline, "preparation_deadline")
            verify_source_binding(source, desired)
            self.ledger.record(session, SOURCE, intent, {"intent": intent, "artifact": self.ledger.artifacts.put(source)})
        self.progress(stage="building_fixed_design", source_inputs=len(source["documents"]))
        design = design_module.build_design(source, data["seed"])
        encoder = offline_tokenizer()
        packets, unavailable = build_packets(source, design, lambda text: len(encoder.encode(text, disallowed_special=())))
        total = sum(p["reservation_nanousd"] for p in packets)
        self.progress(stage="manifest_budget_preflight", planned_requests=len(packets),
            selected_distinct_pairs=len(design["pair_tasks"]), full_manifest_reservation_nanousd=total,
            api_cap_nanousd=CAP, reservation_excess_nanousd=max(0, total-CAP))
        require(total <= CAP, "full_manifest_reservation_exceeds_budget")
        self.guard(code=desired["implementation"])
        require(time.monotonic() < deadline, "preparation_deadline")
        optimistic = {r["pair_key"]: "negative" for r in design["pair_tasks"]}
        optimistic.update({r["pair_key"]: "same_event" for r in design["samples"]["precision"]["slots"]})
        value = {**desired, "intent": intent, "versions": versions, "source_artifact": self.ledger.artifacts.put(source),
            "design_artifact": self.ledger.artifacts.put(design), "packets_artifact": self.ledger.artifacts.put(packets),
            "unavailable_pairs": unavailable, "planned_requests": len(packets), "selected_distinct_pairs": len(design["pair_tasks"]),
            "full_manifest_reservation_nanousd": total, "best_case_report": design_module.compute_report(design, optimistic)}
        identifier = self.ledger.record(session, PLAN, intent, value)
        return self.report(session, {"id": identifier, **value}, source, design, packets)

    def load_plan(self):
        plan = self.one(PLAN)
        require(plan["implementation"] == implementation(), "implementation_changed")
        intent = self.one(INTENT)
        require(plan["intent"] == intent["id"] and all(plan.get(k) == v for k, v in intent.items() if k != "id"), "plan_intent")
        require(plan["api_cap_nanousd"] == CAP and plan["price"] == PRICE, "plan_budget")
        desired = {k: v for k, v in intent.items() if k != "id"}
        expected_versions = version_contents(desired)
        require(set(plan["versions"]) == set(expected_versions), "version_partition")
        for kind, content in expected_versions.items():
            rows = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, METHOD)))
            require(len(rows) == 1 and rows[0][0] == plan["versions"][kind], "version_identity")
            value = self.ledger.get(rows[0][0], kind)
            require(digest(value["content"]) == digest(content) and value["branch"] == "main" and value["reason"] is None, "version_changed")
        require(plan["approval"] == {**APPROVAL, "method_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest()}, "approval")
        source = self.ledger.artifacts.read(plan["source_artifact"])
        saved = self.one(SOURCE)
        require(saved["intent"] == plan["intent"] and saved["artifact"] == plan["source_artifact"], "source_checkpoint_binding")
        verify_source_binding(source, desired)
        design = self.ledger.artifacts.read(plan["design_artifact"])
        packets = self.ledger.artifacts.read(plan["packets_artifact"])
        require(design == design_module.build_design(source, plan["seed"]), "design_replay")
        encoder = offline_tokenizer()
        rebuilt, unavailable = build_packets(source, design, lambda text: len(encoder.encode(text, disallowed_special=())))
        require(packets == rebuilt and unavailable == plan["unavailable_pairs"]
            and sum(p["reservation_nanousd"] for p in packets) == plan["full_manifest_reservation_nanousd"] <= CAP
            and len(packets) == plan["planned_requests"] and len(design["pair_tasks"]) == plan["selected_distinct_pairs"], "packet_replay")
        return plan, source, design, packets

    def census(self, plan, packets):
        bykey = {p["task_key"]: p for p in packets}
        intents, attempts = {}, {}
        for raw in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
            value = json.loads(raw[0])
            key, attempt = value.get("task_key"), value.get("attempt")
            require(key in bykey and key not in intents and attempt not in attempts and value.get("batch") == plan["id"], "attempt_scope_or_retry")
            packet = bykey[key]
            require(value["number"] == 1 and value["packet"] == digest(packet) and value["request"] == packet["request_sha256"]
                and value["reserved_nanousd"] == packet["reservation_nanousd"] and value["method"] == METHOD, "intended_packet")
            invocation = transport.Invocation(packet["request"], attempt)
            require(self.ledger.artifacts.read(value["dispatch"]) == invocation.manifest(), "intended_dispatch")
            intents[key], attempts[attempt] = value, key
        receipts = {}
        for raw in self.ledger.db.execute("SELECT payload FROM events WHERE kind='luna_quality.response.received' ORDER BY seq"):
            row = json.loads(raw[0])
            attempt = row["attempt"]
            require(attempt in attempts and attempt not in receipts, "received_response_identity")
            packet = bykey[attempts[attempt]]
            retained = ProviderResponse(**self.ledger.artifacts.read(row["response"]))
            derived, parsed = outcome(packet, retained)
            receipts[attempt] = {"reference": row["response"], "raw": retained, "derived": derived, "parsed": parsed}
        responses = {}
        input_tokens = 0
        measured_responses = 0
        for receipt in receipts.values():
            if receipt["derived"]["cost_nanousd"] is not None:
                input_tokens += receipt["raw"].usage["input_tokens"]
                measured_responses += 1
        for value in self.rows(RESPONSE):
            key = value["task_key"]
            require(key in intents and key not in responses and value["attempt"] == intents[key]["attempt"]
                and value["plan"] == plan["id"], "response_identity")
            require(value["attempt"] in receipts and receipts[value["attempt"]]["reference"] == value["response"], "response_receipt_binding")
            receipt = receipts[value["attempt"]]
            derived, parsed = receipt["derived"], receipt["parsed"]
            require(all(digest(value.get(k)) == digest(v) for k, v in derived.items()), "response_accounting_replay")
            require(value["parsed"] == (digest(parsed) if parsed else None), "response_parser_replay")
            responses[key] = value
        completions = {}
        for raw in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.completed'"):
            value = json.loads(raw[0])
            require(value["attempt"] in attempts and value["attempt"] not in completions, "completion_scope")
            key = attempts[value["attempt"]]
            require(key in responses and responses[key]["id"] == value["assessment"]
                and responses[key]["response"] == value["response"] and not responses[key]["hold"], "completion_binding")
            completions[value["attempt"]] = value
        settled = held = 0
        labels, scores = {}, []
        for key, intended in intents.items():
            row = responses.get(key)
            receipt = receipts.get(intended["attempt"])
            cost = receipt["derived"]["cost_nanousd"] if receipt else None
            if intended["attempt"] in completions:
                require(type(cost) is int and cost >= 0, "settled_cost_missing")
                settled += cost
            else:
                held += max(intended["reserved_nanousd"], cost or 0)
            if row and row["usable"] and intended["attempt"] in completions:
                _, current, current_scores = packet_labels(bykey[key], receipt["raw"].payload)
                require(current == row["pair_labels"], "response_labels_replay")
                labels.update(current)
                scores.extend(current_scores)
        require(set(self.ledger.unresolved) == set(attempts) - set(completions), "unresolved_inventory")
        health_responses = dict(responses)
        for attempt, receipt in receipts.items():
            if attempts[attempt] not in responses:
                health_responses[attempts[attempt]] = {**receipt["derived"], "usable": False}
        return {"intents": intents, "responses": responses, "settled_nanousd": settled, "held_nanousd": held,
            "committed_nanousd": settled + held, "labels": labels, "scores": scores,
            "returned_requests": len(receipts), "unreturned_requests": len(intents) - len(receipts), "unknown_holds": len(attempts) - len(completions),
            "health": health_state(intents, health_responses), "observed_usage": {"input_tokens": input_tokens,
                "responses_with_valid_input_usage": measured_responses, "responses_without_valid_input_usage": len(receipts) - measured_responses,
                "cache_breakdown_not_inferred": True}}

    def provider(self, plan, deadline, packets):
        next_at = [time.monotonic()]
        byrequest = {p["request_sha256"]: p for p in packets}
        def before(invocation):
            require(not self._dispatch_stop.is_set(), "dispatch_stopped")
            self.guard(deadline=deadline, code=plan["implementation"])
            require(invocation.kind == "decisions" and digest(invocation.request) in byrequest, "dispatch_request")
            packet = byrequest[digest(invocation.request)]
            while time.monotonic() < next_at[0]:
                require(not self._dispatch_stop.is_set(), "dispatch_stopped")
                self.guard(deadline=deadline)
                time.sleep(min(.2, max(0, next_at[0] - time.monotonic())))
            self.guard(deadline=deadline)
            require(not self._dispatch_stop.is_set(), "dispatch_stopped")
            next_at[0] = time.monotonic() + max(60 / RPM, packet["input_tokens_proxy"] * 1.25 * 60 / TPM)
            return True
        return transport.UnifiedTransport(before_dispatch=before)

    def complete(self, session, intended, response_ref, assessment, status):
        def project(event):
            self.ledger.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (
                intended["attempt"], intended["task_key"], intended["batch"], 1, intended["request"],
                response_ref, status, assessment, None, event))
        self.ledger.append(session, "model.attempt.completed", {"attempt": intended["attempt"], "status": status,
            "assessment": assessment, "response": response_ref, "ended_at": utc()}, project)
        self.ledger.unresolved.pop(intended["attempt"])

    def run(self, session, plan, source, design, packets, data):
        require(not self.config.offline and data["allow_paid_execution"] is True
            and bool(os.environ.get("OPENAI_API_KEY")), "explicit_paid_permission_and_key")
        self.guard(code=plan["implementation"])
        state = self.census(plan, packets)
        if state["health"]["stop_reason"]:
            return self.report(session, plan, source, design, packets)
        launch = self.one(LAUNCH, optional=True)
        require(launch is not None or not state["intents"], "attempt_before_first_admission")
        ready = [p for p in packets if p["task_key"] not in state["intents"]]
        if not ready:
            return self.report(session, plan, source, design, packets)
        if not launch:
            started = now()
            value = {"plan": plan["id"], "started_at": started.isoformat(), "expires_at": (started + timedelta(seconds=RUN_SECONDS)).isoformat(),
                "duration_seconds": RUN_SECONDS, "api_cap_nanousd": CAP}
            identifier = self.ledger.record(session, LAUNCH, plan["id"], value)
            launch = {"id": identifier, **value}
        require(launch["plan"] == plan["id"] and launch["duration_seconds"] == RUN_SECONDS and launch["api_cap_nanousd"] == CAP, "launch_binding")
        require(datetime.fromisoformat(launch["expires_at"]) - datetime.fromisoformat(launch["started_at"]) == timedelta(seconds=RUN_SECONDS), "launch_window")
        deadline = launch["expires_at"]
        self._dispatch_stop.clear()
        provider = self.provider(plan, deadline, packets)
        reason, start = "fixed_manifest_processed", 0
        while start < len(ready):
            try:
                self.guard(deadline=deadline, code=plan["implementation"])
            except AuditError as error:
                reason = str(error)
                break
            if state["health"]["stop_reason"]:
                reason = state["health"]["stop_reason"]
                break
            wave, rows = [], []
            width = MAX_WORKERS if state["intents"] else 1
            for packet in ready[start:start + width]:
                if state["committed_nanousd"] + sum(r["reserved_nanousd"] for r in rows) + packet["reservation_nanousd"] > CAP:
                    reason = "budget_bound"
                    break
                self.guard(deadline=deadline, code=plan["implementation"])
                attempt = str(uuid.uuid4())
                invocation = transport.Invocation(packet["request"], attempt)
                intended = {"method": METHOD, "attempt": attempt, "task_key": packet["task_key"], "number": 1,
                    "batch": plan["id"], "request": self.ledger.artifacts.put(packet["request"]),
                    "packet": self.ledger.artifacts.put(packet), "dispatch": self.ledger.artifacts.put(invocation.manifest()),
                    "reserved_nanousd": packet["reservation_nanousd"], "started_at": utc()}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                rows.append(intended)
                wave.append((invocation, attempt))
            if not wave:
                break
            for intended in rows:
                state["intents"][intended["task_key"]] = intended
                state["held_nanousd"] += intended["reserved_nanousd"]
                state["unknown_holds"] += 1
            state["committed_nanousd"] = state["settled_nanousd"] + state["held_nanousd"]
            for position, response in self.gateway.codex_dispatch(session, provider, wave, len(wave)):
                intended = rows[position]
                packet = ready[start + position]
                response_ref = self.ledger.artifacts.put(asdict(response))
                self.ledger.append(session, "luna_quality.response.received", {"attempt": intended["attempt"], "response": response_ref})
                derived, parsed = outcome(packet, response)
                row = {"plan": plan["id"], "task_key": intended["task_key"], "attempt": intended["attempt"],
                    "response": response_ref, "parsed": self.ledger.artifacts.put(parsed) if parsed else None,
                    **derived, "at": utc()}
                identifier = self.ledger.record(session, RESPONSE, intended["task_key"], row)
                state["responses"][intended["task_key"]] = {"id": identifier, **row}
                if not derived["hold"]:
                    self.complete(session, intended, response_ref, identifier, "valid" if derived["usable"] else "invalid")
                    state["held_nanousd"] -= intended["reserved_nanousd"]
                    state["settled_nanousd"] += derived["cost_nanousd"]
                    state["unknown_holds"] -= 1
                    state["labels"].update(derived["pair_labels"])
                else:
                    self.ledger.unresolved[intended["attempt"]]["cost_nanousd"] = derived["cost_nanousd"]
                    state["held_nanousd"] += max(0, (derived["cost_nanousd"] or 0) - intended["reserved_nanousd"])
                if derived["fatal"]:
                    self._dispatch_stop.set()
                    reason = derived["fatal"]
            state["committed_nanousd"] = state["settled_nanousd"] + state["held_nanousd"]
            state["health"] = health_state(state["intents"], state["responses"])
            self.progress(stage="running", planned_requests=len(packets), attempted_requests=len(state["intents"]),
                returned_requests=len(state["responses"]), planned_pairs=plan["selected_distinct_pairs"],
                resolved_pairs=sum(v != "unknown" for v in state["labels"].values()), unknown_pairs=plan["selected_distinct_pairs"] - sum(v != "unknown" for v in state["labels"].values()),
                settled_nanousd=state["settled_nanousd"], held_nanousd=state["held_nanousd"], remaining_nanousd=max(0, CAP-state["committed_nanousd"]), expires_at=deadline)
            start += len(wave)
            if reason != "fixed_manifest_processed" or state["health"]["stop_reason"]:
                reason = state["health"]["stop_reason"] or reason
                break
        self.ledger.record(session, END, str(uuid.uuid4()), {"plan": plan["id"], "reason": reason, "at": utc()})
        return self.report(session, plan, source, design, packets)

    def report(self, session, plan, source, design, packets):
        state = self.census(plan, packets)
        results = design_module.compute_report(design, state["labels"])
        histogram = Counter("unknown" if r["chosen_probability"] is None else f"{min(9, int(r['chosen_probability'] * 10)) / 10:.1f}–{min(10, int(r['chosen_probability'] * 10) + 1) / 10:.1f}" for r in state["scores"])
        errors = []
        selected = {r["pair_key"]: "precision" for r in design["samples"]["precision"]["slots"]}
        selected.update({r["pair_key"]: "nonjoined" for r in design["samples"]["nonjoined"]["slots"]})
        for task in design["pair_tasks"]:
            key = task["pair_key"]
            if (selected.get(key) == "precision" and state["labels"].get(key) == "negative") or (selected.get(key) == "nonjoined" and state["labels"].get(key) == "same_event"):
                errors.append({"pair_key": key, "component": selected[key], "left": task["left"], "right": task["right"],
                    "source_artifact": plan["source_artifact"], "label": state["labels"][key]})
        value = {"method": METHOD, "plan": plan["id"], "analysis": results, "best_case_report": plan["best_case_report"],
            "planned_requests": len(packets), "attempted_requests": len(state["intents"]), "returned_requests": state["returned_requests"],
            "assessed_response_records": len(state["responses"]),
            "unattempted_requests": len(packets) - len(state["intents"]), "unreturned_requests": state["unreturned_requests"],
            "selected_distinct_pairs": plan["selected_distinct_pairs"], "resolved_pairs": sum(v != "unknown" for v in state["labels"].values()),
            "unknown_pairs": plan["selected_distinct_pairs"] - sum(v != "unknown" for v in state["labels"].values()),
            "capacity_unknown_pairs": len(plan["unavailable_pairs"]), "score_distribution": dict(histogram),
            "scores_artifact": self.ledger.artifacts.put(state["scores"]), "error_examples": errors[:20],
            "settled_nanousd": state["settled_nanousd"], "held_nanousd": state["held_nanousd"],
            "committed_nanousd": state["committed_nanousd"], "unknown_holds": state["unknown_holds"],
            "response_health": state["health"], "price_basis": PRICE, "observed_usage": state["observed_usage"],
            "api_cap_nanousd": CAP, "remaining_nanousd": max(0, CAP-state["committed_nanousd"]),
            "cost_is_conservative_estimate_not_invoice": True, "old_budgets_and_dossiers_unchanged": True,
            "first_admission": self.one(LAUNCH, optional=True), "last_run": self.rows(END)[-1:]}
        identifier = self.ledger.record(session, REPORT, digest(value), value)
        self.progress(stage="report", planned_requests=value["planned_requests"], attempted_requests=value["attempted_requests"],
            resolved_pairs=value["resolved_pairs"], unknown_pairs=value["unknown_pairs"], settled_nanousd=value["settled_nanousd"],
            held_nanousd=value["held_nanousd"], remaining_nanousd=value["remaining_nanousd"])
        return {"id": identifier, **value}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "status", "report"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    require((args.input is not None) == (args.action == "prepare"), "cli_input")
    data = json.loads(args.input.read_text(encoding="utf-8")) if args.input else {}
    data["action"] = args.action
    if args.action == "run":
        data["allow_paid_execution"] = args.allow_paid_execution
    engine = Audit(args.workspace, config=Config(offline=args.action != "run"))
    try:
        print(json.dumps(engine.execute("status", data, objective="Approved bounded Luna dossier quality audit", actor="codex:luna-quality-audit")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
