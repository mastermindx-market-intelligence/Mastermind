"""Native planner producers are an explicit Control opt-in, never a default.

Reproduces the retained defect: the real ``_service_from_config`` always supplies
a claim-aware adapter factory, and the supervisor used to derive a fresh
``v1`` producer preference from that factory's presence.  Runtime then minted a
native V1 producer binding, while the real default ``RemoteCodexOperatorAdapter``
carries no ``plan_contract`` at all, so ``_adapter_for_attempt`` refused before
any I/O with "claim-bound adapter plan contract differs from retained producer
binding".

These tests use the actual Control factory, the actual supervisor and the actual
default operator proxy.  The broker is inert and no provider or socket is ever
contacted; the only native adapter that can declare a plan contract is the
explicitly declared test fixture below.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from control_plane import executive_worker_broker as broker
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor,
    ExecutiveOperatorSupervisorError,
)
from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V1,
    PLAN_SCHEMA_V3,
    PLAN_SCHEMA_V4,
    PLAN_SCHEMA_V5,
)
from control_plane.executive_runtime import (
    AttemptLease,
    AttemptStatus,
    Runtime,
    StateConflict,
)
from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
from scripts import executive_os_phase1c as cli
from test_ceo_submit_armed_composition import _raw, _write
from test_executive_operator_supervisor import _seed_dispatchable_operator_planner
from test_planner_producer_binding import _VersionedAdapter

EXPLICIT_VERSIONS = (PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5)


class _InertBrokerClient:
    """Stands in for the broker socket; any use at all is a test failure."""

    def __init__(self) -> None:
        self.uses: list[str] = []

    def __getattr__(self, name: str):
        self.uses.append(name)
        raise AssertionError(f"inert broker client was used via {name!r}")

    def __setattr__(self, name: str, value) -> None:
        if name == "uses":
            super().__setattr__(name, value)
            return
        raise AssertionError(f"inert broker client was mutated via {name!r}")


def capture(tmp_path, monkeypatch, *, runtime=None, prompt_source=None, raw=None, **kwargs):
    """Build the actual Control service and its actual operator supervisor."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    config = cli.load_control_config(
        _write(tmp_path, raw if raw is not None else _raw(tmp_path, worker_id="worker-a"))
    )
    captured: dict = {}
    client = _InertBrokerClient()
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **k: client)
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda name: object())

    def service(cfg, **bindings):
        captured.update(bindings)
        return SimpleNamespace(config=cfg)

    monkeypatch.setattr(cli, "ExecutiveControlService", service)
    result = cli._service_from_config(config, **kwargs)
    supervisor = captured["operator_supervisor_factory"](
        runtime if runtime is not None else object(),
        prompt_source if prompt_source is not None else object(),
    )
    return result, supervisor, client


def _job_created_payload(runtime, job_id: str) -> dict:
    with runtime.store.read() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM events WHERE event_type='JOB_CREATED' AND job_id=?",
            (job_id,),
        ).fetchall()
    assert len(rows) == 1
    return json.loads(str(rows[0]["payload_json"]))


def test_default_control_supervisor_prefers_no_native_producer(tmp_path, monkeypatch):
    """The real default composition offers Runtime a ``None`` producer preference."""

    _, supervisor, _ = capture(tmp_path / "composition", monkeypatch)
    assert supervisor.plan_schema_version == PLAN_SCHEMA_V1
    # This exact attribute is what executive_service reads for CooCycle.
    assert supervisor.fresh_planner_schema_version is None
    assert supervisor._claimed_adapter_factory is not None
    assert supervisor.adapter_factory is None


def supervisor_attributes(supervisor):
    return {
        "plan_schema_version": supervisor.plan_schema_version,
        "fresh_planner_schema_version": supervisor.fresh_planner_schema_version,
        "has_claimed": supervisor._claimed_adapter_factory is not None,
        "has_legacy": supervisor.adapter_factory is not None,
    }


def test_explicit_none_matches_omission_through_the_real_control_factory(
    tmp_path, monkeypatch
):
    """Explicit ``None`` is legacy omission, not a versioned producer."""

    runtime, _, _ = _seed_dispatchable_operator_planner(tmp_path / "seed", create_planner=False)
    _, omitted, _ = capture(tmp_path / "omitted", monkeypatch, runtime=runtime)
    _, explicit, _ = capture(
        tmp_path / "explicit", monkeypatch, runtime=runtime, plan_schema_version=None
    )
    assert supervisor_attributes(explicit) == supervisor_attributes(omitted)
    assert supervisor_attributes(explicit) == {
        "plan_schema_version": PLAN_SCHEMA_V1,
        "fresh_planner_schema_version": None,
        "has_claimed": True,
        "has_legacy": False,
    }


def test_default_producer_preference_mints_no_native_binding_and_reaches_the_proxy(
    tmp_path, monkeypatch
):
    """Control factory, Runtime and default-proxy regression with an inert broker.

    The default Control supervisor retains a ``None`` preference; Runtime records
    no native producer binding in the fresh planner's JOB_CREATED; and the actual
    default claim-aware factory builds its real ``RemoteCodexOperatorAdapter``,
    which ``_adapter_for_attempt`` accepts without a contract-label failure.
    """

    from test_executive_operator_supervisor import _PromptSource

    runtime, root, _ = _seed_dispatchable_operator_planner(
        tmp_path / "seed", create_planner=False
    )
    _, supervisor, client = capture(
        tmp_path / "composition", monkeypatch, runtime=runtime
    )
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
        # Exactly what executive_service passes to CooCycle.
        plan_schema_version=getattr(supervisor, "fresh_planner_schema_version", None),
    )
    assert runtime.jobs.get_planner_producer_binding(planner.job_id) is None
    created = _job_created_payload(runtime, planner.job_id)
    assert "planner_producer_binding" not in created
    assert "planner_producer_binding_digest" not in created

    dispatched = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    lease = AttemptLease(dispatched.attempt, dispatched.lease_token)
    supervisor.prompt_source = _PromptSource()
    profile = supervisor._requested_profile(planner, lease)
    adapter = supervisor._adapter_for_attempt(
        lease, profile, lambda _turn: "inert", recovery=False
    )
    # The real default proxy, carrying no plan_contract, is retained here.
    assert isinstance(adapter, RemoteCodexOperatorAdapter)
    assert adapter.client is client
    assert getattr(adapter, "plan_contract", None) is None
    assert supervisor._planner_schema(planner) == PLAN_SCHEMA_V1
    assert runtime.attempts.get_attempt(dispatched.attempt.attempt_id).status is AttemptStatus.CLAIMED
    # No provider, socket or broker traffic happened anywhere in this proof.
    assert client.uses == []


@pytest.mark.parametrize("version", EXPLICIT_VERSIONS)
def test_explicit_native_v1_and_friends_stay_bound_through_a_declared_adapter(
    tmp_path, version
):
    """Explicit opt-in keeps a genuine native producer binding end to end."""

    from test_executive_operator_supervisor import _PromptSource

    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, plan_schema_version=version, routing_capacity=True
    )
    binding = runtime.jobs.get_planner_producer_binding(planner.job_id)
    assert binding["plan_schema_version"] == version
    adapters = []

    def factory(_attempt, _requested, loader, *, recovery):
        assert recovery is False
        adapter = _VersionedAdapter(runtime, loader, version)
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory,
        prompt_source=_PromptSource(), plan_schema_version=version,
    )
    command = f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id, command_id=command))
    assert outcome.outcome == "TERMINAL"
    assert outcome.attempt.status is AttemptStatus.COMPLETED
    # The fixture genuinely declares the contract Runtime retained at creation.
    assert adapters[0].plan_contract == binding["native_result_contract"]["name"]
    assert runtime.jobs.get_planner_producer_binding(planner.job_id) == binding


def test_legacy_unbound_v1_is_distinct_from_explicit_native_v1(tmp_path):
    """The two V1s differ only in the retained producer binding."""

    from test_executive_operator_supervisor import _PromptSource

    legacy_runtime, legacy_root, legacy = _seed_dispatchable_operator_planner(
        tmp_path / "legacy"
    )
    native_runtime, native_root, native = _seed_dispatchable_operator_planner(
        tmp_path / "native", plan_schema_version=PLAN_SCHEMA_V1
    )
    assert legacy_runtime.jobs.get_planner_producer_binding(legacy.job_id) is None
    native_binding = native_runtime.jobs.get_planner_producer_binding(native.job_id)
    assert native_binding["plan_schema_version"] == PLAN_SCHEMA_V1

    # The same declared contract is acceptable to the legacy unbound planner...
    legacy_supervisor = ExecutiveOperatorSupervisor(
        legacy_runtime,
        claimed_adapter_factory=lambda *a, **k: SimpleNamespace(
            plan_contract="executive-plan-v1"
        ),
        prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V1,
    )
    legacy_lease = _claim(legacy_runtime, legacy_root, legacy)
    legacy_adapter = legacy_supervisor._adapter_for_attempt(
        legacy_lease, legacy_supervisor._requested_profile(legacy, legacy_lease),
        lambda _turn: "inert", recovery=False,
    )
    assert legacy_adapter.plan_contract == "executive-plan-v1"

    # ...but an unlabelled adapter is refused once V1 is genuinely bound.
    native_supervisor = ExecutiveOperatorSupervisor(
        native_runtime,
        claimed_adapter_factory=lambda *a, **k: SimpleNamespace(),
        prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V1,
    )
    native_lease = _claim(native_runtime, native_root, native)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="retained producer binding"):
        native_supervisor._adapter_for_attempt(
            native_lease, native_supervisor._requested_profile(native, native_lease),
            lambda _turn: "inert", recovery=False,
        )


def _claim(runtime, root, planner):
    dispatched = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    return AttemptLease(dispatched.attempt, dispatched.lease_token)


@pytest.mark.parametrize("version", EXPLICIT_VERSIONS)
def test_supervisor_refuses_explicit_version_without_claimed_factory(tmp_path, version):
    runtime = Runtime.at(tmp_path)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="claim-aware"):
        ExecutiveOperatorSupervisor(
            runtime, adapter_factory=lambda loader: object(),
            prompt_source=object(), plan_schema_version=version,
        )


@pytest.mark.parametrize("version", EXPLICIT_VERSIONS)
def test_trusted_control_refuses_explicit_version_without_claimed_factory(
    monkeypatch, version
):
    def forbidden(*args, **kwargs):
        pytest.fail("unbound plan selection reached the broker/socket")

    monkeypatch.setattr(broker, "WorkerBrokerClient", forbidden)
    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    with pytest.raises(cli.ServiceError, match="claim-bound"):
        cli._service_from_config({}, plan_schema_version=version)


def test_trusted_control_refuses_versioned_remote_binding_before_any_io(
    tmp_path, monkeypatch
):
    """The remote transport still has no qualified native contract custody."""

    def forbidden(*args, **kwargs):
        pytest.fail("versioned remote binding reached the broker/socket")

    monkeypatch.setattr(broker, "WorkerBrokerClient", forbidden)
    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    for version in EXPLICIT_VERSIONS:
        with pytest.raises(cli.ServiceError, match="claim-bound"):
            cli._service_from_config(
                {},
                plan_schema_version=version,
                claimed_operator_adapter_factory=forbidden,
                remote_operator_binding_source=lambda worker_id, job_id: None,
            )


def test_legacy_remote_binding_keeps_the_unbound_v1_path(tmp_path, monkeypatch):
    """Omission keeps both the primary and the remote legacy V1 paths."""

    runtime, _, _ = _seed_dispatchable_operator_planner(tmp_path / "seed", create_planner=False)
    _, supervisor, _ = capture(
        tmp_path / "composition",
        monkeypatch,
        runtime=runtime,
        remote_operator_binding_source=lambda worker_id, job_id: None,
    )
    assert supervisor.plan_schema_version == PLAN_SCHEMA_V1
    assert supervisor.fresh_planner_schema_version is None
    assert supervisor._claimed_adapter_factory is not None
    # The remote claim-aware transport is still the construction owner.
    assert supervisor._claimed_adapter_factory.__module__.endswith("remote_attempt_transport")


def test_selected_ceo_selection_still_requires_an_explicit_native_producer(
    tmp_path, monkeypatch
):
    """The default opt-out must not weaken the retained CEO selection guard."""

    from test_frontier_planner_binding import _selection

    runtime, root, _ = _seed_dispatchable_operator_planner(
        tmp_path / "seed", create_planner=False, frontier_selection=_selection()
    )
    _, supervisor, _ = capture(tmp_path / "composition", monkeypatch, runtime=runtime)
    preference = supervisor.fresh_planner_schema_version
    assert preference is None
    with pytest.raises(StateConflict, match="selected CEO"):
        runtime.jobs.create_cycle_planner(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-planner:0",
            plan_schema_version=preference,
        )
    assert [job.job_id for job in runtime.jobs.list_jobs()] == [root.job_id]
    assert runtime.attempts.list_attempts() == []
