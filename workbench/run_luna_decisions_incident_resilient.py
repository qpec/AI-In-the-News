"""Registered local-checkpoint retry extension; never retries provider requests."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from newsresearch.common import AuditError, Config, utc
from newsresearch.runtime import audited_handler
import run_luna_decisions_incident_corpus as runner

METHOD = "luna-decisions-incident-checkpoint-resilience-20261021-v1"
REPLACE_ATTEMPTS = 101
REPLACE_DELAY_SECONDS = .2


class Study(runner.Study):
    def save(self, name, value):
        if name != "progress.json":
            return super().save(name, value)
        destination = self.ledger.root / name
        temporary = self.ledger.root / ("progress-" + uuid.uuid4().hex + ".writing")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        for number in range(REPLACE_ATTEMPTS):
            try:
                os.replace(temporary, destination)
                return
            except PermissionError:
                if number + 1 == REPLACE_ATTEMPTS:
                    raise
                time.sleep(REPLACE_DELAY_SECONDS)

    @audited_handler
    def _status(self, session, context, data):
        if data["action"] == "run":
            plan = self.one("full_screen_plan")
            content = {"method": METHOD, "plan": plan["_record_id"],
                "implementation": {**runner.implementation(), str(Path(__file__).relative_to(runner.pilot.ROOT)):
                                   hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
                "procedure": "Retry only atomic replacement of progress.json after Windows PermissionError, using one unique temporary file, at most 101 attempts separated by 0.2 seconds (20 seconds total). The scientific runner, requests, model, gateway, validators, budget, holds, corpus exclusion, no-provider-retry rule and original deadline remain unchanged. Completed wave results are durable before the replace. Any persistent local failure still stops visibly.",
                "reason": "Observed WinError 5 stopped the worker while replacing its progress cache after a completed wave.",
                "user_instruction": "Poll status every 30 minutes. And ensure it keeps going. Plus give x/x and eta",
                "provider_retries": 0}
            profiles = self.rows("incident_checkpoint_execution_profile")
            if profiles:
                if len(profiles) != 1 or profiles[0]["content"] != content:
                    raise AuditError("incident_checkpoint_profile_changed")
                profile = profiles[0]["_record_id"]
            else:
                version = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": content})
                profile = self.ledger.record(session, "incident_checkpoint_execution_profile", METHOD,
                    {"version": version["id"], "content": content})
            self.ledger.record(session, "incident_execution_start", str(uuid.uuid4()),
                {"profile": profile, "plan": plan["_record_id"], "at": utc(),
                 "next_launch_number": len(self.rows("full_screen_launch")) + 1,
                 "saved_response_baseline": len(self.rows("full_screen_decision"))})
        return super()._status(session, context, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=False))
    try:
        print(json.dumps(study.execute("status", {"action": "run", "allow_paid_execution": args.allow_paid_execution},
            objective="Resume untouched incident-report screening with bounded local checkpoint retries and preserved identities and spending",
            actor="codex:incident-decisions-resilience"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
