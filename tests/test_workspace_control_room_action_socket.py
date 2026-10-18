"""One-send action custody on the existing private Workspace client.

Transport and provider inputs are fixtures. No installed socket or live action.
"""
import asyncio

import pytest

from common import workspace_control_room_action_contract as wire
from common.executive_workspace_contract import canonical
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_workspace_control_room_action_contract import frame


def returned():
    return {"ok": True, "result": wire.action_result(
        "open", {"ok": True, "verified": True}, status=200, disposition="OWNER_RETURNED",
    )}


class Writer:
    def __init__(self, failure=None):
        self.failure, self.writes, self.close_calls = failure, [], 0

    def write(self, raw):
        self.writes.append(raw)
        if self.failure == "write": raise OSError("fixture partial write")

    async def drain(self):
        if self.failure == "drain": raise OSError("fixture drain")

    def close(self):
        self.close_calls += 1
        if self.failure == "close": raise OSError("fixture close")

    async def wait_closed(self):
        if self.failure == "wait_closed": raise OSError("fixture wait_closed")
        if self.failure == "close_timeout": await asyncio.Event().wait()


def transport(monkeypatch, *, raw=None, failure=None, entered=None, release=None):
    writer, connections = Writer(failure), []
    class Reader:
        async def readuntil(self, separator):
            assert separator == b"\n"
            if entered is not None: entered.set()
            if release is not None: await release.wait()
            if failure == "read": raise asyncio.IncompleteReadError(b"partial", None)
            if failure == "timeout": await asyncio.Event().wait()
            return canonical(returned()) + b"\n" if raw is None else raw

    async def connect(path, *, limit):
        connections.append((path, limit))
        if failure == "connect": raise OSError("fixture connect")
        return Reader(), writer

    monkeypatch.setattr(asyncio, "open_unix_connection", connect)
    return writer, connections


@pytest.mark.parametrize("failure", [None, "close", "wait_closed", "close_timeout"])
def test_complete_action_outcome_survives_connection_cleanup(monkeypatch, failure):
    writer, connections = transport(monkeypatch, failure=failure)
    request = frame()
    client = CeoIngressWorkspaceClient("/fixture/app.sock", action_timeout_seconds=.1)
    assert asyncio.run(client.request(request)) == returned()
    assert connections == [("/fixture/app.sock", wire.MAX_RESPONSE_BYTES)]
    assert writer.writes == [canonical(request) + b"\n"] and writer.close_calls == 1


@pytest.mark.parametrize("failure", ["write", "drain", "read", "timeout"])
def test_any_failure_after_write_attempt_is_unknown_and_never_retried(monkeypatch, failure):
    writer, connections = transport(monkeypatch, failure=failure)
    client = CeoIngressWorkspaceClient("/fixture/app.sock", action_timeout_seconds=.1)
    result = asyncio.run(client.request(frame()))
    assert result == {"ok": True, "result": wire.unknown_result("open")}
    assert len(writer.writes) == len(connections) == 1 and writer.close_calls == 1


def test_connection_failure_before_write_is_known_not_dispatched(monkeypatch):
    writer, connections = transport(monkeypatch, failure="connect")
    client = CeoIngressWorkspaceClient("/fixture/app.sock", action_timeout_seconds=.1)
    result = asyncio.run(client.request(frame()))
    assert result == {"ok": True, "result": wire.refused_result(
        "open", code="source_unavailable", status=503,
    )}
    assert len(connections) == 1 and writer.writes == []


@pytest.mark.parametrize("kind", ["malformed", "duplicate", "wrong_operation", "read_error", "oversize"])
def test_unqualified_reply_after_send_cannot_prove_non_dispatch(monkeypatch, kind):
    envelope = returned()
    if kind == "malformed": raw = b"not-json\n"
    elif kind == "duplicate": raw = b'{"ok":false,' + canonical(envelope)[1:] + b"\n"
    elif kind == "wrong_operation":
        envelope["result"]["operation"] = "unbind"
        raw = canonical(envelope) + b"\n"
    elif kind == "read_error":
        raw = canonical({"ok": False, "status": 503,
                         "error": {"code": "source_unavailable", "message": "fixture"}}) + b"\n"
    else: raw = b" " * wire.MAX_RESPONSE_BYTES + b"\n"
    writer, connections = transport(monkeypatch, raw=raw)
    client = CeoIngressWorkspaceClient("/fixture/app.sock", action_timeout_seconds=.1)
    assert asyncio.run(client.request(frame())) == {"ok": True, "result": wire.unknown_result("open")}
    assert len(writer.writes) == len(connections) == 1


def test_invalid_action_frame_never_connects(monkeypatch):
    writer, connections = transport(monkeypatch)
    request = frame()
    request["payload"]["owner"] = "not-a-host-input"
    client = CeoIngressWorkspaceClient("/fixture/app.sock", action_timeout_seconds=.1)
    assert asyncio.run(client.request(request)) == {"ok": True, "result": wire.refused_result(
        "open", code="invalid_input", status=400,
    )}
    assert connections == writer.writes == []


@pytest.mark.parametrize("value", [True, 0, 481, float("inf"), float("nan"), "480"])
def test_action_budget_is_finite_and_does_not_widen_old_read_budgets(value):
    with pytest.raises(ValueError, match="invalid_input"):
        CeoIngressWorkspaceClient("/fixture/app.sock", action_timeout_seconds=value)
    client = CeoIngressWorkspaceClient("/fixture/app.sock")
    assert client.timeout_seconds == 10 and client.acceptance_timeout_seconds == 30
    assert client.action_timeout_seconds == 480


def test_repeated_cancellation_preserves_one_owned_exchange(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        writer, connections = transport(monkeypatch, entered=entered, release=release)
        client = CeoIngressWorkspaceClient("/fixture/app.sock", action_timeout_seconds=1)
        task = asyncio.create_task(client.request(frame()))
        await entered.wait()
        try:
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and writer.close_calls == 0
            assert len(writer.writes) == len(connections) == 1
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert writer.close_calls == 1 and len(writer.writes) == len(connections) == 1
    asyncio.run(scenario())


def real_control(tmp_path, socket_root, monkeypatch, *, app_uid=None):
    import os
    from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
    from control_plane.workspace_read_service import workspace_provider_factory
    from scripts import chairman_control_room as publisher
    from tests.test_control_room_binding_transactions import FIRST, binding, config, save
    from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config
    from tests.test_workspace_control_room_actions import owner_fixture
    from tests.test_workspace_control_room_lifecycle import doc

    cfg = config(tmp_path)
    save(cfg, [binding(FIRST)])
    seed, hosted, bindings, clock, request = owner_fixture(cfg)
    hosted._cache_active = False  # The real service start owns activation in this fixture.
    monkeypatch.setattr(publisher, "_compose_state_doc", lambda *a, **k: doc())
    monkeypatch.setattr(publisher.capability, "census", lambda **k: {})
    factory = workspace_provider_factory(
        control_room=hosted, authorize=seed._authorize,
        authorize_actions=dict(seed._authorize_actions), action_now=lambda: clock[0],
        armed={"ceo_submit_armed": False}, runtime_identity={},
    )
    factory_calls = []
    def provide(runtime):
        factory_calls.append(runtime)
        return factory(runtime)
    svc = ExecutiveControlService(
        _config(tmp_path, socket_root=socket_root),
        supervisor_factory=lambda runtime: _FakeSupervisor(),
        ceo_ingress_socket_path=socket_root / "ceo.sock",
        ceo_ingress_peer_uid=os.geteuid() + 1000,
        ceo_ingress_grounding_provider=_FakeGrounding(),
        ceo_ingress_app_binding=CeoIngressAppBinding(
            peer_uid=os.geteuid() if app_uid is None else app_uid,
            armed=False, grounding_provider=_FakeGrounding(),
            workspace_read_provider_factory=provide,
        ),
        workspace_control_room=hosted,
    )
    return svc, cfg, hosted, request, factory_calls


from tests.test_executive_ceo_ingress import short_socket_root


def test_actual_app_peer_dispatches_once_without_business_arming(tmp_path, short_socket_root, monkeypatch):
    svc, cfg, host, request, factories = real_control(tmp_path, short_socket_root, monkeypatch)
    calls = []
    cfg.open_binding_fn = lambda *a, **k: calls.append(True) or {"ok": True, "verified": True}
    async def scenario():
        await svc.start()
        try:
            runtime = svc.runtime
            result = await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(request)
            assert result == returned() and calls == [True] and factories == [runtime]
            assert host.current_owner() is cfg and host._server is None
            assert svc._ceo_ingress_armed is False and svc._ceo_ingress_app_binding.armed is False
        finally:
            await svc.close()
    asyncio.run(scenario())


def test_action_private_bytes_are_strictly_reparsed_before_factory(tmp_path, short_socket_root, monkeypatch):
    svc, cfg, _, request, factories = real_control(tmp_path, short_socket_root, monkeypatch)
    cfg.open_binding_fn = lambda *a, **k: pytest.fail("duplicate raw frame reached owner")
    async def scenario():
        await svc.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(svc.ceo_ingress_socket_path))
            try:
                writer.write(b'{"operation":"open",' + canonical(request)[1:] + b"\n")
                await writer.drain()
                result = wire.decode_result_envelope(await reader.readuntil(b"\n"), operation="open")
                assert result["result"] == wire.refused_result("open", code="invalid_input", status=400)
                assert factories == []
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await svc.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("movement", ["binding", "factory", "closing", "ready", "state"])
def test_real_host_guard_is_rechecked_at_the_actual_effect_edge(
    tmp_path, short_socket_root, monkeypatch, movement,
):
    import dataclasses
    from control_plane import surface_bindings as sb
    svc, cfg, _, request, factories = real_control(tmp_path, short_socket_root, monkeypatch)
    read = sb.load_bindings
    before = cfg.bindings_path.read_bytes()
    def changed(path):
        value = read(path)
        if movement == "binding":
            svc._ceo_ingress_app_binding = dataclasses.replace(svc._ceo_ingress_app_binding)
        elif movement == "factory":
            object.__setattr__(svc._ceo_ingress_app_binding, "workspace_read_provider_factory",
                               lambda runtime: pytest.fail("replacement factory used"))
        elif movement == "closing": svc._closing = True
        elif movement == "ready": svc._ceo_ingress_ready = False
        else: svc._service_state = "QUARANTINED"
        return value
    monkeypatch.setattr(sb, "load_bindings", changed)
    cfg.open_binding_fn = lambda *a, **k: pytest.fail("retired ingress reached provider")
    async def scenario():
        await svc.start()
        try:
            result = await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(request)
            assert result == {"ok": True, "result": wire.refused_result(
                "open", code="source_unavailable", status=503,
            )}
            assert len(factories) == 1 and cfg.bindings_path.read_bytes() == before
        finally:
            await svc.close()
    asyncio.run(scenario())


def test_wrong_kernel_peer_never_reaches_action_factory(tmp_path, short_socket_root, monkeypatch):
    import os
    svc, cfg, _, request, factories = real_control(
        tmp_path, short_socket_root, monkeypatch, app_uid=os.geteuid() + 2000,
    )
    cfg.open_binding_fn = lambda *a, **k: pytest.fail("wrong peer reached provider")
    async def scenario():
        await svc.start()
        try:
            result = await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(request)
            # The generic pre-body peer refusal is not an action receipt. The
            # client conservatively preserves uncertainty after its one send.
            assert result == {"ok": True, "result": wire.unknown_result("open")}
            assert factories == []
        finally:
            await svc.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["normal_close", "handler_cancel", "client_disconnect"])
def test_existing_ingress_drain_retains_admitted_owner_until_actual_completion(
    tmp_path, short_socket_root, monkeypatch, mode,
):
    import threading
    svc, cfg, host, request, _ = real_control(tmp_path, short_socket_root, monkeypatch)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def provider(*a, **k):
        calls.append(True)
        entered.set()
        assert release.wait(4), "fixture release was not signalled"
        finished.set()
        return {"ok": True, "verified": True}
    cfg.open_binding_fn = provider

    async def scenario():
        client_task = close_task = writer = None
        await svc.start()
        try:
            runtime = svc.runtime
            if mode == "client_disconnect":
                _, writer = await asyncio.open_unix_connection(str(svc.ceo_ingress_socket_path))
                writer.write(canonical(request) + b"\n")
                await writer.drain()
            else:
                client_task = asyncio.create_task(
                    CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(request),
                )
            assert await asyncio.to_thread(entered.wait, 2)
            handlers = tuple(svc._ceo_ingress_tasks)
            assert len(handlers) == 1
            if mode == "handler_cancel":
                handlers[0].cancel()
                await asyncio.sleep(0)
                handlers[0].cancel()
            elif mode == "client_disconnect":
                writer.close()
                await writer.wait_closed()
            close_task = asyncio.create_task(svc.close())
            await asyncio.sleep(.02)
            assert svc._closing and not close_task.done() and not finished.is_set()
            assert svc.runtime is runtime and host.current_owner() is cfg
            assert set(handlers) <= svc._ceo_ingress_tasks
            release.set()
            if client_task is not None:
                result = await client_task
                assert result == (returned() if mode == "normal_close"
                                  else {"ok": True, "result": wire.unknown_result("open")})
            await close_task
            assert finished.is_set() and calls == [True]
            assert host.current_owner() is None and not svc._ceo_ingress_tasks
        finally:
            release.set()
            if writer is not None: writer.close()
            if client_task is not None: await asyncio.gather(client_task, return_exceptions=True)
            if close_task is not None: await asyncio.gather(close_task, return_exceptions=True)
            await svc.close()
    asyncio.run(scenario())
