"""Registered offline comparison of retained Batch and Codex article outputs."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from newsresearch.common import AuditError, Config, require_no_credentials
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import WorkspaceLock, check_permissions

import lean_luna_state as state
import luna_event_contract_v2 as contract
from luna_batch_literal_projection import project_literal_refs

METHOD = "luna-codex-batch-quality-comparison-v1"
ROOT = Path(__file__).resolve().parents[1]


def assess_output(packet, output, *, completed, technical_failure, saved_status, saved_errors):
    """Use one content policy for both lanes; technical failures cannot pass."""
    packet_errors = contract.validate_packet(packet)
    if packet_errors:
        raise AuditError("comparison_packet_invalid")
    if technical_failure or not completed:
        status = saved_status if saved_status in {"unknown", "not_dispatched", "error"} else "error"
        return {"raw_status": status, "derived_status": status,
            "raw_errors": list(saved_errors), "derived_errors": list(saved_errors),
            "technical_failure": True, "projection": None, "status_matches_saved": status == saved_status}
    if output is None and "content:invalid_json" in saved_errors:
        return {"raw_status": "invalid", "derived_status": "invalid",
            "raw_errors": ["content:invalid_json"], "derived_errors": ["content:invalid_json"],
            "technical_failure": False, "projection": None, "status_matches_saved": saved_status == "invalid"}
    projection = project_literal_refs(output, packet, response_status="completed")
    raw_status = "invalid" if projection["raw_errors"] else "valid"
    return {"raw_status": raw_status, "derived_status": "valid" if projection["valid"] else "invalid",
        "raw_errors": projection["raw_errors"], "derived_errors": projection["derived_errors"],
        "technical_failure": False, "projection": projection, "status_matches_saved": raw_status == saved_status}


def summarize(rows):
    def rate(numerator, denominator):
        return round(100 * numerator / denominator, 4) if denominator else None
    total = len(rows)
    raw = Counter(r["raw_status"] for r in rows)
    derived = Counter(r["derived_status"] for r in rows)
    complete = sum(not r["technical_failure"] for r in rows)
    lengths = sorted(r["body_characters"] for r in rows)
    def percentile(q):
        return lengths[int((len(lengths) - 1) * q)] if lengths else None
    return {"attempted": total, "content_evaluable": complete, "technical_failures": total - complete,
        "saved_statuses": dict(Counter(r["saved_status"] for r in rows)),
        "raw_statuses": dict(raw), "derived_statuses": dict(derived),
        "raw_pass_percent_all_attempts": rate(raw["valid"], total),
        "raw_pass_percent_content_evaluable": rate(raw["valid"], complete),
        "derived_pass_percent_all_attempts": rate(derived["valid"], total),
        "derived_pass_percent_content_evaluable": rate(derived["valid"], complete),
        "recovered_by_projection": sum(r["raw_status"] != "valid" and r["derived_status"] == "valid" for r in rows),
        "projection_changed_outputs": sum(r["projection_changed"] for r in rows),
        "saved_status_mismatches": sum(not r["status_matches_saved"] for r in rows),
        "raw_error_counts": dict(Counter(e for r in rows for e in set(r["raw_errors"])).most_common()),
        "remaining_error_counts": dict(Counter(e for r in rows for e in set(r["derived_errors"])).most_common()),
        "raw_valid_focus": dict(Counter(r["focus"] for r in rows if r["raw_status"] == "valid")),
        "derived_valid_focus": dict(Counter(r["focus"] for r in rows if r["derived_status"] == "valid")),
        "languages": dict(Counter(r["language"] for r in rows)),
        "body_characters": {"min": min(lengths) if lengths else None, "p50": percentile(.5),
            "p95": percentile(.95), "max": max(lengths) if lengths else None},
        "unique_body_hashes": len({r["body_sha256"] for r in rows}),
        "human_validated": sum(r["human_validated"] is True for r in rows),
        "accepted": sum(r["accepted"] is True for r in rows),
        "human_validation_unavailable": sum(r["human_validated"] is None for r in rows)}


def compare_bodies(left, right):
    left_hashes = {r["body_sha256"] for r in left}
    right_hashes = {r["body_sha256"] for r in right}
    return {"shared_exact_body_hashes": len(left_hashes & right_hashes),
        "left_unique_bodies": len(left_hashes), "right_unique_bodies": len(right_hashes),
        "paired_accuracy_comparison": False}


def comparison_row(assessment, packet, output, check, *, lane, identity, packet_ref, response_ref):
    projection = check.pop("projection")
    body = packet["source_map"]["source_fields"]["body"]
    return {"lane": lane, "identity": identity, "assessment": assessment["_record_id"],
        "packet_ref": packet_ref, "response_ref": response_ref, "saved_status": assessment["status"],
        "human_validated": assessment.get("human_validated"), "accepted": assessment.get("accepted"),
        "body_sha256": body["sha256"], "body_characters": len(body["text"]),
        "language": packet["model_input"]["context"].get("language") or "unavailable",
        "focus": output.get("focus") if isinstance(output, dict) else None,
        "projection_changed": bool(projection and projection["changed"]),
        "transformations": projection["transformations"] if projection else [],
        "derived_output": projection["derived_output"] if projection and projection["changed"] else None,
        **check}


def render_report(summary):
    lines = ["# Codex Fast and API Batch output comparison", "",
        "Completed offline using retained immutable outputs. No new model calls or article retries.", "",
        "| Lane / corpus | Attempts | Raw mechanical passes | After identical reference cleanup | Technical failures |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for name, item in summary["lanes"].items():
        lines.append(f"| {name} | {item['attempted']:,} | {item['raw_statuses'].get('valid', 0):,} ({item['raw_pass_percent_all_attempts']:.2f}%) | "
            f"{item['derived_statuses'].get('valid', 0):,} ({item['derived_pass_percent_all_attempts']:.2f}%) | {item['technical_failures']} |")
    lines.extend(["", "The denominator includes all attempts, including technical failures. Content-only rates are in the structured report.",
        "Raw means parsed extraction content before literal-reference cleanup; previously recorded terminal-envelope parser repairs remain in use.",
        "Cleanup removes only an unmatched original reference when an unchanged literal occurs in another original reference. No new evidence, wording, roles or facts are introduced. Originals and statuses are unchanged.", "",
        f"Codex versus incident-report Batch shared exact article bodies: {summary['overlap']['incident-reports']['shared_exact_body_hashes']}.",
        "The sets are unpaired and differ in article mix and configuration. Codex used low reasoning plus execution notes; Batch used none and a 4,096-output-token cap. These rates cannot establish one transport's accuracy advantage.", "",
        "Confirmed: retained packet fidelity, request/response bindings and uniform schema/literal-reference validation for the inspected rows. This is selected-record verification, not a replay of the entire parent history.",
        "Not established: correct focus, event boundaries, entity identity, roles, factual entailment, completeness or truth. No new human or model semantic review was performed. Mechanical passes remain provisional.", ""])
    for name, item in summary["lanes"].items():
        lines.extend([f"## {name}", "",
            f"Saved status mismatches on revalidation: {item['saved_status_mismatches']}. Human-validated flags: {item['human_validated']}; accepted flags: {item['accepted']}.",
            f"Recovered by the separate deterministic projection: {item['recovered_by_projection']}. Remaining failures by code (codes can overlap):", ""])
        lines.extend(f"- {code}: {count}" for code, count in list(item["remaining_error_counts"].items())[:8])
        lines.extend(["", f"Body characters: {item['body_characters']}. Languages: {item['languages']}.", ""])
    lines.extend(["## Provenance", "", f"Protocol: `{summary['protocol']}`.",
        f"Batch checkpoint: `{summary['checkpoint']}`.", f"Codex result: `{summary['codex_result']}`.",
        f"Contract: `{summary['contract_digest']}`.", f"Protected per-row comparison: `{summary['details_artifact']}`.", ""])
    return "\n".join(lines)


def check_batch_chunk(bundle):
    """Validate immutable artifacts in a worker; SQL stays in the coordinator."""
    owner, pairs = bundle
    batch_artifacts = state.SelectedArtifacts(Path(owner))
    digest, prompt, schema = contract.contract_digest(), contract.load_prompt(), contract.load_schema()
    chunk_results = []
    for identity, compact, request, raw_assessment, task, plan_id in pairs:
        assessment = state.row_value(raw_assessment, "luna_budget_assessment")
        batch_artifacts.check(raw_assessment["artifact"])
        if assessment != compact or assessment["plan"] != plan_id:
            raise AuditError("comparison_batch_assessment_mismatch")
        descriptor = request["descriptor"]
        if (assessment["custom_id"] != identity or assessment["corpus_id"] != request["corpus_id"]
                or assessment["packet_ref"] != request["packet_ref"]
                or assessment["request"] != request["request_body_ref"]
                or descriptor["contract_sha256"] != digest):
            raise AuditError("comparison_batch_binding_mismatch")
        if (task["packet_ref"] != assessment["packet_ref"] or task["request_body_ref"] != assessment["request"]
                or task["corpus_id"] != assessment["corpus_id"]):
            raise AuditError("comparison_batch_manifest_binding_mismatch")
        packet = batch_artifacts.json(assessment["packet_ref"])
        body = batch_artifacts.json(assessment["request"])
        parsed = batch_artifacts.json(assessment["response"])
        bindings = {
            "body_hash": descriptor["retained_body_sha256"] == packet["source_map"]["source_fields"]["body"]["sha256"],
            # The retained parser omitted optional packet refs; the
            # immutable assessment and dispatch manifest bind them.
            "packet_ref": parsed.get("packet_ref") in {None, assessment["packet_ref"]},
            "custom_id": parsed["custom_id"] == identity,
            "status": parsed["status"] == assessment["status"],
            "wire_prompt": body["instructions"] == prompt,
            "packet_prompt": packet["model_input"]["instructions"] == prompt,
            "codebook": packet["model_input"]["codebook"] == contract.CODEBOOK,
            "schema": body["text"]["format"]["schema"] == schema,
            "input": json.loads(body["input"][0]["content"][0]["text"]) == {
                key: value for key, value in packet["model_input"].items() if key != "instructions"}}
        if not all(bindings.values()):
            raise AuditError("comparison_batch_binding:" + ",".join(key for key, valid in bindings.items() if not valid))
        output = parsed["result"] if parsed["status"] == "valid" else parsed.get("rejected_output")
        checked = assess_output(packet, output, completed=parsed.get("provider_status") == "completed",
            technical_failure=parsed["technical_failure"], saved_status=assessment["status"], saved_errors=assessment["errors"])
        name = "batch-" + assessment["corpus_id"]
        row = comparison_row(assessment, packet, output, checked,
            lane=name, identity=identity, packet_ref=assessment["packet_ref"], response_ref=assessment["response"])
        chunk_results.append((row,
            state.canonical({key: body.get(key) for key in ("model", "reasoning", "max_output_tokens")}),
            assessment.get("parser_mode", "unavailable"),
            bool((assessment.get("phase_projection") or {}).get("changed")), parsed.get("packet_ref") is None))
    return chunk_results, batch_artifacts.checked


class ComparisonResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD,
            "amend_latest": True, "reason": "Bind the exact comparison implementation before inspection",
            "content": {"method": METHOD, "retrospective": True, "phase": data["phase"],
                "scope": "Latest specified Codex Fast result versus retained API Batch results, incident-report corpus separately from cybercrime. Inspect compact checkpoint-bound state and selected immutable records/artifacts. No complete parent-history replay.",
                "checks": "Report raw mechanical passes before any transformation. Revalidate full-text packets and outputs with the same v2 schema/literal validator; apply the same separate original-ref-subset projection to both lanes. Compare body hashes for overlap; do not infer transport accuracy from unpaired articles. Preserve originals and holds.",
                "offline_validation_workers": 8,
                "limits": "Zero model/network calls, no source collection, no article retries or status changes. Semantic accuracy and independent human review are not established by these checks.",
                "implementation": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
                    Path(__file__), ROOT / "scripts/lean_luna_state.py", ROOT / "scripts/luna_batch_literal_projection.py",
                    ROOT / "src/newsresearch/luna_speed_provider.py")},
                "contract_digest": contract.contract_digest(), "codex_result": data["codex_result"]}})["id"]
        with ExitStack() as stack:
            database = Path(data["batch_state"]).resolve(strict=True)
            check_permissions(database.parent, root=True)
            check_permissions(database)
            self.ledger.append(session, "lane.comparison.inspection.intended", {
                "batch_state": str(database), "codex_owner": data["codex_owner"], "codex_result": data["codex_result"],
                "sql": ["SELECT key,value FROM meta", "SELECT * FROM requests", "SELECT * FROM results",
                        "SELECT * FROM records WHERE id=?", "SELECT * FROM records WHERE kind='lean_luna_checkpoint' AND logical_key=? ORDER BY created_event DESC LIMIT 1"],
                "protocol": protocol, "write_to_parent_stores": False})
            stack.enter_context(state.StateLock(database))
            db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=0)
            stack.callback(db.close)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT key,value FROM meta")}
            readers = {}
            def reader(owner):
                owner = Path(owner).resolve(strict=True)
                if owner not in readers:
                    check_permissions(owner, root=True)
                    lock = WorkspaceLock(owner / "workspace.lock")
                    stack.callback(lock.close)
                    conn = state.read_only_database(owner)
                    stack.callback(conn.close)
                    readers[owner] = (conn, state.SelectedArtifacts(owner))
                return readers[owner]
            checkpoint_db, checkpoint_artifacts = reader(database.parent / "runtime")
            checkpoint_row = checkpoint_db.execute("SELECT * FROM records WHERE kind='lean_luna_checkpoint' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (meta["snapshot_id"],)).fetchone()
            checkpoint = state.row_value(checkpoint_row, "lean_luna_checkpoint")
            checkpoint_artifacts.check(checkpoint_row["artifact"])
            if hashlib.sha256(db.serialize()).hexdigest() != checkpoint["state_sha256"]:
                raise AuditError("comparison_compact_state_not_at_checkpoint")
            batch_db, batch_artifacts = reader(meta["source_owner"])
            codex_db, codex_artifacts = reader(data["codex_owner"])
            def record(conn, artifacts, identifier, kind):
                row = conn.execute("SELECT * FROM records WHERE id=?", (identifier,)).fetchone()
                value = state.row_value(row, kind)
                artifacts.check(row["artifact"])
                return value
            codex = record(codex_db, codex_artifacts, data["codex_result"], "luna_fast_result")
            codex_plan = record(codex_db, codex_artifacts, codex["plan"], "luna_fast_plan")
            request_rows = list(db.execute("SELECT * FROM requests"))
            result_rows = list(db.execute("SELECT * FROM results"))
            requests = {r["custom_id"]: {**json.loads(r["payload"]), "_status": r["status"],
                         "_submitted": bool(r["submitted"])} for r in request_rows}
            results = {r["custom_id"]: json.loads(r["payload"]) for r in result_rows}
            summary = {"protocol": protocol, "checkpoint": checkpoint["_record_id"],
                "batch_owner": meta["source_owner"], "batch_plan": meta["plan_id"],
                "codex_result": data["codex_result"], "codex_plan": codex["plan"],
                "batch_totals": {corpus: {"submitted": sum(r["_submitted"] for r in requests.values() if r["corpus_id"] == corpus),
                    "saved_statuses": dict(Counter(r["status"] for r in results.values() if r["corpus_id"] == corpus))}
                    for corpus in sorted({r["corpus_id"] for r in requests.values()})},
                "codex_counts": codex["counts"], "contract_digest": contract.contract_digest(),
                "model_calls": 0, "network_calls": 0, "original_status_changes": 0,
                "parent_full_history_replayed": False, "semantic_accuracy_confirmed": False}
            if data["phase"] == "inventory":
                example = next(r for r in results.values() if r["corpus_id"] == "incident-reports")
                request = requests[example["custom_id"]]
                parsed = batch_artifacts.json(example["response"])
                body = batch_artifacts.json(example["request"])
                summary["shapes"] = {"assessment_keys": sorted(example), "request_keys": sorted(request),
                    "descriptor_keys": sorted(request.get("descriptor", {})), "parsed_response_keys": sorted(parsed),
                    "request_body_keys": sorted(body), "reasoning": body.get("reasoning"),
                    "model": body.get("model"), "output_cap": body.get("max_output_tokens"),
                    "codex_config": codex_plan["config"], "compact_results_record_ids": all("_record_id" in r for r in results.values())}
            else:
                from newsresearch.gateway import ProviderResponse
                from newsresearch.luna_speed_provider import validate_response
                lanes: dict[str, list[dict[str, Any]]] = {"codex-incident-reports": []}
                configs = Counter()
                parser_modes = Counter()
                phase_changes = 0
                missing_parsed_packet_refs = 0
                manifests = {}
                expected = {key for key, request in requests.items() if request["_submitted"]}
                if set(results) != expected:
                    raise AuditError("comparison_batch_result_coverage_mismatch")
                # Read each selected SQL projection once in this locked snapshot.
                # Workers receive those bytes and verify their immutable artifacts.
                for manifest_id in sorted({row["manifest"] for row in results.values()}):
                    manifest = record(batch_db, batch_artifacts, manifest_id, "luna_budget_dispatch_manifest")
                    if manifest["plan"] != meta["plan_id"]:
                        raise AuditError("comparison_batch_manifest_plan_mismatch")
                    manifests[manifest_id] = {task["custom_id"]: task for task in manifest["tasks"]}
                pairs = []
                for identity, compact in sorted(results.items()):
                    row = batch_db.execute("SELECT * FROM records WHERE id=?", (compact["_record_id"],)).fetchone()
                    if row is None:
                        raise AuditError("comparison_batch_assessment_missing")
                    pairs.append((identity, compact, requests[identity], dict(row),
                        manifests[compact["manifest"]][identity], meta["plan_id"]))
                checked_count = 0
                with ProcessPoolExecutor(max_workers=8) as pool:
                    futures = [pool.submit(check_batch_chunk, (meta["source_owner"], pairs[start:start + 250]))
                        for start in range(0, len(pairs), 250)]
                    try:
                        for future in as_completed(futures):
                            checked_rows, artifacts_checked = future.result()
                            batch_artifacts.checked.update(artifacts_checked)
                            for row, config, parser_mode, phase_change, missing_ref in checked_rows:
                                lanes.setdefault(row["lane"], []).append(row)
                                configs[config] += 1
                                parser_modes[parser_mode] += 1
                                phase_changes += phase_change
                                missing_parsed_packet_refs += missing_ref
                            checked_count += len(checked_rows)
                            print(json.dumps({"comparison_batch_checked": checked_count, "expected": len(results),
                                "offline_validation_workers": 8}), flush=True)
                    except BaseException:
                        for future in futures:
                            future.cancel()
                        raise
                tasks = {task["task_key"]: task for task in codex_plan["tasks"]}
                for saved in codex["outcomes"]:
                    assessment = record(codex_db, codex_artifacts, saved["assessment"], "luna_fast_assessment")
                    if any(assessment[key] != saved[key] for key in assessment if not key.startswith("_")):
                        raise AuditError("comparison_codex_assessment_mismatch")
                    task = tasks[assessment["task_key"]]
                    capsule = codex_artifacts.json(task["packet"])
                    packet = capsule["packet"]
                    request = codex_artifacts.json(assessment["request"])
                    response = codex_artifacts.json(assessment["response"])
                    if (request["packet"] != packet or request["contract_digest"] != contract.contract_digest()
                            or request["schema"] != contract.load_schema() or response["raw_response"]["packet"] != packet
                            or capsule["body_sha256"] != packet["source_map"]["source_fields"]["body"]["sha256"]
                            or capsule["source_version"] != assessment["source_version"] or assessment["plan"] != codex["plan"]):
                        raise AuditError("comparison_codex_binding_mismatch")
                    errors = validate_response(ProviderResponse(**response), packet)
                    technical = any(error.startswith("response:") for error in errors)
                    checked = assess_output(packet, response["payload"], completed=not technical,
                        technical_failure=technical, saved_status=assessment["status"], saved_errors=assessment["errors"])
                    lanes["codex-incident-reports"].append(comparison_row(assessment, packet, response["payload"], checked,
                        lane="codex-incident-reports", identity=assessment["attempt"], packet_ref=task["packet"], response_ref=assessment["response"]))
                for rows in lanes.values():
                    rows.sort(key=lambda row: row["identity"])
                details = {"protocol": protocol, "originals_unchanged": True, "rows": lanes}
                require_no_credentials(details)
                summary.update(lanes={name: summarize(rows) for name, rows in lanes.items()},
                    overlap={corpus: compare_bodies(lanes["codex-incident-reports"], lanes["batch-" + corpus])
                        for corpus in ("incident-reports", "cybercrime")},
                    batch_configurations=[{"config": json.loads(key), "count": count} for key, count in configs.items()],
                    offline_validation_workers=8, codex_configuration=codex_plan["config"], batch_parser_modes=dict(parser_modes),
                    batch_terminal_envelope_projections=phase_changes,
                    batch_parsed_packet_refs_missing=missing_parsed_packet_refs,
                    batch_packet_binding_basis="checkpoint plus immutable assessment and dispatch manifest; present parsed refs also checked",
                    details_artifact=self.ledger.artifacts.put(details))
                report = render_report(summary)
                summary["report_artifact"] = self.ledger.artifacts.put_bytes(report.encode("utf-8"))
                summary["report_path"] = str(self.ledger.root / "objects" / summary["report_artifact"])
            summary["verified_artifact_counts"] = {str(owner): len(artifacts.checked) for owner, (_, artifacts) in readers.items()}
            require_no_credentials(summary)
            identifier = self.ledger.record(session, "luna_lane_comparison", data["phase"], summary)
            return {"id": identifier, **summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inventory", "compare"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--batch-state", type=Path, required=True)
    parser.add_argument("--codex-owner", type=Path, required=True)
    parser.add_argument("--codex-result", required=True)
    args = parser.parse_args()
    engine = ComparisonResearch(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"phase": args.phase, "batch_state": str(args.batch_state),
            "codex_owner": str(args.codex_owner), "codex_result": args.codex_result},
            objective="Compare retained Codex and API Batch extraction outputs using uniform mechanical quality checks",
            actor="codex:luna-lane-comparison")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
