"use strict";

// This view owns no registry, timer-driven collection, native command or saved snapshot.
(() => {
  const byId = id => document.getElementById(id);
  const REASONS = Object.freeze({
    NONE: "Inventory stable at its two sampling boundaries; this is not an atomic account total.",
    ADAPTER_UNCONFIGURED: "This extension has no valid profile-local instance configuration.",
    QUERY_UNAVAILABLE: "The profile-scoped tab query is unavailable.",
    INVALID_INVENTORY: "The tab inventory could not be validated.",
    INVALID_TAB: "At least one returned tab could not be identified safely.",
    TAB_LIMIT: "The bounded reader did not sample every returned tab.",
    INVENTORY_LIMIT: "The browser returned more inventory than this reader can safely process.",
    INVENTORY_CHANGED: "Tabs changed during collection. Refresh before relying on this snapshot.",
    FINAL_QUERY_UNAVAILABLE: "The final inventory check failed; completeness is unknown.",
  });
  const STATES = Object.freeze({
    OBSERVED: "Cue sampled", DISCARDED: "Discarded", FROZEN: "Frozen", LOADING: "Loading / unknown",
    NAVIGATING: "Navigating", NOT_A_CONVERSATION: "No conversation locator", INVALID_TAB: "Invalid tab identity",
    OUT_OF_SCOPE: "Outside approved scope", PROBE_UNAVAILABLE: "No reachable content script",
    PROBE_TIMEOUT: "Probe timed out", INVALID_PROBE: "Probe rejected", TARGET_CHANGED: "Target changed",
    LOOKUP_UNAVAILABLE: "Tab lookup unavailable", SWEEP_DEADLINE: "Not sampled in deadline",
    PROBE_SLOTS_EXHAUSTED: "Probe slots unavailable",
  });
  let busy = false;
  function element(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
  }
  function metric(value, label) {
    const node = element("div", "", "metric");
    node.append(element("strong", Number.isSafeInteger(value) ? String(value) : "—"), element("span", label));
    return node;
  }
  function clearSnapshot() {
    byId("rows").replaceChildren(); byId("summary").replaceChildren();
    byId("scope").textContent = ""; byId("timestamp").textContent = "";
  }
  function render(result) {
    const hasInventory = Number.isSafeInteger(result.initial_tab_count);
    byId("summary").replaceChildren(
      metric(result.initial_tab_count, "Tabs in initial query"),
      metric(hasInventory ? result.generation_cue_count : null, "Generation cues"),
      metric(hasInventory ? result.unknown_cue_count : null, "Unknown cue state"),
      metric(hasInventory ? result.duplicate_tab_count : null, "Extra conversation views"),
    );
    const status = byId("status");
    status.className = `status${result.inventory_coverage === "UNAVAILABLE" ? " error" :
      result.inventory_coverage === "PARTIAL" ? " warning" : ""}`;
    status.textContent = REASONS[result.reason] || "Observation unavailable.";
    const scope = "Normal ChatGPT tabs in this profile only · " + (hasInventory
      ? `${result.probed_tab_count} sampled · ${result.unique_conversation_count} distinct observed conversation locators`
      : "Inventory unavailable");
    byId("scope").textContent = scope + (result.excluded_private_count ? ` · ${result.excluded_private_count} private tabs excluded` : "") +
      (result.omitted_tab_count ? ` · ${result.omitted_tab_count} returned entries omitted` : "") +
      (result.unobserved_added_count ? ` · ${result.unobserved_added_count} new tabs not sampled` : "");
    const when = typeof result.completed_at === "string" && /^\d{4}-\d{2}-\d{2}T/.test(result.completed_at)
      ? result.completed_at.replace("T", " ").replace("Z", " UTC") : "Time unavailable";
    byId("timestamp").textContent = `${hasInventory ? "Captured" : "Attempted"} ${when} · ${result.duration_ms} ms · Refresh to resample`;
    const rows = byId("rows"); rows.replaceChildren();
    for (const row of result.rows) {
      const tr = document.createElement("tr");
      const surface = document.createElement("td");
      surface.append(element("span", `Observed tab ${String(row.slot).padStart(2, "0")}`, "cell-title"));
      surface.append(element("span", row.conversation_fingerprint ? `${row.conversation_fingerprint.slice(0, 12)}…` : "Unbound locator", "detail"));
      if (row.duplicate_count > 1) surface.append(element("span", `${row.duplicate_count} tabs share this locator`, "detail"));
      if (row.duplicate_cue_disagreement) surface.append(element("span", "Cue observations differ", "detail"));
      const cue = document.createElement("td");
      const present = row.generation_cue === "PRESENT", unknown = row.generation_cue === "UNKNOWN";
      cue.append(element("span", present ? "Cue present" : unknown ? "Unknown" : "No cue observed",
        `badge${present ? " present" : unknown ? " unknown" : ""}`));
      if (row.provider_error_present) cue.append(element("span", "Error cue also present", "detail"));
      if (row.auth_required) cue.append(element("span", "Sign-in cue present", "detail"));
      const browser = document.createElement("td");
      browser.append(element("span", STATES[row.status] || "Unknown"));
      browser.append(element("span", row.selected_in_window === true ? "Selected in its window" :
        row.selected_in_window === false ? "Not selected in its window" : "Window selection unknown", "detail"));
      const mode = document.createElement("td");
      mode.append(element("span", "Unverified / Unverified"));
      mode.append(element("span", "Served model: unknown", "detail"));
      tr.append(surface, cue, browser, mode); rows.append(tr);
    }
    if (!result.rows.length) {
      const tr = document.createElement("tr"), td = element("td", !hasInventory
        ? "No usable snapshot. This is not evidence that no sessions exist."
        : "No normal ChatGPT tabs were sampled in this profile.", "empty");
      td.colSpan = 4; tr.append(td); rows.append(tr);
    }
  }
  async function refresh() {
    if (busy) return;
    busy = true; byId("refresh").disabled = true;
    byId("status").className = "status"; byId("status").textContent = "Collecting a bounded read-only snapshot…";
    clearSnapshot();
    try {
      const instance = globalThis.MMX_WEB_SOL_INSTANCE;
      render(await globalThis.MMXWebSolCensus.collect(chrome.tabs, instance && instance.instanceId));
    } catch (_) {
      clearSnapshot();
      byId("status").className = "status error";
      byId("status").textContent = "Snapshot unavailable. No browser-control action was attempted.";
    } finally { busy = false; byId("refresh").disabled = false; }
  }
  byId("refresh").addEventListener("click", refresh);
  refresh();
})();
