"""User-facing read failures stay distinct from legitimate not-built-yet states."""
from __future__ import annotations

import json
from pathlib import Path


def _body(resp):
    return json.loads(resp.body)


def _boom(*_args, **_kwargs):
    raise RuntimeError("secret /Users/private/presentation token=bad")


def test_posture_failure_is_unavailable_and_secret_safe(monkeypatch):
    from app import web
    from brain import posture

    monkeypatch.setattr(posture, "posture", _boom)
    response = web.api_posture("flagship")
    payload = _body(response)

    assert payload["available"] is False
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "posture_unavailable"
    assert payload["posture_label"] == "—"
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def test_market_view_missing_artifact_remains_not_built(tmp_path, monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    response = web.api_market_view()
    payload = _body(response)
    assert response.status_code == 404
    assert payload["available"] is False
    assert "not built yet" in payload["note"]
    assert "read_status" not in payload


def test_market_view_read_failure_is_closed_unavailable(tmp_path, monkeypatch):
    from app import web

    root = tmp_path / "market_view"
    root.mkdir(parents=True)
    (root / "latest.json").write_text("{not-json")
    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    response = web.api_market_view()
    payload = _body(response)

    assert response.status_code == 500
    assert payload == {
        "available": False,
        "read_status": "unavailable",
        "error": "market_view_unavailable",
        "note": "market view unavailable",
    }
    assert "not-json" not in response.body.decode()


def test_agenda_missing_artifact_remains_not_built(monkeypatch):
    from app import web
    from brain import improvement_agenda

    monkeypatch.setattr(improvement_agenda, "latest", lambda: None)
    response = web.api_agenda()
    payload = _body(response)
    assert response.status_code == 404
    assert payload["available"] is False
    assert "no agenda built yet" in payload["note"]
    assert "read_status" not in payload


def test_agenda_read_failure_is_closed_unavailable(monkeypatch):
    from app import web
    from brain import improvement_agenda

    monkeypatch.setattr(improvement_agenda, "latest", _boom)
    response = web.api_agenda()
    payload = _body(response)

    assert response.status_code == 500
    assert payload == {
        "available": False,
        "read_status": "unavailable",
        "error": "agenda_unavailable",
        "note": "agenda unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def test_clients_render_failure_as_unavailable_not_not_built_or_raw_error():
    index = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert "function _postureUnavailable()" in index
    chip = index[index.index("function _postureChipHTML") : index.index("function loadDeskPosture")]
    assert "p.read_status === 'unavailable'" in chip
    assert chip.index("p.read_status === 'unavailable'") < chip.index("!p.available")
    load = index[index.index("function loadDeskPosture") : index.index("function renderDecisions")]
    assert "_postureUnavailable()" in load
    assert "host.innerHTML = '';" not in load

    market = (Path(__file__).parents[1] / "app" / "static" / "market_view.html").read_text()
    fetch = market[market.index('fetch("/api/market_view"') : market.index('</script>', market.index('fetch("/api/market_view"'))]
    assert "res.body.error" not in fetch
    assert "e && e.message" not in fetch
    assert '"market view unavailable"' in fetch

    agenda = (Path(__file__).parents[1] / "app" / "static" / "agenda.html").read_text()
    fetch = agenda[agenda.index('fetch("/api/agenda"') : agenda.index('</script>', agenda.index('fetch("/api/agenda"'))]
    assert "res.body.error" not in fetch
    assert "e && e.message" not in fetch
    assert '"agenda unavailable"' in fetch
