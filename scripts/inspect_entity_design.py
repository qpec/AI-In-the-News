"""Inspect frozen development source texts for codebook design; no model dispatch."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from newsresearch.common import Config, Context, Json, ResearchError, digest
from newsresearch.event_extraction_contract import validate_request
from newsresearch.runtime import Research, audited_handler

PLAN = "c532c7ce77af1ad916f17aaa15055132d16fb52ae635488d0c4f300bb1a68bce"
OWNER = "luna-seven-day-validation-20261016-v1"
METHOD = "development-article-codebook-inspection-v1"
RESULT = "58d95bf1b7d390d250010b7f2ce120577ff1be0a135facfe5e6b4650ba86278d"


def render(articles: list[Json]) -> str:
    lines = ["**Executed source inspection for codebook design.**", "",
             "Scope: the existing 12-article development selection, not a representative corpus sample. "
             "Sealed validation bodies were excluded in its original preparation. This reads original "
             "articles, not rejected model proposals. No new model calls, embeddings, labels or membership changes.", ""]
    for index, article in enumerate(articles, 1):
        lines += [f"### {index}. {article.get('title')}", f"Source URL: {article.get('url')}",
                  f"Source version: {article['source_version']}; publication: {article.get('published_at')}",
                  f"Full retained body: {len(article['body'])} characters; {len(article['passages'])} passages.", ""]
        for ordinal, passage in enumerate(article["passages"], 1):
            lines += [f"[{ordinal}; {passage['id']}; {passage['start']}:{passage['end']}]", passage["text"], ""]
    lines += ["Coverage: 12/12 full-text packets and every supplied passage returned; zero missing, failed or pending "
              "inspection slots. Returning text does not attest human reading. No entity or event frequency was estimated. "
              "This exact overview is a protected artifact; record_presentation does not support this inspection-note kind."]
    return "\n".join(lines) + "\n"


class DesignInspectionResearch(Research):
    def __init__(self, workspace: Path, *, config: Config | None = None) -> None:
        if workspace.name != OWNER or (config is not None and not config.offline):
            raise ResearchError("entity_inspection_original_offline_owner_required")
        super().__init__(workspace, config=config or Config(offline=True))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if data == {"replay": RESULT}:
            self.ledger.append(session, "entity.design.presentation_replay.intended", {"note": RESULT})
            result = self.ledger.get(RESULT, "note")["content"]
            # This re-presents retained evidence, without a new sample or inference.
            lines = ["Existing development inspection: articles 3–8, compact full-body replay.",
                     "All six retained bodies are shown below; no new model calls or labels."]
            for index, article in enumerate(result["articles"][2:8], 3):
                lines += [f"### {index}. {article.get('title')}", f"Source URL: {article.get('url')}",
                          f"Source version: {article['source_version']}", article["body"], ""]
            markdown = "\n".join(lines)
            artifact = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
            self.ledger.append(session, "entity.design.presentation_replay.prepared", {
                "note": RESULT, "artifact": artifact, "delivery_observed": False,
                "record_presentation_supported": False})
            return {"id": RESULT, "markdown_artifact": artifact, "markdown": markdown}
        if data != {"plan": PLAN}:
            raise ResearchError("entity_inspection_frozen_plan_required")
        definitions = {
            "protocol": {"method": METHOD, "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         "procedure": "Read only exact original full-source request packets of the fixed development plan; validate source/quote/coverage contract; inspect original stable passages through core runtime. No model dispatch, label reading, retries, event adoption or provider-source collection."},
            "selection": {"rules": "All 12 original frozen development plan slots, no reselection or label-based choices; not representative prevalence.", "plan": PLAN},
            "question": {"text": "Which original article wording should inform the next entity codebook and compact event-identity output design?"},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }
        key = digest(definitions)
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD + "-" + key, "content": value})["id"]
                    for kind, value in definitions.items()}
        self.ledger.append(session, "entity.design.plan_read.intended", {"plan": PLAN, "versions": versions})
        plan = self.ledger.get(PLAN, "luna_group_validation_plan")
        if (plan.get("method") != "saved-text-event-extraction-v1" or len(plan["tasks"]) != 12
                or Path(plan["owner_workspace"]).resolve() != self.ledger.root.resolve()):
            raise ResearchError("entity_inspection_plan_mismatch")
        articles = []
        examples = {row["source_version"]: row for row in plan["examples"]}
        for task in plan["tasks"]:
            self.ledger.append(session, "entity.design.source_read.intended", {
                "source": task["source_version"], "packet": task["request"], "versions": versions})
            request = self.ledger.artifacts.read(task["request"])
            validate_request(request)
            if request["source"]["source_version"] != task["source_version"] or request["versions"] != plan["versions"]:
                raise ResearchError("entity_inspection_source_binding_mismatch")
            inspected = self._inspect(session, Context(context.objective, context.actor, {
                **plan["versions"], "protocol": versions["protocol"]}),
                {"passage_ids": [row["id"] for row in request["evidence"]]})
            identity_fields = ("id", "source_id", "start", "end", "text", "text_hash")
            if ([tuple(row[field] for field in identity_fields) for row in inspected["passages"]]
                    != [tuple(row[field] for field in identity_fields) for row in request["evidence"]]):
                raise ResearchError("entity_inspection_original_passage_mismatch")
            articles.append({**request["source"], "url": examples[task["source_version"]].get("url"),
                             "body": request["body"], "passages": request["evidence"], "inspection": inspected["id"]})
        markdown = render(articles)
        artifact = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
        result = {"method": METHOD, "plan": PLAN, "versions": versions, "articles": articles,
                  "article_count": len(articles), "passage_count": sum(len(row["passages"]) for row in articles),
                  "markdown_artifact": artifact, "model_calls": 0, "new_labels": 0,
                  "record_presentation_supported": False, "delivery_observed": False}
        identifier = self._version(session, Context(context.objective, context.actor, versions),
                                   {"kind": "note", "key": METHOD + "-result-" + key, "content": result})["id"]
        return {"id": identifier, **result, "markdown": markdown}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = DesignInspectionResearch(args.workspace)
    try:
        result = engine.execute("status", {"replay": RESULT} if args.replay else {"plan": PLAN}, objective="Inspect actual saved development articles before revising event entity codebook", actor="codex:entity-codebook-design")
        print(result["markdown"])
        print(json.dumps({"note": result["id"], "report": str(engine.ledger.artifacts.root / result["markdown_artifact"])}))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
