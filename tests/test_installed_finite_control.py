"""Production wrapper selection; no service, canary or provider is started."""
from types import SimpleNamespace

import pytest

from scripts import executive_os_phase1c as service
from scripts import executive_os_phase1c_control_wrapper as wrapper
from tests.test_executive_fabric_composition import root_stats
from tests.test_attended_worker_definition import inputs
from control_plane.fabric_attended_routing import FINITE_DEFINITION_DIR, FINITE_SOCKET_PATH


def finite_raw():
    return dict(coo_autonomy_armed=True, coo_foreground_only=True,
        coo_operator_model_alias='coo.operator.readonly', fabric_bridge_armed=False,
        fabric_bindings_path=FINITE_DEFINITION_DIR+'/bindings.json', fabric_bindings_sha256='a'*64,
        fabric_attended_probe={'worker_config_path':FINITE_DEFINITION_DIR+'/worker.json'})


def test_exact_fixed_tuple_has_original_operation_and_no_caller_selectors():
    from control_plane.fabric_attended_routing import installed_control_placements
    items = installed_control_placements(finite_raw())
    assert len(items) == 1
    item = items[0]
    assert (item.model_alias, item.harness_binding_id, item.quota_class) == (
        'minimax.attended', 'minimax-token-plan.claude-code-anthropic', 'minimax-finite-read')
    assert item.qualification.operation_key == 'fabric-parent-native-operator-proof-01a11e90-v1'
    assert item.qualification.arguments_sha256 == '36678c742b06b0ce04aa2b6acc46cb8aba9eba82c322ca960611e2cbb2580f56'


@pytest.mark.parametrize('raw', [{}, {'coo_autonomy_armed':True},
    dict(finite_raw(), coo_autonomy_armed=False, coo_foreground_only=False)])
def test_ordinary_and_unarmed_staging_select_nothing(raw):
    from control_plane.fabric_attended_routing import installed_control_placements
    assert installed_control_placements(raw) == ()


@pytest.mark.parametrize('change', [
    {'coo_foreground_only':False}, {'coo_autonomy_armed':False},
    {'coo_operator_model_alias':'coo.operator.native-return'}, {'fabric_bridge_armed':True},
    {'fabric_attended_probe':{}}, {'fabric_bindings_sha256':'missing'},
    {'fabric_bindings_path':'/another/bindings.json'},
    {'fabric_attended_probe':{'worker_config_path':'/another/worker.json'}},
])
def test_invalid_selected_definition_refuses_instead_of_ordinary_fallback(change):
    from control_plane.fabric_attended_routing import installed_control_placements
    with pytest.raises((ValueError, service.ServiceError)):
        installed_control_placements(dict(finite_raw(), **change))


@pytest.mark.parametrize('edge', ['disabled', 'enabled', 'config_refused', 'profile_refused'])
def test_postexec_wrapper_calls_fixed_service_entry(monkeypatch, tmp_path, edge):
    from ops.executive_os import control_aead_profile as aead
    monkeypatch.setattr(wrapper, '_ROOT', tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(wrapper.SENTINEL_NAME, 'a'*64)
    monkeypatch.setattr('sys.argv', ['wrapper', '--post-exec', '--config', str(tmp_path/'control.json'),
        '--attestation', str(tmp_path/'attestation.json'), '--release-root', str(tmp_path)])
    seen=[]
    raw = {'reply_events': {'armed': edge != 'disabled'}}
    def load(path):
        assert path == tmp_path/'control.json'
        seen.append('config')
        if edge == 'config_refused':
            raise service.ServiceError('synthetic invalid configuration')
        return raw
    def activate(supplied, release):
        assert supplied is raw and release == tmp_path
        seen.append('profile')
        if edge == 'profile_refused':
            raise aead.AeadProfileError('synthetic invalid profile')
    monkeypatch.setattr(service, 'load_control_config', load)
    monkeypatch.setattr(aead, 'activate_if_enrolled', activate)
    monkeypatch.setattr(wrapper, 'attest_current_service_environment', lambda **kw: seen.append('attested'))
    monkeypatch.setattr(service, 'main', lambda *a, **k: pytest.fail('default CLI loses finite tuple'))
    monkeypatch.setattr(service, 'serve_installed_control', lambda path: seen.append(path) or 0, raising=False)
    if edge in ('config_refused', 'profile_refused'):
        with pytest.raises((service.ServiceError, aead.AeadProfileError)):
            wrapper._post_exec_main()
        assert seen == (['attested', 'config'] if edge == 'config_refused'
                        else ['attested', 'config', 'profile'])
    else:
        assert wrapper._post_exec_main() == 0
        assert seen == ['attested', 'config', 'profile', tmp_path/'control.json']


def test_fixed_entry_reaches_same_loaded_definition_and_original_guard(tmp_path, monkeypatch, root_stats):
    from tests.test_attended_control_startup import setup_startup
    # Exercise the real startup until its original autonomy guard. The guard
    # must refuse before a canary/client or service factory is called.
    raw, _, captured = setup_startup(tmp_path, monkeypatch)
    raw.update(finite_raw())
    physical = SimpleNamespace(bindings=(SimpleNamespace(worker_id='minimax-finite-01', provider='minimax', socket_path=FINITE_SOCKET_PATH),))
    monkeypatch.setattr(service, '_staged_fabric_binding_source', lambda loaded: physical)
    monkeypatch.setattr(service, '_sha256_file', lambda path: 'a'*64)
    called=[]
    def guard(*a, **kw):
        called.append(kw)
        raise service.AutonomyRefusal('synthetic invalid original receipt')
    monkeypatch.setattr(service, 'validate_runtime_guard_file', guard)
    monkeypatch.setattr(service, '_request_boot_autonomy_canary', lambda *a, **kw: pytest.fail('guard bypass'))
    assert service.serve_installed_control(tmp_path/'control.json') == 2
    assert len(called) == 1 and captured == {}


@pytest.mark.parametrize('edge', ['selected', 'drift', 'staged'])
def test_actual_wrapper_chain_binds_guard_to_selected_definition(tmp_path, monkeypatch, root_stats, edge):
    from tests.test_attended_control_startup import setup_startup
    raw, _, captured = setup_startup(tmp_path, monkeypatch)
    raw.update(finite_raw())
    if edge == 'staged':
        raw.update(coo_autonomy_armed=False, coo_foreground_only=False)
    physical = SimpleNamespace(bindings=(SimpleNamespace(worker_id='minimax-finite-01', provider='minimax', socket_path=FINITE_SOCKET_PATH),))
    monkeypatch.setattr(service, '_staged_fabric_binding_source', lambda loaded: physical)
    digest = ['a'*64]
    monkeypatch.setattr(service, '_sha256_file', lambda path: digest[0])
    events=[]
    def guard(*a, **kw):
        assert kw['own_config_sha256'] == 'a'*64
        events.append('guard')
        if edge == 'drift': digest[0]='b'*64
    monkeypatch.setattr(service, 'validate_runtime_guard_file', guard)
    async def canary(*a, **kw):
        events.append('canary')
        return {}
    monkeypatch.setattr(service, '_request_boot_autonomy_canary', canary)
    monkeypatch.setattr(wrapper, '_ROOT', tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(wrapper.SENTINEL_NAME, 'a'*64)
    monkeypatch.setattr('sys.argv', ['wrapper', '--post-exec', '--config', str(tmp_path/'control.json'),
        '--attestation', str(tmp_path/'attestation.json'), '--release-root', str(tmp_path)])
    monkeypatch.setattr(wrapper, 'attest_current_service_environment', lambda **kw: events.append('attested'))
    assert wrapper._post_exec_main() == (2 if edge == 'drift' else 0)
    if edge == 'drift':
        assert events == ['attested','guard'] and captured == {}
    elif edge == 'staged':
        assert events == ['attested'] and captured['served']
        assert captured['attended_work_placements'] == ()
    else:
        assert events == ['attested','guard','canary'] and captured['served']
        assert captured['attended_work_placements'][0].qualification.operation_key == 'fabric-parent-native-operator-proof-01a11e90-v1'


def test_control_delta_binds_actual_rendered_bytes_without_arming(inputs):
    from ops.executive_os import attended_worker_definition as render
    import hashlib
    inputs = dict(inputs, worker_id='minimax-finite-01', definition_dir=FINITE_DEFINITION_DIR, socket_path=FINITE_SOCKET_PATH)
    artifacts = render.build_finite_worker_artifacts(**inputs)
    delta = render.build_finite_control_delta(definition_dir=inputs['definition_dir'], worker_artifacts=artifacts)
    assert set(delta) == {'fabric_bridge_armed', 'fabric_bindings_path', 'fabric_bindings_sha256', 'fabric_attended_probe'}
    assert delta['fabric_bridge_armed'] is False
    assert delta['fabric_bindings_sha256'] == hashlib.sha256(artifacts['bindings.json']).hexdigest()
    assert delta['fabric_attended_probe']['worker_config_path'] == inputs['definition_dir']+'/worker.json'
    artifacts['worker.json'] += b' '
    with pytest.raises(render.AttendedDefinitionError):
        render.build_finite_control_delta(definition_dir=FINITE_DEFINITION_DIR, worker_artifacts=artifacts)


def test_delta_refuses_another_owner(inputs):
    from ops.executive_os import attended_worker_definition as render
    artifacts = render.build_finite_worker_artifacts(**inputs)
    with pytest.raises(render.AttendedDefinitionError):
        render.build_finite_control_delta(definition_dir=inputs['definition_dir'], worker_artifacts=artifacts)
