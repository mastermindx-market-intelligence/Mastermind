"use strict";

/**
 * Chairman Control Room — client.
 *
 * Security posture (unchanged from P0, and load-bearing):
 *   * No external resources. The page is served under
 *     `default-src 'self'; script-src 'self'; style-src 'self'`.
 *   * Every element carrying a source-owned string is populated via
 *     textContent and built with createElement — this file never assigns
 *     innerHTML, never builds markup from a template string, and never puts
 *     source-owned text into an attribute that is parsed as code. No source
 *     value can inject markup into this page.
 *   * Every request this file makes — every POST, and every GET against
 *     /api/state or /api/discover (H0 hardening, 2026-08-22: those two read
 *     endpoints expose full org state and are token-gated like a POST) —
 *     attaches the X-CCR-Token minted server-side and injected once into
 *     <meta name="ccr-token">. No other credential or secret ever appears
 *     in this file or in any DOM node it creates.
 *
 * Presentation law (see control_room.css for the full statement):
 *   * The three sources are never blended. Every work card renders all three
 *     provenance rails — Agent OS, Executive, GitHub — in fixed order, and a
 *     source with nothing to say says so rather than vanishing.
 *   * disagreements[] is printed verbatim, per card, never summarised.
 *   * There is no aggregate status anywhere: no score, no percentage, no
 *     combined health state. The sources disagree by design.
 *   * A field that is null renders as an explicit "unknown", never as a blank.
 */

(function () {
  var TOKEN = (function () {
    var meta = document.querySelector('meta[name="ccr-token"]');
    return meta ? meta.getAttribute("content") : "";
  })();

  /** Mirrors control_plane.surface_bindings._PROVIDER_LOCATOR_KIND. A pair
   *  outside this map is exactly what integrations.chairman_surfaces.contract
   *  .open_binding refuses before it ever reaches an adapter, so the page can
   *  honestly show UNSUPPORTED without asking the server first. */
  var PROVIDER_LOCATOR_KIND = {
    chatgpt: "chatgpt_managed_env",
    claude_code: "claude_code_session",
    claude_desktop: "claude_desktop_url",
    cursor_agent: "cursor_agent_thread",
    codex: "codex_session",
  };

  /** A verified-open older than this reads as STALE rather than openable. */
  var STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;

  /** Seat names as the Chairman refers to them, not as the store keys them. */
  var ROLE_NAME = { chairman: "Your seat", ceo: "Sol", coo: "Fable", worker: "Worker" };
  var OPEN_LABEL = { chairman: "Open your seat", ceo: "Open Sol", coo: "Open Fable", worker: "Open worker" };

  // -- tiny DOM helpers ----------------------------------------------------

  function el(tag, opts) {
    var node = document.createElement(tag);
    opts = opts || {};
    if (opts.text !== undefined) node.textContent = opts.text;
    if (opts.className) node.className = opts.className;
    if (opts.attrs) {
      for (var key in opts.attrs) {
        if (Object.prototype.hasOwnProperty.call(opts.attrs, key)) {
          node.setAttribute(key, opts.attrs[key]);
        }
      }
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function append(parent, child) {
    parent.appendChild(child);
    return child;
  }

  // -- honest value formatting ---------------------------------------------

  function isBlank(value) {
    return value === null || value === undefined || value === "";
  }

  /** A value, or an explicitly-marked unknown — never an empty slot. */
  function valueNode(value, unknownWord) {
    if (isBlank(value)) return el("span", { text: unknownWord || "unknown", className: "ccr-unknown" });
    return el("span", { text: String(value) });
  }

  function shortSha(value) {
    if (typeof value !== "string" || value.length < 7) return value;
    return value.slice(0, 7);
  }

  function parseStamp(value) {
    if (typeof value !== "string" || !value) return null;
    var ms = Date.parse(value);
    return isNaN(ms) ? null : ms;
  }

  /** Relative age of an ISO stamp, or null when it cannot be parsed. */
  function ageWords(value) {
    var ms = parseStamp(value);
    if (ms === null) return null;
    var delta = Date.now() - ms;
    if (delta < 0) return "ahead of this clock";
    var mins = Math.floor(delta / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + "m ago";
    var hours = Math.floor(mins / 60);
    if (hours < 48) return hours + "h ago";
    return Math.floor(hours / 24) + "d ago";
  }

  function metaPair(label, value) {
    var span = el("span");
    span.appendChild(el("span", { text: label + " ", className: "ccr-meta-k" }));
    span.appendChild(valueNode(value));
    return span;
  }

  function chip(text, variant) {
    return el("span", { text: text, className: "ccr-chip " + variant });
  }

  // -- transport -----------------------------------------------------------

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
      headers: {
        "Content-Type": "application/json",
        "X-CCR-Token": TOKEN,
      },
      body: JSON.stringify(body || {}),
    }).then(function (resp) {
      return resp.json();
    });
  }

  // -- source stamps -------------------------------------------------------

  var SOURCE_STAMPS = [
    { key: "mastermind_sha", label: "Mastermind", sha: true, extra: "mastermind_branch" },
    { key: "macro_sha", label: "Macro", sha: true },
    { key: "composed_at", label: "State composed", age: true },
    { key: "agent_os_state_generated_at", label: "Agent OS state generated", age: true },
    { key: "active_builds_collected_at", label: "Active builds collected", age: true },
    { key: "runtime_db_present", label: "Runtime database", bool: true },
    { key: "bindings_path_present", label: "Bindings file", bool: true },
    { key: "macro_root", label: "Macro root" },
    { key: "executive_inbox_schema", label: "Executive inbox schema" },
    { key: "agent_os_brief_schema", label: "Agent OS brief schema" },
    { key: "agent_os_state_schema", label: "Agent OS state schema" },
    { key: "active_builds_schema", label: "Active builds schema" },
  ];

  function stampValueNode(spec, sources) {
    var raw = sources[spec.key];
    if (spec.bool) {
      if (raw === true) return el("span", { text: "present" });
      if (raw === false) return el("span", { text: "absent" });
      return el("span", { text: "unknown", className: "ccr-unknown" });
    }
    if (isBlank(raw)) return el("span", { text: "unknown", className: "ccr-unknown" });

    var wrap = el("span");
    wrap.appendChild(el("span", { text: spec.sha ? shortSha(String(raw)) : String(raw) }));
    if (spec.extra && !isBlank(sources[spec.extra])) {
      wrap.appendChild(el("span", { text: " · " + String(sources[spec.extra]) }));
    }
    if (spec.age) {
      var words = ageWords(raw);
      if (words) wrap.appendChild(el("span", { text: words, className: "ccr-age" }));
    }
    return wrap;
  }

  function renderStampList(dl, sources, specs) {
    clear(dl);
    specs.forEach(function (spec) {
      // dt/dd are wrapped as a pair: a bare dt+dd sequence in a multi-column
      // grid lets a value land under a different label.
      var pair = el("div");
      pair.appendChild(el("dt", { text: spec.label }));
      var dd = el("dd");
      dd.appendChild(stampValueNode(spec, sources));
      pair.appendChild(dd);
      dl.appendChild(pair);
    });
  }

  function renderSources(sources) {
    renderStampList(document.getElementById("ccr-sources"), sources, SOURCE_STAMPS);
    // The same three stamps repeated where the data they qualify actually is.
    renderStampList(document.getElementById("ccr-work-stamps"), sources, [
      { key: "agent_os_state_generated_at", label: "Agent OS state generated", age: true },
      { key: "active_builds_collected_at", label: "Active builds collected", age: true },
      { key: "macro_sha", label: "Macro", sha: true },
    ]);
  }

  // -- degraded ------------------------------------------------------------

  function renderDegraded(items) {
    var section = document.getElementById("degraded");
    var listNode = section.querySelector("ul");
    clear(listNode);
    var rows = items || [];
    rows.forEach(function (entry) {
      listNode.appendChild(el("li", { text: String(entry) }));
    });
    // Hidden only when genuinely empty. Never hidden while a source is
    // degraded, and never replaced by a reassuring summary when it is not.
    section.className = rows.length ? "ccr-alarm" : "ccr-alarm is-empty";
  }

  // -- attention -----------------------------------------------------------

  function renderEvidence(item) {
    var rows = item.evidence || [];
    if (!rows.length) return null;
    var fold = el("details", { className: "ccr-fold ccr-evidence" });
    var summary = el("summary");
    summary.appendChild(el("span", { text: "Evidence", className: "ccr-fold-name" }));
    summary.appendChild(el("span", { text: String(rows.length), className: "ccr-tally" }));
    fold.appendChild(summary);
    var list = el("ul");
    rows.forEach(function (entry) {
      if (entry === null || typeof entry !== "object") {
        list.appendChild(el("li", { text: String(entry) }));
        return;
      }
      Object.keys(entry).forEach(function (key) {
        list.appendChild(el("li", { text: key + ": " + String(entry[key]) }));
      });
    });
    fold.appendChild(list);
    return fold;
  }

  function renderAttentionItem(item) {
    var li = el("li", { className: "ccr-item" });

    var reason = isBlank(item.reason) ? null : String(item.reason);
    li.appendChild(el("p", {
      text: reason || "This item carries no reason text.",
      className: reason ? "ccr-item-reason" : "ccr-item-reason ccr-unknown",
    }));

    var meta = el("div", { className: "ccr-item-meta" });
    meta.appendChild(metaPair("kind", item.kind));
    meta.appendChild(metaPair("work", item.workstream));
    meta.appendChild(metaPair("status", item.status));
    meta.appendChild(metaPair("job", item.job_id));
    meta.appendChild(metaPair("reported by", item.source));
    meta.appendChild(metaPair("id", item.attention_id));
    li.appendChild(meta);

    var next = item.existing_next_actions || [];
    if (next.length) {
      var box = el("div", { className: "ccr-item-next" });
      box.appendChild(el("span", { text: "Next action already on record", className: "ccr-next-label" }));
      next.forEach(function (line) {
        box.appendChild(el("div", { text: String(line) }));
      });
      li.appendChild(box);
    }

    var evidence = renderEvidence(item);
    if (evidence) li.appendChild(evidence);

    return li;
  }

  function renderAttentionList(listNode, items, emptyLine) {
    clear(listNode);
    var rows = items || [];
    rows.forEach(function (item) {
      listNode.appendChild(renderAttentionItem(item));
    });
    if (!rows.length) {
      listNode.appendChild(el("li", { text: emptyLine, className: "ccr-empty" }));
    }
    return rows.length;
  }

  // -- bindings ------------------------------------------------------------

  /** One of UNBOUND / UNSUPPORTED / BOUND_UNVERIFIED / STALE / VERIFIED_OPENABLE.
   *  Every branch is derivable from the binding summary the server already
   *  sent; nothing here asks the server to guess on the page's behalf. */
  function bindingConfidence(binding) {
    if (!binding) return { state: "UNBOUND", variant: "ccr-chip-unbound", note: "No surface is bound to this work.", openable: false };

    var expected = PROVIDER_LOCATOR_KIND[binding.provider];
    if (!expected || binding.locator_kind !== expected) {
      return {
        state: "UNSUPPORTED",
        variant: "ccr-chip-unsupported",
        note: "carries locator " + String(binding.locator_kind) + ", which this machine cannot open for it.",
        openable: false,
      };
    }

    if (isBlank(binding.last_verified_at)) {
      return {
        state: "BOUND_UNVERIFIED",
        variant: "ccr-chip-unverified",
        note: "Bound, never opened from here. Recorded " + (ageWords(binding.observed_at) || "at an unknown time") + ".",
        openable: true,
      };
    }

    var ms = parseStamp(binding.last_verified_at);
    if (ms === null) {
      return {
        state: "VERIFIED_OPENABLE",
        variant: "ccr-chip-verified",
        note: "Opened before, at an unreadable timestamp: " + String(binding.last_verified_at) + ".",
        openable: true,
      };
    }
    if (Date.now() - ms > STALE_AFTER_MS) {
      return {
        state: "STALE",
        variant: "ccr-chip-stale",
        note: "Last opened " + ageWords(binding.last_verified_at) + ". It may no longer be there.",
        openable: true,
      };
    }
    return {
      state: "VERIFIED_OPENABLE",
      variant: "ccr-chip-verified",
      note: "Last opened " + ageWords(binding.last_verified_at) + ".",
      openable: true,
    };
  }

  function renderBindingRow(binding) {
    var confidence = bindingConfidence(binding);
    var row = el("div", { className: "ccr-binding-row" });

    row.appendChild(el("span", {
      text: ROLE_NAME[binding.role] || String(binding.role),
      className: "ccr-binding-who",
    }));
    row.appendChild(chip(confidence.state, confidence.variant));
    row.appendChild(el("span", { className: "ccr-binding-spacer" }));

    var openBtn = el("button", {
      text: OPEN_LABEL[binding.role] || "Open surface",
      className: "ccr-open",
    });
    openBtn.type = "button";
    openBtn.disabled = !confidence.openable;

    var note = el("div", {
      text: String(binding.provider) + " · " + confidence.note,
      className: "ccr-binding-note",
    });

    if (confidence.openable) {
      openBtn.addEventListener("click", function () {
        openBtn.disabled = true;
        note.className = "ccr-binding-note";
        note.textContent = "Opening …";
        postJSON("/api/open", { binding_id: binding.binding_id })
          .then(function (outcome) {
            if (outcome && outcome.ok) {
              note.className = "ccr-binding-note";
              note.textContent = "Opened · " + String(outcome.action || "") +
                (outcome.detail ? " · " + String(outcome.detail) : "");
            } else {
              note.className = "ccr-binding-note is-bad";
              note.textContent = "Did not open · " + String((outcome && outcome.failure_kind) || "unknown reason") +
                ((outcome && outcome.detail) ? " · " + String(outcome.detail) : "");
            }
          })
          .catch(function () {
            note.className = "ccr-binding-note is-bad";
            note.textContent = "Did not open · this page could not reach the local server.";
          })
          .finally(function () {
            openBtn.disabled = false;
          });
      });
    }
    row.appendChild(openBtn);

    var unbindBtn = el("button", { text: "Unbind", className: "ccr-unbind" });
    unbindBtn.type = "button";
    unbindBtn.addEventListener("click", function () {
      unbindBtn.disabled = true;
      postJSON("/api/unbind", { binding_id: binding.binding_id }).then(function () {
        loadState();
      });
    });

    var foot = el("div", { className: "ccr-binding-foot" });
    foot.appendChild(note);
    foot.appendChild(unbindBtn);
    row.appendChild(foot);
    return row;
  }

  function renderBindings(card) {
    var wrap = el("div", { className: "ccr-bindings" });
    wrap.appendChild(el("p", { text: "Surfaces", className: "ccr-bindings-label" }));

    var bindings = card.bindings || [];
    if (!bindings.length) {
      var confidence = bindingConfidence(null);
      var row = el("div", { className: "ccr-binding-row" });
      row.appendChild(el("span", { text: "Worker", className: "ccr-binding-who" }));
      row.appendChild(chip(confidence.state, confidence.variant));
      row.appendChild(el("span", { className: "ccr-binding-spacer" }));
      var dead = el("button", { text: "Open worker", className: "ccr-open" });
      dead.type = "button";
      dead.disabled = true;
      row.appendChild(dead);
      var deadFoot = el("div", { className: "ccr-binding-foot" });
      deadFoot.appendChild(el("div", {
        text: confidence.note + " Bind one below to open it from here.",
        className: "ccr-binding-note",
      }));
      row.appendChild(deadFoot);
      wrap.appendChild(row);
      return wrap;
    }

    bindings.forEach(function (binding) {
      wrap.appendChild(renderBindingRow(binding));
    });
    return wrap;
  }

  // -- work cards ----------------------------------------------------------

  function provRow(grid, name, silent, build) {
    var nameNode = el("p", { text: name, className: "ccr-prov-name" });
    var valNode = el("div", { className: "ccr-prov-val" });
    if (silent) {
      nameNode.className = "ccr-prov-name is-dim";
      valNode.className = "ccr-prov-val is-dim";
    }
    build(valNode);
    // display:contents on a wrapper would break the grid rails, so the two
    // cells are placed directly and the silent styling is carried per cell.
    grid.appendChild(nameNode);
    grid.appendChild(valNode);
  }

  function line(parent, text, className) {
    parent.appendChild(el("span", { text: text, className: className || "ccr-prov-line" }));
  }

  function renderAgentOsRail(grid, card) {
    var ao = card.agent_os;
    var known = ao && (!isBlank(ao.status) || !isBlank(ao.state) || !isBlank(ao.next_action) ||
      !isBlank(ao.program) || !isBlank(ao.reason));
    provRow(grid, "Agent OS", !known, function (val) {
      if (!known) {
        line(val, "silent — no Agent OS record for this reference");
        return;
      }
      var head = el("span", { className: "ccr-prov-line" });
      head.appendChild(el("span", { text: "status " }));
      head.appendChild(valueNode(ao.status));
      head.appendChild(el("span", { text: " · readiness " }));
      head.appendChild(valueNode(ao.state));
      val.appendChild(head);

      if (!isBlank(ao.program)) line(val, "program " + String(ao.program), "ccr-prov-line ccr-prov-sub");
      if (!isBlank(ao.reason)) line(val, String(ao.reason), "ccr-prov-line");
      if (!isBlank(ao.next_action)) line(val, "next — " + String(ao.next_action), "ccr-prov-line");
      var unmet = (ao.unmet_dependencies || []);
      if (unmet.length) {
        line(val, "waiting on " + unmet.join(", "), "ccr-prov-line ccr-prov-sub");
      }
    });
  }

  function renderExecutiveRail(grid, card) {
    var jobs = (card.executive && card.executive.jobs) || [];
    provRow(grid, "Executive", !jobs.length, function (val) {
      if (!jobs.length) {
        line(val, "silent — no Executive job cites this reference");
        return;
      }
      jobs.forEach(function (job) {
        var row = el("span", { className: "ccr-prov-line" });
        row.appendChild(el("span", { text: String(job.job_id) + " ", className: "ccr-mono" }));
        row.appendChild(valueNode(job.status, "status unknown"));
        val.appendChild(row);
      });
      var joinedBy = card.executive && card.executive.joined_by;
      if (!isBlank(joinedBy)) {
        line(val, "joined by " + String(joinedBy), "ccr-prov-line ccr-prov-sub");
      }
    });
  }

  function prLink(pr, label) {
    var link = el("a", { text: label, className: "ccr-open" });
    link.href = pr.url || "#";
    link.target = "_blank";
    link.rel = "noopener";
    return link;
  }

  function renderGithubRail(grid, card) {
    var prs = (card.github && card.github.prs) || [];
    provRow(grid, "GitHub", !prs.length, function (val) {
      if (!prs.length) {
        line(val, "silent — no open PR cites this reference");
        return;
      }
      prs.forEach(function (pr) {
        var row = el("div", { className: "ccr-prov-line ccr-prov-pr" });
        var left = el("span");
        left.appendChild(el("span", {
          text: String(pr.repo || "unknown repo") + " #" + String(pr.number || "?") + " ",
          className: "ccr-mono",
        }));
        left.appendChild(el("span", { text: String(pr.title || "no title") }));
        row.appendChild(left);

        var facts = el("span", { className: "ccr-prov-sub" });
        facts.textContent = (pr.draft === true ? "draft · " : pr.draft === false ? "ready · " : "") +
          "merge state " + (isBlank(pr.merge_state) ? "unknown" : String(pr.merge_state));
        row.appendChild(facts);
        row.appendChild(prLink(pr, "Open PR"));
        val.appendChild(row);
      });
    });
  }

  function renderWorkCard(card) {
    var attentionCount = (card.attention_ids || []).length;
    var disagreements = card.disagreements || [];

    var classes = ["ccr-work-card"];
    if (attentionCount) classes.push("ccr-card-wanted");
    if (disagreements.length) classes.push("ccr-card-disputed");
    var wrap = el("article", { className: classes.join(" ") });

    var head = el("div", { className: "ccr-card-head" });
    head.appendChild(el("h3", { text: String(card.work_ref) }));

    var title = card.agent_os && card.agent_os.title;
    head.appendChild(el("p", {
      text: isBlank(title) ? "no title from any source" : String(title),
      className: isBlank(title) ? "ccr-card-title ccr-untitled" : "ccr-card-title",
    }));

    if (attentionCount || disagreements.length) {
      var flags = el("div", { className: "ccr-card-flags" });
      if (attentionCount) {
        flags.appendChild(chip(
          attentionCount === 1 ? "1 attention item" : attentionCount + " attention items",
          "ccr-chip-flag"
        ));
      }
      if (disagreements.length) {
        flags.appendChild(chip("sources disagree", "ccr-chip-flag"));
      }
      head.appendChild(flags);
    }
    wrap.appendChild(head);

    var grid = el("div", { className: "ccr-prov" });
    renderAgentOsRail(grid, card);
    renderExecutiveRail(grid, card);
    renderGithubRail(grid, card);
    wrap.appendChild(grid);

    if (disagreements.length) {
      var box = el("ul", { className: "ccr-disagreements" });
      box.appendChild(el("li", { text: "Reported as written, unresolved", className: "ccr-disagree-label" }));
      disagreements.forEach(function (entry) {
        box.appendChild(el("li", { text: String(entry) }));
      });
      wrap.appendChild(box);
    }

    wrap.appendChild(renderBindings(card));
    return wrap;
  }

  /** Cards the Chairman is being asked about come first; the rest stay in the
   *  server's own reference order. The rule is printed in the section hint so
   *  the ordering is never a silent editorial act. */
  function workOrder(cards) {
    return cards.map(function (card, index) {
      return { card: card, index: index };
    }).sort(function (a, b) {
      var aw = (a.card.attention_ids || []).length ? 1 : 0;
      var bw = (b.card.attention_ids || []).length ? 1 : 0;
      if (aw !== bw) return bw - aw;
      var ad = (a.card.disagreements || []).length ? 1 : 0;
      var bd = (b.card.disagreements || []).length ? 1 : 0;
      if (ad !== bd) return bd - ad;
      return a.index - b.index;
    }).map(function (entry) {
      return entry.card;
    });
  }

  function renderWork(cards) {
    var container = document.querySelector("#work .ccr-work-cards");
    clear(container);
    var rows = cards || [];
    workOrder(rows).forEach(function (card) {
      container.appendChild(renderWorkCard(card));
    });
    if (!rows.length) {
      container.appendChild(el("p", {
        text: "No work card exists. No source named a work reference in this collection.",
        className: "ccr-empty",
      }));
    }
    return rows.length;
  }

  // -- loose ends ----------------------------------------------------------

  function renderUnjoinedPRs(prs) {
    var listNode = document.querySelector("#unjoined-prs ul");
    clear(listNode);
    var rows = prs || [];
    rows.forEach(function (pr) {
      var li = el("li", { className: "ccr-row" });
      var left = el("span", { className: "ccr-row-title" });
      left.appendChild(el("span", {
        text: String(pr.repo || "unknown repo") + " #" + String(pr.number || "?") + " ",
        className: "ccr-row-id",
      }));
      left.appendChild(el("span", { text: String(pr.title || "no title") }));
      li.appendChild(left);
      li.appendChild(prLink(pr, "Open PR"));
      listNode.appendChild(li);
    });
    if (!rows.length) {
      listNode.appendChild(el("li", { text: "Every open PR is claimed by a card above.", className: "ccr-empty" }));
    }
    return rows.length;
  }

  function renderUnboundSurfaces(rows) {
    var listNode = document.querySelector("#unbound-surfaces ul");
    clear(listNode);
    var items = rows || [];
    items.forEach(function (row) {
      var li = el("li", { className: "ccr-row" });
      var left = el("span", { className: "ccr-row-title" });
      left.appendChild(el("span", { text: String(row.work_ref || "no work reference") + " ", className: "ccr-row-id" }));
      left.appendChild(el("span", { text: (ROLE_NAME[row.role] || String(row.role)) + " · " + String(row.provider) }));
      li.appendChild(left);
      li.appendChild(chip("UNBOUND", "ccr-chip-unbound"));
      listNode.appendChild(li);
    });
    if (!items.length) {
      listNode.appendChild(el("li", { text: "Every bound surface points at work shown above.", className: "ccr-empty" }));
    }
    return items.length;
  }

  function renderBindingConflicts(rows) {
    var listNode = document.querySelector("#binding-conflicts ul");
    clear(listNode);
    var items = rows || [];
    items.forEach(function (row) {
      var li = el("li", { className: "ccr-row" });
      var left = el("span", { className: "ccr-row-title" });
      left.appendChild(el("span", { text: String(row.work_ref) + " · " + (ROLE_NAME[row.role] || String(row.role)), className: "ccr-row-id" }));
      // one claimant per line: run together, ids break mid-token and read wrong
      (row.binding_ids || []).forEach(function (id) {
        left.appendChild(el("span", { text: String(id), className: "ccr-row-id ccr-row-claim" }));
      });
      li.appendChild(left);
      li.appendChild(chip(String((row.binding_ids || []).length) + " CLAIMS", "ccr-chip-unsupported"));
      listNode.appendChild(li);
    });
    if (!items.length) {
      listNode.appendChild(el("li", { text: "No work and role is claimed twice.", className: "ccr-empty" }));
    }
    return items.length;
  }

  // -- the ladder ----------------------------------------------------------

  function setTally(name, count) {
    var nodes = document.querySelectorAll('[data-tally="' + name + '"]');
    for (var i = 0; i < nodes.length; i++) nodes[i].textContent = String(count);
  }

  function renderLadder(counts) {
    var order = ["chairman", "ceo", "coo", "work", "loose"];
    var leadFound = false;
    order.forEach(function (name) {
      var node = document.querySelector('[data-rung="' + name + '"]');
      if (!node) return;
      node.textContent = String(counts[name]);
      var li = node.closest ? node.closest("li") : null;
      if (!li) return;
      var classes = [];
      if (!counts[name]) classes.push("is-zero");
      // Brass marks the topmost SEAT that owes a move — work and loose ends
      // are not people, so they never take it.
      if (!leadFound && counts[name] > 0 && (name === "chairman" || name === "ceo" || name === "coo")) {
        classes.push("is-lead");
        leadFound = true;
      }
      li.className = classes.join(" ");
    });
  }

  // -- state ---------------------------------------------------------------

  /** Freshness + degraded surfacing for the H0 hardening envelope fields
   *  (composed_at / refresh_in_flight / state_refresh_error — cached,
   *  single-flight background composition, 2026-08-22). None of this is
   *  part of the pure control_room document itself; it describes the
   *  cache serving it. */
  function renderStateFreshness(body) {
    var docSources = (body && body.control_room && body.control_room.sources) || {};
    var sources = {};
    for (var key in docSources) {
      sources[key] = docSources[key];
    }
    sources.composed_at = body && body.composed_at;

    var refreshingEl = document.getElementById("ccr-refreshing");
    if (refreshingEl) refreshingEl.hidden = !(body && body.refresh_in_flight);

    return sources;
  }

  function loadState() {
    return getJSON("/api/state").then(function (body) {
      var doc = (body && body.control_room) || {};
      renderSources(renderStateFreshness(body));

      // state_refresh_error describes the CACHE (a background recompose
      // that failed, last good doc still served), never the document
      // itself — folded into the same degraded list/rendering so it reads
      // with the same honesty law (never hidden, never summarised away)
      // without inventing a second alarm surface.
      var degradedRows = (doc.degraded || []).slice();
      if (body && body.state_refresh_error) degradedRows.push(body.state_refresh_error);
      renderDegraded(degradedRows);

      var attention = doc.attention || {};
      var chairmanCount = renderAttentionList(
        document.querySelector("#needs-you .ccr-attention-list"),
        attention.chairman,
        "Nothing is waiting on you."
      );
      var ceoCount = renderAttentionList(
        document.querySelector("#sol-attention .ccr-attention-list"),
        attention.ceo,
        "Nothing is waiting on Sol."
      );
      var cooCount = renderAttentionList(
        document.querySelector("#coo .ccr-attention-list"),
        attention.coo,
        "Nothing is waiting on ops."
      );

      var needsYou = document.getElementById("needs-you");
      needsYou.className = chairmanCount ? "ccr-tier ccr-tier-you ccr-has-items" : "ccr-tier ccr-tier-you";
      var solSection = document.getElementById("sol-attention");
      solSection.className = ceoCount ? "ccr-tier ccr-tier-sol ccr-has-items" : "ccr-tier ccr-tier-sol";

      var workCount = renderWork(doc.work);
      var unjoined = renderUnjoinedPRs(doc.unjoined_open_prs);
      var unbound = renderUnboundSurfaces(doc.unbound_surfaces);
      var conflicts = renderBindingConflicts(doc.binding_conflicts);

      setTally("chairman", chairmanCount);
      setTally("ceo", ceoCount);
      setTally("coo", cooCount);
      setTally("work", workCount);
      setTally("unjoined", unjoined);
      setTally("loose", unjoined + unbound + conflicts);

      renderLadder({
        chairman: chairmanCount,
        ceo: ceoCount,
        coo: cooCount,
        work: workCount,
        loose: unjoined + unbound + conflicts,
      });
    });
  }

  // -- discover ------------------------------------------------------------

  function discoverGroup(container, heading, rows, toText, emptyLine) {
    container.appendChild(el("h3", { text: heading }));
    var list = el("ul");
    (rows || []).forEach(function (row) {
      list.appendChild(el("li", { text: toText(row) }));
    });
    if (!rows || !rows.length) {
      list.appendChild(el("li", { text: emptyLine, className: "ccr-empty" }));
    }
    container.appendChild(list);
  }

  /** ChatGPT discovery groups: read-only local environment identities.
   *  Rendered with the existing chip style (ccr-chip-verified for a running
   *  environment, ccr-chip-unbound for a stopped one) rather than plain
   *  text, so "running" reads the same way it does on a bound surface row.
   *  A plain list — like the existing Claude Code / Codex discovery groups,
   *  there is no click-to-prefill wiring in this codebase to mirror.
   *  Discovery confers zero ownership by itself; nothing is bound until the
   *  Bind form below is filled in and submitted by hand. */
  function discoverEnvGroup(container, heading, rows, buildLine, emptyLine) {
    container.appendChild(el("h3", { text: heading }));
    var list = el("ul");
    (rows || []).forEach(function (row) {
      var li = el("li", { className: "ccr-row" });
      var left = el("span", { className: "ccr-row-title ccr-mono" });
      buildLine(left, row);
      li.appendChild(left);
      li.appendChild(chip(row.running ? "running" : "not running", row.running ? "ccr-chip-verified" : "ccr-chip-unbound"));
      list.appendChild(li);
    });
    if (!rows || !rows.length) {
      list.appendChild(el("li", { text: emptyLine, className: "ccr-empty" }));
    }
    container.appendChild(list);
  }

  function renderDiscoverResults(doc) {
    var container = document.getElementById("discover-results");
    clear(container);
    doc = doc || {};
    var envs = doc.chatgpt_environments || {};

    discoverEnvGroup(container, "ChatGPT — Multilogin environments", envs.multilogin, function (left, row) {
      left.appendChild(el("span", { text: "f:" + String(row.folder_id) + " p:" + String(row.profile_id) }));
    }, "No local Multilogin environment was found.");

    discoverEnvGroup(container, "ChatGPT — GoLogin environments", envs.gologin, function (left, row) {
      left.appendChild(el("span", { text: "p:" + String(row.profile_id) }));
    }, "No local GoLogin environment was found.");

    discoverGroup(container, "Claude Code sessions", doc.claude_code_sessions, function (s) {
      return String(s.project_dir) + " / " + String(s.session_id);
    }, "No Claude Code session was found.");

    discoverGroup(container, "Codex sessions", doc.codex_sessions, function (s) {
      return String(s.date) + " / " + String(s.session_id);
    }, "No Codex session was found.");
  }

  // -- theme ---------------------------------------------------------------

  var THEME_KEY = "ccr-theme";
  var THEME_CYCLE = ["system", "light", "dark"];

  function readTheme() {
    try {
      var stored = window.localStorage.getItem(THEME_KEY);
      return THEME_CYCLE.indexOf(stored) === -1 ? "system" : stored;
    } catch (e) {
      return "system";
    }
  }

  function applyTheme(mode) {
    if (mode === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", mode);
    }
    var button = document.getElementById("ccr-theme");
    if (button) button.textContent = "Theme: " + mode.charAt(0).toUpperCase() + mode.slice(1);
  }

  applyTheme(readTheme());

  // -- wiring --------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(readTheme());
    loadState();

    document.getElementById("ccr-theme").addEventListener("click", function () {
      var next = THEME_CYCLE[(THEME_CYCLE.indexOf(readTheme()) + 1) % THEME_CYCLE.length];
      try {
        window.localStorage.setItem(THEME_KEY, next);
      } catch (e) { /* a private-mode failure must not break the toggle */ }
      applyTheme(next);
    });

    document.getElementById("discover-run").addEventListener("click", function () {
      getJSON("/api/discover").then(renderDiscoverResults);
    });

    document.getElementById("refresh-builds").addEventListener("click", function () {
      var button = this;
      var resultNode = document.getElementById("refresh-builds-result");
      button.disabled = true;
      resultNode.textContent = "Asking GitHub …";
      postJSON("/api/refresh-builds", {}).then(function (outcome) {
        clear(resultNode);
        if (outcome && outcome.ok) {
          resultNode.appendChild(el("span", { text: "Refreshed · collected " + String(outcome.collected_at) }));
          loadState();
        } else {
          resultNode.appendChild(el("span", {
            text: "Did not refresh · " + String((outcome && outcome.detail) || "no detail given"),
            className: "ccr-problem",
          }));
        }
      }).finally(function () {
        button.disabled = false;
      });
    });

    // -- chatgpt bind fields: managed-environment identity, never a Chrome
    //    profile (Sol architecture correction, MAS-113, 2026-08-22). ------

    function updateBindFieldVisibility() {
      var provider = document.getElementById("bind-provider").value;
      var isChatgpt = provider === "chatgpt";
      document.getElementById("bind-chatgpt-fields").hidden = !isChatgpt;
      document.getElementById("bind-locator-field").hidden = isChatgpt;
      document.getElementById("bind-locator").required = !isChatgpt;

      var manager = document.getElementById("bind-chatgpt-manager").value;
      var folderField = document.getElementById("bind-chatgpt-folder-field");
      folderField.hidden = !isChatgpt || manager !== "multilogin";
    }

    document.getElementById("bind-provider").addEventListener("change", updateBindFieldVisibility);
    document.getElementById("bind-chatgpt-manager").addEventListener("change", updateBindFieldVisibility);
    updateBindFieldVisibility();

    /** Builds the chatgpt locator from the dedicated fields — never from the
     *  generic JSON textarea, which is hidden for this provider. Returns
     *  ``null`` (never throws) when a required field is blank; the caller
     *  reports that as a problem instead of posting an incomplete locator. */
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

    document.getElementById("bind-form").addEventListener("submit", function (event) {
      event.preventDefault();
      var resultNode = document.getElementById("bind-result");
      var provider = document.getElementById("bind-provider").value;
      var locator;
      if (provider === "chatgpt") {
        locator = buildChatgptLocator();
        if (locator === null) {
          clear(resultNode);
          resultNode.appendChild(el("div", {
            text: "Fill in the environment manager, profile ID (and folder ID for multilogin), and conversation URL.",
            className: "ccr-problem",
          }));
          return;
        }
      } else {
        var locatorText = document.getElementById("bind-locator").value;
        try {
          locator = JSON.parse(locatorText || "{}");
        } catch (e) {
          clear(resultNode);
          resultNode.appendChild(el("div", {
            text: "The locator is not valid JSON. Fix it and bind again.",
            className: "ccr-problem",
          }));
          return;
        }
      }
      var body = {
        work_ref: document.getElementById("bind-work-ref").value,
        role: document.getElementById("bind-role").value,
        provider: provider,
        locator: locator,
      };
      var seatRef = document.getElementById("bind-seat-ref").value;
      if (seatRef) body.seat_ref = seatRef;

      postJSON("/api/bind", body).then(function (outcome) {
        clear(resultNode);
        if (outcome && outcome.ok) {
          resultNode.appendChild(el("div", { text: "Bound · " + String(outcome.binding_id) }));
          loadState();
        } else {
          var problems = (outcome && outcome.problems) || ["The server refused the binding and gave no detail."];
          problems.forEach(function (p) {
            resultNode.appendChild(el("div", { text: String(p), className: "ccr-problem" }));
          });
        }
      });
    });
  });
})();
