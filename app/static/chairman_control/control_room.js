"use strict";

/**
 * Chairman Control Room P0 — placeholder client.
 *
 * No external resources; every element that carries a source-owned string is
 * populated via textContent (never innerHTML with unescaped data), so no
 * source value can inject markup into this page. Every POST attaches the
 * X-CCR-Token minted server-side and injected once into this page's
 * <meta name="ccr-token"> tag — no other credential/secret ever appears in
 * this file or in any DOM node it creates.
 */

(function () {
  var TOKEN = (function () {
    var meta = document.querySelector('meta[name="ccr-token"]');
    return meta ? meta.getAttribute("content") : "";
  })();

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

  function getJSON(path) {
    return fetch(path, { method: "GET", credentials: "same-origin" }).then(function (resp) {
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

  // -- rendering ---------------------------------------------------------

  function renderAttentionList(listNode, items) {
    clear(listNode);
    (items || []).forEach(function (item) {
      var li = el("li");
      li.appendChild(el("span", { text: String(item.attention_id || "") + " " }));
      li.appendChild(el("span", { text: String(item.kind || item.workstream || "") }));
      listNode.appendChild(li);
    });
    if (!items || items.length === 0) {
      listNode.appendChild(el("li", { text: "(none)", className: "ccr-empty" }));
    }
  }

  function renderDegraded(items) {
    var listNode = document.querySelector("#degraded ul");
    clear(listNode);
    (items || []).forEach(function (entry) {
      listNode.appendChild(el("li", { text: entry }));
    });
    if (!items || items.length === 0) {
      listNode.appendChild(el("li", { text: "(none)", className: "ccr-empty" }));
    }
  }

  function bindingConfidence(binding) {
    if (binding.last_verified_at) return "VERIFIED_OPENABLE";
    return "BOUND_UNVERIFIED";
  }

  function renderBindingRow(binding) {
    var row = el("div", { className: "ccr-binding-row" });
    row.appendChild(el("span", { text: binding.role + " / " + binding.provider }));
    row.appendChild(el("span", { text: bindingConfidence(binding), className: "ccr-confidence" }));
    var openBtn = el("button", { text: "Open" });
    openBtn.type = "button";
    openBtn.addEventListener("click", function () {
      openBtn.disabled = true;
      postJSON("/api/open", { binding_id: binding.binding_id })
        .then(function (outcome) {
          row.appendChild(el("span", { text: outcome.ok ? "opened" : "failed: " + (outcome.failure_kind || ""), className: "ccr-outcome" }));
        })
        .finally(function () {
          openBtn.disabled = false;
        });
    });
    row.appendChild(openBtn);
    var unbindBtn = el("button", { text: "Unbind" });
    unbindBtn.type = "button";
    unbindBtn.addEventListener("click", function () {
      postJSON("/api/unbind", { binding_id: binding.binding_id }).then(function () {
        loadState();
      });
    });
    row.appendChild(unbindBtn);
    return row;
  }

  function renderWorkCard(card) {
    var wrap = el("article", { className: "ccr-work-card" });
    wrap.appendChild(el("h3", { text: card.work_ref }));

    if (card.agent_os && (card.agent_os.title || card.agent_os.status || card.agent_os.next_action)) {
      var ao = el("div", { className: "ccr-agent-os" });
      if (card.agent_os.title) ao.appendChild(el("div", { text: card.agent_os.title }));
      if (card.agent_os.status) ao.appendChild(el("div", { text: "status: " + card.agent_os.status }));
      if (card.agent_os.next_action) ao.appendChild(el("div", { text: "next: " + card.agent_os.next_action }));
      wrap.appendChild(ao);
    }

    var jobs = (card.executive && card.executive.jobs) || [];
    if (jobs.length) {
      var jobsList = el("ul", { className: "ccr-jobs" });
      jobs.forEach(function (job) {
        jobsList.appendChild(el("li", { text: job.job_id + ": " + job.status }));
      });
      wrap.appendChild(jobsList);
    }

    var prs = (card.github && card.github.prs) || [];
    if (prs.length) {
      var prsList = el("ul", { className: "ccr-prs" });
      prs.forEach(function (pr) {
        var li = el("li");
        var link = el("a", { text: (pr.repo || "") + " #" + (pr.number || "") });
        link.href = pr.url || "#";
        link.target = "_blank";
        link.rel = "noopener";
        li.appendChild(link);
        prsList.appendChild(li);
      });
      wrap.appendChild(prsList);
    }

    wrap.appendChild(el("div", { text: "attention: " + ((card.attention_ids || []).length), className: "ccr-attention-count" }));

    var bindings = card.bindings || [];
    var bindingsWrap = el("div", { className: "ccr-bindings" });
    bindings.forEach(function (binding) {
      bindingsWrap.appendChild(renderBindingRow(binding));
    });
    wrap.appendChild(bindingsWrap);

    var disagreements = card.disagreements || [];
    if (disagreements.length) {
      var dList = el("ul", { className: "ccr-disagreements" });
      disagreements.forEach(function (d) {
        dList.appendChild(el("li", { text: d }));
      });
      wrap.appendChild(dList);
    }

    return wrap;
  }

  function renderWork(cards) {
    var container = document.querySelector("#work .ccr-work-cards");
    clear(container);
    (cards || []).forEach(function (card) {
      container.appendChild(renderWorkCard(card));
    });
    if (!cards || cards.length === 0) {
      container.appendChild(el("p", { text: "(no active work cards)", className: "ccr-empty" }));
    }
  }

  function renderUnjoinedPRs(prs) {
    var listNode = document.querySelector("#unjoined-prs ul");
    clear(listNode);
    (prs || []).forEach(function (pr) {
      var li = el("li");
      var link = el("a", { text: (pr.repo || "") + " #" + (pr.number || "") + " " + (pr.title || "") });
      link.href = pr.url || "#";
      link.target = "_blank";
      link.rel = "noopener";
      li.appendChild(link);
      listNode.appendChild(li);
    });
  }

  function renderUnboundSurfaces(rows) {
    var listNode = document.querySelector("#unbound-surfaces ul");
    clear(listNode);
    (rows || []).forEach(function (row) {
      listNode.appendChild(el("li", { text: row.work_ref + " / " + row.role + " / " + row.provider }));
    });
    if (!rows || rows.length === 0) {
      listNode.appendChild(el("li", { text: "(none)", className: "ccr-empty" }));
    }
  }

  function renderBindingConflicts(rows) {
    var listNode = document.querySelector("#binding-conflicts ul");
    clear(listNode);
    (rows || []).forEach(function (row) {
      listNode.appendChild(el("li", { text: row.work_ref + " / " + row.role + ": " + row.binding_ids.join(", ") }));
    });
    if (!rows || rows.length === 0) {
      listNode.appendChild(el("li", { text: "(none)", className: "ccr-empty" }));
    }
  }

  function renderSources(sources) {
    var dl = document.getElementById("ccr-sources");
    clear(dl);
    var fields = [
      "mastermind_sha", "macro_sha", "active_builds_collected_at",
      "agent_os_state_generated_at", "runtime_db_present", "bindings_path_present",
    ];
    fields.forEach(function (field) {
      dl.appendChild(el("dt", { text: field }));
      dl.appendChild(el("dd", { text: String(sources[field]) }));
    });
  }

  function loadState() {
    return getJSON("/api/state").then(function (body) {
      var doc = body.control_room || {};
      renderSources(doc.sources || {});
      renderDegraded(doc.degraded);
      var attention = doc.attention || {};
      renderAttentionList(document.querySelector("#needs-you .ccr-attention-list"), attention.chairman);
      renderAttentionList(document.querySelector("#sol-attention .ccr-attention-list"), attention.ceo);
      renderAttentionList(document.querySelector("#coo .ccr-attention-list"), attention.coo);
      renderWork(doc.work);
      renderUnjoinedPRs(doc.unjoined_open_prs);
      renderUnboundSurfaces(doc.unbound_surfaces);
      renderBindingConflicts(doc.binding_conflicts);
    });
  }

  // -- discover ------------------------------------------------------------

  function renderDiscoverResults(doc) {
    var container = document.getElementById("discover-results");
    clear(container);

    var tabsList = el("ul", { className: "ccr-discover-tabs" });
    (doc.chatgpt_tabs || []).forEach(function (tab) {
      tabsList.appendChild(el("li", { text: tab.title + " — " + tab.url }));
    });
    container.appendChild(el("h3", { text: "ChatGPT tabs" }));
    container.appendChild(tabsList);

    var sessionsList = el("ul", { className: "ccr-discover-sessions" });
    (doc.claude_code_sessions || []).forEach(function (s) {
      sessionsList.appendChild(el("li", { text: s.project_dir + " / " + s.session_id }));
    });
    container.appendChild(el("h3", { text: "Claude Code sessions" }));
    container.appendChild(sessionsList);

    var codexList = el("ul", { className: "ccr-discover-codex" });
    (doc.codex_sessions || []).forEach(function (s) {
      codexList.appendChild(el("li", { text: s.date + " / " + s.session_id }));
    });
    container.appendChild(el("h3", { text: "Codex sessions" }));
    container.appendChild(codexList);
  }

  // -- wiring ----------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", function () {
    loadState();

    document.getElementById("discover-run").addEventListener("click", function () {
      getJSON("/api/discover").then(renderDiscoverResults);
    });

    document.getElementById("refresh-builds").addEventListener("click", function () {
      var resultNode = document.getElementById("refresh-builds-result");
      postJSON("/api/refresh-builds", {}).then(function (outcome) {
        clear(resultNode);
        resultNode.appendChild(el("span", { text: outcome.ok ? "refreshed at " + outcome.collected_at : "failed: " + (outcome.detail || "") }));
        if (outcome.ok) loadState();
      });
    });

    document.getElementById("bind-form").addEventListener("submit", function (event) {
      event.preventDefault();
      var resultNode = document.getElementById("bind-result");
      var locatorText = document.getElementById("bind-locator").value;
      var locator;
      try {
        locator = JSON.parse(locatorText || "{}");
      } catch (e) {
        clear(resultNode);
        resultNode.appendChild(el("span", { text: "locator must be valid JSON" }));
        return;
      }
      var body = {
        work_ref: document.getElementById("bind-work-ref").value,
        role: document.getElementById("bind-role").value,
        provider: document.getElementById("bind-provider").value,
        locator: locator,
      };
      var seatRef = document.getElementById("bind-seat-ref").value;
      if (seatRef) body.seat_ref = seatRef;

      postJSON("/api/bind", body).then(function (outcome) {
        clear(resultNode);
        if (outcome.ok) {
          resultNode.appendChild(el("span", { text: "bound: " + outcome.binding_id }));
          loadState();
        } else {
          var problems = outcome.problems || [];
          problems.forEach(function (p) {
            resultNode.appendChild(el("div", { text: p }));
          });
        }
      });
    });
  });
})();
