"""Trusted constructor propagation only; no live host or profile activation."""
from types import SimpleNamespace

import pytest

from control_plane import executive_worker_broker as broker
from control_plane.executive_service import ExecutiveControlService
from control_plane.fabric_attended_canary import AttendedControlProbeSource
from control_plane.fabric_attended_routing import AttendedWorkPlacement, placement_member
from control_plane.model_router import ModelRouter, RoutingPolicyError
from scripts import executive_os_phase1c as cli
from tests.test_ceo_submit_armed_composition import _raw, _write
from tests.test_executive_fabric_composition import root_stats
from tests.test_executive_fabric_phase1c import compose, staged
from tests.test_fabric_attended_routing import router, BINDING


def selected():
    return AttendedWorkPlacement('minimax.attended', BINDING, 'minimax-read')


def finite_configuration(tmp_path):
    # Explicit protected-definition issuer fixture; real source/hash checks
    # are covered by test_fabric_attended_probe_join.
    def configuration(self, physical):
        return {}, {'run_root':str(tmp_path/'finite'/physical.worker_id/'runs')}, {}
    return configuration


def sources(tmp_path, monkeypatch):
    monkeypatch.setattr(AttendedControlProbeSource, 'configuration', finite_configuration(tmp_path))
    raw = _raw(tmp_path)
    raw.update(staged(tmp_path, raw))
    loaded = cli.load_control_config(_write(tmp_path, raw))
    physical = cli._staged_fabric_binding_source(loaded)
    probe = AttendedControlProbeSource.from_startup(tmp_path / 'control.json', loaded,
                                                  {'config_sha256': 'a' * 64})
    return loaded, physical, probe


def forbid_clients(monkeypatch):
    monkeypatch.setattr(broker, 'WorkerBrokerClient',
                        lambda *a, **kw: pytest.fail('unqualified placement reached a client'))


def test_trusted_factory_reaches_existing_attended_union_and_mode(tmp_path, monkeypatch, root_stats, router):
    raw, physical, probe = sources(tmp_path, monkeypatch)
    raw['coo_autonomy_armed'] = True
    probe = AttendedControlProbeSource.from_startup(tmp_path / 'control.json', raw,
                                                  {'config_sha256': 'a' * 64})
    monkeypatch.setattr(ModelRouter, 'load', classmethod(lambda cls, *a, **kw: router))
    service, mixed, _ = compose(tmp_path, monkeypatch, raw,
        fabric_worker_binding_source=physical, fabric_attended_probe_source=probe,
        attended_work_placements=(selected(),))
    assert service.config.coo_attended_work_placements == (selected(),)
    binding = ExecutiveControlService._load_coo_execution_binding(service)
    assert placement_member(router, selected()) in binding['work_placement_union']
    assert binding['provider'] == 'codex'
    assert mixed.primary is mixed.owners[service.config.worker_id]
    assert mixed.primary.runs_root==raw['worker_runs_root']
    for physical_binding in physical.bindings:
        owner=mixed.owners[physical_binding.worker_id]
        assert owner.runs_root==tmp_path/'finite'/physical_binding.worker_id/'runs'
        assert owner.shared_run_gid==physical_binding.worker_gid
    assert ExecutiveControlService._foreground_execution_state(service, binding=binding).mode == 'ATTENDED_WORK'


@pytest.mark.parametrize('placements', [None, [], ({'model_alias': 'minimax.attended'},), (selected(),) * 7])
def test_untyped_or_unbounded_refuses_before_client(monkeypatch, placements):
    forbid_clients(monkeypatch)
    with pytest.raises(cli.ServiceError, match='bounded typed'):
        cli._service_from_config({}, attended_work_placements=placements)


@pytest.mark.parametrize('missing', ['physical', 'probe'])
def test_placements_require_both_owner_sources(tmp_path, monkeypatch, root_stats, missing):
    raw, physical, probe = sources(tmp_path, monkeypatch)
    forbid_clients(monkeypatch)
    with pytest.raises(cli.ServiceError, match='binding and startup probe'):
        cli._service_from_config(raw, attended_work_placements=(selected(),),
            fabric_worker_binding_source=None if missing == 'physical' else physical,
            fabric_attended_probe_source=None if missing == 'probe' else probe)


def test_current_disabled_paid_profile_stays_refused(tmp_path, monkeypatch, root_stats):
    raw, physical, probe = sources(tmp_path, monkeypatch)
    forbid_clients(monkeypatch)
    with pytest.raises(RoutingPolicyError, match='attended model alias refused'):
        cli._service_from_config(raw, attended_work_placements=(selected(),),
            fabric_worker_binding_source=physical, fabric_attended_probe_source=probe)


def test_json_cannot_select_typed_host_placements(tmp_path):
    raw = _raw(tmp_path)
    raw['coo_attended_work_placements'] = [{'model_alias': 'minimax.attended'}]
    with pytest.raises(cli.ServiceError):
        cli.load_control_config(_write(tmp_path, raw))


def test_default_factory_preserves_ordinary_route(tmp_path, monkeypatch):
    raw = cli.load_control_config(_write(tmp_path, _raw(tmp_path)))
    service, supervisor, _ = compose(tmp_path, monkeypatch, raw)
    assert service.config.coo_attended_work_placements == ()
    assert type(supervisor.adapter) is broker.RemoteCodexWorkerAdapter
    binding = ExecutiveControlService._load_coo_execution_binding(service)
    assert len(binding['work_placement_union']) == 2
    assert ExecutiveControlService._foreground_execution_state(service, binding=binding).mode == 'QUEUED_AUTONOMY_OFF'
