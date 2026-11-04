"""Exercise actual primary/Fabric supervisor composition without host effects."""
import dataclasses
import json
import os
from pathlib import Path

import pytest
from control_plane import workspace_source_join
import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from control_plane.agentos_product_acceptance_basis import AgentOsProductAcceptanceBasisReader
from control_plane.product_acceptance_review_owner import ProductAcceptanceReviewBasisOwner
from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
from scripts import executive_os_phase1c as cli
from tests import test_executive_coo_host as coo
from tests import test_executive_fabric_phase1c as fabric
from tests.executive_installed_control_fixture import spawn_workspace_room_listener, unix_listener
from tests.test_workspace_read_app import _workspace_policy
from tests.test_c1_ceo_ingress_composition import _raw

root_stats = fabric.root_stats


def configured(tmp_path, monkeypatch, selected):
    owner, _, _, _ = coo.setup(tmp_path)
    raw = _raw(tmp_path)
    raw["shared_run_gid"] = os.getgid()  # Use this test process actual writable group.
    raw.update(ceo_ingress_app_peer_uid=max(raw["control_uid"], raw["worker_uid"],
        raw["ceo_ingress_peer_uid"], *raw["allowed_peer_uids"]) + 1, ceo_ingress_app_armed=False,
        ceo_ingress_app_macro_root=tmp_path / "macro",
        workspace_control_room={"transport": "unix",
                                "socket_path": "/var/run/mastermind-executive/workspace-control-room.sock",
                                "launchd_socket_name": "WorkspaceControlRoom",
                                "allowed_peer_uids": [raw["control_uid"]]},
        workspace_acquisition={}, workspace_resource_policy=json.loads(json.dumps(dataclasses.asdict(_workspace_policy()))),
        ceo_ingress_app_boot_python=tmp_path / "sealed-python", executive_mcp_profile="web_ceo_v2",
        coo_principal_armed=True, coo_principal_dialogue_armed=selected)
    authority = {"schema": "mastermind.workspace_acquisition_bindings.v1", "profiles": {
        key: {"enabled": False, "binding": None} for key in ("web", "mac")}}
    monkeypatch.setattr(cli, "_attest_app_boot_runtime", lambda p: p)
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    fake_sockets = {}
    listener_factory = fabric._workspace_aware_listener(raw)

    def tracked_factory(name):
        listener = listener_factory(name)
        if name == "WorkspaceControlRoom" and listener is not None and not isinstance(listener, type(object())):
            fake_sockets[name] = listener
        return listener

    monkeypatch.setattr(cli, "activate_launchd_socket", tracked_factory)
    monkeypatch.setattr(workspace_source_join, "build_workspace_composer", lambda **kw: lambda stamp: {})
    return raw, dict(workspace_acquisition_loader=lambda: authority, coo_source=owner.source), fake_sockets


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("mixed", [False, True])
def test_actual_host_selects_review_basis_on_the_same_runtime(tmp_path, monkeypatch, root_stats, selected, mixed):
    raw, options, fake_sockets = configured(tmp_path, monkeypatch, selected)
    try:
        monkeypatch.setattr(AgentOsProductAcceptanceBasisReader, "read",
            lambda *a, **kw: pytest.fail("composition must not read source or launch a review"))
        if mixed:
            options["fabric_worker_binding_source"] = cli._staged_fabric_binding_source(
                {**raw, **fabric.staged(tmp_path, raw)})
        service, supervisor, _ = fabric.compose(tmp_path, monkeypatch, raw, **options)
        owners = supervisor.owners.values() if type(supervisor) is MixedExecutionOwnerSupervisor else [supervisor]
        for worker_owner in owners:
            review = worker_owner._product_acceptance_review_owner
            if not selected:
                assert review is None
            else:
                assert type(review) is ProductAcceptanceReviewBasisOwner
                assert review.runtime is worker_owner.runtime is supervisor.runtime
                assert type(review.reader) is AgentOsProductAcceptanceBasisReader
                assert review.reader._macro_root == raw["ceo_ingress_app_macro_root"]
                from integrations.executive_mcp.installed import InstalledBootPacketCollector
                assert type(review.reader._installed_context_owner) is InstalledBootPacketCollector
                assert review.reader._installed_context_owner._macro_root == raw["ceo_ingress_app_macro_root"]
        assert raw["ceo_ingress_app_armed"] is False
        assert service.config.coo_autonomy_armed is False
    finally:
        for listener in fake_sockets.values():
            listener.close()


def test_selected_host_retains_original_intent_in_actual_review_schema(tmp_path, monkeypatch, root_stats):
    from tests import test_product_acceptance_review_owner as review_fixture
    from control_plane.product_acceptance_review_owner import read_retained_product_review_input
    work = tmp_path / "work"
    host_root = tmp_path / "host"
    work.mkdir()
    host_root.mkdir()
    runtime, job, attempt, _, commission, _, basis, calls = review_fixture.fixture(work, monkeypatch)
    raw, options, fake_sockets = configured(host_root, monkeypatch, True)
    try:
        # Supply the original Runtime to the real captured host factory. All source
        # reads remain the existing deterministic Agent OS fixture, not a live CLI.
        with monkeypatch.context() as scoped:
            scoped.setattr(fabric.Runtime, "at", lambda path: runtime)
            _, supervisor, _ = fabric.compose(host_root, scoped, raw, **options)
        owner = supervisor._product_acceptance_review_owner
        selected = owner.select_and_retain(job=job, attempt=attempt, commission=commission)
        assert read_retained_product_review_input(runtime, job=job, attempt=attempt) == selected
        schema_path = supervisor._write_schema(host_root / "review-input", job=job,
            attempt=attempt, effective_grant={"fixture": True})
        body = json.loads(schema_path.read_text())["properties"]["role_result"]["properties"]
        assert body["schema_version"] == {"const": "mastermind.review_result/v2"}
        assert body["product_acceptance_proof"]["properties"]["acceptance_basis_digest"] == {
            "const": selected.expected.basis_digest}
        assert basis.entry["proof_obligations"][0]["required_outcome"] in supervisor._prompt(
            job, attempt, commission=commission.ref_dict(), inline_commission=commission.content.decode())
        assert len(calls) == 1
    finally:
        for listener in fake_sockets.values():
            listener.close()


def test_source_selection_cannot_retarget_between_host_and_supervisor_construction(tmp_path, monkeypatch, root_stats):
    raw, options, fake_sockets = configured(tmp_path, monkeypatch, True)
    try:
        original_root = raw["ceo_ingress_app_macro_root"]
        from types import SimpleNamespace
        from control_plane import executive_worker_broker
        from control_plane.executive_runtime import Runtime
        captured = {}
        def service(config, **bindings):
            captured.update(bindings)
            raw["ceo_ingress_app_macro_root"] = tmp_path / "foreign"
            return SimpleNamespace(config=config)
        monkeypatch.setattr(cli, "ExecutiveControlService", service)
        monkeypatch.setattr(executive_worker_broker, "WorkerBrokerClient", lambda *a, **kw: object())
        cli._service_from_config(raw, **options)
        runtime = Runtime.at(tmp_path / "selection-runtime")
        owner = captured["supervisor_factory"](runtime)._product_acceptance_review_owner
        assert owner.runtime is runtime
        assert owner.reader._macro_root == original_root
        assert owner.reader._macro_root != raw["ceo_ingress_app_macro_root"]
    finally:
        for listener in fake_sockets.values():
            listener.close()


@pytest.mark.parametrize("drift", ["missing_macro_root", "principal_disabled", "unsealed_source"])
def test_selected_host_refuses_incomplete_principal_binding(tmp_path, monkeypatch, root_stats, drift):
    raw, options, fake_sockets = configured(tmp_path, monkeypatch, True)
    try:
        if drift == "missing_macro_root":
            del raw["ceo_ingress_app_macro_root"]
        elif drift == "principal_disabled":
            raw["coo_principal_armed"] = False
        else:
            options["coo_source"] = object()
        with pytest.raises(cli.ServiceError):
            fabric.compose(tmp_path, monkeypatch, raw, **options)
    finally:
        for listener in fake_sockets.values():
            listener.close()


def test_selected_r2_host_preserves_ordinary_review_without_declared_acceptance(tmp_path, monkeypatch, root_stats):
    from tests import test_executive_os_phase1fc as phase
    from control_plane.product_acceptance_review_owner import AGGREGATE
    work = tmp_path / "ordinary"
    host_root = tmp_path / "host"
    work.mkdir()
    host_root.mkdir()
    runtime, cycle, dispatches, root, _, _, _ = phase._cycle_through_completed_work(
        work, intent_id="CEO-ORDINARY-REVIEW", review_workers=["worker-b"])
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    attempt = dispatches[-1].attempt
    job = runtime.jobs.get_job(attempt.job_id)
    raw, options, fake_sockets = configured(host_root, monkeypatch, True)
    try:
        monkeypatch.setattr(AgentOsProductAcceptanceBasisReader, "read",
            lambda *a, **kw: pytest.fail("ordinary review must not acquire an acceptance basis"))
        with monkeypatch.context() as scoped:
            scoped.setattr(fabric.Runtime, "at", lambda path: runtime)
            _, supervisor, _ = fabric.compose(host_root, scoped, raw, **options)
        assert supervisor._product_acceptance_review_owner.select_and_retain(
            job=job, attempt=attempt, commission=None) is None
        assert runtime.events.list_events(aggregate_type=AGGREGATE,
        aggregate_id=attempt.attempt_id) == []
        assert supervisor._product_acceptance_review_suffix(job, attempt) == ""
    finally:
        for listener in fake_sockets.values():
            listener.close()
