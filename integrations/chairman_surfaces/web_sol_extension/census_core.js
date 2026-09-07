"use strict";

// A popup-local, non-authoritative reader. It never writes browser or native state.
(function expose(root) {
  const MAX_TABS = 128;
  const MAX_INVENTORY = 4096;
  const CONCURRENCY = 8;
  const CALL_MS = 800;
  const SWEEP_MS = 5000;
  const SCHEMA = "mastermind.web_sol_local_census.v1";
  // Popup-lifetime backpressure for collector-issued reads: one count per API object,
  // no target map, saved observation, queue, retry or lifecycle state. A timeout
  // never releases a still-pending read. Closing the view drops this local count.
  const pendingReads = new WeakMap();
  const NO_SLOT = Symbol("no-read-slot");
  function readBrowser(tabs, call) {
    const pending = pendingReads.get(tabs) || 0;
    if (pending >= CONCURRENCY) return NO_SLOT;
    pendingReads.set(tabs, pending + 1);
    return Promise.resolve().then(call).finally(() => {
      pendingReads.set(tabs, Math.max(0, (pendingReads.get(tabs) || 0) - 1));
    });
  }
  function readProbe(tabs, id, request) {
    return readBrowser(tabs, () => tabs.sendMessage(id, request, {frameId: 0}));
  }
  const PATTERNS = Object.freeze(["https://chatgpt.com/*", "https://chat.openai.com/*"]);
  const HEX = /^[0-9a-f]{64}$/;
  const CHAT_PATH = /^(?:\/c\/[^/]+|\/g\/g-p-[A-Za-z0-9_-]+\/c\/[^/]+)\/?$/;
  const OBSERVATION_KEYS = Object.freeze([
    "schema", "target_present", "exact_conversation_loaded", "page_responsive",
    "document_ready_state", "visibility", "composer_available", "generation_state",
    "auth_required", "provider_error_present",
  ]);
  const monotonic = () => performance.now();
  const timestamp = () => new Date().toISOString();
  const booleanOrNull = value => typeof value === "boolean" ? value : null;
  const plain = value => value !== null && typeof value === "object" && !Array.isArray(value);
  function exactKeys(value, keys) {
    return plain(value) && Object.keys(value).length === keys.length &&
      keys.every(key => Object.prototype.hasOwnProperty.call(value, key));
  }
  function validTab(value) {
    return plain(value) && Number.isSafeInteger(value.id) && value.id >= 0 &&
      Number.isSafeInteger(value.windowId) && value.windowId >= 0;
  }
  function locator(value) {
    if (typeof value !== "string" || value.length > 4096) return null;
    try {
      const u = new URL(value);
      if (u.protocol !== "https:" || u.username || u.password ||
          !["https://chatgpt.com", "https://chat.openai.com"].includes(u.origin)) return null;
      const pathname = u.pathname.endsWith("/") ? u.pathname.slice(0, -1) : u.pathname;
      return {canonical: `https://chatgpt.com${pathname}`, conversation: CHAT_PATH.test(u.pathname)};
    } catch (_) { return null; }
  }
  async function fingerprint(value) {
    const bytes = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
  }
  // Late results are discarded; this function neither retries nor cancels a browser action.
  function bounded(call, ms) {
    if (ms <= 0) return Promise.resolve({ok: false, timeout: true});
    return new Promise(resolve => {
      let settled = false;
      const finish = value => {
        if (settled) return;
        settled = true; clearTimeout(timer); resolve(value);
      };
      const timer = setTimeout(() => finish({ok: false, timeout: true}), ms);
      Promise.resolve().then(call).then(
        value => finish({ok: true, value}),
        () => finish({ok: false, timeout: false}),
      );
    });
  }
  function blankRow(t, slot) {
    const safe = plain(t) ? t : {};
    return {
      slot, conversation_fingerprint: null, identity_evidence: "UNVERIFIED",
      document_binding: "UNVERIFIED", status: "SWEEP_DEADLINE", generation_cue: "UNKNOWN",
      selected_in_window: booleanOrNull(safe.active), discarded: booleanOrNull(safe.discarded),
      frozen: booleanOrNull(safe.frozen), visibility: "UNKNOWN", auth_required: null,
      provider_error_present: null, duplicate_count: 1, duplicate_cue_disagreement: false, observed_at: null,
      selected_model: null, selected_effort: null, served_model: null, model_evidence: "UNVERIFIED",
    };
  }
  function validProbe(p) {
    if (!exactKeys(p, ["kind", "conversation_fingerprint", "observation"]) ||
        p.kind !== "MMX_WEB_SOL_PROBE" || !HEX.test(p.conversation_fingerprint)) return false;
    const o = p.observation;
    if (!exactKeys(o, OBSERVATION_KEYS) || o.schema !== "mastermind.web_sol_surface_probe.v1") return false;
    if (!["target_present", "exact_conversation_loaded", "page_responsive"].every(k => typeof o[k] === "boolean")) return false;
    if (!["loading", "interactive", "complete"].includes(o.document_ready_state) ||
        !["visible", "hidden"].includes(o.visibility) ||
        !["active", "idle", "unknown"].includes(o.generation_state)) return false;
    return ["composer_available", "auth_required", "provider_error_present"].every(k =>
      o[k] === null || typeof o[k] === "boolean");
  }
  function sameLocator(a, b) {
    if (!validTab(a) || !validTab(b) || a.id !== b.id || a.windowId !== b.windowId ||
        a.incognito === true || b.incognito === true) return false;
    const one = locator(a.url), two = locator(b.url);
    return Boolean(one && two && one.canonical === two.canonical && !a.pendingUrl && !b.pendingUrl);
  }
  function sleepState(t) {
    if (t.pendingUrl) return "NAVIGATING";
    if (t.discarded === true) return "DISCARDED";
    if (t.frozen === true) return "FROZEN";
    if (t.status !== "complete") return "LOADING";
    return null;
  }
  async function observe(t, slot, tabs, deadline, duplicatedId) {
    const row = blankRow(t, slot);
    const call = fn => bounded(fn, Math.min(CALL_MS, deadline - monotonic()));
    if (!validTab(t) || duplicatedId) { row.status = "INVALID_TAB"; return row; }
    const initial = locator(t.url);
    if (!initial) { row.status = "OUT_OF_SCOPE"; return row; }
    if (!initial.conversation) { row.status = "NOT_A_CONVERSATION"; return row; }
    const digest = await call(() => fingerprint(initial.canonical));
    if (!digest.ok) return row;
    row.conversation_fingerprint = digest.value; row.identity_evidence = "BROWSER_LOCATOR";
    const asleep = sleepState(t);
    if (asleep) { row.status = asleep; return row; }
    const before = await call(() => readBrowser(tabs, () => tabs.get(t.id)));
    if (!before.ok) { row.status = before.timeout ? "SWEEP_DEADLINE" : "LOOKUP_UNAVAILABLE"; return row; }
    if (before.value === NO_SLOT) { row.status = "PROBE_SLOTS_EXHAUSTED"; return row; }
    if (!sameLocator(t, before.value)) { row.status = "TARGET_CHANGED"; return row; }
    const nowAsleep = sleepState(before.value);
    if (nowAsleep) { row.status = nowAsleep; return row; }
    const reply = await call(() => readProbe(tabs, t.id, {
      kind: "MMX_WEB_SOL_REPROBE", expected_conversation_fingerprint: digest.value,
    }));
    if (!reply.ok) { row.status = reply.timeout ? "PROBE_TIMEOUT" : "PROBE_UNAVAILABLE"; return row; }
    if (reply.value === NO_SLOT) { row.status = "PROBE_SLOTS_EXHAUSTED"; return row; }
    if (!validProbe(reply.value)) { row.status = "INVALID_PROBE"; return row; }
    const p = reply.value, o = p.observation;
    if (p.conversation_fingerprint !== digest.value || !o.target_present || !o.exact_conversation_loaded) {
      row.status = "TARGET_CHANGED"; return row;
    }
    if (!o.page_responsive || o.document_ready_state !== "complete") { row.status = "LOADING"; return row; }
    const after = await call(() => readBrowser(tabs, () => tabs.get(t.id)));
    if (!after.ok) { row.status = after.timeout ? "SWEEP_DEADLINE" : "LOOKUP_UNAVAILABLE"; return row; }
    if (after.value === NO_SLOT) { row.status = "PROBE_SLOTS_EXHAUSTED"; return row; }
    if (!sameLocator(before.value, after.value) || sleepState(after.value)) { row.status = "TARGET_CHANGED"; return row; }
    row.status = "OBSERVED"; row.identity_evidence = "LOCATOR_AND_V1_PROBE";
    // A v1 probe does not bind a Chrome documentId. Never promote this to a document or runtime attestation.
    row.generation_cue = o.generation_state === "active" ? "PRESENT" :
      o.generation_state === "idle" && o.composer_available === true ? "NOT_OBSERVED" : "UNKNOWN";
    row.visibility = o.visibility.toUpperCase(); row.selected_in_window = booleanOrNull(after.value.active);
    row.auth_required = o.auth_required; row.provider_error_present = o.provider_error_present;
    row.observed_at = timestamp();
    return row;
  }
  function inventory(rows) {
    const normal = rows.filter(t => !plain(t) || t.incognito !== true);
    const ids = new Map();
    for (const t of normal) if (validTab(t)) ids.set(t.id, (ids.get(t.id) || 0) + 1);
    const malformed = normal.some(t => !validTab(t) || ids.get(t.id) !== 1 || !locator(t.url));
    normal.sort((a, b) => (validTab(a) ? a.id : Number.MAX_SAFE_INTEGER) -
      (validTab(b) ? b.id : Number.MAX_SAFE_INTEGER));
    return {normal, ids, malformed, excluded: rows.length - normal.length};
  }
  // Private comparison material never leaves this call or enters a receipt, storage, or log.
  function signature(rows) {
    return JSON.stringify(rows.map(t => validTab(t) ? [t.id, t.windowId, t.url,
      t.pendingUrl || null, booleanOrNull(t.discarded), booleanOrNull(t.frozen), t.status || null] : null));
  }
  function invalidate(row) {
    row.status = "TARGET_CHANGED"; row.generation_cue = "UNKNOWN";
    row.identity_evidence = "UNVERIFIED"; row.conversation_fingerprint = null;
    row.observed_at = null; row.visibility = "UNKNOWN"; row.selected_in_window = null;
    row.auth_required = null; row.provider_error_present = null;
  }
  function summarize(out) {
    const groups = new Map();
    for (const row of out.rows) if (row.conversation_fingerprint)
      groups.set(row.conversation_fingerprint, (groups.get(row.conversation_fingerprint) || 0) + 1);
    const cues = new Map();
    for (const row of out.rows) if (row.conversation_fingerprint && row.generation_cue !== "UNKNOWN") {
      if (!cues.has(row.conversation_fingerprint)) cues.set(row.conversation_fingerprint, new Set());
      cues.get(row.conversation_fingerprint).add(row.generation_cue);
    }
    for (const row of out.rows) {
      row.duplicate_count = groups.get(row.conversation_fingerprint) || 1;
      row.duplicate_cue_disagreement = (cues.get(row.conversation_fingerprint) || new Set()).size > 1;
    }
    out.unique_conversation_count = groups.size;
    out.duplicate_tab_count = Array.from(groups.values()).reduce((n, count) => n + count - 1, 0);
    out.probed_tab_count = out.rows.filter(r => r.status === "OBSERVED").length;
    out.generation_cue_count = out.rows.filter(r => r.generation_cue === "PRESENT").length;
    out.unknown_cue_count = out.rows.filter(r => r.generation_cue === "UNKNOWN").length;
    out.probe_coverage = out.probed_tab_count === 0 ? "NONE" :
      out.probed_tab_count === out.initial_tab_count ? "COMPLETE_IN_SCOPE" : "PARTIAL";
    return out;
  }
  async function collect(tabs, instanceId) {
    const start = monotonic();
    const out = {
      schema: SCHEMA, scope: "CURRENT_PROFILE_NORMAL_CHATGPT_TABS",
      adapter_instance_id: typeof instanceId === "string" && HEX.test(instanceId) ? instanceId : null,
      started_at: timestamp(), completed_at: null, duration_ms: null,
      inventory_coverage: "UNAVAILABLE", consistency: "UNKNOWN", reason: "QUERY_UNAVAILABLE",
      initial_tab_count: null, final_tab_count: null, excluded_private_count: 0,
      omitted_tab_count: 0, unobserved_added_count: null, rows: [],
    };
    const finish = () => {
      out.completed_at = timestamp(); out.duration_ms = Math.max(0, Math.round(monotonic() - start));
      return summarize(out);
    };
    if (!out.adapter_instance_id) { out.reason = "ADAPTER_UNCONFIGURED"; return finish(); }
    if (!tabs || !["query", "get", "sendMessage"].every(k => typeof tabs[k] === "function")) return finish();
    try {
      const first = await bounded(() => readBrowser(tabs, () => tabs.query({url: PATTERNS.slice()})), CALL_MS);
      if (!first.ok || first.value === NO_SLOT) return finish();
      if (!Array.isArray(first.value)) { out.reason = "INVALID_INVENTORY"; return finish(); }
      if (first.value.length > MAX_INVENTORY) {
        out.reason = "INVENTORY_LIMIT"; out.inventory_coverage = "PARTIAL";
        // Normal/private breakdown has not been computed; do not invent a scoped count.
        out.omitted_tab_count = first.value.length; return finish();
      }
      const initial = inventory(first.value);
      out.initial_tab_count = initial.normal.length; out.excluded_private_count = initial.excluded;
      out.omitted_tab_count = Math.max(0, initial.normal.length - MAX_TABS);
      out.inventory_coverage = initial.malformed || out.omitted_tab_count ? "PARTIAL" : "COMPLETE_IN_SCOPE";
      out.reason = out.omitted_tab_count ? "TAB_LIMIT" : initial.malformed ? "INVALID_TAB" : "NONE";
      const sampled = initial.normal.slice(0, MAX_TABS);
      out.rows = sampled.map((t, i) => blankRow(t, i + 1));
      let next = 0;
      let retired = 0;
      async function worker() {
        while (next < sampled.length) {
          const i = next++;
          if (monotonic() >= start + SWEEP_MS - CALL_MS) continue;
          try { out.rows[i] = await observe(sampled[i], i + 1, tabs, start + SWEEP_MS - CALL_MS,
            validTab(sampled[i]) && initial.ids.get(sampled[i].id) !== 1); }
          catch (_) { out.rows[i].status = "INVALID_PROBE"; }
          // A timeout cannot cancel Chrome's pending read. Retire this slot, so
          // unresolved requests plus active slots never exceed CONCURRENCY.
          if (["PROBE_TIMEOUT", "SWEEP_DEADLINE", "PROBE_SLOTS_EXHAUSTED"].includes(out.rows[i].status)) { retired++; return; }
        }
      }
      await Promise.all(Array.from({length: Math.min(CONCURRENCY, sampled.length)}, worker));
      if (retired && monotonic() < start + SWEEP_MS - CALL_MS) {
        for (const row of out.rows) if (row.status === "SWEEP_DEADLINE") row.status = "PROBE_SLOTS_EXHAUSTED";
      }
      const last = await bounded(() => readBrowser(tabs, () => tabs.query({url: PATTERNS.slice()})), Math.min(CALL_MS, start + SWEEP_MS - monotonic()));
      if (!last.ok || !Array.isArray(last.value) || last.value.length > MAX_INVENTORY) {
        out.inventory_coverage = "PARTIAL";
        if (out.reason === "NONE") out.reason = "FINAL_QUERY_UNAVAILABLE";
        return finish();
      }
      const final = inventory(last.value);
      out.final_tab_count = final.normal.length;
      out.unobserved_added_count = final.normal.filter(t => validTab(t) && !initial.ids.has(t.id)).length;
      out.consistency = signature(initial.normal) === signature(final.normal) && !initial.malformed && !final.malformed
        ? "STABLE_AT_BOUNDARIES" : "CHANGED";
      if (out.consistency !== "STABLE_AT_BOUNDARIES") {
        out.inventory_coverage = "PARTIAL";
        if (out.reason === "NONE") out.reason = "INVENTORY_CHANGED";
        const finalById = new Map(final.normal.filter(validTab).map(t => [t.id, t]));
        for (let i = 0; i < sampled.length; i++) {
          const t = sampled[i]; if (!validTab(t)) continue;
          const current = finalById.get(t.id);
          if (!current || final.ids.get(t.id) !== 1 || signature([t]) !== signature([current])) invalidate(out.rows[i]);
        }
      }
      return finish();
    } catch (_) {
      out.inventory_coverage = "UNAVAILABLE"; out.reason = "INVALID_INVENTORY"; out.rows = [];
      out.initial_tab_count = null; out.final_tab_count = null; out.consistency = "UNKNOWN";
      return finish();
    }
  }
  const api = Object.freeze({collect, MAX_TABS, CONCURRENCY});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MMXWebSolCensus = api;
})(globalThis);
