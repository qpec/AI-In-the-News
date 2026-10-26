"""Unregistered initial-slot packet/resource bridge; no persistence or dispatch.

The parent must verify/freeze sources, frame, schedule, history inventory, order
seed, tokenizer and resource authority before using this output. This module
constructs exact full packets and immutable local dispositions, not permission.
load_token_counter reads only the hash-checked local public tokenizer cache; it
cannot download a vocabulary. All preparation itself operates on supplied data.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import hmac
import importlib.metadata
import json
from pathlib import Path
from types import MappingProxyType

import tiktoken
from tiktoken_ext.openai_public import cl100k_base

import final_validation_contract as contract
import final_validation_execution as execution
import final_validation_history as history
import final_validation_schedule as schedules
from final_validation_design import pair_from_rank
from final_validation_frame import ProbabilityFrame, build_input_index
from newsresearch.common import ResearchError, canonical, digest
from newsresearch.embeddings import VOCAB_HASH, offline_tokenizer

METHOD = "final-validation-initial-packet-preparation-v1"
ORDER_VERSION = "final-validation-role-source-order-v1"
ORDER_POLICY = "HMAC-SHA256-frozen-seed-frame-rank-role-low-bit-reversal-v1"


def require(value, reason):
    if not value:
        raise ResearchError("final_packets_" + reason)


def sha(value):
    history.sha(value)


def implementation():
    result = execution.implementation()
    root = Path(__file__).resolve().parents[3]
    files = [Path(__file__), Path(schedules.__file__), root / "src/newsresearch/embeddings.py",
             *[Path(__file__).with_name(name) for name in ("final_validation_frame.py", "final_validation_design.py")]]
    result.update({path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files})
    return result


def _bytes(value):
    return canonical(value).encode("utf-8")


def _hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _tokenizer_configuration():
    # Fail before the package constructor can read a missing/unverified cache.
    # Reconstruct from that verified vocabulary, not the mutable registry object.
    offline_tokenizer()
    return cl100k_base()


def _tokenizer_configuration_digest(configuration):
    return digest({"name": configuration["name"], "pattern": configuration["pat_str"],
        "special_tokens": configuration["special_tokens"], "vocabulary_sha256": VOCAB_HASH})


@dataclass(frozen=True)
class TokenCounter:
    identity_json: bytes
    evidence_record: str
    encoder: tiktoken.Encoding = field(repr=False, compare=False)

    @property
    def identity(self):
        return json.loads(self.identity_json)

    def validate(self):
        sha(self.evidence_record)
        require(type(self.identity_json) is bytes and self.identity_json == _bytes(self.identity), "tokenizer_identity_bytes")
        require(self.identity == {"encoding": "cl100k_base", "library": "tiktoken",
            "version": importlib.metadata.version("tiktoken")}, "tokenizer_identity")
        require(type(self.encoder) is tiktoken.Encoding and self.encoder.name == "cl100k_base", "tokenizer_encoder")
        configuration = _tokenizer_configuration()
        require(self.encoder._pat_str == configuration["pat_str"]
                and self.encoder._mergeable_ranks == configuration["mergeable_ranks"]
                and self.encoder._special_tokens == configuration["special_tokens"], "tokenizer_configuration")
        return _tokenizer_configuration_digest(configuration)

    def count(self, text):
        require(isinstance(text, str), "tokenizer_text")
        return len(self.encoder.encode(text, disallowed_special=()))


def load_token_counter(*, evidence_record, expected_identity):
    """Use the verified local cl100k vocabulary, never an arbitrary proxy callback.

    The evidence record's existence, registration timing and content remain parent
    obligations. No source/model/account probe or vocabulary download occurs here.
    """
    encoder = tiktoken.Encoding(**_tokenizer_configuration())
    result = TokenCounter(_bytes(expected_identity), evidence_record, encoder)
    result.validate()
    return result


def order_seed_payload(seed):
    require(isinstance(seed, str) and seed.strip(), "order_seed")
    return {"version": ORDER_VERSION, "seed": seed}


def _documents(frame, documents):
    require(isinstance(frame, ProbabilityFrame), "frame_required")
    index = frame.index
    rebuilt = build_input_index([{"document_id": r.document_id, "input_sha256": r.input_sha256,
        "article_row_ids": list(r.article_row_ids)} for r in index.inputs],
        {r.document_id: r.accepted_dossier_id for r in index.inputs}, bindings=dict(index.bindings))
    require(rebuilt == index, "input_index_binding")
    require(isinstance(documents, list) and len(documents) == len(index.inputs), "full_document_frame")
    result = []
    for indexed, row in zip(index.inputs, documents, strict=True):
        require(isinstance(row, dict) and row.get("document_id") == indexed.document_id, "document_manifest_order")
        title, body = row.get("title"), row.get("body")
        require(isinstance(title, str) and isinstance(body, str) and bool(body.strip()), "full_literal_document")
        actual = {"title_sha256": _hash_bytes(title.encode()), "body_sha256": _hash_bytes(body.encode()),
                  "input_sha256": digest({"title": title, "body": body})}
        require(actual["input_sha256"] == indexed.input_sha256
                and all(key not in row or row[key] == value for key, value in actual.items()), "document_hash_binding")
        result.append({"document_id": indexed.document_id, "title": title, "body": body, **actual})
    return result


def _identity(documents):
    return sorted([{key: row[key] for key in history.SOURCE_FIELDS} for row in documents], key=lambda r: r["document_id"])


def _article_order(frame_digest, rank, role, documents, seed):
    material = _bytes([ORDER_VERSION, frame_digest, rank, role])
    bit = hmac.new(seed.encode(), material, hashlib.sha256).digest()[0] & 1
    order = [row["document_id"] for row in documents]
    return list(reversed(order)) if bit else order


@dataclass(frozen=True)
class PreparedInitial:
    payload_json: bytes
    artifacts: object = field(repr=False)
    digest: str

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def tasks(self):
        return self.payload["tasks"]

    @property
    def catalog(self):
        return self.payload["slot_catalog"]

    def build_execution_manifest(self, admission_record):
        """Call after parent retains the exact protected upstream slot admission."""
        sha(admission_record)
        value = self.payload
        require(self.payload_json == _bytes(value) and self.digest == digest(value), "preparation_digest")
        require(value["implementation"] == implementation(), "implementation_changed")
        require(set(self.artifacts) == set(value["artifact_sha256"])
                and all(_hash_bytes(raw) == reference for reference, raw in self.artifacts.items()), "artifact_binding")
        result = execution.build_manifest(scope=value["execution_scope"], prefix=value["initial_prefix"],
            tasks=value["tasks"], cli_profile=value["cli_profile"], resources=value["resources"], upstream_binding=admission_record)
        require(result["slot_catalog_sha256"] == value["slot_catalog_sha256"]
                and result["planned_token_reservations"] == value["resource_census"]["planned_token_reservations"],
                "execution_projection_changed")
        return result


def prepare_initial_packets(frame, schedule, documents, *, historical_records, history_inventory,
                            order_seed, bindings, token_counter, cli_profile, resources,
                            user_instruction_sha256, max_input_tokens=contract.MAX_INPUT_TOKENS):
    """Map the verified fixed prefix to exact TASK_FIELDS without substitutions.

    Returned artifacts contain protected full packets and failed-capacity stdin.
    The caller retains each exact byte blob by its digest before registration.
    This does not verify parent evidence records or produce a dispatchable owner.
    """
    docs = _documents(frame, documents)  # Validate ALL frame inputs, not selected ones only.
    schedules.verify_schedule(frame, schedule)
    expected_fields = {"source_snapshot_record", "source_snapshot_artifact", "frame_verification_record",
        "history_verification_record", "history_records_sha256", "history_inventory_sha256",
        "order_seed_record", "order_seed_artifact", "tokenizer_evidence_record"}
    require(isinstance(bindings, dict) and set(bindings) == expected_fields, "upstream_binding_fields")
    for value in bindings.values():
        sha(value)
    sha(user_instruction_sha256)
    require(type(token_counter) is TokenCounter, "bound_token_counter_required")
    tokenizer_configuration = token_counter.validate()
    require(token_counter.evidence_record == bindings["tokenizer_evidence_record"], "tokenizer_evidence_binding")
    require(isinstance(cli_profile, dict) and cli_profile.get("tokenizer_identity") == token_counter.identity,
            "provider_tokenizer_binding")
    require(digest(order_seed_payload(order_seed)) == bindings["order_seed_artifact"], "order_seed_binding")
    history.validate_inventory(history_inventory)
    # Full historical consistency is checked before any per-pair lookups.
    history.normalize_records(historical_records)
    require(digest(historical_records) == bindings["history_records_sha256"]
            and digest(history_inventory) == bindings["history_inventory_sha256"], "history_inventory_binding")
    execution.validate_resources(resources)
    require(type(max_input_tokens) is int and 1 <= max_input_tokens <= contract.MAX_INPUT_TOKENS, "input_capacity_policy")
    prefix = schedule.manifest["initial_prefix"]
    require(prefix["reserved_invocations"] <= resources["maximum_invocations"], "resource_invocation_limit")
    tasks, catalog, details, artifacts, used_physical = [], [], [], {}, set()
    reservation, fresh = 0, 0

    def retain(raw):
        reference = _hash_bytes(raw)
        previous = artifacts.setdefault(reference, raw)
        require(previous == raw, "artifact_collision")
        return reference

    for slot in prefix["tasks"]:
        rank, role = slot["pair_rank"], slot["kind"]
        left, right = pair_from_rank(len(frame.index.inputs), rank)
        selected = [docs[left], docs[right]]
        identity = _identity(selected)
        entry = history.resolve_history(identity, role, historical_records, history_inventory)
        for attempt in entry["physical_attempts"]:
            key = (attempt["owner_sha256"], attempt["attempt_id"])
            require(key not in used_physical, "independent_slots_share_physical_judgment")
            used_physical.add(key)
        order = _article_order(frame.digest, rank, role, selected, order_seed)
        packet, capacity, observed = None, None, []
        if entry["state"] == "fresh_unattempted":
            def measure(text):
                tokens = token_counter.count(text)
                observed.append((text, tokens))
                return tokens
            try:
                packet = contract.request(selected, order=order, count_tokens=measure, max_input_tokens=max_input_tokens)
            except ResearchError as error:
                if str(error) != "final_pair_packet_capacity":
                    raise
                require(len(observed) == 1, "capacity_measurement_missing")
                stdin, tokens = observed[0]
                proof = {"method": METHOD, "reason_code": "full_pair_capacity", "pair_rank": rank, "role": role,
                    "source_identity": identity, "document_order": order, "definition_version": contract.DEFINITION_VERSION,
                    "stdin_artifact": retain(stdin.encode()), "input_tokens_proxy": tokens,
                    "input_bytes": len(stdin.encode()), "max_input_tokens": max_input_tokens,
                    "max_input_bytes": contract.MAX_INPUT_BYTES, "tokenizer_identity": token_counter.identity,
                    "tokenizer_evidence_record": token_counter.evidence_record, "new_model_calls": 0,
                    "provider_attempted": False, "no_truncation": True}
                require(tokens > max_input_tokens or proof["input_bytes"] > contract.MAX_INPUT_BYTES,
                        "capacity_failure_without_excess")
                capacity = {"reason_code": "full_pair_capacity", "evidence_sha256": retain(_bytes(proof))}
            if packet is not None:
                contract.validate_for_dispatch(packet, count_tokens=token_counter.count)
                require(execution.source_identity(packet) == identity, "packet_source_substitution")
                retain(_bytes(packet))
                fresh += 1
                reservation += packet["input_tokens_proxy"] + resources["output_token_allowance"]
        disposition = "fresh" if packet is not None else "reused" if entry["state"] == "reused_resolved" else "unavailable"
        task = {"pair_rank": rank, "role": role, "packet": packet, "history": entry, "capacity_unavailable": capacity}
        tasks.append(task)
        catalog.append({"pair_rank": rank, "role": role, "source_identity_sha256": digest(identity),
            "history_entry_sha256": entry["entry_sha256"], "capacity_unavailable": capacity,
            "disposition": disposition, "request_sha256": packet["request_sha256"] if packet else None})
        details.append({"pair_rank": rank, "role": role, "indexed_positions": [left, right],
            "source_identity": identity, "frozen_article_order": order, "disposition": disposition,
            "packet_artifact": digest(packet) if packet else None,
            "packet_bytes": len(_bytes(packet)) if packet else None,
            "request_bytes": len(_bytes(packet["request"])) if packet else None,
            "stdin_bytes": packet["input_bytes"] if packet else (len(observed[0][0].encode()) if observed else None),
            "input_tokens_proxy": packet["input_tokens_proxy"] if packet else (observed[0][1] if observed else None),
            "output_token_allowance": resources["output_token_allowance"] if packet else 0,
            "reservation_tokens": packet["input_tokens_proxy"] + resources["output_token_allowance"] if packet else 0,
            "capacity_evidence": capacity["evidence_sha256"] if capacity else None})
    require(reservation <= resources["maximum_token_reservations"], "resource_token_limit")
    counts = Counter(item["disposition"] for item in catalog)
    value = {"method": METHOD, "implementation": implementation(), "bindings": bindings,
        "input_index_digest": frame.index.digest, "frame_digest": frame.digest, "schedule_digest": schedule.digest,
        "initial_prefix": prefix, "tasks": tasks, "slot_catalog": catalog, "slot_catalog_sha256": digest(catalog),
        "slot_resource_details": details, "cli_profile": cli_profile, "resources": resources,
        "execution_scope": {"frame_sha256": frame.digest, "definition_version": contract.DEFINITION_VERSION,
            "user_instruction_sha256": user_instruction_sha256},
        "order_policy": ORDER_POLICY, "order_seed_binding": {"record": bindings["order_seed_record"],
            "artifact": bindings["order_seed_artifact"]},
        "tokenizer_binding": {"identity": token_counter.identity, "evidence_record": token_counter.evidence_record,
            "vocabulary_sha256": VOCAB_HASH, "configuration_sha256": tokenizer_configuration,
            "counter": "len(cl100k_base.encode(exact_stdin,disallowed_special=()))"},
        "resource_census": {"selected_primary_pairs": len(prefix["primary_ranks"]), "selected_slots": len(tasks),
            "reserved_schedule_invocations": prefix["reserved_invocations"], "fresh_potential_invocations": fresh,
            "reused_slots": counts["reused"], "unavailable_slots": counts["unavailable"],
            "capacity_deferred_slots": sum(t["capacity_unavailable"] is not None for t in tasks),
            "planned_token_reservations": reservation, "generation_token_cap_enforced": False,
            "coordinator_invocations_not_remote_requests": True, "account_dollar_cost": None},
        "artifact_sha256": sorted(artifacts), "no_substitution": True, "new_model_calls": 0, "dispatch_authorized": False,
        "source_history_seed_and_authority_provenance_verified": False,
        "limitations": "Parent verifies exact source/frame/history/seed/tokenizer evidence records, pre-label timing and authority, retains protected artifacts, registers admission, then uses Research.execute/shared gateway. Counts are exact local stdin proxies/reservations, not actual CLI usage or enforced remote generation caps. Reused/unavailable slots create no new invocation. Initial prefix is not a statistical look."}
    return PreparedInitial(_bytes(value), MappingProxyType(artifacts), digest(value))
