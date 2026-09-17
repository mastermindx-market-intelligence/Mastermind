"""Source-free browser shell for one authorized visible-turn window."""
from __future__ import annotations

UI_PATH = "/workspace/conversation"

WORKSPACE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mastermind Conversation</title>
<style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;background:#080a0f;color:#ecebe5}
*{box-sizing:border-box}
body{margin:0;background:#080a0f;color:#ecebe5}
button{font:inherit}
.shell{min-height:100vh;display:grid;grid-template-rows:auto 1fr;background:radial-gradient(circle at 78% -10%,#192035 0,transparent 32%),#080a0f}
.top{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 24px;border-bottom:1px solid #252932;background:rgba(10,12,18,.92)}
.brand{min-width:0}.eyebrow{font:600 10px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.14em;color:#b89a68}.brand h1{margin:4px 0 0;font-size:17px;line-height:1.3}.state{display:flex;align-items:center;gap:8px}.pill{padding:6px 9px;border:1px solid #343a46;border-radius:999px;font:600 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:#aeb5c2}.dot{width:7px;height:7px;border-radius:50%;background:#687080}.pill[data-state="CONNECTED"] .dot{background:#55d992;box-shadow:0 0 12px #55d96688}.pill[data-state="DEGRADED"] .dot{background:#dcb35f}.pill[data-state="REFUSED"] .dot{background:#e57979}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) 290px;min-height:0}.conversation{min-width:0;display:grid;grid-template-rows:auto auto 1fr;padding:24px 30px 30px}.conversation-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding-bottom:18px}.conversation-head h2{margin:0;font-size:24px;letter-spacing:-.02em}.subtitle{margin:7px 0 0;color:#8e96a5;font-size:13px}.actions{display:flex;gap:8px}.action{border:1px solid #303641;background:#131720;color:#cdd2dc;border-radius:8px;padding:8px 11px;cursor:pointer}.action:hover{border-color:#565f70}.action:focus-visible{outline:2px solid #a98a58;outline-offset:2px}.action:disabled{opacity:.42;cursor:not-allowed}
.notice{margin:0 0 14px;padding:11px 13px;border:1px solid #574826;border-radius:9px;background:#201b11;color:#dfc783;font-size:12px}.notice[hidden]{display:none}.thread-wrap{min-height:0;position:relative;border:1px solid #222731;border-radius:14px;background:#0c0f15;overflow:hidden}.thread{height:100%;min-height:360px;max-height:calc(100vh - 190px);overflow:auto;padding:18px 20px 40px;scrollbar-gutter:stable}.empty{display:grid;place-items:center;height:100%;min-height:320px;padding:32px;color:#7d8593;text-align:center;font-size:13px}.empty[hidden]{display:none}.message{max-width:780px;margin:0 0 14px;padding:14px 16px;border:1px solid #2a303b;border-radius:12px;background:#11151d}.message[data-state="partial"]{border-style:dashed}.message[data-kind="withheld"]{background:#101218;color:#89909c}.message-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:8px}.message-label{font:600 10px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;color:#b89a68;text-transform:uppercase}.message-state{font:500 10px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;color:#7f8795}.message-body{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.58;color:#e1e3e8}
.context{border-left:1px solid #252932;background:#0b0e14;padding:24px 20px;overflow:auto}.context h3{margin:0 0 18px;font-size:13px}.facts{display:grid;gap:14px}.fact{padding-bottom:13px;border-bottom:1px solid #20252e}.fact-key{font:600 9px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:#6f7888;text-transform:uppercase;letter-spacing:.08em}.fact-value{margin-top:5px;font-size:12px;line-height:1.45;color:#c3c8d1;overflow-wrap:anywhere}.boundary{margin-top:20px;padding:12px;border:1px solid #2c323d;border-radius:9px;color:#858e9d;font-size:11px;line-height:1.5}
dialog{width:min(560px,calc(100vw - 32px));border:1px solid #343b48;border-radius:13px;background:#10141c;color:#e7e6e0;padding:0;box-shadow:0 24px 80px #000a}dialog::backdrop{background:#000a}.dialog-head{display:flex;justify-content:space-between;align-items:center;padding:16px 18px;border-bottom:1px solid #2b3039}.dialog-head h3{margin:0;font-size:14px}.dialog-body{padding:18px}.close{border:0;background:transparent;color:#adb4c0;font-size:19px;cursor:pointer}.evidence{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;color:#b8c0cd}
@media(max-width:850px){.workspace{grid-template-columns:1fr}.context{border-left:0;border-top:1px solid #252932}.thread{max-height:65vh}.conversation{padding:20px 16px}.top{padding:15px 16px}.conversation-head{align-items:flex-start;flex-direction:column}.actions{width:100%}.action{flex:1}}
</style>
</head>
<body>
<div class="shell">
  <header class="top">
    <div class="brand"><div class="eyebrow">MASTERMIND OS</div><h1>Conversation workspace</h1></div>
    <div id="connection" class="pill" data-state="DISCONNECTED"><span class="dot"></span><span id="connectionText">DISCONNECTED</span></div>
  </header>
  <main class="workspace">
    <section class="conversation" aria-labelledby="conversationTitle">
      <div class="conversation-head">
        <div><h2 id="conversationTitle">Managed turn</h2><p id="subtitle" class="subtitle">Connect an authorized host to read one qualified visible window.</p></div>
        <div class="actions"><button id="refresh" class="action" type="button" disabled>Refresh</button><button id="evidenceButton" class="action" type="button" disabled>Evidence</button><button id="disconnect" class="action" type="button" disabled>Disconnect</button></div>
      </div>
      <div id="gapNotice" class="notice" role="status" hidden></div>
      <div class="thread-wrap">
        <div id="empty" class="empty">No source content is embedded in this page.</div>
        <div id="thread" class="thread" aria-live="polite" hidden></div>
      </div>
    </section>
    <aside class="context" aria-label="Observation context">
      <h3>Current observation</h3>
      <div class="facts">
        <div class="fact"><div class="fact-key">Coverage</div><div id="coverage" class="fact-value">Not connected</div></div>
        <div class="fact"><div class="fact-key">History</div><div id="history" class="fact-value">Not proven</div></div>
        <div class="fact"><div class="fact-key">Acceptance</div><div id="acceptance" class="fact-value">Not projected</div></div>
        <div class="fact"><div class="fact-key">Turn state</div><div id="terminal" class="fact-value">Unknown</div></div>
      </div>
      <div class="boundary">This surface observes permitted content only. It cannot send, resume, stop, approve, or control a provider.</div>
    </aside>
  </main>
</div>
<dialog id="evidenceDialog"><div class="dialog-head"><h3>Source evidence</h3><button id="evidenceClose" class="close" type="button" aria-label="Close evidence">×</button></div><div class="dialog-body"><pre id="evidence" class="evidence"></pre></div></dialog>
<script>
(() => {
  "use strict";
  const WIRE_SCHEMA = "mastermind.workspace.content_read.v1";
  const VIEW_SCHEMA = "mastermind.workspace.visible_window.v1";
  const exact = (value, keys) => value !== null && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
  const elements = Object.freeze({
    connection: document.getElementById("connection"), connectionText: document.getElementById("connectionText"), subtitle: document.getElementById("subtitle"), refresh: document.getElementById("refresh"), evidenceButton: document.getElementById("evidenceButton"), disconnect: document.getElementById("disconnect"), gapNotice: document.getElementById("gapNotice"), empty: document.getElementById("empty"), thread: document.getElementById("thread"), coverage: document.getElementById("coverage"), history: document.getElementById("history"), acceptance: document.getElementById("acceptance"), terminal: document.getElementById("terminal"), evidenceDialog: document.getElementById("evidenceDialog"), evidenceClose: document.getElementById("evidenceClose"), evidence: document.getElementById("evidence")
  });
  let reader = null;
  let requestGeneration = 0;
  let current = null;

  function validEnvelope(value) {
    if (!exact(value, ["schema", "selection_ref", "mode", "view"]) || value.schema !== WIRE_SCHEMA || value.mode !== "observed-turn-window" || typeof value.selection_ref !== "string") return false;
    const view = value.view;
    if (!exact(view, ["schema", "source_ref", "scope", "observed_at", "epoch", "terminal", "coverage", "history", "acceptance", "capabilities", "items", "gaps"]) || view.schema !== VIEW_SCHEMA || view.source_ref !== value.selection_ref || view.scope !== "one-managed-turn-window" || typeof view.observed_at !== "string" || typeof view.epoch !== "string" || typeof view.terminal !== "boolean" || !["OBSERVED_WINDOW", "READ_LIMIT_REACHED", "GAP_PRESENT"].includes(view.coverage) || view.history !== "NOT_PROVEN" || view.acceptance !== "NOT_PROJECTED") return false;
    if (!exact(view.capabilities, ["send", "provider_control", "history"]) || Object.values(view.capabilities).some((flag) => flag !== false) || !Array.isArray(view.items) || view.items.length > 256 || !Array.isArray(view.gaps) || view.gaps.length > 256) return false;
    const ids = new Set();
    for (const item of view.items) {
      if (!exact(item, ["id", "source_sequence", "publication_sequence", "state", "kind", "text", "representation", "display_sha256"]) || typeof item.id !== "string" || ids.has(item.id) || !Number.isSafeInteger(item.source_sequence) || !Number.isSafeInteger(item.publication_sequence) || !["partial", "completed"].includes(item.state) || !["visible-response", "withheld"].includes(item.kind)) return false;
      ids.add(item.id);
      if (item.kind === "withheld") { if (item.text !== null || item.representation !== "WITHHELD" || item.display_sha256 !== null) return false; }
      else if (typeof item.text !== "string" || !["VISIBLE_TEXT", "FILTERED_VISIBLE_TEXT"].includes(item.representation) || typeof item.display_sha256 !== "string") return false;
    }
    return view.gaps.every((gap) => exact(gap, ["first", "last", "reason"]) && Number.isSafeInteger(gap.first) && Number.isSafeInteger(gap.last) && gap.first <= gap.last && gap.reason === "SOURCE_REPORTED_GAP");
  }

  function setState(value, detail) {
    elements.connection.dataset.state = value;
    elements.connectionText.textContent = value;
    if (detail !== undefined) elements.subtitle.textContent = detail;
  }

  function messageNode(item) {
    let card = Array.from(elements.thread.children).find((node) => node.dataset.itemId === item.id);
    if (!card) {
      card = document.createElement("article"); card.className = "message"; card.dataset.itemId = item.id;
      const head = document.createElement("div"); head.className = "message-head";
      const label = document.createElement("span"); label.className = "message-label";
      const state = document.createElement("span"); state.className = "message-state";
      const body = document.createElement("p"); body.className = "message-body";
      head.append(label, state); card.append(head, body);
    }
    card.dataset.state = item.state; card.dataset.kind = item.kind;
    card.querySelector(".message-label").textContent = item.kind === "withheld" ? "Withheld content" : "Visible response";
    card.querySelector(".message-state").textContent = item.state.toUpperCase();
    card.querySelector(".message-body").textContent = item.kind === "withheld" ? "Content withheld by source policy." : item.text;
    return card;
  }

  function render(value) {
    current = value;
    const view = value.view;
    const previousTop = elements.thread.scrollTop;
    const nearBottom = elements.thread.scrollHeight - previousTop - elements.thread.clientHeight < 60;
    const keep = new Set(view.items.map((item) => item.id));
    for (const child of Array.from(elements.thread.children)) if (!keep.has(child.dataset.itemId)) child.remove();
    for (const item of view.items) elements.thread.appendChild(messageNode(item));
    elements.empty.hidden = view.items.length > 0;
    elements.thread.hidden = view.items.length === 0;
    if (!elements.thread.hidden) elements.thread.scrollTop = nearBottom ? elements.thread.scrollHeight : previousTop;
    elements.coverage.textContent = view.coverage.replaceAll("_", " ");
    elements.history.textContent = "Not proven beyond this observed window";
    elements.acceptance.textContent = "Not projected by this source";
    elements.terminal.textContent = view.terminal ? "Provider turn terminal" : "Provider turn nonterminal";
    elements.gapNotice.hidden = view.gaps.length === 0;
    elements.gapNotice.textContent = view.gaps.length ? `${view.gaps.length} source-reported gap${view.gaps.length === 1 ? "" : "s"}. This is not complete history.` : "";
    elements.evidence.textContent = JSON.stringify({source_ref: value.selection_ref, observed_at: view.observed_at, epoch: view.epoch, coverage: view.coverage, history: view.history, acceptance: view.acceptance, terminal: view.terminal, gaps: view.gaps}, null, 2);
    elements.refresh.disabled = false; elements.disconnect.disabled = false; elements.evidenceButton.disabled = false;
    setState(view.gaps.length ? "DEGRADED" : "CONNECTED", `Observed ${view.items.length} item${view.items.length === 1 ? "" : "s"} at ${view.observed_at}.`);
  }

  function clear(detail = "Connect an authorized host to read one qualified visible window.") {
    current = null; elements.thread.replaceChildren(); elements.thread.hidden = true; elements.empty.hidden = false; elements.empty.textContent = "No source content is embedded in this page."; elements.gapNotice.hidden = true; elements.coverage.textContent = "Not connected"; elements.history.textContent = "Not proven"; elements.acceptance.textContent = "Not projected"; elements.terminal.textContent = "Unknown"; elements.evidence.textContent = ""; elements.refresh.disabled = reader === null; elements.disconnect.disabled = reader === null; elements.evidenceButton.disabled = true; setState("DISCONNECTED", detail);
  }

  async function refresh() {
    if (typeof reader !== "function") return;
    const request = ++requestGeneration;
    elements.refresh.disabled = true;
    setState("LOADING", "Reading the current authorized window…");
    try {
      const value = await reader();
      if (request !== requestGeneration) return;
      if (!validEnvelope(value)) throw new Error("REFUSED");
      render(value);
    } catch (error) {
      if (request !== requestGeneration) return;
      const code = error !== null && typeof error === "object" && typeof error.code === "string" ? error.code : "";
      if (current !== null && code === "SOURCE_UNAVAILABLE") {
        elements.refresh.disabled = false; elements.disconnect.disabled = false; elements.evidenceButton.disabled = false;
        setState("DEGRADED", "Source unavailable. Showing the last qualified observation.");
        return;
      }
      current = null; elements.thread.replaceChildren(); elements.thread.hidden = true; elements.empty.hidden = false; elements.empty.textContent = "The authorized source could not be displayed."; elements.evidenceButton.disabled = true; elements.gapNotice.hidden = true; elements.refresh.disabled = false; elements.disconnect.disabled = false; setState("REFUSED", "Source unavailable, access changed, or the response was invalid.");
    }
  }

  function connect(readerFunction) {
    if (typeof readerFunction !== "function") throw new TypeError("reader must be a function");
    reader = readerFunction;
    requestGeneration += 1;
    return refresh();
  }

  function disconnect() {
    reader = null; requestGeneration += 1; clear();
  }

  elements.refresh.addEventListener("click", refresh);
  elements.disconnect.addEventListener("click", disconnect);
  elements.evidenceButton.addEventListener("click", () => { if (current) elements.evidenceDialog.showModal(); });
  elements.evidenceClose.addEventListener("click", () => elements.evidenceDialog.close());
  window.mastermindWorkspace = Object.freeze({connect, refresh, disconnect});
  clear();
})();
</script>
</body>
</html>"""

__all__ = ["UI_PATH", "WORKSPACE_HTML"]
