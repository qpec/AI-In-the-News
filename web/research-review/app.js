"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { data: null, rows: [], visible: [], filter: "supported", search: "", savedOnly: false, unreadOnly: false, selected: null, saved: new Set(), read: new Set(), storageKey: "", storageAvailable: true, mobileView: "list", mobileListScroll: 0 };
  const mobileScreen = matchMedia("(max-width: 850px)");
  const conversation = { metadata: null, actor: "", job: null, timer: null, posting: false, pendingRequest: null, lastFocus: null, error: "", showTurnId: null };
  const labels = { supported: "Supported example", insufficient: "Insufficient evidence", uncertain: "Uncertain", unknown: "Unprocessed" };
  const node = (tag, className, text) => { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = String(text); return el; };
  const textValue = (value) => {
    if (value === null || value === undefined || value === "") return "";
    if (typeof value !== "object") return String(value);
    if (Array.isArray(value)) return value.map(textValue).filter(Boolean).join("; ");
    return Object.entries(value).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([key, val]) => `${key.replaceAll("_", " ")}: ${textValue(val)}`).join(" · ");
  };
  function answerStatus(row) {
    const raw = row.answer?.status ?? row.status;
    if (["supported", "yes", "supported_example"].includes(raw)) return "supported";
    if (["insufficient", "insufficient_evidence", "no"].includes(raw)) return "insufficient";
    if (["uncertain", "unclear"].includes(raw)) return "uncertain";
    return "unknown";
  }
  function rowId(row) { return String(row.result_id || row.source_version || `rank-${row.rank}`); }
  function safeUrl(raw) {
    if (typeof raw !== "string") return null;
    try { const url = new URL(raw); return ["https:", "http:"].includes(url.protocol) ? url : null; } catch { return null; }
  }
  function host(row) { return safeUrl(row.url)?.hostname.replace(/^www\./, "") || "Source link unavailable"; }
  function announce(message) { $("announcement").textContent = message; }
  function persist() {
    if (!state.storageAvailable) return;
    try { localStorage.setItem(state.storageKey, JSON.stringify({ saved: [...state.saved], read: [...state.read] })); }
    catch { state.storageAvailable = false; announce("Reading progress cannot be saved in this browser. It will last only for this visit."); }
  }
  function restore() {
    try {
      const stored = JSON.parse(localStorage.getItem(state.storageKey) || "{}");
      const ids = new Set(state.rows.map(rowId));
      state.saved = new Set(Array.isArray(stored.saved) ? stored.saved.filter(id => ids.has(id)) : []);
      state.read = new Set(Array.isArray(stored.read) ? stored.read.filter(id => ids.has(id)) : []);
    } catch { state.storageAvailable = false; announce("Reading progress is available for this visit only."); }
  }
  function setProgress() {
    $("progress-count").textContent = `${state.read.size} / ${state.rows.length}`;
    $("progress-label").textContent = state.storageAvailable ? "Marked as read" : "Read · this visit only";
    $("progress-bar").style.width = `${state.rows.length ? state.read.size / state.rows.length * 100 : 0}%`;
  }
  function badge(status) { return node("span", `pill pill-${status}`, labels[status]); }
  function action(label, fn, className = "action-button") { const button = node("button", className, label); button.type = "button"; button.addEventListener("click", fn); return button; }
  function selectionIndex() { return state.visible.findIndex(row => rowId(row) === state.selected); }
  function updateMobileControls() {
    const index = selectionIndex();
    $("mobile-list-count").textContent = String(state.visible.length);
    const position = index >= 0 ? `${index + 1} / ${state.visible.length}` : "—";
    $("mobile-answer-position").textContent = position;
    $("mobile-reading-position").textContent = position;
    $("mobile-answer-view").disabled = index < 0;
    $("mobile-prev").disabled = index <= 0;
    $("mobile-next").disabled = index < 0 || index >= state.visible.length - 1;
    $("mobile-list-view").setAttribute("aria-pressed", String(state.mobileView === "list"));
    $("mobile-answer-view").setAttribute("aria-pressed", String(state.mobileView === "detail"));
  }
  function showMobileView(view, focusContent = false) {
    if (!mobileScreen.matches || (view === "detail" && !state.selected)) return;
    if (state.mobileView === view) return;
    if (state.mobileView === "list") state.mobileListScroll = window.scrollY;
    state.mobileView = view;
    document.body.dataset.mobileView = view;
    updateMobileControls();
    if (focusContent) {
      if (view === "detail") $("article-detail").focus({ preventScroll: true });
      else document.querySelector(".result-card.selected")?.focus({ preventScroll: true });
    }
    window.scrollTo({ top: view === "list" ? state.mobileListScroll : 0, left: 0, behavior: "instant" });
  }
  function move(offset) {
    const index = selectionIndex() + offset;
    if (index >= 0 && index < state.visible.length) select(rowId(state.visible[index]), true);
  }
  function select(id, scrollList = false) {
    const changedArticle = id !== state.selected;
    state.selected = id;
    renderList(); renderDetail(); updateMobileControls();
    if (mobileScreen.matches && state.mobileView === "detail" && changedArticle) window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    else if (scrollList && !mobileScreen.matches) document.querySelector(".result-card.selected")?.scrollIntoView({ block: "nearest" });
  }
  function toggleSaved() {
    if (!state.selected) return;
    const wasSaved = state.saved.has(state.selected);
    if (wasSaved) state.saved.delete(state.selected); else state.saved.add(state.selected);
    persist(); refresh(); announce(wasSaved ? "Article removed from saved." : "Article saved.");
  }
  function toggleRead() {
    if (!state.selected) return;
    const wasRead = state.read.has(state.selected);
    if (wasRead) state.read.delete(state.selected); else state.read.add(state.selected);
    persist(); refresh(); announce(wasRead ? "Article marked unread." : "Article marked as read. This is reading progress, not research validation.");
  }
  function refresh() {
    const previousSelection = state.selected;
    const oldIndex = selectionIndex();
    state.visible = state.rows.filter(row => (!state.savedOnly || state.saved.has(rowId(row))) && (!state.unreadOnly || !state.read.has(rowId(row))) && (state.filter === "all" || answerStatus(row) === state.filter) && (!state.search || row._search.includes(state.search)));
    if (!state.visible.some(row => rowId(row) === state.selected)) state.selected = state.visible[Math.min(Math.max(oldIndex, 0), state.visible.length - 1)] ? rowId(state.visible[Math.min(Math.max(oldIndex, 0), state.visible.length - 1)]) : null;
    document.querySelectorAll("[data-filter]").forEach(button => { const active = button.dataset.filter === state.filter; button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active)); });
    $("visible-count").textContent = `${state.visible.length} shown`;
    setProgress(); renderList(); renderDetail(); updateMobileControls();
    if (mobileScreen.matches && state.mobileView === "detail" && state.selected !== previousSelection) window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }
  function emptyState(title, description, symbol = "↗") {
    const box = node("div", "empty-state");
    const icon = node("span", "empty-symbol", symbol); icon.setAttribute("aria-hidden", "true");
    box.append(icon, node("h2", "", title), node("p", "", description)); return box;
  }
  function renderList() {
    const list = $("result-list");
    const focusedCard = list.contains(document.activeElement) ? document.activeElement.closest(".result-card") : null;
    const focusedId = focusedCard?.dataset.resultId;
    const scrollTop = list.scrollTop;
    list.replaceChildren();
    if (!state.visible.length) { list.append(emptyState("No matching answers", "Try a different filter or a shorter search. Your original results are unchanged.", "⌕")); return; }
    const fragment = document.createDocumentFragment();
    state.visible.forEach(row => {
      const id = rowId(row), selected = id === state.selected;
      const card = action("", () => { select(id); showMobileView("detail", true); }, `result-card${selected ? " selected" : ""}`);
      card.dataset.testid = "result-card"; card.dataset.rank = String(row.rank); card.dataset.resultId = id; card.setAttribute("aria-current", selected ? "true" : "false");
      card.setAttribute("aria-label", `Rank ${row.rank}. ${row.title || "Untitled article"}. ${labels[answerStatus(row)]}${state.read.has(id) ? ". Read" : ""}${state.saved.has(id) ? ". Saved" : ""}`);
      const top = node("div", "card-top"); top.append(node("span", "rank", `#${String(row.rank).padStart(2, "0")}`), node("span", "similarity", `Similarity ${typeof row.score === "number" ? row.score.toFixed(4) : "unavailable"}`));
      const flags = node("span", "card-flags", `${state.saved.has(id) ? "◆" : ""}${state.read.has(id) ? "✓" : ""}`); flags.setAttribute("aria-hidden", "true"); top.append(flags);
      const bottom = node("div", "card-bottom"); bottom.append(node("span", "source-name", host(row)), badge(answerStatus(row)));
      card.append(top, node("span", "card-title", row.title || "Untitled article"), bottom); fragment.append(card);
    });
    list.append(fragment);
    list.scrollTop = scrollTop;
    if (focusedId) {
      const restoredCard = [...list.querySelectorAll(".result-card")].find(card => card.dataset.resultId === focusedId);
      (restoredCard || list.querySelector(".result-card.selected"))?.focus({ preventScroll: true });
    }
  }
  function fact(label, value, wide = false) {
    const box = node("div", `fact${wide ? " wide" : ""}`); box.append(node("h3", "", label));
    if (Array.isArray(value) && value.length) { const list = node("ul"); value.forEach(item => list.append(node("li", "", textValue(item)))); box.append(list); }
    else box.append(node("p", textValue(value) ? "" : "not-reported", textValue(value) || "Not established in this answer."));
    return box;
  }
  function renderDetail() {
    const pane = $("article-detail");
    const sameArticle = pane.querySelector(".detail-content")?.dataset.resultId === state.selected;
    const scrollTop = pane.scrollTop;
    const pageScroll = { left: window.scrollX, top: window.scrollY };
    const openDetails = sameArticle ? [...pane.querySelectorAll("details")].map(details => details.open) : [];
    const focusTargets = "button,a,summary";
    const focusedIndex = sameArticle && pane.contains(document.activeElement) ? [...pane.querySelectorAll(focusTargets)].indexOf(document.activeElement) : -1;
    pane.replaceChildren();
    const row = state.rows.find(item => rowId(item) === state.selected);
    if (!row) { pane.append(emptyState("Choose another view", "There are no articles in this selection. Adjust the filters to keep reading.")); return; }
    const answer = row.answer && typeof row.answer === "object" ? row.answer : {}, status = answerStatus(row), id = rowId(row), index = selectionIndex();
    const content = node("article", "detail-content"); content.dataset.testid = "article-answer"; content.dataset.resultId = id;
    const toolbar = node("div", "article-toolbar"), buttons = node("div", "toolbar-actions");
    toolbar.append(node("span", "article-position", `${index + 1} of ${state.visible.length} in this view`));
    const save = action(state.saved.has(id) ? "◆ Saved" : "◇ Save", toggleSaved, `action-button${state.saved.has(id) ? " is-on" : ""}`); save.id = "save-article"; save.setAttribute("aria-pressed", String(state.saved.has(id))); save.setAttribute("aria-label", "Save article");
    const read = action(state.read.has(id) ? "✓ Read" : "Mark read", toggleRead, `action-button${state.read.has(id) ? " is-on" : ""}`); read.id = "mark-read"; read.setAttribute("aria-pressed", String(state.read.has(id))); read.setAttribute("aria-label", "Mark article as read");
    const prev = action("←", () => move(-1), "nav-button"); prev.disabled = index <= 0; prev.setAttribute("aria-label", "Previous article");
    const next = action("→", () => move(1), "nav-button"); next.disabled = index >= state.visible.length - 1; next.setAttribute("aria-label", "Next article");
    buttons.append(save, read, prev, next); toolbar.append(buttons); content.append(toolbar);
    const meta = node("div", "article-meta"); meta.append(node("span", "", `RETRIEVAL RANK ${row.rank}`), node("span", "", "·"), node("span", "", `SIMILARITY ${typeof row.score === "number" ? row.score.toFixed(4) : "UNAVAILABLE"}`), badge(status)); content.append(meta);
    content.append(node("h2", "article-title", row.title || "Untitled article"));
    const url = safeUrl(row.url);
    if (url) { const link = node("a", "source-link", `Read original at ${host(row)} ↗`); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; content.append(link); }
    else content.append(node("span", "source-name", "Original source URL unavailable"));
    const panel = node("section", `answer-panel ${status}`); panel.append(node("h3", "section-label", "Model answer"), node("p", "answer-text", textValue(answer.answer) || "No completed model answer is available for this article."), node("p", "provisional-note", "Provisional · not human validated. Evidence records a source claim; it does not establish independent confirmation.")); content.append(panel);
    const facts = node("section", "fact-grid"); facts.setAttribute("aria-label", "Extracted details");
    facts.append(fact("Organization", answer.organization), fact("Organization members", answer.actors), fact("Specific decisions", answer.decisions, true), fact("AI incident", answer.incident, true), fact("Negative impact", answer.negative_impact, true), fact("Timing of decisions", answer.timing, true)); content.append(facts);
    const claims = Array.isArray(answer.claims) ? answer.claims : [];
    const evidence = node("section", "evidence-section"), evidenceTitle = node("div", "evidence-title"); evidenceTitle.append(node("h3", "", "Source evidence"), node("span", "", `${claims.length} cited passage${claims.length === 1 ? "" : "s"}`)); evidence.append(evidenceTitle);
    if (!claims.length) evidence.append(node("p", "provisional-note", "No supporting passage was supplied in this answer. Insufficient evidence is not proof that no decision or harm occurred."));
    claims.forEach((claim, i) => { const details = node("details"), supports = textValue(claim.supports); details.dataset.testid = "evidence-quote"; details.append(node("summary", "", `Evidence ${i + 1}${supports ? ` · ${supports}` : " · Source passage"}`)); const body = node("div", "quote-body"); body.append(node("blockquote", "", textValue(claim.quote) || "Quote unavailable."), node("p", "", `Passage ID: ${claim.passage_id || "Unavailable"}`)); details.append(body); evidence.append(details); }); content.append(evidence);
    const audit = node("details", "audit-details"); audit.append(node("summary", "", "Result provenance & score limitations")); const auditBody = node("div", "audit-content"), dl = node("dl");
    const fields = [["Result set", state.data.id || "Unavailable"], ["Article result", row.result_id || "Unavailable"], ["Source version", row.source_version || "Unavailable"], ["Assessment", row.assessment || "Unavailable"], ["Processing status", row.status || "Unavailable"], ["Inspected passages", Array.isArray(answer.inspected_passage_ids) ? answer.inspected_passage_ids.length : "Unavailable"], ["Research question", state.data.question || state.data.query || "Unavailable"]];
    fields.forEach(([label, value]) => dl.append(node("dt", "", label), node("dd", "", textValue(value)))); auditBody.append(dl, node("p", "provisional-note", "Similarity is a retrieval score, not a probability or evidence of correctness. This result set has no applied relevance cutoff or new relevance tags. Reading and saving here do not record a research review or accept findings.")); audit.append(auditBody); content.append(audit);
    const bottom = node("div", "detail-bottom"); bottom.append(node("span", "", "Saved and read indicators stay in this browser. They are not research assessments.")); const nextBottom = action("Next answer →", () => move(1)); nextBottom.disabled = index >= state.visible.length - 1; bottom.append(nextBottom); content.append(bottom);
    pane.append(content);
    if (sameArticle) {
      pane.querySelectorAll("details").forEach((details, index) => { details.open = Boolean(openDetails[index]); });
      pane.scrollTop = scrollTop;
      if (focusedIndex >= 0) pane.querySelectorAll(focusTargets)[focusedIndex]?.focus({ preventScroll: true });
      window.scrollTo({ ...pageScroll, behavior: "instant" });
    } else pane.scrollTop = 0;
  }
  function selectedConversationScope() { return document.querySelector("input[name='conversation-scope']:checked").value; }
  function newRequestId() {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  function updateConversationForm() {
    const meta = conversation.metadata;
    const bounded = Number.isInteger(meta?.max_attempts) && meta.max_attempts > 0;
    const enabled = meta?.enabled === true && bounded;
    const busy = conversation.posting || Boolean(conversation.job) || Boolean(conversation.pendingRequest);
    $("conversation-form").hidden = !enabled;
    $("conversation-disabled").hidden = enabled;
    if (!enabled && meta) $("conversation-disabled-reason").textContent = meta.enabled === true && !bounded ? "This server has not supplied a bounded model-run configuration. The saved answers remain available to read." : "Audited follow-ups are not enabled on this server. You can continue browsing the saved answers.";
    const canSearch = enabled && meta.search_supported === true && meta.search_method === "local_fts";
    $("conversation-search-scope").disabled = !canSearch || busy;
    if (!canSearch) document.querySelector("input[name='conversation-scope'][value='current']").checked = true;
    document.querySelector("input[name='conversation-scope'][value='current']").disabled = busy;
    const scope = selectedConversationScope();
    $("conversation-query-field").hidden = scope !== "search";
    $("conversation-scope-note").textContent = scope === "search" ? "Runs a new local keyword search of the corpus and selects at most 20 articles. This uses no new embedding. Only submitting below starts the search." : `Reuses the latest retrieval within a bounded context, with coverage reported in the answer. No new corpus search or embedding.${canSearch ? "" : " New corpus searches are unavailable on this server."}`;
    const needsActor = !conversation.actor;
    $("conversation-actor-field").hidden = !needsActor;
    $("conversation-actor").required = enabled && needsActor;
    ["conversation-question", "conversation-query", "conversation-actor"].forEach(id => { $(id).disabled = busy; });
    $("conversation-submit").disabled = !enabled || busy;
    $("conversation-submit").replaceChildren(document.createTextNode(busy ? "Request in progress" : "Ask Codex"), node("span", "", busy ? "⋯" : "↑"));
    $("conversation-authorization").textContent = `Submitting authorizes up to ${bounded ? meta.max_attempts : "the configured number of"} audited Codex account answer attempt${meta?.max_attempts === 1 ? "" : "s"} using the chosen evidence scope. No paid API or new embedding request.`;
    $("conversation-context").textContent = meta ? "Follow-ups use the current retrieval, including your latest explicit search. Each result shows available citations, coverage and audit references." : "Checking whether audited follow-ups are available…";
  }
  function conversationError(message, retryRequest = false) {
    const box = $("conversation-error"); box.replaceChildren(node("span", "", message)); box.hidden = !message;
    if (retryRequest && conversation.pendingRequest) box.append(action("Retry the same request", () => sendConversationRequest(conversation.pendingRequest), "conversation-check-status"));
    else if (message && conversation.job) box.append(action("Check request status", () => pollConversation(conversation.job.job_id), "conversation-check-status"));
  }
  function jobStatus(message) { $("conversation-job-status").textContent = message; $("conversation-job-status").hidden = !message; }
  function conversationCitation(citation, index) {
    const details = node("details", "conversation-citation");
    details.append(node("summary", "", `Source ${index + 1} · ${citation.title || "Cited passage"}`));
    const body = node("div", "quote-body"), url = safeUrl(citation.url);
    if (url) { const link = node("a", "source-link", `Read source at ${url.hostname.replace(/^www\./, "")} ↗`); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; body.append(link); }
    body.append(node("blockquote", "", citation.quote || "No quote supplied."), node("p", "", `Passage: ${citation.passage_id || "Unavailable"}${citation.source_version ? ` · Source version: ${citation.source_version}` : ""}`));
    details.append(body); return details;
  }
  function conversationTurn(turn, index) {
    const article = node("article", "conversation-turn"); article.dataset.turnId = String(turn.id || index); article.dataset.testid = "conversation-turn";
    article.append(node("p", "conversation-question", turn.question || "Question unavailable."));
    if (typeof turn.retrieval?.markdown === "string") {
      const retrieval = node("details", "conversation-retrieval-report"); retrieval.open = true;
      retrieval.append(node("summary", "", "Recorded search results · query, scope and ranked matches"), node("pre", "conversation-recorded-markdown", turn.retrieval.markdown));
      article.append(retrieval);
    } else if (turn.scope === "search") article.append(node("p", "conversation-turn-note", "The recorded search overview is unavailable in this response. Search results have not been reconstructed; see the audit references."));
    const answer = turn.answer && typeof turn.answer === "object" ? turn.answer : {};
    const answerLabels = { answered: "Source-grounded answer", needs_retrieval: "More evidence needed", uncertain: "Uncertain" };
    const heading = node("div", "conversation-answer-heading"); heading.append(node("strong", "", "Codex"), node("span", `pill${answer.status === "answered" ? " pill-supported" : " pill-uncertain"}`, answerLabels[answer.status] || "No completed answer")); article.append(heading);
    article.append(node("p", "conversation-turn-answer", answer.answer || "No validated model answer is available for this request."));
    const evidenceMode = node("div", "conversation-evidence-mode");
    evidenceMode.append(node("span", "", turn.scope === "search" ? "New local keyword retrieval" : turn.scope === "current" ? "Current retrieval reused" : "Evidence scope unavailable"));
    if (turn.evidence_mode) evidenceMode.append(node("span", "", `Mode: ${textValue(turn.evidence_mode)}`)); article.append(evidenceMode);
    const citations = Array.isArray(answer.citations) ? answer.citations : [];
    citations.forEach((citation, citationIndex) => article.append(conversationCitation(citation, citationIndex)));
    if (!citations.length) article.append(node("p", "conversation-turn-note", "No source citations were supplied. Missing evidence is not a negative finding."));
    if (answer.suggested_query) {
      const suggestion = node("div", "conversation-suggested-query"); suggestion.append(node("p", "", `Suggested query: ${answer.suggested_query}`));
      if (conversation.metadata?.search_supported && conversation.metadata?.search_method === "local_fts") suggestion.append(action("Prepare this search", () => { $("conversation-search-scope").checked = true; $("conversation-query").value = answer.suggested_query; if (!$("conversation-question").value.trim()) $("conversation-question").value = turn.question || ""; updateConversationForm(); $("conversation-query").focus(); }, "action-button"));
      article.append(suggestion);
    }
    if (typeof turn.presentation?.markdown === "string") {
      const recorded = node("details", "conversation-recorded-presentation");
      recorded.append(node("summary", "", "Exact recorded answer presentation"), node("pre", "conversation-recorded-markdown", turn.presentation.markdown)); article.append(recorded);
    }
    const provenance = node("details", "conversation-coverage"); provenance.append(node("summary", "", "Evidence coverage & audit references")); const dl = node("dl");
    const withoutMarkdown = value => { if (!value || typeof value !== "object") return value; const metadata = Object.fromEntries(Object.entries(value).filter(([key]) => key !== "markdown")); return Object.keys(metadata).length ? metadata : "Unavailable"; };
    const entries = [["Turn ID", turn.id || "Unavailable"], ["Initial result", conversation.metadata?.initial_result_id || "Unavailable"], ["Processing status", turn.status || "Unavailable"], ["Coverage", turn.coverage || "Unavailable"], ["Audit", turn.audit || "Unavailable"], ["Retrieval", withoutMarkdown(turn.retrieval) || "Unavailable"], ["Presentation", withoutMarkdown(turn.presentation) || "Unavailable"], ["Inspected passages", Array.isArray(answer.inspected_passage_ids) ? answer.inspected_passage_ids.length : "Unavailable"]];
    entries.forEach(([key, value]) => dl.append(node("dt", "", key), node("dd", "", textValue(value)))); provenance.append(dl); article.append(provenance, node("p", "conversation-turn-note", "Provisional model answer · not human validated. Source citations preserve reported claims; they do not independently confirm them."));
    return article;
  }
  function renderConversation() {
    const thread = $("conversation-thread"), scrollTop = thread.scrollTop, nearBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
    const existingTurns = new Set([...thread.querySelectorAll(".conversation-turn")].map(turn => turn.dataset.turnId));
    const expanded = new Set([...thread.querySelectorAll("details[open]")].map(details => `${details.closest(".conversation-turn")?.dataset.turnId}:${[...details.parentElement.querySelectorAll("details")].indexOf(details)}`));
    thread.replaceChildren();
    const turns = Array.isArray(conversation.metadata?.turns) ? conversation.metadata.turns : [];
    if (turns.length) turns.forEach((turn, index) => thread.append(conversationTurn(turn, index)));
    else thread.append(emptyState("Ask what comes next.", conversation.metadata?.history_loaded === false ? "Earlier saved conversation history, if present, loads with your first submitted request. No new research runs until you submit." : "Follow up on the current evidence, or explicitly request a new local keyword search. Nothing runs until you submit.", "↗"));
    thread.querySelectorAll("details").forEach(details => { const turnId = details.closest(".conversation-turn")?.dataset.turnId; const key = `${turnId}:${[...details.parentElement.querySelectorAll("details")].indexOf(details)}`; if (existingTurns.has(turnId)) details.open = expanded.has(key); });
    const latestTurn = [...thread.querySelectorAll(".conversation-turn")].at(-1);
    if (conversation.showTurnId) {
      showNewConversationTurn();
    } else if (nearBottom && latestTurn && !existingTurns.has(latestTurn.dataset.turnId)) {
      conversation.showTurnId = latestTurn.dataset.turnId;
      showNewConversationTurn();
    } else thread.scrollTop = scrollTop;
    updateConversationForm();
  }
  function showNewConversationTurn() {
    if (!conversation.showTurnId || !$("conversation-dialog").open) return;
    const thread = $("conversation-thread"), turn = [...thread.querySelectorAll(".conversation-turn")].find(item => item.dataset.turnId === conversation.showTurnId);
    if (turn) thread.scrollTop += turn.getBoundingClientRect().top - thread.getBoundingClientRect().top - 14;
    conversation.showTurnId = null;
  }
  async function loadConversation() {
    try {
      const response = await fetch("/api/conversation", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("Conversation unavailable");
      const metadata = await response.json();
      conversation.metadata = metadata;
      if (typeof metadata.actor === "string" && metadata.actor.trim()) conversation.actor = metadata.actor.trim();
      renderConversation();
      if (metadata.pending?.job_id && ["queued", "running"].includes(metadata.pending.status) && !conversation.job) {
        conversation.job = metadata.pending; updateConversationForm(); pollConversation(metadata.pending.job_id);
      }
      return true;
    } catch {
      if (!conversation.metadata) conversation.metadata = { enabled: false };
      renderConversation();
      $("conversation-disabled-reason").textContent = "The conversation service is unavailable. Your saved article answers are still available to read.";
      return false;
    } finally { $("open-conversation").disabled = false; }
  }
  async function pollConversation(jobId) {
    if (!jobId) return;
    if (conversation.timer) { clearTimeout(conversation.timer); conversation.timer = null; }
    try {
      const response = await fetch(`/api/conversation/jobs/${encodeURIComponent(jobId)}`, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("Request status unavailable");
      const job = await response.json();
      if (["queued", "running"].includes(job.status)) {
        conversation.job = { ...job, job_id: jobId };
        jobStatus(job.status === "queued" ? "Request queued. No additional question has been submitted." : "Audited research request running. You can continue reading while it finishes.");
        conversationError(""); updateConversationForm();
        conversation.timer = setTimeout(() => pollConversation(jobId), 3000);
      } else if (job.status === "completed") {
        conversation.job = null; jobStatus(""); conversationError("");
        if (job.result?.id) conversation.showTurnId = String(job.result.id);
        const refreshed = await loadConversation();
        if (!refreshed && job.result) {
          const turns = Array.isArray(conversation.metadata?.turns) ? conversation.metadata.turns : [];
          conversation.metadata = { ...conversation.metadata, turns: [...turns.filter(turn => turn.id !== job.result.id), job.result] }; renderConversation();
        }
        announce("Your follow-up result is ready in the conversation.");
      } else if (job.status === "failed") {
        conversation.job = null; jobStatus(""); await loadConversation();
        conversationError(`The audited request failed${job.error_type ? ` (${String(job.error_type)})` : ""}. No completed answer has been assumed. Check the saved coverage and audit references before retrying.`); updateConversationForm();
      } else throw new Error("Unknown request status");
    } catch {
      jobStatus("Request outcome is currently unknown.");
      conversationError("The request status could not be checked. No automatic model retry was made; check this same request's status."); updateConversationForm();
    }
  }
  async function sendConversationRequest(packet) {
    if (!packet || conversation.posting) return;
    conversation.posting = true; conversation.pendingRequest = packet; conversationError(""); updateConversationForm();
    try {
      const response = await fetch("/api/conversation", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", cache: "no-store", body: JSON.stringify(packet) });
      if (!response.ok) {
        if (response.status >= 400 && response.status < 500) { conversation.pendingRequest = null; conversationError(response.status === 401 ? "Open the pairing page on your computer and scan its QR code." : "The server did not accept this request. Check your question, actor and selected scope before submitting again."); return; }
        throw new Error("Request acknowledgement unavailable");
      }
      const result = await response.json();
      if (typeof result.job_id !== "string" || !result.job_id) throw new Error("Request acknowledgement unavailable");
      conversation.actor = packet.actor; conversation.pendingRequest = null; conversation.job = { job_id: result.job_id, status: "queued" };
      $("conversation-question").value = ""; $("conversation-query").value = "";
      jobStatus("Request queued. The chosen scope and question will be recorded with the answer.");
      pollConversation(result.job_id);
    } catch {
      jobStatus("Request acknowledgement is currently unknown.");
      conversationError("The connection ended before acknowledgement. A retry uses this exact request ID; it does not submit a new question.", true);
    } finally { conversation.posting = false; updateConversationForm(); }
  }
  function submitConversation(event) {
    event.preventDefault();
    if (conversation.metadata?.enabled !== true || conversation.posting || conversation.job || conversation.pendingRequest) return;
    const question = $("conversation-question").value.trim(), actor = conversation.actor || $("conversation-actor").value.trim();
    if (!question || !actor) { if (!actor) $("conversation-actor").focus(); else $("conversation-question").focus(); return; }
    const scope = selectedConversationScope();
    if (scope === "search" && !(conversation.metadata.search_supported && conversation.metadata.search_method === "local_fts")) return;
    const packet = { request_id: newRequestId(), question, scope, actor, confirm_model: true };
    if (scope === "search" && $("conversation-query").value.trim()) packet.query = $("conversation-query").value.trim();
    sendConversationRequest(packet);
  }
  async function load() {
    $("workspace").setAttribute("aria-busy", "true");
    let pairingRequired = false;
    try {
      const pairingKey = new URLSearchParams(window.location.hash.slice(1)).get("pair");
      if (pairingKey !== null) {
        history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
        pairingRequired = true;
        const paired = await fetch("/api/pair", { method: "POST", headers: { "Content-Type": "text/plain" }, body: pairingKey, credentials: "same-origin", cache: "no-store" });
        if (paired.status !== 200) throw new Error("Pairing failed");
        pairingRequired = false;
      }
      const response = await fetch("/api/results", { cache: "no-store", credentials: "same-origin" });
      if (response.status === 401) pairingRequired = true;
      if (!response.ok) throw new Error("Result unavailable");
      const data = await response.json();
      if (!data || !Array.isArray(data.rows)) throw new Error("Invalid result structure");
      state.data = data; state.rows = data.rows.map(row => ({ ...row, _search: `${row.title || ""} ${host(row)} ${textValue(row.answer)}`.toLocaleLowerCase() })).sort((a, b) => Number(a.rank) - Number(b.rank));
      state.storageKey = `ai-news-reading:${String(data.id || "saved-results")}`; restore();
      $("research-question").textContent = data.question || data.query || "Research question unavailable.";
      const number = value => typeof value === "number" ? value.toLocaleString("en-GB") : "unavailable";
      $("scope").textContent = `Saved RAG run · ${number(data.expected_articles)} articles in scope · ${number(data.scored_articles)} scored · ${number(data.missing_scores)} without scores. Browsing does not run new inference.`;
      const computed = { supported: 0, insufficient: 0, uncertain: 0 }; state.rows.forEach(row => { const status = answerStatus(row); if (Object.hasOwn(computed, status)) computed[status]++; });
      const counts = { supported: data.counts?.supported ?? computed.supported, insufficient: data.counts?.insufficient ?? data.counts?.insufficient_evidence ?? computed.insufficient, uncertain: data.counts?.uncertain ?? computed.uncertain, all: state.rows.length };
      $("stat-total").textContent = number(state.rows.length); ["supported", "insufficient", "uncertain"].forEach(key => { $(`stat-${key}`).textContent = number(counts[key]); });
      document.querySelectorAll("[data-count]").forEach(el => { el.textContent = String(counts[el.dataset.count]); });
      refresh(); announce(`${state.rows.length} saved answers loaded. Showing supported examples.`); loadConversation();
    } catch {
      const title = pairingRequired ? "Pair this device to continue" : "The saved results could not be opened";
      const instruction = pairingRequired ? "Open the pairing page on your computer and scan its QR code." : "Keep the local server running and try again. No new research or model calls are needed.";
      const box = emptyState(title, instruction, "!"); box.classList.add("error-state"); box.append(action("Try again", load, "retry-button")); $("result-list").replaceChildren(box); $("visible-count").textContent = "Unavailable"; $("research-question").textContent = pairingRequired ? instruction : "The result is not currently available."; $("article-detail").replaceChildren(emptyState("Waiting for your saved results", instruction)); announce(pairingRequired ? instruction : "Could not load the saved results.");
    } finally { $("workspace").setAttribute("aria-busy", "false"); }
  }
  document.querySelectorAll("[data-filter]").forEach(button => button.addEventListener("click", () => { state.filter = button.dataset.filter; refresh(); }));
  $("search").addEventListener("input", event => { state.search = event.target.value.trim().toLocaleLowerCase(); refresh(); });
  $("saved-only").addEventListener("change", event => { state.savedOnly = event.target.checked; refresh(); });
  $("unread-only").addEventListener("change", event => { state.unreadOnly = event.target.checked; refresh(); });
  $("mobile-list-view").addEventListener("click", () => showMobileView("list", true));
  $("mobile-answer-view").addEventListener("click", () => showMobileView("detail", true));
  $("mobile-back-list").addEventListener("click", () => showMobileView("list", true));
  $("mobile-prev").addEventListener("click", () => move(-1));
  $("mobile-next").addEventListener("click", () => move(1));
  $("open-conversation").addEventListener("click", () => { conversation.lastFocus = document.activeElement; $("conversation-dialog").showModal(); document.body.classList.add("conversation-open"); if (conversation.metadata?.enabled) (conversation.actor ? $("conversation-question") : $("conversation-actor")).focus(); else { $("close-conversation").focus(); loadConversation(); } showNewConversationTurn(); });
  $("close-conversation").addEventListener("click", () => $("conversation-dialog").close());
  $("conversation-dialog").addEventListener("close", () => { document.body.classList.remove("conversation-open"); conversation.lastFocus?.focus({ preventScroll: true }); });
  $("conversation-form").addEventListener("submit", submitConversation);
  document.querySelectorAll("input[name='conversation-scope']").forEach(input => input.addEventListener("change", updateConversationForm));
  mobileScreen.addEventListener("change", () => {
    updateMobileControls();
    if (!mobileScreen.matches) return;
    if (state.mobileView === "list" && $("article-detail").contains(document.activeElement)) $("mobile-list-view").focus({ preventScroll: true });
    else if (state.mobileView === "detail" && document.querySelector(".results-pane").contains(document.activeElement)) $("article-detail").focus({ preventScroll: true });
  });
  document.addEventListener("keydown", event => {
    if ($("conversation-dialog").open) return;
    if (event.ctrlKey || event.metaKey || event.altKey || event.target.closest("input,textarea,select,button,a,summary,[contenteditable='true']")) return;
    const key = event.key.toLowerCase();
    if (key === "/") { event.preventDefault(); $("search").focus(); }
    else if (key === "j") { event.preventDefault(); move(1); }
    else if (key === "k") { event.preventDefault(); move(-1); }
    else if (key === "s") { event.preventDefault(); toggleSaved(); }
    else if (key === "r") { event.preventDefault(); toggleRead(); }
  });
  load();
})();
