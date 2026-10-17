"""Offline literal-grounding diagnosis of a retained speed-test result."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from newsresearch.common import Config, Context, Json, ResearchError, digest
from newsresearch.event_extraction_workflow import _escape, _link, save
from newsresearch.runtime import Research, audited_handler

import luna_event_contract_v2 as contract


class DiagnosisResearch(Research):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        protocol = self._version(session, context, {"kind": "protocol", "key": "luna-speed-literal-diagnosis-v1",
            "content": {"method": "offline-exact-surface-diagnostic-v1", "result": data["result"],
                "procedure": "Replay current exact validator, compare participant surfaces to own cited units and complete supplied text. Preserve rejected status; no semantic inference, model or retry.",
                "implementation": digest(Path(__file__).read_text(encoding="utf-8"))}})["id"]
        result = self.ledger.get(data["result"], "luna_speed_result")
        plan = self.ledger.get(result["plan"], "luna_speed_plan")
        if plan["contract_digest"] != contract.contract_digest():
            raise ResearchError("diagnosis_requires_exact_contract")
        tasks = {row["source_version"]: row for row in plan["tasks"]}
        diagnosed = []
        for outcome in result["outcomes"]:
            if outcome["status"] != "invalid":
                continue
            task = tasks[outcome["source_version"]]
            self.ledger.append(session, "speed.diagnosis.inspection.intended", {
                "assessment": outcome["assessment"], "packet": task["packet"], "response": outcome["response"]})
            packet = self.ledger.artifacts.read(task["packet"])["packet"]
            response = self.ledger.artifacts.read(outcome["response"])
            output = response.get("payload")
            if not isinstance(output, dict):
                diagnosed.append({"source_version": task["source_version"], "title": task["title"],
                                  "url": task["url"], "transport_failure": response["raw_response"].get("failure"), "output": None})
                continue
            errors = contract.validate_output(output, packet)
            if errors != outcome["errors"]:
                raise ResearchError("diagnosis_validator_replay_changed")
            evidence = packet["model_input"]["evidence"]
            units = {row["id"]: row["text"] for row in [evidence["title"], *evidence["paragraphs"]]}
            failures = []
            for index, participant in enumerate((output.get("event") or {}).get("participants", [])):
                surface = participant["surface"]
                cited = [ref for ref in participant["refs"] if surface in units.get(ref, "")]
                if not cited:
                    failures.append({"index": index, "surface": surface, "refs": participant["refs"],
                        "exact_elsewhere_refs": [ref for ref, text in units.items() if surface in text],
                        "casefold_in_cited_refs": [ref for ref in participant["refs"] if surface.casefold() in units.get(ref, "").casefold()],
                        "cited_units": {ref: units.get(ref) for ref in participant["refs"]}})
            diagnosed.append({"source_version": task["source_version"], "title": task["title"], "url": task["url"],
                "errors": errors, "failed_participants": failures, "rejected_output": output, "status_unchanged": "invalid"})
        value = {"protocol": protocol, "original_result": data["result"], "plan": result["plan"],
                 "versions": plan["versions"], "diagnosed": diagnosed, "model_calls": 0, "retries": 0,
                 "statuses_changed": False, "semantic_review": False}
        identifier = self.ledger.record(session, "luna_speed_diagnosis", data["result"], value)
        lines = [f"Offline diagnosis completed: {len(diagnosed)} rejected response(s) inspected; zero model calls, retries or changed statuses.",
                 "Literal checks are mechanical; the following event/entity previews remain rejected and unvalidated."]
        for row in diagnosed:
            lines += ["", f"Article: {_link(row)}"]
            if "rejected_output" not in row:
                lines.append("No parsed output; transport failure: " + str(row["transport_failure"]))
                continue
            output = row["rejected_output"]
            lines.append("Replayed errors: " + json.dumps(row["errors"]))
            if output.get("event"):
                lines.append("Rejected event preview: " + _escape(output["event"]["summary"]))
                lines.append("Rejected participant previews: " + "; ".join(_escape(p["surface"]) for p in output["event"]["participants"]))
            for failure in row["failed_participants"]:
                lines.append(f"Failed literal: `{_escape(failure['surface'])}`; cited {failure['refs']}; "
                    f"exact elsewhere {failure['exact_elsewhere_refs']}; case-insensitive match in cited units {failure['casefold_in_cited_refs']}.")
                ref = failure["refs"][0]
                lines.append(f"Cited {ref} begins: “{_escape((failure['cited_units'][ref] or '')[:100])}”.")
        lines.append("No semantic correctness, recall or ten-minute parallel throughput was established. Original stop remains latched.")
        text = "\n".join(lines)
        reference = self.ledger.artifacts.put_bytes(text.encode("utf-8"))
        self.ledger.append(session, "presentation.artifact.saved", {"artifact": reference, "result": identifier,
            "status": "prepared_for_delivery", "record_presentation_supported": False})
        save(self, session, dict(Counter(error for row in diagnosed for error in row.get("errors", []))), "Diagnostic error counts")
        return {"id": identifier, "presentation": reference, "markdown": text}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = DiagnosisResearch(args.workspace, config=Config(offline=True))
    try:
        value = engine.execute("status", {"result": args.result},
            objective="Diagnose retained speed-test literal failures offline without retrying or accepting output",
            actor="codex:luna-speed-diagnosis")
        print(value["markdown"])
        print(json.dumps({k: value[k] for k in ("id", "presentation")}))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
