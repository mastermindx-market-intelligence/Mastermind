"""Self-contained in-chat Control Room resource for the Steward app."""
from __future__ import annotations

UI_RESOURCE_URI = "ui://mastermind/steward/control-room-v2.html"
UI_MIME_TYPE = "text/html;profile=mcp-app"

CONTROL_ROOM_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mastermind Control Room</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box}
body{margin:0;background:#090d14;color:#edf2f7}
.wrap{padding:16px;min-width:0}
.head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}
h1{font-size:16px;line-height:1.25;margin:0}
.pill{flex:0 0 auto;padding:5px 9px;border:1px solid #334155;border-radius:999px;font-size:11px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}
.card{min-width:0;background:#111827;border:1px solid #263244;border-radius:10px;padding:10px}
.key{font-size:10px;color:#94a3b8;text-transform:uppercase;overflow-wrap:anywhere}
.value{font-size:14px;font-weight:650;margin-top:5px;overflow-wrap:anywhere}
.meta{font-size:10px;color:#94a3b8;margin-top:5px;overflow-wrap:anywhere}
.notice{margin:0 0 8px;padding:8px 10px;border:1px solid #334155;border-radius:8px;color:#cbd5e1;font-size:11px;overflow-wrap:anywhere}
.notice[hidden]{display:none}
.pill[data-state="FACTS"]{border-color:#166534;color:#86efac}
.pill[data-state="DEGRADED"]{border-color:#854d0e;color:#fde047}
.pill[data-state="REFUSED"]{border-color:#991b1b;color:#fca5a5}
.empty{padding:24px;border:1px dashed #334155;border-radius:10px;text-align:center;color:#94a3b8;overflow-wrap:anywhere}
@media (max-width:480px){.wrap{padding:12px}.head{align-items:flex-start}.grid{grid-template-columns:1fr}.empty{padding:18px 12px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <h1>Mastermind Control Room</h1>
    <span id="state" class="pill" aria-live="polite">UNKNOWN</span>
  </div>
  <div id="notice" class="notice" aria-live="polite" hidden></div>
  <div id="content" class="empty" aria-live="polite">No authoritative facts available.</div>
</div>
<script>
(() => {
  const MAX_FACTS = 64;
  const RESULT_SCHEMA = "mastermind.secretary_grounding_mcp_result.v2";
  const VALID_STATES = new Set(["FACTS", "DEGRADED", "UNKNOWN", "REFUSED"]);
  const VALID_FRESHNESS = new Set(["FRESH", "STALE", "UNKNOWN"]);
  const content = document.getElementById("content");
  const notice = document.getElementById("notice");
  const state = document.getElementById("state");
  let latest = null;

  const isRecord = (value) =>
    value !== null && typeof value === "object" && !Array.isArray(value);

  const hasOwn = (value, key) =>
    Object.prototype.hasOwnProperty.call(value, key);

  const hasExactKeys = (value, keys) =>
    isRecord(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((key) => hasOwn(value, key));

  const shorten = (value) => {
    const text = String(value ?? "");
    return text.length > 32
      ? text.slice(0, 16) + "…" + text.slice(-10)
      : text;
  };

  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };

  const reasonText = (data) => {
    const reasons = data && data.reason_codes ? data.reason_codes.slice(0, 4) : [];
    return reasons.length ? " " + reasons.join(", ") + "." : "";
  };

  const emptyMessage = (value, data) => {
    if (value === "REFUSED") return "The request was refused." + reasonText(data);
    if (value === "DEGRADED") return "Source data is degraded." + reasonText(data);
    if (value === "FACTS") return "No structured facts returned.";
    return "No authoritative facts available." + reasonText(data);
  };

  const sourceIsValid = (source) =>
    hasExactKeys(source, ["owner", "source_ref", "observed_at"]) &&
    typeof source.owner === "string" && source.owner.trim() === source.owner &&
    source.owner.length > 0 &&
    typeof source.source_ref === "string" &&
    source.source_ref.trim() === source.source_ref && source.source_ref.length > 0 &&
    (source.observed_at === null || typeof source.observed_at === "string");

  const factIsValid = (fact) => {
    if (!isRecord(fact) || Object.prototype.hasOwnProperty.call(fact, "subject_ref")) {
      return false;
    }
    if (!hasExactKeys(fact, ["predicate", "value", "freshness", "sources"])) {
      return false;
    }
    const valueType = typeof fact.value;
    const valueIsValid =
      valueType === "string" ||
      valueType === "boolean" ||
      (valueType === "number" && Number.isInteger(fact.value));
    return (
      typeof fact.predicate === "string" && fact.predicate.length > 0 &&
      valueIsValid &&
      VALID_FRESHNESS.has(fact.freshness) &&
      Array.isArray(fact.sources) &&
      fact.sources.length > 0 && fact.sources.length <= 8 &&
      fact.sources.every(sourceIsValid)
    );
  };

  const subjectIsValid = (subject) => {
    if (!isRecord(subject) || Object.keys(subject).length !== 2) return false;
    if (!hasOwn(subject, "subject_ref") || !hasOwn(subject, "facts")) return false;
    if (
      typeof subject.subject_ref !== "string" ||
      subject.subject_ref.trim() !== subject.subject_ref ||
      subject.subject_ref.length === 0 ||
      !Array.isArray(subject.facts) ||
      subject.facts.length === 0
    ) {
      return false;
    }
    const seenPredicates = new Set();
    for (const fact of subject.facts) {
      if (!factIsValid(fact) || seenPredicates.has(fact.predicate)) return false;
      seenPredicates.add(fact.predicate);
    }
    return true;
  };

  const dataIsValid = (data) => {
    const subjects = data && data.subjects;
    if (!hasExactKeys(data, ["state", "subjects", "reason_codes"])) return false;
    if (!VALID_STATES.has(data.state) || !Array.isArray(subjects)) return false;
    if (
      !Array.isArray(data.reason_codes) ||
      data.reason_codes.length > 16 ||
      new Set(data.reason_codes).size !== data.reason_codes.length ||
      !data.reason_codes.every(
        (reason) => typeof reason === "string" && reason.length > 0
      )
    ) {
      return false;
    }
    const seenSubjects = new Set();
    let factCount = 0;
    for (const subject of subjects) {
      if (!subjectIsValid(subject) || seenSubjects.has(subject.subject_ref)) return false;
      seenSubjects.add(subject.subject_ref);
      factCount += subject.facts.length;
    }
    if (data.state === "FACTS") {
      return (
        factCount > 0 &&
        data.reason_codes.length === 0 &&
        subjects.every((subject) =>
          subject.facts.every((fact) => fact.freshness === "FRESH")
        )
      );
    }
    if (data.state === "DEGRADED") return data.reason_codes.length > 0;
    return factCount === 0 && data.reason_codes.length > 0;
  };

  const rowsFor = (data) => {
    if (!dataIsValid(data)) return [];
    const rows = [];
    for (const subject of data.subjects) {
      for (const fact of subject.facts) {
        if (rows.length >= MAX_FACTS) break;
        rows.push({ subjectRef: subject.subject_ref, fact });
      }
      if (rows.length >= MAX_FACTS) break;
    }
    return rows;
  };

  const totalFacts = (data) =>
    data.subjects.reduce((count, subject) => count + subject.facts.length, 0);

  const viewFor = (value) => {
    if (value === null) {
      return { currentState: "UNKNOWN", data: null, rows: [], malformed: false };
    }
    const envelope = isRecord(value) && value.structuredContent
      ? value.structuredContent
      : value;
    if (!isRecord(envelope)) {
      return { currentState: "REFUSED", data: null, rows: [], malformed: true };
    }
    if (envelope.ok === false) {
      return { currentState: "REFUSED", data: null, rows: [], malformed: false };
    }
    let data = envelope;
    if (hasOwn(envelope, "data")) {
      if (
        envelope.ok !== true ||
        envelope.schema !== RESULT_SCHEMA ||
        envelope.server_version !== "2.0.0"
      ) {
        return { currentState: "REFUSED", data: null, rows: [], malformed: true };
      }
      data = envelope.data;
    }
    if (!dataIsValid(data)) {
      return { currentState: "REFUSED", data: null, rows: [], malformed: true };
    }
    return {
      currentState: data.state,
      data,
      rows: rowsFor(data),
      malformed: false,
    };
  };

  function render() {
    const view = viewFor(latest);
    state.textContent = view.currentState;
    state.dataset.state = view.currentState;
    notice.replaceChildren();
    notice.hidden = true;
    content.replaceChildren();

    if (view.malformed) {
      content.className = "empty";
      content.appendChild(node("span", "", "Malformed tool result refused."));
      return;
    }

    if (!view.rows.length) {
      content.className = "empty";
      content.appendChild(node("span", "", emptyMessage(view.currentState, view.data)));
      return;
    }

    const messages = [];
    if (view.data.reason_codes.length) {
      messages.push("Reasons: " + view.data.reason_codes.slice(0, 4).join(", ") + ".");
    }
    if (totalFacts(view.data) > view.rows.length) {
      messages.push("Showing the first 64 facts.");
    }
    if (messages.length) {
      notice.hidden = false;
      notice.appendChild(node("span", "", messages.join(" ")));
    }

    content.className = "grid";
    for (const row of view.rows) {
      const fact = row.fact;
      const source = fact.sources[0];
      const card = node("article", "card");
      card.appendChild(node("div", "key", fact.predicate));
      card.appendChild(node("div", "value", fact.value));
      card.appendChild(
        node(
          "div",
          "meta",
          `${shorten(row.subjectRef)} · ${fact.freshness}`
        )
      );
      card.appendChild(
        node(
          "div",
          "meta",
          `${source.owner} · ${shorten(source.source_ref)}`
        )
      );
      content.appendChild(card);
    }
  }

  function accept(value) {
    if (value !== undefined && value !== null) {
      latest = value;
      render();
    }
  }

  window.addEventListener(
    "message",
    (event) => {
      if (event.source !== window.parent) return;
      const message = event && event.data;
      if (!message || message.jsonrpc !== "2.0") return;
      if (message.method !== "ui/notifications/tool-result") return;
      accept(message.params && (message.params.structuredContent || message.params));
    },
    { passive: true }
  );

  window.addEventListener("openai:set_globals", (event) => {
    const globals = event.detail && event.detail.globals;
    accept(globals && (globals.toolOutput || globals.structuredContent));
  });

  const openai = window.openai || {};
  accept(openai.toolOutput || openai.structuredContent);
  render();
})();
</script>
</body>
</html>"""

__all__ = ["CONTROL_ROOM_HTML", "UI_MIME_TYPE", "UI_RESOURCE_URI"]
