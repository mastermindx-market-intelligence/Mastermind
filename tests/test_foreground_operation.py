"""Actual fresh Runtime admission and local source lifetime, with an inert claim boundary."""
import asyncio
import copy
import dataclasses
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from common.session_bridge_private_contract import PRIVATE_SCHEMA
from control_plane import ceo_request, foreground_operation as module
from control_plane.executive_runtime import Runtime
from tests import test_foreground_fresh_admission as fresh
from tests import test_session_bridge_installed as installed


def frame(key="foreground-source-only", **principal_changes):
    request = copy.deepcopy(fresh.hooks._strict_v2_frame()["request"])
    p = installed.principal_frame()
    p.update(issued_at=int(time.time()) - 30, expires_at=int(time.time()) + 300)
    p.update(principal_changes)
    return {"schema": PRIVATE_SCHEMA, "tool": "session_summon", "principal": p,
            "arguments": {**request, "operation_key": key}}


async def admit(runtime, tmp_path, operation, f):
    public = copy.deepcopy(fresh.hooks._strict_v2_frame())
    public["request_ref"] = ceo_request.app_request_ref(f["arguments"]["operation_key"])
    public["request"] = {k: v for k, v in f["arguments"].items() if k != "operation_key"}
    if runtime.workers.get_worker("worker-a") is None:
        return await fresh.strict_call(runtime, tmp_path, operation._bind_admitted_root, frame=public)
    # The fixture's registration happens once; duplicate submission reuses it.
    with patch.object(fresh.phase1fc, "_register_placement_union", lambda _: None):
        return await fresh.strict_call(runtime, tmp_path, operation._bind_admitted_root, frame=public)


def test_unavailable_outside_original_handler_and_no_public_mint(tmp_path):
    assert module._current_foreground_operation_or_none() is None
    with pytest.raises(module.ForegroundOperationClosed):
        module.current_foreground_operation()
    with pytest.raises(module.ForegroundOperationClosed):
        module.ForegroundOperation(mint=None, runtime=None, host_current=None, principal=None, arguments={})
    with pytest.raises(module.ForegroundOperationClosed):
        module.require_start({}, {}, "1" * 64, "2" * 64)


@pytest.mark.parametrize("fault,code", [
    ("read_tool", "foreground_unavailable"), ("send_tool", "foreground_unavailable"),
    ("foreign_schema", "foreground_unavailable"), ("extra_field", "foreground_unavailable"),
    ("expired", "principal_not_live"), ("future", "principal_not_live"),
    ("boolean_time", "principal_not_live"), ("scope", "scope_denied"),
    ("issuer", "foreground_unavailable"), ("host", "host_not_current"),
    ("host_bool", "host_not_current"),
])
def test_actual_frame_principal_and_host_refusals(tmp_path, fault, code):
    f = frame()
    host = lambda: None
    if fault == "read_tool": f["tool"] = "session_targets"
    if fault == "send_tool": f["tool"] = "session_send"
    if fault == "foreign_schema": f["schema"] = "caller-selected"
    if fault == "extra_field": f["attendance"] = True
    if fault == "expired": f["principal"]["expires_at"] = int(time.time()) - 1
    if fault == "future": f["principal"]["issued_at"] = int(time.time()) + 60
    if fault == "boolean_time": f["principal"]["issued_at"] = True
    if fault == "scope": f["principal"]["scopes"] = ["mastermind.executive.read"]
    if fault == "issuer": f["principal"]["issuer_digest"] = "0" * 64
    if fault == "host":
        def host(): raise ValueError("PRIVATE CONTENT")
    if fault == "host_bool": host = lambda: True
    async def run():
        async with module._session_bridge_foreground_dispatch(Runtime.at(tmp_path), f, host):
            pytest.fail("refused source entered")
    with pytest.raises(module.ForegroundOperationRefusal) as error:
        asyncio.run(run())
    assert error.value.code == code and "PRIVATE CONTENT" not in str(error.value)


def test_actual_fresh_commit_binds_once_but_queue_is_not_start(tmp_path):
    runtime, f = Runtime.at(tmp_path / "runtime"), frame()
    async def run():
        async with module._session_bridge_foreground_dispatch(runtime, f, lambda: None) as op:
            assert module.current_foreground_operation() is op
            result = await admit(runtime, tmp_path, op, f)
            assert op._root == result["job_id"] and result["dispatched"] is False
            op.require_root(result["job_id"])
            assert not result["duplicate"] and runtime.attempts.list_attempts() == []
            with pytest.raises(module.ForegroundOperationRefusal, match="already bound"):
                op._bind_admitted_root(op._root, op._command)
            with pytest.raises(TypeError):
                op._bind_admitted_root({"root_id": op._root, "dispatched": True})
            return op, result
    op, result = asyncio.run(run())
    with pytest.raises(module.ForegroundOperationClosed): op.require_arguments(f["arguments"])
    async def replay():
        async with module._session_bridge_foreground_dispatch(runtime, f, lambda: None) as again:
            duplicate = await admit(runtime, tmp_path, again, f)
            assert duplicate["duplicate"] and again._root is None
            with pytest.raises(module.ForegroundOperationRefusal) as unbound:
                again.require_root(result["job_id"])
            assert unbound.value.code == "root_unbound"
            with pytest.raises(module.ForegroundOperationRefusal) as error:
                again._bind_admitted_root(result["job_id"], again._command)
            assert error.value.code == "admission_not_fresh"
    asyncio.run(replay())
    assert len(runtime.jobs.list_jobs()) == 1


@pytest.mark.parametrize("edge", ["return", "exception", "cancel"])
def test_scope_closes_and_propagated_task_cannot_retain_source(tmp_path, edge):
    runtime, held = Runtime.at(tmp_path), []
    async def run():
        ready = asyncio.Event()
        async def copied():
            await ready.wait()
            with pytest.raises(module.ForegroundOperationClosed): module.current_foreground_operation()
        task = None
        try:
            async with module._session_bridge_foreground_dispatch(runtime, frame(), lambda: None) as op:
                held.append(op)
                task = asyncio.create_task(copied())
                if edge == "exception": raise ValueError("test")
                if edge == "cancel": raise asyncio.CancelledError()
        except (ValueError, asyncio.CancelledError): pass
        ready.set()
        await task
        assert module._current_foreground_operation_or_none() is None
    asyncio.run(run())
    assert held[0]._closed


def test_changed_arguments_and_current_host_refuse_without_fallback(tmp_path):
    state = {"live": True}
    def host():
        if not state["live"]: raise ValueError()
    async def run():
        f = frame()
        async with module._session_bridge_foreground_dispatch(Runtime.at(tmp_path), f, host) as op:
            op.require_arguments(f["arguments"])
            with pytest.raises(module.ForegroundOperationRefusal) as error:
                op.require_arguments({**f["arguments"], "objective": "Changed"})
            assert error.value.code == "arguments_changed"
            state["live"] = False
            with pytest.raises(module.ForegroundOperationRefusal) as error:
                module._current_foreground_operation_or_none()
            assert error.value.code == "host_not_current"
    asyncio.run(run())


def test_commit_then_lost_host_preserves_canonical_root(tmp_path, monkeypatch):
    runtime, f = Runtime.at(tmp_path / "runtime"), frame()
    state = {"live": True}
    def host():
        if not state["live"]: raise ValueError()
    original = module.ForegroundOperation._bind_admitted_root
    def disconnected(self, root_id, command_id):
        state["live"] = False
        original(self, root_id, command_id)
    monkeypatch.setattr(module.ForegroundOperation, "_bind_admitted_root", disconnected)
    async def run():
        async with module._session_bridge_foreground_dispatch(runtime, f, host) as op:
            with pytest.raises(fresh.sink._FreshAdmissionObserverFailed):
                await admit(runtime, tmp_path, op, f)
            assert op._root is None
    asyncio.run(run())
    assert len(runtime.jobs.list_jobs()) == 1 and runtime.attempts.list_attempts() == []


@pytest.mark.parametrize("fault,code", [
    ("none", None), ("root", "root_replaced"), ("claim", "claim_moved"),
    ("grant", "claim_moved"), ("commission", "commission_moved"),
    ("physical", "receipt_stale"), ("request", "receipt_stale"),
    ("json", "receipt_refused"), ("new_scope", "receipt_refused"),
])
def test_receipt_is_exact_scope_and_current_claim_not_json(tmp_path, monkeypatch, fault, code):
    # Real fresh root/event/commission; the remote claim boundary is an explicit
    # stand-in. This is source comparison coverage, not qualified remote START.
    runtime, f = Runtime.at(tmp_path / "runtime"), frame()
    physical, request = "1" * 64, "2" * 64
    async def run():
        async with module._session_bridge_foreground_dispatch(runtime, f, lambda: None) as op:
            result = await admit(runtime, tmp_path, op, f)
            with runtime.store.read() as connection:
                source = module._dialogue_source_from_root_creation(connection, root_job_id=result["job_id"])
            binding = dict(root_id=result["job_id"], job_id="fixture-job", attempt_id="fixture-attempt",
                effective_grant_digest="3" * 64, commission_sha256=source.commission_ref.content_sha256)
            job = SimpleNamespace(job_id=binding["job_id"], root_job_id=binding["root_id"])
            attempt = SimpleNamespace(attempt_id=binding["attempt_id"], effective_grant_digest="3" * 64)
            monkeypatch.setattr(module, "_read_claim", lambda *_a, **_k: (job, attempt, None, None))
            receipt = op.start_receipt(binding, physical, request)
            assert receipt.operation_key == f["arguments"]["operation_key"]
            assert set(receipt.as_dict()) == set(module._BINDING) | {
                "physical_binding_sha256", "start_request_sha256", "principal_identity",
                "operation_key", "arguments_sha256"}
            changed, p, r, value = dict(binding), physical, request, receipt
            if fault == "root": changed["root_id"] = "foreign-root"
            if fault == "claim": attempt.attempt_id = "moved"
            if fault == "grant": attempt.effective_grant_digest = "4" * 64
            if fault == "commission": changed["commission_sha256"] = "4" * 64
            if fault == "physical": p = "4" * 64
            if fault == "request": r = "4" * 64
            if fault == "json": value = receipt.as_dict()
            if fault == "new_scope":
                # Even identical public fields cannot move a receipt to another
                # active in-process invocation, including nested ContextVars.
                async with module._session_bridge_foreground_dispatch(runtime, f, lambda: None):
                    with pytest.raises(module.ForegroundOperationRefusal) as error:
                        module.require_start(value, changed, p, r)
                assert error.value.code == code
            elif code:
                with pytest.raises(module.ForegroundOperationRefusal) as error:
                    module.require_start(value, changed, p, r)
                assert error.value.code == code
            else:
                module.require_start(value, changed, p, r)
    asyncio.run(run())


def test_incumbent_real_claim_refusal_is_closed(tmp_path):
    runtime, f = Runtime.at(tmp_path / "runtime"), frame()
    async def run():
        async with module._session_bridge_foreground_dispatch(runtime, f, lambda: None) as op:
            result = await admit(runtime, tmp_path, op, f)
            binding = dict(root_id=result["job_id"], job_id=result["job_id"], attempt_id="absent",
                effective_grant_digest="1" * 64, commission_sha256="2" * 64)
            with pytest.raises(module.ForegroundOperationRefusal) as error:
                op.start_receipt(binding, "3" * 64, "4" * 64)
            assert error.value.code == "claim_refused"
    asyncio.run(run())


def test_before_claim_rechecks_exact_canonical_root_event(tmp_path, monkeypatch):
    runtime, f = Runtime.at(tmp_path / "runtime"), frame()
    async def run():
        async with module._session_bridge_foreground_dispatch(runtime, f, lambda: None) as op:
            result = await admit(runtime, tmp_path, op, f)
            original = runtime.store.find_event_by_command_id
            def drift(command):
                event = original(command)
                return {**event, "created_at_ms": event["created_at_ms"] + 1}
            monkeypatch.setattr(runtime.store, "find_event_by_command_id", drift)
            with pytest.raises(module.ForegroundOperationRefusal) as error:
                op.require_root(result["job_id"])
            assert error.value.code == "root_replaced"
    asyncio.run(run())
