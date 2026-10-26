"""Bounded eventUri audit by the current conversation, through the shared gateway.

No CLI model workers, network requests, controller resumes, or accepted findings.
The adapter freezes requests before observable handoff and reconciles exact replies.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
import uuid
import zipfile

from newsresearch.common import Config, Context, ResearchError, digest, require_no_credentials, utc
from newsresearch.gateway import BOUNDARY, ProviderResponse
from newsresearch.runtime import Research, audited_handler

from audit_article_scope_metadata import CORPORA, read_partition, sha256, within

METHOD = "provider-event-label-current-conversation-v1"
SEED = "newsapi-event-label-check-20261019-v1"
RULES = """Compare the focal real-world events in articles A and B using only supplied text.
Different perspectives, consequences discussed as context, and later reports of the
same occurrence can be same_event. A common topic, person, organization or background
event is insufficient. Separate announcements, incidents, lawsuits, investigations,
verdicts or other distinct developments are different_event. General analysis without
an identifiable focal occurrence, competing focal events, or insufficient evidence is
uncertain. Do not equate publication time with event time. Attribute allegations.
Read all supplied text and provide label, a short rationale, one focal-event summary
per article, and an exact short quote from each article. No external knowledge or
retrieval. These are provisional model judgments, not independent human ground truth.
"""
LABELS = ("same_event", "different_event", "uncertain")


def select_pairs(groups, seed, count):
    eligible = {key: sorted(set(ids)) for key, ids in groups.items() if len(set(ids)) >= 2}
    if len(eligible) < count:
        raise ResearchError("Insufficient eligible event IDs")
    chosen = sorted(eligible, key=lambda key: (digest([seed, "event", key]), key))[:count]
    return [{"corpus": key[0], "event_uri": key[1], "group_size": len(eligible[key]),
             "article_ids": sorted(eligible[key], key=lambda item: (digest([seed, "article", key, item]), item))[:2]}
            for key in chosen], len(eligible)


@dataclass(frozen=True)
class Invocation:
    request: dict

    def manifest(self):
        return {"transport": "current-conversation-tool-output", "request": self.request,
                "model_identity": None, "usage": None, "provider_request_id": None,
                "observability": "Application packet and submitted visible reply only; host internals unavailable"}


class ConversationHandoff:
    def complete_prepared(self, invocation):
        # This is a handoff receipt, deliberately NOT an inferred model response.
        return ProviderResponse(None, "codex-current-conversation", None,
                                raw_response={"handoff_ready": True, "request": invocation.request})


def validate_reply(request, reply):
    if set(reply) != {"pair", "label", "rationale", "event_a", "event_b", "quote_a", "quote_b"}:
        raise ResearchError("Reply fields differ from registered schema")
    if reply["pair"] != request["pair"] or reply["label"] not in LABELS:
        raise ResearchError("Reply identity or label invalid")
    for key in ("rationale", "event_a", "event_b"):
        if not isinstance(reply[key], str) or not reply[key].strip():
            raise ResearchError("Reply field empty")
    for role in ("a", "b"):
        if not request[role]["body"]:
            if reply["label"] != "uncertain" or reply["quote_" + role] != "":
                raise ResearchError("Missing text requires uncertainty and an empty quote")
            continue
        if not isinstance(reply["quote_" + role], str) or not reply["quote_" + role].strip():
            raise ResearchError("Nonmissing source requires a quotation")
        if reply["quote_" + role] not in request[role]["body"]:
            raise ResearchError("Evidence quotation does not match supplied article")
    return {"schema": "valid", "quotes": "exact_available_sources", "missing_sources": sum(not request[role]["body"] for role in ("a", "b")), "human_validated": False,
            "semantic_correctness": "not mechanically verified"}


class LabelAudit(Research):
    @audited_handler
    def _status(self, session, context, data):
        action = data["action"]
        if action == "prepare":
            return self.prepare(session, context, data)
        plans = self.ledger.db.execute("SELECT id FROM records WHERE kind='provider_label_plan'").fetchall()
        if len(plans) != 1:
            raise ResearchError("Exactly one frozen plan required")
        plan_id = plans[0][0]
        plan = self.ledger.get(plan_id, "provider_label_plan")
        if action == "dispatch":
            return self.dispatch(session, plan_id, plan, data)
        if action == "read":
            packets = []
            for number in data["pairs"]:
                task = digest([plan_id, number])
                row = self.ledger.db.execute("SELECT id FROM records WHERE kind='provider_label_handoff' AND logical_key=?", (task,)).fetchone()
                if not row:
                    raise ResearchError("Cannot inspect evidence without a prior gateway handoff")
                intent = self.ledger.get(row[0], "provider_label_handoff")
                request = self.ledger.artifacts.read(intent["request"])
                packet = {"pair": number, "request": intent["request"], "start": data["start"], "end": data["end"]}
                for role in ("a", "b"):
                    source = request[role]
                    packet[role] = {"title": source["title"], "published": source["published"], "total_chars": len(source["body"]),
                                    "text": source["body"][data["start"]:data["end"]]}
                packets.append(packet)
            self.ledger.append(session, "provider_label.request.chunk_inspected", {"packets": self.ledger.artifacts.put(packets),
                "purpose": "Recover/inspect an exact window of already handed-off requests; no new inference attempt or changed evidence."})
            return {"packets": packets}
        if action == "submit":
            return self.submit(session, plan_id, plan, data)
        if action == "report":
            return self.report(session, plan_id, plan)
        raise ResearchError("Unsupported label-audit action")

    def prepare(self, session, context, data):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='provider_label_plan'").fetchone():
            raise ResearchError("Sample already frozen; no redraw")
        count = data["count"]
        if not isinstance(count, int) or not 1 <= count <= 50:
            raise ResearchError("Sample must contain 1 to 50 event IDs")
        versions = {}
        content = {
            "protocol": {"method": METHOD, "implementation_sha256": sha256(Path(__file__)),
                         "sampling_helper_sha256": sha256(Path(__file__).with_name("audit_article_scope_metadata.py")),
                         "user_authorization_basis": "User requested 50 random provider event IDs and 50 counterparts, compared by this Codex agent.",
                         "retention": "Selected stored articles retained privately for requested comparison; no publication of source bodies. Credential-pattern-flagged or explicitly restricted rows retain only hash/locator, with no text and no replacement; missing evidence requires uncertainty.",
                         "inference": "Current conversation only; frozen application packets via shared Gateway.codex_dispatch; no fresh model processes or API calls.",
                         "attempt_policy": "One initial dispatch per pair; unknown or invalid attempts never retried; exact replay of a saved reply is idempotent.",
                         "limits": "Does not capture host instructions, hidden reasoning, token usage, actual model ID or proof of reading."},
            "selection": {"rules": "Uniform pseudorandom hash ranking of (corpus,eventUri) groups with >=2 distinct exact nonblank article URIs; choose two distinct article URIs independently by hash. Corpus namespaces remain separate. Collapse repeated article URI rows to lexicographically first bundle/line; exclude identities with conflicting eventUri strings. Do not condition on article content, group size or judging outcomes. No replacement after selection.",
                          "seed": data["seed"], "count": count, "corpora": list(CORPORA)},
            "question": {"text": "Do two randomly selected reports sharing NewsAPI.ai eventUri describe the same focal real-world event?"},
            "dossier_definition": {"unit": "One specific real-world occurrence; perspectives may differ; one pair does not validate the whole provider group."},
            "codebook": {"labels": list(LABELS), "definitions": RULES},
            "prompt": {"instructions": BOUNDARY + "\n" + RULES},
            "profile": {"mode": "exploratory", "population_estimate": False,
                        "human_validated": False, "maximum_pair_attempts": count, "maximum_article_exposures": 2 * count},
        }
        for kind, value in content.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": value,
                "amend_latest": True, "reason": "Preserve frozen deterministic sampling; retain any credential-pattern or restricted row as an uninspectable selected source, without replacement."})["id"]
        root = Path(data["data_root"])
        identities, partitions, counts = {}, {}, {}
        for corpus in CORPORA:
            partition = read_partition(root, corpus)
            partitions[corpus] = partition
            records = defaultdict(list)
            state = Counter()
            for bundle in partition["manifest"]["bundles"]:
                path = within(root, bundle["path"])
                self.ledger.append(session, "provider_label.archive.scan.intended", {
                    "corpus": corpus, "path": str(path), "sha256": bundle["sha256"], "versions": versions})
                if sha256(path) != bundle["sha256"]:
                    raise ResearchError("Archive hash differs from frozen manifest")
                rows = 0
                with zipfile.ZipFile(path) as archive, archive.open("artikelen.jsonl") as stream:
                    for number, raw in enumerate(stream, 1):
                        if not raw.strip():
                            continue
                        rows += 1
                        article = json.loads(raw)["article"]
                        uri, event = article.get("uri"), article.get("eventUri")
                        state["rows"] += 1
                        if not isinstance(uri, str) or not uri.strip():
                            state["no_article_uri"] += 1
                            continue
                        if not isinstance(event, str) or not event.strip():
                            state["no_populated_event_uri"] += 1
                            continue
                        records[uri].append({"event": event, "path": bundle["path"], "line": number,
                                             "row_sha256": hashlib.sha256(raw).hexdigest(), "archive_sha256": bundle["sha256"]})
                if rows != bundle["declared_records"]:
                    raise ResearchError("Archive count differs from manifest")
                self.ledger.append(session, "provider_label.archive.scanned", {"corpus": corpus, "path": str(path), "rows": rows})
            for uri, entries in records.items():
                if len({item["event"] for item in entries}) > 1:
                    state["conflicting_event_identity"] += 1
                    continue
                identities[(corpus, uri)] = min(entries, key=lambda item: (item["path"], item["line"]))
                state["collapsed_repeat_rows"] += len(entries) - 1
            counts[corpus] = dict(state)
        groups = defaultdict(list)
        for (corpus, uri), locator in identities.items():
            groups[(corpus, locator["event"])].append(uri)
        pairs, eligible = select_pairs(groups, data["seed"], count)
        targets = defaultdict(dict)
        for pair in pairs:
            for uri in pair["article_ids"]:
                loc = identities[(pair["corpus"], uri)]
                targets[loc["path"]][loc["line"]] = (pair["corpus"], uri, loc)
        selected = {}
        for relative, lines in targets.items():
            path = within(root, relative)
            if sha256(path) != next(iter(lines.values()))[2]["archive_sha256"]:
                raise ResearchError("Selected archive changed")
            with zipfile.ZipFile(path) as archive, archive.open("artikelen.jsonl") as stream:
                for number, raw in enumerate(stream, 1):
                    if number not in lines:
                        continue
                    corpus, uri, loc = lines[number]
                    if hashlib.sha256(raw).hexdigest() != loc["row_sha256"]:
                        raise ResearchError("Selected source changed")
                    original_row = json.loads(raw)
                    article = original_row["article"]
                    excluded = any(original_row.get(key) for key in ("metadata_only", "quarantined", "quarantine", "retention_exclusion")) or original_row.get("retention") == "metadata_only"
                    try:
                        require_no_credentials(original_row)
                    except ResearchError:
                        excluded = True
                    if excluded:
                        selected[(corpus, uri)] = {"source_sha256": digest(article), "locator": loc,
                            "original": None, "title": "[withheld by retention or credential-pattern check]", "url": None,
                            "published": None, "body": "", "quarantined": True}
                        self.ledger.append(session, "provider_label.source.withheld", {"locator": loc,
                            "source_sha256": digest(article), "reason": "retention_marker_or_credential_pattern", "replaced": False})
                        continue
                    selected[(corpus, uri)] = {"source_sha256": digest(article), "locator": loc,
                        "original": self.ledger.artifacts.put_bytes(raw), "title": article.get("title"),
                        "url": article.get("url"), "published": article.get("dateTimePub") or article.get("dateTime") or article.get("date"),
                        "body": article.get("body") or ""}
        for number, pair in enumerate(pairs, 1):
            pair["pair"] = number
            pair["articles"] = [selected[(pair["corpus"], uri)] for uri in pair["article_ids"]]
            pair["exact_duplicate_body"] = bool(pair["articles"][0]["body"]) and pair["articles"][0]["body"] == pair["articles"][1]["body"]
        plan = {"method": METHOD, "versions": versions, "seed": data["seed"], "pairs": pairs,
                "eligible_groups": eligible, "eligible_by_corpus": dict(Counter(key[0] for key, ids in groups.items() if len(set(ids)) >= 2)),
                "frame_counts": counts, "partitions": partitions,
                "frame_digest": digest(sorted((key, sorted(set(ids))) for key, ids in groups.items())),
                "sampled_by_corpus": dict(Counter(pair["corpus"] for pair in pairs)),
                "selection_probability": count / eligible, "prepared_at": utc()}
        identifier = self.ledger.record(session, "provider_label_plan", METHOD, plan)
        return {"plan": identifier, "eligible_groups": eligible, "eligible_by_corpus": plan["eligible_by_corpus"],
                "sampled_by_corpus": plan["sampled_by_corpus"], "pairs": count, "seed": data["seed"],
                "exact_duplicate_bodies": sum(pair["exact_duplicate_body"] for pair in pairs),
                "body_characters": sum(len(article["body"]) for pair in pairs for article in pair["articles"]),
                "uninspectable_sources": sum(not article["body"] for pair in pairs for article in pair["articles"]),
                "judgments": 0, "frame_counts": counts}

    def dispatch(self, session, plan_id, plan, data):
        requests, invocations = [], []
        if len(data["pairs"]) != len(set(data["pairs"])):
            raise ResearchError("Duplicate dispatch pair")
        batch = str(uuid.uuid4())
        for number in data["pairs"]:
            if number not in range(1, len(plan["pairs"]) + 1):
                raise ResearchError("Pair outside frozen sample")
            task = digest([plan_id, number])
            if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='provider_label_handoff' AND logical_key=?", (task,)).fetchone():
                raise ResearchError("Already dispatched; no repeat or retry")
            pair = plan["pairs"][number - 1]
            request = {"pair": number, "boundary": BOUNDARY, "instructions": RULES,
                       "versions": plan["versions"], "response_fields": ["pair", "label", "rationale", "event_a", "event_b", "quote_a", "quote_b"]}
            for role, article in zip(("a", "b"), pair["articles"]):
                request[role] = {key: article[key] for key in ("source_sha256", "title", "published", "body")}
            invocation = Invocation(request)
            attempt = str(uuid.uuid4())
            intended = {"attempt": attempt, "task_key": task, "number": 1, "batch": batch,
                        "request": self.ledger.artifacts.put(request), "dispatch": self.ledger.artifacts.put(invocation.manifest()),
                        "plan": plan_id, "pair": number, "started_at": utc(), "reserved_pair_attempts": 1,
                        "reserved_article_exposures": 2, "authorization_key": METHOD}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
            self.ledger.record(session, "provider_label_handoff", task, intended)
            requests.append(request)
            invocations.append((invocation, attempt))
        for _, response in self.gateway.codex_dispatch(session, ConversationHandoff(), invocations, 1):
            if not (response.raw_response or {}).get("handoff_ready"):
                raise ResearchError("Current-conversation handoff failed; attempt stays unresolved")
        self.ledger.append(session, "provider_label.handoff.prepared", {"plan": plan_id, "pairs": data["pairs"],
            "observation": "Packets returned in operation output; actual UI visibility and model attention unobserved."})
        return {"requests": requests, "state": "awaiting_current_conversation_replies"}

    def submit(self, session, plan_id, plan, data):
        saved = []
        for reply in data["replies"]:
            task = digest([plan_id, reply["pair"]])
            previous = self.ledger.db.execute("SELECT id FROM records WHERE kind='provider_label_judgment' AND logical_key=?", (task,)).fetchone()
            if previous:
                value = self.ledger.get(previous[0], "provider_label_judgment")
                if value["reply"] != reply:
                    raise ResearchError("Cannot replace a completed judgment")
                saved.append(previous[0])
                continue
            row = self.ledger.db.execute("SELECT id FROM records WHERE kind='provider_label_handoff' AND logical_key=?", (task,)).fetchone()
            if not row:
                raise ResearchError("Reply lacks prior gateway handoff")
            intent = self.ledger.get(row[0], "provider_label_handoff")
            if intent["attempt"] not in self.ledger.unresolved:
                raise ResearchError("Attempt already closed")
            request = self.ledger.artifacts.read(intent["request"])
            response = ProviderResponse(reply, "codex-current-conversation", None, raw_response=reply)
            response_ref = self.ledger.artifacts.put(asdict(response))
            self.ledger.append(session, "codex.response.received", {"attempt": intent["attempt"], "artifact": response_ref,
                "provenance": "Exact agent-authored JSON submitted in this conversation; actual provider model ID and token usage unavailable."})
            assessment, status = None, "invalid"
            try:
                validation = validate_reply(request, reply)
                assessment = self.ledger.record(session, "provider_label_judgment", task,
                    {"plan": plan_id, "attempt": intent["attempt"], "request": intent["request"], "response": response_ref,
                     "reply": reply, "validation": validation, "human_validated": False, "recorded_at": utc()})
                status = "valid"
            except ResearchError as error:
                validation = {"status": "invalid", "reason": str(error)}
            def project(event):
                self.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                    intent["attempt"], task, intent["batch"], 1, intent["request"], response_ref, status, assessment, None, event))
            self.ledger.append(session, "model.attempt.completed", {"attempt": intent["attempt"], "status": status,
                "response": response_ref, "assessment": assessment, "validation": validation, "ended_at": utc()}, project)
            self.ledger.unresolved.pop(intent["attempt"])
            saved.append({"pair": reply["pair"], "status": status, "assessment": assessment, "validation": validation})
        return {"saved": saved}

    def report(self, session, plan_id, plan):
        values = [self.ledger.get(row[0], "provider_label_judgment") for row in self.ledger.db.execute(
            "SELECT id FROM records WHERE kind='provider_label_judgment' ORDER BY created_event")]
        by_pair = {value["reply"]["pair"]: value for value in values}
        windows = defaultdict(list)
        for event in self.ledger.db.execute("SELECT payload FROM events WHERE kind='provider_label.request.chunk_inspected' ORDER BY seq"):
            packet_ref = json.loads(event[0])["packets"]
            for packet in self.ledger.artifacts.read(packet_ref):
                for role in ("a", "b"):
                    windows[(packet["pair"], role)].append((packet["start"], packet["start"] + len(packet[role]["text"]), packet[role]["text"]))
        rows = []
        for pair in plan["pairs"]:
            value = by_pair.get(pair["pair"])
            coverage = {}
            for role, article in zip(("a", "b"), pair["articles"]):
                spans = sorted(windows[(pair["pair"], role)])
                covered, frontier = 0, 0
                for start, end, _ in spans:
                    covered += max(0, end - max(start, frontier))
                    frontier = max(frontier, end)
                quote = value["reply"]["quote_" + role] if value else ""
                coverage[role] = {"stored_characters": len(article["body"]), "window_characters_returned": covered,
                    "complete_stored_body_returned": bool(article["body"]) and covered == len(article["body"]),
                    "quote_present_in_inspected_window": bool(quote) and any(quote in text for _, _, text in spans),
                    "scope": "missing" if not article["body"] else ("complete_stored_body" if covered == len(article["body"]) else "partial_stored_body")}
            rows.append({"pair": pair["pair"], "corpus": pair["corpus"], "event_uri": pair["event_uri"],
                         "group_size": pair["group_size"], "exact_duplicate_body": bool(pair["articles"][0]["body"]) and pair["exact_duplicate_body"],
                         "uninspectable_sources": sum(not article["body"] for article in pair["articles"]),
                         "inspection_coverage": coverage,
                         "articles": [{key: article[key] for key in ("title", "url", "published", "source_sha256", "locator")} for article in pair["articles"]],
                         "judgment": value["reply"] if value else None})
        all_coverage = [coverage for row in rows for coverage in row["inspection_coverage"].values()]
        inspection = {"method": "Title and opening 2300-3000 characters, plus additional windows for ambiguous pairs; not uniform full-text review.",
            "complete_stored_bodies_returned": sum(item["complete_stored_body_returned"] for item in all_coverage),
            "partial_stored_bodies_returned": sum(item["scope"] == "partial_stored_body" for item in all_coverage),
            "missing_stored_bodies": sum(item["scope"] == "missing" for item in all_coverage),
            "window_characters_returned": sum(item["window_characters_returned"] for item in all_coverage),
            "stored_characters": sum(item["stored_characters"] for item in all_coverage),
            "available_source_quotes_found_in_windows": sum(item["quote_present_in_inspected_window"] for item in all_coverage),
            "observation_limit": "Saved chunk-output preparation, not proof of attention or original-webpage completeness. Initial oversized dispatch output was truncated; bounded chunk inspection was added before judgments. A Windows console encoding failure was recovered by rereading the same saved packets; no new model attempts."}
        report_note = self._version(session, Context(
            "Document observed inspection scope and a corrected missing-text diagnostic", "codex:current-conversation-event-label-review", {}),
            {"kind": "note", "key": METHOD + "-observed-scope", "content": {
                "retrospective": True, "inspection": inspection, "implementation_sha256": sha256(Path(__file__)),
                "diagnostic_correction": "Frozen preparation reported one duplicate because two withheld empty placeholders compared equal. Final exact-body-duplicate counts require a nonempty body; no sample or judgment was replaced."}})["id"]
        result = {"plan": plan_id, "method": METHOD, "seed": plan["seed"], "eligible_groups": plan["eligible_groups"],
                  "eligible_by_corpus": plan["eligible_by_corpus"], "sampled_by_corpus": plan["sampled_by_corpus"],
                  "counts": dict(Counter(value["reply"]["label"] for value in values)), "reviewed": len(values),
                  "pending_or_failed": len(rows) - len(values), "rows": rows, "human_validated": False,
                  "unresolved_attempts": len(self.ledger.unresolved), "inspection": inspection, "scope_note": report_note,
                  "readable_pairs": sum(not row["uninspectable_sources"] for row in rows),
                  "uninspectable_pairs": sum(bool(row["uninspectable_sources"]) for row in rows),
                  "exact_duplicate_body_pairs": sum(row["exact_duplicate_body"] for row in rows),
                  "by_corpus": {corpus: dict(Counter(row["judgment"]["label"] for row in rows if row["corpus"] == corpus and row["judgment"])) for corpus in CORPORA},
                  "limitations": "One current Codex review using titles/opening passages plus selective further reading, not a uniform full-text or independent human validation. Pair checks do not establish whole-group purity, recall, singleton quality or other corpora. Equal group selection is not article-weighted. Syndication can inflate agreement. Stored bodies may be incomplete excerpts or differ from original webpages. Host-internal context and usage are unavailable."}
        result_id = self.ledger.record(session, "provider_label_report", METHOD, result)
        summary = "; ".join(f"{label}: {result['counts'].get(label, 0)}/{len(rows)} ({result['counts'].get(label, 0) / len(rows):.0%})" for label in LABELS)
        lines = ["# NewsAPI.ai event label sample", "", f"Recorded {len(values)}/{len(rows)} pair outcomes; {result['readable_pairs']} pairs have readable evidence. Counts: {result['counts']}.",
                 f"Seed: `{plan['seed']}`. Eligible groups: {plan['eligible_groups']}. Sample: {plan['sampled_by_corpus']}.", "",
                 summary + f". Uncertain includes {result['uninspectable_pairs']} uninspectable pair(s). These are this review's sample outcomes, not an independently verified accuracy estimate.",
                 "", result["limitations"], "", f"Reading coverage: {inspection['complete_stored_bodies_returned']} complete stored bodies, {inspection['partial_stored_bodies_returned']} partial bodies, {inspection['missing_stored_bodies']} withheld/missing. {inspection['available_source_quotes_found_in_windows']} quotations match inspected windows. Exact nonempty body duplicates: {result['exact_duplicate_body_pairs']} (corrected from the initial empty-placeholder comparison).",
                 "", "See report.json in this directory for per-pair quotations, source hashes, archive locators, and exact reading coverage.",
                 "", "| # | Corpus / eventUri | Judgment | Reason | Articles |", "|---|---|---|---|---|"]
        for row in rows:
            answer = row["judgment"] or {"label": "pending_or_failed", "rationale": "Not completed"}
            links = " / ".join(f"[{article['title']}]({article['url']})" for article in row["articles"])
            cells = [str(row["pair"]), row["corpus"] + " / " + row["event_uri"], answer["label"], answer["rationale"], links]
            lines.append("| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |")
        markdown = "\n".join(lines) + "\n"
        presentation = self.ledger.record(session, "provider_label_presentation", METHOD,
            {"result": result_id, "markdown": markdown, "destination": "private_file_and_codex_chat", "state": "prepared_for_delivery"})
        (self.ledger.root / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.ledger.root / "report.md").write_text(markdown, encoding="utf-8")
        return {key: result[key] for key in ("counts", "reviewed", "pending_or_failed", "unresolved_attempts", "readable_pairs", "uninspectable_pairs", "exact_duplicate_body_pairs", "by_corpus", "inspection")} | {
            "result": result_id, "presentation": presentation, "report": str(self.ledger.root / "report.md")}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "dispatch", "read", "submit", "report"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--seed", default=SEED)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--pairs", type=int, nargs="+")
    parser.add_argument("--reply-json")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=3000)
    args = parser.parse_args()
    payload = {"action": args.action}
    if args.action == "prepare":
        payload.update(data_root=str(args.data_root), seed=args.seed, count=args.count)
    if args.action in ("dispatch", "read"):
        payload["pairs"] = args.pairs
    if args.action == "read":
        payload.update(start=args.start, end=args.end)
    if args.action == "submit":
        payload["replies"] = json.loads(args.reply_json)
    engine = LabelAudit(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", payload, objective="Check a frozen random sample of NewsAPI.ai event labels using this Codex conversation", actor="codex:current-conversation-event-label-review")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
