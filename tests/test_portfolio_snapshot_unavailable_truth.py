"""Critical portfolio snapshot failures stay typed and secret-safe."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


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

def _assert_unavailable(response):
    assert response.status_code == 500
    assert _body(response) == {
        "error": "portfolio_unavailable", "snapshot_status": "unavailable",
        "portfolio_id": "autonomous",
    }
    assert "private" not in response.body.decode()
    assert "token=" not in response.body.decode()


@pytest.mark.parametrize("case", [
    "directory", "dangling", "unreadable", "path_resolution",
    "read_missing_existing_entry", "lstat_unreadable",
])
def test_filesystem_entry_failure_is_typed_not_false_absence(tmp_path, monkeypatch, caplog, case):
    from app import web
    latest = tmp_path / "latest.json"
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    if case == "directory":
        latest.mkdir()
    elif case == "dangling":
        latest.symlink_to(tmp_path / "absent-target")
    elif case == "path_resolution":
        def fail_dir(_pid=None):
            raise PermissionError("private path token=hidden")
        monkeypatch.setattr(web, "_portfolio_dir", fail_dir)
    elif case in ("unreadable", "read_missing_existing_entry"):
        latest.write_text('{"positions":[]}')
        read = Path.read_text
        def fail_read(path, *args, **kwargs):
            if path == latest:
                error = PermissionError if case == "unreadable" else FileNotFoundError
                raise error("private reader token=hidden")
            return read(path, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", fail_read)
    else:
        lstat = Path.lstat
        def fail_lstat(path, *args, **kwargs):
            if path == latest:
                raise PermissionError("private stat token=hidden")
            return lstat(path, *args, **kwargs)
        monkeypatch.setattr(Path, "lstat", fail_lstat)
    _assert_unavailable(web.api_portfolio("autonomous"))
    assert "private" not in caplog.text and "token=" not in caplog.text


def test_snapshot_read_does_not_trust_exists_preflight(tmp_path, monkeypatch):
    from app import web
    latest = tmp_path / "latest.json"
    latest.write_text("{bad-json")
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    exists = Path.exists
    def misleading(path):
        if path == latest:
            raise AssertionError("exists must not decide observed snapshot availability")
        return exists(path)
    monkeypatch.setattr(Path, "exists", misleading)
    _assert_unavailable(web.api_portfolio("autonomous"))


@pytest.mark.parametrize("payload", [None, [], "wrong"])
def test_malformed_top_level_snapshot_is_typed_unavailable(tmp_path, monkeypatch, payload):
    from app import web
    (tmp_path / "latest.json").write_text(json.dumps(payload))
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    _assert_unavailable(web.api_portfolio("autonomous"))


def test_actual_asgi_snapshot_failure_is_fixed_and_does_not_change_artifact(tmp_path, monkeypatch, caplog):
    from app import web
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    latest = tmp_path / "latest.json"
    latest.write_text('{"private":"token=hidden", broken')
    before = latest.read_bytes()
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    app = FastAPI()
    app.include_router(web.router)
    with TestClient(app) as client:
        response = client.get("/api/portfolio", params={"portfolio": "autonomous"})
    assert response.status_code == 500
    assert response.json() == {
        "error": "portfolio_unavailable", "snapshot_status": "unavailable",
        "portfolio_id": "autonomous",
    }
    assert "JSONDecodeError" in caplog.text
    assert "private" not in response.text + caplog.text
    assert "token=hidden" not in response.text + caplog.text
    assert latest.read_bytes() == before


def test_clean_absence_requires_read_and_absence_confirmation(tmp_path, monkeypatch):
    from app import web
    latest = tmp_path / "latest.json"
    latest.write_text("{}")
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    observed = []
    read, lstat = Path.read_text, Path.lstat
    def gone_read(path, *args, **kwargs):
        if path == latest:
            observed.append("read")
            raise FileNotFoundError("gone")
        return read(path, *args, **kwargs)
    def gone_lstat(path, *args, **kwargs):
        if path == latest:
            observed.append("lstat")
            raise FileNotFoundError("gone")
        return lstat(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", gone_read)
    monkeypatch.setattr(Path, "lstat", gone_lstat)
    response = web.api_portfolio("autonomous")
    assert response.status_code == 404
    assert _body(response) == {"error": "no book yet", "portfolio_id": "autonomous"}
    assert observed == ["read", "lstat"]


def test_unknown_id_is_rejected_before_snapshot_path(monkeypatch):
    from app import web
    from fastapi import HTTPException
    monkeypatch.setattr(web, "_portfolio_dir", lambda *_a: pytest.fail("unknown ID accessed snapshot path"))
    with pytest.raises(HTTPException) as exc:
        web.api_portfolio("not-a-real-portfolio")
    assert exc.value.status_code == 404
