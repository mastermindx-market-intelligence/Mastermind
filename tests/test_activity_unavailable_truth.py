"""Brain Log activity preserves partial/unavailable evidence truth."""
from __future__ import annotations

import json
from pathlib import Path


def _body(resp):
    return json.loads(resp.body)


def test_successful_empty_activity_keeps_legacy_list_contract(tmp_path, monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    payload = _body(web.api_activity())
    assert payload == []


def test_successful_activity_events_keep_required_shape(tmp_path, monkeypatch):
    from app import web

    book = tmp_path / "portfolio"
    book.mkdir(parents=True)
    (book / "latest.json").write_text(json.dumps({
        "as_of": "2026-09-17",
        "gross": 0.25,
        "cash": 0.75,
        "regime": {"quad_name": "Goldilocks"},
        "decisions": [{"subject": "AAPL", "lean": "buy", "thesis": "test", "logged_at": "2026-09-17T12:00:00Z"}],
    }))
    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    payload = _body(web.api_activity())
    assert isinstance(payload, list) and payload
    assert {row["kind"] for row in payload} >= {"decision", "run"}
    for row in payload:
        for field in ("ts", "kind", "title", "detail"):
            assert field in row


def test_one_source_failure_is_partial_not_silently_omitted(tmp_path, monkeypatch):
    from app import web

    book = tmp_path / "portfolio"
    book.mkdir(parents=True)
    (book / "latest.json").write_text(json.dumps({
        "as_of": "2026-09-17", "gross": 0.2, "cash": 0.8,
        "decisions": [{"subject": "AAPL", "lean": "watch", "thesis": "healthy source"}],
    }))

    calls = {"n": 0}
    def data_root():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("secret /Users/private/positions_ledger.json")
        return tmp_path

    monkeypatch.setattr(web, "_data", data_root)
    response = web.api_activity()
    payload = _body(response)

    assert payload["activity_status"] == "partial"
    assert isinstance(payload["events"], list) and payload["events"]
    assert {row["kind"] for row in payload["events"]} >= {"decision", "run"}
    assert payload["failed_sources"] == ["trades"]
    assert "secret" not in response.body.decode()
    assert "/Users/private" not in response.body.decode()


def test_all_source_failures_are_unavailable_not_empty(monkeypatch):
    from app import web

    monkeypatch.setattr(
        web,
        "_data",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/activity")),
    )
    response = web.api_activity()
    payload = _body(response)

    assert payload["activity_status"] == "unavailable"
    assert payload["events"] is None
    assert payload["failed_sources"] == ["trades", "decisions", "research"]
    assert "secret" not in response.body.decode()
    assert "/Users/private" not in response.body.decode()


def test_activity_client_consumes_unavailable_and_partial_before_empty():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "function _activityFetch()" in html
    assert "function _applyActivityFeed(data)" in html
    assert "window.retryBrainActivity = function()" in html

    render_start = html.index("function renderBrainLog()")
    render_end = html.index("// ── RESEARCH FEED", render_start)
    render = html[render_start:render_end]
    assert "_activityStatus === 'loading'" in render
    assert "_activityStatus === 'unavailable'" in render
    assert "_activityStatus === 'partial'" in render
    assert render.index("_activityStatus === 'unavailable'") < render.index("!_activity.length")
    assert render.index("_activityStatus === 'partial'") < render.index("!_activity.length")
    assert "retryBrainActivity()" in render

    hydrate_start = html.index("function _hydrateShared()")
    hydrate_end = html.index("async function fetchAll", hydrate_start)
    hydrate = html[hydrate_start:hydrate_end]
    assert "_activityFetch()" in hydrate
    assert "_applyActivityFeed" in hydrate
    assert "fetch('/api/activity').then(function(r)  { return r.ok ? r.json() : [];" not in hydrate
