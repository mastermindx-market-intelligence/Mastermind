"""Self-Directed history failures must not become a zero-trade blotter."""
from __future__ import annotations

import json
from pathlib import Path


def test_self_directed_history_failure_is_unknown_and_secret_safe(monkeypatch):
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(
        self_directed,
        "_load_account",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/self-history")),
    )

    payload = json.loads(web.api_self_directed_history().body)

    assert payload["history_status"] == "unavailable"
    assert payload["error"] == "self_directed_history_unavailable"
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "self_directed_history_unreadable"
    assert payload["history"] == []
    assert payload["pending"] == []
    assert payload["realized_total"] is None
    assert payload["n_closed"] is None
    assert payload["n_buys"] is None
    assert payload["win_rate"] is None
    encoded = json.dumps(payload)
    assert "secret" not in encoded
    assert "/Users/private" not in encoded


def test_self_history_ui_distinguishes_loading_unavailable_and_empty():
    import subprocess

    html = (Path(__file__).parents[1] / "app/static/index.html").read_text()

    def shipped_function(name):
        start = html.index(f"function {name}(")
        end = html.index("\n}", start) + 2
        return html[start:end]

    source = "\n".join(shipped_function(name) for name in (
        "_selfHistoryUnavailable", "refreshSelf", "_selfHistState", "renderSelfHistory",
    ))
    harness = r"""
const assert = require('node:assert/strict');
const host = {innerHTML: ''};
let _self = null, _selfHist = null, _selfSettled = false, _selfHistSettled = false;
let response;
function t(key) { return key; }
function E(id) { return id === 'sd-history-host' ? host : null; }
function renderSelf() { renderSelfHistory(); }
async function fetch(url) {
  if (url.endsWith('/history')) return response();
  return {ok: true, json: async () => ({nav: 2000})};
}
""" + source + r"""
(async () => {
  renderSelfHistory();
  assert.match(host.innerHTML, /load/i);
  assert.doesNotMatch(host.innerHTML, /sd\.hist_empty/);

  response = () => ({ok: true, json: async () => ({history: []})});
  await refreshSelf();
  assert.match(host.innerHTML, /sd\.hist_empty/);

  for (const failed of [
    () => ({ok: false}),
    () => { throw new Error('offline'); },
    () => ({ok: true, json: async () => ({history: [], history_status: 'unavailable'})}),
    () => ({ok: true, json: async () => ({history: [], error: 'self_directed_history_unavailable'})}),
    () => ({ok: true, json: async () => ({history: [], status: 'unavailable'})}),
  ]) {
    response = failed;
    await refreshSelf();
    assert.match(host.innerHTML, /sd\.hist_unavailable/);
    assert.doesNotMatch(host.innerHTML, /sd\.hist_empty/);
    assert.equal(_selfHistSettled, true);
  }

  response = () => ({ok: true, json: async () => ({history: []})});
  await refreshSelf();
  assert.match(host.innerHTML, /sd\.hist_empty/);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run(["node", "-e", harness], check=True, timeout=20)
