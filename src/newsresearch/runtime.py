from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from functools import wraps
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import uuid
from typing import Any, Callable

from .common import (
    AuditError,
    Config,
    Context,
    Json,
    ResearchError,
    canonical,
    digest,
    require_no_credentials,
)
from .storage import Ledger

VERSION_KINDS = {
    "protocol",
    "question",
    "selection",
    "dossier_definition",
    "codebook",
    "prompt",
    "profile",
    "policy",
    "exclusion",
    "note",
    "export_policy",
    "evaluation",
    "embedding_profile",
    "retrieval_profile",
    "model_profile",
}
FULL_BINDINGS = {
    "dataset",
    "dossiers",
    "protocol",
    "question",
    "selection",
    "dossier_definition",
    "codebook",
    "prompt",
    "profile",
}


def audited_handler(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def checked(engine: Research, session: str, *args: Any, **kwargs: Any) -> Any:
        from .common import require_active

        require_active(engine, session)
        return function(engine, session, *args, **kwargs)

    return checked


class Research:
    """All supported research operations, including reads, enter through execute."""

    def __init__(self, workspace: Path, project: Path | None = None, config: Config | None = None) -> None:
        self.project = (project or Path(__file__).resolve().parents[2]).resolve()
        self.config = config or Config.load(self.project / "research.toml")
        self.ledger = Ledger(workspace)
        self._active: set[str] = set()
        from .gateway import Gateway, MockProvider

        self.gateway = Gateway(self, MockProvider())

    def close(self) -> None:
        self.ledger.close()

    def identity(self) -> Json:
        candidates = [
            *self.project.glob("src/**/*.py"),
            *self.project.glob("docs/*.md"),
            *self.project.glob(".agents/skills/**/*.md"),
            *self.project.glob(".codex/*.toml"),
            self.project / "AGENTS.md",
            self.project / "uv.lock",
            self.project / "pyproject.toml",
            self.project / "research.toml",
        ]
        files = {
            p.relative_to(self.project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in candidates
            if p.is_file()
        }
        result = subprocess.run(
            ["git", "-C", str(self.project), "rev-parse", "HEAD"], capture_output=True, text=True
        )
        return {
            "git_head": result.stdout.strip() if result.returncode == 0 else None,
            "code_files": files,
            "code_digest": digest(files),
            "python": sys.version,
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
            "packages": {name: importlib.metadata.version(name) for name in
                         ["jsonschema", "matplotlib", "numpy", "faiss-cpu"]},
        }

    def execute(
        self,
        operation: str,
        payload: Json | None = None,
        *,
        objective: str,
        actor: str,
        versions: dict[str, str] | None = None,
    ) -> Any:
        context = Context(objective, actor, dict(versions or {}))
        context.validate()
        content = payload or {}
        require_no_credentials(content)
        preflight = self.ledger.verify()
        handlers = {
            "version": self._version,
            "ingest": self._ingest,
            "dossiers": self._dossiers,
            "search": self._search,
            "inspect": self._inspect,
            "batch": self._batch,
            "review": self._review,
            "measure": self._measure,
            "chart": self._chart,
            "trace": self._trace,
            "replay": self._replay,
            "export": self._export,
            "status": self._status,
            "clone_workspace": self._clone_workspace,
            "collect": self._collect,
            "newsapi_probe": self._newsapi_probe,
            "newsapi_collection": self._newsapi_collection,
            "keyword_study": self._keyword_study,
            "newsapi_overview": self._newsapi_overview,
            "hook": self._hook,
            "evaluate": self._evaluate,
            "review_queue": self._review_queue,
            "resolve_attempt": self._resolve_attempt,
            "import_newsapi": self._import_newsapi,
            "demo": self._demo,
            "benchmark": self._benchmark,
            "heldout_demo": self._heldout_demo,
            "propose_groups": self._propose_groups,
            "verify_legacy": self._verify_legacy,
            "prepare_legacy_pilot": self._prepare_legacy_pilot,
            "plan_embeddings": self._plan_embeddings,
            "embed": self._embed,
            "build_vector_index": self._build_vector_index,
            "vector_search": self._vector_search,
            "evaluate_vector_index": self._evaluate_vector_index,
            "inspect_candidates": self._inspect_candidates,
            "tag_retrieve": self._tag_retrieve,
            "tag_setup": self._tag_setup,
            "similarity_setup": self._similarity_setup,
            "similarity_score": self._similarity_score,
            "similarity_calibrate": self._similarity_calibrate,
            "similarity_apply": self._similarity_apply,
            "similarity_provisional_apply": self._similarity_provisional_apply,
            "article_query_rows": self._article_query_rows,
            "article_query_overview": self._article_query_overview,
            "record_presentation": self._record_presentation,
            "adaptive_cutoff": self._adaptive_cutoff,
            "rag_query": self._rag_query,
            "conversation": self._conversation,
            "conversation_search": self._conversation_search,
            "conversation_chat": self._conversation_chat,
            "evaluate_aws_clustering": self._evaluate_aws_clustering,
            "evaluate_event_clustering": self._evaluate_event_clustering,
            "plan_event_pairs": self._plan_event_pairs,
            "event_pair_experiment": self._event_pair_experiment,
            "event_pair_feature_experiment": self._event_pair_feature_experiment,
            "event_pair_conjunction_experiment": self._event_pair_conjunction_experiment,
            "event_pair_monotone_screen": self._event_pair_monotone_screen,
            "apply_event_rule": self._apply_event_rule,
            "refine_event_groups": self._refine_event_groups,
            "check_event_time_spans": self._check_event_time_spans,
            "compare_event_group_windows": self._compare_event_group_windows,
            "propose_cross_window_group_links": self._propose_cross_window_group_links,
            "prepare_cross_window_event_review": self._prepare_cross_window_event_review,
            "judge_cross_window_event_review": self._judge_cross_window_event_review,
            "test_collective_group_vectors": self._test_collective_group_vectors,
            "scale_event_vector_store": self._scale_event_vector_store,
            "plan_catalog_embeddings": self._plan_catalog_embeddings,
            "index_catalog_embeddings": self._index_catalog_embeddings,
            "luna_group_validation": self._luna_group_validation,
            "luna_group_validation_continue": self._luna_group_validation_continue,
            "luna_study_export": self._luna_study_export,
            "luna_study_import": self._luna_study_import,
            "plan_tags": self._plan_tags,
            "tag": self._tag,
            "tag_inspect": self._tag_inspect,
            "tag_review_queue": self._tag_review_queue,
            "tag_review": self._tag_review,
            "tag_calibrate": self._tag_calibrate,
            "tag_apply": self._tag_apply,
        }
        if operation not in handlers:
            raise ResearchError("Unsupported research operation")
        for kind, reference in context.versions.items():
            self.ledger.get(reference, kind)
        if {"dataset", "dossiers"} <= context.versions.keys():
            if (
                self.ledger.get(context.versions["dossiers"], "dossiers")["versions"]["dataset"]
                != context.versions["dataset"]
            ):
                raise ResearchError("Dossier version belongs to another dataset")
        session = str(uuid.uuid4())
        identity = self.ledger.artifacts.put(self.identity())
        self.ledger.append(
            session,
            "session.started",
            {
                "context": asdict(context),
                "identity": identity,
                "configuration": self.config.payload(),
                "preflight": preflight,
                "actor_assurance": "self-asserted local operator",
            },
        )
        self._active.add(session)
        try:
            if operation == "ingest" and any(
                item.get("retention") == "metadata_only" and (item.get("body") or item.get("raw_record"))
                for item in content.get("articles", [])
            ):
                raise ResearchError("Metadata-only retention forbids storing a body/raw record")
            request = self.ledger.artifacts.put(content)
            self.ledger.append(session, "operation.intended", {"operation": operation, "input": request})
            from .study_ownership import enforce

            enforce(self, session, operation, content)
            result = handlers[operation](session, context, content)
            result_ref = self.ledger.artifacts.put(result)
            self.ledger.append(session, "operation.completed", {"operation": operation, "result": result_ref})
            self.ledger.append(session, "session.ended", {"status": "completed"})
            return result
        except Exception as error:
            # Exception messages may contain provider bodies or credentials; store only observable type.
            self.ledger.append(
                session, "operation.failed", {"operation": operation, "error_type": type(error).__name__}
            )
            raise
        finally:
            self._active.discard(session)

    def _require(self, context: Context, kinds: set[str]) -> None:
        missing = kinds - context.versions.keys()
        if missing:
            raise ResearchError(f"Required version bindings missing: {sorted(missing)}")

    @audited_handler
    def _version(self, session: str, context: Context, data: Json) -> Json:
        kind = data["kind"]
        if kind not in VERSION_KINDS or not data.get("key") or not isinstance(data.get("content"), dict):
            raise ResearchError("A version needs a supported kind, key and object content")
        required_fields = {
            "protocol": "method",
            "question": "text",
            "selection": "rules",
            "dossier_definition": "unit",
            "prompt": "instructions",
            "profile": "mode",
            "embedding_profile": "model",
            "retrieval_profile": "method",
        }
        if kind in required_fields and not data["content"].get(required_fields[kind]):
            raise ResearchError("Versioned research methods cannot be empty")
        if kind == "profile" and data["content"]["mode"] not in {"exploratory", "systematic"}:
            raise ResearchError("Profile mode must distinguish exploration from systematic measurement")
        parent = data.get("supersedes")
        if data.get("amend_latest"):
            if parent or not data.get("reason"):
                raise ResearchError("Automatic amendment needs a reason and no explicit parent")
            latest = self.ledger.db.execute(
                "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1",
                (kind, data["key"]),
            ).fetchone()
            if latest:
                previous = self.ledger.get(latest[0], kind)
                if previous["content"] == data["content"] and previous["branch"] == data.get(
                    "branch", "main"
                ):
                    self.ledger.append(session, "record.reused", {"record": latest[0]})
                    return {"id": latest[0], "kind": kind}
                parent = latest[0]
        if parent:
            self.ledger.get(parent, kind)
            if not data.get("reason"):
                raise ResearchError("Amendments need a recorded reason")
        if kind == "codebook":
            labels = data["content"].get("labels", [])
            if "missing" in labels:
                raise ResearchError("The label missing is reserved for processing state, not a finding")
            if (
                not labels
                or len(labels) != len(set(labels))
                or any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", x) for x in labels)
            ):
                raise ResearchError("Codebook labels must be distinct controlled identifiers")
        body = {
            "content": data["content"],
            "registered_by": context.actor,
            "reason": data.get("reason"),
            "branch": data.get("branch", "main"),
        }
        return {"id": self.ledger.record(session, kind, data["key"], body, parent), "kind": kind}

    @audited_handler
    def _ingest(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, {"protocol", "selection"})
        articles = data["articles"]
        if not isinstance(articles, list) or not 0 < len(articles) <= self.config.max_articles:
            raise ResearchError("Article count exceeds the registered working limit")
        retrieval = data.get("retrieval", {})
        if not retrieval.get("source") or "retrieved_at" not in retrieval or "parameters" not in retrieval:
            raise ResearchError("Retrieval source, timestamp state and parameters are required")
        if retrieval["retrieved_at"] is None:
            protocol = self.ledger.get(context.versions["protocol"], "protocol")["content"]
            reason = retrieval.get("unavailable_reason")
            if not reason or reason != protocol.get("unavailable_retrieval_reason"):
                raise ResearchError(
                    "Unknown historical retrieval requires a matching registered protocol reason"
                )
        elif datetime.fromisoformat(retrieval["retrieved_at"].replace("Z", "+00:00")).tzinfo is None:
            raise ResearchError("Retrieval timestamps require an explicit timezone")
        normalized: list[Json] = []
        for article in articles:
            if article.get("retention") not in {"permitted", "metadata_only"} or not article.get(
                "source_key"
            ):
                raise ResearchError("Each source needs an identifier and explicit retention permission")
            if article["retention"] == "metadata_only" and (article.get("body") or article.get("raw_record")):
                raise ResearchError("Restricted retention forbids persisting source body/raw record")
            body = article.get("body", "")
            if not isinstance(body, str):
                raise ResearchError("Source body must be text")
            normalized.append({**article, "body": body, "retrieval": retrieval})
        raw_ref = self.ledger.artifacts.put(normalized)
        identifiers = [digest(item) for item in normalized]
        if len(identifiers) != len(set(identifiers)):
            raise ResearchError("Duplicate identical source versions in one import")

        def project(event: int) -> None:
            for index, (source_id, item) in enumerate(zip(identifiers, normalized, strict=True)):
                if self.ledger.db.execute("SELECT 1 FROM sources WHERE id=?", (source_id,)).fetchone():
                    continue
                self.ledger.db.execute(
                    "INSERT INTO sources VALUES (?,?,?,?,?,?)",
                    (source_id, item["source_key"], canonical(item), raw_ref, index, event),
                )
                for match in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", item["body"]):
                    text = match.group()
                    text_hash = hashlib.sha256(text.encode()).hexdigest()
                    passage_id = digest(
                        {"source": source_id, "start": match.start(), "end": match.end(), "sha256": text_hash}
                    )
                    self.ledger.db.execute(
                        "INSERT INTO passages VALUES (?,?,?,?,?,?)",
                        (passage_id, source_id, match.start(), match.end(), text, text_hash),
                    )
                    self.ledger.db.execute("INSERT INTO passage_fts VALUES (?,?)", (passage_id, text))

        self.ledger.append(
            session,
            "sources.imported",
            {"raw_ref": raw_ref, "source_versions": identifiers, "versions": context.versions},
            project,
        )
        dataset = {
            "source_versions": identifiers,
            "retrieval": retrieval,
            "versions": context.versions,
            "synthetic": all(item.get("synthetic") is True for item in normalized),
        }
        version = self.ledger.record(
            session, "dataset", data.get("key", "dataset"), dataset, data.get("supersedes")
        )
        return {"id": version, "sources": identifiers, "articles": len(identifiers)}

    @audited_handler
    def _dossiers(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, {"dataset", "protocol", "dossier_definition"})
        dataset = self.ledger.get(context.versions["dataset"], "dataset")
        available = set(dataset["source_versions"])
        groups = data["dossiers"]
        identifiers = [group["id"] for group in groups]
        if len(identifiers) != len(set(identifiers)) or not groups:
            raise ResearchError("Dossier IDs must be unique and nonempty")
        confirmed: set[str] = set()
        for group in groups:
            if not group.get("members") or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", group["id"]):
                raise ResearchError("Each dossier needs a stable safe ID and members")
            local: set[str] = set()
            for member in group["members"]:
                source = member["source"]
                if (
                    source not in available
                    or source in local
                    or member.get("assignment") not in {"confirmed", "uncertain", "duplicate"}
                ):
                    raise ResearchError("Invalid, repeated or out-of-dataset dossier membership")
                local.add(source)
                if member["assignment"] != "uncertain":
                    if source in confirmed:
                        raise ResearchError("A source cannot be confirmed in two active dossiers")
                    confirmed.add(source)
        parent = data.get("supersedes")
        history = data.get("changes", [])
        if context.versions.get("dossiers") and not parent:
            raise ResearchError("An existing dossier frame requires explicit amendment lineage")
        if parent:
            previous = self.ledger.get(parent, "dossiers")
            old = {item["id"] for item in previous["dossiers"]}
            for change in history:
                if not change.get("reason") or change.get("action") not in {"merge", "split", "amend"}:
                    raise ResearchError("Dossier changes need a type and reason")
                if not set(change["from"]) <= old or not set(change["to"]) <= set(identifiers):
                    raise ResearchError("Dossier lineage references unavailable IDs")
                if change["action"] == "merge" and (len(change["from"]) < 2 or len(change["to"]) != 1):
                    raise ResearchError("A merge needs multiple parents and one successor")
                if change["action"] == "split" and (len(change["from"]) != 1 or len(change["to"]) < 2):
                    raise ResearchError("A split needs one parent and multiple successors")
            if not history:
                raise ResearchError("Dossier amendments must preserve change history")
            old_groups = {item["id"]: item for item in previous["dossiers"]}
            new_groups = {item["id"]: item for item in groups}
            changed_before = {key for key in old_groups if old_groups[key] != new_groups.get(key)}
            changed_after = {key for key in new_groups if new_groups[key] != old_groups.get(key)}
            covered_before = {key for change in history for key in change["from"]}
            covered_after = {key for change in history for key in change["to"]}
            if not changed_before <= covered_before or not changed_after <= covered_after:
                raise ResearchError("Dossier lineage must cover every changed or removed group")
        payload = {
            "dossiers": groups,
            "changes": history,
            "versions": context.versions,
            "reviewer": context.actor,
            "method": data.get("method", "manual grouping"),
            "proposed_by_assessment": data.get("proposed_by_assessment"),
        }
        return {"id": self.ledger.record(session, "dossiers", data.get("key", "dossiers"), payload, parent)}

    def _evidence(self, passage_id: str) -> Json:
        if not self._active:
            raise AuditError("Evidence inspection requires an active audited operation")
        row = self.ledger.db.execute("SELECT * FROM passages WHERE id=?", (passage_id,)).fetchone()
        if not row:
            raise ResearchError("Evidence reference does not exist")
        source = self.ledger.db.execute(
            "SELECT payload FROM sources WHERE id=?", (row["source_id"],)
        ).fetchone()
        body = json.loads(source[0])["body"]
        if body[row["start"] : row["end"]] != row["text"]:
            raise AuditError("Evidence passage no longer matches its source version")
        return dict(row)

    def _dossier_evidence(
        self, versions: dict[str, str], dossier_id: str, groups: dict[str, Json] | None = None
    ) -> list[Json]:
        if not self._active:
            raise AuditError("Evidence inspection requires an active audited operation")
        if groups is None:
            collection = self.ledger.get(versions["dossiers"], "dossiers")
            if collection["versions"]["dataset"] != versions["dataset"]:
                raise ResearchError("Dossier version belongs to another dataset")
            groups = {item["id"]: item for item in collection["dossiers"]}
        group = groups.get(dossier_id)
        if group is None:
            raise ResearchError("Unknown dossier ID")
        evidence: list[Json] = []
        for member in group["members"]:
            for row in self.ledger.db.execute(
                "SELECT id FROM passages WHERE source_id=? ORDER BY start", (member["source"],)
            ):
                evidence.append({**self._evidence(row[0]), "assignment": member["assignment"]})
        return evidence

    @audited_handler
    def _search(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, {"dataset", "dossiers", "question", "protocol", "profile"})
        groups = self.ledger.get(context.versions["dossiers"], "dossiers")["dossiers"]
        members: dict[str, list[str]] = {}
        for group in groups:
            for member in group["members"]:
                members.setdefault(member["source"], []).append(group["id"])
        limit = int(data.get("limit", 20))
        if not 1 <= limit <= 1000:
            raise ResearchError("Search limit must be between 1 and 1000")
        sql = "SELECT p.id,p.source_id FROM passage_fts f JOIN passages p ON p.id=f.id WHERE passage_fts MATCH ? AND p.source_id IN (SELECT value FROM json_each(?)) ORDER BY rank LIMIT ?"
        parameters = [data["query"], canonical(sorted(members)), limit]
        hits = [
            {"passage": self._evidence(row["id"]), "dossiers": members[row["source_id"]]}
            for row in self.ledger.db.execute(sql, parameters)
        ]
        result = {
            "query": data["query"],
            "sql": sql,
            "parameters": parameters,
            "hits": hits,
            "retrieved_dossiers": sorted({d for hit in hits for d in hit["dossiers"]}),
            "total_dossiers_in_snapshot": len(groups),
            "limit": limit,
            "scope": "exploratory retrieval; not a population count",
            "versions": context.versions,
            "inspection_observation": "passages returned to caller; human reading not observable",
        }
        return {"id": self.ledger.record(session, "search", str(uuid.uuid4()), result), **result}

    @audited_handler
    def _inspect(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, {"dataset", "protocol"})
        allowed = set(self.ledger.get(context.versions["dataset"], "dataset")["source_versions"])
        passages = [self._evidence(identifier) for identifier in data["passage_ids"]]
        if any(p["source_id"] not in allowed for p in passages):
            raise ResearchError("Inspection is outside the bound dataset")
        result = {"passages": passages, "observation": "returned to caller", "versions": context.versions}
        return {"id": self.ledger.record(session, "inspection", str(uuid.uuid4()), result), **result}

    @audited_handler
    def _batch(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, FULL_BINDINGS)
        return self.gateway.run(session, context, data)

    @audited_handler
    def _review(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, FULL_BINDINGS)
        return self.gateway.review(session, context, data)

    @audited_handler
    def _measure(self, session: str, context: Context, data: Json) -> Json:
        from .analysis import measure

        self._require(context, FULL_BINDINGS)
        return measure(self, session, context, data)

    @audited_handler
    def _chart(self, session: str, context: Context, data: Json) -> Json:
        from .analysis import chart

        self._require(context, FULL_BINDINGS)
        return chart(self, session, context, data)

    @audited_handler
    def _export(self, session: str, context: Context, data: Json) -> Json:
        from .analysis import export

        self._require(context, FULL_BINDINGS | {"export_policy"})
        return export(self, session, context, data)

    @audited_handler
    def _trace(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, FULL_BINDINGS)
        record = self.ledger.get(data["id"])
        if "versions" in record:
            from .analysis import compatible

            compatible(record, context)
        kind = self.ledger.db.execute("SELECT kind FROM records WHERE id=?", (data["id"],)).fetchone()[0]
        result: Json = {"id": data["id"], "kind": kind, "record": record}
        if kind == "chart":
            result["table"] = self.ledger.get(record["table"], "table")
        if kind == "table":
            result["accepted_findings"] = [
                self.ledger.get(row["acceptance"], "accepted") for row in record["rows"] if row["acceptance"]
            ]
        if kind == "accepted":
            result["assessment"] = self.ledger.get(record["assessment"], "assessment")
            result["evidence"] = [
                self._evidence(claim["passage_id"]) for claim in result["assessment"]["result"]["claims"]
            ]
            result["source_versions"] = [
                {
                    "id": evidence["source_id"],
                    "source": json.loads(
                        self.ledger.db.execute(
                            "SELECT payload FROM sources WHERE id=?", (evidence["source_id"],)
                        ).fetchone()[0]
                    ),
                }
                for evidence in result["evidence"]
            ]
            result["review"] = self.ledger.get(record["review"], "review")
        return result

    @audited_handler
    def _replay(self, session: str, context: Context, data: Json) -> Json:
        from .analysis import replay

        self._require(context, FULL_BINDINGS)
        return replay(self, session, context, data)

    @audited_handler
    def _evaluate(self, session: str, context: Context, data: Json) -> Json:
        from .analysis import evaluate

        self._require(context, FULL_BINDINGS | {"evaluation"})
        return evaluate(self, session, context, data)

    @audited_handler
    def _review_queue(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, FULL_BINDINGS)
        rows = []
        for row in self.ledger.db.execute("SELECT id,payload FROM records WHERE kind='assessment'"):
            item = json.loads(row["payload"])
            if item["versions"] == context.versions:
                accepted = self.ledger.db.execute(
                    "SELECT id FROM accepted WHERE assessment_id=?", (row["id"],)
                ).fetchone()
                if not accepted:
                    previous = self.ledger.db.execute(
                        "SELECT payload FROM records WHERE kind='review' AND json_extract(payload,'$.assessment')=? ORDER BY created_event DESC LIMIT 1",
                        (row["id"],),
                    ).fetchone()
                    decision = json.loads(previous[0])["decision"] if previous else "unreviewed"
                    if decision != "reject":
                        rows.append(
                            {
                                "assessment": row["id"],
                                "dossier_id": item["dossier_id"],
                                "provisional_label": item["result"]["label"],
                                "review_state": decision,
                            }
                        )
        return {
            "items": rows,
            "status": "pending human review; labels are provisional",
            "versions": context.versions,
        }

    @audited_handler
    def _newsapi_overview(self, session: str, context: Context, data: Json) -> Json:
        from .newsapi_probe import overview

        return overview(self, session, context, data)

    @audited_handler
    def _newsapi_probe(self, session: str, context: Context, data: Json) -> Json:
        from .newsapi_probe import probe

        return probe(self, session, context, data)

    @audited_handler
    def _keyword_study(self, session: str, context: Context, data: Json) -> Json:
        from .keyword_study import run

        return run(self, session, context, data)

    @audited_handler
    def _newsapi_collection(self, session: str, context: Context, data: Json) -> Json:
        from .newsapi_collection import run

        return run(self, session, context, data)

    @audited_handler
    def _collect(self, session: str, context: Context, data: Json) -> Json:
        raise ResearchError(
            "Live collection is disabled; import permitted stored responses with ingest. A live transport and run authorization are not installed."
        )

    @audited_handler
    def _clone_workspace(self, session: str, context: Context, data: Json) -> Json:
        from .workspace_clone import clone_workspace

        return clone_workspace(self, session, context, data)

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        return {
            "journal": self.ledger.verify(),
            "counts": {
                table: self.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ["sources", "passages", "records", "attempts", "accepted"]
            },
        }

    @audited_handler
    def _hook(self, session: str, context: Context, data: Json) -> Json:
        allowed = {
            key: data.get(key)
            for key in ["hook_event_name", "session_id", "turn_id", "tool_name", "tool_use_id", "model"]
        }
        self.ledger.append(
            session,
            "codex.observed",
            {"metadata": allowed, "scope": "lifecycle metadata only; no tool payload or hidden reasoning"},
        )
        return {"recorded": True, "scope": "supplementary lifecycle metadata"}

    @audited_handler
    def _resolve_attempt(self, session: str, context: Context, data: Json) -> Json:
        if data.get("attempt") not in self.ledger.unresolved or not data.get("reason"):
            raise ResearchError("Resolution needs an unresolved attempt and recorded rationale")
        self.ledger.append(
            session,
            "model.attempt.resolved",
            {
                "attempt": data["attempt"],
                "status": "unknown_outcome_abandoned",
                "reviewer": context.actor,
                "reason": data["reason"],
                "provider_outcome": "unknown; not a negative finding",
            },
        )
        return {"resolved": data["attempt"], "outcome": "unknown"}

    @audited_handler
    def _import_newsapi(self, session: str, context: Context, data: Json) -> Json:
        from .importers import import_newsapi

        self._require(context, {"protocol", "selection"})
        return import_newsapi(self, session, context, data)

    @audited_handler
    def _demo(self, session: str, context: Context, data: Json) -> Json:
        from .demo import demo

        return demo(self, context.actor)

    @audited_handler
    def _benchmark(self, session: str, context: Context, data: Json) -> Json:
        from .demo import benchmark

        return benchmark(self, context.actor, int(data.get("articles", 20000)))

    @audited_handler
    def _heldout_demo(self, session: str, context: Context, data: Json) -> Json:
        from .demo import heldout_demo

        return heldout_demo(self, context.actor)

    @audited_handler
    def _propose_groups(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, {"dataset", "protocol", "dossier_definition"})
        method = self.ledger.get(context.versions["dossier_definition"], "dossier_definition")["content"]
        if method.get("proposal_method") != "provider-event-uri-v1":
            raise ResearchError("Register the provider-event grouping method before execution")
        sources = self.ledger.get(context.versions["dataset"], "dataset")["source_versions"]
        candidates: dict[str, list[Json]] = {}
        for identifier in sources:
            source = json.loads(
                self.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (identifier,)).fetchone()[0]
            )
            event = source.get("raw_record", {}).get("eventUri")
            group_id = "candidate-" + digest({"event": event} if event else {"singleton": identifier})[:20]
            candidates.setdefault(group_id, []).append({"source": identifier, "assignment": "uncertain"})
        result = {
            "dossiers": [
                {"id": identifier, "members": members} for identifier, members in sorted(candidates.items())
            ],
            "method": "provider-event-uri-v1",
            "versions": context.versions,
            "status": "candidate grouping; human review required; provider event is not a confirmed incident",
        }
        return {"id": self.ledger.record(session, "grouping_proposal", str(uuid.uuid4()), result), **result}

    @audited_handler
    def _verify_legacy(self, session: str, context: Context, data: Json) -> Json:
        from .legacy import verify

        self._require(context, {"protocol", "selection"})
        root = Path(data["data_root"]).resolve()
        inventory_ref = self.ledger.artifacts.put(
            json.loads((root / "metadata/source-inventory.json").read_text(encoding="utf-8"))
        )
        result = {**verify(root), "input_inventory": inventory_ref, "versions": context.versions}
        return {"id": self.ledger.record(session, "legacy_verification", str(uuid.uuid4()), result), **result}

    @audited_handler
    def _prepare_legacy_pilot(self, session: str, context: Context, data: Json) -> Json:
        from .preparation import prepare_legacy_pilot

        self._require(context, {"protocol", "selection", "question", "profile"})
        return prepare_legacy_pilot(self, session, context, data)

    @audited_handler
    def _plan_embeddings(self, session: str, context: Context, data: Json) -> Json:
        self._require(context, {"dataset", "protocol", "question", "selection", "profile"})
        return self.gateway.plan_embeddings(session, context, data)

    @audited_handler
    def _embed(self, session: str, context: Context, data: Json) -> Json:
        self._require(
            context, {"dataset", "protocol", "question", "selection", "profile", "embedding_profile"}
        )
        return self.gateway.embed(session, context, data)

    @audited_handler
    def _build_vector_index(self, session: str, context: Context, data: Json) -> Json:
        from .retrieval import build

        self._require(context, {"dataset", "protocol", "question", "selection", "profile", "embedding_profile"})
        return build(self, session, context, data)

    @audited_handler
    def _vector_search(self, session: str, context: Context, data: Json) -> Json:
        from .retrieval import search

        self._require(context, {"dataset", "protocol", "question", "selection", "profile", "retrieval_profile"})
        return search(self, session, context, data)

    @audited_handler
    def _evaluate_vector_index(self, session: str, context: Context, data: Json) -> Json:
        from .retrieval import evaluate

        self._require(context, {"dataset", "protocol", "question", "selection", "profile", "retrieval_profile"})
        return evaluate(self, session, context, data)

    @audited_handler
    def _inspect_candidates(self, session: str, context: Context, data: Json) -> Json:
        from .retrieval import inspect_candidates

        self._require(context, {"dataset", "retrieval_profile"})
        return inspect_candidates(self, session, context, data)

    @audited_handler
    def _tag_retrieve(self, session: str, context: Context, data: Json) -> Json:
        from .tagging import retrieve

        return retrieve(self, session, context, data)

    @audited_handler
    def _tag_setup(self, session: str, context: Context, data: Json) -> Json:
        from .tagging import setup

        return setup(self, session, context, data)

    @audited_handler
    def _similarity_setup(self, session: str, context: Context, data: Json) -> Json:
        from .similarity_tags import setup

        return setup(self, session, context, data)

    @audited_handler
    def _similarity_score(self, session: str, context: Context, data: Json) -> Json:
        from .similarity_tags import score

        return score(self, session, context, data)

    @audited_handler
    def _similarity_calibrate(self, session: str, context: Context, data: Json) -> Json:
        from .similarity_tags import calibrate

        return calibrate(self, session, context, data)

    @audited_handler
    def _similarity_apply(self, session: str, context: Context, data: Json) -> Json:
        from .similarity_tags import apply

        return apply(self, session, context, data)

    @audited_handler
    def _article_query_rows(self, session: str, context: Context, data: Json) -> Json:
        from .similarity_tags import read_rows

        return read_rows(self, session, context, data)

    @audited_handler
    def _similarity_provisional_apply(self, session: str, context: Context, data: Json) -> Json:
        from .provisional_tags import apply

        return apply(self, session, context, data)

    @audited_handler
    def _article_query_overview(self, session: str, context: Context, data: Json) -> Json:
        from .query_overview import overview

        return overview(self, session, context, data)

    @audited_handler
    def _record_presentation(self, session: str, context: Context, data: Json) -> Json:
        from .presentation import record

        return record(self, session, context, data)

    @audited_handler
    def _adaptive_cutoff(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.adaptive_cutoff(session, context, data)

    @audited_handler
    def _rag_query(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.rag_query(session, context, data)

    @audited_handler
    def _plan_tags(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.plan_tags(session, context, data)

    @audited_handler
    def _conversation(self, session: str, context: Context, data: Json) -> Json:
        from .conversation import execute

        return execute(self, session, context, data)

    @audited_handler
    def _conversation_search(self, session: str, context: Context, data: Json) -> Json:
        from .conversation_search import execute

        return execute(self, session, context, data)

    @audited_handler
    def _conversation_chat(self, session: str, context: Context, data: Json) -> Json:
        from .conversation_chat import execute

        return execute(self, session, context, data)

    @audited_handler
    def _evaluate_aws_clustering(self, session: str, context: Context, data: Json) -> Json:
        from .aws_clustering_evaluation import execute

        return execute(self, session, context, data)

    @audited_handler
    def _evaluate_event_clustering(self, session: str, context: Context, data: Json) -> Json:
        from .event_clustering_evaluation import execute

        return execute(self, session, context, data)

    @audited_handler
    def _plan_event_pairs(self, session: str, context: Context, data: Json) -> Json:
        from .event_pair_study import prepare, render

        result = prepare(self, session, context, data)
        from .presentation import record
        presentation = record(self, session, Context(context.objective, context.actor, result["versions"]), {
            "results": [{"kind": "event_pair_plan", "id": result["id"]}],
            "markdown": render(result), "destination": "codex_chat"})
        return {**result, "presentation": presentation}

    @audited_handler
    def _event_pair_experiment(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.event_pair_experiment(session, context, data)

    @audited_handler
    def _event_pair_feature_experiment(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.event_pair_feature_experiment(session, context, data)

    @audited_handler
    def _event_pair_conjunction_experiment(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.event_pair_conjunction_experiment(session, context, data)

    @audited_handler
    def _event_pair_monotone_screen(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.event_pair_monotone_screen(session, context, data)

    @audited_handler
    def _apply_event_rule(self, session: str, context: Context, data: Json) -> Json:
        from .event_rule_application_study import execute
        return execute(self, session, context, data)

    @audited_handler
    def _refine_event_groups(self, session: str, context: Context, data: Json) -> Json:
        from .event_group_refinement_study import execute
        return execute(self, session, context, data)

    @audited_handler
    def _check_event_time_spans(self, session: str, context: Context, data: Json) -> Json:
        from .event_temporal_study import execute
        return execute(self, session, context, data)

    @audited_handler
    def _compare_event_group_windows(self, session: str, context: Context, data: Json) -> Json:
        from .event_window_study import execute
        return execute(self, session, context, data)

    @audited_handler
    def _propose_cross_window_group_links(self, session: str, context: Context, data: Json) -> Json:
        from .event_group_link_study import execute
        return execute(self, session, context, data)

    @audited_handler
    def _prepare_cross_window_event_review(self, session: str, context: Context, data: Json) -> Json:
        from .event_group_evidence_study import execute
        return execute(self, session, context, data)

    @audited_handler
    def _judge_cross_window_event_review(self, session: str, context: Context, data: Json) -> Json:
        from .event_group_evidence_judging import execute
        return execute(self, session, context, data)

    @audited_handler
    def _test_collective_group_vectors(self, session: str, context: Context, data: Json) -> Json:
        from .event_group_centroid_study import execute
        return execute(self, session, context, data)

    @audited_handler
    def _scale_event_vector_store(self, session: str, context: Context, data: Json) -> Json:
        from .event_vector_scale import execute

        return execute(self, session, context, data)

    @audited_handler
    def _plan_catalog_embeddings(self, session: str, context: Context, data: Json) -> Json:
        from .catalog_embedding_plan import execute

        return execute(self, session, context, data)

    @audited_handler
    def _index_catalog_embeddings(self, session: str, context: Context, data: Json) -> Json:
        from .catalog_vector_index import execute

        return execute(self, session, context, data)

    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.luna_group_validation(session, context, data)

    @audited_handler
    def _luna_group_validation_continue(self, session: str, context: Context, data: Json) -> Json:
        from .luna_validation_continuation import run

        return run(self, session, context, data)

    @audited_handler
    def _luna_study_export(self, session: str, context: Context, data: Json) -> Json:
        from .luna_study_transfer import export

        return export(self, session, context, data)

    @audited_handler
    def _luna_study_import(self, session: str, context: Context, data: Json) -> Json:
        from .luna_study_transfer import import_into

        return import_into(self, session, context, data)

    @audited_handler
    def _tag(self, session: str, context: Context, data: Json) -> Json:
        return self.gateway.tag(session, context, data)

    @audited_handler
    def _tag_inspect(self, session: str, context: Context, data: Json) -> Json:
        from .tagging import inspect

        return inspect(self, session, context, data)

    @audited_handler
    def _tag_review_queue(self, session: str, context: Context, data: Json) -> Json:
        from .tagging import queue

        return queue(self, session, context, data)

    @audited_handler
    def _tag_review(self, session: str, context: Context, data: Json) -> Json:
        from .tagging import review

        return review(self, session, context, data)

    @audited_handler
    def _tag_calibrate(self, session: str, context: Context, data: Json) -> Json:
        from .tag_calibration import calibrate

        return calibrate(self, session, context, data)

    @audited_handler
    def _tag_apply(self, session: str, context: Context, data: Json) -> Json:
        from .tag_calibration import apply

        return apply(self, session, context, data)
