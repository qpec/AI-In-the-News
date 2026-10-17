"""Registered fine-grid branch; the historical coarse implementation is retained."""
from .event_coverage_candidate import CoverageCandidateResearch

METHOD = "coverage-guarded-event-split-v3"
DELTAS = (.05, .055, .06, .065, .07, .075)


class FineCoverageCandidateResearch(CoverageCandidateResearch):
    METHOD = METHOD
    DELTAS = DELTAS
    PHASE = "prepare_fine_coverage_grid"
    MANIFEST_KIND = "event_fine_coverage_candidate_manifest"
    EXTRA_IMPLEMENTATION = ("event_fine_coverage_candidate.py",)
    REFERENCE_DELTA = .05
