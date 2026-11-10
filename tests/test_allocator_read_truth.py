"""Shadow allocator persisted/read/build failures remain explicit and secret-safe."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio import firm_allocator as FA


@pytest.fixture(autouse=True)
def _private_allocator_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(FA, "_OUT_DIR", tmp_path / "allocator")
    monkeypatch.setattr(FA, "_latest_lifecycle", lambda: {})
    monkeypatch.setattr(FA, "_latest_benchmark", lambda: {})
    monkeypatch.setattr(FA, "_latest_mandate_packet", lambda _bid: {})


def _module():
    return FA


def _route(web):
    return web.api_firm_allocator


def _body(resp):
    return json.loads(resp.body)


def test_checked_latest_distinguishes_absent_from_corrupt(tmp_path, monkeypatch):
    mod = _module()
    monkeypatch.setattr(mod, "_OUT_DIR", tmp_path / "allocator")

    status, artifact = mod.latest_artifact_checked()
    assert status == "absent"
    assert artifact is None

    mod._OUT_DIR.mkdir(parents=True)
    (mod._OUT_DIR / "2026-09-17.json").write_text("{not-json")
    status, artifact = mod.latest_artifact_checked()
    assert status == "unavailable"
    assert artifact is None


def test_legacy_latest_still_returns_none_for_missing(tmp_path, monkeypatch):
    mod = _module()
    monkeypatch.setattr(mod, "_OUT_DIR", tmp_path / "allocator")
    assert mod.latest_artifact() is None


def test_build_failure_is_closed_and_secret_safe(tmp_path, monkeypatch):
    mod = _module()
    monkeypatch.setattr(mod, "_OUT_DIR", tmp_path / "allocator")

    def boom():
        raise RuntimeError("secret /Users/private/lifecycle api_key=bad")

    monkeypatch.setattr(mod, "_latest_lifecycle", boom)
    artifact = mod.build_latest()
    assert artifact["advisory_only"] is True
    assert artifact["computed"] is False
    assert artifact["build_status"] == "unavailable"
    assert artifact["error"] == "firm_allocator_build_unavailable"
    assert artifact["reason"] == "firm allocator unavailable"
    raw = json.dumps(artifact)
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


def test_persist_failure_preserves_computed_evidence_but_marks_partial(monkeypatch):
    from app import web
    mod = _module()
    monkeypatch.setattr(mod, "_persist", lambda _artifact: False)

    artifact = mod.build_latest(
        lifecycle={}, benchmark={}, mandate_packets={}, book_ids=["flagship"]
    )
    assert artifact["advisory_only"] is True
    assert artifact["computed"] is True
    assert artifact["persist_status"] == "unavailable"
    assert artifact["error"] == "firm_allocator_persist_unavailable"
    assert artifact["reason"] == "firm allocator computed but persistence unavailable"
    assert artifact["books"]

    monkeypatch.setattr(mod, "latest_artifact_checked", lambda: ("absent", None), raising=False)
    monkeypatch.setattr(mod, "latest_artifact", lambda: None)
    monkeypatch.setattr(mod, "build_latest", lambda: artifact)
    payload = _body(_route(web)())
    assert payload["read_status"] == "partial"
    assert payload["computed"] is True
    assert payload["books"] == artifact["books"]


def test_endpoint_corrupt_latest_is_unavailable_and_does_not_rebuild(tmp_path, monkeypatch):
    from app import web
    mod = _module()
    out = tmp_path / "allocator"
    out.mkdir()
    (out / "2026-09-17.json").write_text("{not-json")
    monkeypatch.setattr(mod, "_OUT_DIR", out)
    called = {"n": 0}

    def build():
        called["n"] += 1
        return {"advisory_only": True, "computed": True}

    monkeypatch.setattr(mod, "build_latest", build)
    response = _route(web)()
    payload = _body(response)
    assert called["n"] == 0
    assert payload == {
        "advisory_only": True,
        "computed": False,
        "read_status": "unavailable",
        "error": "firm_allocator_artifact_unavailable",
        "reason": "firm allocator artifact unavailable",
    }


def test_endpoint_absent_latest_builds_and_returns_success(tmp_path, monkeypatch):
    from app import web
    mod = _module()
    monkeypatch.setattr(mod, "_OUT_DIR", tmp_path / "allocator")
    expected = {"advisory_only": True, "computed": True, "asof": "2026-09-17", "books": {}, "firm": {}}
    monkeypatch.setattr(mod, "build_latest", lambda: expected)
    assert _body(_route(web)()) == expected


def test_endpoint_failed_build_maps_to_closed_unavailable(monkeypatch):
    from app import web
    mod = _module()
    monkeypatch.setattr(mod, "latest_artifact_checked", lambda: ("absent", None), raising=False)
    monkeypatch.setattr(mod, "latest_artifact", lambda: None)
    monkeypatch.setattr(mod, "build_latest", lambda: {
        "advisory_only": True,
        "computed": False,
        "build_status": "unavailable",
        "error": "firm_allocator_build_unavailable",
        "reason": "firm allocator unavailable",
    })
    payload = _body(_route(web)())
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "firm_allocator_build_unavailable"
    assert payload["reason"] == "firm allocator unavailable"


def test_endpoint_outer_failure_is_secret_safe(monkeypatch):
    from app import web
    mod = _module()

    def boom():
        raise RuntimeError("secret /Users/private/allocator token=bad")

    monkeypatch.setattr(mod, "latest_artifact_checked", boom, raising=False)
    monkeypatch.setattr(mod, "latest_artifact", boom)
    response = _route(web)()
    payload = _body(response)
    assert payload == {
        "advisory_only": True,
        "computed": False,
        "read_status": "unavailable",
        "error": "firm_allocator_unavailable",
        "reason": "firm allocator unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw

def _unavailable_artifact():
    return {
        "advisory_only": True, "computed": False, "read_status": "unavailable",
        "error": "firm_allocator_artifact_unavailable",
        "reason": "firm allocator artifact unavailable",
    }


@pytest.mark.parametrize("case", [
    "dangling", "file", "unreadable_listing", "failed_absence_stat", "partial_listing",
])
def test_unavailable_output_location_never_rebuilds(tmp_path, monkeypatch, case):
    from app import web
    out = FA._OUT_DIR
    if case == "dangling":
        out.symlink_to(tmp_path / "absent-target", target_is_directory=True)
    elif case == "file":
        out.write_text("not a directory")
    elif case in ("unreadable_listing", "partial_listing"):
        out.mkdir()
        saved = out / "2026-11-06.json"
        saved.write_text('{"advisory_only":true,"asof":"2026-11-06"}')
        iterdir, glob = Path.iterdir, Path.glob
        def unreadable(path, *args, **kwargs):
            if path == out:
                if case == "partial_listing":
                    def interrupted():
                        yield saved
                        raise PermissionError("private enumeration token=hidden")
                    return interrupted()
                raise PermissionError("private enumeration token=hidden")
            return iterdir(path, *args, **kwargs)
        def unreadable_glob(path, *args, **kwargs):
            if path == out:
                return unreadable(path)
            return glob(path, *args, **kwargs)
        monkeypatch.setattr(Path, "iterdir", unreadable)
        monkeypatch.setattr(Path, "glob", unreadable_glob)
    else:
        lstat = Path.lstat
        def denied_stat(path, *args, **kwargs):
            if path == out:
                raise PermissionError("private stat token=hidden")
            return lstat(path, *args, **kwargs)
        monkeypatch.setattr(Path, "lstat", denied_stat)
    calls = []
    monkeypatch.setattr(FA, "build_latest", lambda: calls.append("build") or {"advisory_only": True})
    response = web.api_firm_allocator()
    assert calls == []
    assert _body(response) == _unavailable_artifact()
    assert "private" not in response.body.decode() and "token=" not in response.body.decode()


@pytest.mark.parametrize("case", ["corrupt", "wrong_shape", "unreadable", "vanished", "directory", "dangling"])
def test_selected_latest_failure_never_falls_back_or_rebuilds(tmp_path, monkeypatch, case):
    from app import web
    out = FA._OUT_DIR
    out.mkdir()
    older = out / "2026-11-06.json"
    older.write_text('{"advisory_only":true,"asof":"2026-11-06"}')
    before = older.read_bytes()
    selected = out / "2026-11-07.json"
    if case == "directory":
        selected.mkdir()
    elif case == "dangling":
        selected.symlink_to(tmp_path / "absent-target")
    else:
        selected.write_text("{bad" if case == "corrupt" else "[]" if case == "wrong_shape"
                            else '{"advisory_only":true,"asof":"2026-11-07"}')
    if case in ("unreadable", "vanished"):
        read = Path.read_text
        def fail_read(path, *args, **kwargs):
            if path == selected:
                error = PermissionError if case == "unreadable" else FileNotFoundError
                raise error("private selected artifact")
            return read(path, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", fail_read)
    calls = []
    monkeypatch.setattr(FA, "build_latest", lambda: calls.append("build") or {"advisory_only": True})
    assert _body(web.api_firm_allocator()) == _unavailable_artifact()
    assert calls == []
    assert older.read_bytes() == before


def test_actual_enumeration_precedes_exists_or_glob_preflight(monkeypatch):
    from app import web
    out = FA._OUT_DIR
    out.mkdir()
    artifact = {"advisory_only": True, "asof": "2026-11-07"}
    (out / "2026-11-07.json").write_text(json.dumps(artifact))
    exists, glob = Path.exists, Path.glob
    def fail_exists(path):
        if path == out:
            raise PermissionError("preflight must not substitute for the observed read")
        return exists(path)
    def fail_glob(path, *args, **kwargs):
        if path == out:
            raise PermissionError("glob must not suppress directory read errors")
        return glob(path, *args, **kwargs)
    monkeypatch.setattr(Path, "exists", fail_exists)
    monkeypatch.setattr(Path, "glob", fail_glob)
    calls = []
    monkeypatch.setattr(FA, "build_latest", lambda: calls.append("build") or {"advisory_only": True})
    assert _body(web.api_firm_allocator()) == artifact
    assert calls == []


@pytest.mark.parametrize("case", ["empty", "text_only"])
def test_genuine_empty_directory_keeps_existing_build_path(monkeypatch, case):
    from app import web
    out = FA._OUT_DIR
    out.mkdir()
    if case == "text_only":
        (out / "notes.txt").write_text("not an allocator artifact")
    calls = []
    expected = {"advisory_only": True, "computed": True, "books": {}, "firm": {}}
    monkeypatch.setattr(FA, "build_latest", lambda: calls.append("build") or expected)
    assert _body(web.api_firm_allocator()) == expected
    assert calls == ["build"]


@pytest.mark.parametrize("artifact", [{}, {"advisory_only": True, "asof": "2026-11-07"}])
def test_legacy_wrapper_preserves_valid_minimal_mapping(artifact):
    out = FA._OUT_DIR
    out.mkdir()
    (out / "2026-11-07.json").write_text(json.dumps(artifact))
    assert FA.latest_artifact() == artifact


@pytest.mark.parametrize("case", ["success", "partial_write_error"])
def test_actual_persist_reports_write_completion_without_claiming_unchanged_bytes(monkeypatch, case):
    out = FA._OUT_DIR
    artifact = {"advisory_only": True, "asof": "2026-11-07", "books": {"autonomous": {"shadow_weight": 1.0}}}
    target = out / "2026-11-07.json"
    if case == "partial_write_error":
        write = Path.write_text
        def partial_write(path, data, *args, **kwargs):
            if path == target:
                write(path, "{partial", *args, **kwargs)
                raise OSError("private disk token=hidden")
            return write(path, data, *args, **kwargs)
        monkeypatch.setattr(Path, "write_text", partial_write)
    result = FA._persist(artifact)
    if case == "success":
        assert result is True
        assert json.loads(target.read_text()) == artifact
    else:
        assert result is False
        assert target.read_text() == "{partial"


@pytest.mark.parametrize("failure", ["mkdir", "write"])
def test_actual_persistence_failure_reaches_route_as_partial(monkeypatch, failure):
    from app import web
    out = FA._OUT_DIR
    if failure == "mkdir":
        out.write_text("not a directory")
    else:
        write = Path.write_text
        def denied_write(path, *args, **kwargs):
            if path.parent == out:
                raise OSError("private persistence token=hidden")
            return write(path, *args, **kwargs)
        monkeypatch.setattr(Path, "write_text", denied_write)
    response = web.api_firm_allocator(rebuild=True)
    payload = _body(response)
    assert payload["advisory_only"] is True
    assert payload["computed"] is True
    assert payload["read_status"] == "partial"
    assert payload["persist_status"] == "unavailable"
    assert payload["books"] and payload["firm"]
    assert payload["error"] == "firm_allocator_persist_unavailable"
    assert "private" not in response.body.decode() and "token=" not in response.body.decode()


def test_actual_asgi_corrupt_read_preserves_artifact_without_implicit_build(monkeypatch):
    from app import web
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    out = FA._OUT_DIR
    out.mkdir()
    path = out / "2026-11-07.json"
    path.write_text('{"private":"token=hidden", broken')
    before = path.read_bytes()
    calls = []
    monkeypatch.setattr(FA, "build_latest", lambda: calls.append("build") or {"advisory_only": True})
    app = FastAPI()
    app.include_router(web.router)
    with TestClient(app) as client:
        response = client.get("/api/firm_allocator")
    assert response.status_code == 200
    assert response.json() == _unavailable_artifact()
    assert calls == [] and path.read_bytes() == before


def test_actual_asgi_explicit_rebuild_replaces_corrupt_artifact():
    from app import web
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    out = FA._OUT_DIR
    out.mkdir()
    path = out / (FA.date.today().isoformat() + ".json")
    path.write_text("{bad-json")
    app = FastAPI()
    app.include_router(web.router)
    with TestClient(app) as client:
        response = client.get("/api/firm_allocator", params={"rebuild": "true"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["advisory_only"] is True
    assert payload["books"] and payload["firm"]
    assert "error" not in payload
    assert json.loads(path.read_text()) == payload
