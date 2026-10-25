"""Same-owner action dispatch with synthetic grants and inert providers."""
import asyncio
import copy
import json
import threading
from types import SimpleNamespace

import pytest

from common import workspace_control_room_action_contract as wire
from control_plane import surface_bindings as sb
from control_plane.workspace_control_room_actions import ExistingControlRoomActions
from control_plane.workspace_control_room_lifecycle import HostedControlRoom
from control_plane.workspace_read_service import ExistingControlRoomCache
from integrations.mastermind_workspace_app.contract import (
    workspace_authorizers, workspace_control_room_authorizers,
)
from scripts import chairman_control_room as publisher
from tests.test_control_room_binding_transactions import FIRST, binding, config, save
from tests.test_control_room_refresh_publication import compiler_fixture, document
from tests.test_workspace_control_room_action_grants import compile_source
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_control_room_action_contract import payload


def owner_fixture(cfg):
    policy, _, _, bindings = compile_source()
    load = lambda: bindings
    authorize = workspace_authorizers(policy=policy, load_bindings=load)[1]
    action_owners = {
        action: workspace_control_room_authorizers(policy=policy, load_bindings=load, action=action)[1]
        for action in wire.OPERATIONS
    }
    # Explicitly inert fixture room: exact HostedControlRoom class identity
    # over this fixture's config, but no protected-constructor custody, no
    # listener, and never started — the action unit layer makes no installed
    # lifecycle claim here. The inert server record supplies only the exact
    # config field read by current_owner(); it is not a serving thread or
    # custody proof. Retirement still uses the room's own stop gate.
    hosted = HostedControlRoom.__new__(HostedControlRoom)
    hosted.config = cfg
    hosted.shutdown_timeout = 10.0
    hosted._server = SimpleNamespace(config=cfg)
    hosted._server_thread = None
    hosted._refresh_thread = None
    hosted._stop = threading.Event()
    clock = [100]
    service = ExistingControlRoomActions(
        hosted, authorize=authorize, authorize_actions=action_owners,
        now=lambda: clock[0],
    )
    frame = {"schema": wire.FRAME_SCHEMA, "operation": "open",
             "principal": principal(bindings), "admission_expires_at": 200,
             "payload": {"binding_id": FIRST}}
    return service, hosted, bindings, clock, frame


def call(service, frame, *, ready=lambda: True):
    response = asyncio.run(service.handle_frame(frame, host_ready=ready))
    assert set(response) == {"ok", "result"} and response["ok"] is True
    return wire.validate_result(response["result"], operation=frame["operation"])


@pytest.mark.parametrize("operation", ["open", "bind", "unbind", "refresh-builds"])
def test_only_an_explicit_current_grant_can_reach_an_operation(tmp_path, monkeypatch, operation):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    service, _, bindings, _, request = owner_fixture(cfg)
    request["operation"], request["payload"] = operation, payload(operation)
    bindings["profiles"]["member-0"]["control_room_actions"][operation] = None
    before = cfg.bindings_path.read_bytes()
    monkeypatch.setattr(publisher, "open_surface", lambda *a, **k: pytest.fail("refused operation called"))
    monkeypatch.setattr(publisher, "bind_surface", lambda *a, **k: pytest.fail("refused operation called"))
    monkeypatch.setattr(publisher, "unbind_surface", lambda *a, **k: pytest.fail("refused operation called"))
    monkeypatch.setattr(publisher, "refresh_builds", lambda *a, **k: pytest.fail("refused operation called"))
    result = call(service, request)
    assert result["status"] == 403 and result["disposition"] == "NOT_DISPATCHED"
    assert cfg.bindings_path.read_bytes() == before


@pytest.mark.parametrize("state", ["inactive", "stopping", "host_not_ready", "missing_host_guard"])
def test_an_unstarted_or_retired_owner_never_becomes_an_action_owner(tmp_path, state):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    service, hosted, _, _, request = owner_fixture(cfg)
    cfg.open_binding_fn = lambda *a, **k: pytest.fail("unavailable owner reached provider")
    ready = lambda: True
    if state == "inactive": hosted._stop.set()  # retired room gate: no live owner
    elif state == "stopping": cfg.state_stopping = True
    elif state == "host_not_ready": ready = lambda: False
    else: ready = None
    result = call(service, request, ready=ready)
    assert result["status"] == 503 and result["disposition"] == "NOT_DISPATCHED"


def test_refresh_repairs_stale_error_cache_on_the_same_existing_owner(tmp_path, monkeypatch):
    cfg, snapshot = compiler_fixture(
        tmp_path, monkeypatch,
        source=lambda now, *, active_builds_snapshot: document(active_builds_snapshot),
    )
    cfg.state_cache["doc"] = document({"previous": True})
    cfg.state_cache["composed_monotonic"] = -1000
    cfg.state_refresh_error = "fixture stale presentation"
    service, _, _, _, request = owner_fixture(cfg)
    request["operation"], request["payload"] = "refresh-builds", {}
    cache, live = cfg.state_cache, cfg.live_cache
    monkeypatch.setattr(
        ExistingControlRoomCache, "snapshot",
        lambda *a: pytest.fail("action required a fresh READ snapshot"),
    )
    result = call(service, request)
    assert result["status"] == 200 and result["disposition"] == "OWNER_RETURNED"
    assert result["outcome"] == {"ok": True, "collected_at": snapshot["collected_at"]}
    assert cfg.state_cache is cache and cfg.live_cache is live
    assert live["active_builds"] == snapshot and cfg.state_published_seq == 1


@pytest.mark.parametrize("movement,status", [
    ("owner", 503), ("instance", 503), ("stopping", 503),
    ("grant", 403), ("expiry", 403), ("host_ready", 503),
])
def test_actual_effect_guard_refuses_changes_during_the_binding_read(
    tmp_path, monkeypatch, movement, status,
):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    service, hosted, bindings, clock, request = owner_fixture(cfg)
    ready = [True]
    before = cfg.bindings_path.read_bytes()
    read = sb.load_bindings
    calls = []
    cfg.open_binding_fn = lambda *a, **k: calls.append(a) or {"ok": True, "verified": True}

    def changed(path):
        result = read(path)
        if movement == "owner": hosted._server.config = config(tmp_path / "replacement")
        elif movement == "instance": cfg._workspace_read_instance = "f" * 64
        elif movement == "stopping": cfg.state_stopping = True
        elif movement == "grant": bindings["profiles"]["member-0"]["control_room_actions"]["open"] = None
        elif movement == "expiry": clock[0] = 200
        else: ready[0] = False
        return result

    monkeypatch.setattr(sb, "load_bindings", changed)
    result = call(service, request, ready=lambda: ready[0])
    assert result["status"] == status and result["disposition"] == "NOT_DISPATCHED"
    assert calls == [] and cfg.bindings_path.read_bytes() == before


@pytest.mark.parametrize("operation", ["bind", "unbind"])
def test_authorized_binding_actions_use_the_existing_transaction_owner(tmp_path, operation):
    cfg = config(tmp_path)
    original = binding(FIRST)
    save(cfg, [original])
    service, _, _, _, request = owner_fixture(cfg)
    request["operation"], request["payload"] = operation, payload(operation)
    result = call(service, request)
    assert result["status"] == 200 and result["disposition"] == "OWNER_RETURNED"
    assert result["outcome"]["ok"] is True
    doc, problems = sb.load_bindings(cfg.bindings_path)
    assert not problems and len(doc["bindings"]) == (2 if operation == "bind" else 0)


@pytest.mark.parametrize("movement", ["expiry", "revocation", "stopping"])
def test_admitted_owner_outcome_survives_later_admission_changes(tmp_path, movement):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    service, _, bindings, clock, request = owner_fixture(cfg)
    calls = []

    def provider(*args, **kwargs):
        calls.append(True)
        if movement == "expiry": clock[0] = 200
        elif movement == "revocation": bindings["profiles"]["member-0"]["control_room_actions"]["open"] = None
        else: cfg.state_stopping = True
        return {"ok": True, "verified": True, "detail": "fixture completed"}

    cfg.open_binding_fn = provider
    result = call(service, request)
    assert result["status"] == 200 and result["disposition"] == "OWNER_RETURNED"
    assert result["outcome"] == {"ok": True, "verified": True, "detail": "fixture completed"}
    assert calls == [True]


@pytest.mark.parametrize("failure", ["exception", "oversize", "malformed"])
def test_uncertain_dispatched_result_never_becomes_a_pre_dispatch_refusal(tmp_path, failure):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    service, _, _, _, request = owner_fixture(cfg)
    calls = []

    def provider(*args, **kwargs):
        calls.append(True)
        if failure == "exception": raise ValueError("/fixture/private provider may have acted")
        if failure == "malformed": return []
        return {"ok": True, "detail": "x" * wire.MAX_RESPONSE_BYTES}

    cfg.open_binding_fn = provider
    result = call(service, request)
    assert result == wire.unknown_result("open") and calls == [True]
    assert "/fixture/private" not in json.dumps(result)


def test_provider_failure_text_is_still_an_owner_returned_outcome(tmp_path):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    service, _, _, _, request = owner_fixture(cfg)
    cfg.open_binding_fn = lambda *a, **k: {
        "ok": False, "verified": False, "failure_kind": "source_precondition_failed",
    }
    result = call(service, request)
    assert result["status"] == 200 and result["disposition"] == "OWNER_RETURNED"
    assert result["outcome"]["failure_kind"] == "source_precondition_failed"


def test_owed_no_provider_refusal_remains_known_after_permission_admission(tmp_path, monkeypatch):
    from tests.test_chairman_control_room_server import (
        _b5_navigation_fixture, _b5_owed_request, _b5_sample,
    )
    cfg, source_clock, _ = _b5_navigation_fixture(tmp_path, monkeypatch)
    publisher._refresh_state_cache(
        cfg, timeout=240, generation=publisher._reserve_composition(cfg),
        include_capabilities=False,
    )
    snapshot = publisher._cached_state_snapshot(cfg)
    owed = _b5_owed_request({
        "control_room": snapshot["doc"], "source_validity": snapshot["source_validity"],
    })
    service, _, _, _, request = owner_fixture(cfg)
    request["payload"] = owed
    checks, calls = [], []

    def clock():
        checks.append(True)
        if len(checks) == 2:
            source_clock[:] = _b5_sample(1984)
        return 100

    service._now = clock
    cfg.open_binding_fn = lambda *a, **k: calls.append(a)
    result = call(service, request)
    assert result["status"] == 409 and result["disposition"] == "NOT_DISPATCHED"
    assert result["outcome"]["failure_kind"] == "source_precondition_failed"
    assert len(checks) >= 2 and calls == []


def test_repeated_cancellation_retains_the_owned_operation_until_it_finishes(tmp_path):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    service, hosted, _, _, request = owner_fixture(cfg)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def provider(*args, **kwargs):
        calls.append(True)
        entered.set()
        assert release.wait(3), "fixture failed to release owned provider"
        finished.set()
        return {"ok": True, "verified": True}

    cfg.open_binding_fn = provider

    async def scenario():
        task = asyncio.create_task(service.handle_frame(request, host_ready=lambda: True))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and not finished.is_set()
            assert hosted.current_owner() is cfg
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set() and calls == [True]

    asyncio.run(scenario())


def factory_fixture(tmp_path, **options):
    from control_plane.workspace_read_service import workspace_provider_factory
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    seed, hosted, bindings, clock, request = owner_fixture(cfg)
    defaults = dict(
        control_room=hosted, authorize=seed._authorize,
        armed={"ceo_submit_armed": False}, runtime_identity={},
    )
    if options.pop("enable_actions", True):
        defaults.update(
            authorize_actions=dict(seed._authorize_actions), action_now=lambda: clock[0],
        )
    defaults.update(options)
    return workspace_provider_factory(**defaults), cfg, bindings, request


def test_factory_action_branch_retains_the_same_owner_and_admitted_outcome(tmp_path):
    provide, cfg, bindings, request = factory_fixture(tmp_path)
    calls = []

    def provider(*args, **kwargs):
        calls.append(True)
        bindings["profiles"]["member-0"]["control_room_actions"]["open"] = None
        return {"ok": True, "verified": True}

    cfg.open_binding_fn = provider
    first, second = provide(object()), provide(object())
    assert first.cache is second.cache
    assert first._control_room_actions is second._control_room_actions
    response = asyncio.run(first.handle_frame(request, action_host_ready=lambda: True))
    assert response["result"]["disposition"] == "OWNER_RETURNED"
    assert response["result"]["outcome"]["ok"] is True and calls == [True]
    refused = asyncio.run(second.handle_frame(request, action_host_ready=lambda: True))
    assert refused["result"]["status"] == 403 and calls == [True]


@pytest.mark.parametrize("enabled", [False, True])
def test_factory_actions_remain_unavailable_without_the_outer_host_guard(tmp_path, enabled):
    provide, cfg, _, request = factory_fixture(tmp_path, enable_actions=enabled)
    cfg.open_binding_fn = lambda *a, **k: pytest.fail("no host admission")
    response = asyncio.run(provide(object()).handle_frame(request))
    assert response == {
        "ok": True,
        "result": wire.refused_result("open", code="source_unavailable", status=503),
    }


def test_factory_action_names_cannot_enter_the_read_frame_path(tmp_path):
    from common.workspace_control_room_read_contract import FRAME_SCHEMA
    provide, cfg, _, request = factory_fixture(tmp_path)
    cfg.open_binding_fn = lambda *a, **k: pytest.fail("READ cannot act")
    read = {"schema": FRAME_SCHEMA, "operation": "open", "principal": request["principal"]}
    response = asyncio.run(provide(object()).handle_frame(read))
    assert response["ok"] is False and response["status"] == 400


@pytest.mark.parametrize("operation", ["open", "bind", "unbind"])
@pytest.mark.parametrize("path", [None, "absolute_string", "relative_path"])
def test_binding_actions_require_the_explicit_incumbent_store(tmp_path, monkeypatch, operation, path):
    from pathlib import Path
    cfg = config(tmp_path)
    service, _, _, _, request = owner_fixture(cfg)
    cfg.bindings_path = (str(tmp_path / "unselected.json") if path == "absolute_string"
                         else Path("unselected.json") if path == "relative_path" else None)
    request["operation"], request["payload"] = operation, payload(operation)
    monkeypatch.setattr(sb, "load_bindings", lambda *a: pytest.fail("no selected binding store"))
    monkeypatch.setattr(sb, "save_bindings", lambda *a: pytest.fail("no selected binding store"))
    cfg.open_binding_fn = lambda *a, **k: pytest.fail("no selected binding store")
    result = call(service, request)
    assert result == wire.refused_result(operation, code="source_unavailable", status=503)


@pytest.mark.parametrize("operation", ["open", "bind", "unbind"])
def test_store_movement_during_read_refuses_before_provider_or_write(tmp_path, monkeypatch, operation):
    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    original_path, original_bytes = cfg.bindings_path, cfg.bindings_path.read_bytes()
    service, _, _, _, request = owner_fixture(cfg)
    request["operation"], request["payload"] = operation, payload(operation)
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(original_bytes)
    original_read = sb.load_bindings
    def read(path):
        value = original_read(path)
        cfg.bindings_path = replacement
        return value
    monkeypatch.setattr(sb, "load_bindings", read)
    monkeypatch.setattr(sb, "save_bindings", lambda *a: pytest.fail("store moved before effect"))
    cfg.open_binding_fn = lambda *a, **k: pytest.fail("store moved before provider")
    result = call(service, request)
    assert result == wire.refused_result(operation, code="source_unavailable", status=503)
    assert original_path.read_bytes() == replacement.read_bytes() == original_bytes
