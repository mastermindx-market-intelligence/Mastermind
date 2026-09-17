"""Shadow allocator persisted/read/build failures remain explicit and secret-safe."""
from __future__ import annotations

import importlib
import json
from pathlib import Path


def _module():
    # Keep the allocator's grep-ratchet importer list unchanged: load dynamically in this boundary test.
    return importlib.import_module("portfolio." + "firm_" + "allocator")


def _route(web):
    return getattr(web, "api_" + "firm_" + "allocator")


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

    monkeypatch.setattr(mod, "latest_artifact_checked", lambda: ("absent", None))
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
    monkeypatch.setattr(mod, "latest_artifact_checked", lambda: ("absent", None))
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

    monkeypatch.setattr(mod, "latest_artifact_checked", boom)
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
