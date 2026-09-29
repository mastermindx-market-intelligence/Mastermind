"""Service composition tests; synthetic consumer method, no installed authority."""

from __future__ import annotations

import asyncio
import dataclasses
import threading
from types import SimpleNamespace

import pytest

from control_plane.executive_release_consumer import (
    ReleaseControlConsumer,
    ReleaseConsumerError,
)
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_service import ExecutiveControlService, ServiceError
from tests.test_executive_service import _config, _FakeSupervisor


@pytest.fixture
def config(tmp_path, tmp_path_factory):
    return _config(tmp_path, socket_root=tmp_path_factory.mktemp("s"))


def _armed(config, **kwargs):
    return ExecutiveControlService(
        dataclasses.replace(config, release_control_armed=True),
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
        **kwargs,
    )


@pytest.mark.parametrize("value", [1, 0, "true", None, [], {}])
def test_arm_requires_literal_boolean(config, value):
    with pytest.raises(ValueError, match="release_control_armed"):
        dataclasses.replace(config, release_control_armed=value)


def test_factory_and_explicit_arm_must_be_coupled(config):
    with pytest.raises(ValueError, match="requires its consumer factory"):
        _armed(config)
    with pytest.raises(ValueError, match="requires release_control_armed"):
        ExecutiveControlService(
            config, release_control_consumer_factory=ReleaseControlConsumer
        )


def test_unarmed_start_does_not_touch_release_history(config, monkeypatch):
    def forbidden(_self):
        pytest.fail("default-off startup reached release history")

    monkeypatch.setattr(
        ReleaseControlConsumer,
        "finalize_unresolved_admission",
        forbidden,
        raising=False,
    )

    async def run():
        service = ExecutiveControlService(config, supervisor_factory=_FakeSupervisor)
        await service.start()
        try:
            assert service.service_state == "READY"
            assert service._release_control_consumer is None
            assert not service.runtime.events.list_events()
        finally:
            await service.close()

    asyncio.run(run())


def test_cached_consumer_runtime_and_startup_order(config, monkeypatch):
    order = []
    consumers = []

    def finalize(self):
        order.append("release")
        assert self is consumers[0]
        assert service.runtime is self.runtime
        assert service._server is None
        assert service._lock_fd is not None
        assert service._namespace_custody is not None

    monkeypatch.setattr(
        ReleaseControlConsumer, "finalize_unresolved_admission", finalize, raising=False
    )

    def factory(runtime):
        order.append("factory")
        consumers.append(ReleaseControlConsumer(runtime))
        return consumers[-1]

    class Supervisor(_FakeSupervisor):
        def reconcile_restart(self, **kwargs):
            order.append("supervisor")
            return super().reconcile_restart(**kwargs)

    service = _armed(config, release_control_consumer_factory=factory)
    service._supervisor_factory = Supervisor
    original_bind = service._bind_operator_server

    async def replay():
        order.append("terminal")

    async def bind(**kwargs):
        order.append("listen")
        await original_bind(**kwargs)

    monkeypatch.setattr(service, "_replay_terminal_returns_on_startup", replay)
    monkeypatch.setattr(service, "_bind_operator_server", bind)

    async def run():
        await service.start()
        try:
            assert order == ["factory", "supervisor", "release", "terminal", "listen"]
            assert service._require_release_control_consumer() is consumers[0]
            assert service._require_release_control_consumer() is consumers[0]
            assert len(consumers) == 1
            assert not service.runtime.events.list_events()
            assert not service._physical_workers
        finally:
            await service.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "kind", ["lookalike", "subclass", "foreign_runtime", "missing_method"]
)
def test_incomplete_factory_refuses_before_listening(
    config, monkeypatch, tmp_path, kind
):
    if kind == "missing_method":
        monkeypatch.delattr(
            ReleaseControlConsumer, "finalize_unresolved_admission", raising=False
        )
    if kind != "missing_method":
        monkeypatch.setattr(
            ReleaseControlConsumer,
            "finalize_unresolved_admission",
            lambda self: None,
            raising=False,
        )

    class Subclass(ReleaseControlConsumer):
        pass

    def factory(runtime):
        if kind == "lookalike":
            return SimpleNamespace(
                runtime=runtime, finalize_unresolved_admission=lambda: None
            )
        if kind == "subclass":
            return Subclass(runtime)
        if kind == "foreign_runtime":
            return ReleaseControlConsumer(Runtime.at(tmp_path / "foreign"))
        return ReleaseControlConsumer(runtime)

    async def run():
        service = _armed(config, release_control_consumer_factory=factory)
        with pytest.raises(ServiceError, match="composition is unavailable"):
            await service.start()
        assert service._server is None
        assert service._lock_fd is None
        assert not service.runtime.events.list_events()

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["unknown", False, {}, "exception"])
def test_uncertain_closure_quarantines_before_terminal_or_listeners(
    config, monkeypatch, outcome
):
    calls = []

    def finalize(self):
        calls.append("closure")
        if outcome == "exception":
            raise ReleaseConsumerError("RELEASE_EFFECT_IN_PROGRESS")
        return outcome

    monkeypatch.setattr(
        ReleaseControlConsumer, "finalize_unresolved_admission", finalize, raising=False
    )

    async def run():
        service = _armed(
            config, release_control_consumer_factory=ReleaseControlConsumer
        )

        async def replay():
            pytest.fail("terminal replay ran before qualified release closure")

        monkeypatch.setattr(service, "_replay_terminal_returns_on_startup", replay)
        with pytest.raises(StateConflict, match="release closure was quarantined"):
            await service.start()
        assert service.service_state == "QUARANTINED"
        assert service._server is None
        assert calls == ["closure"]
        assert not service.runtime.events.list_events()

    asyncio.run(run())


def test_existing_supervisor_quarantine_cannot_finalize_release(config, monkeypatch):
    def forbidden(self):
        pytest.fail("quarantined supervisor cannot authorize release closure")

    monkeypatch.setattr(
        ReleaseControlConsumer,
        "finalize_unresolved_admission",
        forbidden,
        raising=False,
    )

    class Supervisor(_FakeSupervisor):
        def reconcile_restart(self, **kwargs):
            return [SimpleNamespace(status="IDENTITY_AMBIGUOUS")]

    async def run():
        service = _armed(
            config, release_control_consumer_factory=ReleaseControlConsumer
        )
        service._supervisor_factory = Supervisor
        await service.start()
        try:
            assert service.service_state == "QUARANTINED"
            assert not service.runtime.events.list_events()
        finally:
            await service.close()

    asyncio.run(run())


@pytest.mark.parametrize("fail", [False, True])
def test_canary_defers_release_until_activation_before_ready(config, monkeypatch, fail):
    order = []

    def finalize(self):
        order.append("release")
        assert service.service_state == "ACTIVATING_CANARY"
        if fail:
            raise ReleaseConsumerError("RELEASE_HISTORY_ADMISSION_UNQUALIFIED")

    monkeypatch.setattr(
        ReleaseControlConsumer, "finalize_unresolved_admission", finalize, raising=False
    )
    # This test owns service ordering only; the canary validator has its own gate.
    monkeypatch.setattr(
        "control_plane.codex_worker.validate_secret_canary_verdict",
        lambda value, **kwargs: value,
    )
    service = _armed(
        config,
        release_control_consumer_factory=ReleaseControlConsumer,
        service_state="AWAITING_CANARY",
    )

    def supervisor_factory(runtime):
        supervisor = _FakeSupervisor(runtime)
        supervisor.secret_canary_verdict = {}
        supervisor.require_complete_launch_attestation = False
        return supervisor

    service._supervisor_factory = supervisor_factory

    async def replay():
        order.append("terminal")

    monkeypatch.setattr(service, "_replay_terminal_returns_on_startup", replay)

    async def run():
        await service.start()
        try:
            assert order == []
            if fail:
                with pytest.raises(
                    StateConflict, match="release closure was quarantined"
                ):
                    await service.activate_canary({})
                assert order == ["release"]
                assert service.service_state == "QUARANTINED"
            else:
                await service.activate_canary({})
                assert order == ["release", "terminal"]
                assert service.service_state == "READY"
                with pytest.raises(ServiceError, match="not awaiting a canary"):
                    await service.activate_canary({})
                assert order == ["release", "terminal"]
            assert not service.runtime.events.list_events()
        finally:
            await service.close()

    asyncio.run(run())


def test_cancelled_finalizer_retains_owned_work_and_quarantine(config, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def finalize(self):
        calls.append("closure")
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(
        ReleaseControlConsumer, "finalize_unresolved_admission", finalize, raising=False
    )

    async def run():
        service = _armed(
            config, release_control_consumer_factory=ReleaseControlConsumer
        )
        service.runtime = Runtime.at(config.runtime_root)
        service._release_control_consumer = ReleaseControlConsumer(service.runtime)
        task = asyncio.create_task(service._finalize_release_admission_on_startup())
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert service.service_state == "QUARANTINED"
            assert len(service._physical_workers) == 1
            assert calls == ["closure"]
        finally:
            release.set()
            await service.close()
        assert not service._physical_workers
        assert not service.runtime.events.list_events()

    asyncio.run(run())


@pytest.mark.parametrize(
    "armed,state,admitted",
    [
        (True, "READY", True),
        (True, "AWAITING_CANARY", False),
        (False, "AWAITING_CANARY", True),
    ],
)
def test_native_gateway_uses_same_consumer_only_after_canary(
    config, monkeypatch, armed, state, admitted
):
    import json
    import os
    from control_plane.executive_release_ingress import FRAME_SCHEMA
    from control_plane.executive_service import CeoIngressAppBinding
    from tests.test_executive_ceo_ingress import _FakeGrounding, _raw_ceo_request

    finalized = []
    handled = []

    def finalize(self):
        finalized.append(self)

    def handle(self, raw, connection):
        handled.append(self)
        assert connection.fileno() >= 0
        return {"ok": True, "synthetic_service_wiring": True}

    monkeypatch.setattr(
        ReleaseControlConsumer, "finalize_unresolved_admission", finalize, raising=False
    )
    monkeypatch.setattr(ReleaseControlConsumer, "handle", handle)

    async def run():
        service = ExecutiveControlService(
            dataclasses.replace(config, release_control_armed=armed),
            supervisor_factory=_FakeSupervisor,
            release_control_consumer_factory=ReleaseControlConsumer if armed else None,
            service_state=state,
            ceo_ingress_socket_path=config.socket_path.parent / "ceo.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(),
                armed=True,
                grounding_provider=_FakeGrounding(),
            ),
        )
        await service.start()
        try:
            before = tuple(service.runtime.events.list_events())
            raw = (
                json.dumps(
                    {
                        "schema": FRAME_SCHEMA,
                        "operation": "reconcile_release_transition",
                    }
                )
                + "\n"
            ).encode()
            for _ in range(2):
                result = await _raw_ceo_request(service.ceo_ingress_socket_path, raw)
                assert result["ok"] is admitted
                if not admitted:
                    assert result["error"]["code"] == "RELEASE_UNAVAILABLE"
            assert len(handled) == (2 if admitted else 0)
            if armed and admitted:
                assert finalized == [service._release_control_consumer]
                assert handled == [finalized[0], finalized[0]]
            else:
                assert not finalized
            assert tuple(service.runtime.events.list_events()) == before
            assert not service.runtime.jobs.list_jobs()
        finally:
            await service.close()

    asyncio.run(run())


@pytest.mark.parametrize("route", ["method", "socket"])
@pytest.mark.parametrize("failure", ["finalizer", "reconciliation", "cancel", "none"])
def test_overlapping_activation_cannot_retry_or_clear_quarantine(
    config, monkeypatch, route, failure
):
    from tests.test_executive_service import _request

    entered = threading.Event()
    release = threading.Event()
    reconciled = []
    finalized = []

    class Supervisor(_FakeSupervisor):
        secret_canary_verdict = {}
        require_complete_launch_attestation = False

        def reconcile_restart(self, **kwargs):
            reconciled.append(self)
            entered.set()
            assert release.wait(5)
            if failure == "reconciliation":
                raise StateConflict("synthetic reconciliation failure")
            return []

    def finalize(self):
        finalized.append(self)
        if failure == "finalizer":
            raise ReleaseConsumerError("RELEASE_EFFECT_IN_PROGRESS")

    monkeypatch.setattr(
        ReleaseControlConsumer, "finalize_unresolved_admission", finalize, raising=False
    )
    monkeypatch.setattr(
        "control_plane.codex_worker.validate_secret_canary_verdict",
        lambda value, **kwargs: value,
    )
    service = _armed(
        config,
        release_control_consumer_factory=ReleaseControlConsumer,
        service_state="AWAITING_CANARY",
        canary_loader=lambda: {},
    )
    service._supervisor_factory = Supervisor

    async def activate():
        if route == "socket":
            return await _request(service, "activate-canary")
        return await service.activate_canary({})

    async def run():
        await service.start()
        tasks = []
        try:
            tasks.append(asyncio.create_task(activate()))
            assert await asyncio.to_thread(entered.wait, 3)
            tasks.append(asyncio.create_task(activate()))
            # The sibling must refuse while the first physical reconciliation
            # is still blocked, not wait and retry after it fails.
            sibling = await asyncio.wait_for(
                asyncio.gather(tasks[1], return_exceptions=True), 2
            )
            assert (
                isinstance(sibling[0], ServiceError)
                if route == "method"
                else sibling[0]["ok"] is False
            )
            assert len(reconciled) == 1
            assert not finalized
            if failure == "cancel":
                if route == "method":
                    tasks[0].cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await tasks[0]
                    assert service.service_state == "QUARANTINED"
                else:
                    # Cancel the owned handler itself, not merely the client.
                    handlers = [
                        task for task in service._operator_handlers if not task.done()
                    ]
                    assert len(handlers) == 1
                    handlers[0].cancel()
                    await asyncio.gather(handlers[0], return_exceptions=True)
                    assert service.service_state == "QUARANTINED"
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(
                *list(service._physical_workers), return_exceptions=True
            )
            expected = "READY" if failure == "none" else "QUARANTINED"
            assert service.service_state == expected
            assert len(finalized) == (1 if failure in {"finalizer", "none"} else 0)
            assert not service.runtime.events.list_events()
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(
                *list(service._physical_workers), return_exceptions=True
            )
            await service.close()

    asyncio.run(run())
