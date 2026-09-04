"""Self-contained in-chat Control Room resource for the Steward app."""
from __future__ import annotations

UI_RESOURCE_URI = "ui://mastermind/steward/control-room-v1.html"
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
  <div id="content" class="empty" aria-live="polite">No authoritative facts available.</div>
</div>
<script>
(() => {
  const content = document.getElementById("content");
  const state = document.getElementById("state");
  let latest = null;

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
    const reasons = Array.isArray(data && data.reason_codes)
      ? data.reason_codes.filter((value) => typeof value === "string").slice(0, 4)
      : [];
    return reasons.length ? " " + reasons.join(", ") + "." : "";
  };

  const emptyMessage = (value, data) => {
    if (value === "REFUSED") return "The request was refused." + reasonText(data);
    if (value === "DEGRADED") return "Source data is degraded." + reasonText(data);
    if (value === "FACTS") return "No structured facts returned.";
    return "No authoritative facts available." + reasonText(data);
  };

  function render() {
    const envelope = latest && latest.structuredContent
      ? latest.structuredContent
      : latest;
    const data = envelope && envelope.data ? envelope.data : envelope;
    const facts = Array.isArray(data && data.facts) ? data.facts.slice(0, 64) : [];
    const currentState = String(
      (data && data.state) || (envelope && envelope.ok === false ? "REFUSED" : "UNKNOWN")
    );
    state.textContent = currentState;
    content.replaceChildren();

    if (!facts.length) {
      content.className = "empty";
      content.appendChild(node("span", "", emptyMessage(currentState, data)));
      return;
    }

    content.className = "grid";
    for (const fact of facts) {
      const source = Array.isArray(fact && fact.sources) && fact.sources[0]
        ? fact.sources[0]
        : {};
      const card = node("article", "card");
      card.appendChild(node("div", "key", fact && fact.predicate));
      card.appendChild(node("div", "value", fact && fact.value));
      card.appendChild(
        node(
          "div",
          "meta",
          `${shorten(fact && fact.subject_ref)} · ${String((fact && fact.freshness) || "UNKNOWN")}`
        )
      );
      card.appendChild(
        node(
          "div",
          "meta",
          `${String(source.owner || "unknown")} · ${shorten(source.source_ref)}`
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
