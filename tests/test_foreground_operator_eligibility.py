"""Real installed factory/admission/driver, with only physical execution inert.

Host receipt and grounding are explicit fixtures. No production provider or
credential is used; Runtime, eligibility, binding and OHF completion are real.
"""
import asyncio
import dataclasses
import hashlib
import os
from pathlib import Path
import subprocess
from contextlib import asynccontextmanager

import pytest

from control_plane import ceo_request, executive_ceo_ingress as ingress, foreground_operation as scope
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.executive_runtime import NATIVE_RETURN_TX5_EXECUTION_PROFILE, JobStatus
from tests.test_executive_service import prepare_credentialless_clone
from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
from tests import test_executive_mcp_installed_fabric_composition as installed
from tests import test_foreground_fresh_admission as fresh
from tests.test_foreground_operation import frame
from tests.test_executive_operator_supervisor import _ActiveAdapter, _CommissionPromptSource


class _InertForegroundAdapter(_ActiveAdapter):
    """Unqualified inert adapter; never impersonates the actual transport owner."""
    def __init__(self, *args, **kwargs):
        _ActiveAdapter.__init__(self, *args, **kwargs)
        self._fresh_effect_guard = None
        self._foreground_attempt_id = None

    def start_session(self, **kwargs):
        assert self._fresh_effect_guard is not None
        self._fresh_effect_guard()
        return super().start_session(**kwargs)

    def begin_turn(self, **kwargs):
        assert self._fresh_effect_guard is not None
        self._fresh_effect_guard()
        return super().begin_turn(**kwargs)


@asynccontextmanager
async def real_factory(tmp_path, socket_root, monkeypatch, *, armed=True, harness=True):
    raw = installed._raw_for_factory(tmp_path, socket_root, profile=WEB_CEO_SESSIONS_PROFILE)
    source = Path(raw["proof_source_repository"])
    commission = source / "docs/commissions/executive-terminal-return.md"
    commission.parent.mkdir(parents=True)
    commission.write_text("Read one fixture fact and return one bounded plan.\n")
    subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "fixture commission"], cwd=source, check=True, capture_output=True)
    raw.update(proof_base_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
        coo_autonomy_armed=armed, coo_operator_harness_armed=harness,
        coo_tick_interval_seconds=3600.0, shared_run_gid=os.getegid(),
        operator_harness_binary_digest="a" * 64, operator_harness_version="0.147.0")
    sockets = {"Operator": installed._listening(Path(raw["control_socket_path"])),
               "CeoIngress": installed._listening(Path(raw["ceo_ingress_socket_path"]))}
    module = installed._patch_composition(monkeypatch, sockets)
    holder = {"adapters": [], "guard": 0, "identity": 0, "valid_receipt": True}

    class Broker:
        async def request(self, method, args):
            assert method == "ohf-identity" and args == {}
            holder["identity"] += 1
            return {"worker_id": "codex-01", "binary_sha256": "a" * 64,
                    "binary_version": "0.147.0", "operator_harness_armed": harness}

    class Sealed(_CommissionPromptSource, ExecutiveSupervisor):
        def __init__(self, *args, **kwargs):
            pass
        def reconcile_restart(self, **kw):
            return []
        def take_recovered_runs(self):
            return ()
        async def start_cycle_job(self, *args, **kw):
            pytest.fail("ordinary Operator must never enter the sealed-worker fallback")

    monkeypatch.setattr("control_plane.executive_worker_broker.WorkerBrokerClient", lambda *a, **k: Broker())
    monkeypatch.setattr("control_plane.executive_supervisor.ExecutiveSupervisor", Sealed)
    def guard():
        holder["guard"] += 1
        if not holder["valid_receipt"]:
            raise ValueError("fixture receipt expired")
    def claimed(attempt, requested, loader, *, recovery):
        assert not recovery and attempt.worker_id == requested.worker_id == "codex-01"
        adapter = _InertForegroundAdapter(service._require_runtime(), loader, cancel_during_collect=False)
        holder["adapters"].append(adapter)
        return adapter
    service = None
    try:
        service = module._service_from_config(raw, autonomy_guard=guard,
            initial_canary={}, claimed_operator_adapter_factory=claimed)
        await service.start()
        service._register_worker()
        runtime = service._require_runtime()
        grounding = {**fresh.hooks.pr_a.GROUNDING_A, "mastermind_sha": raw["proof_base_sha"]}
        dialogue = fresh.hooks._dialogue_source(raw["proof_base_sha"])
        dialogue["commission_ref"]["content_sha256"] = hashlib.sha256(commission.read_bytes()).hexdigest()
        original = ingress.handle_frame
        observer = ingress._observe_trusted_grounding
        async def observe(_):
            return await observer(fresh.hooks.pr_a._FakeGrounding([grounding]))
        async def submit(parsed, **kw):
            binding_provider, admission_guard = kw["execution_binding_provider"], kw["admission_guard"]
            bind_root = kw["fresh_admission_observer"]
            def current_binding():
                if holder.get("before_binding"):
                    holder["before_binding"]()
                return binding_provider()
            def guarded(envelope):
                if holder.get("before_guard"):
                    holder["before_guard"]()
                return admission_guard(envelope)
            def admitted(root, command):
                bind_root(root, command)
                if holder.get("after_commit"):
                    holder["after_commit"]()
            return await original(parsed, **{**kw,
                "execution_binding_provider": current_binding, "admission_guard": guarded,
                "fresh_admission_observer": admitted if bind_root is not None else None,
                "grounding_provider": fresh.hooks.pr_a._FakeGrounding([grounding]),
                "dialogue_source_provider": lambda *_: dialogue})
        monkeypatch.setattr(ingress, "_observe_trusted_grounding", observe)
        monkeypatch.setattr(ingress, "handle_frame", submit)
        f = frame("real-operator-factory")
        intent = ceo_request.automated_intent_id(ceo_request.app_request_ref(f["arguments"]["operation_key"]))
        prepare_credentialless_clone(source, Path(raw["proof_workspace_root"]), job_id=intent,
            base_sha=raw["proof_base_sha"], branch=ceo_request.derive_branch(intent), shared_gid=os.getegid())
        driver = service._drive_foreground_cycle
        async def diagnosed_driver(*args):
            try:
                return await driver(*args)
            except Exception as exc:
                holder["driver_error"] = repr(exc)
                raise
        monkeypatch.setattr(service, "_drive_foreground_cycle", diagnosed_driver)
        owner = service._ceo_ingress_app_binding.session_bridge_provider_factory(runtime)
        yield service, owner, f, holder
    finally:
        if service is not None:
            await service.close()
        for sock in sockets.values():
            sock.close()


async def invoke(service, owner, f):
    async with scope._session_bridge_foreground_dispatch(service._require_runtime(), f, lambda: None) as op:
        return await owner.handle_frame(f)


def test_unqualified_foreground_adapter_refuses_without_provider_start(tmp_path, short_socket_root, monkeypatch):
    """A live Web foreground request must not adopt the former inert adapter.

    The ordinary Supervisor's standalone non-foreground tests retain their
    positive execution proof. A Web path requires the genuinely qualified
    RemoteOperatorHarnessAdapter, not a mock that only mimics its interface.
    """
    async def run():
        async with real_factory(tmp_path, short_socket_root, monkeypatch) as (s, owner, f, h):
            result = await invoke(s, owner, f)
            assert not result["ok"], result
            assert result["error"]["code"] == "effect_unknown", result
            assert "qualified transport owner" in h.get("driver_error", "")
            assert len(h["adapters"]) == 1
            adapter = h["adapters"][0]
            assert (adapter.begin_turn_calls, adapter.stop_calls, adapter.cancel_calls) == (0, 0, 0)
            assert adapter.prompts == []
            assert not any(attempt.status.value in {"RUNNING", "COMPLETED"}
                           for attempt in s._require_runtime().attempts.list_attempts())
            # A claimed-but-unstarted original Attempt is not permission to retry.
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["autonomy_off", "harness_off", "native", "receipt", "binding", "closing", "not_ready", "worker"])
def test_current_eligibility_before_canonical_commit(tmp_path, short_socket_root, monkeypatch, mode):
    async def run():
        async with real_factory(tmp_path, short_socket_root, monkeypatch,
                armed=mode != "autonomy_off", harness=mode not in {"autonomy_off", "harness_off"}) as (s, owner, f, h):
            if mode == "native":
                # Profile fixture only: the eligibility/factory/real driver remain production.
                binding = s._require_current_coo_binding()
                binding["operator_execution_profile_id"] = NATIVE_RETURN_TX5_EXECUTION_PROFILE
                monkeypatch.setattr(s, "_require_current_coo_binding", lambda: binding)
            if mode == "receipt": h["valid_receipt"] = False
            if mode == "binding": s._coo_execution_binding["model"] = "drift"
            if mode == "closing": s._closing = True
            if mode == "not_ready": s._service_state = "AWAITING_CANARY"
            if mode == "worker":
                s.config = dataclasses.replace(s.config, worker_id="unregistered-worker")
            try:
                result = await invoke(s, owner, f)
                queued = mode in {"autonomy_off", "harness_off", "native"}
                assert result["ok"] is queued, result
                assert len(s._require_runtime().jobs.list_jobs()) == (1 if queued else 0)
                if queued:
                    assert result["data"]["dispatched"] is False
                    assert "foreground_completion" not in result["data"]
                assert not s._require_runtime().attempts.list_attempts() and not h["adapters"]
                assert s._foreground_cycle_owner is None and not s._coo_action_tasks
            finally:
                s._closing = False
    asyncio.run(run())


@pytest.mark.parametrize("edge", ["arm_before_guard", "receipt_before_guard", "worker_before_guard",
    "binding_before_provider", "queued_mode_before_guard", "arm_after_commit", "queued_after_commit"])
def test_exact_request_snapshot_fences_drift_at_real_admission(tmp_path, short_socket_root, monkeypatch, edge):
    async def run():
        queued = edge.startswith("queued")
        async with real_factory(tmp_path, short_socket_root, monkeypatch, harness=not queued) as (s, owner, f, h):
            if edge == "arm_before_guard":
                h["before_guard"] = lambda: setattr(s, "config", dataclasses.replace(s.config, coo_autonomy_armed=False, coo_operator_harness_armed=False))
            elif edge == "receipt_before_guard":
                h["before_guard"] = lambda: h.update(valid_receipt=False)
            elif edge == "worker_before_guard":
                h["before_guard"] = lambda: setattr(s, "config", dataclasses.replace(s.config, worker_id="missing-worker"))
            elif edge == "binding_before_provider":
                h["before_binding"] = lambda: s._coo_execution_binding.update(model="changed")
            elif edge == "queued_mode_before_guard":
                # Both snapshots are nondriving: comparing only bool would miss this.
                old_binding = s._require_current_coo_binding()
                def native():
                    monkeypatch.setattr(s, "_require_current_coo_binding", lambda: {
                        **old_binding, "operator_execution_profile_id": NATIVE_RETURN_TX5_EXECUTION_PROFILE})
                h["before_guard"] = native
            elif edge == "arm_after_commit":
                h["after_commit"] = lambda: setattr(s, "config", dataclasses.replace(s.config, coo_autonomy_armed=False, coo_operator_harness_armed=False))
            else:
                h["after_commit"] = lambda: setattr(s, "config", dataclasses.replace(s.config, coo_autonomy_armed=False))
            result = await invoke(s, owner, f)
            assert result["ok"] is False, result
            post = edge.endswith("after_commit")
            expected = "effect_unknown" if post else "backend_unavailable" if edge == "binding_before_provider" else "backend_refused"
            assert result["error"]["code"] == expected, result["error"]
            assert len(s._require_runtime().jobs.list_jobs()) == (1 if post else 0)
            assert not s._require_runtime().attempts.list_attempts() and not h["adapters"]
            assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


def test_frozen_harness_off_root_cannot_fall_through_to_sealed_worker(tmp_path, short_socket_root, monkeypatch):
    async def run():
        async with real_factory(tmp_path, short_socket_root, monkeypatch, harness=False) as (s, owner, f, h):
            async with scope._session_bridge_foreground_dispatch(s._require_runtime(), f, lambda: None) as op:
                receipt = await owner.handle_frame(f)
                assert receipt["ok"] and "foreground_completion" not in receipt["data"]
                root_id = receipt["data"]["job_id"]
                s.config = dataclasses.replace(s.config, coo_operator_harness_armed=True)
                s._coo_execution_binding = s._load_coo_execution_binding()
                s._register_worker()
                root = s._require_runtime().jobs.get_job(root_id)
                assert s._require_current_coo_binding()["operator_harness_armed"] is True
                assert s._coo_binding_for_root(root)["operator_harness_armed"] is False
                async with s._foreground_cycle_scope(op) as drive:
                    assert drive
                    result = await s._drive_foreground_cycle(op, root_id)
                assert result == {"state": "NO_ACTION", "root_job_id": root_id, "delivery": "INCOMPLETE"}
                assert len(s._require_runtime().jobs.list_jobs()) == 1
                assert not s._require_runtime().attempts.list_attempts() and not h["adapters"]
    asyncio.run(run())
