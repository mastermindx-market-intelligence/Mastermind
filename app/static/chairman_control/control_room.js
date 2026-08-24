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
  var TOKEN = (function () {
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
  };

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

  // transport -------------------------------------------------------------
  function getJSON(path) {
    return fetch(path, {
      method: "GET",
      credentials: "same-origin",
      headers: { "X-CCR-Token": TOKEN },
    }).then(function (resp) {
      return resp.json();
    });
  }

  function postJSON(path, body) {
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
    // Ages are shown exactly as clocks, not interpreted against a UI-invented
    // freshness SLA. Source-owned degraded state is rendered separately.
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
    document.getElementById("ccr-detail-title").textContent = safeText(item.reason, "Attention item");
    var body = document.getElementById("ccr-detail-body");
    clear(body);

    var summary = el("section", { className: "ccr-detail-summary" });
    var meta = [
      ["id", item.attention_id],
      ["kind", item.kind],
      ["work", item.workstream],
      ["status", item.status],
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
      workSection.appendChild(button("Open work", "ccr-open-button", function () { openDetail(card); }));
      body.appendChild(workSection);
    }
  }

  function openAttentionDetail(item, target) {
    STATE.selectedWork = null;
    renderAttentionDetail(item, target);
    var drawer = document.getElementById("ccr-detail-drawer");
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    document.getElementById("ccr-drawer-scrim").hidden = false;
    document.getElementById("ccr-drawer-close").focus();
  }

  function renderNeedsYou(items) {
    var section = document.getElementById("needs-you");
    var list = section.querySelector(".ccr-attention-list");
    clear(list);
    var rows = items || [];
    section.className = rows.length ? "ccr-needs ccr-has-items" : "ccr-needs";
    if (!rows.length) {
      list.appendChild(el("li", { text: "Nothing is waiting on you.", className: "ccr-empty-line" }));
      return;
    }
    rows.forEach(function (item) {
      var li = el("li", { className: "ccr-attention-item" });
      var body = el("div");
      body.appendChild(el("p", { text: safeText(item.reason, "This item carries no reason text."), className: "ccr-attention-reason" }));
      var meta = el("div", { className: "ccr-attention-meta" });
      [
        ["work", item.workstream], ["kind", item.kind], ["status", item.status], ["reported by", item.source]
      ].forEach(function (pair) {
        if (!isBlank(pair[1])) meta.appendChild(el("span", { text: pair[0] + " " + pair[1] }));
      });
      body.appendChild(meta);
      var next = item.existing_next_actions || [];
      if (next.length) body.appendChild(el("p", { text: next.join(" · "), className: "ccr-attention-next" }));
      li.appendChild(body);

      var actions = el("div", { className: "ccr-attention-actions" });
      var card = findCardForAttention(item);
      actions.appendChild(button("Inspect", "ccr-open-button", function (event) {
        event.stopPropagation();
        openAttentionDetail(item, "chairman");
      }));
      if (card) actions.appendChild(button("Open work", "ccr-open-button", function (event) {
        event.stopPropagation();
        openDetail(card);
      }));
      var sol = uniqueBinding(card, "ceo");
      if (sol) actions.appendChild(openBindingButton(sol, "Open Sol"));
      li.appendChild(actions);
      list.appendChild(li);
    });
  }

  function renderMiniAttention(containerId, items) {
    var container = document.querySelector("#" + containerId + " .ccr-mini-list");
    clear(container);
    var rows = items || [];
    var target = containerId === "sol-attention" ? "ceo" : "coo";
    if (!rows.length) {
      container.appendChild(el("li", { text: "Clear", className: "ccr-empty-line" }));
      return;
    }
    rows.slice(0, 5).forEach(function (item) {
      var li = el("li", { className: "ccr-mini-item" });
      li.appendChild(el("span", { text: safeText(item.reason, "Attention item") }));
      var card = findCardForAttention(item);
      var work = card ? card.work_ref : item.workstream;
      li.appendChild(el("span", { text: safeText(work, "unjoined"), className: "ccr-mini-work" }));
      li.tabIndex = 0;
      li.role = "button";
      li.addEventListener("click", function () { openAttentionDetail(item, target); });
      li.addEventListener("keydown", function (event) { if (event.key === "Enter") openAttentionDetail(item, target); });
      container.appendChild(li);
    });
    if (rows.length > 5) container.appendChild(el("li", { text: "+" + (rows.length - 5) + " more", className: "ccr-empty-line" }));
  }

  // bindings --------------------------------------------------------------
  function bindingConfidence(binding) {
    if (!binding) return { state: "UNBOUND", variant: "is-dim", openable: false, note: "No bound destination." };
    var expected = PROVIDER_LOCATOR_KIND[binding.provider];
    if (!expected || binding.locator_kind !== expected) {
      return { state: "UNSUPPORTED", variant: "is-dim", openable: false, note: "Locator is not supported by this Control Room." };
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
      } else {
        if (statusNode) {
          statusNode.textContent = "Did not open · " + safeText(outcome && outcome.failure_kind, "unknown reason");
          statusNode.className = "ccr-binding-meta ccr-problem";
        }
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

    row.addEventListener("click", function () { openDetail(card); });
    row.addEventListener("keydown", function (event) { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openDetail(card); } });
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
      rows.sort(function (a, b) { return (focusSet[a.work_ref] || 0) - (focusSet[b.work_ref] || 0); });
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
        var link = el("a", { text: "Open PR", className: "ccr-open-button", attrs: { href: pr.url || "#", target: "_blank", rel: "noopener" } });
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
        copy.appendChild(el("div", { text: ROLE_NAME[entry.target] + " · " + safeText(entry.item.reason, "Attention item"), className: "ccr-binding-title" }));
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

  function openDetail(card) {
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
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    document.getElementById("ccr-drawer-scrim").hidden = true;
    STATE.selectedWork = null;
  }

  // loose ends ------------------------------------------------------------
  function renderLooseRows(selector, rows, rowBuilder, emptyLine) {
    var list = document.querySelector(selector + " ul");
    clear(list);
    (rows || []).forEach(function (row) { list.appendChild(rowBuilder(row)); });
    if (!rows || !rows.length) list.appendChild(el("li", { text: emptyLine, className: "ccr-empty-line" }));
    return (rows || []).length;
  }

  function renderLooseEnds(doc) {
    var unjoined = renderLooseRows("#unjoined-prs", doc.unjoined_open_prs, function (pr) {
      var li = el("li", { className: "ccr-row" });
      li.appendChild(el("span", { text: safeText(pr.repo) + " #" + safeText(pr.number) + " · " + safeText(pr.title, "Untitled PR"), className: "ccr-row-title" }));
      li.appendChild(el("a", { text: "Open PR", className: "ccr-open-button", attrs: { href: pr.url || "#", target: "_blank", rel: "noopener" } }));
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
      li.appendChild(el("span", { text: safeText(row.work_ref) + " · " + safeText(row.role) + " · " + (row.binding_ids || []).length + " claims", className: "ccr-row-title ccr-row-id" }));
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
        action: function () { closePalette(); openDetail(card); },
      });
      (((card.github || {}).prs) || []).forEach(function (pr) {
        items.push({
          kind: "PR",
          title: safeText(pr.title, "Untitled PR"),
          sub: safeText(pr.repo) + " #" + safeText(pr.number) + " · " + safeText(card.work_ref),
          search: [pr.title, pr.repo, pr.number, card.work_ref].map(normalizedSearchText).join(" "),
          actionLabel: "Open",
          action: function () { closePalette(); if (pr.url) window.open(pr.url, "_blank", "noopener"); },
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
          closePalette();
          if (confidence.openable) {
            openBinding(binding, null, null).then(function () { loadState(); });
          } else if (relatedCard) {
            openDetail(relatedCard);
          } else {
            document.getElementById("system").scrollIntoView({ behavior: "smooth", block: "start" });
            setActiveNav("system");
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

  function openPalette() {
    var wrap = document.getElementById("ccr-palette");
    wrap.hidden = false;
    STATE.paletteIndex = 0;
    var input = document.getElementById("ccr-palette-input");
    input.value = "";
    renderPaletteResults();
    input.focus();
  }

  function closePalette() { document.getElementById("ccr-palette").hidden = true; }

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

    var sources = {};
    Object.keys(doc.sources || {}).forEach(function (key) { sources[key] = doc.sources[key]; });
    sources.composed_at = body && body.composed_at;
    renderSourcePulse(body, sources);
    renderSystemSources(sources);

    var degraded = (doc.degraded || []).slice();
    if (body && body.state_refresh_error) degraded.push(body.state_refresh_error);
    renderDegraded(degraded);

    var attention = doc.attention || {};
    var chairman = attention.chairman || [];
    var ceo = attention.ceo || [];
    var coo = attention.coo || [];
    renderNeedsYou(chairman);
    renderMiniAttention("sol-attention", ceo);
    renderMiniAttention("coo", coo);
    setTally("chairman", chairman.length);
    setTally("ceo", ceo.length);
    setTally("coo", coo.length);
    document.getElementById("nav-today-count").textContent = String(chairman.length);

    renderWork();
    renderSurfaces();
    var loose = renderLooseEnds(doc);
    renderCapabilities(STATE.capabilities);
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
      renderDegraded(["control_room_api: unavailable — this page could not reach the local state endpoint"]);
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
    if (btn) btn.textContent = mode === "system" ? "Theme · System" : "Theme · " + mode.charAt(0).toUpperCase() + mode.slice(1);
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

    document.getElementById("ccr-theme").addEventListener("click", cycleTheme);
    document.getElementById("ccr-command").addEventListener("click", openPalette);
    document.getElementById("ccr-palette-backdrop").addEventListener("click", closePalette);
    document.getElementById("ccr-palette-input").addEventListener("input", function () { STATE.paletteIndex = 0; renderPaletteResults(); });
    document.getElementById("ccr-palette-input").addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") { event.preventDefault(); if (STATE.paletteResults.length) STATE.paletteIndex = (STATE.paletteIndex + 1) % STATE.paletteResults.length; renderPaletteResults(); }
      else if (event.key === "ArrowUp") { event.preventDefault(); if (STATE.paletteResults.length) STATE.paletteIndex = (STATE.paletteIndex - 1 + STATE.paletteResults.length) % STATE.paletteResults.length; renderPaletteResults(); }
      else if (event.key === "Enter") { event.preventDefault(); if (STATE.paletteResults[STATE.paletteIndex]) STATE.paletteResults[STATE.paletteIndex].action(); }
      else if (event.key === "Escape") { closePalette(); }
    });

    document.addEventListener("keydown", function (event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openPalette(); }
      if (event.key === "Escape") { if (!document.getElementById("ccr-palette").hidden) closePalette(); else closeDetail(); }
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
      workModeButtons[i].addEventListener("click", function () { STATE.workMode = this.getAttribute("data-work-mode") || "focus"; renderWork(); });
    }

    var navLinks = document.querySelectorAll("[data-nav]");
    for (var n = 0; n < navLinks.length; n++) navLinks[n].addEventListener("click", function () { setActiveNav(this.getAttribute("data-nav")); });

    var dock = document.getElementById("ccr-surface-dock");
    var layout = document.querySelector(".ccr-layout");
    var collapsed = false;
    function applyDockState() {
      // Below the dock breakpoint the dock is replaced by the responsive
      // Surfaces section. A remembered desktop collapse preference must not
      // reserve a phantom 42px grid column when the dock itself is hidden.
      var desktopDockVisible = !(window.matchMedia && window.matchMedia("(max-width: 1050px)").matches);
      var activeCollapsed = collapsed && desktopDockVisible;
      dock.classList.toggle("is-collapsed", activeCollapsed);
      if (layout) layout.classList.toggle("ccr-dock-collapsed", activeCollapsed);
      var toggle = document.getElementById("ccr-dock-collapse");
      toggle.textContent = collapsed ? "›" : "‹";
      toggle.setAttribute("aria-label", collapsed ? "Expand surfaces" : "Collapse surfaces");
    }
    try { collapsed = window.localStorage.getItem(DOCK_KEY) === "1"; } catch (_e) { collapsed = false; }
    applyDockState();
    window.addEventListener("resize", applyDockState);
    document.getElementById("ccr-dock-collapse").addEventListener("click", function () {
      collapsed = !collapsed;
      applyDockState();
      try { window.localStorage.setItem(DOCK_KEY, collapsed ? "1" : "0"); } catch (_e) { /* no-op */ }
    });

    document.getElementById("discover-run").addEventListener("click", function () { getJSON("/api/discover").then(renderDiscoverResults); });
    document.getElementById("refresh-builds").addEventListener("click", function () {
      var btn = this;
      var result = document.getElementById("refresh-builds-result");
      btn.disabled = true;
      result.textContent = "Reading GitHub…";
      postJSON("/api/refresh-builds", {}).then(function (outcome) {
        if (outcome && outcome.ok) {
          result.textContent = "Refreshed · " + safeText(outcome.collected_at);
          return loadState();
        }
        result.textContent = "Did not refresh · " + safeText(outcome && outcome.detail, "no detail");
        result.className = "ccr-problem";
        return null;
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
          ((outcome && outcome.problems) || ["The server refused the binding."]).forEach(function (problem) { result.appendChild(el("div", { text: problem, className: "ccr-problem" })); });
        }
      });
    });
  });
})();
