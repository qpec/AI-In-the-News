from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import sys

from .common import ResearchError, default_workspace
from .runtime import Research


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audited, offline-first research. Paid inference requires a plan-bound approval."
    )
    parser.add_argument(
        "--workspace", type=Path, default=default_workspace(), help="Protected storage outside Git"
    )
    parser.add_argument(
        "--objective", help="Required for research commands except the explicitly synthetic demo"
    )
    parser.add_argument(
        "--actor",
        default=getpass.getuser(),
        help="Identifiable local reviewer/operator; identity is self-asserted",
    )
    parser.add_argument("--versions", type=Path, help="JSON object of version IDs, or a saved demo context")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Run ingestion through source trace entirely offline")
    sub.add_parser(
        "heldout-demo", help="Synthetic held-out evaluation with intentional errors and missingness"
    )
    sub.add_parser("status", help="Audited preflight and workspace state")
    benchmark = sub.add_parser("benchmark", help="Synthetic article/dossier scale check; no model calls")
    benchmark.add_argument("--articles", type=int, default=20000)
    run = sub.add_parser("run", help="Run a registered research operation from JSON")
    run.add_argument(
        "operation",
        choices=[
            "version",
            "ingest",
            "import_newsapi",
            "collect",
            "dossiers",
            "propose_groups",
            "search",
            "inspect",
            "batch",
            "review",
            "review_queue",
            "measure",
            "chart",
            "trace",
            "replay",
            "export",
            "evaluate",
            "resolve_attempt",
            "verify_legacy",
            "prepare_legacy_pilot",
            "plan_embeddings",
            "embed",
            "build_vector_index",
            "scale_event_vector_store",
            "plan_catalog_embeddings",
            "index_catalog_embeddings",
            "vector_search",
            "evaluate_vector_index",
            "inspect_candidates",
            "tag_retrieve",
            "tag_setup",
            "similarity_setup",
            "similarity_score",
            "similarity_calibrate",
            "similarity_apply",
            "similarity_provisional_apply",
            "article_query_rows",
            "article_query_overview",
            "record_presentation",
            "adaptive_cutoff",
            "rag_query",
            "conversation",
            "conversation_search",
            "conversation_chat",
            "evaluate_aws_clustering",
            "evaluate_event_clustering",
            "plan_event_pairs",
            "event_pair_experiment",
            "event_pair_feature_experiment",
            "event_pair_conjunction_experiment",
            "event_pair_monotone_screen",
            "apply_event_rule",
            "refine_event_groups",
            "plan_tags",
            "tag",
            "tag_inspect",
            "tag_review_queue",
            "tag_review",
            "tag_calibrate",
            "tag_apply",
        ],
    )
    run.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    objective = args.objective
    if not objective:
        if args.command not in {"demo", "benchmark", "heldout-demo"}:
            parser.error("--objective is required; research sessions cannot have an implicit purpose")
        objective = {
            "demo": "Offline synthetic software demonstration",
            "heldout-demo": "Held-out synthetic software evaluation",
            "benchmark": "Synthetic scaling check of the dossier foundation",
        }[args.command]
    versions = {}
    if args.versions:
        supplied = json.loads(args.versions.read_text(encoding="utf-8-sig"))
        versions = supplied.get("versions", supplied)
    operation = args.operation if args.command == "run" else args.command.replace("-", "_")
    payload = json.loads(args.input.read_text(encoding="utf-8-sig")) if args.command == "run" else {}
    if args.command == "benchmark":
        payload = {"articles": args.articles}
    engine = None
    try:
        engine = Research(args.workspace)
        result = engine.execute(operation, payload, objective=objective, actor=args.actor, versions=versions)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (ResearchError, OSError, ValueError, KeyError) as error:
        print(f"Research operation blocked or failed ({type(error).__name__}): {error}", file=sys.stderr)
        return 1
    finally:
        if engine:
            engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
