"""Offline validation-owner initialization and guarded final-source freeze only.

No CLI/paid/account execution, automatic source path, sampling or model transport.
The actual human-origin evidence is operator supplied and retained verbatim; this
records its asserted authority rather than authenticating a human transcript.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

import final_validation_contract as contract
import final_validation_packets as packets
import final_validation_schedule as schedule
import final_validation_source as source
from newsresearch.common import AuditError, Config, Context, digest, require_active, require_no_credentials, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-final-validation-offline-owner-v1"
INTENT = "cyber_final_validation_initialization_intent"
SEEDS = "cyber_final_validation_seed_commitment"
STUDY = "cyber_final_validation_study_registration"
FREEZE = "cyber_final_validation_freeze_binding"
ACCESS = "cyber_final_validation_source_access"
SNAPSHOT = "cyber_final_validation_source_snapshot"
ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "research/cybercrime_nl/FINAL_CODEX_VALIDATION.md"
SEED_GENERATOR = {"algorithm": "four-independent-secrets.token_hex(32)-draws", "entropy_bytes_per_draw": 32,
    "version": 1, "before_this_owner_source_access": True, "external_preexposure_verified": False}
POLICY = {"offline_only": True, "model_dispatch_authorized": False, "paid_fallback_authorized": False,
    "sampling_performed": False, "later_tranches_authorized": False, "account_quota": "unavailable"}
WRITER = re.compile(r"(?:run_dossiers(?:_v\d+)?|run_summary_fidelity_diagnostic(?:_v\d+)?)\.py")


def require(value, code):
    if not value:
        raise AuditError("final_validation_study_" + code)


def implementation():
    result = {key.replace("\\", "/"): value for key, value in source.implementation().items()}
    result.update(packets.implementation())
    for path in (Path(__file__), Path(schedule.__file__), ROOT / "docs/RESEARCH_PROTOCOL.md",
                 ROOT / "docs/AUDITABILITY.md", ROOT / "src/newsresearch/gateway.py"):
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def configuration(*, expected_documents, expected_articles, expected_aliases):
    result = {"expected_documents": expected_documents, "expected_articles": expected_articles,
        "expected_aliases": expected_aliases, "reference_route": "codex_cli_account",
        "configured_model": contract.MODEL, "reasoning_effort": contract.REASONING_EFFORT,
        "fast_mode": False, "definition_version": contract.DEFINITION_VERSION,
        "method_specification_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "initial_primary_limit": 40, "initial_total_task_limit": 60, **POLICY}
    validate_configuration(result)
    return result


def validate_configuration(value):
    require(isinstance(value, dict), "configuration_required")
    counts = {k: value.get(k) for k in ("expected_documents", "expected_articles", "expected_aliases")}
    require(all(type(v) is int and v >= 0 for v in counts.values())
        and counts["expected_documents"] > 0
        and counts["expected_documents"] + counts["expected_aliases"] == counts["expected_articles"], "frame_counts")
    source._sha(value.get("method_specification_sha256"))
    expected = {**counts, "method_specification_sha256": value["method_specification_sha256"],
        "reference_route": "codex_cli_account", "configured_model": contract.MODEL,
        "reasoning_effort": contract.REASONING_EFFORT, "fast_mode": False,
        "definition_version": contract.DEFINITION_VERSION, "initial_primary_limit": 40,
        "initial_total_task_limit": 60, **POLICY}
    require(value == expected, "configuration_policy_changed")


def instruction(value):
    require(isinstance(value, dict) and set(value) == {"instruction", "source_reference", "source_timestamp"}
        and all(isinstance(value[k], str) and value[k].strip() for k in ("instruction", "source_reference")), "instruction_evidence")
    if value["source_timestamp"] is not None:
        require(isinstance(value["source_timestamp"], str)
            and datetime.fromisoformat(value["source_timestamp"]).tzinfo is not None, "instruction_timestamp")
    require_no_credentials(value)


class WindowsProcessObserver:
    """Actual CIM enumeration; raw command lines are never persisted or returned.

    Missing commands/identities and inspection errors fail closed. The OS lock in
    Source supplies independent exclusion of ordinary ledger writers. Ambiguous
    default-owner pipeline commands conservatively block a freeze as well.
    """
    @staticmethod
    def _capture():
        require(os.name == "nt", "supported_process_observer_required")
        script = r"""$ErrorActionPreference = 'Stop'
$rows = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(?:w|3(?:\.\d+)?)?\.exe$' } | ForEach-Object {
  @{pid=[int]$_.ProcessId; parent_pid=[int]$_.ParentProcessId; name=$_.Name;
    created_at=$_.CreationDate.ToUniversalTime().ToString('o'); command_line=$_.CommandLine}
})
ConvertTo-Json -InputObject $rows -Compress -Depth 4
"""
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                text=True, timeout=30, check=True)
            return json.loads(result.stdout)
        except Exception:
            raise AuditError("final_validation_study_process_inspection_failed") from None

    def observe(self, engine, session, owner):
        require_active(engine, session)
        rows = self._capture()
        require(isinstance(rows, list), "process_inventory_shape")
        expected = str(owner).replace("\\", "/").casefold().rstrip("/")
        seen, matched, inventory, by_pid = set(), [], [], {}
        for row in rows:
            require(isinstance(row, dict) and set(row) == {"pid", "parent_pid", "name", "created_at", "command_line"},
                "process_inventory_fields")
            require(type(row["pid"]) is int and row["pid"] > 0 and row["pid"] not in seen
                and type(row["parent_pid"]) is int and row["parent_pid"] >= 0
                and isinstance(row["command_line"], str) and bool(row["command_line"].strip())
                and isinstance(row["name"], str) and row["name"].lower().startswith("python")
                and isinstance(row["created_at"], str) and datetime.fromisoformat(row["created_at"]).tzinfo is not None,
                "process_inspection_incomplete")
            seen.add(row["pid"])
            by_pid[row["pid"]] = row
            metadata = {k: row[k] for k in ("pid", "parent_pid", "name", "created_at")}
            metadata["command_sha256"] = hashlib.sha256(row["command_line"].encode()).hexdigest()
            inventory.append(metadata)
        require(os.getpid() in by_pid, "observer_missing_from_process_inventory")
        ignored = {os.getpid()}
        current = by_pid[os.getpid()]
        def arguments(row):
            return re.sub(r'^(?:"[^"]+"|\S+)\s*', "", row["command_line"], count=1).replace("\\", "/").casefold()
        while current["parent_pid"] in by_pid and current["parent_pid"] not in ignored:
            parent = by_pid[current["parent_pid"]]
            if (arguments(parent) != arguments(current) or WRITER.search(arguments(parent))
                or datetime.fromisoformat(parent["created_at"]) > datetime.fromisoformat(current["created_at"])):
                break
            ignored.add(parent["pid"])
            current = parent
        for row, metadata in zip(rows, inventory, strict=True):
            if row["pid"] in ignored:
                continue
            command = row["command_line"].replace("\\", "/").casefold()
            default_runner = WRITER.search(command)
            if expected in command or (default_runner and not re.search(r"--workspace(?:\s|=)", command)):
                matched.append(metadata)
        inventory_ref = engine.ledger.artifacts.put({"observer": METHOD, "observed_at": utc(),
            "processes": sorted(inventory, key=lambda r: r["pid"]), "verified_observer_process_ids": sorted(ignored),
            "raw_command_lines_retained": False})
        evidence = {"source_owner": str(owner), "observed_at": utc(), "inspection_complete": True,
            "active_writers": matched, "matching_processes": matched}
        evidence_ref = engine.ledger.artifacts.put(evidence)
        engine.ledger.record(session, "cyber_final_validation_process_observation", evidence_ref,
            {"evidence_artifact": evidence_ref, "inventory_artifact": inventory_ref,
             "python_processes_examined": len(rows), "matching_processes": len(matched)})
        return {**evidence, "evidence_sha256": evidence_ref}


class Study(Research):
    def __init__(self, workspace, *, source_owner, config=None):
        workspace, source_owner = Path(workspace), Path(source_owner)
        require(workspace.is_absolute() and source_owner.is_absolute(), "explicit_absolute_owners_required")
        require(not any(p.is_symlink() or p.is_junction() for path in (workspace, source_owner)
            for p in [path, *path.parents]), "owner_links_forbidden")
        workspace, source_owner = workspace.resolve(), source_owner.resolve()
        require(workspace != source_owner and workspace not in source_owner.parents
            and source_owner not in workspace.parents, "separate_owner_required")
        selected_config = config or Config(offline=True)
        require(selected_config.offline, "offline_required")
        self.source_owner = source_owner
        self.observer = WindowsProcessObserver()
        super().__init__(workspace, config=selected_config)

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        require(operation == "status" and not versions, "offline_entry_operations_only")
        payload = payload or {}
        action = payload.get("action")
        fields = {"initialize": {"action", "instruction_evidence", "configuration"},
            "freeze": {"action", "source_bindings"}, "status": {"action"}}
        require(action in fields and set(payload) == fields[action], "operation_shape")
        return super().execute("status", {"method": METHOD, **payload}, objective=objective, actor=actor)

    def _rows(self, kind):
        return [{"id": r["id"], "created_event": r["created_event"],
                 "payload": self.ledger.get(r["id"], kind)} for r in self.ledger.db.execute(
            "SELECT id,created_event FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def _one(self, kind, *, optional=False):
        rows = self._rows(kind)
        require(len(rows) == 1 or (optional and not rows), "single_immutable_" + kind)
        return rows[0] if rows else None

    def _version_once(self, session, context, kind, key, content):
        rows = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, key)))
        require(len(rows) <= 1, "version_replaced")
        if rows:
            old = self.ledger.get(rows[0]["id"], kind)
            require(old["content"] == content and old["reason"] is None and old["branch"] == "main", "version_binding_changed")
            return rows[0]["id"]
        return self._version(session, context, {"kind": kind, "key": key, "content": content})["id"]

    def _fresh_owner(self):
        require(not self.ledger.db.execute("SELECT 1 FROM records LIMIT 1").fetchone()
            and not self.ledger.db.execute("SELECT 1 FROM sources LIMIT 1").fetchone()
            and not self.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%' LIMIT 1").fetchone(),
            "owner_has_prior_research")
        for row in self.ledger.db.execute("SELECT payload FROM events WHERE kind='operation.intended'"):
            operation = json.loads(row["payload"])
            data = self.ledger.artifacts.read(operation["input"])
            require(operation["operation"] == "status" and data.get("method") == METHOD
                and data.get("action") in {"status", "initialize"}, "owner_has_prior_operations")

    def _registration(self):
        row = self._one(STUDY)
        value = row["payload"]
        require(value["method"] == METHOD and value["source_owner"] == str(self.source_owner)
            and value["implementation"] == implementation(), "registration_changed")
        intent, seeds = self._one(INTENT), self._one(SEEDS)
        require(value["initialization_intent"] == intent["id"] and value["seed_record"] == seeds["id"]
            and intent["created_event"] < seeds["created_event"] < row["created_event"], "seed_order_or_identity")
        require(value["configuration"] == intent["payload"]["configuration"]
            and value["instruction_evidence_artifact"] == intent["payload"]["instruction_evidence_artifact"]
            and seeds["payload"]["initialization_intent"] == intent["id"]
            and seeds["payload"]["generator"] == SEED_GENERATOR, "registration_provenance")
        validate_configuration(value["configuration"])
        instruction(self.ledger.artifacts.read(value["instruction_evidence_artifact"]))
        for kind, identifier in value["versions"].items():
            require(self.ledger.get(identifier, kind)["content"] == value["version_contents"][kind], "registered_versions_changed")
        require(hashlib.sha256(self.ledger.artifacts.read_bytes(value["specification_artifact"])).hexdigest()
            == value["configuration"]["method_specification_sha256"], "registered_specification_changed")
        self._verify_seeds(seeds["payload"])
        return row

    def _verify_seeds(self, value):
        sampling = self.ledger.artifacts.read(value["schedule_seed_artifact"])
        ordering = self.ledger.artifacts.read(value["article_order_seed_artifact"])
        require(sampling == schedule.seed_payload(sampling["seeds"])
            and ordering == packets.order_seed_payload(ordering["seed"]), "seed_artifact_binding")
        values = [*sampling["seeds"].values(), ordering["seed"]]
        require(len(set(values)) == 4 and all(re.fullmatch(r"[0-9a-f]{64}", s) for s in values), "seed_generator_format")

    def _summary(self, row):
        value = row["payload"]
        seeds = self.ledger.get(value["seed_record"], SEEDS)
        return {"study_record": row["id"], "study_artifact": digest(value), "method": METHOD,
            "versions": value["versions"], "seed_record": value["seed_record"],
            "schedule_seed_artifact": seeds["schedule_seed_artifact"],
            "article_order_seed_artifact": seeds["article_order_seed_artifact"],
            "instruction_evidence_artifact": value["instruction_evidence_artifact"],
            "specification_artifact": value["specification_artifact"],
            "configuration_sha256": digest(value["configuration"]), "implementation_sha256": digest(value["implementation"]),
            "source_frozen": bool(self._rows(SNAPSHOT)), "new_model_calls": 0, "sample_drawn": False,
            "dispatch_authorized": False, "human_origin_independently_verified": False}

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data.get("method") == METHOD, "offline_registered_entry_required")
        if data["action"] == "initialize":
            return self.initialize(session, context, data)
        if data["action"] == "status":
            return self._summary(self._registration()) if self._rows(STUDY) else {
                "method": METHOD, "initialized": False, "incomplete_initialization": bool(self._rows(INTENT)),
                "new_model_calls": 0, "dispatch_authorized": False}
        require(data["action"] == "freeze", "offline_entry_operations_only")
        return self.freeze(session, context, data["source_bindings"])

    @audited_handler
    def initialize(self, session, context, data):
        instruction(data["instruction_evidence"])
        validate_configuration(data["configuration"])
        code = implementation()
        intended = {"method": METHOD, "source_owner": str(self.source_owner), "implementation": code,
            "configuration": data["configuration"], "instruction_evidence_artifact": digest(data["instruction_evidence"]),
            "specification_artifact": data["configuration"]["method_specification_sha256"], "policy": POLICY}
        existing = self._one(INTENT, optional=True)
        if existing:
            require(existing["payload"] == intended, "initialization_changed_requires_amendment")
            require(self._rows(STUDY), "incomplete_initialization_requires_explicit_recovery")
            return self._summary(self._registration())
        self._fresh_owner()
        spec_bytes = SPEC.read_bytes()
        require(hashlib.sha256(spec_bytes).hexdigest() == intended["specification_artifact"], "declared_specification_changed")
        self.ledger.artifacts.put(data["instruction_evidence"])
        require(self.ledger.artifacts.put_bytes(spec_bytes) == intended["specification_artifact"], "retained_specification_changed")
        intent_id = self.ledger.record(session, INTENT, METHOD, intended)
        # One durable intent precedes randomness. If any following write fails,
        # repeat initialization fails closed instead of generating new seeds.
        values = [secrets.token_hex(32) for _ in range(4)]
        require(len(set(values)) == 4 and all(re.fullmatch(r"[0-9a-f]{64}", s) for s in values),
            "entropy_collision_requires_explicit_recovery")
        seed_value = {"method": METHOD, "initialization_intent": intent_id, "generator": SEED_GENERATOR,
            "schedule_seed_artifact": self.ledger.artifacts.put(schedule.seed_payload(dict(zip(
                ("primary", "qc", "diagnostic"), values[:3], strict=True)))),
            "article_order_seed_artifact": self.ledger.artifacts.put(packets.order_seed_payload(values[3]))}
        seed_id = self.ledger.record(session, SEEDS, METHOD, seed_value)
        contents = {"protocol": {"method": METHOD, "implementation": code, "initialization_intent": intent_id,
            "seed_record": seed_id, "configuration_sha256": digest(data["configuration"]),
            "specification_artifact": intended["specification_artifact"]},
            "policy": {**POLICY, "instruction_evidence_artifact": intended["instruction_evidence_artifact"],
                "initialization_intent": intent_id, "seed_record": seed_id},
            "selection": {"rules": "Freeze the explicitly declared complete final output before frame construction; preserve every exact input/alias/unknown.",
                "configuration_sha256": digest(data["configuration"]), "seed_record": seed_id}}
        versions = {kind: self._version_once(session, context, kind, METHOD, content) for kind, content in contents.items()}
        value = {**intended, "initialization_intent": intent_id, "seed_record": seed_id, "versions": versions,
            "version_contents": contents, "new_model_calls": 0, "source_access_performed": False}
        identifier = self.ledger.record(session, STUDY, METHOD, value)
        require(implementation() == code, "implementation_changed_during_initialization")
        return self._summary(self._one(STUDY)) | {"study_record": identifier}

    @audited_handler
    def freeze(self, session, context, bindings):
        registration = self._registration()
        value = registration["payload"]
        for kind, identifier in value["versions"].items():
            require(self.ledger.get(identifier, kind)["content"] == value["version_contents"][kind], "registered_versions_changed")
        source._bindings(bindings)
        require(Path(bindings["source_owner"]).resolve() == self.source_owner, "source_owner_changed")
        require(all(bindings[k] == value["configuration"][k]
            for k in ("expected_documents", "expected_articles", "expected_aliases")), "source_frame_changed")
        desired = {"method": METHOD, "study_record": registration["id"], "seed_record": value["seed_record"],
            "source_bindings": bindings, "source_bindings_sha256": digest(bindings),
            "source_implementation": source.implementation()}
        old = self._one(FREEZE, optional=True)
        if old:
            require(old["payload"] == desired, "source_cutoff_changed_requires_amendment")
        else:
            require(not self._rows(SNAPSHOT) and not self._rows(ACCESS), "source_access_before_freeze_binding")
            self.ledger.record(session, FREEZE, METHOD, desired)
        existing = self._one(SNAPSHOT, optional=True)
        if existing:
            require(existing["payload"]["source_bindings"] == bindings, "snapshot_binding_changed")
            return self._frozen_summary(existing, reused=True)
        require(type(self.observer) is WindowsProcessObserver, "concrete_process_observer_required")
        versions = {}
        for kind, content in {"protocol": {"method": source.METHOD, "implementation": source.implementation(),
            "source_bindings_sha256": digest(bindings), "study_record": registration["id"], "seed_record": value["seed_record"]},
            "selection": {"rules": "Exact completed final output, complete inputs/aliases and explicit final audit dispositions.",
                "source_bindings_sha256": digest(bindings), "study_record": registration["id"], "seed_record": value["seed_record"]}}.items():
            versions[kind] = self._version_once(session, context, kind, METHOD + ":freeze", content)
        access = {"study_record": registration["id"], "seed_record": value["seed_record"],
            "source_bindings_sha256": digest(bindings), "versions": versions}
        self.ledger.record(session, ACCESS, METHOD, access)
        require(self._one(SEEDS)["created_event"] < self._one(ACCESS)["created_event"], "source_access_before_seeds")
        result = source.freeze_final_snapshot(self, session, Context(context.objective, context.actor, versions), bindings,
            observe_liveness=lambda owner: self.observer.observe(self, session, owner))
        require(implementation() == value["implementation"], "implementation_changed_during_freeze")
        return self._frozen_summary(self._one(SNAPSHOT), reused=False) | {"snapshot_record": result["snapshot_record"]}

    def _frozen_summary(self, row, *, reused):
        snapshot = row["payload"]
        audit = snapshot["reported_final_audit_completion"]
        return {"method": METHOD, "study_record": self._one(STUDY)["id"],
            "snapshot_record": row["id"], "snapshot_artifact": digest(snapshot),
            **{k: snapshot[k] for k in ("input_index_digest", "unique_documents", "article_rows", "alias_rows",
                "accepted_group_count", "accepted_inputs", "singleton_prediction_inputs", "pipeline_processing_complete",
                "pipeline_finished", "export_verified", "new_model_calls", "source_mutations")},
            "final_audit_complete": audit["complete"], "final_audit_selected": audit["selected"],
            "final_audit_available": audit["available"], "final_audit_unavailable": audit["unavailable"],
            "final_audit_not_attempted": audit["not_attempted"], "reused_frozen_cutoff": reused,
            "current_source_quiescence_verified": not reused, "sample_drawn": False, "dispatch_authorized": False,
            "population_accuracy_measured": False,
            "pending": ["complete_attempt_and_history_inventories", "embedding_provenance", "frame_and_schedule",
                "slot_resource_admission", "registered_account_execution", "statistical_estimation"]}
