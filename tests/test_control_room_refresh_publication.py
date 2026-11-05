"""Fixture-only Refresh/source-publication checks; no host or provider action."""
import copy
import json
import threading
from types import SimpleNamespace

import pytest

from control_plane import chairman_control_room as ccr
from control_plane import workspace_source_join as join
from scripts import chairman_control_room as publisher
from tests.test_workspace_programs_qualification import empty_inputs
from tests.test_workspace_read_service import STAMP


def config(tmp_path, *, source=None):
    return publisher.ServerConfig(
        repo_root=tmp_path, macro_root=None, bindings_path=None,
        token="fixture", origin="http://127.0.0.1:0", port=0,
        now_fn=lambda: STAMP, compose_inputs=source,
    )


def document(snapshot=None):
    return {"schema": ccr.SCHEMA, "generated_at": STAMP,
            "fixture_active_builds": copy.deepcopy(snapshot)}


@pytest.fixture
def installed(tmp_path, monkeypatch):
    inputs = empty_inputs()
    reads = []
    captures = []

    def active_reader(root, *, installed_byte_budget):
        reads.append((root, installed_byte_budget))
        return inputs["active_builds"], None

    monkeypatch.setattr(ccr, "_read_active_builds", active_reader)
    monkeypatch.setattr(
        ccr, "_read_agent_os_state",
        lambda root, **kwargs: (inputs["agent_os_state"], None),
    )
    monkeypatch.setattr(
        join, "_bounded_runtime_inputs", lambda runtime: ([], [], [], {}, [], True),
    )

    def compose(**kwargs):
        captures.append(kwargs["active_builds"])
        return document(kwargs["active_builds"])

    monkeypatch.setattr(ccr, "compose_control_room", compose)
    monkeypatch.setattr(ccr, "build_control_room", lambda **kwargs: pytest.fail("legacy gather"))
    source = join.build_workspace_composer(
        packet_collector=lambda **kwargs: inputs["boot_packet"],
        repo_root=tmp_path, macro_root=tmp_path / "macro",
        bounded_runtime=lambda: object(), bindings_path=None,
    )
    return config(tmp_path, source=source), inputs, reads, captures


@pytest.mark.parametrize("snapshot", [
    None, {"schema": "unavailable-fixture"},
    {"schema": "project_active_builds.v1", "collected_at": STAMP, "builds": []},
])
def test_installed_join_uses_explicit_snapshot_without_artifact_substitution(installed, snapshot):
    cfg, _, reads, captures = installed
    cfg.live_cache["active_builds"] = copy.deepcopy(snapshot)
    result = publisher._compose_state_doc(cfg)
    assert result["fixture_active_builds"] == snapshot
    assert captures == [snapshot]
    assert reads == []


def test_omission_retains_existing_bounded_installed_artifact_reader(installed):
    cfg, inputs, reads, captures = installed
    publisher._compose_state_doc(cfg)
    assert captures == [inputs["active_builds"]]
    assert reads == [(str(cfg.repo_root / "macro"), join.INSTALLED_BYTE_BUDGET)]


def test_configured_composer_receives_detached_snapshot(tmp_path):
    original = {"schema": "project_active_builds.v1", "builds": [{"name": "original"}]}

    def source(now, *, active_builds_snapshot):
        active_builds_snapshot["builds"][0]["name"] = "composer-local"
        return document(active_builds_snapshot)

    cfg = config(tmp_path, source=source)
    cfg.live_cache["active_builds"] = copy.deepcopy(original)
    assert publisher._compose_state_doc(cfg)["fixture_active_builds"]["builds"][0]["name"] == "composer-local"
    assert cfg.live_cache["active_builds"] == original


def compiler_fixture(tmp_path, monkeypatch, *, source=None, runner=None):
    cfg = config(tmp_path, source=source)
    macro = tmp_path / "macro"
    script = macro / "scripts" / "build_project_active_build_map.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fixture path only; never executed\n")
    cfg.macro_root = str(macro)
    snapshot = {"schema": "project_active_builds.v1", "collected_at": "fixture-A", "builds": []}
    cfg.runner = runner or (lambda *args, **kwargs: {
        "code": 0, "timed_out": False, "stdout": json.dumps(snapshot), "stderr": "",
    })
    monkeypatch.setattr(publisher.capability, "census", lambda **kwargs: {})
    return cfg, snapshot


def handler(cfg):
    replies = []
    value = publisher.ChairmanControlRoomHandler.__new__(publisher.ChairmanControlRoomHandler)
    value.server = SimpleNamespace(config=cfg)
    value._read_json_body = lambda: ({}, None)
    value._bad_request = lambda detail: pytest.fail(detail)
    value._send_json = lambda status, body, **kwargs: replies.append((status, body))
    return value, replies


def test_refresh_does_not_report_success_when_composition_failed(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("fixture source unavailable")

    cfg, snapshot = compiler_fixture(tmp_path, monkeypatch, source=unavailable)
    old = document({"previous": True})
    cfg.state_cache["doc"] = old
    cfg.state_compose_seq = cfg.state_published_seq = 1
    request, replies = handler(cfg)
    request._handle_refresh_builds()
    assert replies[0][0] == 200 and replies[0][1]["ok"] is False
    assert cfg.state_cache["doc"] is old
    assert cfg.state_published_seq == 1
    assert cfg.state_refresh_error is not None
    assert cfg.live_cache["active_builds"] == snapshot
    assert cfg.state_refreshes_in_flight == 0


def test_refresh_does_not_report_success_for_a_superseded_generation(tmp_path, monkeypatch):
    cfg, _ = compiler_fixture(tmp_path, monkeypatch)
    newer = {"schema": "project_active_builds.v1", "collected_at": "fixture-B", "builds": []}
    first = [True]

    def compose(now, *, active_builds_snapshot):
        if first[0]:
            first[0] = False
            generation = publisher._reserve_composition(
                cfg, explicit=True, active_builds_snapshot=newer,
            )
            assert publisher._refresh_state_cache(
                cfg, timeout=1, generation=generation, include_capabilities=False,
            ) is True
        return document(active_builds_snapshot)

    cfg.compose_inputs = compose
    request, replies = handler(cfg)
    request._handle_refresh_builds()
    assert replies[0][1]["ok"] is False
    assert cfg.state_cache["doc"]["fixture_active_builds"] == newer
    assert cfg.state_published_seq == cfg.state_explicit_floor == 2
    assert cfg.state_refreshes_in_flight == 0


def test_refresh_snapshot_and_explicit_generation_share_one_reservation(tmp_path, monkeypatch):
    first_waiting, release_first = threading.Event(), threading.Event()
    failures = []

    def runner(*args, **kwargs):
        name = "fixture-A" if threading.current_thread().name == "refresh-A" else "fixture-B"
        snapshot = {"schema": "project_active_builds.v1", "collected_at": name, "builds": []}
        return {"code": 0, "timed_out": False, "stdout": json.dumps(snapshot), "stderr": ""}

    cfg, _ = compiler_fixture(tmp_path, monkeypatch, runner=runner)
    monkeypatch.setattr(
        ccr, "build_control_room",
        lambda **kwargs: document(kwargs.get("active_builds_snapshot")),
    )
    original_reserve = publisher._reserve_composition

    def reserve(owner, **kwargs):
        if threading.current_thread().name == "refresh-A":
            first_waiting.set()
            assert release_first.wait(5)
        return original_reserve(owner, **kwargs)

    monkeypatch.setattr(publisher, "_reserve_composition", reserve)
    request_a, replies_a = handler(cfg)
    request_b, replies_b = handler(cfg)

    def invoke_a():
        try:
            request_a._handle_refresh_builds()
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=invoke_a, name="refresh-A")
    thread.start()
    try:
        assert first_waiting.wait(5)
        request_b._handle_refresh_builds()
    finally:
        release_first.set()
        thread.join(5)
    assert not thread.is_alive() and failures == []
    assert replies_a[0][1] == {"ok": True, "collected_at": "fixture-A"}
    assert replies_b[0][1] == {"ok": True, "collected_at": "fixture-B"}
    assert cfg.state_cache["doc"]["fixture_active_builds"]["collected_at"] == "fixture-A"
    assert cfg.live_cache["active_builds"]["collected_at"] == "fixture-A"
    assert cfg.state_published_seq == cfg.state_explicit_floor == 2
    assert cfg.state_refreshes_in_flight == 0


def test_stopping_owner_never_accepts_snapshot_or_reservation(tmp_path):
    cfg = config(tmp_path)
    cfg.state_stopping = True
    with pytest.raises(RuntimeError, match="owner is stopping"):
        publisher._reserve_composition(
            cfg, explicit=True, active_builds_snapshot={"schema": "project_active_builds.v1"},
        )
    assert cfg.live_cache == {}
    assert cfg.state_compose_seq == cfg.state_refreshes_in_flight == 0

def test_overlapping_refreshes_compose_their_own_snapshot_and_only_newer_publishes(tmp_path, monkeypatch):
    first_waiting, release_first = threading.Event(), threading.Event()
    failures, captured = [], []

    def runner(*args, **kwargs):
        name = "fixture-A" if threading.current_thread().name == "refresh-A" else "fixture-B"
        snapshot = {"schema": "project_active_builds.v1", "collected_at": name, "builds": []}
        return {"code": 0, "timed_out": False, "stdout": json.dumps(snapshot), "stderr": ""}

    cfg, _ = compiler_fixture(tmp_path, monkeypatch, runner=runner)
    monkeypatch.setattr(
        ccr, "build_control_room",
        lambda **kwargs: document(kwargs.get("active_builds_snapshot")),
    )
    original_compose = publisher._compose_state_doc

    def compose(owner, **kwargs):
        is_first = threading.current_thread().name == "refresh-A"
        if is_first:
            first_waiting.set()
            assert release_first.wait(5)
        result = original_compose(owner, **kwargs)
        captured.append(("A" if is_first else "B", result["fixture_active_builds"]["collected_at"]))
        return result

    monkeypatch.setattr(publisher, "_compose_state_doc", compose)
    request_a, replies_a = handler(cfg)
    request_b, replies_b = handler(cfg)

    def invoke_a():
        try:
            request_a._handle_refresh_builds()
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=invoke_a, name="refresh-A")
    thread.start()
    try:
        assert first_waiting.wait(5)
        request_b._handle_refresh_builds()
    finally:
        release_first.set()
        thread.join(5)
    assert not thread.is_alive() and failures == []
    assert replies_a[0][1]["ok"] is False
    assert replies_b[0][1] == {"ok": True, "collected_at": "fixture-B"}
    assert sorted(captured) == [("A", "fixture-A"), ("B", "fixture-B")]
    assert cfg.state_cache["doc"]["fixture_active_builds"]["collected_at"] == "fixture-B"
    assert cfg.live_cache["active_builds"]["collected_at"] == "fixture-B"
    assert cfg.state_published_seq == cfg.state_explicit_floor == 2
    assert cfg.state_refreshes_in_flight == 0

@pytest.mark.parametrize("source_fails", [False, True])
def test_retirement_during_composition_never_publishes_or_reports_success(tmp_path, monkeypatch, source_fails):
    cfg, _ = compiler_fixture(tmp_path, monkeypatch)
    old = document({"previous": True})
    cfg.state_cache["doc"] = old
    cfg.state_compose_seq = cfg.state_published_seq = 1

    def retire(now, *, active_builds_snapshot):
        with cfg.state_lock:
            cfg.state_stopping = True
        if source_fails:
            raise RuntimeError("fixture source retired")
        return document(active_builds_snapshot)

    cfg.compose_inputs = retire
    request, replies = handler(cfg)
    request._handle_refresh_builds()
    assert replies[0][1]["ok"] is False
    assert cfg.state_cache["doc"] is old and cfg.state_published_seq == 1
    assert cfg.state_refresh_error is None
    assert cfg.state_refreshes_in_flight == 0
