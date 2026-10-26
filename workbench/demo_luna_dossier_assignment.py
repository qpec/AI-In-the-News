"""Synthetic full-article assignment demonstration; no corpus, API or research I/O."""
from __future__ import annotations

import json

from newsresearch import luna_dossier_assignment as method


def main():
    representative = method.Article("example-1", "synthetic-v1", "Example laboratory opens",
        "Example Observatory opened its laboratory on Monday. This is invented test material.", "clear")
    incoming = method.Article("example-2", "synthetic-v2", "New laboratory at Example Observatory",
        "On Monday Example Observatory opened a new laboratory. This is invented test material.", "clear")
    dossier = method.DossierSnapshot("example-dossier", ((representative.article_id, representative.version),),
                                     representative)
    packet = method.assignment_request(incoming, [dossier])
    # Handwritten fixture, not a returned Luna judgment or a reference annotation.
    choices = packet["request"]["questions"][0]["choices"]
    fixture = {"model": method.MODEL, "answers": [{"name": packet["phase"], "type": "choice",
        "choice": "D1", "confidence": .99, "probabilities": [
            {"value": c["value"], "probability": .99 if c["value"] == "D1" else .01 / (len(choices) - 1)}
            for c in choices]}]}
    proposal = method.membership_proposal(packet, fixture, {dossier.dossier_id: dossier}, threshold=.95)
    print(json.dumps({"synthetic_only": True, "new_model_calls": 0, "proposal": proposal,
        "planning_scenarios": [method.workload_scenario(8603, count) for count in (1000, 3000, 6000)]}, indent=2))


if __name__ == "__main__":
    main()
