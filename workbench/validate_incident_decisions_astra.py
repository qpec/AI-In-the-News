"""Registered full-text Astra validation of stratified Luna incident decisions."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

from newsresearch import astra_incident_validation as method
from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lean_luna_state as state  # noqa: E402

METHOD = "incident-decisions-astra-stratified-validation-20261022-v1"
BASE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")
PARENT = BASE / "luna-decisions-incident-reports-20261021-v1"
PLAN = "36902c844c4f2156d87621aabb0caa91af98bd80d65a02f7de82fd317c617269"
REPORT = "0dc3615b046805dcb342d83e566a0dce9fc758e99cb0f7e25802c56a0e25cd9d"
EXE = Path("C:/Users/ynhan/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe")


class Source:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        check_permissions(self.root, root=True)
        self.db = state.read_only_database(self.root)
        self.artifacts = state.SelectedArtifacts(self.root)

    def one(self, kind):
        rows = list(self.db.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (kind,)))
        if len(rows) != 1:
            raise AuditError("astra_source_one_record_required")
        self.artifacts.check(rows[0]["artifact"])
        return state.row_value(rows[0], kind)

    def close(self):
        self.db.close()


def implementation():
    names = [Path(__file__), Path(method.__file__), ROOT / "src/newsresearch/codex_provider.py",
             ROOT / "src/newsresearch/runtime.py", ROOT / "src/newsresearch/gateway.py",
             ROOT / "src/newsresearch/storage.py", ROOT / "src/newsresearch/common.py",
             ROOT / "scripts/lean_luna_state.py", ROOT / "uv.lock"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in names}


class Study(Research):
    def rows(self, kind):
        return [{**self.ledger.get(r[0], kind), "_record_id": r[0]} for r in
                self.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def one(self, kind):
        rows = self.rows(kind)
        if len(rows) != 1:
            raise AuditError("astra_one_record_required_" + kind)
        return rows[0]

    def save(self, name, value):
        temporary = self.ledger.root / (uuid.uuid4().hex + ".writing")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.ledger.root / name)

    @audited_handler
    def _status(self, session, context, data):
        if data["action"] == "prepare":
            return self.prepare(session, context, data)
        plan = self.one("astra_validation_plan")
        if plan["implementation"] != implementation():
            raise AuditError("astra_frozen_implementation_changed")
        if data["action"] == "run":
            return self.run(session, plan, data)
        if data["action"] == "report":
            return self.report(session, plan, data["phase"])
        if data["action"] == "status":
            return self.progress(plan)
        raise AuditError("astra_unknown_action")

    def prepare(self, session, context, data):
        if self.rows("astra_validation_preparation"):
            raise AuditError("astra_preparation_already_registered")
        target = data.get("per_stratum", method.FINAL_PER_STRATUM)
        if not method.PILOT_PER_STRATUM <= target <= 1500:
            raise AuditError("astra_sample_cap")
        definitions = {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "procedure": "Freeze uniformly pseudorandom samples without replacement within saved keep/exclude strata. First 50 per stratum form the 100-article pilot, followed by a predetermined expansion to the frozen final size. Fresh Astra Codex contexts see full original retained title/body, original question definitions and opaque article IDs, but no Luna answers/probabilities/strata. Freeze references before comparison. Validate exact quotes and coverage. No data-dependent stopping, prompt tuning, replacement of missing/uncertain articles or retries. Report pilot and final separately, with TP/FP/TN/FN against clear Astra references and uncertainty explicitly retained.",
                "statistics": "Wilson 95% intervals for each stratum's positive-reference fraction. Target at most 0.05 absolute distance from estimate to either interval endpoint. Final size fixed before any judgments; pilot descriptive. Boundary-ambiguous references are unresolved even if a tentative route is given. Weight known and unresolved counts by original stratum population/sample size, never pool balanced-sample accuracy as corpus accuracy. Approximate simultaneous 95% recall bounds use Bonferroni 97.5% stratum Wilson bounds, including adversarial allocation of unresolved labels. No finite population correction; small sampling fractions. Article-level inference only, no inference to unique events or other corpora.",
                "limitations": "Astra is a blinded model reference, not human gold. Related-model errors, ambiguous original definitions and retained-text incompleteness limit truth claims. A larger sample reduces sampling error but does not validate the reference model. Review/unknown Luna rows are outside this binary evaluation frame. Selected-record/artifact verification is not full replay of the old owner."},
            "question": {"text": "How many true/false positives and negatives does the Luna screen have against blinded full-text Astra reference judgments, and how precise are stratified article-level estimates?"},
            "selection": {"rules": "Only incident-reports export rows with valid status and keep/exclude route. Rank each stratum by SHA256 canonical [seed,stratum,custom_id,request_hash]. First 50 per group are pilot; take a fixed prefix for expansion. Preserve all selected cases. The judge never receives selection strata.", "seed": method.SEED, "final_per_stratum": target},
            "profile": {"mode": "exploratory", "population_estimate": False, "article_frame_estimates_only": True},
            "prompt": {"instructions": method.RULES, "model": method.MODEL, "reasoning_effort": "medium", "batch_size_max": 5, "questions": "Exact questions verified identical across all selected frozen requests before dispatch; bound in plan."},
            "policy": {"approved_by": "user:current-chat", "instruction": "Do a structured validation on 100 random articles 50/50 from in and exclude and find true positives false positives true negatives false negatives. Use codex for this astra. After check if sample suffices and upscale to make significant. Also note the previous method step and this one and push to github",
                       "maximum_articles": 2 * target, "maximum_workers": 4, "max_retries": 0,
                       "allow_codex_account_execution": True, "new_paid_api_calls": 0,
                       "codex_account_dollar_cost": None, "prior_api_budget_and_holds_unchanged": True},
        }
        versions = {k: self._version(session, context, {"kind": k, "key": METHOD, "content": v})["id"] for k, v in definitions.items()}
        self.ledger.record(session, "astra_validation_preparation", METHOD, {"versions": versions, "at": utc()})
        source = Source(data.get("parent", PARENT))
        try:
            parent, report = source.one("full_screen_plan"), source.one("full_screen_report")
            if parent["_record_id"] != data.get("expected_plan", PLAN) or report["_record_id"] != data.get("expected_report", REPORT):
                raise AuditError("astra_parent_identity_mismatch")
            raw = source.artifacts.read(report["article_results_artifact"])
            frame = [json.loads(line) for line in raw.splitlines()]
            if len(frame) != report["selected_articles"] or any(r["corpus"] != "incident-reports" for r in frame):
                raise AuditError("astra_export_scope_mismatch")
            selected, sizes = method.select_sample(frame, target)
            chosen = {r["custom_id"]: r for r in selected}
            self.ledger.record(session, "astra_validation_selection", METHOD, {"versions": versions,
                "source_owner": str(source.root), "parent_plan": parent["_record_id"], "parent_report": report["_record_id"],
                "export_sha256": report["article_results_artifact"], "frame_sizes": sizes,
                "excluded_status_route_counts": dict(Counter(r["status"] + ":" + (r.get("decision") or {}).get("route", "") for r in frame if r["custom_id"] not in chosen)),
                "selected": selected})
            del raw, frame
            items, hidden, questions = [], [], None
            for chunk in parent["chunks"]:
                tasks = source.artifacts.json(chunk["artifact"])
                if len(tasks) != chunk["count"]:
                    raise AuditError("astra_source_chunk_count")
                for task in tasks:
                    row = chosen.pop(task["custom_id"], None)
                    if row is None:
                        continue
                    request = task["request"]
                    evidence = json.loads(request["input"])
                    if (task["corpus"] != "incident-reports" or request["model"] != "gpt-6-luna"
                            or digest(request) != row["request_hash"] or row["request_hash"] != task["request_hash"]
                            or set(evidence) != {"title", "body"}
                            or hashlib.sha256(evidence["body"].encode()).hexdigest() != task["descriptor"]["retained_body_sha256"]):
                        raise AuditError("astra_original_input_mismatch")
                    if questions is None:
                        questions = request["questions"]
                    if request["questions"] != questions:
                        raise AuditError("astra_original_questions_changed")
                    article_id = digest([method.SEED, "blinded", row["custom_id"]])[:20]
                    phase = "pilot" if row["within_stratum_rank"] <= method.PILOT_PER_STRATUM else "extension"
                    item = {"article_id": article_id, **evidence, "phase": phase}
                    items.append(item)
                    hidden.append({"article_id": article_id, "phase": phase, "custom_id": row["custom_id"],
                        "stratum": row["stratum"], "rank": row["within_stratum_rank"], "request_hash": row["request_hash"],
                        "luna": row["decision"], "source_locator": row["source_locator"], "decision_record": row["record_id"]})
            if chosen or len(items) != 2 * target:
                raise AuditError("astra_selected_input_missing")
            checked = sorted(source.artifacts.checked)
        finally:
            source.close()
        versions["codebook"] = self._version(session, context, {"kind": "codebook", "key": METHOD,
            "content": {"labels": sorted({v for choices in method.LABELS.values() for v in choices}),
                        "questions": questions, "boundary_ambiguous_policy": "Retain as unresolved in primary confusion matrix"}})["id"]
        batches = []
        for phase in ("pilot", "extension"):
            ordered = sorted((r for r in items if r["phase"] == phase), key=lambda r: digest([method.SEED, "order", r["article_id"]]))
            block, chars = [], 0
            for item in ordered:
                size = len(item["title"]) + len(item["body"])
                if block and (len(block) >= 5 or chars + size > 80000):
                    batches.append({"phase": phase, "items": self.ledger.artifacts.put(block), "count": len(block)})
                    block, chars = [], 0
                block.append({k: item[k] for k in ("article_id", "title", "body")})
                chars += size
            if block:
                batches.append({"phase": phase, "items": self.ledger.artifacts.put(block), "count": len(block)})
        plan = {"method": METHOD, "versions": versions, "implementation": implementation(), "frame_sizes": sizes,
                "per_stratum": target, "selected": len(items), "batches": batches,
                "hidden": self.ledger.artifacts.put(hidden), "questions": questions,
                "checked_source_artifacts": checked, "codex_executable": str(data.get("codex_executable", EXE)),
                "codex_binary_sha256": hashlib.sha256(Path(data.get("codex_executable", EXE)).read_bytes()).hexdigest(),
                "deadline": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
                "source_owner": str(source.root), "new_api_calls": 0}
        identifier = self.ledger.record(session, "astra_validation_plan", METHOD, plan)
        result = {"id": identifier, "selected": len(items), "pilot": method.PILOT_PER_STRATUM * 2,
                  "frame_sizes": sizes, "batches": len(batches), "model": method.MODEL, "new_api_calls": 0,
                  "max_body_characters": max(len(r["body"]) for r in items)}
        self.save("preparation-report.json", result)
        return result

    def progress(self, plan):
        rows = self.rows("astra_validation_response")
        return {"at": utc(), "saved_batches": len(rows), "planned_batches": len(plan["batches"]),
                "valid_references": sum(len(r["references"]) for r in rows),
                "failed_articles": sum(r["count"] for r in rows if not r["references"]),
                "unresolved_batches": len(self.ledger.unresolved), "selected": plan["selected"],
                "new_api_calls": 0, "codex_account_dollar_cost": None}

    def run(self, session, plan, data):
        if not data.get("allow_codex_execution") or self.config.offline:
            raise AuditError("astra_execution_not_authorized")
        phase = data["phase"]
        if phase not in {"pilot", "extension"}:
            raise AuditError("astra_dispatch_phase")
        if phase == "extension" and not any(r["phase"] == "pilot" for r in self.rows("astra_validation_report")):
            raise AuditError("astra_pilot_report_required")
        executable = Path(plan["codex_executable"])
        if hashlib.sha256(executable.read_bytes()).hexdigest() != plan["codex_binary_sha256"]:
            raise AuditError("astra_binary_changed")
        provider = method.AstraProvider(self.ledger.root / "workers", executable=str(executable), model=method.MODEL,
                                        timeout_seconds=600, max_input_bytes=1_000_000, max_output_bytes=4_000_000)
        attempts = {r["batch_index"] for r in self.rows("astra_validation_intended")}
        pending = [(i, b) for i, b in enumerate(plan["batches"]) if b["phase"] == phase and i not in attempts]
        max_batches = data.get("max_batches")
        if max_batches is not None:
            pending = pending[:max_batches]
        stop, started, failures = "phase_exhausted", time.perf_counter(), 0
        for offset in range(0, len(pending), 4):
            if (self.ledger.root / "STOP").exists():
                stop = "user_stop"
                break
            if datetime.now(timezone.utc) >= datetime.fromisoformat(plan["deadline"]):
                stop = "deadline"
                break
            wave = []
            for index, batch in pending[offset:offset + 4]:
                request = method.request_for(self.ledger.artifacts.read(batch["items"]), plan["questions"])
                invocation = provider.prepare(request)
                attempt = str(uuid.uuid4())
                intended = {"attempt": attempt, "task_key": digest([plan["_record_id"], index]), "number": 1,
                    "batch": plan["_record_id"], "batch_index": index, "count": batch["count"], "phase": phase,
                    "request": self.ledger.artifacts.put(request), "dispatch": self.ledger.artifacts.put(invocation.manifest()), "started_at": utc()}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                self.ledger.record(session, "astra_validation_intended", intended["task_key"], intended)
                wave.append((invocation, intended))
            failed_wave = False
            for position, response in self.gateway.codex_dispatch(session, provider, [(a, b["attempt"]) for a, b in wave], len(wave)):
                invocation, intended = wave[position]
                response_ref = self.ledger.artifacts.put(asdict(response))
                self.ledger.append(session, "astra_validation.response.received", {"attempt": intended["attempt"], "response": response_ref})
                references, error = [], None
                if response.payload is not None:
                    try:
                        references = method.validate_references(invocation.request, response.payload)
                    except (ResearchError, ValueError, TypeError, KeyError) as exc:
                        error = str(exc) if isinstance(exc, ResearchError) else type(exc).__name__
                raw = response.raw_response or {}
                unknown = bool(raw.get("unknown_outcome")) or response.payload is None
                value = {**intended, "response": response_ref, "references": references, "validation_error": error,
                         "unknown_outcome": unknown, "failure": raw.get("failure"), "usage": response.usage,
                         "model_observed": response.model, "configured_model": method.MODEL, "finished_at": utc()}
                identifier = self.ledger.record(session, "astra_validation_response", intended["task_key"], value)
                if not unknown:
                    self.ledger.append(session, "model.attempt.completed", {"attempt": intended["attempt"],
                        "request": intended["request"], "response": response_ref, "record": identifier,
                        "outcome": "valid" if references else "invalid", "completed_at": utc()})
                    self.ledger.unresolved.pop(intended["attempt"], None)
                failed_wave |= not bool(references)
            progress = {**self.progress(plan), "phase": phase, "execution_elapsed_seconds": time.perf_counter() - started}
            self.save("progress.json", progress)
            print(json.dumps(progress), flush=True)
            failures = failures + 1 if failed_wave else 0
            if failures >= 2:
                stop = "two_consecutive_failed_waves"
                break
        result = {**self.progress(plan), "phase": phase, "stop_reason": stop}
        self.ledger.record(session, "astra_validation_run_end", digest(result), result)
        return result

    def report(self, session, plan, phase):
        if phase not in {"pilot", "all"}:
            raise AuditError("astra_report_phase")
        hidden = self.ledger.artifacts.read(plan["hidden"])
        if phase == "pilot":
            hidden = [r for r in hidden if r["phase"] == "pilot"]
        intended = {r["batch_index"] for r in self.rows("astra_validation_intended")}
        needed = {i for i, b in enumerate(plan["batches"]) if phase == "all" or b["phase"] == "pilot"}
        if not needed <= intended:
            raise AuditError("astra_report_requires_all_selected_attempts")
        responses = self.rows("astra_validation_response")
        references = {r["article_id"]: r for block in responses for r in block["references"]}
        freeze = self.ledger.record(session, "astra_validation_references_frozen", digest([phase, references]),
            {"phase": phase, "plan": plan["_record_id"], "references": references, "at": utc()})
        cases = [{**r, "reference": references.get(r["article_id"])} for r in hidden]
        summary = method.metrics(cases, plan["frame_sizes"])
        payload = {"phase": phase, "plan": plan["_record_id"], "references_frozen": freeze,
                   "metrics": summary, "cases": self.ledger.artifacts.put(cases),
                   "at": utc(), "new_api_calls": 0, "codex_account_dollar_cost": None,
                   "source_text_published": False, "human_validated": False}
        identifier = self.ledger.record(session, "astra_validation_report", digest(payload), payload)
        result = {"id": identifier, **payload}
        self.save(phase + "-report.json", result)
        self.save(phase + "-cases.json", cases)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "report", "status"])
    parser.add_argument("--workspace", type=Path, default=BASE / METHOD)
    parser.add_argument("--phase", choices=["pilot", "extension", "all"], default="pilot")
    parser.add_argument("--per-stratum", type=int, default=method.FINAL_PER_STRATUM)
    parser.add_argument("--allow-codex-execution", action="store_true")
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {k: v for k, v in vars(args).items() if k != "workspace"}
        print(json.dumps(study.execute("status", data, objective="Validate the completed incident-only Luna screen against blinded Astra full-text references", actor="codex:astra-validation")))
    finally:
        study.close()


if __name__ == "__main__":
    main()
