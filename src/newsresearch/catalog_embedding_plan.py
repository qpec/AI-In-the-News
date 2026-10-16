"""Prepare bounded core datasets and standard gateway embedding plans offline."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active
from . import preparation
from . import event_vector_store as store
from .event_vector_scale import _save
from .legacy import sha256

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "full-catalog-bounded-gateway-planning-v1"
UNKNOWN = "Source retrieval times remain in original catalog occurrences/receipts; no new retrieval occurred during bounded catalog import."


def _implementation(engine: Research) -> str:
    return digest({k:v for k,v in engine.identity()["code_files"].items() if k.startswith("src/") or k=="uv.lock"})


def _batch(engine: Research, session: str, context: Context, catalog: store.Catalog, selected: list[Json], snapshot: str, key: str) -> Json:
    previous=engine.ledger.db.execute("SELECT id FROM records WHERE kind='catalog_embedding_batch' AND logical_key=?",(key,)).fetchone()
    if previous:
        value=engine.ledger.get(previous[0],"catalog_embedding_batch")
        plan=engine.ledger.get(value["plan"],"embedding_plan")
        if value["selection_hash"]!=digest(selected) or plan["implementation_digest"]!=_implementation(engine):
            raise ResearchError("Stored batch selection or executable code changed")
        engine.ledger.append(session,"catalog_embedding.batch.reused",{"batch":previous[0],"plan":value["plan"]})
        return {"id":previous[0],**value}
    articles=[]
    for row in selected:
        payload=catalog.db.execute("SELECT payload FROM records WHERE record_id=?",(row["record_id"],)).fetchone()
        if payload is None:
            raise AuditError("Selected catalog source record is missing")
        article=json.loads(payload[0])
        body=article.get("body")
        if (article.get("retention")!="permitted" or article.get("quarantined") or not isinstance(body,str) or not body.strip()
                or hashlib.sha256(body.encode()).hexdigest()!=article["body_sha256"]
                or store.article_identity(article)!=row["article_id"]):
            raise AuditError("Selected catalog body/retention differs from pending frame")
        articles.append({"source_key":"eventregistry:"+article["provider_article_id"],"body":body,"retention":"permitted",
            "title":article.get("title"),"url":article.get("url"),"published_at":article.get("published_at"),
            "synthetic":False,"raw_record":article.get("raw_record"),"catalog_provenance":{
                "snapshot":snapshot,"catalog_artifact":str(catalog.path.name),"article_id":row["article_id"],
                "record_id":row["record_id"],"body_sha256":article["body_sha256"]}})
    dataset=engine._ingest(session,context,{"key":key,"articles":articles,"retrieval":{
        "source":"Immutable audited full-corpus catalog; exact original occurrences remain linked",
        "retrieved_at":None,"parameters":None,"unavailable_reason":UNKNOWN,"catalog_snapshot":snapshot,"network_calls":0}})
    del articles
    versions={**context.versions,"dataset":dataset["id"]}
    bound=Context(context.objective,context.actor,versions)
    mapping=[{"source_version":source,**row} for source,row in zip(dataset["sources"],selected,strict=True)]
    mapping_ref=_save(engine,session,mapping,"Exact full-catalog to bounded core-source mapping")
    sql="SELECT * FROM passages WHERE source_id IN (SELECT value FROM json_each(?)) ORDER BY source_id,start"
    parameters=[canonical(dataset["sources"])]
    engine.ledger.append(session,"catalog_embedding.passages.inspection.intended",{"sql":sql,"parameters":parameters,"purpose":"Prepare exact original-method chunks, without semantic inspection"})
    pending=[]
    chunks=[]
    chunk_count=passage_count=0
    for passage in engine.ledger.db.execute(sql,parameters):
        passage_count+=1
        for chunk in preparation.chunks(dict(passage)):
            pending.append(chunk)
            chunk_count+=1
            if len(pending)==1000:
                chunks.append(_save(engine,session,pending,"Bounded exact embedding-input chunks"))
                pending=[]
    if pending:
        chunks.append(_save(engine,session,pending,"Bounded exact embedding-input chunks"))
    if chunk_count!=sum(row["chunks"] for row in selected):
        raise AuditError("Core passage/chunk coverage differs from registered pending frame")
    prepared={"versions":context.versions,"dataset":dataset["id"],"method":METHOD,"catalog_snapshot":snapshot,
        "selection_manifest":mapping_ref,"selected_records":len(selected),"text_unavailable_records":0,
        "embedding_input_chunks":chunk_count,"chunk_artifacts":chunks,"passages":passage_count,
        "network_calls":0,"model_calls":0,"scope":"Offline exact catalog-source import; embedding execution not authorized"}
    prepared_id=engine.ledger.record(session,"corpus_preparation",key,prepared)
    plan=engine._plan_embeddings(session,bound,{"preparation":prepared_id})
    if (plan["versions"]["embedding_profile"]!=catalog.spec["embedding_profile"]
            or any(plan["profile"][field]!=catalog.spec[field] for field in ("provider","model","dimensions"))):
        raise ResearchError("Standard gateway plan changed the original compatible embedding profile")
    if plan["input_tokens"]!=sum(row["input_tokens"] for row in selected) or plan["expected_chunks"]!=chunk_count:
        raise AuditError("Gateway plan token/chunk totals differ from audited pending workload")
    value={"versions":versions,"snapshot":snapshot,"dataset":dataset["id"],"preparation":prepared_id,
        "plan":plan["id"],"plan_versions":plan["versions"],"context_artifact":plan["context_artifact"],
        "selection_hash":digest(selected),"mapping_artifact":mapping_ref,"articles":len(selected),
        "chunks":chunk_count,"requests":plan["request_count"],"input_tokens":plan["input_tokens"],
        "estimated_cost_usd":plan["estimated_cost_usd"],"model_calls":0,"network_calls":0}
    identifier=engine.ledger.record(session,"catalog_embedding_batch",key,value)
    engine.ledger.append(session,"catalog_embedding.batch.completed",{"batch":identifier,"plan":plan["id"],
        "articles":len(selected),"requests":plan["request_count"],"tokens":plan["input_tokens"]})
    return {"id":identifier,**value}


def render(value: Json) -> str:
    return "\n".join([
        "Full-corpus embedding preparation result","",
        f"Prepared {value['articles']:,}/{value['selected_articles']:,} previously unembedded text-bearing article versions in {len(value['batches'])} bounded core datasets and standard gateway plans.",
        f"Coverage: {value['chunks']:,} exact chunks; {value['requests']:,} planned API requests; {value['input_tokens']:,} input tokens; estimated successful-input cost USD {value['estimated_cost_usd']}.",
        f"Failed/pending articles: {value['failed_articles']:,}/{value['pending_articles']:,}. Paid/model/network calls: 0/0/0. Newly embedded articles: 0.",
        "The plans are executable through the existing audited embedding gateway only after concrete plan-bound paid approval. No approval was created. Credentials were not read.",
        "Original compatible vectors and seven-day memberships are unchanged. Article inclusion is a technical text-availability queue, not a relevance judgement or event count.",
        "Plans bind the exact current executable source code; source-code changes before execution require refreshed plans. This check has not validated semantic event grouping."
    ])


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine,session)
    if set(data)-{"snapshot","key","instruction","batch_size"} or not isinstance(data.get("instruction"),str) or not data["instruction"].strip():
        raise ResearchError("Declare offline plan scope; no paid execution fields")
    size=data.get("batch_size",20000)
    if type(size) is not int or not 1<=size<=engine.config.max_articles:
        raise ResearchError("Every core import must fit the unchanged working limit")
    key=data["key"]
    if not isinstance(key,str) or not key.strip() or len(key)>128:
        raise ResearchError("Declare a bounded stable planning key")
    snapshot=engine.ledger.get(data["snapshot"],"event_vector_store_result")
    code=_implementation(engine)
    method={"method":METHOD,"implementation":code,"adapter_sha256":sha256(Path(__file__)),
        "snapshot":data["snapshot"],"batch_size":size,"operator_instruction":data["instruction"],
        "retention":"Only nonblank, permitted, nonquarantined pending catalog versions; exact body/hash checks and full provenance; no network/models",
        "chunks":preparation.CHUNK_METHOD,"standard_planner":"Research._plan_embeddings through shared gateway; original embedding profile",
        "catalog_validation":"Full current binary hash plus exact prior complete catalog verification; selected bodies/source identities and new passages/chunks fully revalidated",
        "scope":"One bounded core dataset per at most20000 articles; master plans preserve full coverage; no global limit change"}
    prior=engine.ledger.db.execute("SELECT id FROM records WHERE kind='catalog_embedding_manifest' AND logical_key=?",(key,)).fetchone()
    if prior:
        old=engine.ledger.get(prior[0],"catalog_embedding_manifest")
        if old["method"]!=method:
            raise ResearchError("Planning key binds a different snapshot/method/code; register another version")
        versions=dict(old["versions"])
        manifest=prior[0]
    else:
        versions={k:v for k,v in snapshot["versions"].items() if k!="retrieval_profile"}
        definitions={"protocol":{"method":method,"unavailable_retrieval_reason":UNKNOWN},
            "question":{"text":"Prepare all missing full-corpus article embeddings as bounded audited gateway plans, without model dispatch"},
            "selection":{"rules":{"snapshot":data["snapshot"],"catalog":snapshot["catalog"]["artifact"],"selected_table":"pending_embeddings","order":"article_id","batch_size":size}},
            "profile":{"mode":"exploratory","population_estimate":False,"scope":"Technical preparation only; no inference/event acceptance"}}
        for kind,content in definitions.items():
            versions[kind]=engine._version(session,context,{"kind":kind,"key":key,"content":content})["id"]
        manifest=engine.ledger.record(session,"catalog_embedding_manifest",key,{"versions":versions,"method":method})
    engine.ledger.append(session,"catalog_embedding.preparation.intended",{"manifest":manifest,"versions":versions,"snapshot":data["snapshot"],"maximum_batch_articles":size,"model_calls":0})
    bound=Context(context.objective,context.actor,versions)
    catalog_ref=snapshot["catalog"]["artifact"]
    path=engine.ledger.artifacts.verified_path(catalog_ref)
    catalog=store.Catalog(path,snapshot["spec"],readonly=True)
    try:
        if snapshot["catalog"]["summary"].get("status")!="verified" or snapshot.get("failed_rows") or snapshot.get("pending_rows"):
            raise AuditError("Require the completed fully verified catalog snapshot")
        engine.ledger.append(session,"analysis.cache_reused",{"catalog":catalog_ref,"snapshot":data["snapshot"],
            "basis":"Fresh full binary hash verification of the exact previously fully verified catalog; selected source bodies and all new passages/chunks revalidated before gateway planning"})
        sql="SELECT p.article_id,p.passages,p.chunks,p.input_tokens,min(r.record_id) AS record_id FROM records r JOIN pending_embeddings p USING(article_id) GROUP BY p.article_id ORDER BY p.article_id"
        engine.ledger.append(session,"catalog_embedding.selection.intended",{"catalog":catalog_ref,"sql":sql,"parameters":[]})
        frame=[dict(row) for row in catalog.db.execute(sql)]
        if (len(frame)!=snapshot["catalog"]["pending"]["articles"] or sum(row["chunks"] for row in frame)!=snapshot["catalog"]["pending"]["chunks"]
                or sum(row["input_tokens"] for row in frame)!=snapshot["catalog"]["pending"]["input_tokens"]):
            raise AuditError("Full pending source frame no longer matches original workload")
        selection=_save(engine,session,frame,"Complete selected catalog IDs and exact per-article workload before bounded core imports")
        if shutil.disk_usage(engine.ledger.root).free < path.stat().st_size*4+2*1024**3:
            raise ResearchError("Insufficient free space for bounded core sources/passages and request plans")
        batches=[]
        for start in range(0,len(frame),size):
            if code!=_implementation(engine):
                raise ResearchError("Executable source code changed during planning; no model calls occurred; retain completed batches")
            batches.append(_batch(engine,session,bound,catalog,frame[start:start+size],data["snapshot"],key+f"-{start//size:03d}"))
        if code!=_implementation(engine):
            raise ResearchError("Executable source code changed before plan completion; do not dispatch these plans")
    finally:
        catalog.close()
    value={"versions":versions,"manifest":manifest,"snapshot":data["snapshot"],"selection":selection,"selected_articles":len(frame),
        "batches":batches,"articles":sum(row["articles"] for row in batches),"chunks":sum(row["chunks"] for row in batches),
        "requests":sum(row["requests"] for row in batches),"input_tokens":sum(row["input_tokens"] for row in batches),
        "estimated_cost_usd":str(sum((Decimal(row["estimated_cost_usd"]) for row in batches),Decimal(0))),
        "failed_articles":0,"pending_articles":0,"paid_calls":0,"model_calls":0,"network_calls":0,"new_embeddings":0,
        "status":"planned_pending_concrete_paid_approval","implementation_digest":code,"execution_commit":engine.identity()["git_head"]}
    identifier=engine.ledger.record(session,"catalog_embedding_plan_result",key,value)
    presentation=engine._record_presentation(session,bound,{"results":[{"kind":"catalog_embedding_plan_result","id":identifier}],
        "markdown":render(value),"destination":"codex_chat","status":"prepared_for_delivery"})
    return {"id":identifier,**value,"presentation":presentation}
