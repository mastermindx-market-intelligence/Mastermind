"""New acquisition transport joins the real original selector; all state is disposable."""
import asyncio
import dataclasses
import threading

import pytest

from control_plane.principal_ruling_target import PrincipalRulingTarget
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_product_acceptance_original_selector import anchor, bind_actual_issuer
from tests.test_product_acceptance_read_projection import case
from tests.test_product_acceptance_workspace_read import provider


def acquisition_frame(frame):
    return {**frame, "operation": "mission_v4_original",
            "selection": {k: frame["selection"][k] for k in ("work_ref", "root_job_id")}}


@pytest.mark.parametrize("complete", [True, False])
def test_actual_selector_dispatch_preserves_original_events(tmp_path, monkeypatch, complete):
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch, complete=complete) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected)
        target = PrincipalRulingTarget(selected["work_ref"], obligation.obligation_id, "test-owner")
        before = runtime.events.list_events()
        def execute(bound):
            svc, frame, _ = provider(tmp_path, runtime, owner.reader, selected, bound)
            svc._product_acceptance_owner_target = target
            return asyncio.run(svc.handle_frame(acquisition_frame(frame)))
        result = run(execute)
        assert result["ok"] is True, result
        assert result["result"]["product_acceptance"]["selection"] == selected
        assert result["result"]["product_acceptance"]["state"] == (
            "ACCEPTED" if complete else "UNAVAILABLE")
        assert runtime.events.list_events() == before


@pytest.mark.parametrize("change", ["missing", "foreign", "replace", "mutate"])
def test_missing_foreign_or_rotated_host_target_withholds_body(tmp_path, monkeypatch, change):
    import integrations.product_acceptance_selector as selector
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected)
        target = PrincipalRulingTarget(selected["work_ref"], obligation.obligation_id, "test-owner")
        actual = selector.read_original_acceptance_observation
        calls = []
        async def changed(svc, frame, *, owner_target):
            calls.append(owner_target)
            result = await actual(svc, frame, owner_target=owner_target)
            if change == "replace":
                svc._product_acceptance_owner_target = dataclasses.replace(owner_target)
            elif change == "mutate":
                object.__setattr__(owner_target, "reasoning_surface", "foreign")
            return result
        monkeypatch.setattr(selector, "read_original_acceptance_observation", changed)
        def execute(bound):
            svc, frame, _ = provider(tmp_path, runtime, owner.reader, selected, bound)
            svc._product_acceptance_owner_target = (
                None if change == "missing" else dataclasses.replace(target, work_ref="WS:FOREIGN")
                if change == "foreign" else target)
            return asyncio.run(svc.handle_frame(acquisition_frame(frame)))
        before = runtime.events.list_events()
        # Missing/foreign target must refuse before acquiring any Runtime read.
        response = execute(None) if change in ("missing", "foreign") else run(execute)
        assert response == {"ok": False, "status": 503,
            "error": {"code": "source_unavailable", "message": "workspace read refused"}}
        assert runtime.events.list_events() == before
        assert len(calls) == (0 if change in ("missing", "foreign") else 1)


@pytest.mark.parametrize("target", [{}, "WAK-incorrect", object()])
def test_configuration_rejects_client_shaped_target(target):
    with pytest.raises(ValueError):
        WorkspaceReadService(cache=None, runtime=None, authorize=lambda _: True,
            armed={}, runtime_identity={}, product_acceptance_owner_target=target)


def test_default_target_is_absent():
    service = WorkspaceReadService(cache=None, runtime=None, authorize=lambda _: True,
        armed={}, runtime_identity={})
    assert service._product_acceptance_owner_target is None


@pytest.mark.parametrize("reader", ["_product_acceptance_read", "_product_acceptance_observe"])
@pytest.mark.parametrize("change", ["missing", "rotated"])
def test_missing_or_rotated_outer_reader_withholds_original_result(tmp_path, monkeypatch, reader, change):
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected)
        target = PrincipalRulingTarget(selected["work_ref"], obligation.obligation_id, "test-owner")
        events = runtime.events.list_events()

        def execute(bound):
            svc, frame, _ = provider(tmp_path, runtime, owner.reader, selected, bound)
            svc._product_acceptance_owner_target = target
            if change == "missing":
                setattr(svc, reader, None)
            else:
                original = svc._product_acceptance_observe

                async def rotated(*args, **kwargs):
                    result = await original(*args, **kwargs)
                    setattr(svc, reader, lambda *a, **kw: None)
                    return result

                svc._product_acceptance_observe = rotated
            return asyncio.run(svc.handle_frame(acquisition_frame(frame)))

        # Missing composition refuses before acquiring a Runtime read binding.
        response = execute(None) if change == "missing" else run(execute)
        assert response == {"ok": False, "status": 503,
            "error": {"code": "source_unavailable", "message": "workspace read refused"}}
        assert runtime.events.list_events() == events


def test_acquisition_cancellation_settles_original_read_without_disclosure(tmp_path, monkeypatch):
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, run):
        obligation = anchor(runtime, owner, selected)
        target = PrincipalRulingTarget(selected["work_ref"], obligation.obligation_id, "test-owner")
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        before = runtime.events.list_events()
        def execute(bound):
            svc, frame, _ = provider(tmp_path, runtime, owner.reader, selected, bound)
            svc._product_acceptance_owner_target = target
            actual = svc._read_mission_v4
            def held_read(value):
                started.set()
                try:
                    assert release.wait(3)
                    return actual(value)
                finally:
                    finished.set()
            monkeypatch.setattr(svc, "_read_mission_v4", held_read)
            async def cancelled():
                task = asyncio.create_task(svc.handle_frame(acquisition_frame(frame)))
                try:
                    assert await asyncio.to_thread(started.wait, 2)
                    task.cancel()
                    await asyncio.sleep(.02)
                    task.cancel()
                    await asyncio.sleep(.02)
                    assert not task.done()
                finally:
                    release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert finished.is_set()
            asyncio.run(cancelled())
        run(execute)
        assert runtime.events.list_events() == before
