"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { data: null, rows: [], visible: [], filter: "supported", search: "", savedOnly: false, unreadOnly: false, selected: null, saved: new Set(), read: new Set(), storageKey: "", storageAvailable: true };
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
  function move(offset) {
    const index = selectionIndex() + offset;
    if (index >= 0 && index < state.visible.length) select(rowId(state.visible[index]), true);
  }
  function select(id, scrollList = false) {
    state.selected = id;
    renderList(); renderDetail();
    if (scrollList) document.querySelector(".result-card.selected")?.scrollIntoView({ block: "nearest" });
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
    const oldIndex = selectionIndex();
    state.visible = state.rows.filter(row => (!state.savedOnly || state.saved.has(rowId(row))) && (!state.unreadOnly || !state.read.has(rowId(row))) && (state.filter === "all" || answerStatus(row) === state.filter) && (!state.search || row._search.includes(state.search)));
    if (!state.visible.some(row => rowId(row) === state.selected)) state.selected = state.visible[Math.min(Math.max(oldIndex, 0), state.visible.length - 1)] ? rowId(state.visible[Math.min(Math.max(oldIndex, 0), state.visible.length - 1)]) : null;
    document.querySelectorAll("[data-filter]").forEach(button => { const active = button.dataset.filter === state.filter; button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active)); });
    $("visible-count").textContent = `${state.visible.length} shown`;
    setProgress(); renderList(); renderDetail();
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
      const card = action("", () => { select(id); if (matchMedia("(max-width: 850px)").matches) $("article-detail").scrollIntoView({ block: "start" }); }, `result-card${selected ? " selected" : ""}`);
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
  async function load() {
    $("workspace").setAttribute("aria-busy", "true");
    try {
      const response = await fetch("/api/results", { cache: "no-store", credentials: "same-origin" });
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
      refresh(); announce(`${state.rows.length} saved answers loaded. Showing supported examples.`);
    } catch {
      const box = emptyState("The saved results could not be opened", "Keep the local server running and try again. No new research or model calls are needed.", "!"); box.classList.add("error-state"); box.append(action("Try again", load, "retry-button")); $("result-list").replaceChildren(box); $("visible-count").textContent = "Unavailable"; $("research-question").textContent = "The result is not currently available."; $("article-detail").replaceChildren(emptyState("Waiting for your saved results", "Once the local result is available, its answers and source links will appear here.")); announce("Could not load the saved results.");
    } finally { $("workspace").setAttribute("aria-busy", "false"); }
  }
  document.querySelectorAll("[data-filter]").forEach(button => button.addEventListener("click", () => { state.filter = button.dataset.filter; refresh(); }));
  $("search").addEventListener("input", event => { state.search = event.target.value.trim().toLocaleLowerCase(); refresh(); });
  $("saved-only").addEventListener("change", event => { state.savedOnly = event.target.checked; refresh(); });
  $("unread-only").addEventListener("change", event => { state.unreadOnly = event.target.checked; refresh(); });
  document.addEventListener("keydown", event => {
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
