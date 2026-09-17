"""Critical portfolio snapshot failures stay typed and secret-safe."""
from __future__ import annotations

import json


def _body(resp):
    return json.loads(resp.body)


def test_missing_snapshot_remains_clean_not_found(tmp_path, monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    response = web.api_portfolio("autonomous")
    payload = _body(response)
    assert response.status_code == 404
    assert payload == {"error": "no book yet", "portfolio_id": "autonomous"}


def test_corrupt_snapshot_is_closed_unavailable(tmp_path, monkeypatch):
    from app import web

    (tmp_path / "latest.json").write_text('{"secret":"/Users/private/book", bad-json')
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    response = web.api_portfolio("autonomous")
    payload = _body(response)

    assert response.status_code == 500
    assert payload == {
        "error": "portfolio_unavailable",
        "snapshot_status": "unavailable",
        "portfolio_id": "autonomous",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "bad-json" not in raw


def test_registry_failure_is_closed_unavailable(tmp_path, monkeypatch):
    from app import web
    from portfolio import registry

    (tmp_path / "latest.json").write_text(json.dumps({"positions": [], "rejected": []}))
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    monkeypatch.setattr(
        registry,
        "benchmark",
        lambda _pid: (_ for _ in ()).throw(RuntimeError("secret /Users/private/registry token=bad")),
    )
    response = web.api_portfolio("autonomous")
    payload = _body(response)
    assert response.status_code == 500
    assert payload["error"] == "portfolio_unavailable"
    assert payload["snapshot_status"] == "unavailable"
    assert payload["portfolio_id"] == "autonomous"
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw
