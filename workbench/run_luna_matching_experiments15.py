"""Fifteen registered variants, development selection, fresh test and full graph."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

import sklearn

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.storage import check_permissions
from newsresearch.runtime import audited_handler
from newsresearch import luna_scalable_matching as base
from newsresearch import luna_matching_experiments15 as core

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lean_luna_state as state  # noqa: E402
import run_luna_scalable_experiment as references  # noqa: E402
from luna_scalable_rule_experiment_v2 import group  # noqa: E402
from benchmark_luna_matching_scale import peak_working_set  # noqa: E402

METHOD = core.METHOD
SEED = "luna-fifteen-fresh-test-20261020-v1"
DEFAULT_BASE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")


@dataclass(frozen=True)
class LocalInvocation:
    request: dict

    def manifest(self):
        return {"transport": "local-deterministic-sklearn", "sklearn_version": sklearn.__version__,
            "method": METHOD, "request_sha256": digest(self.request), "network_calls": 0}


class LocalProvider:
    def complete_prepared(self, invocation):
        request = invocation.request
        if request["operation"] == "develop":
            result = core.develop(request["rows"])
        elif request["operation"] == "score":
            result = [[core.score(e["id"], p, e["model"]) for e in request["specs"]] for p in request["features"]]
        else:
            raise AuditError("unknown_local_computation")
        return ProviderResponse(result, "local-sklearn", "LogisticRegression-" + sklearn.__version__,
            usage={"local_rows": len(request.get("rows", request.get("features", []))), "paid_api_requests": 0},
            raw_response={"deterministic_local_computation": True, "network_calls": 0})


def implementation():
    files = [Path(__file__), Path(core.__file__), Path(base.__file__), Path(references.__file__),
        Path(__file__).with_name("luna_scalable_rule_experiment_v2.py"), Path(core.previous.__file__)]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


class Source:
    def __init__(self, owner):
        self.owner = Path(owner).resolve(strict=True)
        check_permissions(self.owner, root=True)
        self.artifacts = state.SelectedArtifacts(self.owner)
        self.db = state.read_only_database(self.owner)

    def rows(self, kind):
        rows = []
        for row in self.db.execute("SELECT * FROM records WHERE kind=?", (kind,)):
            self.artifacts.check(row["artifact"])
            rows.append(state.row_value(row, kind))
        return rows

    def one(self, kind):
        rows = self.rows(kind)
        if len(rows) != 1:
            raise AuditError("fifteen_source_one_required_" + kind)
        return rows[0]

    def close(self):
        self.db.close()


def panel_groups(rows, scores, threshold):
    totals, panels = Counter(), []
    for family in sorted({r["family"] for r in rows}):
        selected = [(r, s) for r, s in zip(rows, scores, strict=True) if r["family"] == family]
        values = {(r["left"], r["right"]): (r, s) for r, s in selected}
        ids = sorted({r[k] for r, _ in selected for k in ("left", "right")})
        def lookup(a, b):
            _, value = values[(a, b)]
            return {"left": a, "right": b, "label": "same_event" if value >= threshold else "unresolved", "score": value}
        decisions = {(r["left"], r["right"]): lookup(r["left"], r["right"]) for r, _ in selected if r["retrieved_rank"] is not None}
        result = group(ids, decisions, lookup)
        positions = {i: n for n, members in enumerate(result["groups"]) for i in members}
        for r, _ in selected:
            if positions[r["left"]] == positions[r["right"]]:
                totals["joined_pairs"] += 1
                totals["correct_joins"] += r["reference"] == "same_event"
                totals["false_joins"] += r["reference"] == "different_event"
                totals["unverifiable_joins"] += r["reference"] == "insufficient_evidence"
            elif r["reference"] == "same_event":
                totals["missed_same_pairs"] += 1
        totals["additional_pairs"] += result["added_pairs"]
        totals["multi_article_groups"] += sum(len(g) > 1 for g in result["groups"])
        panels.append({"family": family, **result})
    return {"counts": dict(totals), "panels": panels}


class Study(references.Experiment):
    def local_compute(self, session, operation, **data):
        request = {"operation": operation, "method": METHOD, "implementation": implementation(), **data}
        key = digest(request)
        if any(v["task_key"] == key for v in self.ledger.unresolved.values()) or self.ledger.db.execute(
            "SELECT 1 FROM attempts WHERE task_key=?", (key,)).fetchone():
            raise AuditError("local_computation_already_attempted_no_retry")
        invocation = LocalInvocation(request)
        attempt, batch = str(uuid.uuid4()), str(uuid.uuid4())
        intended = {"attempt": attempt, "task_key": key, "number": 1, "batch": batch,
            "request": self.ledger.artifacts.put(request), "dispatch": self.ledger.artifacts.put(invocation.manifest()),
            "started_at": utc(), "operation": operation, "provider": "local-sklearn"}
        self.ledger.append(session, "model.attempt.intended", intended)
        self.ledger.unresolved[attempt] = intended
        response = next(self.gateway.codex_dispatch(session, LocalProvider(), [(invocation, attempt)], 1))[1]
        response_ref = self.ledger.artifacts.put(asdict(response))
        if response.payload is None or (response.raw_response or {}).get("unknown_outcome"):
            self.ledger.append(session, "matching15.local.unknown", {"attempt": attempt, "response": response_ref})
            raise AuditError("local_computation_unknown_no_retry")
        identifier = self.ledger.record(session, "matching15_local_computation", key,
            {"request": intended["request"], "response": response_ref, "operation": operation,
             "provider": response.provider, "model": response.model, "paid_api_requests": 0})
        def project(event):
            self.ledger.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (
                attempt, key, batch, 1, intended["request"], response_ref, "valid", identifier, None, event))
        self.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "status": "valid",
            "assessment": identifier, "response": response_ref, "ended_at": utc()}, project)
        self.ledger.unresolved.pop(attempt)
        return response.payload

    @audited_handler
    def _status(self, session, context, data):
        action = data["action"]
        if action == "prepare":
            return self.prepare(session, context, data)
        frozen = self.one("matching15_input")
        if frozen["implementation"] != implementation():
            raise AuditError("fifteen_frozen_implementation_changed")
        if action == "develop":
            return self.develop(session, frozen)
        development = self.one("matching15_development")
        if action == "panels":
            return self.panels15(session, context, frozen, development)
        plan = self.one("luna_scalable_panel_plan")
        if action == "dispatch":
            return self.dispatch(session, plan, "test")
        if action == "read":
            return self.read(session, plan, {**data, "split": "test"})
        if action == "submit":
            return self.submit(session, plan, {**data, "split": "test"})
        if action == "evaluate":
            return self.evaluate15(session, frozen, development, plan)
        if action == "profile":
            return self.profile(session, frozen, development)
        raise AuditError("unknown_fifteen_action")

    def prepare(self, session, context, data):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='matching15_input'").fetchone():
            raise AuditError("fifteen_input_already_frozen")
        versions = {}
        definitions = {
            "protocol": {"method": METHOD, "implementation": implementation(), "experiments": core.MANIFEST,
                "scope": "Exactly fifteen new deterministic rule/classifier variants plus the unchanged v3 baseline. Reuse 78 prior Luna-only model references as development, including previous tests. Keep the frozen 30,340-card v3 retrieval graph and its bounds. Enrich saved fields without article-body inference, new extraction, embeddings or paid API. All outputs remain provisional.",
                "selection": "Rule thresholds maximize correct development calls subject to zero false/uncertain calls; ties favor higher threshold. Three logistic models use standardized numeric features, C=1, balanced classes, liblinear, seed 1701, and leave-one-panel-family-out predictions for threshold selection. Fit the final model on all development references; save plain coefficients, no pickle. Select the method with most safe development positives; ties favor earlier experiment ID. Freeze before test selection or evidence exposure. All fifteen test results are descriptive comparisons; never switch the selected method based on them.",
                "held_out": "Six fresh entity panels per corpus, same dated/multiple-publisher sampling recipe with a new seed. Exclude prior panel bodies and anchor families, and all available body hashes and article IDs from the earlier 1,100-card pilot. Missing pilot hashes remain explicit; different IDs with an unavailable body hash cannot be proven disjoint. All unordered panel pairs judged once through the current-conversation shared gateway. No source-article/human gold; same model develops and reviews methods.",
                "evaluation": "Report separate same/different/uncertain counts, overall supported fraction including uncertain calls, known-positive candidate recovery, candidate-conditional calls, and complete-link group errors. No population prevalence or general recall estimate. Selection across 15 methods increases optimism; the single fresh test is not used for tuning.",
                "promotion_gate": "Selected method: at least 10 known-positive test pairs; >=90% candidate recovery; >=5 supported same calls; zero false or unverifiable calls and group joins. Gate permits full-input provisional grouping only; no accepted research findings.",
                "resources": "Reuse <=384 scored candidates and <=20 neighbors per article. Full profile scores all fifteen on the same <=606,800 directed links; bounded missing-link grouping uses <=5*N extra pairs, <=50 members and <=8 passes. Character input capped at 800 characters with flags; name trigram cache bounded at 60,000 entries.",
                "local_model_audit": "All classifier fitting and inference passes through the shared audited gateway with a truthful offline sklearn provider. Exact numeric inputs, serialized coefficients, dispatch manifests and results are recorded before/after each computation. No external request, automatic retry or hidden provider fallback. Full scoring is batched at 10,000 pairs.",
                "budget": "Existing user $20 API ceiling persists including prior estimate $0.0211706. This run dispatches no paid API requests. Current-conversation usage is unavailable, not asserted zero."},
            "question": {"text": "Which of fifteen deterministic changes improves provisional event matching without merging distinct or ambiguous occurrences?"},
            "selection": {"rules": "Frozen saved Standard single-event cards; original corpora separate; fixed candidate graph; previous references become development; new seed and body/family exclusions for final test."},
            "profile": {"mode": "exploratory", "population_estimate": False},
            "dossier_definition": {"unit": "Same specific focal occurrence; shared subject, actor or product insufficient; unresolved parent/local event boundaries abstain."},
            "codebook": {"labels": sorted(references.LABELS), "definitions": references.RULES},
        }
        for kind, content in definitions.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        self.ledger.append(session, "matching15.prepare.intended", {"versions": versions})
        root = Path(data["base"])
        parent = Source(root / "luna-scalable-experiment-20261020-v3")
        try:
            source_input = parent.one("luna_scalable_input")
            retrieval = parent.one("luna_scalable_retrieval")
            chunks, cards = [], {}
            for ref in source_input["chunks"]:
                values = parent.artifacts.json(ref)
                chunks.append(self.ledger.artifacts.put(values))
                cards.update((c["article_id"], c) for c in values if c["readiness"] == "ready")
            parent.artifacts.check(retrieval["candidate_artifact"])
            candidate = self.ledger.artifacts.put_file(parent.artifacts.path(retrieval["candidate_artifact"]))
        finally:
            parent.close()
        rows, bodies, families, prior_refs = [], set(), set(), []
        for name in ("luna-scalable-experiment-20261020-v1", "luna-scalable-experiment-20261020-v3"):
            source = Source(root / name)
            try:
                plan = source.one("luna_scalable_panel_plan")
                mapping = {m["panel"]: m for m in plan["mapping"]}
                for m in plan["mapping"]:
                    families.add((m["corpus"], m["family_key"]))
                    bodies.update((cards[i]["corpus"], cards[i]["body_sha256"]) for i in m["cards"].values())
                for reference in source.rows("luna_scalable_panel_references"):
                    prior_refs.append(reference["_record_id"])
                    for r in reference["replies"]:
                        m = mapping[r["panel"]]
                        a, b = sorted((m["cards"][r["a"]], m["cards"][r["b"]]))
                        rows.append({"left": a, "right": b, "corpus": m["corpus"], "family": digest([name, r["panel"]]),
                            "reference": r["label"], "source_reference": reference["_record_id"], "source_panel": r["panel"]})
            finally:
                source.close()
        prior = Source(root / "luna-matching-pilot-20261020-v1")
        try:
            pilot = prior.one("luna_matching_pilot_plan")
            pilot_cards = prior.artifacts.json(pilot["cards"])
            pilot_bodies = {(c["corpus"], c["body_sha256"]) for c in pilot_cards}
            excluded_ids = {c["article_id"] for c in pilot_cards} | {i for r in rows for i in (r["left"], r["right"])}
        finally:
            prior.close()
        index = base.Index(base.features(c) for c in cards.values())
        rich = {i: core.enrich(cards[i]) for r in rows for i in (r["left"], r["right"])}
        own = state.SelectedArtifacts(self.ledger.root)
        db = sqlite3.connect(own.path(candidate).as_uri() + "?mode=ro", uri=True)
        try:
            db.execute("PRAGMA query_only=ON")
            for row in rows:
                row["features"] = core.rich_pair(rich[row["left"]], rich[row["right"]], index.idf[row["corpus"]])
                found = db.execute("SELECT best_rank FROM pairs WHERE corpus=? AND left_id=? AND right_id=?", (row["corpus"], row["left"], row["right"])).fetchone()
                row["retrieved_rank"] = found[0] if found else None
        finally:
            db.close()
        if len({(r["left"], r["right"]) for r in rows}) != len(rows):
            raise AuditError("duplicate_development_pair")
        result = {"versions": versions, "implementation": implementation(), "sklearn_version": sklearn.__version__, "chunks": chunks,
            "development_pairs": self.ledger.artifacts.put(rows), "candidate_artifact": candidate,
            "source_input": source_input["_record_id"], "source_retrieval": retrieval["_record_id"], "prior_references": prior_refs,
            "excluded_bodies": sorted(bodies | pilot_bodies, key=lambda v: json.dumps(v)), "excluded_families": sorted(families),
            "excluded_body_keys_missing_hash": sum(body is None for _, body in bodies | pilot_bodies),
            "excluded_article_ids": sorted(excluded_ids), "pilot_cards_missing_body_hash": sum(c["body_sha256"] is None for c in pilot_cards),
            "ready_articles": len(cards), "development_pairs_count": len(rows), "development_panels": len({r["family"] for r in rows}),
            "prior_panel_bodies": len(bodies), "pilot_bodies": len(pilot_bodies), "new_paid_api_requests": 0}
        identifier = self.ledger.record(session, "matching15_input", METHOD, result)
        return {"id": identifier, **{k: result[k] for k in ("ready_articles", "development_pairs_count", "development_panels", "prior_panel_bodies", "pilot_bodies", "new_paid_api_requests")}}

    def develop(self, session, frozen):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='matching15_development'").fetchone():
            raise AuditError("fifteen_development_already_frozen")
        self.ledger.append(session, "matching15.develop.intended", {"input": frozen["_record_id"]})
        rows = self.ledger.artifacts.read(frozen["development_pairs"])
        result = self.local_compute(session, "develop", rows=rows)
        result.update({"input": frozen["_record_id"], "implementation": implementation(), "references": dict(Counter(r["reference"] for r in rows)), "paid_api_requests": 0})
        identifier = self.ledger.record(session, "matching15_development", METHOD, result)
        (self.ledger.root / "development.json").write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, "selected_experiment": result["selected_experiment"], "baseline": result["baseline"],
            "experiments": [{k: e[k] for k in ("id", "name", "threshold", "development", "scoring_mode")} for e in result["experiments"]]}

    def panels15(self, session, context, frozen, development):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_scalable_panel_plan'").fetchone():
            raise AuditError("fifteen_panels_already_frozen")
        self.ledger.append(session, "matching15.panels.intended", {"input": frozen["_record_id"], "development": development["_record_id"], "seed": SEED})
        excluded, old_families = {tuple(v) for v in frozen["excluded_bodies"]}, {tuple(v) for v in frozen["excluded_families"]}
        excluded_ids = set(frozen["excluded_article_ids"])
        cards, field, publishers, groups = {}, {}, {}, defaultdict(list)
        for c in self.cards(frozen):
            if c["readiness"] != "ready" or c["article_id"] in excluded_ids or (c["corpus"], c["body_sha256"]) in excluded:
                continue
            f = core.enrich(c)
            pubs = {m["publisher"]["uri"] for m in c["metadata_variants"] if m["publisher"]["uri"]}
            if f.base.day is None or len(pubs) != 1:
                continue
            i = c["article_id"]
            cards[i], field[i], publishers[i] = c, f, next(iter(pubs))
            for name in f.names:
                groups[(c["corpus"], name)].append(i)
        panels, mapping, used = [], [], set()
        for corpus in sorted({key[0] for key in groups}):
            selected = 0
            keys = sorted((k for k, ids in groups.items() if k[0] == corpus and 3 <= len(ids) <= 120 and k not in old_families), key=lambda k: digest([SEED, k]))
            for key in keys:
                if selected == 6:
                    break
                members = sorted((i for i in groups[key] if (corpus, cards[i]["body_sha256"]) not in used), key=lambda i: (field[i].base.day, i))
                windows = []
                for a in members:
                    nearby = [i for i in members if 0 <= field[i].base.day - field[a].base.day <= 7]
                    if len({publishers[i] for i in nearby}) >= 3:
                        windows.append((a, nearby))
                if not windows:
                    continue
                anchor, nearby = min(windows, key=lambda item: digest([SEED, key, item[0]]))
                chosen, pubs, bodies = [], set(), set()
                for i in sorted(nearby, key=lambda i: digest([SEED, key, i])):
                    body = cards[i]["body_sha256"]
                    if publishers[i] not in pubs and body not in bodies:
                        chosen.append(i)
                        pubs.add(publishers[i])
                        bodies.add(body)
                    if len(chosen) == 3:
                        break
                if len(chosen) != 3:
                    continue
                distant = [i for i in members if 15 <= abs(field[i].base.day - field[anchor].base.day) <= 365 and cards[i]["body_sha256"] not in bodies]
                if distant:
                    chosen.append(min(distant, key=lambda i: digest([SEED, "distant", key, i])))
                number, packet, mapped = len(panels) + 1, [], {}
                for side, i in zip("ABCD", chosen):
                    c = cards[i]
                    packet.append({"side": side, "published_at": c["published_at"], "records": [{"view": r["view"], "output": r["output"]} for r in c["records"] if r["mechanically_usable"]]})
                    mapped[side] = i
                    used.add((corpus, c["body_sha256"]))
                panels.append({"panel": number, "cards": packet})
                mapping.append({"panel": number, "split": "test", "corpus": corpus, "family_key": key[1], "cards": mapped})
                selected += 1
            if selected != 6:
                raise AuditError("insufficient_fresh_fifteen_panel_families")
        result = {"input": frozen["_record_id"], "development": development["_record_id"], "implementation": implementation(),
            "packets": self.ledger.artifacts.put(panels), "mapping": mapping, "seed": SEED,
            "prompt": self._version(session, context, {"kind": "prompt", "key": METHOD, "content": {"instructions": references.RULES}})["id"],
            "panels": len(panels), "pairs": sum(len(m["cards"]) * (len(m["cards"]) - 1) // 2 for m in mapping), "article_cards": len(used)}
        identifier = self.ledger.record(session, "luna_scalable_panel_plan", METHOD, result)
        self.ledger.record(session, "luna_scalable_calibration", METHOD, {"development": development["_record_id"], "selected_experiment": development["selected_experiment"], "implementation": implementation()})
        return {"id": identifier, "panels": result["panels"], "pairs": result["pairs"], "article_cards": result["article_cards"]}

    def evaluate15(self, session, frozen, development, plan):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='matching15_test'").fetchone():
            raise AuditError("fifteen_test_already_frozen")
        reference = self.one("luna_scalable_panel_references")
        self.ledger.append(session, "matching15.test.intended", {"references": reference["_record_id"], "development": development["_record_id"]})
        cards = {c["article_id"]: c for c in self.cards(frozen) if c["readiness"] == "ready"}
        index = base.Index(base.features(c) for c in cards.values())
        mapping = {m["panel"]: m for m in plan["mapping"]}
        rich = {i: core.enrich(cards[i]) for m in mapping.values() for i in m["cards"].values()}
        store = state.SelectedArtifacts(self.ledger.root)
        store.check(frozen["candidate_artifact"])
        db = sqlite3.connect(store.path(frozen["candidate_artifact"]).as_uri() + "?mode=ro", uri=True)
        rows = []
        try:
            db.execute("PRAGMA query_only=ON")
            for r in reference["replies"]:
                m = mapping[r["panel"]]
                a, b = sorted((m["cards"][r["a"]], m["cards"][r["b"]]))
                found = db.execute("SELECT best_rank FROM pairs WHERE corpus=? AND left_id=? AND right_id=?", (m["corpus"], a, b)).fetchone()
                rows.append({"panel": r["panel"], "a": r["a"], "b": r["b"], "left": a, "right": b, "corpus": m["corpus"],
                    "family": digest([plan["_record_id"], r["panel"]]), "reference": r["label"], "retrieved_rank": found[0] if found else None,
                    "features": core.rich_pair(rich[a], rich[b], index.idf[m["corpus"]])})
        finally:
            db.close()
        experiments = [{"id": "B00", "name": "Unchanged v3 baseline", "threshold": .5, "model": None}] + development["experiments"]
        outputs, private_scores = [], {}
        matrix = self.local_compute(session, "score", stage="fresh-test", specs=experiments, features=[r["features"] for r in rows])
        for column, e in enumerate(experiments):
            scores = [s[column] for s in matrix]
            private_scores[e["id"]] = scores
            grouping = panel_groups(rows, scores, e["threshold"])
            outputs.append({"id": e["id"], "name": e["name"], "threshold": e["threshold"],
                "rule": core.metrics(rows, scores, e["threshold"]),
                "retrieved_rule": core.metrics(rows, [s if r["retrieved_rank"] is not None else -1 for r, s in zip(rows, scores, strict=True)], e["threshold"]),
                "groups": grouping["counts"], "group_details": self.ledger.artifacts.put(grouping["panels"])})
        positive = [r for r in rows if r["reference"] == "same_event"]
        recovery = {str(k): {"recovered": sum(r["retrieved_rank"] is not None and r["retrieved_rank"] <= k for r in positive), "reference_pairs": len(positive)} for k in (5, 10, 20)}
        selected = next(e for e in outputs if e["id"] == development["selected_experiment"])
        measured, joins = selected["retrieved_rule"], selected["groups"]
        gate = bool(len(positive) >= 10 and recovery["20"]["recovered"] / len(positive) >= .90 and measured["correct_same"] >= 5
            and not measured["false_same"] and not measured["unverifiable_same"] and not joins.get("false_joins", 0) and not joins.get("unverifiable_joins", 0))
        result = {"input": frozen["_record_id"], "development": development["_record_id"], "plan": plan["_record_id"], "reference": reference["_record_id"],
            "reference_counts": dict(Counter(r["reference"] for r in rows)), "retrieval_recovery": recovery,
            "selected_experiment": development["selected_experiment"], "selected": selected, "promotion_passed": gate,
            "experiments": outputs, "pairs": self.ledger.artifacts.put(rows), "scores": self.ledger.artifacts.put(private_scores),
            "human_validated": False, "new_paid_api_requests": 0}
        identifier = self.ledger.record(session, "matching15_test", METHOD, result)
        (self.ledger.root / "test.json").write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, **{k: v for k, v in result.items() if k not in {"pairs", "scores", "experiments"}},
            "experiments": [{k: e[k] for k in ("id", "name", "rule", "groups")} for e in outputs]}

    def profile(self, session, frozen, development):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='matching15_profile'").fetchone():
            raise AuditError("fifteen_profile_already_frozen")
        test = self.one("matching15_test")
        self.ledger.append(session, "matching15.profile.intended", {"input": frozen["_record_id"], "development": development["_record_id"], "test": test["_record_id"]})
        started = time.perf_counter()
        rich = {c["article_id"]: core.enrich(c) for c in self.cards(frozen) if c["readiness"] == "ready"}
        index = base.Index(r.base for r in rich.values())
        store = state.SelectedArtifacts(self.ledger.root)
        store.check(frozen["candidate_artifact"])
        source = sqlite3.connect(store.path(frozen["candidate_artifact"]).as_uri() + "?mode=ro", uri=True)
        source.execute("PRAGMA query_only=ON")
        path = self.ledger.root / "all-experiment-scores.sqlite3"
        if path.exists():
            raise AuditError("fifteen_profile_store_already_exists")
        target = sqlite3.connect(path)
        target.execute("CREATE TABLE scores(corpus TEXT,left_id TEXT,right_id TEXT,scores TEXT,PRIMARY KEY(corpus,left_id,right_id)) WITHOUT ROWID")
        target.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)")
        target.execute("INSERT INTO metadata VALUES('complete','false')")
        specs = [{"id": "B00", "threshold": .5, "model": None}] + development["experiments"]
        counts, total, decisions = Counter(), 0, defaultdict(dict)
        selected = next(e for e in specs if e["id"] == development["selected_experiment"])
        try:
            if source.execute("SELECT value FROM metadata WHERE key='complete'").fetchone() != ("true",):
                raise AuditError("fifteen_source_candidate_store_incomplete")
            cursor = source.execute("SELECT corpus,left_id,right_id FROM pairs ORDER BY corpus,left_id,right_id")
            while batch := cursor.fetchmany(10000):
                features = [core.rich_pair(rich[a], rich[b], index.idf[corpus]) for corpus, a, b in batch]
                matrix = self.local_compute(session, "score", stage="full-profile", offset=total, specs=specs, features=features)
                for (corpus, a, b), scores in zip(batch, matrix, strict=True):
                    target.execute("INSERT INTO scores VALUES(?,?,?,?)", (corpus, a, b, json.dumps(scores)))
                    for e, value in zip(specs, scores, strict=True):
                        counts[e["id"]] += value >= e["threshold"]
                        if e["id"] == selected["id"] and test["promotion_passed"]:
                            decisions[corpus][(a, b)] = {"left": a, "right": b, "label": "same_event" if value >= e["threshold"] else "unresolved", "score": value}
                total += len(batch)
                target.commit()
                print(json.dumps({"stage": "fifteen_full_profile", "pairs": total, "elapsed_seconds": round(time.perf_counter() - started, 2)}), flush=True)
            target.execute("UPDATE metadata SET value='true' WHERE key='complete'")
            target.execute("INSERT INTO metadata VALUES('experiment_order',?)", (json.dumps([e["id"] for e in specs]),))
            target.commit()
        finally:
            source.close()
            target.close()
        grouping = None
        if test["promotion_passed"]:
            groups, totals = [], Counter()
            for corpus in sorted(index.idf):
                ids = [i for i, r in rich.items() if r.base.corpus == corpus]
                added, trace = 0, []
                for iteration in range(1, 9):
                    result = base.complete_link_groups(ids, decisions[corpus].values(), verification_cap=max(0, 5 * len(ids) - added))
                    missing = [tuple(p) for p in result["verification_queue"] if tuple(p) not in decisions[corpus]]
                    trace.append({"iteration": iteration, "groups": len(result["groups"]), "queued": len(missing)})
                    if not missing or iteration == 8:
                        break
                    for offset in range(0, len(missing), 10000):
                        batch = missing[offset:offset + 10000]
                        features = [core.rich_pair(rich[a], rich[b], index.idf[corpus]) for a, b in batch]
                        matrix = self.local_compute(session, "score", stage="full-grouping", corpus=corpus,
                            iteration=iteration, offset=offset, specs=[selected], features=features)
                        for (a, b), values in zip(batch, matrix, strict=True):
                            s = values[0]
                            decisions[corpus][(a, b)] = {"left": a, "right": b, "score": s, "label": "same_event" if s >= selected["threshold"] else "unresolved"}
                        added += len(batch)
                result.update({"added_pairs": added, "remaining_pairs": len(missing), "trace": trace})
                for members in result["groups"]:
                    groups.append({"corpus": corpus, "members": members})
                    totals["multi_article_groups"] += len(members) > 1
                    totals["unmatched_articles"] += len(members) == 1
                for k in ("added_pairs", "remaining_pairs", "verification_cap_hit", "blocked_merges", "oversize_merges"):
                    totals[k] += result[k]
            grouping = {"counts": dict(totals), "artifact": self.ledger.artifacts.put(groups), "accepted_findings": False}
        result = {"input": frozen["_record_id"], "development": development["_record_id"], "test": test["_record_id"],
            "articles": len(rich), "candidate_pairs": total, "experiments_executed": 15, "baseline_executed": True,
            "called_same_by_experiment": dict(counts), "selected_experiment": selected["id"], "grouping": grouping,
            "promotion_passed": test["promotion_passed"], "character_truncated_articles": sum(r.character_truncated for r in rich.values()),
            "elapsed_seconds": time.perf_counter() - started, "peak_working_set_bytes": peak_working_set(),
            "score_artifact": self.ledger.artifacts.put_file(path), "new_paid_api_requests": 0, "accuracy_of_unlabeled_pairs_known": False}
        identifier = self.ledger.record(session, "matching15_profile", METHOD, result)
        (self.ledger.root / "profile.json").write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, **result}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "develop", "panels", "dispatch", "read", "submit", "evaluate", "profile"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=1)
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    engine = Study(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(engine.execute("status", {"action": args.action, "base": str(args.base), "start": args.start, "end": args.end, "input": str(args.input)},
            objective="Improve Luna-based event matching through fifteen deterministic experiments and a fresh held-out test", actor="codex:luna-fifteen"), ensure_ascii=False))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
