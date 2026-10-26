"""Pure one-pass atomic-menu rollout; proposals never authorize a merge."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from itertools import islice, zip_longest
import hashlib
import json
from pathlib import Path

import luna_snippet_grouping as pilot
from newsresearch.common import ResearchError, canonical, digest, require_no_credentials

METHOD = "luna-snippet-rollout-grouping-v1"
MAX_ARTICLES, MAX_TOKENS, LOOKAHEAD = 100, 32_000, 32
CATEGORIES = ("loose", "singleton", "multi")
RULES = pilot.RULES + "\n\n" + pilot.base.PAIR_RULES + "\n\n" + pilot.focal.FOCUS_RULES + (
    "\nOnly snippets are supplied in this proposal task. Any requirement above to inspect a whole article "
    "is deferred to separate full-source QA; never assume missing body evidence was inspected. "
    "Only the named anchor units have questions. Other displayed units are context. A question may show "
    "one predefined segment of its anchor's candidate menu. KEEP and UNKNOWN apply only to that "
    "question's listed targets, never to omitted targets or global uniqueness. Judge each question independently.")
PILOT_RULES = pilot.RULES + "\n\n" + pilot.base.PAIR_RULES + "\n\n" + pilot.focal.FOCUS_RULES + (
    "\nOnly snippets are supplied in this proposal task. Any requirement above to inspect a whole article "
    "is deferred to the separate full-source QA; never assume missing body evidence was inspected.")

proposals = pilot.proposals
select_supported = pilot.select_supported
snippet = pilot.snippet


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = [Path(__file__), Path(pilot.__file__), Path(pilot.base.__file__), Path(pilot.focal.__file__),
        Path(pilot.recall.__file__), root / "src/newsresearch/common.py"]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _require(condition, reason):
    if not condition:
        raise ResearchError("snippet_rollout_" + reason)


def _balanced_order(units):
    queues = [[u for u in sorted(units) if units[u]["kind"] == kind] for kind in CATEGORIES]
    return [u for row in zip_longest(*queues) for u in row if u is not None]


def normalized_question_identity(packet, name):
    """Exact supported rubric, source membership and targets; names/context grant no retry."""
    instructions = json.loads(packet["request"]["input"])["instructions"]
    _require(instructions in {RULES, PILOT_RULES}, "unsupported_question_rubric")
    mapping = packet["question_map"][name]
    anchor = mapping["unit_id"]
    def members(unit):
        binding = packet["unit_bindings"][unit]
        return {"members": sorted(binding["members"]), "input_bindings": sorted(binding["input_bindings"])}
    target_values = [members(u) for u in packet["menus"][anchor]]
    return digest({"semantic_role": "same_focal_event_snippet_unit_choice",
        "rubric": digest([pilot.RULES, pilot.base.PAIR_RULES, pilot.focal.FOCUS_RULES]),
        "model": packet["request"]["model"], "anchor": members(anchor),
        "targets": sorted(target_values, key=digest)})


def _segment(anchor, targets, full_menu, menu_id, *, mode="complete", ordinal=0, count=1):
    identity = {"method": METHOD, "anchor": anchor, "menu_id": menu_id, "targets": list(targets)}
    return {**identity, "segment_id": digest(identity), "full_menu_targets": list(full_menu),
        "mode": mode, "ordinal": ordinal, "segment_count": count}


def _task_identity(packet):
    return digest({"method": METHOD, "request": packet["request_sha256"],
        "units": packet["unit_bindings"], "segments": packet["anchor_segments"]})


def _packet(segments, units, snippets, count_tokens):
    anchors = [s["anchor"] for s in segments]
    _require(len(set(anchors)) == len(anchors) and bool(anchors), "duplicate_anchor")
    selected = sorted({u for s in segments for u in [s["anchor"], *s["targets"]]})
    article_ids = sorted(i for u in selected for i in units[u]["members"])
    if len(article_ids) > MAX_ARTICLES:
        raise ResearchError("snippet_rollout_packet_capacity")
    by_anchor = {s["anchor"]: deepcopy(s) for s in segments}
    questions, question_map = [], {}
    for n, u in enumerate(sorted(anchors)):
        s = by_anchor[u]
        name = f"unit_{n:03d}"
        targets = s["targets"]
        questions.append(pilot.base._question(name,
            f"Choose independently for UNIT {u} using the shared proposal and event rules. All displayed members remain atomic.",
            ["target:" + v for v in targets] + ["KEEP", "UNKNOWN"],
            [f"Propose union of all members of {u} and {v}; full-source QA remains required." for v in targets]
            + ["Keep this unit; no merge proposed among this question's listed targets.",
                "Snippet evidence is insufficient or conflicting."]))
        question_map[name] = {"kind": "snippet_assignment", "unit_id": u,
            "membership_revision": units[u]["membership_revision"], "source_version": units[u]["source_version"],
            "segment_id": s["segment_id"]}
    displayed = [{"unit_id": u, "articles": [{k: snippets[i][k] for k in
        ("document_id", "title", "first_sentence", "last_sentence")} for i in units[u]["members"]]} for u in selected]
    request = {"model": pilot.base.MODEL, "input": canonical({"instructions": RULES, "units": displayed}),
        "questions": questions, "prompt_cache_options": {"mode": "explicit"}}
    require_no_credentials(request)
    wire = canonical(request)
    size = len(wire.encode("utf-8"))
    if size > pilot.base.MAX_WIRE_BYTES:
        raise ResearchError("snippet_rollout_packet_capacity")
    tokens = count_tokens(wire)
    _require(type(tokens) is int and tokens >= 0, "token_measurement")
    if tokens > MAX_TOKENS:
        raise ResearchError("snippet_rollout_packet_capacity")
    bindings = {u: pilot._binding(units[u]) for u in selected}
    packet = {"method": METHOD, "kind": "decisions", "role": "snippet_proposal",
        "request": request, "request_sha256": digest(request), "question_map": question_map,
        "unit_ids": selected, "unit_bindings": bindings, "anchor_unit_ids": sorted(anchors),
        "context_only_unit_ids": sorted(set(selected) - set(anchors)), "anchor_segments": by_anchor,
        "article_ids": article_ids, "article_occurrences": len(article_ids),
        "input_tokens_proxy": tokens, "wire_bytes": size, "token_count_is_provider_exact": False,
        "menus": {u: list(by_anchor[u]["targets"]) for u in sorted(anchors)},
        "seed_units": [anchors[0]], "logical_ids": sorted(s["segment_id"] for s in segments),
        "snippet_bindings": {i: {k: snippets[i][k] for k in ("input_sha256", "body_spans", "snippet_sha256")} for i in article_ids}}
    packet["task_key"] = _task_identity(packet)
    packet["reservation_nanousd"] = pilot.recall.reservation(packet)
    packet["coverage"] = sorted({pilot._stratum(s["anchor"], v, units) for s in segments for v in s["targets"]})
    packet["visible_unit_pairs"] = [list(e) for e in sorted({tuple(sorted((s["anchor"], v))) for s in segments for v in s["targets"]})]
    return packet


def _try_packet(segments, units, snippets, count_tokens):
    try:
        return _packet(segments, units, snippets, count_tokens)
    except ResearchError as error:
        if str(error) != "snippet_rollout_packet_capacity":
            raise
        return None


def _split(anchor, menu, menu_id, units, snippets, count_tokens):
    """One ordered scan; no member or menu edge disappears on capacity failure."""
    if not menu:
        return [], [{"anchor": anchor, "target": None, "reason": "no_retained_candidates"}]
    if len(units[anchor]["members"]) > MAX_ARTICLES:
        return [], [{"anchor": anchor, "target": v, "reason": "atomic_anchor_exceeds_article_capacity"} for v in menu]
    whole = _segment(anchor, menu, menu, menu_id)
    if _try_packet([whole], units, snippets, count_tokens) is not None:
        return [whole], []
    portions, current, unavailable = [], [], []
    for target in menu:
        trial = _segment(anchor, [*current, target], menu, menu_id)
        if _try_packet([trial], units, snippets, count_tokens) is not None:
            current.append(target)
            continue
        if current:
            portions.append(current)
            current = []
            if _try_packet([_segment(anchor, [target], menu, menu_id)], units, snippets, count_tokens) is not None:
                current = [target]
                continue
        unavailable.append({"anchor": anchor, "target": target, "reason": "atomic_pair_exceeds_packet_capacity"})
    if current:
        portions.append(current)
    return [_segment(anchor, targets, menu, menu_id, mode="sharded", ordinal=n, count=len(portions))
        for n, targets in enumerate(portions)], unavailable


def prepare(source, state, count_tokens, *, prior_questions=None):
    """Freeze all menus and bounded-lookahead packets; no paid coverage is claimed."""
    _require(prior_questions is None or isinstance(prior_questions, dict), "prior_questions")
    prior_questions = prior_questions or {}
    units, snippets = pilot._units(source, state)
    menus, _, missing = pilot._menus(source, units)
    order = _balanced_order(units)
    calls = 0
    def counted(wire):
        nonlocal calls
        calls += 1
        return count_tokens(wire)
    plans, segments, unavailable, candidate_pairs = {}, [], [], set()
    for anchor in order:
        targets = [r["unit_id"] for r in menus[anchor]]
        menu_id = digest({"method": METHOD, "anchor": pilot._binding(units[anchor]),
            "targets": [pilot._binding(units[v]) for v in targets]})
        for target in targets:
            candidate_pairs.update(tuple(sorted((a, b))) for a in units[anchor]["members"] for b in units[target]["members"])
        portions, gaps = _split(anchor, targets, menu_id, units, snippets, counted)
        segments.extend(portions)
        unavailable.extend(gaps)
        plans[anchor] = {"menu_id": menu_id, "targets": targets,
            "segments": [s["segment_id"] for s in portions], "unavailable": gaps,
            "mode": "complete" if portions and portions[0]["mode"] == "complete" else "sharded" if portions else "unavailable",
            "all_menu_edges_planned": bool(targets) and not gaps}
    prior_blocked, fresh = [], []
    for s in segments:
        # Identity needs only exact source hashes/memberships, not another wire
        # rendering or tokenizer pass over all displayed snippets.
        identity_view = {"request": {"model": pilot.base.MODEL, "input": canonical({"instructions": RULES})},
            "question_map": {"unit_000": {"unit_id": s["anchor"]}}, "menus": {s["anchor"]: s["targets"]},
            "unit_bindings": {u: units[u] for u in [s["anchor"], *s["targets"]]}}
        identity = normalized_question_identity(identity_view, "unit_000")
        s["normalized_question_id"] = identity
        if identity in prior_questions:
            prior_blocked.append({"anchor": s["anchor"], "segment_id": s["segment_id"],
                "question_identity": identity, "reason": "exact_proposal_question_already_attempted"})
        else:
            fresh.append(s)
    pending = OrderedDict((s["segment_id"], s) for s in fresh)
    _require(len(pending) == len(fresh), "duplicate_segment")
    packets, segment_packets = [], {}
    while pending:
        _, first = pending.popitem(last=False)
        chosen = [first]
        packet = _packet(chosen, units, snippets, counted)
        # At most 32 candidates are examined per packet; never rescan the corpus.
        window = dict(islice(pending.items(), LOOKAHEAD))
        while window:
            selected_units = set(packet["unit_ids"])
            selected_anchors = {s["anchor"] for s in chosen}
            eligible = [(key, s) for key, s in window.items() if s["anchor"] not in selected_anchors]
            if not eligible:
                break
            def priority(item):
                key, s = item
                extra = {s["anchor"], *s["targets"]} - selected_units
                return sum(len(units[u]["members"]) for u in extra), s["anchor"], s["ordinal"], key
            key, candidate = min(eligible, key=priority)
            del window[key]
            trial = _try_packet([*chosen, candidate], units, snippets, counted)
            if trial is not None:
                chosen.append(candidate)
                packet = trial
                del pending[key]
        packets.append(packet)
        for s in chosen:
            _require(s["segment_id"] not in segment_packets, "repeated_segment")
            segment_packets[s["segment_id"]] = packet["task_key"]
    planned_edges = {(s["anchor"], v) for s in segments for v in s["targets"]}
    missing_edges = {(g["anchor"], g["target"]) for g in unavailable if g["target"] is not None}
    all_edges = {(a, row["unit_id"]) for a in order for row in menus[a]}
    _require(not planned_edges.intersection(missing_edges) and planned_edges | missing_edges == all_edges
        and sum(len(s["targets"]) for s in segments) == len(planned_edges), "menu_edge_partition")
    shown = sorted({i for p in packets for i in p["article_ids"]})
    coverage_plan = {"method": METHOD, "category_order": list(CATEGORIES), "anchor_order": order,
        "lookahead": LOOKAHEAD, "anchors": plans, "segment_packets": segment_packets,
        "unavailable": unavailable, "prior_blocked": prior_blocked,
        "planning_only": True, "actual_attempts_available": False}
    coverage_plan["sha256"] = digest(coverage_plan)
    coverage = {"total_units": len(units), "total_articles": len(snippets), "packets": len(packets),
        "question_segments": len(segments), "complete_menu_anchors": sum(p["mode"] == "complete" for p in plans.values()),
        "sharded_menu_anchors": sum(p["mode"] == "sharded" for p in plans.values()),
        "unavailable_anchors": sum(p["mode"] == "unavailable" for p in plans.values()),
        "all_edges_planned_anchors": sum(p["all_menu_edges_planned"] for p in plans.values()),
        "shared_packets": sum(len(p["anchor_unit_ids"]) > 1 for p in packets),
        "prior_blocked_segments": len(prior_blocked), "fresh_question_segments": len(fresh),
        "menu_edges": len(all_edges), "planned_menu_edges": len(planned_edges), "unavailable_menu_edges": len(missing_edges),
        "article_occurrences": sum(p["article_occurrences"] for p in packets), "unique_articles": len(shown),
        "unique_units": len({u for p in packets for u in p["unit_ids"]}),
        "missing_neighbor_channels": missing, "deferred": unavailable, "tokenizer_calls": calls,
        "covered_strata": sorted({s for p in packets for s in p["coverage"]}),
        "all_corpus_compared": False, "global_uniqueness_proved": False, "coverage_is_planned_only": True}
    return {"method": METHOD, "packets": packets, "units": units, "menus": menus,
        "source_binding": digest({i: s["input_sha256"] for i, s in snippets.items()}),
        "state_binding": digest({u: pilot._binding(v) for u, v in units.items()}),
        "coverage_plan": coverage_plan, "coverage": coverage,
        "candidate_article_pairs": [list(p) for p in sorted(candidate_pairs)],
        "planned_shown_article_ids": shown, "actual_shown_article_ids": None}


def coverage_status(selection, attempted_packet_keys, usable_packet_keys):
    """Coverage is based on asked segments, never context-only appearances."""
    plan = selection["coverage_plan"]
    _require(plan["sha256"] == digest({k: v for k, v in plan.items() if k != "sha256"}), "coverage_plan")
    packets = {p["task_key"]: p for p in selection["packets"]}
    attempted, usable = set(attempted_packet_keys), set(usable_packet_keys)
    _require(usable <= attempted <= set(packets), "coverage_attempt_keys")
    prior_ids = {p["segment_id"] for p in plan["prior_blocked"]}
    result = {"complete_joint": 0, "all_shards": 0, "partial": 0, "unattempted": 0,
        "prior_blocked": 0, "capacity": 0, "no_candidates": 0}
    for anchor in plan["anchor_order"]:
        row = plan["anchors"][anchor]
        segment_ids = row["segments"]
        packet_ids = [plan["segment_packets"][s] for s in segment_ids if s in plan["segment_packets"]]
        if not row["targets"]:
            result["no_candidates"] += 1
        elif row["unavailable"]:
            result["capacity"] += 1
        elif prior_ids.intersection(segment_ids):
            result["prior_blocked"] += 1
        elif packet_ids and all(p in usable for p in packet_ids):
            result["complete_joint" if row["mode"] == "complete" else "all_shards"] += 1
        elif any(p in attempted for p in packet_ids):
            result["partial"] += 1
        else:
            result["unattempted"] += 1
    shown = sorted({i for key in attempted for i in packets[key]["article_ids"]})
    return {**result, "total_units": len(plan["anchors"]), "attempted_packets": len(attempted),
        "usable_packets": len(usable), "actual_shown_article_ids": shown,
        "actual_shown_unique_articles": len(shown),
        "actual_article_occurrences": sum(packets[k]["article_occurrences"] for k in attempted),
        "coverage_unit": "anchor_menu_not_context_exposure", "global_uniqueness_proved": False}


def parse(packet, payload):
    """Same proposal labels as pilot, with exact anchor-only segment bindings."""
    _require(packet["method"] == METHOD and packet["kind"] == "decisions"
        and packet["role"] == "snippet_proposal", "packet_method")
    _require(packet["request_sha256"] == digest(packet["request"])
        and packet["task_key"] == _task_identity(packet), "packet_identity")
    bindings, segments = packet["unit_bindings"], packet["anchor_segments"]
    anchors = packet["anchor_unit_ids"]
    _require(len(anchors) == len(set(anchors)) and set(anchors) == set(segments) == set(packet["menus"])
        and set(bindings) == set(packet["unit_ids"]) and set(anchors) <= set(bindings), "packet_units")
    mapped = [q["unit_id"] for q in packet["question_map"].values()]
    names = [q["name"] for q in packet["request"]["questions"]]
    _require(len(mapped) == len(set(mapped)) and set(mapped) == set(anchors)
        and len(names) == len(set(names)) and set(names) == set(packet["question_map"]), "question_unit_bijection")
    for q in packet["request"]["questions"]:
        m = packet["question_map"][q["name"]]
        u, targets = m["unit_id"], packet["menus"][m["unit_id"]]
        s = segments[u]
        expected = _segment(u, targets, s["full_menu_targets"], s["menu_id"],
            mode=s["mode"], ordinal=s["ordinal"], count=s["segment_count"])
        expected["normalized_question_id"] = normalized_question_identity(packet, q["name"])
        _require(s == expected and m["segment_id"] == s["segment_id"]
            and m["membership_revision"] == bindings[u]["membership_revision"]
            and m["source_version"] == bindings[u]["source_version"], "question_binding")
        _require(bool(targets) and len(targets) == len(set(targets)) and u not in targets
            and set(targets) <= set(bindings) and set(targets) <= set(s["full_menu_targets"])
            and len(s["full_menu_targets"]) == len(set(s["full_menu_targets"]))
            and s["mode"] in {"complete", "sharded"}
            and type(s["ordinal"]) is int and type(s["segment_count"]) is int
            and 0 <= s["ordinal"] < s["segment_count"] <= pilot.MENU_SIZE
            and len(s["full_menu_targets"]) <= pilot.MENU_SIZE and u not in s["full_menu_targets"]
            and (s["mode"] != "complete" or targets == s["full_menu_targets"])
            and [c["value"] for c in q["choices"]] == ["target:" + v for v in targets] + ["KEEP", "UNKNOWN"], "question_targets")
    parsed = pilot.base.parse_decisions(packet, payload)
    links, keep, unknown = [], [], []
    for answer in parsed["answers"].values():
        u = answer["unit_id"]
        if answer["status"] != "valid" or answer["label"] == "UNKNOWN":
            unknown.append(u)
        elif answer["label"] == "KEEP":
            keep.append(u)
        else:
            v = answer["label"][len("target:"):]
            links.append({"source": u, "target": v, "probability": answer["probability"],
                "task_key": packet["task_key"], "segment_id": segments[u]["segment_id"],
                "source_revision": bindings[u]["membership_revision"], "target_revision": bindings[v]["membership_revision"],
                "source_version": bindings[u]["source_version"], "target_version": bindings[v]["source_version"]})
    return {"method": METHOD, "status": parsed["status"], "task_key": packet["task_key"], "answers": parsed["answers"],
        "links": links, "keep": sorted(keep), "unknown": sorted(unknown),
        "answered_segments": sorted(s["segment_id"] for s in segments.values()),
        "proposal_only": True, "global_uniqueness_proved": False, "probabilities_calibrated": False,
        "keep_and_unknown_scope": "visible_menu_segment_only"}
