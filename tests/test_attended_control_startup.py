"""Inert original startup wiring; no service, credentials or provider effects."""
import asyncio
from types import SimpleNamespace
import pytest
from scripts import executive_os_phase1c as cli
from control_plane.fabric_attended_canary import AttendedControlProbeSource
from control_plane.model_router import ModelRouter, RoutingPolicyError
from tests.test_fabric_attended_factory_placement import selected, sources
from tests.test_executive_fabric_composition import root_stats
from tests.test_fabric_attended_routing import router


def setup_startup(tmp_path, monkeypatch, *, probe=True):
    from ops.executive_os import coo_principal_host, dialogue_wake_canary_control
    raw, physical, _ = sources(tmp_path,monkeypatch)
    if probe:
        raw['fabric_attended_probe'] = {'worker_config_path': str(tmp_path/'worker.json')}
    captured = {}
    monkeypatch.setattr(cli, 'load_control_config', lambda p: raw)
    monkeypatch.setattr(cli, '_load_control_environment_attestation', lambda *a, **kw: {'config_sha256': 'a'*64})
    monkeypatch.setattr(cli, '_bind_exact_worker_target_source', lambda *a, **kw: None)
    monkeypatch.setattr(cli, '_bind_hot_content_profile_source', lambda *a, **kw: None)
    monkeypatch.setattr(cli, '_ceo_admission_guard', lambda *a, **kw: lambda: None)
    monkeypatch.setattr(coo_principal_host, 'validate_control_coo', lambda raw: False)
    monkeypatch.setattr(dialogue_wake_canary_control, 'load_verified_profile', lambda **kw: None)
    async def serve():
        captured['served'] = True
    def factory(loaded, **kw):
        assert loaded is raw
        captured.update(kw)
        return SimpleNamespace(serve_until_stopped=serve)
    monkeypatch.setattr(cli, '_service_from_config', factory)
    return raw, physical, captured


def test_selected_startup_passes_original_physical_probe_and_tuple(tmp_path, monkeypatch, root_stats, router):
    raw, physical, captured = setup_startup(tmp_path, monkeypatch)
    monkeypatch.setattr(ModelRouter, 'load', classmethod(lambda cls, **kw: router))
    placements = (selected(),)
    asyncio.run(cli._serve_from_config(tmp_path/'control.json', attended_work_placements=placements))
    source = captured['fabric_worker_binding_source']
    assert source.path == physical.path and source.expected_sha256 == physical.expected_sha256
    assert captured['attended_work_placements'] is placements
    probe = captured['fabric_attended_probe_source']
    assert type(probe) is AttendedControlProbeSource
    probe.require_definition(raw)
    assert captured['served']


def test_staged_but_unselected_startup_stays_ordinary(tmp_path, monkeypatch, root_stats):
    _, _, captured = setup_startup(tmp_path, monkeypatch, probe=False)
    asyncio.run(cli._serve_from_config(tmp_path/'control.json'))
    assert captured.get('fabric_worker_binding_source') is None
    assert captured.get('attended_work_placements', ()) == ()
    assert captured['served']


@pytest.mark.parametrize('placements', [None, [], ({'model_alias':'minimax.attended'},), (selected(),)*7])
def test_invalid_selection_refuses_before_attestation_or_canary(tmp_path, monkeypatch, root_stats, placements):
    setup_startup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, '_load_control_environment_attestation', lambda *a, **kw: pytest.fail('invalid selection reached host read'))
    with pytest.raises(cli.ServiceError, match='bounded typed'):
        asyncio.run(cli._serve_from_config(tmp_path/'control.json', attended_work_placements=placements))


@pytest.mark.parametrize('missing', ['physical','probe'])
def test_selection_without_fixed_sources_refuses_before_host_read(tmp_path, monkeypatch, root_stats, missing):
    raw, _, _ = setup_startup(tmp_path, monkeypatch, probe=missing!='probe')
    if missing == 'physical':
        for key in ('fabric_bindings_path','fabric_bindings_sha256','fabric_bridge_armed','fabric_attended_probe'):
            raw.pop(key,None)
    monkeypatch.setattr(cli, '_load_control_environment_attestation', lambda *a, **kw: pytest.fail('unbound selection reached host read'))
    with pytest.raises(cli.ServiceError, match='binding and startup probe'):
        asyncio.run(cli._serve_from_config(tmp_path/'control.json', attended_work_placements=(selected(),)))


def test_current_disabled_catalogue_refuses_before_host_read(tmp_path, monkeypatch, root_stats):
    setup_startup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, '_load_control_environment_attestation', lambda *a, **kw: pytest.fail('disabled route reached host read'))
    with pytest.raises(RoutingPolicyError, match='attended model alias refused'):
        asyncio.run(cli._serve_from_config(tmp_path/'control.json', attended_work_placements=(selected(),)))
