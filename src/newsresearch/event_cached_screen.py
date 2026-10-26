"""Retrospective, descriptive screening against retained model pair references."""
from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit

from .common import Context, Json, ResearchError, digest, require_active
from .event_eval_overview import LABELS, _counts, _escape, _example
from .event_eval_workflow import METHOD as PAIR_METHOD
from .runtime import Research, audited_handler

METHOD = "provider-candidate-cached-model-reference-screen-v1"
RESULTS = (
    "534e49b0895111db1b55d2fb53a825b8e2e9309f4a9a88bd2c0dbe095c82f6aa",
    "fe5404e07d882fa1e4851d27154ea553239ec2890e8ff415dd535f4588f52d9f",
    "4ec5b1ada0424f40ee77f17339e6de7c99b26375c426959018737fc2e64fdbe3",
)


def subset(membership: Json, studies: list[Json]) -> Json:
    """Keep each study separate and preserve repeated/conflicting references."""
    rows, references = [], defaultdict(list)
    for study in studies:
        within = [task for task in study["tasks"] if task["phase"] == "evaluation" and task["stratum"] == "within_group"]
        kept: list[Json] = []
        removed: list[Json] = []
        for task in within:
            if task["left"] not in membership or task["right"] not in membership:
                raise ResearchError("cached_screen_source_outside_candidate")
            survives = membership[task["left"]] == membership[task["right"]]
            (kept if survives else removed).append(task)
            outcome = study["outcomes"].get(task["pair_id"])
            label = "pending" if outcome is None else outcome["label"] if outcome["status"] == "valid" else outcome["status"]
            references[task["pair_id"]].append({"result": study["id"], "label": label,
                "assessment": outcome.get("assessment") if outcome else None, "survives": survives})
        rows.append({"result": study["id"], "study_key": study["study_key"], "versions": study.get("versions"), "within_total": len(within),
            "surviving": _counts(kept, study["outcomes"]), "removed": _counts(removed, study["outcomes"])})
    overlap = {pair: refs for pair, refs in references.items() if len(refs) > 1}
    return {"studies": rows, "overlap_references": overlap, "overlap_pairs": len(overlap),
        "conflicting_decisive_pairs": sum({"same_event", "different_event"} <= {ref["label"] for ref in refs} for refs in overlap.values()),
        "disagreeing_reference_pairs": sum(len({ref["label"] for ref in refs}) > 1 for refs in overlap.values())}


def render(value: Json) -> str:
    lines = ["**Retrospective cached-model screen; candidate precision remains unmeasured.**", "",
        "| Previous study | Candidate subset | Total | Same | Different | Uncertain | Unusable/pending |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in value["studies"]:
        for key in ("surviving", "removed"):
            counts = row[key]
            unusable = sum(counts[label] for label in LABELS[3:])
            lines.append(f"| {_escape(row['study_key'])} | {key} | {counts['total']} | {counts['same_event']} | {counts['different_event']} | {counts['uncertain']} | {unusable} |")
    lines.extend(["", f"Repeated pairs across studies: {value['overlap_pairs']}; conflicting decisive labels: {value['conflicting_decisive_pairs']}; any differing labels/statuses: {value['disagreeing_reference_pairs']}.",
        "Each study is reported separately. Overlapping references are retained, never overwritten or pooled into an accuracy estimate. Uncertain, failed and absent responses are unresolved, never negative findings.",
        "This is post hoc reuse of model lead judgments, not fresh held-out evaluation, representative candidate precision, human gold, whole-group purity or a demonstrated 90% target. Unjudged candidate pairs remain unjudged. Zero new model calls, policies or membership changes.",
        "The frozen candidate creation record declares zero evaluation-label access/use. This screen registered its method and verified that record before reading old references; activity outside the runtime is unobserved."])
    for example in value["examples"]:
        links = []
        for article in example["articles"]:
            url = article["url"]
            title = _escape(article["title"] or article["source_version"])
            links.append(f"[{title}](<{url}>)" if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"}
                and not any(char in url for char in "<>\n\r") else title)
        lines.extend(["", f"- Surviving retained model `{example['label']}`: {'; '.join(links)}. Model reason: {_escape(example['reason'])}"])
        lines.extend(f"  - {span['span_id']} exact cited prefix: “{_escape(span['exact_prefix'])}”{' (clipped)' if span['clipped'] else ''}" for span in example["support"])
    if not value["examples"]:
        lines.extend(["", "No surviving different-event/uncertain model example is available."])
    return "\n".join(lines)


class CachedReferenceScreenResearch(Research):
    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        require_active(self, session)
        if set(data) != {"candidate_result"} or not self.config.offline:
            raise ResearchError("cached_screen_exact_offline_fields_required")
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD,
            "content": {"method": METHOD, "candidate_result": data["candidate_result"], "previous_results": list(RESULTS),
                "procedure": "Retrospective per-study surviving/removed within-pair counts; retain overlap/conflicts; at most two surviving different/uncertain examples",
                "new_models": 0, "new_thresholds": 0, "accuracy_estimate": False, "memberships_changed": False},
            "amend_latest": True, "reason": "Register post hoc screen before candidate, prior-result or evidence reads"})["id"]
        candidate = self.ledger.get(data["candidate_result"], "event_group_refinement_result")
        if (candidate.get("method") != "provider-anchored-event-split-v1" or candidate.get("evaluation_labels_accessed") != 0
                or candidate.get("reference_labels_used_for_selection") != 0 or candidate.get("adopted") is not False
                or candidate.get("unchanged_original_memberships") is not True):
            raise ResearchError("cached_screen_label_blind_frozen_candidate_required")
        if context.versions and context.versions != candidate["versions"]:
            raise ResearchError("cached_screen_context_differs")
        manifest = self.ledger.get(candidate["manifest"], "event_provider_candidate_manifest")
        if (manifest["versions"] != candidate["versions"] or manifest["method"].get("method") != candidate["method"]
                or manifest["method"].get("evaluation_labels_accessed") != 0
                or manifest["method"].get("reference_labels_used_for_selection") != 0):
            raise ResearchError("cached_screen_creation_manifest_invalid")
        membership = self.ledger.artifacts.read(candidate["candidate_membership"])
        if (not isinstance(membership, dict) or len(membership) != candidate["all_source_count"]
                or any(not isinstance(key, str) or not isinstance(val, str) or not val for key, val in membership.items())):
            raise ResearchError("cached_screen_candidate_frame_invalid")
        self.ledger.append(session, "cached.screen.frozen_candidate.verified", {"candidate": data["candidate_result"],
            "membership": candidate["candidate_membership"], "manifest": candidate["manifest"],
            "creation_declared_evaluation_labels_accessed": 0, "prior_reference_reads_in_this_handler": 0})
        studies: list[Json] = []
        examples: list[Json] = []
        for identifier in RESULTS:
            result = self.ledger.get(identifier, "luna_group_validation_result")
            plan = self.ledger.get(result["plan"], "luna_group_validation_plan")
            if (result.get("method") != PAIR_METHOD or plan.get("method") != PAIR_METHOD
                    or result.get("status") != "complete" or result.get("metrics", {}).get("reference_kind") != "model"
                    or result["versions"] != plan["versions"] or result["study_key"] != plan["study_key"]
                    or result["versions"]["dataset"] != candidate["versions"]["dataset"]
                    or set(membership) != {source for members in plan["design"]["groups"].values() for source in members}
                    or len(membership) != sum(len(members) for members in plan["design"]["groups"].values())):
                raise ResearchError("cached_screen_study_or_source_frame_invalid")
            tasks = {task["pair_id"]: task for task in plan["tasks"]}
            if len(tasks) != len(plan["tasks"]) or set(result["outcomes"]) - set(tasks):
                raise ResearchError("cached_screen_outcome_frame_invalid")
            for pair, outcome in result["outcomes"].items():
                if "assessment" not in outcome:
                    if outcome.get("status") not in {"unknown", "unavailable"}:
                        raise ResearchError("cached_screen_assessment_required")
                    continue
                retained = self.ledger.get(outcome["assessment"], "event_pair_eval_assessment")
                task = tasks[pair]
                if (retained != {key: val for key, val in outcome.items() if key != "assessment"}
                        or retained["pair_id"] != pair or retained["request"] != task["request"] or retained["phase"] != task["phase"]):
                    raise ResearchError("cached_screen_assessment_binding_invalid")
            studies.append({"id": identifier, "study_key": plan["study_key"], "versions": plan["versions"],
                "tasks": plan["tasks"], "outcomes": result["outcomes"]})
            for task in plan["tasks"]:
                outcome = result["outcomes"].get(task["pair_id"], {})
                if (len(examples) < 2 and task["phase"] == "evaluation" and task["stratum"] == "within_group"
                        and membership[task["left"]] == membership[task["right"]] and outcome.get("status") == "valid"
                        and outcome.get("label") in {"different_event", "uncertain"}):
                    examples.append(_example(self, session, plan, task, outcome))
        value = {"method": METHOD, "versions": candidate["versions"], "screen_protocol": protocol,
            "candidate_result": data["candidate_result"], **subset(membership, studies), "examples": examples,
            "new_model_calls": 0, "candidate_precision": None, "human_validated": False, "memberships_changed": False}
        identifier = self.ledger.record(session, "luna_group_validation_diagnostic", digest(value), value)
        presentation = self._record_presentation(session, Context(context.objective, context.actor, candidate["versions"]), {
            "results": [{"kind": "luna_group_validation_diagnostic", "id": identifier}],
            "markdown": render(value), "destination": "codex_chat", "status": "prepared_for_delivery"})
        return {"id": identifier, **value, "presentation": presentation}
