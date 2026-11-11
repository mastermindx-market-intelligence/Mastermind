"""Readiness and experiment-registry outages stay distinct from legitimate empty state."""
from __future__ import annotations

import json
import asyncio
from copy import deepcopy
from pathlib import Path

import pytest



@pytest.fixture(autouse=True)
def registry_case(tmp_path, monkeypatch):
    from brain import experiment_registry as registry

    path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "_REGISTRY_PATH", path)
    writer_calls = []

    def safe_maturity_stub(*_args, **_kwargs):
        writer_calls.append("matured")
        return []

    def forbidden_save(*_args, **_kwargs):
        pytest.fail("read qualification must not save the experiment registry")

    monkeypatch.setattr(registry, "matured", safe_maturity_stub)
    monkeypatch.setattr(registry, "_save", forbidden_save)
    return registry, path, writer_calls


def _unavailable():
    return {
        "read_status": "unavailable", "as_of": None, "total": None,
        "open": None, "matured": None, "judged": None, "cancelled": None,
        "matured_items": None, "all_items": None, "open_tristate": None,
        "error": "experiment_registry_unavailable",
    }


def _read_registry_response():
    from app import web
    response = web.api_desk_experiments()
    assert response.status_code == 200
    return response, _body(response)


def _body(resp):
    return json.loads(resp.body)


def _boom(*_args, **_kwargs):
    raise RuntimeError("secret /Users/private/governance token=bad")


def test_readiness_successful_empty_state_remains_successful(monkeypatch):
    from app import web
    from portfolio import readiness

    monkeypatch.setattr(readiness, "status", lambda: {})
    monkeypatch.setattr(readiness, "alerts", lambda: [])
    payload = _body(web.api_readiness())
    assert payload == {"status": {}, "alerts": []}


def test_readiness_failure_is_unavailable_not_empty(monkeypatch):
    from app import web
    from portfolio import readiness

    monkeypatch.setattr(readiness, "status", _boom)
    response = web.api_readiness()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "status": None,
        "alerts": None,
        "error": "readiness_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def test_experiment_registry_successful_zero_state_remains_zero(monkeypatch):
    from app import web
    from brain import experiment_registry

    monkeypatch.setattr(experiment_registry, "summary", lambda **_kwargs: {
        "as_of": "2026-09-17", "total": 0, "open": 0, "matured": 0,
        "judged": 0, "cancelled": 0, "matured_items": [], "open_tristate": [],
    })
    monkeypatch.setattr(experiment_registry, "load", lambda **_kwargs: [])
    payload = _body(web.api_desk_experiments())
    assert payload["total"] == 0
    assert payload["all_items"] == []
    assert "read_status" not in payload
    assert "error" not in payload


def test_experiment_registry_failure_is_unavailable_not_zero(monkeypatch):
    from app import web
    from brain import experiment_registry

    monkeypatch.setattr(experiment_registry, "summary", _boom)
    response = web.api_desk_experiments()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "as_of": None,
        "total": None,
        "open": None,
        "matured": None,
        "judged": None,
        "cancelled": None,
        "matured_items": None,
        "all_items": None,
        "open_tristate": None,
        "error": "experiment_registry_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


@pytest.mark.parametrize("raw", [
    b"{broken", b"\xff", b"{}", b"null", b'{"experiments": null}',
    b'{"experiments": {}}', b"[null]", b'[{"id": ""}]',
    b'[{"id": "duplicate"}, {"id": "duplicate"}]',
])
def test_actual_registry_invalid_bytes_are_unavailable(registry_case, raw):
    _registry, path, calls = registry_case
    path.write_bytes(raw)
    _response, payload = _read_registry_response()
    assert payload == _unavailable()
    assert path.read_bytes() == raw
    assert calls == []
    assert not path.with_name(path.name + ".lock").exists()


@pytest.mark.parametrize("kind", [
    "missing", "missing_nested", "empty_list", "empty_envelope", "envelope_metadata",
])
def test_actual_registry_genuine_empty_state_stays_zero(registry_case, tmp_path, monkeypatch, kind):
    registry, path, calls = registry_case
    if kind == "missing_nested":
        path = tmp_path / "not_created" / "nested" / "registry.json"
        monkeypatch.setattr(registry, "_REGISTRY_PATH", path)
    elif kind == "empty_list":
        path.write_text("[]")
    elif kind == "empty_envelope":
        path.write_text('{"experiments": []}')
    elif kind == "envelope_metadata":
        path.write_text('{"schema": "v1", "experiments": []}')
    existed = path.exists()
    original = path.read_bytes() if existed else None
    _response, payload = _read_registry_response()
    assert payload["total"] == payload["open"] == payload["matured"] == 0
    assert payload["judged"] == payload["cancelled"] == 0
    assert payload["matured_items"] == payload["open_tristate"] == payload["all_items"] == []
    assert "read_status" not in payload and "error" not in payload
    assert calls == []
    assert path.exists() is existed
    if original is not None:
        assert path.read_bytes() == original
    assert not path.with_name(path.name + ".lock").exists()


@pytest.mark.parametrize("kind", ["dangling_file", "dangling_parent", "not_directory"])
def test_actual_registry_path_failures_do_not_become_empty(registry_case, tmp_path, monkeypatch, kind):
    registry, path, calls = registry_case
    if kind == "dangling_file":
        path.symlink_to(tmp_path / "absent_target")
    elif kind == "dangling_parent":
        parent = tmp_path / "dangling_parent"
        parent.symlink_to(tmp_path / "absent_parent")
        path = parent / "registry.json"
    else:
        parent = tmp_path / "ordinary_file"
        parent.write_text("not a directory")
        path = parent / "registry.json"
    monkeypatch.setattr(registry, "_REGISTRY_PATH", path)
    _response, payload = _read_registry_response()
    assert payload == _unavailable()
    assert calls == []


@pytest.mark.parametrize("error", [PermissionError, OSError, FileNotFoundError])
def test_actual_registry_failed_read_is_not_absence(registry_case, monkeypatch, error):
    _registry, path, calls = registry_case
    path.write_text("[]")
    original = Path.read_bytes

    def failed_read(candidate):
        if candidate == path:
            raise error("secret /Users/private/registry token=bad")
        return original(candidate)

    monkeypatch.setattr(Path, "read_bytes", failed_read)
    response, payload = _read_registry_response()
    assert payload == _unavailable()
    assert "secret" not in response.body.decode()
    assert calls == []


def test_actual_registry_failed_absence_probe_is_unavailable(registry_case, monkeypatch):
    _registry, path, calls = registry_case
    original = Path.lstat

    def failed_probe(candidate):
        if candidate == path:
            raise PermissionError("secret probe")
        return original(candidate)

    monkeypatch.setattr(Path, "lstat", failed_probe)
    _response, payload = _read_registry_response()
    assert payload == _unavailable()
    assert calls == []


def test_actual_registry_snapshot_preserves_counts_statuses_and_tristate(registry_case):
    _registry, path, calls = registry_case
    rows = [
        {"id": "proof-due", "status": "open", "comeback_date": "2000-01-02",
         "artifact_paths": ["proof.json"], "metadata": {"keep": ["original"]}},
        {"id": "proof-matured", "status": "matured", "comeback_date": "2000-01-01"},
        {"id": "proof-future", "status": "open", "comeback_date": "2999-01-01"},
        {"id": "proof-stuck", "status": "open", "_evaluator_first_blocked": "2000-01-01"},
        {"id": "proof-blocked", "status": "open"},
        {"id": "proof-judged", "status": "judged"},
        {"id": "proof-cancelled", "status": "cancelled"},
    ]
    raw = json.dumps({"experiments": rows, "metadata": "retain on disk"}).encode()
    path.write_bytes(raw)
    _response, payload = _read_registry_response()
    assert {key: payload[key] for key in ("total", "open", "matured", "judged", "cancelled")} == {
        "total": 7, "open": 4, "matured": 1, "judged": 1, "cancelled": 1,
    }
    assert [row["id"] for row in payload["all_items"]] == [row["id"] for row in rows]
    for original, observed in zip(rows, payload["all_items"]):
        assert all(observed[key] == value for key, value in original.items())
    assert [(row["id"], row["status"]) for row in payload["matured_items"]] == [
        ("proof-matured", "matured"), ("proof-due", "open"),
    ]
    assert [row["id"] for row in payload["open_tristate"]] == [
        "proof-matured", "proof-due", "proof-stuck", "proof-blocked", "proof-future",
    ]
    assert [row["evaluation"]["state"] for row in payload["open_tristate"]] == [
        "ready_for_review", "ready_for_review", "blocked_missing_evidence",
        "blocked_missing_evidence", "not_old_enough",
    ]
    assert payload["open_tristate"][2]["evaluation"]["stuck"] is True
    assert path.read_bytes() == raw and calls == []
    assert not path.with_name(path.name + ".lock").exists()


def test_due_snapshot_does_not_override_a_mechanical_block(registry_case, monkeypatch):
    registry, path, calls = registry_case
    row = {"id": "proof-controlled", "status": "open", "comeback_date": "2000-01-01"}
    path.write_text(json.dumps([row]))
    evidence = {"state": registry.STATE_BLOCKED, "reason": "evidence still missing",
                "evidence_n": 0, "required_n": 4, "expected_ready_date": None}

    def blocked(_item, _asof):
        return dict(evidence)

    monkeypatch.setitem(registry._EVALUATORS, row["id"], blocked)
    _response, payload = _read_registry_response()
    assert payload["matured"] == 0 and payload["open"] == 1
    assert payload["matured_items"][0]["status"] == "open"
    evaluation = payload["open_tristate"][0]["evaluation"]
    assert all(evaluation[key] == value for key, value in evidence.items())
    assert json.loads(path.read_text()) == [row] and calls == []


def test_actual_api_reads_one_snapshot_for_counts_and_all_items(registry_case, monkeypatch):
    _registry, path, calls = registry_case
    rows = [{"id": "proof-single-read", "status": "judged"}]
    raw = json.dumps(rows).encode()
    path.write_bytes(raw)
    original = Path.read_bytes
    reads = []

    def once(candidate):
        if candidate == path:
            reads.append(candidate)
            if len(reads) > 1:
                raise OSError("a second read must not be needed")
            return raw
        return original(candidate)

    monkeypatch.setattr(Path, "read_bytes", once)
    _response, payload = _read_registry_response()
    assert payload["total"] == payload["judged"] == 1
    assert payload["all_items"][0]["id"] == "proof-single-read"
    assert len(reads) == 1 and calls == []


def test_projection_failure_is_fixed_unavailable(registry_case, monkeypatch, caplog):
    registry, path, calls = registry_case
    path.write_text("[]")
    monkeypatch.setattr(registry, "open_with_tristate", _boom)
    response, payload = _read_registry_response()
    assert payload == _unavailable()
    assert "secret" not in response.body.decode()
    assert "/Users/private" not in caplog.text and "token=bad" not in caplog.text
    assert calls == []


def test_failed_strict_load_never_calls_summary(registry_case, monkeypatch):
    registry, _path, _calls = registry_case
    summary_calls = []

    def summary(**_kwargs):
        summary_calls.append(True)
        return {"total": 0}

    monkeypatch.setattr(registry, "load", _boom)
    monkeypatch.setattr(registry, "summary", summary)
    _response, payload = _read_registry_response()
    assert payload == _unavailable()
    assert summary_calls == []


def test_default_reader_retains_tolerant_compatibility(registry_case):
    registry, path, calls = registry_case
    raw = b"{broken"
    path.write_bytes(raw)
    assert registry.load() == []
    assert path.read_bytes() == raw and calls == []


def test_default_summary_retains_existing_dispatch_and_shape(registry_case, monkeypatch):
    registry, _path, calls = registry_case
    rows = [{"id": "default-one", "status": "open"}]
    sentinel = [{"id": "default-one", "evaluation": {"state": "blocked_missing_evidence"}}]
    monkeypatch.setattr(registry, "load", lambda: deepcopy(rows))
    monkeypatch.setattr(registry, "open_with_tristate", lambda: sentinel)
    payload = registry.summary()
    assert set(payload) == {"as_of", "total", "open", "matured", "judged", "cancelled",
                            "matured_items", "open_tristate"}
    assert payload["total"] == payload["open"] == 1 and payload["matured"] == 0
    assert payload["matured_items"] == [] and payload["open_tristate"] is sentinel
    assert calls == ["matured"]


def test_default_tristate_reader_retains_fail_soft_compatibility(registry_case, monkeypatch):
    registry, _path, calls = registry_case
    monkeypatch.setattr(registry, "load", _boom)
    assert registry.open_with_tristate() == []
    assert calls == []


@pytest.mark.parametrize("kind", ["empty", "corrupt"])
def test_registered_experiment_route_preserves_http_and_availability(registry_case, kind):
    import httpx
    from fastapi import FastAPI
    from app import web

    _registry, path, calls = registry_case
    path.write_text("[]" if kind == "empty" else "{broken")
    app = FastAPI()
    app.include_router(web.router)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://qualification.invalid") as client:
            return await client.get("/api/desk/experiments")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    if kind == "empty":
        assert payload["total"] == 0 and payload["all_items"] == []
        assert "read_status" not in payload
    else:
        assert payload == _unavailable()
    assert calls == []
