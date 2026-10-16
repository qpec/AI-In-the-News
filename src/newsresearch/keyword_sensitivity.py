"""Exploratory, registered sensitivity calculations over immutable retrieval records."""
from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

from .common import Context, Json, ResearchError, digest, require_active, utc
from .keyword_study import TERMS

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-keyword-sensitivity-v1"


def calculate(results: list[Json]) -> Json:
    strata: dict[tuple[str, int], dict[str, set[str]]] = {}
    capped = set()
    records = {}
    caps = {term: 0 for term in [*TERMS, "control"]}
    for result in results:
        if result["status"] != "completed":
            continue
        query = result["query"]
        key = query["domain"], query["period"]
        strata.setdefault(key, {})[query["term"]] = {item["identity"] for item in result["items"]}
        records.update({item["identity"]: item for item in result["items"]})
        if result["possibly_capped"]:
            capped.add(key)
            caps[query["term"]] += 1
    strata = {key: pools for key, pools in strata.items() if set(pools) == set([*TERMS, "control"])}
    train = {key: pools for key, pools in strata.items() if key[1] < 5}
    test = {key: pools for key, pools in strata.items() if key[1] == 5}
    def coverage(terms: tuple[str, ...], selected: dict[tuple[str, int], dict[str, set[str]]]) -> Json:
        found = reference = 0
        for pools in selected.values():
            reference += len(set().union(*pools.values()))
            found += len(set().union(*(pools[term] for term in terms)))
        return {"found": found, "reference": reference,
                "fraction": found/reference if reference else None, "strata": len(selected)}
    subsets = []
    for size in range(1, 11):
        _, best = max((coverage(terms, train)["found"], terms) for terms in combinations(TERMS, size))
        subsets.append({"size": size, "terms": list(best), "train": coverage(best, train),
                        "heldout": coverage(best, test),
                        "uncapped_train": coverage(best, {k: p for k, p in train.items() if k not in capped}),
                        "uncapped_heldout": coverage(best, {k: p for k, p in test.items() if k not in capped})})
    candidates = {
        "original_five": ("hack", "gehackt", "ransomware", "datalek", "cyberaanval"),
        "four_families_eight_forms": tuple(t for t in TERMS if t not in {"gijzelsoftware", "datadiefstal"}),
        "all_ten": tuple(TERMS),
    }
    comparisons = {key: {"terms": list(terms), "train": coverage(terms, train), "heldout": coverage(terms, test),
        "all": coverage(terms, strata), "uncapped": coverage(terms, {k: p for k, p in strata.items() if k not in capped}),
        "by_publisher": {domain: coverage(terms, {k: p for k, p in strata.items() if k[0] == domain})
                         for domain in sorted({k[0] for k in strata})}} for key, terms in candidates.items()}
    all_pools = {t: set().union(*(p[t] for p in strata.values())) if strata else set() for t in TERMS}
    pairs = []
    for base, variant in [("hack", "gehackt"), ("hack", "hackers"), ("datalek", "datalekken"),
                          ("cyberaanval", "cyberaanvallen"), ("ransomware", "gijzelsoftware")]:
        pairs.append({"base": base, "variant": variant, "variant_records": len(all_pools[variant]),
                      "also_found_by_base": len(all_pools[variant] & all_pools[base]),
                      "additional_vs_base": len(all_pools[variant]-all_pools[base])})
    title_counts = {term: sum(term in set(item["title_words"]) for item in records.values()) for term in TERMS}
    return {"comparisons": comparisons, "subsets": subsets, "variant_pairs": pairs,
            "title_counts": title_counts, "title_denominator": len(records), "caps_by_term": caps,
            "complete_strata": len(strata), "uncapped_strata": len(set(strata)-capped),
            "title_publisher_denominator": len({item["title_publisher_identity"] for item in records.values()}),
            "inference": "Deterministic exploratory retrieval diagnostics; no relevance/event inference or gold labels"}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"retrieval_profile"})
    profile = engine.ledger.get(context.versions["retrieval_profile"], "retrieval_profile")["content"]
    if profile.get("method") != METHOD:
        raise ResearchError("Register the exact sensitivity method first")
    original = engine.ledger.get(data["result"], "keyword_study")
    if original["pending"] or original["unknown"]:
        raise ResearchError("Finish or explicitly resolve incomplete collection before sensitivity calculation")
    if original["versions"] != {k: v for k, v in context.versions.items() if k != "retrieval_profile"}:
        raise ResearchError("Sensitivity must bind original collection versions exactly")
    inputs = [engine.ledger.get(identifier, "keyword_query") for identifier in original["query_results"]]
    result = {**calculate(inputs), "source_run": data["result"], "query_results": original["query_results"],
              "versions": context.versions, "generated_at": utc(), "model_calls": 0, "network_calls": 0,
              "failed_queries": original["failed"], "scored": 0}
    identifier = engine.ledger.record(session, "keyword_study", digest(result), result)
    return {"id": identifier, **result}
