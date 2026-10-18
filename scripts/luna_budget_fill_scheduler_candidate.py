"""Candidate fill-first scheduling policy; not imported by the live controller.

Deployment changes only the controller's scheduling decision and its two
successful-operation notifications. The existing current-state gate, exact
whole-file admission, deadline boundary, policy loader and transport stay intact.
"""
from __future__ import annotations

from dataclasses import dataclass


MAX_SUBMISSIONS_BEFORE_POLL = 8
SUPPORTED_COUNT_WORKERS = 16


@dataclass
class FillFirstScheduler:
    """Fill available capacity, with a finite bound on deferred observations.

    Counters advance only after successful provider batch creation. A deferred
    or failed create never counts as submission. The caller still stops on
    current errors and its original deadline before invoking this decision.
    """
    submissions_since_poll: int = 0

    def choose(self, *, pending: bool, staged: bool, unmanifested: bool,
               startup: bool, pressure: str | None, poll_due: bool) -> str:
        if startup:
            return "reconcile" if pending and poll_due else "wait"
        if pressure:
            return "reconcile" if pending and poll_due else "wait"
        # A known available file gets priority over an ordinarily due poll.
        # Even an indefinitely long tiny-file queue cannot starve observations.
        if pending and poll_due and self.submissions_since_poll >= MAX_SUBMISSIONS_BEFORE_POLL:
            return "reconcile"
        if staged:
            return "submit"
        if unmanifested:
            return "stage"
        return "reconcile" if pending and poll_due else "wait"

    def submitted(self) -> None:
        self.submissions_since_poll += 1

    def reconciled(self) -> None:
        self.submissions_since_poll = 0
