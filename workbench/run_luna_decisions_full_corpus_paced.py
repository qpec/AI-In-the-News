"""Registered pacing extension; preserves the frozen full-corpus preparation."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time

from newsresearch.common import AuditError, Config, canonical
from newsresearch.runtime import audited_handler
import run_luna_decisions_full_corpus as base
from prepare_luna_multibatch import offline_tokenizer

METHOD = "luna-decisions-full-corpus-pacing-20261021-v1"
TOKENS_PER_MINUTE = 1_600_000
REQUESTS_PER_MINUTE = 4000
ORIGINAL_TRANSPORT = base.DecisionsTransport


class Pacer:
    def __init__(self, ratio, *, clock=time.monotonic, sleep=time.sleep):
        self.encoding = offline_tokenizer()
        self.ratio, self.clock, self.sleep = ratio, clock, sleep
        self.lock = threading.Lock()
        self.next_slot = self.clock()

    def acquire(self, request):
        proxy = len(self.encoding.encode(canonical(request), disallowed_special=())) + 32
        estimate = max(1, proxy * self.ratio * 1.25)
        with self.lock:
            self.next_slot = max(self.next_slot, self.clock()) + max(
                60 / REQUESTS_PER_MINUTE, 60 * estimate / TOKENS_PER_MINUTE)
            delay = max(0, self.next_slot - self.clock())
        self.sleep(delay)
        return estimate


class PacedTransport:
    def __init__(self, pacer, profile, owner, deadline):
        self.pacer, self.profile, self.owner, self.deadline = pacer, profile, owner, deadline
        self.provider = ORIGINAL_TRANSPORT()

    def complete_prepared(self, invocation):
        estimate = self.pacer.acquire(invocation.request)
        if (self.owner / "STOP").exists() or datetime.now(timezone.utc) >= datetime.fromisoformat(self.deadline):
            raise AuditError("paced_stopped_before_http_dispatch")
        response = self.provider.complete_prepared(invocation)
        return replace(response, raw_response={**(response.raw_response or {}),
            "pacing_profile": self.profile, "pacing_input_tokens_estimate": estimate})


class Study(base.Study):
    @audited_handler
    def _status(self, session, context, data):
        if data["action"] != "run":
            return super()._status(session, context, data)
        plan = self.one("full_screen_plan")
        code = {**base.implementation(), str(Path(__file__).relative_to(base.pilot.ROOT)):
                hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        content = {"method": METHOD, "plan": plan["_record_id"], "implementation": code,
            "tokens_per_minute_estimate_cap": TOKENS_PER_MINUTE, "requests_per_minute_cap": REQUESTS_PER_MINUTE,
            "estimate": "Per-request cl100k serialized-request proxy plus 32, scaled by the frozen observed pilot ratio and 1.25 margin. This is pacing, not a billing guarantee.",
            "basis": "Earlier project operational limits 2M TPM/5000 RPM in workbench/LUNA_LEAN_API.md; use 80%. Not a fresh account-limit measurement.",
            "procedure": "A shared monotonic scheduler spaces calls before the unchanged one-attempt transport. Shared gateway, exact evidence, per-request reservation, no-retry identities, labels and original deadline remain unchanged. STOP and deadline are rechecked immediately before HTTP dispatch."}
        profiles = self.rows("full_screen_execution_profile")
        if profiles:
            if len(profiles) != 1 or profiles[0]["content"] != content:
                raise AuditError("paced_profile_changed")
            identifier = profiles[0]["_record_id"]
        else:
            version = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": content})
            identifier = self.ledger.record(session, "full_screen_execution_profile", METHOD,
                {"version": version["id"], "content": content})
        pacer = Pacer(plan["cost_estimate"]["observed_to_proxy_ratio"])

        def provider_factory():
            launch = self.rows("full_screen_launch")[0]
            return PacedTransport(pacer, identifier, self.ledger.root, launch["expires_at"])

        original = base.DecisionsTransport
        base.DecisionsTransport = provider_factory
        try:
            return super()._status(session, context, data)
        finally:
            base.DecisionsTransport = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=False))
    try:
        print(json.dumps(study.execute("status", {"action": "run", "allow_paid_execution": args.allow_paid_execution},
            objective="Run the full eligible-corpus two-question Decisions screen with audited request pacing",
            actor="codex:luna-decisions-full-corpus"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
