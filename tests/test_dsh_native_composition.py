"""Pinned native composition and original owner selection; no installed authority."""
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from control_plane import executive_fabric_composition as composition
from control_plane import remote_attempt_transport as remote
from control_plane.native_conversation_binding import (
    NativeConversationRegistration, NativeConversationHostComposition,
    build_native_operator_selector,
)
from control_plane.native_conversation_result import DSH_NATIVE_RESULT_CONTRACT
from integrations.deepseek_harness.operator_adapter import NativeOperatorAdapter
from test_executive_fabric_composition import root_stats
from test_hermes_secretary_composition import dual_document, source_for
from test_dsh_native_remote_transport import _fresh
from test_remote_attempt_transport import HOST_A


def native_document(tmp_path):
    data = dual_document(tmp_path)
    data["schema_version"] = composition.NATIVE_CONFIG_SCHEMA_VERSION
    data["native_conversation"] = dict(
        schema=composition.NATIVE_OPERATOR_HOST_SCHEMA,
        registration=dict(worker_id="native-fixture", quota_class="dsh-native",
            model_alias="dsh.native.conversation", host_ref=HOST_A,
            worker_source_config_digest="c" * 64),
        harness_binary_digest="c" * 64, harness_version="native-test-only",
        expected_config_digest="d" * 64,
        workspace=dict(workspace_path="/selected-host/workspace", base_sha="a" * 40,
                       device=1, inode=2, uid=501, gid=20))
    return data


def test_v6_retains_hermes_and_the_same_enrolled_transport(tmp_path, root_stats):
    source = source_for(tmp_path, native_document(tmp_path))
    native = source.native_conversation_selection()
    assert native.registration.host_ref == source.hermes_meta_selection().host_ref == HOST_A
    assert source.hermes_secretary_selection().session_id == "native-session"
    assert source.hermes_meta_selection().session_id == "meta-session"
    assert native.transport is source._hermes_role_metadata_read.transport
    assert native.binding.transport is native.transport.binding
    assert native.binding.capabilities == NativeOperatorAdapter.describe_capabilities()
    assert source.remote_operator_binding(HOST_A, "native-fixture") is native.binding
    assert source.has_native_operator_binding is True
    assert source.has_execution_bindings is False  # incumbent Fabric inventory only
    assert source.bindings == () and not source._remote_index
    selected = source.native_conversation_composition()
    assert selected.registration is native.registration
    assert selected.require_current() is None
    for key in ((HOST_A, "foreign"), ("host-" + "f" * 64, "native-fixture"), (True, "native-fixture")):
        with pytest.raises(composition.FabricCompositionError):
            source.remote_operator_binding(*key)


def test_v5_cannot_acquire_native_ownership_by_presence(tmp_path, root_stats):
    data = dual_document(tmp_path)
    source = source_for(tmp_path, data)
    assert source.has_native_operator_binding is False
    assert source.native_conversation_selection() is None
    assert source.native_conversation_composition() is None
    with pytest.raises(composition.FabricCompositionError):
        source.remote_operator_binding(HOST_A, "native-fixture")
    data["native_conversation"] = {}
    with pytest.raises(composition.FabricCompositionError):
        source_for(tmp_path, data)


@pytest.mark.parametrize("fault", [
    "top_extra", "extra_grant", "capabilities", "missing", "wrong_schema",
    "registration_extra", "registration_missing", "registration_type", "source_digest",
    "host", "binary", "config_digest", "version", "workspace_extra", "workspace_missing",
    "workspace_relative", "workspace_alias", "workspace_double_root", "base", "inode",
    "bool_device", "bool_inode", "bool_uid", "negative_gid",
])
def test_v6_closed_facts_never_become_arbitrary_authority(tmp_path, root_stats, fault):
    data = native_document(tmp_path)
    slot = data["native_conversation"]
    if fault == "top_extra": data["enabled"] = True
    elif fault == "extra_grant": slot["armed"] = True
    elif fault == "capabilities": slot["capabilities"] = {"supports_fork": True}
    elif fault == "missing": slot.pop("workspace")
    elif fault == "wrong_schema": slot["schema"] = "mastermind.dsh_native_operator_host_binding/v2"
    elif fault == "registration_extra": slot["registration"]["current"] = True
    elif fault == "registration_missing": slot["registration"].pop("quota_class")
    elif fault == "registration_type": slot["registration"]["worker_id"] = True
    elif fault == "source_digest": slot["registration"]["worker_source_config_digest"] = True
    elif fault == "host": slot["registration"]["host_ref"] = "host-" + "f" * 64
    elif fault == "binary": slot["harness_binary_digest"] = "A" * 64
    elif fault == "config_digest": slot["expected_config_digest"] = False
    elif fault == "version": slot["harness_version"] = ""
    elif fault == "workspace_extra": slot["workspace"]["observed"] = True
    elif fault == "workspace_missing": slot["workspace"].pop("gid")
    elif fault == "workspace_relative": slot["workspace"]["workspace_path"] = "workspace"
    elif fault == "workspace_alias": slot["workspace"]["workspace_path"] = "/host/../workspace"
    elif fault == "workspace_double_root": slot["workspace"]["workspace_path"] = "//host/workspace"
    elif fault == "base": slot["workspace"]["base_sha"] = "A" * 40
    elif fault == "inode": slot["workspace"]["inode"] = 0
    elif fault.startswith("bool_"): slot["workspace"][fault[5:]] = True
    else: slot["workspace"]["gid"] = -1
    with pytest.raises(composition.FabricCompositionError):
        source_for(tmp_path, data)


@pytest.mark.parametrize("surface", ["source", "tls"])
def test_v6_withdrawal_refuses_the_original_selection(tmp_path, root_stats, surface):
    source = source_for(tmp_path, native_document(tmp_path))
    selected = source.native_conversation_composition()
    if surface == "source":
        source.path.write_bytes(source.path.read_bytes() + b" ")
    else:
        from pathlib import Path
        path = Path(source._native_conversation.transport.binding.client_key_path)
        path.write_bytes(b"replacement fixture material")
    with pytest.raises((composition.FabricCompositionError, RuntimeError, ValueError)):
        source.remote_operator_binding(HOST_A, "native-fixture")
    with pytest.raises((composition.FabricCompositionError, RuntimeError, ValueError)):
        selected.require_current()


def pinned_native(tmp_path, monkeypatch):
    claim = tmp_path / "claim"
    claim.mkdir()
    f, _old_host, calls = _fresh(claim, monkeypatch)
    config = tmp_path / "config"
    config.mkdir()
    data = native_document(config)
    data["native_conversation"].update(
        harness_binary_digest=f.requested.harness_binary_digest,
        harness_version=f.requested.harness_version,
        expected_config_digest=f.requested.expected_config_digest,
        workspace=asdict(f.requested.workspace))
    source = source_for(config, data)
    return f, source, calls


def test_pinned_producer_feeds_original_runtime_workspace_and_transport(tmp_path, monkeypatch, root_stats):
    f, source, calls = pinned_native(tmp_path, monkeypatch)
    selection = source.native_conversation_selection()
    selector = build_native_operator_selector(f.runtime, selection.registration, "codex-01")
    assert selector(f.dispatch.attempt, f.job) is True
    identity = remote.build_claimed_remote_workspace_identity_source(f.runtime, source.remote_operator_binding)
    assert identity(f.dispatch.attempt, f.job) == f.requested.workspace
    factory = remote.build_claimed_remote_operator_factory(f.runtime, source.remote_operator_binding)
    adapter = factory(f.dispatch.attempt, f.requested, lambda _: "original input", recovery=False)
    assert adapter.result_contract == DSH_NATIVE_RESULT_CONTRACT
    assert adapter.client.binding is selection.binding.transport
    assert adapter.client.identity["attempt_id"] == f.dispatch.attempt.attempt_id
    assert calls == []
    # Source withdrawal never admits another host or the primary endpoint.
    source.path.write_bytes(source.path.read_bytes() + b" ")
    with pytest.raises(remote.RemoteAttemptTransportError):
        factory(f.dispatch.attempt, f.requested, lambda _: "", recovery=False)
    assert calls == []


@pytest.mark.parametrize("field,value", [
    ("worker_id", "foreign"), ("quota_class", "foreign"),
    ("host_ref", "host-" + "f" * 64), ("worker_source_config_digest", "f" * 64),
])
def test_native_selector_refuses_mismatch_without_primary_fallback(tmp_path, monkeypatch, field, value):
    f, _host, _calls = _fresh(tmp_path, monkeypatch)
    registration = NativeConversationRegistration("native-fixture", "dsh-native",
        "dsh.native.conversation", HOST_A, "c" * 64)
    selector = build_native_operator_selector(f.runtime, replace(registration, **{field: value}), "codex-01")
    with pytest.raises(ValueError):
        selector(f.dispatch.attempt, f.job)


def test_native_selector_preserves_containment_after_model_withdrawal(tmp_path, monkeypatch):
    f, _host, _calls = _fresh(tmp_path, monkeypatch)
    registration = NativeConversationRegistration("native-fixture", "dsh-native",
        "dsh.native.conversation", HOST_A, "c" * 64)
    selector = build_native_operator_selector(f.runtime, registration, "codex-01")
    # Selection is historical owner routing; downstream factory still decides
    # fresh admission versus containment using the original Runtime owner.
    original = f.runtime.workers.get_quota_class
    def withdrawn(worker, quota):
        value = original(worker, quota)
        return replace(value, model="withdrawn") if value is not None else None
    monkeypatch.setattr(f.runtime.workers, "get_quota_class", withdrawn)
    assert selector(f.dispatch.attempt, f.job) is True


def control_supervisor(tmp_path, monkeypatch, runtime, native, source, primary="codex-01"):
    from scripts import executive_os_phase1c as cli
    from control_plane import executive_worker_broker as broker, native_conversation_binding as binding
    from test_ceo_submit_armed_composition import _raw, _write
    raw = cli.load_control_config(_write(tmp_path, _raw(tmp_path,
        worker_id=primary, coo_autonomy_armed=True, coo_operator_harness_armed=True,
        operator_harness_binary_digest="a" * 64, operator_harness_version="fixture-only")))
    captured, bound = {}, []
    client = object()
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **k: client)
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda *a, **k: object())
    def service(config, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(config=config)
    monkeypatch.setattr(cli, "ExecutiveControlService", service)
    def bind(actual, *, registration, current):
        assert registration == native.registration and current() is None
        bound.append(actual)
    monkeypatch.setattr(binding, "bind_installed_native_conversation", bind)
    result = cli._service_from_config(raw, autonomy_guard=lambda: None, initial_canary={},
        native_conversation_composition=native, remote_operator_binding_source=source)
    assert bound == []
    supervisor = captured["operator_supervisor_factory"](runtime, object())
    assert bound == [result]
    return supervisor, client


def test_installed_mixed_factory_keeps_native_on_the_original_host(tmp_path, monkeypatch, root_stats):
    f, source, calls = pinned_native(tmp_path, monkeypatch)
    control = tmp_path / "control"
    control.mkdir()
    supervisor, _client = control_supervisor(control, monkeypatch, f.runtime,
        source.native_conversation_composition(), source.remote_operator_binding)
    adapter = supervisor._claimed_adapter_factory(
        f.dispatch.attempt, f.requested, lambda _: "", recovery=False)
    assert adapter.result_contract == DSH_NATIVE_RESULT_CONTRACT
    assert adapter.client.binding is source.native_conversation_selection().binding.transport
    assert supervisor._workspace_identity(f.job, f.dispatch.attempt) == f.requested.workspace
    assert calls == []


def test_installed_mixed_factory_keeps_primary_client_and_local_workspace(tmp_path, monkeypatch):
    from test_executive_operator_supervisor import _seed_dispatchable_operator_planner
    from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path / "job")
    dispatched = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1", worker_id="worker-a")
    native = NativeConversationHostComposition(NativeConversationRegistration(
        "native-fixture", "dsh-native", "dsh.native.conversation", HOST_A, "c" * 64), lambda: None)
    def forbidden(*_args):
        pytest.fail("primary claim reached native host")
    control = tmp_path / "control"
    control.mkdir()
    supervisor, client = control_supervisor(control, monkeypatch, runtime, native, forbidden, primary="worker-a")
    requested = SimpleNamespace(worker_id="worker-a", provider="openai-codex", harness_kind="codex-app-server")
    adapter = supervisor._claimed_adapter_factory(dispatched.attempt, requested, lambda _: "", recovery=False)
    assert isinstance(adapter, RemoteCodexOperatorAdapter) and adapter.client is client
    identity = supervisor._workspace_identity(planner, dispatched.attempt)
    assert identity.workspace_path == planner.worktree and identity.base_sha == planner.constraints["base_sha"]


@pytest.mark.parametrize("value", [None, 0, 1, "false"])
def test_workspace_selector_refuses_nonboolean_without_local_fallback(tmp_path, monkeypatch, value):
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError
    from test_executive_operator_supervisor import _PromptSource, _seed_dispatchable_operator_planner
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    dispatched = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1")
    def forbidden(*_args):
        pytest.fail("invalid selector reached physical observation")
    supervisor = ExecutiveOperatorSupervisor(runtime, claimed_adapter_factory=forbidden,
        workspace_identity_source=forbidden, workspace_identity_selector=lambda *a: value,
        prompt_source=_PromptSource())
    monkeypatch.setattr(supervisor, "_git_head", forbidden)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="exact boolean"):
        supervisor._workspace_identity(planner, dispatched.attempt)


def primary_selector(runtime):
    return build_native_operator_selector(runtime, NativeConversationRegistration(
        "native-fixture", "dsh-native", "dsh.native.conversation", HOST_A, "c" * 64), "worker-a")


def test_primary_commission_keeps_local_source_with_native_selection_composed(tmp_path, monkeypatch):
    import asyncio
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
    from control_plane import executive_supervisor as owner
    from control_plane.executive_runtime import AttemptStatus
    from test_executive_operator_supervisor import (
        _ActiveAdapter, _CommissionPromptSource, _seed_dispatchable_operator_planner,
    )
    commission = b"# Original primary commission\n\nKeep the exact local source.\n"
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path, commission_content=commission)
    adapters, local_reads = [], []
    probe = owner._commission_git_probe
    def observed_probe(*a, **k):
        local_reads.append(True)
        return probe(*a, **k)
    monkeypatch.setattr(owner, "_commission_git_probe", observed_probe)
    def forbidden(*a, **k):
        pytest.fail("primary commission reached the native host or a remote source")
    monkeypatch.setattr(owner, "_fetch_remote_commission", forbidden)
    def factory(attempt, requested, loader, *, recovery):
        assert not recovery and attempt.worker_id == requested.worker_id == "worker-a"
        adapter = _ActiveAdapter(runtime, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime, claimed_adapter_factory=factory,
        workspace_identity_source=forbidden, workspace_identity_selector=primary_selector(runtime),
        prompt_source=_CommissionPromptSource())
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"))
    assert outcome.attempt.status is AttemptStatus.COMPLETED
    assert local_reads and len(adapters) == 1 and adapters[0].begin_turn_calls == 1
    assert commission.decode() in adapters[0].prompts[0]


def test_primary_recovery_keeps_original_local_commission_branch(tmp_path, monkeypatch):
    from control_plane import executive_supervisor as owner
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
    from control_plane.executive_supervisor import ExecutiveSupervisor, ReconcileStatus
    from control_plane.executive_runtime import AttemptStatus
    from test_executive_operator_supervisor import _seed_commission_bound_legacy_turn
    from test_ordinary_remote_operator_recovery import _recovery_factory
    clock, runtime, planner, dispatch, profile, commission, turn = _seed_commission_bound_legacy_turn(
        tmp_path, legacy_operation=False, production_prompt_source=True)
    adapters, local_reads = [], []
    probe = owner._commission_git_probe
    def observed_probe(*a, **k):
        local_reads.append(True)
        return probe(*a, **k)
    monkeypatch.setattr(owner, "_commission_git_probe", observed_probe)
    def forbidden(*a, **k):
        pytest.fail("primary recovery borrowed selected-host identity")
    monkeypatch.setattr(owner, "_fetch_remote_commission", forbidden)
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=_recovery_factory(runtime, profile, adapters),
        workspace_identity_source=forbidden, workspace_identity_selector=primary_selector(runtime),
        prompt_source=ExecutiveSupervisor(runtime, object(), inspector=object(), process_controller=object()))
    monkeypatch.setattr(supervisor, "_recovery_owner_identity", forbidden)
    clock.advance(3)
    recovered = supervisor.reconcile_restart()
    assert [row.status for row in recovered] == [ReconcileStatus.OPERATOR_RECOVERED]
    assert runtime.attempts.get_attempt(dispatch.attempt.attempt_id).status is AttemptStatus.COMPLETED
    assert local_reads and len(adapters) == 1 and adapters[0].recovery is True
    assert adapters[0].resume_calls == adapters[0].begin_turn_calls == 0
    assert len(runtime.attempts.list_attempts()) == 1


def test_installed_startup_carries_native_and_hermes_under_original_config_guard(tmp_path, monkeypatch, root_stats):
    import asyncio
    import hashlib
    import json
    from scripts import executive_os_phase1c as cli
    from test_attended_control_startup import setup_startup
    raw, _physical, captured = setup_startup(tmp_path, monkeypatch, probe=False)
    data = native_document(tmp_path)
    encoded = json.dumps(data).encode()
    path = tmp_path / "native-installed-composition.json"
    path.write_bytes(encoded)
    path.chmod(0o600)
    raw.update(fabric_bindings_path=str(path), fabric_bindings_sha256=hashlib.sha256(encoded).hexdigest())
    current = ["a" * 64]
    monkeypatch.setattr(cli, "_sha256_file", lambda _path: current[0])
    asyncio.run(cli._serve_from_config(tmp_path / "control.json"))
    assert captured["served"] and captured["fabric_worker_binding_source"] is None
    selected = captured["native_conversation_composition"]
    assert type(selected) is NativeConversationHostComposition
    assert selected.registration.worker_id == "native-fixture"
    assert selected.require_current() is None
    binding = captured["remote_operator_binding_source"](HOST_A, "native-fixture")
    assert binding.provider == "acp" and binding.harness_kind == "dsh-native-web-acp"
    assert captured["secretary_binding_source"].hermes_meta_selection().session_id == "meta-session"
    assert captured["byok_roles_reader"] is not None
    current[0] = "b" * 64
    with pytest.raises(cli.ServiceError, match="cannot rebind Control"):
        selected.require_current()
    current[0] = "a" * 64
    path.write_bytes(encoded + b" ")
    with pytest.raises(composition.FabricCompositionError):
        selected.require_current()


def test_native_cannot_replace_primary_before_any_broker_or_socket(tmp_path, monkeypatch):
    from scripts import executive_os_phase1c as cli
    from control_plane import executive_worker_broker as broker
    def forbidden(*a, **k):
        pytest.fail("owner collision reached a broker or listener")
    monkeypatch.setattr(broker, "WorkerBrokerClient", forbidden)
    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    selected = NativeConversationHostComposition(NativeConversationRegistration(
        "native-fixture", "dsh-native", "dsh.native.conversation", HOST_A, "c" * 64), lambda: None)
    with pytest.raises(cli.ServiceError, match="cannot replace"):
        cli._service_from_config({"worker_id": "native-fixture", "coo_operator_harness_armed": True},
            native_conversation_composition=selected, remote_operator_binding_source=forbidden)
