"""Real admission/Runtime/OHF/retained supervisor; ambient host/provider inert.

The existing authenticated private-peer scope is exercised directly. This does
not claim a signed HTTP caller, installed host arm, provider login, physical
native process, Slack receipt or original-parent consumption.
"""
import asyncio
import dataclasses
import hashlib
import json
import os
import subprocess
import time
from types import SimpleNamespace

import pytest

from common import fresh_conversation_contract as wire
from common.session_bridge_private_contract import PRIVATE_SCHEMA
from control_plane import fresh_conversation as module
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError,
)
from control_plane.executive_runtime import JobStatus, Runtime
from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.foreground_operation import _session_bridge_foreground_dispatch
from control_plane.principal_projection import neutral_principal_projection
from control_plane.remote_codex_operator_adapter import codex_remote_capabilities
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from integrations.company_consultation_host import CompanyConsultationHost
from tests.test_executive_service import _config, _source_repository
from tests.test_native_retained_runtime import _NativeAdapter
from tests.test_session_bridge_installed import principal_frame
from tests.test_workspace_read_service import cache_fixture
from control_plane.workspace_read_service import WorkspaceReadService
from common.executive_workspace_contract import RESOURCE, SCOPE, PRINCIPAL_KEYS


class _ForbiddenBrokerTransport:
    def request_sync(self, *_args, **_kwargs):
        raise AssertionError("fresh conversation fixture forbids physical broker transport")


def case(tmp_path, principal=None, *, runtime_override=None, workspace_override=None, workspace_reader_override=None, work_ref_override=None):
    source, _ = _source_repository(tmp_path)
    content = b"# Original fresh conversation commission\nRead only; one retained native parent; no child dispatch.\n"
    (source / "commission.md").write_bytes(content)
    subprocess.run(["git", "-C", str(source), "add", "commission.md"], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "conversation source"], check=True)
    config = _config(tmp_path, worker_id="worker-a", worker_account_label="worker-a@company",
        worker_type="fixture", coo_autonomy_armed=True, coo_operator_harness_armed=True,
        coo_operator_model_alias="coo.operator.native-return",
        operator_harness_binary_digest="a" * 64, operator_harness_version="0.147.0")
    service = ExecutiveControlService(config, autonomy_guard=lambda: None)
    runtime = Runtime.at(config.runtime_root) if runtime_override is None else runtime_override
    if runtime_override is not None:
        assert type(runtime_override) is Runtime
        service.config = dataclasses.replace(config, runtime_root=runtime.store.root)
    service.runtime = runtime
    service._register_worker()
    adapters = []
    class InertNativeAdapter(_NativeAdapter, RemoteOperatorHarnessAdapter):
        # Provider/process/transport are explicit inert seams. Use the actual
        # RemoteAdapter guard implementation and check it at the same writes.
        def __init__(self, runtime, loader):
            _NativeAdapter.__init__(self, runtime, loader, cancel_during_collect=False)
            RemoteOperatorHarnessAdapter.__init__(self, _ForbiddenBrokerTransport(),
                turn_input_loader=loader, capabilities=codex_remote_capabilities())
            self.start_calls = 0
        def start_session(self, **kwargs):
            hook = getattr(service, "_fixture_before_native_io", None)
            if hook: hook()
            if self._fresh_effect_guard is not None: self._fresh_effect_guard()
            observation = super().start_session(**kwargs)
            self.start_calls += 1
            if getattr(service, "_fixture_lose_start_return", False):
                raise OSError("inert provider start return lost")
            return observation
        def begin_turn(self, **kwargs):
            from control_plane.operator_harness_wire import to_wire
            hook = getattr(service, "_fixture_before_turn_io", None)
            if hook: hook(kwargs)
            # Exercise the actual RemoteAdapter payload-bound prewrite selector,
            # while the native provider/process remains the declared inert seam.
            payload = {key: to_wire(kwargs[key]) for key in ("operation_id", "turn", "generation", "launch")}
            options = self._fresh_write_options("ohf-begin-turn", payload)
            if options: options["before_write"]("ohf-begin-turn", payload)
            return super().begin_turn(**kwargs)
        def _canonical_result(self, turn):
            value = json.loads(super()._canonical_result(turn))
            if self.begin_turn_calls > 1:
                value["summary"] = "Inert native follow-up answer."
            from control_plane.executive_orchestration_result import canonical_bytes
            return canonical_bytes(value).decode("utf-8")
    def factory(loader):
        adapter = InertNativeAdapter(runtime, loader)
        adapters.append(adapter)
        return adapter
    service.operator_supervisor = ExecutiveOperatorSupervisor(runtime, adapter_factory=factory,
        prompt_source=ExecutiveSupervisor(runtime, SimpleNamespace(inspector=object())))
    service._company_consultation_host = CompanyConsultationHost(runtime=runtime,
        repository_root=source, worker_uid=451, relay_socket_path=tmp_path / "inert-relay.sock",
        workspace_id="T0000000001", channel_id="C0000000001", native_return_armed=True)
    service._company_consultation_ready = True
    service._company_consultation_binding = object()  # ambient host readiness seam
    class Grounding:
        def observe(self):
            from control_plane.executive_ceo_ingress import BOOT_PACKET_SCHEMA
            return {"mastermind_sha": config.proof_base_sha, "macro_sha": "b" * 40,
                "boot_packet_schema": BOOT_PACKET_SCHEMA}
    if principal is None:
        raw = principal_frame()
        raw.update(issued_at=int(time.time()) - 1, expires_at=int(time.time()) + 600)
        principal = neutral_principal_projection(**{**raw, "scopes": tuple(raw["scopes"])})
    workspace_principal = (dataclasses.replace(principal, policy_id="workspace-test",
        resource=RESOURCE, scopes=(SCOPE,)) if workspace_override is None else workspace_override)
    expected = {key: list(workspace_principal.scopes) if key == "scopes" else getattr(workspace_principal, key)
        for key in PRINCIPAL_KEYS}
    def authorize(p): return p == expected
    authorize.binding_digest = lambda p: "e" * 64 if authorize(p) else None
    owners, clock, cache = cache_fixture(tmp_path)
    workspace = (WorkspaceReadService(cache=cache, runtime=runtime, authorize=authorize,
        armed={}, runtime_identity={}) if workspace_reader_override is None else workspace_reader_override)
    app = CeoIngressAppBinding(peer_uid=os.geteuid(), armed=True,
        grounding_provider=Grounding(), session_bridge_provider_factory=lambda r: None,
        workspace_read_provider_factory=lambda r: workspace)
    service._ceo_ingress_app_binding = app
    service._ceo_ingress_ready = True  # private peer/startup seam, no listener opened
    source_value = dict(schema_version="mastermind.executive_dialogue_source/v1",
        work_ref="WS:ONE" if work_ref_override is None else work_ref_override, commission_ref=dict(
            repository="mastermindx-market-intelligence/Mastermind", commit=config.proof_base_sha,
            path="commission.md", content_sha256=hashlib.sha256(content).hexdigest()), watch_mode="turn_watch_v1")
    service._ceo_ingress_dialogue_source_provider = lambda intent_id, work_ref: dict(source_value)
    request = dict(work_ref="WS:ONE" if work_ref_override is None else work_ref_override, operation_key="fresh-original-one", message="  新对话\nRead source.  ")
    owner = module.FreshConversationOwner(service, expected_policy=(principal.policy_id,
        principal.issuer_digest, principal.resource))
    owner._fixture_workspace_principal = workspace_principal
    owner._fixture_catalogue = owners, clock
    return service, runtime, owner, principal, request, adapters


def test_fresh_fixture_preserves_producer_guard_and_forbids_physical_transport(tmp_path):
    from control_plane.executive_orchestration_result import PLAN_SCHEMA_V3
    from tests.test_executive_operator_supervisor import (
        _PromptSource, _seed_dispatchable_operator_planner,
    )

    service, _, _, _, _, _ = case(tmp_path / "fresh")
    adapter = service.operator_supervisor.adapter_factory(lambda _turn: "")
    adapter.require_planner_producer(None)
    assert adapter.describe_capabilities() == codex_remote_capabilities()
    runtime, _, planner = _seed_dispatchable_operator_planner(
        tmp_path / "versioned", plan_schema_version=PLAN_SCHEMA_V3)
    supervisor = ExecutiveOperatorSupervisor(runtime,
        adapter_factory=lambda _loader: adapter, prompt_source=_PromptSource())
    before = runtime.events.list_events()
    with pytest.raises(ExecutiveOperatorSupervisorError, match="producer custody differs"):
        supervisor._require_adapter_contract(planner, adapter)
    assert runtime.events.list_events() == before
    assert adapter.start_calls == adapter.begin_turn_calls == 0
    with pytest.raises(AssertionError, match="forbids physical broker transport"):
        adapter.client.request_sync("ohf-validate", {})


async def preview(owner, principal, request):
    return await owner.preview(principal, request, workspace_principal=owner._fixture_workspace_principal)


async def create(owner, principal, request, preview, *, host=lambda: None):
    raw = dataclasses.asdict(principal)
    raw["scopes"] = list(raw["scopes"])
    workspace = dataclasses.asdict(owner._fixture_workspace_principal)
    workspace["scopes"] = list(workspace["scopes"])
    frame = dict(schema=wire.SCHEMA, operation="create", principal=raw,
        workspace_principal=workspace, arguments={**request, "preview_digest": preview["preview"]["digest"]})
    value = await owner.handle_frame(frame, host_current=host, reader=asyncio.StreamReader())
    if not value["ok"]:
        raise module.ConversationRefusal(value["error"]["code"],
            effect="UNKNOWN" if value["error"]["code"] == "effect_unknown" else "NONE")
    return value["data"]


async def cleanup(service):
    dispatch = service._native_operator_dispatch
    if dispatch is not None:
        # Stop only this inert fixture's retained ordinary lifecycle. This is
        # not a cancellation route exposed by the fresh conversation adapter.
        service._dispatch_tasks[dispatch.job_id].cancel()
        await asyncio.gather(*service._dispatch_tasks.values(), return_exceptions=True)


def test_real_fresh_admission_retention_original_status_and_no_replay(tmp_path, monkeypatch):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        try:
            before = runtime.events.list_events()
            prepared = await preview(owner, principal, request)
            assert prepared["effect"] == "NONE" and prepared["state"] == "PREVIEW_READY"
            assert runtime.events.list_events() == before and not adapters
            observed = []
            original = service._run_coo_cycle
            async def cycle(root):
                try: return await original(root)
                except Exception as exc:
                    observed.append((type(exc).__name__, [f.tb_frame.f_code.co_name for f in _tracebacks(exc)]))
                    raise
            monkeypatch.setattr(service, "_run_coo_cycle", cycle)
            try: first = await create(owner, principal, request, prepared)
            except module.ConversationRefusal:
                pytest.fail("finite source failure " + repr(observed) + " " + repr(service._dispatch_errors))
            assert first["state"] == "CREATED" and first["session"] and not first["parent_consumed"]
            assert len(runtime.jobs.list_jobs()) == 2 and len(runtime.attempts.list_attempts()) == 1
            assert len(adapters) == adapters[0].begin_turn_calls == 1
            selected = {key: request[key] for key in ("work_ref", "operation_key")}
            result = await owner.read(principal, selected)
            assert result["state"] == "CREATED" and result["result"]
            assert result["result"]["digest"] == wire.canonical_digest(result["result"]["envelope"])
            assert not result["can_send"] and not result["parent_consumed"]
            original_events = runtime.events.list_events()
            duplicate = await create(owner, principal, request, prepared)
            assert duplicate["locator"] == first["locator"] and duplicate["effect"] == "NONE"
            assert runtime.events.list_events() == original_events and adapters[0].begin_turn_calls == 1
            assert (await owner.status(dataclasses.replace(principal, subject_digest="f" * 64), selected))["state"] == "ABSENT"
            changed = {**request, "message": request["message"] + " "}
            with pytest.raises(module.ConversationRefusal):
                await create(owner, principal, changed, prepared)
            assert runtime.events.list_events() == original_events
            root = runtime.jobs.get_job(first["locator"]["root_job_id"])
            assert json.loads(root.objective)["message"] == request["message"]
            assert json.loads(root.objective)["mode"] == "fresh_conversation"
            assert json.dumps(root.objective, ensure_ascii=False)[1:-1] in adapters[0].prompts[0]
            assert root.attempt_limit == 1
            assert runtime.jobs.get_job(first["locator"]["job_id"]).status is JobStatus.RUNNING
        finally:
            await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["expired", "scope", "native_unarmed", "profile", "source", "revoked", "preview"])
def test_currentness_refuses_before_any_root_or_provider(tmp_path, fault):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        prepared = await preview(owner, principal, request)
        if fault == "expired": principal = dataclasses.replace(principal, expires_at=int(time.time()) - 1)
        elif fault == "scope": principal = dataclasses.replace(principal, scopes=("mastermind.executive.read",))
        elif fault == "native_unarmed": service._company_consultation_host.native_return_armed = False
        elif fault == "profile":
            service._coo_execution_binding = {**service._coo_execution_binding,
                "operator_execution_profile_id": "operator.appserver.readonly.docs-mcp.native-helper.v1"}
        elif fault == "source": service._ceo_ingress_dialogue_source_provider = lambda *_: None
        elif fault == "revoked": service._ceo_ingress_app_binding = dataclasses.replace(owner._app, armed=False)
        elif fault == "preview": prepared["preview"]["digest"] = "0" * 64
        before = runtime.events.list_events()
        with pytest.raises(Exception):
            await create(owner, principal, request, prepared)
        assert runtime.events.list_events() == before and not adapters
        assert not runtime.jobs.list_jobs() and not runtime.attempts.list_attempts()
    asyncio.run(run())


def test_post_admission_unknown_is_original_retained_state_not_replayed(tmp_path, monkeypatch):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        prepared = await preview(owner, principal, request)
        async def lost(_root_id):
            raise RuntimeError("inert dispatch fault")
        monkeypatch.setattr(service, "_run_coo_cycle", lost)
        with pytest.raises(module.ConversationRefusal) as failure:
            await create(owner, principal, request, prepared)
        assert failure.value.effect == "UNKNOWN"
        assert len(runtime.jobs.list_jobs()) == 1 and not runtime.attempts.list_attempts() and not adapters
        before = runtime.events.list_events()
        duplicate = await create(owner, principal, request, prepared)
        assert duplicate["state"] == "ADMITTED" and duplicate["session"] is None
        assert runtime.events.list_events() == before and not adapters
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["issuer", "subject", "client", "resource", "policy_generation", "host_generation"])
def test_dual_resource_identity_refuses_before_catalogue_or_job(tmp_path, monkeypatch, fault):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        workspace = owner._fixture_workspace_principal
        if fault == "issuer": principal = dataclasses.replace(principal, issuer_digest="f" * 64)
        elif fault == "subject": workspace = dataclasses.replace(workspace, subject_digest="f" * 64)
        elif fault == "client": workspace = dataclasses.replace(workspace, client_ref="f" * 64)
        elif fault == "resource": workspace = dataclasses.replace(workspace, resource=principal.resource)
        elif fault == "policy_generation": workspace = dataclasses.replace(workspace, policy_id="rotated-policy")
        else: service._ceo_ingress_app_binding = dataclasses.replace(owner._app)
        reader = owner._app.workspace_read_provider_factory(runtime)
        calls = []
        original = reader.cache.snapshot
        def observed():
            calls.append(True)
            return original()
        monkeypatch.setattr(reader.cache, "snapshot", observed)
        with pytest.raises(module.ConversationRefusal):
            await owner.preview(principal, request, workspace_principal=workspace)
        assert not calls and not adapters and not runtime.jobs.list_jobs() and not runtime.attempts.list_attempts()
    asyncio.run(run())


def _tracebacks(exc):
    item = exc.__traceback__
    while item is not None:
        yield item
        item = item.tb_next


def test_request_closed_controls_and_lossless_identity():
    valid = dict(work_ref="WS:EXECUTIVE-OS", operation_key="one", message=" \n中文\tmessage\r ")
    assert wire.validate_request(valid, operation="preview") == valid
    for change in ({"provider": "codex"}, {"message": "secret\x1b"}, {"message": "bad\ud800"},
                   {"message": "a" * 701}, {"work_ref": "latest"}, {"operation_key": True}):
        with pytest.raises(ValueError): wire.validate_request({**valid, **change}, operation="preview")
    assert wire.canonical_digest({"b": 1, "a": "中文"}) == wire.canonical_digest({"a": "中文", "b": 1})


@pytest.mark.parametrize("fault", ["request_closed", "real_expiry", "workspace_revoked", "start_return_lost"])
def test_first_io_currentness_and_unknown_never_report_created_or_replay(tmp_path, fault):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        state = {"live": True}
        if fault == "real_expiry":
            # A new short-lived fixture grant, not an extension of any issued
            # production deadline. Three seconds expired during allocation in
            # the retained earlier run; ten reaches the specific first-I/O hook.
            principal = dataclasses.replace(principal, expires_at=int(time.time()) + 10)
        prepared = await preview(owner, principal, request)
        def host():
            if not state["live"]: raise ValueError("original request ended")
        def before_io():
            if fault == "request_closed": state["live"] = False
            elif fault == "real_expiry": time.sleep(max(0, principal.expires_at-time.time()+0.02))
            elif fault == "workspace_revoked":
                owner._app.workspace_read_provider_factory(runtime).authorize = lambda _: False
        service._fixture_before_native_io = before_io
        service._fixture_lose_start_return = fault == "start_return_lost"
        with pytest.raises(module.ConversationRefusal) as failure:
            await create(owner, principal, request, prepared, host=host)
        assert failure.value.effect == "UNKNOWN"
        assert len(runtime.jobs.list_jobs()) == 2 and len(runtime.attempts.list_attempts()) == 1
        assert len(adapters) == 1 and adapters[0].begin_turn_calls == 0
        assert adapters[0].start_calls == (1 if fault == "start_return_lost" else 0)
        before = runtime.events.list_events()
        # Existing unknown state is read by the original namespace only.
        # Renewing this fixture's short token cannot restart a provider.
        principal = dataclasses.replace(principal, expires_at=int(time.time()) + 600)
        state["live"] = True
        selected = {key: request[key] for key in ("work_ref", "operation_key")}
        result = await owner.status(principal, selected)
        assert result["state"] == "RECONCILIATION_REQUIRED" and result["session"] is None
        assert runtime.events.list_events() == before and adapters[0].start_calls == (1 if fault == "start_return_lost" else 0)
    asyncio.run(run())
