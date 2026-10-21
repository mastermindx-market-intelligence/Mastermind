(() => {
  "use strict";
  const domains = [
    ["book_truth", "Book truth"], ["risk_truth", "Market risk"],
    ["market_structure", "Market structure"], ["independence", "Evidence independence"],
    ["factor_risk", "Factor risk"], ["candidate_geometry", "Opportunity geometry"],
    ["relationships", "Relationships"], ["fundamental_state", "Fundamentals"],
    ["positioning", "Positioning"], ["priceability", "Priceability"],
    ["event_state", "Events & catalysts"], ["historical_memory", "Decision history"]
  ];
  const el = id => document.getElementById(id);
  const human = value => String(value || "Unknown").replaceAll("_", " ").toLowerCase();
  let epoch = 0, controller = null, selected = null, activeDomain = "book_truth";
  let offset = 0, nextOffset = null, manifests = [];
  const PAGE_SIZE = 20;

  function status(label, detail, state) {
    el("status").textContent = label;
    el("status-detail").textContent = detail;
    el("status-panel").dataset.state = state;
  }
  function clearContent(message) {
    el("rows").replaceChildren(); el("gaps").replaceChildren(); el("source-refs").textContent = "";
    const p = document.createElement("p"); p.className = "empty-copy"; p.textContent = message;
    el("rows").append(p);
    el("page-label").textContent = "No rows loaded";
    el("domain-state").textContent = "Not loaded";
    el("domain-summary").textContent = "No section evidence is displayed.";
    el("previous-page").disabled = true; el("next-page").disabled = true;
    nextOffset = null;
  }
  function availability(enabled) {
    el("snapshot-select").disabled = !enabled;
    for (const b of el("domain-list").querySelectorAll("button")) b.disabled = !enabled;
  }
  function clearSnapshot() {
    selected = null; manifests = []; availability(false);
    el("snapshot-select").replaceChildren(new Option("No snapshot loaded", ""));
    for (const id of ["cutoff", "coverage", "source-count"]) el(id).textContent = "—";
    el("snapshot-id").textContent = "No identity loaded";
    el("recorded").textContent = "Recorded time unavailable";
    el("coverage-detail").textContent = "Unknown is not complete";
  }
  function begin() {
    if (controller) controller.abort();
    controller = new AbortController();
    epoch += 1;
    return {serial: epoch, signal: controller.signal};
  }
  async function request(params, signal) {
    const response = await fetch("/api/decision-snapshot?" + new URLSearchParams(params), {
      method: "GET", credentials: "same-origin", cache: "no-store", signal
    });
    if (!response.ok) {
      const error = new Error("Evidence request failed"); error.status = response.status; throw error;
    }
    const result = await response.json();
    if (!result || !["ABSENT", "AVAILABLE"].includes(result.status) ||
        result.authority?.write_permitted !== false || result.authority?.execution_authority !== false ||
        result.authority?.numeric_target_authority !== false) throw new Error("Invalid evidence response");
    return result;
  }
  function failure(error, serial) {
    if (serial !== epoch || error.name === "AbortError") return;
    clearSnapshot();
    if (error.status === 401 || error.status === 403) {
      status("Operator authorization required", "This session cannot read private evidence. The existing operator identity must authorize the request; no credentials are collected by this page.", "locked");
    } else if (error.status === 409) {
      status("Evidence integrity check failed", "A stored record could not be verified. No unverified or previously displayed evidence is shown.", "corrupt");
    } else if (error.status === 404) {
      status("Snapshot no longer available", "Refresh to inspect available evidence. A missing record is not an empty decision.", "blocked");
    } else {
      status("Evidence unavailable", "The request did not produce verified evidence. Refresh after the service or connection recovers.", "blocked");
    }
    clearContent("Evidence is hidden until a new authorized, verified read succeeds.");
  }
  function renderManifest(m) {
    if (!m || !/^sha256:[0-9a-f]{64}$/.test(m.snapshot_id) || !m.summary) throw new Error("Invalid manifest");
    selected = m;
    el("snapshot-id").textContent = m.snapshot_id;
    el("cutoff").textContent = m.decision_cutoff.replace("T", " ").replace("Z", "");
    el("recorded").textContent = "Recorded " + m.recorded_at;
    el("coverage").textContent = human(m.coverage_state);
    const s = m.summary;
    el("coverage-detail").textContent = `${s.domains_complete} complete · ${s.domains_partial} partial/unknown · ${s.domains_blocked} blocked`;
    el("source-count").textContent = `${s.sources_available} / ${s.sources_total}`;
    if (m.state === "CORRECTED_GENERATION_AVAILABLE") {
      status("Corrected generation", "This record preserves a correction at the same decision cutoff. Its predecessor remains immutable; coverage is shown separately.", "corrected");
    } else {
      status(human(m.coverage_state) + " evidence", "Preserved snapshot selected. A verified content address proves identity, not completeness, investment accuracy or execution authority.", String(m.coverage_state).toLowerCase());
    }
  }
  async function loadSection(newOffset = 0) {
    if (!selected) return;
    const id = selected.snapshot_id, domain = activeDomain;
    const {serial, signal} = begin(); offset = newOffset;
    for (const b of el("domain-list").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.domain === domain));
    el("domain-title").textContent = domains.find(([key]) => key === domain)[1];
    clearContent("Loading the selected evidence section…");
    try {
      const d = await request({book: "autonomous", snapshot_id: id, section: domain, offset: String(offset), limit: String(PAGE_SIZE)}, signal);
      if (serial !== epoch) return;
      const s = d.section;
      if (d.snapshot?.snapshot_id !== id || s?.snapshot_id !== id || s.section_id !== domain || !Array.isArray(s.rows) || !Array.isArray(s.gaps) || !Array.isArray(s.source_ids)) throw new Error("Evidence identity mismatch");
      if (s.next_offset !== null && (!Number.isInteger(s.next_offset) || s.next_offset <= offset || s.next_offset > 100)) throw new Error("Invalid evidence cursor");
      renderManifest(d.snapshot);
      el("domain-state").textContent = human(s.coverage_state);
      el("domain-summary").textContent = `${s.rows_total} source rows · ${s.stored_rows} preserved · ${s.omitted_rows} omitted from the stored section`;
      el("source-refs").textContent = s.source_ids.length ? "Source references: " + s.source_ids.join(" · ") : "No source references in this section";
      el("rows").replaceChildren(); el("gaps").replaceChildren();
      for (const gap of s.gaps) {
        const row = document.createElement("div"); row.className = "gap-item";
        row.textContent = `${gap.code || "UNKNOWN"} · ${gap.source_id || "unqualified source"} — ${gap.detail || "Coverage is unresolved"}`;
        el("gaps").append(row);
      }
      for (const [index, value] of s.rows.entries()) {
        const card = document.createElement("details"); card.className = "row-card"; card.open = index === 0;
        const title = document.createElement("summary");
        title.textContent = `${offset + index + 1}. ${String(value.ticker || value.kind || value.source_id || "Evidence record")}`;
        const pre = document.createElement("pre"); pre.textContent = JSON.stringify(value, null, 2);
        card.append(title, pre); el("rows").append(card);
      }
      if (!s.rows.length) {
        const p = document.createElement("p"); p.className = "empty-copy";
        p.textContent = "No preserved rows on this page. Consult the section's coverage gaps; absence is not evidence of safety."; el("rows").append(p);
      }
      nextOffset = s.next_offset;
      el("page-label").textContent = s.rows.length ? `Rows ${offset + 1}–${offset + s.rows.length} of ${s.stored_rows} preserved` : "No preserved rows";
      el("previous-page").disabled = offset === 0;
      el("next-page").disabled = nextOffset === null;
    } catch (error) { failure(error, serial); }
  }
  async function refresh() {
    const {serial, signal} = begin(); clearSnapshot(); clearContent("Checking existing evidence…");
    status("Loading evidence", "Checking this session and the existing snapshot store.", "loading");
    try {
      const d = await request({book: "autonomous", limit: "50"}, signal);
      if (serial !== epoch) return;
      if (d.status === "ABSENT") {
        status("No snapshot available", "The store contains no preserved evidence. This inspector does not generate data or substitute a demonstration snapshot.", "absent");
        clearContent("No decision evidence has been materialized for this book."); return;
      }
      if (!Array.isArray(d.snapshots) || d.snapshots.length === 0) throw new Error("Missing manifests");
      manifests = d.snapshots;
      el("snapshot-select").replaceChildren(...manifests.map(m => new Option(`${m.decision_cutoff} · ${human(m.state)}`, m.snapshot_id)));
      el("snapshot-select").value = d.snapshot.snapshot_id;
      renderManifest(d.snapshot); availability(true); await loadSection(0);
    } catch (error) { failure(error, serial); }
  }
  for (const [index, [key, label]] of domains.entries()) {
    const b = document.createElement("button"); b.type = "button"; b.dataset.domain = key;
    const n = document.createElement("span"); n.className = "number"; n.textContent = String(index + 1).padStart(2, "0");
    b.append(n, document.createTextNode(label)); b.setAttribute("aria-pressed", String(key === activeDomain)); b.disabled = true;
    b.addEventListener("click", () => {activeDomain = key; loadSection(0);}); el("domain-list").append(b);
  }
  el("snapshot-select").addEventListener("change", () => {
    const match = manifests.find(m => m.snapshot_id === el("snapshot-select").value);
    if (match) {renderManifest(match); loadSection(0);}
  });
  el("refresh").addEventListener("click", refresh);
  el("previous-page").addEventListener("click", () => loadSection(Math.max(0, offset - PAGE_SIZE)));
  el("next-page").addEventListener("click", () => {if (nextOffset !== null) loadSection(nextOffset);});
  el("theme-toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme !== "light";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    el("theme-toggle").textContent = dark ? "Dark theme" : "Light theme";
    el("theme-toggle").setAttribute("aria-label", dark ? "Switch to dark theme" : "Switch to light theme");
  });
  refresh();
})();
