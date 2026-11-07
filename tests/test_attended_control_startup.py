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


@pytest.mark.parametrize('configured', [False, True])
def test_startup_composes_byok_host_reader_without_attended_admission(tmp_path, monkeypatch, root_stats, configured):
    import hashlib
    import json
    from test_fabric_remote_composition import observation_document
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    from common import workspace_byok_read_contract as wire
    raw, _, captured = setup_startup(tmp_path, monkeypatch, probe=False)
    if configured:
        data = observation_document(tmp_path)
        contents = json.dumps(data).encode()
        path = tmp_path / 'hermes-bindings.json'; path.write_bytes(contents); path.chmod(0o600)
        raw.update(fabric_bindings_path=str(path), fabric_bindings_sha256=hashlib.sha256(contents).hexdigest())
    calls = []
    async def read(client):
        calls.append(client)
        return wire.unavailable()
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'read_hermes_roles', read)
    asyncio.run(cli._serve_from_config(tmp_path / 'control.json'))
    assert captured['served'] and captured['fabric_worker_binding_source'] is None
    assert captured['attended_work_placements'] == ()
    assert calls == []
    reader = captured['byok_roles_reader']
    if configured:
        assert asyncio.run(reader()) == wire.unavailable()
        assert len(calls) == 1
    else:
        assert reader is None


def test_byok_source_does_not_widen_paid_and_attended_composition(tmp_path, monkeypatch, root_stats):
    from control_plane import executive_paid_fabric_composition as paid
    setup_startup(tmp_path, monkeypatch, probe=False)
    monkeypatch.setattr(paid, 'installed_paid_source', lambda *a, **kw: object())
    monkeypatch.setattr(cli, '_load_control_environment_attestation',
                        lambda *a, **kw: pytest.fail('mixed source reached host attestation'))
    with pytest.raises(cli.ServiceError, match='cannot replace or mix'):
        asyncio.run(cli._serve_from_config(tmp_path / 'control.json'))


def paid_metadata_startup(tmp_path, monkeypatch):
    """Real source readers over temporary custody fixtures; no live owner."""
    import json
    from control_plane import executive_paid_fabric_composition as paid
    from tests.test_executive_fabric_composition import installed
    from tests.test_fabric_remote_composition import host_read_document
    from tests.test_paid_fabric_owner_wiring import material

    raw, _, captured = setup_startup(tmp_path, monkeypatch, probe=False)
    metadata_directory = tmp_path / 'metadata-only'
    metadata_directory.mkdir()
    metadata_path, metadata_digest = installed(metadata_directory,
        json.dumps(host_read_document(metadata_directory)).encode())
    raw.update(fabric_bindings_path=str(metadata_path),
               fabric_bindings_sha256=metadata_digest)
    paid_directory = tmp_path / 'paid-source'
    paid_directory.mkdir()
    payload, *_ = material()
    paid_path, paid_digest = installed(paid_directory, json.dumps({
        'schema_version': paid.PAID_BINDINGS_SCHEMA,
        'bindings': [{
            'physical_binding': payload['paid_physical_binding'],
            'source_config': payload['paid_source_config'],
            'quota_class': 'paid-read',
        }],
    }).encode())
    # Relocate only this test's fixed path. The production installed-source
    # parser, pinned file read, closed schema and nominal owner remain real.
    monkeypatch.setattr(paid, 'PAID_INSTALLED_BINDINGS', paid_path)
    raw['canonical_paid_fabric'] = {
        'bindings_path': str(paid_path), 'bindings_sha256': paid_digest,
    }
    config_path = tmp_path / 'control.json'
    # The existing loader fixture has already normalized filesystem fields.
    config_path.write_text(json.dumps(raw, default=str))
    acquired = []
    original = paid.installed_paid_source
    def acquire(document, *, installed_control):
        source = original(document, installed_control=installed_control)
        acquired.append(source)
        return source
    monkeypatch.setattr(paid, 'installed_paid_source', acquire)
    return raw, captured, config_path, acquired


def test_installed_paid_metadata_startup_separates_final_service_arguments(
        tmp_path, monkeypatch, root_stats):
    from control_plane import executive_paid_fabric_composition as paid
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient

    raw, captured, config_path, acquired = paid_metadata_startup(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail('metadata-only startup attempted physical or provider work')
    monkeypatch.setattr(paid.PaidBindingSource, 'client_for', forbidden)
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'request', forbidden)
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'read_hermes_roles', forbidden)
    monkeypatch.setattr(cli, '_request_boot_autonomy_canary', forbidden)

    asyncio.run(cli._serve_from_config(config_path, _installed_control=True))

    assert captured['served'] is True  # The existing inert service stub only.
    assert len(acquired) == 1 and type(acquired[0]) is paid.PaidBindingSource
    assert captured['paid_worker_binding_source'] is acquired[0]
    assert acquired[0].expected_sha256 == raw['canonical_paid_fabric']['bindings_sha256']
    acquired[0]._current()
    assert captured['fabric_worker_binding_source'] is None
    assert captured['fabric_attended_probe_source'] is None
    assert captured['attended_work_placements'] == ()
    assert callable(captured['byok_roles_reader'])


def test_installed_paid_refuses_derived_attended_placement_before_startup_effects(
        tmp_path, monkeypatch, root_stats):
    from control_plane import fabric_attended_routing as attended

    raw, captured, config_path, acquired = paid_metadata_startup(tmp_path, monkeypatch)
    selections = []
    def derive(document):
        assert document is raw
        selections.append(document)
        return (selected(),)
    def forbidden(*args, **kwargs):
        pytest.fail('conflicting installed owners reached attestation or startup')
    monkeypatch.setattr(attended, 'installed_control_placements', derive)
    monkeypatch.setattr(cli, '_load_control_environment_attestation', forbidden)
    monkeypatch.setattr(cli, '_request_boot_autonomy_canary', forbidden)
    monkeypatch.setattr(cli, '_service_from_config', forbidden)

    with pytest.raises(cli.ServiceError, match='installed paid source cannot replace or mix'):
        asyncio.run(cli._serve_from_config(config_path, _installed_control=True))

    assert len(acquired) == len(selections) == 1
    assert captured == {}
