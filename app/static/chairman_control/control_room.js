"use strict";

/**
 * Chairman Control Room X1 — Chairman Command Deck.
 *
 * Presentation-only law:
 * - no aggregate lifecycle / health score;
 * - no model ranking, ownership inference or process-presence -> cognition claim;
 * - canonical attention altitude is preserved exactly from control_room.attention;
 * - navigation bindings are address-book facts only;
 * - source-owned text is rendered through textContent / DOM construction, never innerHTML.
 */
(function () {
  var REMOTE_READ_ONLY = document.documentElement.getAttribute("data-control-room-mode") === "remote-read-only";
  var TOKEN = REMOTE_READ_ONLY ? "" : (function () {
    var meta = document.querySelector('meta[name="ccr-token"]');
    return meta ? meta.getAttribute("content") : "";
  })();

  var PROVIDER_LOCATOR_KIND = {
    chatgpt: "chatgpt_managed_env",
    claude_code: "claude_code_session",
    claude_desktop: "claude_desktop_url",
    cursor_agent: "cursor_agent_thread",
    codex: "codex_session",
  };
  var ROLE_NAME = { chairman: "You", ceo: "Sol", coo: "Fable", worker: "Worker" };
  var OPEN_LABEL = { chairman: "Open", ceo: "Open Sol", coo: "Open Fable", worker: "Open worker" };
  var STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;
  var THEME_KEY = "ccr-x1-theme";
  var DOCK_KEY = "ccr-x1-dock-collapsed";

  var STATE = {
    body: null,
    doc: null,
    work: [],
    capabilities: {},
    attentionTargetById: {},
    workByRef: {},
    workMode: "focus",
    workQuery: "",
    selectedWork: null,
    paletteItems: [],
    paletteResults: [],
    paletteIndex: 0,
    autonomy: null,
  };

  var LAST_DRAWER_OPENER = null;
  var LAST_PALETTE_OPENER = null;

  // DOM -------------------------------------------------------------------
  function el(tag, opts) {
    var node = document.createElement(tag);
    opts = opts || {};
    if (opts.text !== undefined) node.textContent = String(opts.text);
    if (opts.className) node.className = opts.className;
    if (opts.attrs) {
      Object.keys(opts.attrs).forEach(function (key) {
        node.setAttribute(key, String(opts.attrs[key]));
      });
    }
    return node;
  }

  function clear(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function isBlank(value) {
    return value === null || value === undefined || value === "";
  }

  function safeText(value, fallback) {
    return isBlank(value) ? (fallback || "unknown") : String(value);
  }

  function shortSha(value) {
    return typeof value === "string" && value.length >= 7 ? value.slice(0, 7) : safeText(value);
  }

  function parseStamp(value) {
    if (typeof value !== "string" || !value) return null;
    var ms = Date.parse(value);
    return isNaN(ms) ? null : ms;
  }

  function ageWords(value) {
    var ms = parseStamp(value);
    if (ms === null) return null;
    var delta = Date.now() - ms;
    if (delta < 0) return "ahead";
    var mins = Math.floor(delta / 60000);
    if (mins < 1) return "now";
    if (mins < 60) return mins + "m";
    var hours = Math.floor(mins / 60);
    if (hours < 48) return hours + "h";
    return Math.floor(hours / 24) + "d";
  }

  function normalizedSearchText(value) {
    return safeText(value, "").toLowerCase();
  }

  function chip(text, variant) {
    return el("span", { text: text, className: "ccr-chip " + (variant || "is-dim") });
  }

  function setTally(name, count) {
    var nodes = document.querySelectorAll('[data-tally="' + name + '"]');
    for (var i = 0; i < nodes.length; i++) nodes[i].textContent = String(count);
  }

  function button(text, className, onClick) {
    var node = el("button", { text: text, className: className || "ccr-open-button" });
    node.type = "button";
    if (onClick) node.addEventListener("click", onClick);
    return node;
  }

  function openerCandidate(candidate) {
    if (candidate && typeof candidate.focus === "function" && document.contains(candidate)) return candidate;
    var active = document.activeElement;
    if (active && typeof active.focus === "function" && document.contains(active)) return active;
    return null;
  }

  function restoreFocus(candidate) {
    if (!candidate || typeof candidate.focus !== "function" || !document.contains(candidate)) return;
    try { candidate.focus({ preventScroll: true }); }
    catch (_e) { candidate.focus(); }
  }

  function focusableNodes(container) {
    if (!container) return [];
    var nodes = container.querySelectorAll(
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    return Array.prototype.slice.call(nodes).filter(function (node) {
      return !node.hidden && node.getClientRects().length > 0;
    });
  }

  function trapFocus(event, container) {
    if (event.key !== "Tab") return false;
    var nodes = focusableNodes(container);
    if (!nodes.length) return false;
    var first = nodes[0];
    var last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
      return true;
    }
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
      return true;
    }
    return false;
  }

  // transport -------------------------------------------------------------
  function getJSON(path) {
    var options = {
      method: "GET",
      credentials: "same-origin",
      headers: {},
    };
    if (!REMOTE_READ_ONLY) options.headers["X-CCR-Token"] = TOKEN;
    return fetch(path, options).then(function (resp) {
      return resp.json();
    });
  }

  function postJSON(path, body) {
    if (REMOTE_READ_ONLY) return Promise.reject(new Error("remote_read_only"));
    return fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CCR-Token": TOKEN },
      body: JSON.stringify(body || {}),
    }).then(function (resp) {
      return resp.json();
    });
  }

  // source pulse / system -------------------------------------------------
  var SOURCE_STAMPS = [
    { key: "mastermind_sha", label: "Mastermind", sha: true, extra: "mastermind_branch" },
    { key: "macro_sha", label: "Macro", sha: true },
    { key: "composed_at", label: "State composed", age: true },
    { key: "agent_os_state_generated_at", label: "Agent OS generated", age: true },
    { key: "active_builds_collected_at", label: "GitHub evidence collected", age: true },
    { key: "runtime_db_present", label: "Executive runtime DB", bool: true },
    { key: "bindings_path_present", label: "Bindings file", bool: true },
    { key: "macro_root", label: "Macro root" },
    { key: "executive_inbox_schema", label: "Executive inbox schema" },
    { key: "agent_os_brief_schema", label: "Agent OS brief schema" },
    { key: "agent_os_state_schema", label: "Agent OS state schema" },
    { key: "active_builds_schema", label: "Active builds schema" },
  ];

  function stampValue(spec, sources) {
    var raw = sources[spec.key];
    if (spec.bool) {
      if (raw === true) return "present";
      if (raw === false) return "absent";
      return "unknown";
    }
    if (isBlank(raw)) return "unknown";
    var value = spec.sha ? shortSha(String(raw)) : String(raw);
    if (spec.extra && !isBlank(sources[spec.extra])) value += " · " + String(sources[spec.extra]);
    if (spec.age && ageWords(raw)) value += " · " + ageWords(raw);
    return value;
  }

  function renderSystemSources(sources) {
    var dl = document.getElementById("ccr-sources");
    if (!dl) return;
    clear(dl);
    SOURCE_STAMPS.forEach(function (spec) {
      var pair = el("div");
      pair.appendChild(el("dt", { text: spec.label }));
      pair.appendChild(el("dd", { text: stampValue(spec, sources) }));
      dl.appendChild(pair);
    });
  }

  function sourcePulsePill(label, value, absent) {
    var cls = "ccr-pulse-pill";
    if (absent) cls += " is-absent";
    return el("span", { text: label + " · " + value, className: cls });
  }

  function renderSourcePulse(body, sources) {
    var node = document.getElementById("ccr-source-pulse");
    clear(node);
    // Ages are clocks only. Source-owned degraded state is rendered separately.
    var aoAge = ageWords(sources.agent_os_state_generated_at) || "unknown age";
    var ghAge = ageWords(sources.active_builds_collected_at) || "unknown age";
    node.appendChild(sourcePulsePill("Agent OS", aoAge, parseStamp(sources.agent_os_state_generated_at) === null));
    node.appendChild(sourcePulsePill(
      "Executive",
      sources.runtime_db_present === true ? "DB present" : sources.runtime_db_present === false ? "DB absent" : "DB unknown",
      sources.runtime_db_present !== true
    ));
    node.appendChild(sourcePulsePill(
      "GitHub",
      (body && body.live_builds_active ? "live cache · " : "snapshot · ") + ghAge,
      parseStamp(sources.active_builds_collected_at) === null
    ));

    var age = ageWords(body && body.composed_at);
    document.getElementById("ccr-composed-age").textContent = "State " + (age || "unknown");
    document.getElementById("ccr-live-builds-label").textContent = body && body.live_builds_active ? "GitHub live cache" : "GitHub snapshot";

    var banner = document.getElementById("ccr-refresh-banner");
    if (body && body.refresh_in_flight) {
      banner.hidden = false;
      document.getElementById("ccr-refresh-banner-text").textContent = "Refreshing canonical state in the background — showing last good composition";
    } else {
      banner.hidden = true;
    }
  }

  function renderRemoteSources(doc, sourceFreshness, codeIdentity) {
    var node = document.getElementById("ccr-source-pulse");
    clear(node);
    var freshness = sourceFreshness || {};
    Object.keys(freshness).sort().forEach(function (name) {
      var row = freshness[name] || {};
      var value = safeText(row.state);
      if (row.source_time && ageWords(row.source_time)) value += " · " + ageWords(row.source_time);
      node.appendChild(sourcePulsePill(name.replace(/_/g, " "), value, row.state !== "fresh"));
    });
    var identity = codeIdentity || {};
    var sources = {
      remote_schema: doc.schema,
      observed_at: doc.observed_at,
      commit: identity.commit,
      tree: identity.tree,
      artifact_digest: identity.artifact_digest,
    };
    var dl = document.getElementById("ccr-sources");
    clear(dl);
    Object.keys(sources).forEach(function (key) {
      var pair = el("div");
      pair.appendChild(el("dt", { text: key.replace(/_/g, " ") }));
      pair.appendChild(el("dd", { text: key === "commit" || key === "tree" ? shortSha(sources[key]) : safeText(sources[key]) }));
      dl.appendChild(pair);
    });
    document.getElementById("ccr-composed-age").textContent = "State " + (ageWords(doc.observed_at) || "unknown");
    document.getElementById("ccr-live-builds-label").textContent = "Remote projection";
    document.getElementById("ccr-refresh-banner").hidden = true;
  }

  function renderDegraded(items) {
    var section = document.getElementById("degraded");
    var list = section.querySelector("ul");
    clear(list);
    var rows = items || [];
    rows.forEach(function (entry) { list.appendChild(el("li", { text: entry })); });
    section.className = rows.length ? "ccr-alarm" : "ccr-alarm is-empty";
    document.getElementById("nav-system-count").textContent = rows.length ? String(rows.length) : "";
  }

  function renderCapabilities(capabilities) {
    var container = document.getElementById("ccr-capabilities");
    if (!container) return;
    clear(container);
    var keys = Object.keys(capabilities || {}).sort();
    if (!keys.length) {
      container.appendChild(el("p", { text: "Capability census unavailable.", className: "ccr-empty-line" }));
      return;
    }
    keys.forEach(function (key) {
      var row = capabilities[key] || {};
      var card = el("div", { className: "ccr-capability" });
      var head = el("div", { className: "ccr-capability-name" });
      head.appendChild(el("span", { text: key }));
      var state = safeText(row.state);
      var variant = state === "PROVEN" ? "is-ok" : state === "UNSUPPORTED" || state === "NOT_INSTALLED" ? "is-dim" : "is-slate";
      head.appendChild(chip(state, variant));
      card.appendChild(head);
      card.appendChild(el("p", { text: safeText(row.detail, "No detail."), className: "ccr-capability-detail" }));
      container.appendChild(card);
    });
  }

  // attention -------------------------------------------------------------
  function attentionSummary(item) {
    return safeText(item && (item.summary || item.reason), "Attention item");
  }

  function attentionState(item) {
    return item && (item.state || item.status);
  }

  function findCardForAttention(item) {
    var attentionId = item && item.attention_id;
    if (!attentionId) return null;
    for (var i = 0; i < STATE.work.length; i++) {
      if ((STATE.work[i].attention_ids || []).indexOf(attentionId) !== -1) return STATE.work[i];
    }
    return null;
  }

  function uniqueBinding(card, role) {
    var rows = ((card && card.bindings) || []).filter(function (binding) { return binding.role === role; });
    // Never silently pick a winner when more than one destination serves the same role.
    return rows.length === 1 ? rows[0] : null;
  }

  function attentionEvidenceFold(item) {
    var rows = (item && item.evidence) || [];
    if (!rows.length) return null;
    var fold = el("details", { className: "ccr-fold" });
    var summary = el("summary");
    summary.appendChild(el("span", { text: "Source evidence" }));
    summary.appendChild(el("span", { text: String(rows.length), className: "ccr-count" }));
    fold.appendChild(summary);
    var list = el("ul");
    rows.forEach(function (entry) {
      if (entry === null || typeof entry !== "object") {
        list.appendChild(el("li", { text: String(entry), className: "ccr-row ccr-row-id" }));
        return;
      }
      Object.keys(entry).forEach(function (key) {
        list.appendChild(el("li", { text: key + ": " + String(entry[key]), className: "ccr-row ccr-row-id" }));
      });
    });
    fold.appendChild(list);
    return fold;
  }

  function renderAttentionDetail(item, target) {
    document.getElementById("ccr-detail-ref").textContent = "ATTENTION · " + safeText(target, "unknown").toUpperCase();
    document.getElementById("ccr-detail-title").textContent = attentionSummary(item);
    var body = document.getElementById("ccr-detail-body");
    clear(body);

    var summary = el("section", { className: "ccr-detail-summary" });
    var meta = [
      ["id", item.attention_id],
      ["kind", item.kind],
      ["work", item.workstream],
      ["status", attentionState(item)],
      ["job", item.job_id],
      ["reported by", item.source],
    ].filter(function (pair) { return !isBlank(pair[1]); });
    summary.appendChild(el("span", { text: "Source-owned attention", className: "ccr-detail-next-label" }));
    summary.appendChild(el("p", { text: meta.map(function (pair) { return pair[0] + " " + pair[1]; }).join(" · "), className: "ccr-detail-next" }));
    body.appendChild(summary);

    var next = item.existing_next_actions || [];
    if (next.length) {
      var nextSection = el("section", { className: "ccr-detail-section" });
      nextSection.appendChild(el("h3", { text: "Recorded next action" }));
      next.forEach(function (line) { nextSection.appendChild(el("p", { text: line, className: "ccr-detail-line" })); });
      body.appendChild(nextSection);
    }

    var evidence = attentionEvidenceFold(item);
    if (evidence) {
      var evidenceSection = el("section", { className: "ccr-detail-section" });
      evidenceSection.appendChild(el("h3", { text: "Evidence" }));
      evidenceSection.appendChild(evidence);
      body.appendChild(evidenceSection);
    }

    var card = findCardForAttention(item);
    if (card) {
      var workSection = el("section", { className: "ccr-detail-section" });
      workSection.appendChild(el("h3", { text: "Joined work" }));
      workSection.appendChild(button("Open work", "ccr-open-button", function () { openDetail(card, LAST_DRAWER_OPENER); }));
      body.appendChild(workSection);
    }
  }

  function openAttentionDetail(item, target, opener) {
    LAST_DRAWER_OPENER = openerCandidate(opener);
    STATE.selectedWork = null;
    renderAttentionDetail(item, target);
    var drawer = document.getElementById("ccr-detail-drawer");
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    document.getElementById("ccr-drawer-scrim").hidden = false;
    document.getElementById("ccr-drawer-close").focus();
  }

  function attentionReadState(doc, body) {
    var attention = doc && doc.attention;
    var rowsKnown = attention && typeof attention === "object" &&
      Array.isArray(attention.chairman) && Array.isArray(attention.ceo) && Array.isArray(attention.coo);
    if (!rowsKnown || (body && (body.state_refresh_error || body.refresh_in_flight))) return "unavailable";
    if (REMOTE_READ_ONLY) {
      var remoteRuntime = doc.source_freshness && doc.source_freshness.executive_runtime;
      return remoteRuntime && remoteRuntime.state === "current" ? "current" : "unavailable";
    }
    var degraded = Array.isArray(doc.degraded) ? doc.degraded : [];
    if (degraded.some(function (entry) { return typeof entry === "string" && entry.indexOf("executive_inbox:") === 0; })) {
      return "unavailable";
    }
    if ((doc.sources || {}).runtime_db_present !== true || degraded.some(function (entry) {
      return typeof entry === "string" && entry.indexOf("executive_runtime:") === 0;
    })) return "runtime_unavailable";
    return "current";
  }

  function emptyAttentionText(state, normalText) {
    if (state === "unavailable") return "Attention unavailable — refresh canonical sources.";
    if (state === "runtime_unavailable") return "No recorded Inbox items. Executive runtime unavailable.";
    return normalText;
  }

  function appendAttentionFreshnessNote(list, state) {
    if (state === "unavailable") {
      list.appendChild(el("li", { text: "Attention may be stale — refresh canonical sources.", className: "ccr-empty-line" }));
    }
  }

  function renderNeedsYou(items, readState) {
    var section = document.getElementById("needs-you");
    var list = section.querySelector(".ccr-attention-list");
    clear(list);
    var rows = items || [];
    section.className = rows.length ? "ccr-needs ccr-has-items" : "ccr-needs";
    if (!rows.length) {
      list.appendChild(el("li", { text: emptyAttentionText(readState, "Nothing is waiting on you."), className: "ccr-empty-line" }));
      return;
    }
    rows.forEach(function (item) {
      var li = el("li", { className: "ccr-attention-item" });
      var body = el("div");
      body.appendChild(el("p", { text: attentionSummary(item), className: "ccr-attention-reason" }));
      var meta = el("div", { className: "ccr-attention-meta" });
      [
        ["work", item.workstream], ["kind", item.kind], ["status", attentionState(item)], ["reported by", item.source]
      ].forEach(function (pair) {
        if (!isBlank(pair[1])) meta.appendChild(el("span", { text: pair[0] + " " + pair[1] }));
      });
      body.appendChild(meta);
      var next = item.existing_next_actions || [];
      if (next.length) body.appendChild(el("p", { text: next.join(" · "), className: "ccr-attention-next" }));
      li.appendChild(body);

      var actions = el("div", { className: "ccr-attention-actions" });
      var card = findCardForAttention(item);
      var inspectBtn = button("Inspect", "ccr-open-button", function (event) {
        event.stopPropagation();
        openAttentionDetail(item, "chairman", inspectBtn);
      });
      actions.appendChild(inspectBtn);
      if (card) {
        var workBtn = button("Open work", "ccr-open-button", function (event) {
          event.stopPropagation();
          openDetail(card, workBtn);
        });
        actions.appendChild(workBtn);
      }
      var sol = uniqueBinding(card, "ceo");
      if (sol && bindingConfidence(sol).openable) actions.appendChild(openBindingButton(sol, "Open Sol"));
      li.appendChild(actions);
      list.appendChild(li);
    });
    appendAttentionFreshnessNote(list, readState);
  }

  function renderMiniAttention(containerId, items, readState) {
    var container = document.querySelector("#" + containerId + " .ccr-mini-list");
    clear(container);
    var rows = items || [];
    var target = containerId === "sol-attention" ? "ceo" : "coo";
    if (!rows.length) {
      container.appendChild(el("li", { text: emptyAttentionText(readState, "Clear"), className: "ccr-empty-line" }));
      return;
    }
    rows.slice(0, 5).forEach(function (item) {
      var li = el("li", { className: "ccr-mini-item" });
      li.appendChild(el("span", { text: attentionSummary(item) }));
      var card = findCardForAttention(item);
      var work = card ? card.work_ref : item.workstream;
      li.appendChild(el("span", { text: safeText(work, "unjoined"), className: "ccr-mini-work" }));
      li.tabIndex = 0;
      li.role = "button";
      li.addEventListener("click", function () { openAttentionDetail(item, target, li); });
      li.addEventListener("keydown", function (event) { if (event.key === "Enter") openAttentionDetail(item, target, li); });
      container.appendChild(li);
    });
    if (rows.length > 5) container.appendChild(el("li", { text: "+" + (rows.length - 5) + " more", className: "ccr-empty-line" }));
    appendAttentionFreshnessNote(container, readState);
  }

  // bindings --------------------------------------------------------------
  function bindingConfidence(binding) {
    if (!binding) return { state: "UNBOUND", variant: "is-dim", openable: false, note: "No bound destination." };
    var expected = PROVIDER_LOCATOR_KIND[binding.provider];
    if (!expected || binding.locator_kind !== expected) {
      return { state: "UNSUPPORTED", variant: "is-dim", openable: false, note: "Locator is not supported by this Control Room." };
    }

    // Current protected chatgpt.py deliberately refuses every managed-seat
    // navigation path until P0B has a supported real-seat actuator. A valid
    // address remains useful as a binding, but it must never render as an
    // openable action merely because its locator shape is valid.
    if (binding.provider === "chatgpt") {
      return {
        state: "UNSUPPORTED",
        variant: "is-dim",
        openable: false,
        note: "Bound managed-browser seat; current P0B navigation actuator is not supported.",
      };
    }

    var capability = (STATE.capabilities || {})[binding.provider] || null;
    if (capability && (capability.state === "UNSUPPORTED" || capability.state === "NOT_INSTALLED")) {
      return {
        state: capability.state,
        variant: "is-dim",
        openable: false,
        note: safeText(capability.detail, "Provider navigation is unavailable on this machine."),
      };
    }

    if (isBlank(binding.last_verified_at)) {
      return { state: "BOUND", variant: "is-slate", openable: true, note: "Bound; no verified open stamp." };
    }
    var ms = parseStamp(binding.last_verified_at);
    if (ms !== null && Date.now() - ms > STALE_AFTER_MS) {
      return { state: "STALE", variant: "is-dim", openable: true, note: "Last verified " + ageWords(binding.last_verified_at) + " ago." };
    }
    return { state: "VERIFIED", variant: "is-ok", openable: true, note: "Last verified " + (ageWords(binding.last_verified_at) || "at an unreadable time") + "." };
  }

  function openBinding(binding, statusNode, trigger) {
    if (!binding || !binding.binding_id) return Promise.resolve();
    if (trigger) trigger.disabled = true;
    if (statusNode) statusNode.textContent = "Opening…";
    return postJSON("/api/open", { binding_id: binding.binding_id }).then(function (outcome) {
      if (outcome && outcome.ok) {
        if (statusNode) statusNode.textContent = "Opened · " + safeText(outcome.action, "provider action");
      } else if (statusNode) {
        statusNode.textContent = "Did not open · " + safeText(outcome && outcome.failure_kind, "unknown reason");
        statusNode.className = "ccr-binding-meta ccr-problem";
      }
      return outcome;
    }).catch(function () {
      if (statusNode) {
        statusNode.textContent = "Did not open · local server unavailable";
        statusNode.className = "ccr-binding-meta ccr-problem";
      }
      return null;
    }).finally(function () {
      if (trigger) trigger.disabled = false;
    });
  }

  function openBindingButton(binding, label) {
    var confidence = bindingConfidence(binding);
    var btn = button(label || OPEN_LABEL[binding.role] || "Open", "ccr-open-button", function (event) {
      event.stopPropagation();
      openBinding(binding, null, btn).then(function () { loadState(); });
    });
    btn.disabled = !confidence.openable;
    return btn;
  }

  function allBindings() {
    var byId = {};
    STATE.work.forEach(function (card) {
      (card.bindings || []).forEach(function (binding) {
        if (binding && binding.binding_id) byId[binding.binding_id] = binding;
      });
    });
    ((STATE.doc && STATE.doc.unbound_surfaces) || []).forEach(function (binding) {
      if (binding && binding.binding_id) byId[binding.binding_id] = binding;
    });
    return Object.keys(byId).map(function (key) { return byId[key]; });
  }

  function workTitle(ref) {
    var card = STATE.workByRef[ref];
    return card && card.agent_os && card.agent_os.title ? String(card.agent_os.title) : safeText(ref, "Unjoined binding");
  }

  function seatLabel(binding) {
    var seat = safeText(binding.seat_ref, "");
    if (/^chatgpt\d+$/i.test(seat)) return "ChatGPT " + seat.replace(/\D/g, "");
    if (seat) return seat;
    if (binding.provider === "claude_code" || binding.provider === "claude_desktop") return "Claude";
    if (binding.provider === "cursor_agent") return "Cursor";
    if (binding.provider === "codex") return "Codex";
    return binding.provider || "Surface";
  }

  function renderSurfaceGroup(parent, title, bindings) {
    if (!bindings.length) return;
    var group = el("section", { className: "ccr-surface-group" });
    var head = el("div", { className: "ccr-surface-group-head" });
    head.appendChild(el("span", { text: title }));
    head.appendChild(el("span", { text: bindings.length + " destinations" }));
    group.appendChild(head);

    var buckets = {};
    bindings.forEach(function (binding) {
      var key = [binding.provider || "unknown", binding.seat_ref || ""].join("::");
      if (!buckets[key]) buckets[key] = [];
      buckets[key].push(binding);
    });

    Object.keys(buckets).sort().forEach(function (key) {
      var rows = buckets[key];
      var details = el("details", { className: "ccr-seat-block" });
      if (rows.length <= 2) details.open = true;
      var summary = el("summary", { className: "ccr-seat-summary" });
      summary.appendChild(el("span", { text: seatLabel(rows[0]), className: "ccr-seat-name" }));
      summary.appendChild(el("span", { text: rows.length + (rows.length === 1 ? " destination" : " destinations"), className: "ccr-seat-count" }));
      details.appendChild(summary);
      var list = el("div", { className: "ccr-destination-list" });
      rows.sort(function (a, b) { return safeText(a.work_ref).localeCompare(safeText(b.work_ref)); }).forEach(function (binding) {
        var row = el("div", { className: "ccr-destination" });
        var copy = el("div");
        copy.appendChild(el("div", { text: workTitle(binding.work_ref), className: "ccr-destination-title" }));
        copy.appendChild(el("div", { text: safeText(binding.work_ref) + " · " + bindingConfidence(binding).state, className: "ccr-destination-sub" }));
        row.appendChild(copy);
        row.appendChild(openBindingButton(binding, "Open"));
        list.appendChild(row);
      });
      details.appendChild(list);
      group.appendChild(details);
    });
    parent.appendChild(group);
  }

  function buildSurfaceContent() {
    var root = el("div");
    var rows = allBindings();
    var sol = rows.filter(function (b) { return b.role === "ceo"; });
    var ops = rows.filter(function (b) { return b.role === "coo"; });
    var workers = rows.filter(function (b) { return b.role === "worker"; });
    var chairman = rows.filter(function (b) { return b.role === "chairman"; });
    renderSurfaceGroup(root, "Sol", sol);
    renderSurfaceGroup(root, "Fable / Ops", ops);
    renderSurfaceGroup(root, "Workers", workers);
    renderSurfaceGroup(root, "Chairman", chairman);
    if (!rows.length) root.appendChild(el("p", { text: "No navigation surfaces are bound.", className: "ccr-empty-line" }));
    return { node: root, count: rows.length };
  }

  function renderSurfaces() {
    var dock = document.getElementById("ccr-surface-dock-content");
    var mobile = document.getElementById("ccr-surfaces-mobile-content");
    clear(dock);
    clear(mobile);
    var a = buildSurfaceContent();
    var b = buildSurfaceContent();
    while (a.node.firstChild) dock.appendChild(a.node.firstChild);
    while (b.node.firstChild) mobile.appendChild(b.node.firstChild);
    document.getElementById("nav-surface-count").textContent = String(a.count);
  }

  // work ------------------------------------------------------------------
  function cardAttentionTargets(card) {
    var found = {};
    (card.attention_ids || []).forEach(function (id) {
      var target = STATE.attentionTargetById[id];
      if (target) found[target] = true;
    });
    return found;
  }

  function cardFailedJobs(card) {
    return (((card.executive || {}).jobs) || []).filter(function (job) { return String(job.status).toLowerCase() === "failed"; });
  }

  function focusReasons(card) {
    var reasons = [];
    if ((card.attention_ids || []).length) reasons.push("attention");
    if ((card.disagreements || []).length) reasons.push("source disagreement");
    var ao = card.agent_os || {};
    if (String(ao.status).toLowerCase() === "blocked" || String(ao.state).toLowerCase() === "blocked") reasons.push("authored blocked state");
    if ((ao.unmet_dependencies || []).length) reasons.push("unmet dependencies");
    if (cardFailedJobs(card).length) reasons.push("failed executive job");
    return reasons;
  }

  function isFocus(card) { return focusReasons(card).length > 0; }

  function cardSortKey(card, index) {
    var targets = cardAttentionTargets(card);
    var altitude = targets.chairman ? 0 : targets.ceo ? 1 : targets.coo ? 2 : 3;
    var danger = cardFailedJobs(card).length || (card.disagreements || []).length ? 0 : 1;
    var blocked = String((card.agent_os || {}).status).toLowerCase() === "blocked" ? 0 : 1;
    return [altitude, danger, blocked, index];
  }

  function compareKeys(a, b) {
    for (var i = 0; i < a.length; i++) {
      if (a[i] < b[i]) return -1;
      if (a[i] > b[i]) return 1;
    }
    return 0;
  }

  function sortedFocusCards() {
    return STATE.work.map(function (card, index) { return { card: card, key: cardSortKey(card, index) }; })
      .filter(function (row) { return isFocus(row.card); })
      .sort(function (a, b) { return compareKeys(a.key, b.key); })
      .map(function (row) { return row.card; });
  }

  function renderChain(card) {
    var container = el("div", { className: "ccr-chain" });
    var track = el("div", { className: "ccr-chain-track" });
    var targets = cardAttentionTargets(card);
    var bindings = card.bindings || [];

    [
      { role: "chairman", target: "chairman", label: "You" },
      { role: "ceo", target: "ceo", label: "Sol" },
      { role: "coo", target: "coo", label: "Fable" },
      // Executive Inbox has no worker attention bucket. Worker nodes therefore
      // express navigation addressability only, never inferred runtime state.
      { role: "worker", target: null, label: "Workers" },
    ].forEach(function (spec) {
      var roleBindings = bindings.filter(function (b) { return b.role === spec.role; });
      var cls = "ccr-chain-node";
      if (roleBindings.length) cls += " is-bound";
      if (spec.target && targets[spec.target]) cls += " is-attention";
      var node = el("div", { className: cls });
      node.appendChild(el("span", { text: spec.label, className: "ccr-chain-name" }));
      var sub = roleBindings.length ? roleBindings.length + " bound" : "";
      if (spec.target && targets[spec.target]) sub = "attention";
      node.appendChild(el("span", { text: sub, className: "ccr-chain-sub" }));
      track.appendChild(node);
    });
    container.appendChild(track);
    return container;
  }

  function renderMissionRow(card) {
    var targets = cardAttentionTargets(card);
    var failed = cardFailedJobs(card).length > 0;
    var disagreements = (card.disagreements || []).length;
    var cls = "ccr-mission-row";
    var hasHumanAttention = targets.chairman || targets.ceo || targets.coo;
    if (targets.chairman) cls += " ccr-has-chairman-attention";
    else if (targets.ceo || targets.coo) cls += " ccr-has-role-attention";
    // Human attention owns the row's brass stripe. Machine/runtime danger is
    // still explicit in vermilion evidence chips but must never visually
    // overwrite the fact that a person owes the canonical next move.
    if ((failed || disagreements) && !hasHumanAttention) cls += " ccr-has-danger";
    var row = el("article", { className: cls, attrs: { tabindex: "0" } });

    var ao = card.agent_os || {};
    var id = el("div", { className: "ccr-mission-id" });
    id.appendChild(el("div", { text: safeText(ao.title, "Untitled work reference"), className: "ccr-mission-title" }));
    id.appendChild(el("div", { text: safeText(card.work_ref), className: "ccr-mission-ref" }));
    id.appendChild(el("div", { text: [ao.program, ao.status].filter(function (x) { return !isBlank(x); }).join(" · ") || "No authored program/status", className: "ccr-mission-program" }));
    row.appendChild(id);

    var frontier = el("div", { className: "ccr-mission-frontier" });
    frontier.appendChild(el("span", { text: "Recorded frontier", className: "ccr-frontier-label" }));
    frontier.appendChild(el("p", { text: safeText(ao.next_action, "No next action from Agent OS."), className: isBlank(ao.next_action) ? "ccr-frontier-text is-unknown" : "ccr-frontier-text" }));
    row.appendChild(frontier);
    row.appendChild(renderChain(card));

    var evidence = el("div", { className: "ccr-mission-evidence" });
    if ((card.attention_ids || []).length) evidence.appendChild(chip((card.attention_ids || []).length + " attention", "is-brass"));
    var jobs = ((card.executive || {}).jobs) || [];
    if (jobs.length) {
      if (failed) evidence.appendChild(chip("JOB FAILED", "is-danger"));
      else evidence.appendChild(chip(jobs.length + " job" + (jobs.length === 1 ? "" : "s"), "is-slate"));
    }
    var prs = ((card.github || {}).prs) || [];
    evidence.appendChild(chip(prs.length ? "PR " + prs.length : "NO OPEN PR", prs.length ? "is-slate" : "is-dim"));
    if (disagreements) evidence.appendChild(chip("SOURCE DRIFT", "is-danger"));
    var reasons = focusReasons(card);
    if (reasons.indexOf("authored blocked state") !== -1) evidence.appendChild(chip("BLOCKED", "is-danger"));
    row.appendChild(evidence);

    row.addEventListener("click", function () { openDetail(card, row); });
    row.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDetail(card, row);
      }
    });
    return row;
  }

  function workMatches(card, query) {
    if (!query) return true;
    var ao = card.agent_os || {};
    var hay = [card.work_ref, ao.title, ao.program, ao.status, ao.next_action]
      .concat((((card.github || {}).prs) || []).map(function (pr) { return pr.title; }))
      .join(" ").toLowerCase();
    return hay.indexOf(query.toLowerCase()) !== -1;
  }

  function renderMissionList(container, cards) {
    clear(container);
    if (!cards.length) {
      container.appendChild(el("p", { text: "No work matches this view.", className: "ccr-mission-list-empty" }));
      return;
    }
    cards.forEach(function (card) { container.appendChild(renderMissionRow(card)); });
  }

  function renderWork() {
    var focus = sortedFocusCards();
    renderMissionList(document.getElementById("ccr-focus-list"), focus);

    var rows = STATE.work.filter(function (card) {
      return (STATE.workMode === "all" || isFocus(card)) && workMatches(card, STATE.workQuery);
    });
    if (STATE.workMode === "focus") {
      var focusSet = {};
      focus.forEach(function (card, index) { focusSet[card.work_ref] = index; });
      rows.sort(function (a, b) { return focusSet[a.work_ref] - focusSet[b.work_ref]; });
    }
    renderMissionList(document.getElementById("ccr-work-list"), rows);
    setTally("work", STATE.work.length);
    document.getElementById("nav-work-count").textContent = String(STATE.work.length);
    document.getElementById("ccr-work-filter-note").textContent = STATE.workMode === "focus" ? "Showing deterministic focus · " + rows.length : "Showing all loaded work · " + rows.length;

    var buttons = document.querySelectorAll("[data-work-mode]");
    for (var i = 0; i < buttons.length; i++) buttons[i].className = buttons[i].getAttribute("data-work-mode") === STATE.workMode ? "is-active" : "";
  }

  // detail drawer ---------------------------------------------------------
  function detailLine(parent, text, mono) {
    parent.appendChild(el("p", { text: text, className: "ccr-detail-line" + (mono ? " mono" : "") }));
  }

  function detailRail(rails, name, builder) {
    var rail = el("section", { className: "ccr-detail-rail" });
    rail.appendChild(el("div", { text: name, className: "ccr-detail-rail-name" }));
    var body = el("div", { className: "ccr-detail-rail-body" });
    builder(body);
    rail.appendChild(body);
    rails.appendChild(rail);
  }

  function renderDetail(card) {
    var ao = card.agent_os || {};
    document.getElementById("ccr-detail-ref").textContent = safeText(card.work_ref);
    document.getElementById("ccr-detail-title").textContent = safeText(ao.title, "Untitled work reference");
    var body = document.getElementById("ccr-detail-body");
    clear(body);

    var summary = el("section", { className: "ccr-detail-summary" });
    summary.appendChild(el("span", { text: "Recorded next action", className: "ccr-detail-next-label" }));
    summary.appendChild(el("p", { text: safeText(ao.next_action, "No next action from Agent OS."), className: "ccr-detail-next" }));
    body.appendChild(summary);

    var rails = el("div", { className: "ccr-detail-rails" });
    detailRail(rails, "Agent OS", function (node) {
      var facts = [];
      if (!isBlank(ao.status)) facts.push("status " + ao.status);
      if (!isBlank(ao.state)) facts.push("readiness " + ao.state);
      if (!isBlank(ao.program)) facts.push("program " + ao.program);
      if (facts.length) detailLine(node, facts.join(" · "), true);
      if (!isBlank(ao.reason)) detailLine(node, ao.reason, false);
      if ((ao.unmet_dependencies || []).length) detailLine(node, "waiting on " + ao.unmet_dependencies.join(", "), true);
      if (!facts.length && isBlank(ao.reason) && !(ao.unmet_dependencies || []).length) detailLine(node, "silent — no Agent OS facts for this reference", true);
    });
    detailRail(rails, "Executive", function (node) {
      var jobs = ((card.executive || {}).jobs) || [];
      if (!jobs.length) { detailLine(node, "silent — no Executive job cites this reference", true); return; }
      jobs.forEach(function (job) { detailLine(node, safeText(job.job_id) + " · " + safeText(job.status, "status unknown"), true); });
      if (!isBlank((card.executive || {}).joined_by)) detailLine(node, "joined by " + card.executive.joined_by, true);
    });
    detailRail(rails, "GitHub", function (node) {
      var prs = ((card.github || {}).prs) || [];
      if (!prs.length) { detailLine(node, "silent — no open PR cites this reference", true); return; }
      prs.forEach(function (pr) {
        var row = el("div", { className: "ccr-detail-pr" });
        var left = el("div");
        left.appendChild(el("div", { text: safeText(pr.title, "Untitled PR"), className: "ccr-detail-pr-title" }));
        left.appendChild(el("div", { text: safeText(pr.repo) + " #" + safeText(pr.number) + " · " + (pr.draft === true ? "draft" : pr.draft === false ? "ready" : "draft unknown") + " · merge " + safeText(pr.merge_state), className: "ccr-detail-pr-meta" }));
        row.appendChild(left);
        var link = el("a", { text: "Open PR", className: "ccr-open-button", attrs: { href: pr.url || "#", target: "_blank", rel: "noopener noreferrer" } });
        row.appendChild(link);
        node.appendChild(row);
      });
    });
    body.appendChild(rails);

    var attentionRows = [];
    (card.attention_ids || []).forEach(function (id) {
      ["chairman", "ceo", "coo"].forEach(function (target) {
        (((STATE.doc || {}).attention || {})[target] || []).forEach(function (item) {
          if (item.attention_id === id) attentionRows.push({ target: target, item: item });
        });
      });
    });
    if (attentionRows.length) {
      var attSection = el("section", { className: "ccr-detail-section" });
      attSection.appendChild(el("h3", { text: "Attention" }));
      attentionRows.forEach(function (entry) {
        var line = el("div", { className: "ccr-binding-card" });
        var copy = el("div");
        copy.appendChild(el("div", { text: ROLE_NAME[entry.target] + " · " + attentionSummary(entry.item), className: "ccr-binding-title" }));
        copy.appendChild(el("div", { text: safeText(entry.item.attention_id), className: "ccr-binding-meta" }));
        line.appendChild(copy);
        line.appendChild(chip(entry.target.toUpperCase(), "is-brass"));
        attSection.appendChild(line);
        var evidence = attentionEvidenceFold(entry.item);
        if (evidence) attSection.appendChild(evidence);
      });
      body.appendChild(attSection);
    }

    if ((card.disagreements || []).length) {
      var drift = el("section", { className: "ccr-detail-section" });
      drift.appendChild(el("h3", { text: "Source drift — unresolved" }));
      card.disagreements.forEach(function (entry) { drift.appendChild(el("div", { text: entry, className: "ccr-disagreement" })); });
      body.appendChild(drift);
    }

    var bindings = card.bindings || [];
    if (!REMOTE_READ_ONLY) {
      var surfaceSection = el("section", { className: "ccr-detail-section" });
      surfaceSection.appendChild(el("h3", { text: "Navigation surfaces" }));
      if (!bindings.length) surfaceSection.appendChild(el("p", { text: "No surface is bound to this work reference.", className: "ccr-empty-line" }));
      bindings.forEach(function (binding) {
      var confidence = bindingConfidence(binding);
      var row = el("div", { className: "ccr-binding-card" });
      var copy = el("div");
      copy.appendChild(el("div", { text: (ROLE_NAME[binding.role] || binding.role) + " · " + seatLabel(binding), className: "ccr-binding-title" }));
      var status = el("div", { text: safeText(binding.provider) + " · " + confidence.note, className: "ccr-binding-meta" });
      copy.appendChild(status);
      row.appendChild(copy);
      var controls = el("div");
      controls.appendChild(chip(confidence.state, confidence.variant));
      var open = openBindingButton(binding, "Open");
      open.classList.add("ccr-binding-open");
      controls.appendChild(open);
      var unbind = button("Unbind", "ccr-open-button ccr-unbind-button", function (event) {
        event.stopPropagation();
        unbind.disabled = true;
        postJSON("/api/unbind", { binding_id: binding.binding_id }).then(function () {
          closeDetail();
          return loadState();
        }).finally(function () { unbind.disabled = false; });
      });
      controls.appendChild(unbind);
      row.appendChild(controls);
        surfaceSection.appendChild(row);
      });
      body.appendChild(surfaceSection);
    }
  }

  function openDetail(card, opener) {
    LAST_DRAWER_OPENER = openerCandidate(opener);
    STATE.selectedWork = card;
    renderDetail(card);
    var drawer = document.getElementById("ccr-detail-drawer");
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    document.getElementById("ccr-drawer-scrim").hidden = false;
    document.getElementById("ccr-drawer-close").focus();
  }

  function closeDetail() {
    var drawer = document.getElementById("ccr-detail-drawer");
    var wasOpen = drawer.classList.contains("is-open");
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    document.getElementById("ccr-drawer-scrim").hidden = true;
    STATE.selectedWork = null;
    if (wasOpen) {
      var opener = LAST_DRAWER_OPENER;
      LAST_DRAWER_OPENER = null;
      restoreFocus(opener);
    }
  }

  // loose ends ------------------------------------------------------------
  function renderLooseRows(selector, rows, rowBuilder, emptyLine) {
    var list = document.querySelector(selector + " ul");
    if (!list) return 0;
    clear(list);
    (rows || []).forEach(function (row) { list.appendChild(rowBuilder(row)); });
    if (!rows || !rows.length) list.appendChild(el("li", { text: emptyLine, className: "ccr-empty-line" }));
    return (rows || []).length;
  }

  function renderLooseEnds(doc) {
    var unjoined = renderLooseRows("#unjoined-prs", doc.unjoined_open_prs, function (pr) {
      var li = el("li", { className: "ccr-row" });
      li.appendChild(el("span", { text: safeText(pr.repo) + " #" + safeText(pr.number) + " · " + safeText(pr.title, "Untitled PR"), className: "ccr-row-title" }));
      li.appendChild(el("a", { text: "Open PR", className: "ccr-open-button", attrs: { href: pr.url || "#", target: "_blank", rel: "noopener noreferrer" } }));
      return li;
    }, "Every loaded open PR is claimed by a work card.");

    var unbound = renderLooseRows("#unbound-surfaces", doc.unbound_surfaces, function (binding) {
      var li = el("li", { className: "ccr-row" });
      li.appendChild(el("span", { text: safeText(binding.work_ref) + " · " + safeText(binding.role) + " · " + safeText(binding.provider), className: "ccr-row-title ccr-row-id" }));
      li.appendChild(chip("UNJOINED", "is-dim"));
      return li;
    }, "Every binding points at loaded work.");

    var conflicts = renderLooseRows("#binding-conflicts", doc.binding_conflicts, function (row) {
      var li = el("li", { className: "ccr-row" });
      var claimantIds = (row.binding_ids || []).map(function (id) { return String(id); });
      var claimantText = claimantIds.length ? claimantIds.join(", ") : "claimants unknown";
      li.appendChild(el("span", {
        text: safeText(row.work_ref) + " · " + safeText(row.role) + " · " + claimantIds.length + " claims · " + claimantText,
        className: "ccr-row-title ccr-row-id",
      }));
      li.appendChild(chip("CONFLICT", "is-danger"));
      return li;
    }, "No work/role navigation slot has competing claims.");

    setTally("unjoined", unjoined);
    setTally("unbound", unbound);
    setTally("conflicts", conflicts);
    setTally("loose", unjoined + unbound + conflicts);
    return unjoined + unbound + conflicts;
  }

  // command palette -------------------------------------------------------
  function rebuildPaletteIndex() {
    var items = [];
    STATE.work.forEach(function (card) {
      var ao = card.agent_os || {};
      items.push({
        kind: "work",
        title: safeText(ao.title, card.work_ref),
        sub: safeText(card.work_ref) + (ao.program ? " · " + ao.program : ""),
        search: [card.work_ref, ao.title, ao.program, ao.next_action].map(normalizedSearchText).join(" "),
        actionLabel: "Inspect",
        action: function () {
          var opener = LAST_PALETTE_OPENER;
          closePalette(false);
          openDetail(card, opener);
        },
      });
      (((card.github || {}).prs) || []).forEach(function (pr) {
        items.push({
          kind: "PR",
          title: safeText(pr.title, "Untitled PR"),
          sub: safeText(pr.repo) + " #" + safeText(pr.number) + " · " + safeText(card.work_ref),
          search: [pr.title, pr.repo, pr.number, card.work_ref].map(normalizedSearchText).join(" "),
          actionLabel: "Open",
          action: function () {
            closePalette();
            if (pr.url) window.open(pr.url, "_blank", "noopener");
          },
        });
      });
    });
    allBindings().forEach(function (binding) {
      var confidence = bindingConfidence(binding);
      var relatedCard = STATE.workByRef[binding.work_ref] || null;
      items.push({
        kind: "surface",
        title: seatLabel(binding) + " · " + workTitle(binding.work_ref),
        sub: safeText(binding.provider) + " · " + safeText(binding.work_ref) + " · " + confidence.state,
        search: [binding.seat_ref, binding.provider, binding.role, binding.work_ref, workTitle(binding.work_ref)].map(normalizedSearchText).join(" "),
        actionLabel: confidence.openable ? "Open" : "Inspect",
        action: function () {
          var opener = LAST_PALETTE_OPENER;
          closePalette(false);
          if (confidence.openable) {
            openBinding(binding, null, null).then(function () { loadState(); restoreFocus(opener); });
          } else if (relatedCard) {
            openDetail(relatedCard, opener);
          } else {
            document.getElementById("system").scrollIntoView({ behavior: "smooth", block: "start" });
            setActiveNav("system");
            restoreFocus(opener);
          }
        },
      });
    });
    STATE.paletteItems = items;
  }

  function paletteSearch(query) {
    var q = normalizedSearchText(query).trim();
    var rows = STATE.paletteItems.filter(function (item) { return !q || item.search.indexOf(q) !== -1; });
    return rows.slice(0, 30);
  }

  function renderPaletteResults() {
    var container = document.getElementById("ccr-palette-results");
    clear(container);
    var query = document.getElementById("ccr-palette-input").value;
    STATE.paletteResults = paletteSearch(query);
    if (STATE.paletteIndex >= STATE.paletteResults.length) STATE.paletteIndex = 0;
    if (!STATE.paletteResults.length) {
      container.appendChild(el("div", { text: "No loaded work, surface or PR matches that search.", className: "ccr-palette-empty" }));
      return;
    }
    STATE.paletteResults.forEach(function (item, index) {
      var row = el("button", { className: "ccr-palette-result" + (index === STATE.paletteIndex ? " is-active" : "") });
      row.type = "button";
      row.appendChild(el("span", { text: item.kind, className: "ccr-palette-kind" }));
      var copy = el("span");
      copy.appendChild(el("div", { text: item.title, className: "ccr-palette-title" }));
      copy.appendChild(el("div", { text: item.sub, className: "ccr-palette-sub" }));
      row.appendChild(copy);
      row.appendChild(el("span", { text: item.actionLabel || (item.kind === "work" ? "Inspect" : "Open"), className: "ccr-palette-action" }));
      row.addEventListener("click", item.action);
      container.appendChild(row);
    });
  }

  function openPalette(opener) {
    LAST_PALETTE_OPENER = openerCandidate(opener);
    var wrap = document.getElementById("ccr-palette");
    wrap.hidden = false;
    STATE.paletteIndex = 0;
    var input = document.getElementById("ccr-palette-input");
    input.value = "";
    renderPaletteResults();
    input.focus();
  }

  function closePalette(restore) {
    var wrap = document.getElementById("ccr-palette");
    var wasOpen = !wrap.hidden;
    wrap.hidden = true;
    if (wasOpen && restore !== false) {
      var opener = LAST_PALETTE_OPENER;
      LAST_PALETTE_OPENER = null;
      restoreFocus(opener);
    }
  }

  // discovery / bind ------------------------------------------------------
  function discoverGroup(container, heading, rows, toText, emptyLine, runningChip) {
    container.appendChild(el("h3", { text: heading }));
    var list = el("ul");
    (rows || []).forEach(function (row) {
      var li = el("li", { className: runningChip ? "ccr-row" : "" });
      li.appendChild(el("span", { text: toText(row), className: runningChip ? "ccr-row-title ccr-row-id" : "" }));
      if (runningChip) li.appendChild(chip(row.running ? "running profile" : "not running", row.running ? "is-slate" : "is-dim"));
      list.appendChild(li);
    });
    if (!rows || !rows.length) list.appendChild(el("li", { text: emptyLine, className: "ccr-empty-line" }));
    container.appendChild(list);
  }

  function renderDiscoverResults(doc) {
    var container = document.getElementById("discover-results");
    clear(container);
    doc = doc || {};
    var envs = doc.chatgpt_environments || {};
    discoverGroup(container, "ChatGPT · Multilogin", envs.multilogin, function (row) { return "folder " + safeText(row.folder_id) + " · profile " + safeText(row.profile_id); }, "No local Multilogin environment found.", true);
    discoverGroup(container, "ChatGPT · GoLogin", envs.gologin, function (row) { return "profile " + safeText(row.profile_id); }, "No local GoLogin environment found.", true);
    discoverGroup(container, "Claude Code", doc.claude_code_sessions, function (row) { return safeText(row.project_dir) + " / " + safeText(row.session_id); }, "No Claude Code session found.", false);
    discoverGroup(container, "Codex", doc.codex_sessions, function (row) { return safeText(row.date) + " / " + safeText(row.session_id); }, "No Codex session found.", false);

    var cursor = doc.cursor || {};
    container.appendChild(el("h3", { text: "Cursor" }));
    container.appendChild(el("p", {
      text: safeText(cursor.note, cursor.supported === false ? "Cursor native thread discovery is unsupported." : "Cursor discovery state is unknown."),
      className: "ccr-empty-line",
    }));
  }

  function updateBindFieldVisibility() {
    var provider = document.getElementById("bind-provider").value;
    var isChatgpt = provider === "chatgpt";
    document.getElementById("bind-chatgpt-fields").hidden = !isChatgpt;
    document.getElementById("bind-locator-field").hidden = isChatgpt;
    document.getElementById("bind-locator").required = !isChatgpt;
    var manager = document.getElementById("bind-chatgpt-manager").value;
    document.getElementById("bind-chatgpt-folder-field").hidden = !isChatgpt || manager !== "multilogin";
  }

  function buildChatgptLocator() {
    var manager = document.getElementById("bind-chatgpt-manager").value;
    var profileId = document.getElementById("bind-chatgpt-profile-id").value.trim();
    var url = document.getElementById("bind-chatgpt-url").value.trim();
    if (!profileId || !url) return null;
    var locator = { env_manager: manager, profile_id: profileId, url: url };
    if (manager === "multilogin") {
      var folderId = document.getElementById("bind-chatgpt-folder-id").value.trim();
      if (!folderId) return null;
      locator.folder_id = folderId;
    }
    return locator;
  }

  // autonomy --------------------------------------------------------------
  // Presentation law for this section:
  // - owed action and gate lead; event volume is never the headline;
  // - a stale card is drawn as history and never as a live state;
  // - a placement the projection marked not_observable is drawn as an absence,
  //   never as an available capability;
  // - every seat, gate and freshness word is source-owned; nothing is inferred.
  var AU_SEAT_ORDER = ["chairman", "ceo", "coo", "worker", "unknown"];
  var AU_SEAT_SHORT = { chairman: "You", ceo: "Sol", coo: "Fable", worker: "Worker", unknown: "None" };
  var AU_TURN_HEADLINE = {
    chairman: "Your turn",
    ceo: "Sol's turn",
    coo: "Fable's turn",
    worker: "Worker's turn",
    unknown: "No turn recorded",
  };
  var AU_TURN_REASON = {
    blocker_targets_seat: "A recorded gate names this seat.",
    agent_os_declared_blocker_targets_seat: "Agent OS declared this workstream blocked, naming this seat.",
    attention_targets_seat: "A canonical attention fact names this seat.",
    // Repair D (Sol addendum, 2026-09-03): the backend reason token is
    // `worker_runtime_present` and names PRESENCE, never activity — this
    // map keyed `worker_runtime_active`, which the backend never emits, so
    // the row silently fell through to its default. The wording follows the
    // token: a runtime is attached; its liveness is not provable here.
    worker_runtime_present: "A worker runtime is attached to this work.",
    no_owed_turn_signal: "No canonical source records whose move comes next.",
  };
  var AU_ACTIONABILITY = {
    actionable: "Live — this can be acted on now.",
    stale_history: "History — every contributing source is stale.",
    freshness_unknown: "Freshness unknown — not shown as live.",
    query_refused: "A canonical read was refused.",
    no_owed_turn_signal: "Nobody is recorded as owing the next move.",
    source_failure: "A contributing source failed.",
  };
  var AU_PLACEMENT = {
    EFFECT_UNKNOWN: "Effect not confirmed",
    DELIVERED_UNACKNOWLEDGED: "Delivered, not acknowledged",
    TARGET_ACKNOWLEDGED: "Target acknowledged",
    SOURCE_RESOLVED: "Source resolved",
    WAITING_CAPACITY: "Waiting for capacity",
    ELIGIBLE_CANDIDATE_OBSERVED: "Eligible candidate observed",
    ATTEMPT_WORKER_RUNTIMEBINDING_COMMITTED: "Attempt binding committed",
    ACTIVATION_REQUESTED: "Activation requested",
    ACTIVATION_CONFIRMED: "Activation confirmed",
    ACTIVATION_REFUSED_PRE_SUBMIT: "Activation refused before submit",
  };
  var AU_PLACEMENT_VARIANT = {
    EFFECT_UNKNOWN: "is-danger",
    ACTIVATION_REFUSED_PRE_SUBMIT: "is-danger",
    DELIVERED_UNACKNOWLEDGED: "is-brass",
    TARGET_ACKNOWLEDGED: "is-slate",
    SOURCE_RESOLVED: "is-slate",
    ACTIVATION_CONFIRMED: "is-slate",
    ACTIVATION_REQUESTED: "is-slate",
    ATTEMPT_WORKER_RUNTIMEBINDING_COMMITTED: "is-slate",
    ELIGIBLE_CANDIDATE_OBSERVED: "is-slate",
    WAITING_CAPACITY: "is-dim",
  };
  var AU_WAKE = {
    DELIVERED_UNACKNOWLEDGED: "Delivered, not acknowledged",
    TARGET_ACKNOWLEDGED: "Target acknowledged",
    SOURCE_RESOLVED: "Source resolved",
  };
  var AU_QUERY_CHIP = {
    degraded: { text: "READ DEGRADED", variant: "is-danger" },
    refused: { text: "READ REFUSED", variant: "is-danger" },
    unknown: { text: "READ UNKNOWN", variant: "is-dim" },
  };
  var AU_FRESHNESS_CHIP = {
    stale: { text: "STALE SOURCES", variant: "is-dim" },
    unknown: { text: "FRESHNESS UNKNOWN", variant: "is-dim" },
  };

  // Dispatch-consumption groundwork (AD-CR1A commissioning packet,
  // 2026-09-03). Mirrors control_plane.autonomy_control_room_projection.
  // DISPATCH_STATES exactly, one entry per closed-vocabulary token —
  // read-only, additive. `card.dispatch` IS populated: the compositor calls
  // attach_dispatch_consumption, so every card carries a dispatch row. (An
  // earlier revision of this comment said the opposite; it was written while
  // the compositor was out of scope and was left standing after the wiring
  // landed, which is exactly the kind of stale comment that tells a reviewer
  // a live behaviour cannot happen.)
  //
  // The proof chain remains visible as three independent readings. The
  // responsibility mapper owns the Runtime root, C2 owns the exact carrier,
  // and W3C owns canonical terminal/Wake truth. On the current protected base
  // C2's positive reader is owner-held, which keeps W3C unavailable rather
  // than letting this surface infer a carrier from job-tree shape. Any unsafe
  // state suppresses the owed-action Open control; Detail stays reachable.
  // Every function below remains undefined-safe.
  var AU_DISPATCH = {
    WAITING_CAPACITY: "Waiting for capacity",
    RECEIVER_SELECTED: "Receiver selected",
    DELIVERY_SENT: "Delivery sent",
    PICKUP_ACKNOWLEDGED: "Pickup acknowledged",
    STARTED: "Started",
    RETURNED: "Returned — awaiting Sol",
    CONTINUED: "Continued",
    STOPPED: "Stopped",
    DELIVERY_UNCONSUMED: "Delivered, never picked up",
    WATCH_UNPROVEN: "Watch not proven",
    RUNTIME_BINDING_RECONCILIATION_REQUIRED: "Binding needs reconciliation",
    EFFECT_UNKNOWN: "Effect not confirmed",
    UNKNOWN: "Dispatch state unknown",
  };
  var AU_DISPATCH_VARIANT = {
    WAITING_CAPACITY: "is-dim",
    RECEIVER_SELECTED: "is-slate",
    DELIVERY_SENT: "is-slate",
    PICKUP_ACKNOWLEDGED: "is-slate",
    STARTED: "is-slate",
    RETURNED: "is-brass",
    CONTINUED: "is-ok",
    STOPPED: "is-slate",
    DELIVERY_UNCONSUMED: "is-danger",
    WATCH_UNPROVEN: "is-danger",
    RUNTIME_BINDING_RECONCILIATION_REQUIRED: "is-danger",
    EFFECT_UNKNOWN: "is-danger",
    UNKNOWN: "is-dim",
  };
  // The five states the FROZEN SPEC names verbatim: "No owed-action Open
  // control may render for a stale, unacknowledged, watch-unproven,
  // binding-reconciliation or effect-unknown state." UNKNOWN is included
  // defensively — the same "never fabricate a success" law this whole
  // surface exists to enforce.
  var AU_DISPATCH_UNSAFE = {
    DELIVERY_UNCONSUMED: true,
    WATCH_UNPROVEN: true,
    RUNTIME_BINDING_RECONCILIATION_REQUIRED: true,
    EFFECT_UNKNOWN: true,
    UNKNOWN: true,
  };
  var AU_RUNTIME_ROOT = {
    RESOLVED: { text: "ROOT RESOLVED", variant: "is-ok" },
    UNKNOWN: { text: "ROOT UNKNOWN", variant: "is-dim" },
    CONFLICT: { text: "ROOT CONFLICT", variant: "is-danger" },
  };
  var AU_CARRIER = {
    RESOLVED: { text: "C2 CARRIER RESOLVED", variant: "is-ok" },
    OWNER_HELD: { text: "C2 OWNER HELD", variant: "is-dim" },
    UNKNOWN: { text: "C2 CARRIER UNKNOWN", variant: "is-dim" },
  };
  var AU_W3C = {
    RESOLVED: { text: "W3C RESOLVED", variant: "is-ok" },
    ABSENT: { text: "W3C ABSENT", variant: "is-dim" },
    UNAVAILABLE: { text: "W3C UNAVAILABLE", variant: "is-dim" },
    CONFLICT: { text: "W3C CONFLICT", variant: "is-danger" },
    AMBIGUOUS: { text: "W3C AMBIGUOUS", variant: "is-danger" },
    EFFECT_UNKNOWN: { text: "W3C EFFECT UNKNOWN", variant: "is-danger" },
  };

  function auRuntimeRootChip(card) {
    var spec = AU_RUNTIME_ROOT[card.runtime_root_state];
    return spec ? chip(spec.text, spec.variant) : null;
  }

  function auCarrierChip(card) {
    var carrier = (card.dispatch || {}).carrier;
    var spec = carrier && AU_CARRIER[carrier.state];
    return spec ? chip(spec.text, spec.variant) : null;
  }

  function auW3cChip(card) {
    var w3c = (card.dispatch || {}).w3c;
    var spec = w3c && AU_W3C[w3c.state];
    return spec ? chip(spec.text, spec.variant) : null;
  }

  // True when this card's dispatch read is one of the five named-unsafe
  // states, or when Law 9's "stale/unknown contributing source" made the
  // read historical. False (never suppresses anything) when `card.dispatch`
  // is absent — a card with no dispatch evidence supplied is unaffected by
  // this gate until the projection is actually wired in.
  function auDispatchUnsafe(card) {
    var dispatch = card.dispatch;
    if (!dispatch) return false;
    if (AU_DISPATCH_UNSAFE[dispatch.dispatch_state] === true) return true;
    return dispatch.historical === true;
  }

  // Visible dispatch-state chip — the whole point of this projection: make
  // "was this actually picked up" a fact the Chairman can SEE, not infer.
  // Returns null (renders nothing) when no dispatch evidence exists yet.
  function auDispatchChip(card) {
    var dispatch = card.dispatch;
    if (!dispatch || isBlank(dispatch.dispatch_state)) return null;
    var value = String(dispatch.dispatch_state);
    var text = AU_DISPATCH[value] || value.replace(/_/g, " ");
    return chip(text.toUpperCase(), AU_DISPATCH_VARIANT[value] || "is-dim");
  }

  function auWords(map, code, fallback) {
    if (isBlank(code)) return fallback;
    return map[code] || String(code).replace(/_/g, " ");
  }

  function auIsHistory(card) {
    return card.actionability_reason === "stale_history" || card.freshness === "stale";
  }

  function auIsHold(card) {
    var placement = card.placement_state || {};
    var worker = card.current_worker || {};
    return placement.value === "EFFECT_UNKNOWN" || worker.effect_state === "effect_unknown";
  }

  function auOwedSeat(card) {
    var seat = (card.owed_turn || {}).seat;
    return AU_SEAT_SHORT[seat] ? seat : "unknown";
  }

  // Reuses the address-book law exactly: one unambiguous, openable destination
  // for the seat that owes the move, or nothing at all. A hold card (see
  // auIsHold) never yields a binding: the gate already tells the Chairman
  // the effect is unconfirmed, so no provider-actuating control may render
  // here either, regardless of who owes the turn.
  function auOwedBinding(card) {
    if (REMOTE_READ_ONLY) return null;
    if (auIsHold(card)) return null;
    // AD-CR1A dispatch-consumption groundwork, 2026-09-03: the FROZEN SPEC
    // names the same law auIsHold already enforces for EFFECT_UNKNOWN
    // placement, extended to the dispatch read — "No owed-action Open
    // control may render for a stale, unacknowledged, watch-unproven,
    // binding-reconciliation or effect-unknown state." A no-op today
    // (dispatch is populated by the compositor; an UNKNOWN state is
    // unsafe and suppresses the control by design)
    if (auDispatchUnsafe(card)) return null;
    // Repair B (Sol addendum 2, 2026-09-03): this suppressed only the
    // EFFECT_UNKNOWN hold, so a stale/history card still offered
    // "Open Sol/Fable/Worker" built from stale routing evidence while the
    // same card read HISTORY / NOT ACTIONABLE. An owed-action jump is a
    // present-tense instruction; only a currently actionable card may make
    // one. Detail stays available for forensic inspection, and the global
    // Surfaces address book is untouched.
    if (card.is_actionable !== true) return null;
    var seat = auOwedSeat(card);
    if (seat === "unknown") return null;
    var work = STATE.workByRef[card.responsibility_ref];
    var binding = uniqueBinding(work, seat);
    if (!binding) return null;
    return bindingConfidence(binding).openable ? binding : null;
  }

  function auTurnTrack(seat) {
    var track = el("div", { className: "ccr-au-track" });
    AU_SEAT_ORDER.forEach(function (name) {
      var cls = "ccr-au-seat";
      if (name === "unknown") cls += " is-open";
      if (name === seat) cls += " is-owed";
      var node = el("div", { className: cls });
      node.appendChild(el("span", { text: AU_SEAT_SHORT[name], className: "ccr-au-seat-name" }));
      track.appendChild(node);
    });
    return track;
  }

  function auReceiptLine(card) {
    var rows = card.source_receipts || [];
    if (!rows.length) return "No contributing source recorded";
    return rows.length + (rows.length === 1 ? " source · weakest " : " sources · weakest ") + safeText(card.freshness);
  }

  function auRuntimeWords(runtime, absent) {
    if (!runtime) return absent;
    var parts = [safeText(runtime.worker_id, "worker unnamed")];
    if (!isBlank(runtime.status)) parts.push(String(runtime.status));
    if (!isBlank(runtime.attempt_id)) parts.push("attempt " + runtime.attempt_id);
    if (!isBlank(runtime.capacity_state)) parts.push("capacity " + runtime.capacity_state);
    return parts.join(" · ");
  }

  function auPlacementChip(card) {
    var placement = card.placement_state || {};
    if (placement.observable !== true || placement.value === "not_observable" || isBlank(placement.value)) {
      return chip("PLACEMENT NOT OBSERVABLE", "is-dim");
    }
    var value = String(placement.value);
    return chip((AU_PLACEMENT[value] || value.replace(/_/g, " ")).toUpperCase(), AU_PLACEMENT_VARIANT[value] || "is-slate");
  }

  function auMarks(card) {
    var marks = el("div", { className: "ccr-au-marks" });
    if (card.chairman_decision_required === true) marks.appendChild(chip("YOUR CALL", "is-brass"));
    if (card.is_actionable === true && !auIsHistory(card)) marks.appendChild(chip("LIVE", "is-slate"));
    else if (auIsHistory(card)) marks.appendChild(chip("HISTORY", "is-dim"));
    else marks.appendChild(chip("NOT ACTIONABLE", "is-dim"));
    marks.appendChild(auPlacementChip(card));
    var dispatchChip = auDispatchChip(card);
    if (dispatchChip) marks.appendChild(dispatchChip);
    var rootChip = auRuntimeRootChip(card);
    if (rootChip) marks.appendChild(rootChip);
    var carrierChip = auCarrierChip(card);
    if (carrierChip) marks.appendChild(carrierChip);
    var w3cChip = auW3cChip(card);
    if (w3cChip) marks.appendChild(w3cChip);
    var freshness = AU_FRESHNESS_CHIP[card.freshness];
    if (freshness) marks.appendChild(chip(freshness.text, freshness.variant));
    var status = AU_QUERY_CHIP[card.query_status];
    if (status) marks.appendChild(chip(status.text, status.variant));
    if ((card.disagreements || []).length) marks.appendChild(chip("SOURCE DRIFT", "is-danger"));
    return marks;
  }

  // A declared_blocker is plain data Agent OS itself recorded — never a
  // Steward-owned gate (card.blocker) and never merged with one. It is
  // rendered as its own, distinctly labelled note so the Chairman can
  // always tell which system is making the claim.
  function auDeclaredBlockerNote(declared) {
    var note = el("div", { className: "ccr-au-declared" });
    note.appendChild(el("span", { text: "Agent OS declared", className: "ccr-au-declared-label" }));
    note.appendChild(el("p", {
      text: safeText(declared.explanation, "Agent OS recorded a blocker without an explanation."),
      className: "ccr-au-declared-text",
    }));
    var seatWords = declared.target_seat
      ? safeText(AU_SEAT_SHORT[declared.target_seat], safeText(declared.target_seat))
      : "no seat named";
    note.appendChild(el("p", {
      text: safeText(declared.code) + " · holds " + seatWords,
      className: "ccr-au-declared-code",
    }));
    return note;
  }

  function auRow(card) {
    var seat = auOwedSeat(card);
    var cls = "ccr-au-row";
    if (card.chairman_decision_required === true) cls += " is-decision";
    else if (seat === "ceo" || seat === "coo") cls += " is-owed-person";
    else if (seat === "worker") cls += " is-owed-machine";
    if (auIsHistory(card)) cls += " is-history";
    if (auIsHold(card)) cls += " is-hold";
    var row = el("article", { className: cls, attrs: { tabindex: "0" } });

    var id = el("div", { className: "ccr-au-id" });
    id.appendChild(el("div", { text: safeText(card.title, "Untitled responsibility"), className: "ccr-au-title" }));
    id.appendChild(el("div", { text: safeText(card.responsibility_ref), className: "ccr-au-ref" }));
    var stateWords = [
      AU_SEAT_SHORT[card.accountable_seat] ? "accountable " + AU_SEAT_SHORT[card.accountable_seat] : "",
      isBlank(card.state) ? "no recorded state" : String(card.state),
    ].filter(function (part) { return part !== ""; }).join(" · ");
    id.appendChild(el("div", { text: stateWords, className: "ccr-au-state" }));
    row.appendChild(id);

    var turn = el("div", { className: "ccr-au-turn" });
    turn.appendChild(el("span", { text: "Whose turn", className: "ccr-au-label" }));
    turn.appendChild(el("p", {
      text: AU_TURN_HEADLINE[seat],
      className: seat === "unknown" ? "ccr-au-turn-name is-unknown" : "ccr-au-turn-name",
    }));
    turn.appendChild(auTurnTrack(seat));
    turn.appendChild(el("p", {
      text: auWords(AU_TURN_REASON, (card.owed_turn || {}).reason, "No reason recorded."),
      className: "ccr-au-turn-reason",
    }));
    row.appendChild(turn);

    var read = el("div", { className: "ccr-au-read" });
    var blocker = card.blocker || null;
    var gate = el("div", { className: "ccr-au-gate" });
    gate.appendChild(el("span", { text: "Gate", className: "ccr-au-label" }));
    if (blocker) {
      gate.appendChild(el("p", { text: safeText(blocker.explanation, "A gate is recorded without an explanation."), className: "ccr-au-gate-text" }));
      gate.appendChild(el("p", {
        text: safeText(blocker.code) + " · holds " + safeText(AU_SEAT_SHORT[blocker.target_seat], safeText(blocker.target_seat)),
        className: "ccr-au-gate-code",
      }));
    } else {
      gate.appendChild(el("p", { text: "No recorded gate. Conditions are still being watched.", className: "ccr-au-gate-text is-quiet" }));
    }
    if (card.declared_blocker) gate.appendChild(auDeclaredBlockerNote(card.declared_blocker));
    if (auIsHold(card)) {
      gate.appendChild(el("p", {
        text: "Effect not confirmed — retry and failover are not permitted until a canonical source reads the effect.",
        className: "ccr-au-hold",
      }));
    }
    read.appendChild(gate);

    var onit = el("div", { className: "ccr-au-onit" });
    onit.appendChild(el("span", { text: "On it", className: "ccr-au-label" }));
    onit.appendChild(el("p", {
      text: "worker · " + auRuntimeWords(card.current_worker, "no worker runtime recorded"),
      className: card.current_worker ? "ccr-au-mono" : "ccr-au-mono is-quiet",
    }));
    onit.appendChild(el("p", {
      text: "sol target · " + auRuntimeWords(card.current_sol_target, "no Sol target recorded"),
      className: card.current_sol_target ? "ccr-au-mono" : "ccr-au-mono is-quiet",
    }));
    onit.appendChild(el("p", { text: auReceiptLine(card), className: "ccr-au-mono is-quiet" }));
    read.appendChild(onit);
    row.appendChild(read);

    var right = el("div", { className: "ccr-au-right" });
    right.appendChild(auMarks(card));
    var actions = el("div", { className: "ccr-au-actions" });
    var openBtn = button("Detail", "ccr-open-button", function (event) {
      event.stopPropagation();
      openAutonomyDetail(card, openBtn);
    });
    actions.appendChild(openBtn);
    var binding = auOwedBinding(card);
    if (binding) actions.appendChild(openBindingButton(binding, "Open " + AU_SEAT_SHORT[auOwedSeat(card)]));
    right.appendChild(actions);
    row.appendChild(right);

    row.addEventListener("click", function () { openAutonomyDetail(card, row); });
    row.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openAutonomyDetail(card, row);
      }
    });
    return row;
  }

  function auLedger(projection) {
    // Repair C (Sol addendum 3, 2026-09-03): `owed_by_seat` counts EVERY
    // recorded responsibility, including pure history. On the real all-stale
    // packet the ledger therefore showed seat counts and lit the Chairman
    // cell "is-yours" while the reading beside it said history 40 / live 0.
    // The ledger is a CURRENT-ACTION surface, so its per-seat turns are
    // derived from actionable cards only. Nothing is erased: counts.stale,
    // counts.total and each card's historical owed turn and receipts are
    // unchanged and still inspectable on the cards themselves.
    var counts = projection.counts || {};
    var owed = {};
    (projection.responsibilities || []).forEach(function (card) {
      if (!card || card.is_actionable !== true) return;
      var seat = card.owed_turn && card.owed_turn.seat ? card.owed_turn.seat : "unknown";
      owed[seat] = (typeof owed[seat] === "number" ? owed[seat] : 0) + 1;
    });
    var ledger = el("section", { className: "ccr-au-ledger" });

    var track = el("div", { className: "ccr-au-ledger-track" });
    AU_SEAT_ORDER.forEach(function (seat) {
      var value = typeof owed[seat] === "number" ? owed[seat] : 0;
      var cls = "ccr-au-ledger-cell";
      if (seat === "chairman" && value > 0) cls += " is-yours";
      if (seat === "unknown") cls += " is-open";
      if (value === 0) cls += " is-zero";
      var cell = el("div", { className: cls });
      cell.appendChild(el("div", { text: String(value), className: "ccr-au-ledger-count" }));
      cell.appendChild(el("div", { text: seat === "unknown" ? "No seat" : AU_SEAT_SHORT[seat], className: "ccr-au-ledger-name" }));
      track.appendChild(cell);
    });
    ledger.appendChild(track);

    var reading = el("div", { className: "ccr-au-reading" });
    [
      // "gated" stays the Steward-owned block count (card.blocker !=
      // null) exactly as before.  "declared" is a SEPARATE count of
      // Agent-OS-declared blocks (card.declared_blocker plus a declared
      // block on an unmapped row) — never merged into "gated" — so the
      // Chairman can never read "0 gated" while a declared block is
      // visible on a card or unmapped row directly beneath the ledger.
      ["live", counts.actionable],
      ["history", counts.stale],
      ["gated", counts.blocked],
      ["declared", counts.declared_blocked],
      ["carried", counts.total],
    ].forEach(function (pair) {
      var isDeclared = pair[0] === "declared" && typeof pair[1] === "number" && pair[1] > 0;
      var item = el("span", { className: "ccr-au-reading-item" + (isDeclared ? " is-declared" : "") });
      item.appendChild(el("strong", { text: typeof pair[1] === "number" ? String(pair[1]) : "—" }));
      item.appendChild(el("span", { text: pair[0] }));
      reading.appendChild(item);
    });
    ledger.appendChild(reading);
    return ledger;
  }

  function auDecisions(projection, byRef) {
    var refs = projection.chairman_decisions || [];
    var band = el("section", { className: refs.length ? "ccr-au-decisions ccr-has-items" : "ccr-au-decisions" });
    var head = el("div", { className: "ccr-au-decisions-head" });
    head.appendChild(el("p", { text: "Chairman", className: "ccr-section-eyebrow" }));
    head.appendChild(el("h3", { text: "Only you can decide" }));
    head.appendChild(el("span", { text: String(refs.length), className: "ccr-count" }));
    band.appendChild(head);

    if (!refs.length) {
      band.appendChild(el("p", { text: "Nothing here needs your decision. Every recorded turn belongs to an actor that can proceed on its own.", className: "ccr-empty-line" }));
      return band;
    }
    var list = el("ul", { className: "ccr-au-decision-list" });
    refs.forEach(function (ref) {
      var card = byRef[ref] || null;
      var li = el("li", { className: "ccr-au-decision" });
      var copy = el("div");
      copy.appendChild(el("div", { text: card ? safeText(card.title, ref) : String(ref), className: "ccr-au-decision-title" }));
      copy.appendChild(el("div", {
        text: card ? safeText(card.chairman_decision_reason, "Reason not recorded.") : "This reference is not in the loaded responsibility list.",
        className: "ccr-au-decision-reason",
      }));
      copy.appendChild(el("div", { text: String(ref), className: "ccr-au-ref" }));
      li.appendChild(copy);
      if (card) {
        var review = button("Review", "ccr-open-button", function (event) {
          event.stopPropagation();
          openAutonomyDetail(card, review);
        });
        li.appendChild(review);
      }
      list.appendChild(li);
    });
    band.appendChild(list);
    return band;
  }

  function auGapFold(projection) {
    var failures = projection.source_failures || [];
    var issues = projection.issues || [];
    var unmapped = projection.unmapped_responsibilities || [];
    // readGaps counts sources that failed to answer at all. total additionally
    // counts suppressed (unmapped-owner) workstreams, because a surface
    // carrying hidden workstreams must never summarise itself as zero and
    // must never claim every source answered — that would be false even
    // though no read literally failed.
    var readGaps = failures.length + issues.length;
    var total = readGaps + unmapped.length;
    var fold = el("details", { className: "ccr-fold ccr-au-gaps" });
    // When the only anomaly is suppressed workstreams (no read failures or
    // issues), the fold must not stay collapsed-by-default: that is exactly
    // the state that must never read as silence.
    if (!readGaps && unmapped.length) fold.open = true;
    var summary = el("summary");
    summary.appendChild(el("span", { text: "What could not be read" }));
    summary.appendChild(el("span", { text: String(total), className: "ccr-count" }));
    fold.appendChild(summary);
    var wrap = el("div");
    wrap.appendChild(el("p", {
      text: total
        ? "These reads did not answer, or workstreams were hidden below. Losing a source removes detail; it never changes what the canonical sources above already recorded."
        : "Every contributing source answered.",
      className: "ccr-au-gap-note",
    }));
    if (readGaps) {
      var list = el("ul", { className: "ccr-au-gap-list" });
      failures.forEach(function (row) {
        var li = el("li", { className: "ccr-row" });
        li.appendChild(el("span", {
          text: safeText(row.owner) + " · " + safeText(row.code) + " · " + safeText(row.explanation, "no explanation") + " · " + safeText(row.source_ref),
          className: "ccr-row-title ccr-row-id",
        }));
        li.appendChild(chip("SOURCE FAILED", "is-danger"));
        list.appendChild(li);
      });
      issues.forEach(function (row) {
        var li = el("li", { className: "ccr-row" });
        li.appendChild(el("span", {
          text: safeText(row.responsibility_ref, "snapshot-wide") + " · " + safeText(row.code) + " · " + safeText(row.message, "no message"),
          className: "ccr-row-title ccr-row-id",
        }));
        li.appendChild(chip("ISSUE", "is-dim"));
        list.appendChild(li);
      });
      wrap.appendChild(list);
    }
    // Not a source failure and not an alarm: a workstream whose recorded
    // owner is not a recognized seat is simply not shown as a card. Render
    // nothing when there are none.
    if (unmapped.length) {
      wrap.appendChild(el("p", {
        text: "These workstreams are not shown as responsibility cards because their recorded owner is not a recognized seat. This does not affect any responsibility shown above.",
        className: "ccr-au-gap-note",
      }));
      var unmappedList = el("ul", { className: "ccr-au-gap-list" });
      unmapped.forEach(function (row) {
        var li = el("li", { className: "ccr-row" });
        li.appendChild(el("span", {
          text: safeText(row.responsibility_ref, "snapshot-wide") + " · " + safeText(row.reason, "owner_not_a_recognized_seat"),
          className: "ccr-row-title ccr-row-id",
        }));
        li.appendChild(chip("NOT MAPPED", "is-dim"));
        unmappedList.appendChild(li);
      });
      wrap.appendChild(unmappedList);
    }
    fold.appendChild(wrap);
    return fold;
  }

  function auReceiptFold(name, rows) {
    if (!rows || !rows.length) return null;
    var fold = el("details", { className: "ccr-fold" });
    var summary = el("summary");
    summary.appendChild(el("span", { text: name }));
    summary.appendChild(el("span", { text: String(rows.length), className: "ccr-count" }));
    fold.appendChild(summary);
    var list = el("ul");
    rows.forEach(function (row) {
      list.appendChild(el("li", {
        text: safeText(row.owner) + " · " + safeText(row.ref) + " · " + safeText(row.observed_at, "no observed time") + " · " + safeText(row.freshness),
        className: "ccr-row ccr-row-id",
      }));
    });
    fold.appendChild(list);
    return fold;
  }

  function auRuntimeRail(node, runtime, absent) {
    if (!runtime) { detailLine(node, absent, true); return; }
    [
      ["worker", runtime.worker_id], ["attempt", runtime.attempt_id], ["status", runtime.status],
      ["session alias", runtime.session_alias], ["runtime binding", runtime.runtime_binding_id],
      ["binding generation", runtime.binding_generation], ["continuation", runtime.continuation_state],
      ["effect", runtime.effect_state], ["capacity", runtime.capacity_state],
      ["previous attempt", runtime.previous_attempt_id], ["movement reason", runtime.movement_reason_code],
    ].forEach(function (pair) {
      if (!isBlank(pair[1])) detailLine(node, pair[0] + " " + pair[1], true);
    });
  }

  function renderAutonomyDetail(card) {
    var seat = auOwedSeat(card);
    document.getElementById("ccr-detail-ref").textContent = "RESPONSIBILITY · " + safeText(card.responsibility_ref).toUpperCase();
    document.getElementById("ccr-detail-title").textContent = safeText(card.title, "Untitled responsibility");
    var body = document.getElementById("ccr-detail-body");
    clear(body);

    var summary = el("section", { className: "ccr-detail-summary" });
    summary.appendChild(el("span", { text: "Whose turn", className: "ccr-detail-next-label" }));
    summary.appendChild(el("p", { text: AU_TURN_HEADLINE[seat], className: "ccr-detail-next" }));
    summary.appendChild(el("p", {
      text: auWords(AU_TURN_REASON, (card.owed_turn || {}).reason, "No reason recorded."),
      className: "ccr-au-detail-sub",
    }));
    body.appendChild(summary);

    if (auIsHold(card)) {
      body.appendChild(el("p", {
        text: "Effect not confirmed — retry and failover are not permitted until a canonical source reads the effect.",
        className: "ccr-au-hold",
      }));
    }

    var rails = el("div", { className: "ccr-detail-rails" });
    detailRail(rails, "Reading", function (node) {
      detailLine(node, auWords(AU_ACTIONABILITY, card.actionability_reason, "No actionability reason recorded."), false);
      detailLine(node, "freshness " + safeText(card.freshness) + " · read " + safeText(card.query_status), true);
      if (card.chairman_decision_required === true) {
        detailLine(node, safeText(card.chairman_decision_reason, "Chairman decision required; reason not recorded."), false);
      }
    });
    detailRail(rails, "Gate", function (node) {
      var blocker = card.blocker || null;
      if (blocker) {
        detailLine(node, safeText(blocker.explanation, "A gate is recorded without an explanation."), false);
        detailLine(node, "code " + safeText(blocker.code) + " · holds " + safeText(AU_SEAT_SHORT[blocker.target_seat], safeText(blocker.target_seat)) + " · effect " + safeText(blocker.effect_state), true);
      } else if (!card.declared_blocker) {
        detailLine(node, "No recorded gate. Conditions are still being watched.", false);
      }
      var declaredBlocker = card.declared_blocker || null;
      if (declaredBlocker) {
        detailLine(node, "Agent OS declared: " + safeText(declaredBlocker.explanation, "no explanation recorded"), false);
        var seatWords = declaredBlocker.target_seat
          ? safeText(AU_SEAT_SHORT[declaredBlocker.target_seat], safeText(declaredBlocker.target_seat))
          : "no seat named";
        detailLine(node, "code " + safeText(declaredBlocker.code) + " · holds " + seatWords, true);
      }
    });
    detailRail(rails, "Placement", function (node) {
      var placement = card.placement_state || {};
      if (placement.observable !== true || placement.value === "not_observable" || isBlank(placement.value)) {
        detailLine(node, "Not observable from canonical sources.", false);
        detailLine(node, "reason " + safeText(placement.reason, "not recorded"), true);
      } else {
        detailLine(node, AU_PLACEMENT[placement.value] || String(placement.value).replace(/_/g, " "), false);
        detailLine(node, "token " + safeText(placement.value) + " · reason " + safeText(placement.reason, "not recorded"), true);
      }
      detailLine(node, "wake " + (AU_WAKE[card.wake_outcome] || "not observable"), true);
    });
    detailRail(rails, "Dispatch proof", function (node) {
      var dispatch = card.dispatch || {};
      var carrier = dispatch.carrier || null;
      var w3c = dispatch.w3c || null;
      var evidence = dispatch.evidence || {};
      detailLine(node, "Runtime root " + safeText(card.runtime_root_state, "UNKNOWN"), false);
      detailLine(node, "dispatch " + safeText(dispatch.dispatch_state, "UNKNOWN") + " · " + safeText(dispatch.reason, "reason not recorded"), true);
      if (!isBlank(evidence.runtime_generation_state)) {
        detailLine(node, "Runtime generation " + safeText(evidence.runtime_generation_state, "UNKNOWN"), true);
        detailLine(node, "before " + safeText(evidence.runtime_generation_before, "not recorded"), true);
        detailLine(node, "after " + safeText(evidence.runtime_generation_after, "not recorded"), true);
      }
      if (carrier) {
        detailLine(node, "C2 carrier " + safeText(carrier.state, "UNKNOWN") + " · " + safeText(carrier.reason, "reason not recorded"), true);
      } else {
        detailLine(node, "C2 carrier not observed", true);
      }
      if (w3c) {
        detailLine(node, "W3C " + safeText(w3c.state, "UNKNOWN") + " · terminal " + safeText(w3c.terminal_state, "UNKNOWN") + " · wake " + safeText(w3c.wake_state, "UNKNOWN"), true);
        var receipt = dispatch.w3c.source_receipt;
        if (receipt) {
          detailLine(node, "source time " + safeText(receipt.observed_at, "not recorded") + " · " + safeText(receipt.freshness, "freshness unknown"), true);
          detailLine(node, "snapshot " + safeText(receipt.snapshot_digest, "not recorded"), true);
          detailLine(node, "terminal owner " + safeText(receipt.terminal_source_owner, "not recorded"), true);
          detailLine(node, "wake owner " + safeText(receipt.wake_source_owner, "not recorded"), true);
        } else {
          detailLine(node, "No canonical W3C source receipt.", true);
        }
      } else {
        detailLine(node, "W3C not observed", true);
      }
    });
    detailRail(rails, "Worker", function (node) { auRuntimeRail(node, card.current_worker, "silent — no worker runtime is recorded"); });
    detailRail(rails, "Sol target", function (node) { auRuntimeRail(node, card.current_sol_target, "silent — no Sol target runtime is recorded"); });
    detailRail(rails, "Identity", function (node) {
      detailLine(node, "responsibility " + safeText(card.responsibility_ref), true);
      detailLine(node, "accountable " + safeText(card.accountable_seat) + " · state " + safeText(card.state, "not recorded"), true);
      detailLine(node, "root job " + safeText(card.root_job_id, "not recorded"), true);
      if (card.root_job_ambiguous === true) {
        var candidates = card.root_job_candidates || [];
        detailLine(node, "root job ambiguous — " + candidates.length + " distinct Runtime roots cite this workstream, reconciliation required (never picked)", false);
      }
    });
    body.appendChild(rails);

    if ((card.disagreements || []).length) {
      var drift = el("section", { className: "ccr-detail-section" });
      drift.appendChild(el("h3", { text: "Source drift — both readings kept" }));
      card.disagreements.forEach(function (entry) {
        var block = el("div", { className: "ccr-disagreement" });
        block.appendChild(el("div", { text: safeText(entry.field) + " · " + (entry.values || []).join("  |  ") }));
        (entry.sources || []).forEach(function (source) {
          block.appendChild(el("div", { text: safeText(source.owner) + " · " + safeText(source.ref) + " · " + safeText(source.freshness) }));
        });
        drift.appendChild(block);
      });
      body.appendChild(drift);
    }

    var receiptSection = el("section", { className: "ccr-detail-section" });
    receiptSection.appendChild(el("h3", { text: "Source receipts" }));
    var receipts = auReceiptFold("Contributing sources", card.source_receipts);
    if (receipts) receiptSection.appendChild(receipts);
    else receiptSection.appendChild(el("p", { text: "No contributing source is recorded for this responsibility.", className: "ccr-empty-line" }));
    var turnRefs = auReceiptFold("Turn evidence", (card.owed_turn || {}).source_refs);
    if (turnRefs) receiptSection.appendChild(turnRefs);
    if (card.declared_blocker) {
      var declaredReceipt = auReceiptFold("Agent OS declared blocker", [card.declared_blocker.source]);
      if (declaredReceipt) receiptSection.appendChild(declaredReceipt);
    }
    var cardIssues = ((STATE.autonomy || {}).issues || []).filter(function (row) {
      return row && row.responsibility_ref === card.responsibility_ref;
    });
    if (cardIssues.length) {
      var issueFold = el("details", { className: "ccr-fold" });
      var issueSummary = el("summary");
      issueSummary.appendChild(el("span", { text: "Read issues" }));
      issueSummary.appendChild(el("span", { text: String(cardIssues.length), className: "ccr-count" }));
      issueFold.appendChild(issueSummary);
      var issueList = el("ul");
      cardIssues.forEach(function (row) {
        issueList.appendChild(el("li", { text: safeText(row.code) + " · " + safeText(row.message), className: "ccr-row ccr-row-id" }));
      });
      issueFold.appendChild(issueList);
      receiptSection.appendChild(issueFold);
    }
    body.appendChild(receiptSection);
  }

  function openAutonomyDetail(card, opener) {
    LAST_DRAWER_OPENER = openerCandidate(opener);
    STATE.selectedWork = null;
    renderAutonomyDetail(card);
    var drawer = document.getElementById("ccr-detail-drawer");
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    document.getElementById("ccr-drawer-scrim").hidden = false;
    document.getElementById("ccr-drawer-close").focus();
  }

  function auNotWired(mount) {
    var panel = el("section", { className: "ccr-au-quiet" });
    panel.appendChild(el("p", { text: "Not wired yet", className: "ccr-au-quiet-title" }));
    panel.appendChild(el("p", {
      text: "The Control Room is not serving an autonomy projection on this state document. Nothing is hidden and nothing has failed — this surface stays blank until the server publishes it.",
      className: "ccr-au-quiet-text",
    }));
    mount.appendChild(panel);
  }

  function renderAutonomy(projection) {
    var mount = document.getElementById("ccr-autonomy");
    if (!mount) return;
    clear(mount);
    var count = document.getElementById("nav-autonomy-count");
    STATE.autonomy = projection && typeof projection === "object" ? projection : null;

    if (!STATE.autonomy) {
      auNotWired(mount);
      if (count) count.textContent = "—";
      return;
    }

    var cards = STATE.autonomy.responsibilities || [];
    var byRef = {};
    cards.forEach(function (card) { if (card && card.responsibility_ref) byRef[card.responsibility_ref] = card; });

    mount.appendChild(auDecisions(STATE.autonomy, byRef));
    mount.appendChild(auLedger(STATE.autonomy));

    var list = el("div", { className: "ccr-au-list" });
    if (!cards.length) {
      list.appendChild(el("p", {
        text: "No responsibility is being carried right now. The projection answered and returned an empty list.",
        className: "ccr-au-list-empty",
      }));
    } else {
      cards.forEach(function (card) { list.appendChild(auRow(card)); });
    }
    mount.appendChild(list);
    mount.appendChild(auGapFold(STATE.autonomy));
    if (count) count.textContent = String(cards.length);
  }

  // state -----------------------------------------------------------------
  function indexState(doc) {
    STATE.work = doc.work || [];
    STATE.workByRef = {};
    STATE.work.forEach(function (card) { STATE.workByRef[card.work_ref] = card; });
    STATE.attentionTargetById = {};
    var attention = doc.attention || {};
    ["chairman", "ceo", "coo"].forEach(function (target) {
      (attention[target] || []).forEach(function (item) {
        if (item.attention_id) STATE.attentionTargetById[item.attention_id] = target;
      });
    });
  }

  function renderEverything(body) {
    var doc = (body && body.control_room) || {};
    STATE.body = body || {};
    STATE.doc = doc;
    STATE.capabilities = (body && body.capabilities) || {};
    indexState(doc);

    if (REMOTE_READ_ONLY) {
      renderRemoteSources(doc, doc.source_freshness, doc.code_identity);
    } else {
      var sources = {};
      Object.keys(doc.sources || {}).forEach(function (key) { sources[key] = doc.sources[key]; });
      sources.composed_at = body && body.composed_at;
      renderSourcePulse(body, sources);
      renderSystemSources(sources);
    }

    var degraded = (doc.degraded || []).slice();
    if (body && body.state_refresh_error) degraded.push(body.state_refresh_error);
    renderDegraded(degraded);

    var attention = doc.attention || {};
    var attentionState = attentionReadState(doc, body);
    var chairman = attention.chairman || [];
    var ceo = attention.ceo || [];
    var coo = attention.coo || [];
    renderNeedsYou(chairman, attentionState);
    renderMiniAttention("sol-attention", ceo, attentionState);
    renderMiniAttention("coo", coo, attentionState);
    var attentionTally = attentionState === "current" ? chairman.length : "—";
    setTally("chairman", attentionTally);
    setTally("ceo", attentionState === "current" ? ceo.length : "—");
    setTally("coo", attentionState === "current" ? coo.length : "—");
    document.getElementById("nav-today-count").textContent = String(attentionTally);

    renderAutonomy(doc.autonomy);
    renderWork();
    if (!REMOTE_READ_ONLY) renderSurfaces();
    var loose = renderLooseEnds(doc);
    if (!REMOTE_READ_ONLY) renderCapabilities(STATE.capabilities);
    rebuildPaletteIndex();

    if (STATE.selectedWork && STATE.workByRef[STATE.selectedWork.work_ref]) {
      STATE.selectedWork = STATE.workByRef[STATE.selectedWork.work_ref];
      renderDetail(STATE.selectedWork);
    }
    document.getElementById("nav-system-count").textContent = degraded.length || loose ? String(degraded.length + loose) : "";
  }

  function loadState() {
    return getJSON("/api/state").then(function (body) {
      renderEverything(body);
      return body;
    }).catch(function () {
      renderDegraded(["control_room_api: unavailable — this page could not reach the state endpoint"]);
      var previous = STATE.doc && typeof STATE.doc === "object" ? STATE.doc : {};
      var attention = previous.attention && typeof previous.attention === "object" ? previous.attention : {};
      renderNeedsYou(Array.isArray(attention.chairman) ? attention.chairman : [], "unavailable");
      renderMiniAttention("sol-attention", Array.isArray(attention.ceo) ? attention.ceo : [], "unavailable");
      renderMiniAttention("coo", Array.isArray(attention.coo) ? attention.coo : [], "unavailable");
      setTally("chairman", "—");
      setTally("ceo", "—");
      setTally("coo", "—");
      document.getElementById("nav-today-count").textContent = "—";
      return null;
    });
  }

  // theme -----------------------------------------------------------------
  function readTheme() {
    try {
      var mode = window.localStorage.getItem(THEME_KEY);
      return mode === "light" || mode === "dark" || mode === "system" ? mode : "dark";
    } catch (_e) { return "dark"; }
  }

  function resolvedSystemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function applyTheme(mode) {
    var resolved = mode === "system" ? resolvedSystemTheme() : mode;
    document.documentElement.setAttribute("data-theme", resolved);
    var btn = document.getElementById("ccr-theme");
    if (btn) {
      btn.textContent = mode === "system" ? "Theme · System" : "Theme · " + mode.charAt(0).toUpperCase() + mode.slice(1);
      btn.setAttribute("aria-label", btn.textContent);
      btn.setAttribute("title", btn.textContent);
    }
  }

  function cycleTheme() {
    var modes = ["dark", "light", "system"];
    var current = readTheme();
    var next = modes[(modes.indexOf(current) + 1) % modes.length];
    try { window.localStorage.setItem(THEME_KEY, next); } catch (_e) { /* no-op */ }
    applyTheme(next);
  }

  // nav -------------------------------------------------------------------
  function setActiveNav(name) {
    var links = document.querySelectorAll("[data-nav]");
    for (var i = 0; i < links.length; i++) {
      links[i].classList.toggle("is-active", links[i].getAttribute("data-nav") === name);
    }
  }

  // wiring ----------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(readTheme());
    loadState();

    var dock = document.getElementById("ccr-surface-dock");
    var layout = document.querySelector(".ccr-layout");
    var collapsed = false;

    function desktopDockVisible() {
      return !REMOTE_READ_ONLY && !(window.matchMedia && window.matchMedia("(max-width: 1050px)").matches);
    }

    function applyDockState() {
      // Below the dock breakpoint the dock is replaced by the responsive
      // Surfaces section. A remembered desktop collapse preference must not
      // reserve a phantom 42px grid column when the dock itself is hidden.
      if (!dock) return;
      var activeCollapsed = collapsed && desktopDockVisible();
      dock.classList.toggle("is-collapsed", activeCollapsed);
      if (layout) layout.classList.toggle("ccr-dock-collapsed", activeCollapsed);
      var toggle = document.getElementById("ccr-dock-collapse");
      toggle.textContent = collapsed ? "›" : "‹";
      toggle.setAttribute("aria-label", collapsed ? "Expand surfaces" : "Collapse surfaces");
      toggle.setAttribute("aria-expanded", activeCollapsed ? "false" : "true");
    }

    if (!REMOTE_READ_ONLY) {
      try { collapsed = window.localStorage.getItem(DOCK_KEY) === "1"; } catch (_e) { collapsed = false; }
      applyDockState();
      window.addEventListener("resize", applyDockState);
    }

    document.getElementById("ccr-theme").addEventListener("click", cycleTheme);
    document.getElementById("ccr-command").addEventListener("click", function () { openPalette(this); });
    document.getElementById("ccr-palette-backdrop").addEventListener("click", function () { closePalette(); });
    document.getElementById("ccr-palette-input").addEventListener("input", function () { STATE.paletteIndex = 0; renderPaletteResults(); });
    document.getElementById("ccr-palette-input").addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (STATE.paletteResults.length) STATE.paletteIndex = (STATE.paletteIndex + 1) % STATE.paletteResults.length;
        renderPaletteResults();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (STATE.paletteResults.length) STATE.paletteIndex = (STATE.paletteIndex - 1 + STATE.paletteResults.length) % STATE.paletteResults.length;
        renderPaletteResults();
      } else if (event.key === "Enter") {
        event.preventDefault();
        if (STATE.paletteResults[STATE.paletteIndex]) STATE.paletteResults[STATE.paletteIndex].action();
      } else if (event.key === "Escape") {
        event.stopPropagation();
        closePalette();
      }
    });

    document.addEventListener("keydown", function (event) {
      var palette = document.getElementById("ccr-palette");
      var drawer = document.getElementById("ccr-detail-drawer");
      if (event.key === "Tab") {
        if (!palette.hidden) {
          trapFocus(event, palette);
          return;
        }
        if (drawer.classList.contains("is-open")) {
          trapFocus(event, drawer);
          return;
        }
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openPalette(document.activeElement);
      }
      if (event.key === "Escape") {
        if (!palette.hidden) closePalette();
        else closeDetail();
      }
    });

    document.getElementById("ccr-drawer-close").addEventListener("click", closeDetail);
    document.getElementById("ccr-drawer-scrim").addEventListener("click", closeDetail);

    document.getElementById("show-all-work").addEventListener("click", function () {
      STATE.workMode = "all";
      renderWork();
      document.getElementById("work").scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveNav("work");
    });
    document.getElementById("ccr-work-filter").addEventListener("input", function () { STATE.workQuery = this.value.trim(); renderWork(); });
    var workModeButtons = document.querySelectorAll("[data-work-mode]");
    for (var i = 0; i < workModeButtons.length; i++) {
      workModeButtons[i].addEventListener("click", function () {
        STATE.workMode = this.getAttribute("data-work-mode") || "focus";
        renderWork();
      });
    }

    var navLinks = document.querySelectorAll("[data-nav]");
    for (var n = 0; n < navLinks.length; n++) {
      navLinks[n].addEventListener("click", function (event) {
        var name = this.getAttribute("data-nav");
        if (name === "surfaces" && desktopDockVisible()) {
          event.preventDefault();
          collapsed = false;
          applyDockState();
          try { window.localStorage.setItem(DOCK_KEY, "0"); } catch (_e) { /* no-op */ }
          try { dock.focus({ preventScroll: true }); }
          catch (_e) { dock.focus(); }
        }
        setActiveNav(name);
      });
    }

    if (!REMOTE_READ_ONLY) {
      document.getElementById("ccr-dock-collapse").addEventListener("click", function () {
        collapsed = !collapsed;
        applyDockState();
        try { window.localStorage.setItem(DOCK_KEY, collapsed ? "1" : "0"); } catch (_e) { /* no-op */ }
      });

      document.getElementById("discover-run").addEventListener("click", function () {
      getJSON("/api/discover").then(renderDiscoverResults).catch(function () {
        var results = document.getElementById("discover-results");
        clear(results);
        results.appendChild(el("p", { text: "Discovery unavailable — local server request failed.", className: "ccr-problem" }));
      });
    });

      document.getElementById("refresh-builds").addEventListener("click", function () {
      var btn = this;
      var result = document.getElementById("refresh-builds-result");
      btn.disabled = true;
      result.className = "";
      result.textContent = "Reading GitHub…";
      postJSON("/api/refresh-builds", {}).then(function (outcome) {
        if (outcome && outcome.ok) {
          result.textContent = "Refreshed · " + safeText(outcome.collected_at);
          return loadState();
        }
        result.textContent = "Did not refresh · " + safeText(outcome && outcome.detail, "no detail");
        result.className = "ccr-problem";
        return null;
      }).catch(function () {
        result.textContent = "Did not refresh · local server unavailable";
        result.className = "ccr-problem";
      }).finally(function () { btn.disabled = false; });
    });

      document.getElementById("bind-provider").addEventListener("change", updateBindFieldVisibility);
      document.getElementById("bind-chatgpt-manager").addEventListener("change", updateBindFieldVisibility);
      updateBindFieldVisibility();
      document.getElementById("bind-form").addEventListener("submit", function (event) {
      event.preventDefault();
      var result = document.getElementById("bind-result");
      clear(result);
      var provider = document.getElementById("bind-provider").value;
      var locator;
      if (provider === "chatgpt") {
        locator = buildChatgptLocator();
        if (!locator) {
          result.appendChild(el("div", { text: "Fill the exact manager/profile/folder (when required) and conversation URL.", className: "ccr-problem" }));
          return;
        }
      } else {
        try { locator = JSON.parse(document.getElementById("bind-locator").value || "{}"); }
        catch (_e) {
          result.appendChild(el("div", { text: "Locator JSON is invalid.", className: "ccr-problem" }));
          return;
        }
      }
      var request = {
        work_ref: document.getElementById("bind-work-ref").value,
        role: document.getElementById("bind-role").value,
        provider: provider,
        locator: locator,
      };
      var seat = document.getElementById("bind-seat-ref").value.trim();
      if (seat) request.seat_ref = seat;
      postJSON("/api/bind", request).then(function (outcome) {
        clear(result);
        if (outcome && outcome.ok) {
          result.appendChild(el("div", { text: "Bound · " + safeText(outcome.binding_id) }));
          loadState();
        } else {
          ((outcome && outcome.problems) || ["The server refused the binding."]).forEach(function (problem) {
            result.appendChild(el("div", { text: problem, className: "ccr-problem" }));
          });
        }
      }).catch(function () {
        clear(result);
        result.appendChild(el("div", { text: "Binding request failed · local server unavailable", className: "ccr-problem" }));
      });
      });
    }
  });
})();
