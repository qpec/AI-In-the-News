"""Bounded, deterministic matching primitives; audited callers own corpus I/O.

No model calls or accepted research findings. Missing/capped searches are explicit.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Iterable, Iterator
import unicodedata

from .common import ResearchError, digest

METHOD = "luna-scalable-blocking-v1"
STOP = frozenset("the a an and or in on of to for with from that this were was have has had its are is be been into over after before about by as it at new said says van het de een voor met door bij zijn wordt aan dit deze als tot uit ook niet op om na er en in te dat die heeft hebben ze hun nog dan tot zich hij zij al".split())
GENERIC_NAMES = frozenset({"ai", "artificial intelligence", "kunstmatige intelligentie", "de stad", "the company", "het bedrijf", "politie", "de politie", "hackers", "de overheid", "agencies"})


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[^\W_]+", text))


def tokens(value: str) -> frozenset[str]:
    return frozenset(t for t in normalize(value).split() if len(t) >= 3 and t not in STOP)


def publication_day(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).toordinal()
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True, slots=True)
class Features:
    article_id: str
    corpus: str
    day: int | None
    names: frozenset[str]
    roles: frozenset[str]
    actions: frozenset[str]
    wording: frozenset[str]
    facts: frozenset[str]
    summaries: tuple[str, ...]
    event_times: frozenset[str]
    variants: int


def features(card: dict[str, Any]) -> Features:
    if card["readiness"] != "ready":
        raise ResearchError("matching_requires_ready_card")
    records = [r["output"]["event"] for r in card["records"] if r["mechanically_usable"]]
    names, roles, actions, wording, facts, times = set(), set(), set(), set(), set(), set()
    summaries = []
    for event in records:
        summaries.append(normalize(event["summary"]))
        wording.update(tokens(event["summary"]))
        actions.update(tokens(event["action"]["surface"]))
        for participant in event["participants"]:
            name = normalize(participant["surface"])
            if participant["named"] and name not in GENERIC_NAMES and len(name) >= 3:
                names.add(name)
                roles.update(role["role"] + ":" + name for role in participant["roles"])
        for fact in event["facts"]:
            value = normalize(fact["value"]["surface"])
            if len(value) >= 3:
                facts.add(value)
                wording.update(tokens(value))
        if event["time"]:
            times.add(normalize(event["time"]["surface"]))
    wording.update(actions)
    return Features(card["article_id"], card["corpus"], publication_day(card.get("published_at")),
        frozenset(names), frozenset(roles), frozenset(actions), frozenset(wording),
        frozenset(facts), tuple(sorted(set(summaries))), frozenset(times), len(records))


@dataclass(frozen=True, slots=True)
class Settings:
    top_k: int = 20
    keys_per_article: int = 8
    posting_cap: int = 48
    word_keys: int = 3
    minimum_score: float = 0.18

    def validate(self) -> None:
        if not (1 <= self.top_k <= 50 and 1 <= self.keys_per_article <= 12
                and 4 <= self.posting_cap <= 128 and 0 <= self.word_keys <= 4
                and 0 <= self.minimum_score <= 1):
            raise ResearchError("scalable_retrieval_bounds_invalid")


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    shared = len(a & b)
    return shared / (len(a) + len(b) - shared) if a or b else 0.0


def pair_features(a: Features, b: Features, idf: dict[str, float] | None = None) -> dict[str, Any]:
    if a.article_id == b.article_id or a.corpus != b.corpus:
        raise ResearchError("invalid_scalable_pair")
    named = a.names & b.names
    facts = a.facts & b.facts
    words = a.wording & b.wording
    union = a.wording | b.wording
    if idf:
        lexical = sum(idf.get(w, 1.0) for w in words) / max(1.0, sum(idf.get(w, 1.0) for w in union))
    else:
        lexical = jaccard(a.wording, b.wording)
    gap = abs(a.day - b.day) if a.day is not None and b.day is not None else None
    action = jaccard(a.actions, b.actions)
    name = jaccard(a.names, b.names)
    fact = jaccard(a.facts, b.facts)
    # A rank score, not a probability. Publication distance is a small bonus,
    # never a hard event-date contradiction or evidence of a distinct event.
    score = .35 * lexical + .30 * name + .20 * action + .10 * fact
    score += .05 if gap is not None and gap <= 7 else 0
    return {"score": round(score, 8), "lexical": round(lexical, 8), "name": round(name, 8),
        "action": round(action, 8), "fact": round(fact, 8), "publication_gap_days": gap,
        "shared_names": len(named), "shared_roles": len(a.roles & b.roles),
        "shared_facts": len(facts), "shared_words": len(words),
        "identical_summary": bool(set(a.summaries) & set(b.summaries)),
        "single_variant": a.variants == b.variants == 1,
        "same_literal_event_time": bool(a.event_times & b.event_times)}


class Index:
    """Inverted postings sorted once; bounded slices, never dense pair products.

    Memory O(N*F), index build O(N*F log N), at most Kkeys*posting_cap
    scored candidates per article, and at most top_k emitted directed links.
    Feature size F is bounded by the extraction schema and packet limits.
    """
    def __init__(self, rows: Iterable[Features], settings: Settings = Settings()):
        settings.validate()
        self.settings = settings
        self.rows = sorted(rows, key=lambda f: f.article_id)
        self.by_id = {f.article_id: i for i, f in enumerate(self.rows)}
        if len(self.by_id) != len(self.rows):
            raise ResearchError("duplicate_scalable_article")
        self.postings: dict[tuple[str, str], list[tuple[int, str, int]]] = defaultdict(list)
        self.keys: list[list[str]] = []
        df: dict[str, Counter[str]] = defaultdict(Counter)
        counts = Counter(f.corpus for f in self.rows)
        for i, row in enumerate(self.rows):
            keys = ["n:" + n for n in sorted(row.names)] + ["f:" + n for n in sorted(row.facts)]
            keys += ["w:" + w for w in sorted(row.wording)]
            self.keys.append(keys)
            for key in keys:
                self.postings[(row.corpus, key)].append((row.day or 0, row.article_id, i))
            df[row.corpus].update(row.wording)
        for members in self.postings.values():
            members.sort()
        self.idf = {c: {w: math.log1p(counts[c] / n) for w, n in values.items()} for c, values in df.items()}

    def query(self, identifier: str) -> dict[str, Any]:
        i = self.by_id[identifier]
        row, cfg = self.rows[i], self.settings
        keys = self.keys[i]
        def rank(key):
            return len(self.postings[(row.corpus, key)]), key
        strong = sorted((k for k in keys if not k.startswith("w:") and len(self.postings[(row.corpus, k)]) > 1), key=rank)
        words = sorted((k for k in keys if k.startswith("w:") and len(self.postings[(row.corpus, k)]) > 1), key=rank)[:cfg.word_keys]
        selected = (strong[:cfg.keys_per_article - cfg.word_keys] + words)[:cfg.keys_per_article]
        limited_keys = len(strong) > cfg.keys_per_article - cfg.word_keys
        candidates, capped = set(), 0
        touched = 0
        for key in selected:
            members = self.postings[(row.corpus, key)]
            if len(members) > cfg.posting_cap:
                capped += 1
                center = bisect_left(members, (row.day or 0, row.article_id, i))
                start = max(0, min(center - cfg.posting_cap // 2, len(members) - cfg.posting_cap))
                members = members[start:start + cfg.posting_cap]
            touched += len(members)
            candidates.update(item[2] for item in members if item[2] != i)
        scored = []
        for other in sorted(candidates):
            detail = pair_features(row, self.rows[other], self.idf[row.corpus])
            useful = detail["shared_names"] > 0 or (detail["shared_facts"] > 0 and detail["shared_words"] >= 3)
            # Lexical rescue can recover missing/variant named entities; broad
            # single-token overlap and character fragments never qualify alone.
            useful |= detail["lexical"] >= .30 and detail["shared_words"] >= 4
            if useful and detail["score"] >= cfg.minimum_score:
                scored.append((detail["score"], self.rows[other].article_id, detail))
        ordered = sorted(scored, key=lambda x: (-x[0], x[1]))[:cfg.top_k]
        return {"article_id": identifier, "corpus": row.corpus,
            "neighbors": [{"article_id": other, **detail} for _, other, detail in ordered],
            "candidates_scored": len(candidates), "postings_touched": touched,
            "capped_postings": capped, "capped_strong_keys": limited_keys,
            "retrieval_incomplete": bool(capped or limited_keys), "no_candidate": not ordered}

    def query_all(self) -> Iterator[dict[str, Any]]:
        for row in self.rows:
            yield self.query(row.article_id)


def rule_label(values: dict[str, Any], threshold: float = .62) -> str:
    """An exploratory rule: abstains, never infers 'different' from non-match."""
    gap = values["publication_gap_days"]
    anchors = values["shared_names"] >= 1 and (values["shared_facts"] >= 1 or values["shared_names"] >= 2)
    if (values["single_variant"] and anchors and values["action"] >= .10
            and gap is not None and gap <= 14 and values["score"] >= threshold):
        return "same_event"
    return "unresolved"


def pair_id(corpus: str, left: str, right: str) -> str:
    if left == right:
        raise ResearchError("self_pair_forbidden")
    return digest([METHOD, corpus, *sorted((left, right))])


def complete_link_groups(ids: Iterable[str], decisions: Iterable[dict[str, Any]], *, max_size: int = 50,
                         verification_cap: int = 1000) -> dict[str, Any]:
    """Merge only fully observed positive cliques; queue missing links with a cap.

    Unknown, negative and absent links never become positive by transitivity.
    Caller separates corpora. Queue exhaustion leaves explicit incomplete groups.
    """
    if not 2 <= max_size <= 50 or verification_cap < 0:
        raise ResearchError("group_resource_bounds_invalid")
    members = {i: {i} for i in ids}
    owner = {i: i for i in members}
    labels, scores = {}, {}
    for row in decisions:
        a, b = sorted((row["left"], row["right"]))
        if a not in owner or b not in owner or a == b:
            raise ResearchError("group_pair_identity_invalid")
        key = (a, b)
        if key in labels and labels[key] != row["label"]:
            raise ResearchError("conflicting_pair_decisions")
        labels[key] = row["label"]
        scores[key] = row.get("score", 1.0)
    queue, blocked, oversize, cap_hit = set(), 0, 0, False
    for a, b in sorted((p for p in labels if labels[p] == "same_event"), key=lambda p: (-scores[p], p)):
        x, y = owner[a], owner[b]
        if x == y:
            continue
        if len(members[x]) + len(members[y]) > max_size:
            oversize += 1
            continue
        cross = [tuple(sorted((i, j))) for i in sorted(members[x]) for j in sorted(members[y])]
        if any(labels.get(p) not in {None, "same_event"} for p in cross):
            blocked += 1
            continue
        missing = [p for p in cross if p not in labels]
        if missing:
            for p in missing:
                if p not in queue and len(queue) >= verification_cap:
                    cap_hit = True
                elif len(queue) < verification_cap:
                    queue.add(p)
            continue
        keep, drop = sorted((x, y))
        members[keep].update(members.pop(drop))
        for i in members[keep]:
            owner[i] = keep
    return {"groups": [sorted(v) for _, v in sorted(members.items())],
        "verification_queue": [list(p) for p in sorted(queue)], "blocked_merges": blocked,
        "oversize_merges": oversize, "verification_cap_hit": cap_hit,
        "accepted_findings": False}


def settings_dict(settings: Settings) -> dict[str, Any]:
    return asdict(settings)


def write_candidates(index: Index, path: Path, progress=None) -> dict[str, Any]:
    """Stream canonical pairs to a new SQLite file in the caller's private store."""
    if path.exists():
        raise ResearchError("candidate_file_exists_no_overwrite")
    db = sqlite3.connect(path)
    started = time.perf_counter()
    totals: Counter[str] = Counter()
    try:
        db.executescript("""
        CREATE TABLE pairs(corpus TEXT NOT NULL,left_id TEXT NOT NULL,right_id TEXT NOT NULL,
            score REAL NOT NULL,best_rank INTEGER NOT NULL,features TEXT NOT NULL,
            PRIMARY KEY(corpus,left_id,right_id)) WITHOUT ROWID;
        CREATE TABLE anchors(article_id TEXT PRIMARY KEY,corpus TEXT NOT NULL,
            neighbors INTEGER NOT NULL,scored INTEGER NOT NULL,touched INTEGER NOT NULL,
            capped_postings INTEGER NOT NULL,capped_keys INTEGER NOT NULL,incomplete INTEGER NOT NULL);
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)
        db.execute("INSERT INTO metadata VALUES('settings',?)", (json.dumps(settings_dict(index.settings), sort_keys=True),))
        for count, result in enumerate(index.query_all(), 1):
            db.execute("INSERT INTO anchors VALUES(?,?,?,?,?,?,?,?)", (
                result["article_id"], result["corpus"], len(result["neighbors"]),
                result["candidates_scored"], result["postings_touched"],
                result["capped_postings"], int(result["capped_strong_keys"]), int(result["retrieval_incomplete"])))
            rows = []
            for rank, neighbor in enumerate(result["neighbors"], 1):
                a, b = sorted((result["article_id"], neighbor["article_id"]))
                values = {k: v for k, v in neighbor.items() if k != "article_id"}
                rows.append((result["corpus"], a, b, neighbor["score"], rank, json.dumps(values, sort_keys=True, separators=(",", ":"))))
            db.executemany("INSERT INTO pairs VALUES(?,?,?,?,?,?) ON CONFLICT(corpus,left_id,right_id) DO UPDATE SET best_rank=min(best_rank,excluded.best_rank)", rows)
            totals["articles"] += 1
            totals["directed_links"] += len(rows)
            totals["candidates_scored"] += result["candidates_scored"]
            totals["postings_touched"] += result["postings_touched"]
            totals["retrieval_incomplete"] += result["retrieval_incomplete"]
            totals["without_candidates"] += result["no_candidate"]
            if count % 1000 == 0:
                db.commit()
                if progress:
                    progress({"articles": count, "elapsed_seconds": round(time.perf_counter() - started, 2)})
        totals["unique_pairs"] = db.execute("SELECT count(*) FROM pairs").fetchone()[0]
        db.execute("INSERT INTO metadata VALUES('complete','true')")
        db.commit()
        return {**totals, "elapsed_seconds": time.perf_counter() - started,
            "maximum_scored_per_article": index.settings.keys_per_article * index.settings.posting_cap,
            "maximum_directed_links": len(index.rows) * index.settings.top_k,
            "file_bytes": path.stat().st_size}
    finally:
        db.close()
