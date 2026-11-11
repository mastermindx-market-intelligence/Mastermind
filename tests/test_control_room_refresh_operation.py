"""Refresh owner calls use the incumbent config without an HTTP transport."""
import json
import sys

import pytest

from scripts import chairman_control_room as publisher
from tests.test_control_room_refresh_publication import (
    compiler_fixture, config, document, handler,
)


def test_refresh_operation_publishes_to_the_existing_owner_without_http(tmp_path, monkeypatch):
    cfg, snapshot = compiler_fixture(
        tmp_path, monkeypatch,
        source=lambda now, *, active_builds_snapshot: document(active_builds_snapshot),
    )
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return {"code": 0, "timed_out": False, "stdout": json.dumps(snapshot), "stderr": ""}

    cfg.runner = runner
    monkeypatch.setattr(
        publisher, "ControlRoomServer",
        lambda *args, **kwargs: pytest.fail("refresh must not create an HTTP server"),
    )
    cache, live = cfg.state_cache, cfg.live_cache

    result = publisher.refresh_builds(cfg)

    assert result == {"ok": True, "collected_at": snapshot["collected_at"]}
    assert cfg.state_cache is cache and cfg.live_cache is live
    assert cache["doc"]["fixture_active_builds"] == snapshot
    assert live["active_builds"] == snapshot
    assert cfg.state_published_seq == cfg.state_explicit_floor == 1
    assert cfg.state_refreshes_in_flight == 0
    assert calls == [(
        [sys.executable, str(tmp_path / "macro/scripts/build_project_active_build_map.py"),
         "--json-stdout"],
        {"timeout": 180.0, "cwd": str(tmp_path / "macro"), "max_bytes": 4 * 1024 * 1024},
    )]


@pytest.mark.parametrize("missing", ["root", "script"])
def test_missing_macro_input_never_runs_or_reserves(tmp_path, missing):
    cfg = config(tmp_path)
    if missing == "script":
        cfg.macro_root = str(tmp_path)
    cfg.runner = lambda *args, **kwargs: pytest.fail("no compiler input")

    result = publisher.refresh_builds(cfg)

    assert result["ok"] is False
    assert result["detail"] == (
        "no macro root resolved" if missing == "root"
        else "--json-stdout seam not present at macro root"
    )
    assert cfg.live_cache == cfg.state_cache == {}
    assert cfg.state_compose_seq == cfg.state_refreshes_in_flight == 0


@pytest.mark.parametrize("compiler_result,detail", [
    (None, "build_project_active_build_map.py failed"),
    ({"code": 1, "stderr": "fixture failure"}, "build_project_active_build_map.py failed: fixture failure"),
    ({"code": 0, "timed_out": True}, "build_project_active_build_map.py failed"),
    ({"code": 0, "stdout": "invalid"}, "stdout was not valid JSON"),
    ({"code": 0, "stdout": "[]"}, "stdout schema was not project_active_builds.v1"),
    ({"code": 0, "stdout": '{"schema":"other"}'}, "stdout schema was not project_active_builds.v1"),
])
def test_rejected_compiler_output_preserves_the_existing_publication(
    tmp_path, monkeypatch, compiler_result, detail,
):
    cfg, _ = compiler_fixture(
        tmp_path, monkeypatch, runner=lambda *args, **kwargs: compiler_result,
        source=lambda *args, **kwargs: pytest.fail("invalid compiler input reached composer"),
    )
    old = document({"previous": True})
    cfg.state_cache["doc"] = old

    result = publisher.refresh_builds(cfg)

    assert result == {"ok": False, "detail": detail}
    assert cfg.state_cache["doc"] is old
    assert cfg.live_cache == {}
    assert cfg.state_compose_seq == cfg.state_refreshes_in_flight == 0


def test_publication_failure_remains_a_retained_input_not_a_no_effect_claim(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("fixture source unavailable")

    cfg, snapshot = compiler_fixture(tmp_path, monkeypatch, source=unavailable)
    old = document({"previous": True})
    cfg.state_cache["doc"] = old

    result = publisher.refresh_builds(cfg)

    assert result == {"ok": False, "detail": "refreshed builds were not published by this request"}
    assert cfg.state_cache["doc"] is old
    assert cfg.live_cache["active_builds"] == snapshot
    assert cfg.state_published_seq == 0 and cfg.state_explicit_floor == 1
    assert cfg.state_refreshes_in_flight == 0


def test_legacy_handler_delegates_once_to_the_same_refresh_owner(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    request, _ = handler(cfg)
    calls, replies = [], []
    outcome = {"ok": False, "detail": "fixture publication outcome"}

    def refresh(owner):
        calls.append(owner)
        return outcome

    monkeypatch.setattr(publisher, "refresh_builds", refresh)
    request._send_json = lambda status, body, **kwargs: replies.append((status, body, kwargs))

    request._handle_refresh_builds()

    assert calls == [cfg]
    assert replies == [(200, outcome, {"no_store": True})]


@pytest.mark.parametrize("data,error", [({}, "invalid body"), ({"macro_root": "caller"}, None)])
def test_invalid_http_payload_does_not_enter_the_operation(tmp_path, monkeypatch, data, error):
    request, replies = handler(config(tmp_path))
    bad_requests = []
    request._read_json_body = lambda: (data, error)
    request._bad_request = bad_requests.append
    monkeypatch.setattr(
        publisher, "refresh_builds",
        lambda owner: pytest.fail("invalid request reached the operation"),
    )

    request._handle_refresh_builds()

    assert len(bad_requests) == 1
    assert replies == []
