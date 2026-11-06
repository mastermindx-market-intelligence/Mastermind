"""Offline refusal and observation proof; no provider or credential access."""
import copy
import json
import queue
from types import SimpleNamespace

import pytest

from ops.executive_os import provider_identity_probe as probe
from ops.executive_os.provider_readiness import PRODUCTION_MODEL
from ops.executive_os.provider_worker_slots import get_slot

SECRET = '__DO_NOT_EMIT_ACCOUNT_OR_SECRET__'


def models(cursor=None):
    return {'data': [{'model': PRODUCTION_MODEL, 'description': SECRET, 'id': SECRET}], 'nextCursor': cursor}


def limits(permission=False):
    return {'ordinaryUsageAllowed': permission, 'accountId': SECRET,
            'rateLimits': {'primary': {'usedPercent': 0, 'windowDurationMins': 300, 'resetsAt': 1999999999},
                           'credits': {'balance': SECRET}, 'limitName': SECRET}}


def test_backend_permission_is_observed_not_inferred():
    x = probe.normalize_model_capacity(models(), limits(False))
    assert x['capacity']['ordinary_usage_allowed'] is False
    assert x['capacity']['primary']['used_percent'] == 0
    assert x['model_catalog'] == {'listed_in_returned_page': True, 'complete': True}
    assert SECRET not in json.dumps(x)
    assert 'passed' not in x and 'readiness' not in x


def test_partial_page_and_null_fields_stay_unknown():
    x = probe.normalize_model_capacity({'data': [], 'nextCursor': SECRET}, {'rateLimits': {}})
    assert x['model_catalog'] == {'listed_in_returned_page': False, 'complete': False}
    assert x['capacity']['ordinary_usage_allowed'] is None
    assert x['capacity']['primary'] is None and x['capacity']['secondary'] is None
    assert SECRET not in json.dumps(x)


def test_codex_bucket_wins_over_legacy_and_never_exports_other_keys():
    r = limits(True)
    r['rateLimitsByLimitId'] = {'codex': {'primary': {'usedPercent': 100}}, SECRET: r['rateLimits']}
    x = probe.normalize_model_capacity(models(), r)
    assert x['capacity']['source_bucket'] == 'codex'
    assert x['capacity']['primary']['used_percent'] == 100
    assert x['capacity']['ordinary_usage_allowed'] is True
    assert SECRET not in json.dumps(x)


@pytest.mark.parametrize('field,value', [('usedPercent', True), ('usedPercent', float('nan')),
    ('usedPercent', -1), ('usedPercent', 101), ('usedPercent', 1.5),
    ('windowDurationMins', False), ('windowDurationMins', 0), ('resetsAt', True),
    ('resetsAt', -1), ('resetsAt', 2**63)])
def test_invalid_windows_refuse(field, value):
    r = limits(); r['rateLimits']['primary'][field] = value
    with pytest.raises(probe.IdentityProbeError, match='diagnostic_payload_invalid'):
        probe.normalize_model_capacity(models(), r)


@pytest.mark.parametrize('m,r', [({'data': [None]}, limits()), ({'data': [{'model': 'other'}] * 101}, limits()),
    ({'data': [], 'nextCursor': 7}, limits()),
    ({'data': [{'model': PRODUCTION_MODEL}] * 2}, limits()), ({'error': SECRET}, {'error': SECRET}),
    (models(), {'ordinaryUsageAllowed': SECRET}), (models(), {'rateLimitsByLimitId': []}),
    (models(), {'rateLimitsByLimitId': {'codex': None}, 'rateLimits': limits()['rateLimits']})])
def test_malformed_or_ambiguous_frames_refuse(m, r):
    with pytest.raises(probe.IdentityProbeError, match='diagnostic_payload_invalid'):
        probe.normalize_model_capacity(m, r)


def test_nullable_request_preserves_json_null():
    client = probe._Client.__new__(probe._Client)
    client._messages = queue.Queue(); client._messages.put({'id': 5, 'result': {'rateLimits': {}}})
    sent = []; client._send = sent.append
    client.request(5, 'account/rateLimits/read', None)
    assert sent == [{'id': 5, 'method': 'account/rateLimits/read', 'params': None}]


@pytest.fixture
def live(monkeypatch):
    state = SimpleNamespace(calls=[], closed=0, allowed=True, fail=None, binary_calls=0,
                            credential_calls=0, drift=None, status_calls=0)
    monkeypatch.setattr(probe, 'binary_identity', lambda path: binary(path))
    def binary(path):
        state.binary_calls += 1
        return {'sha256': 'changed' if state.drift == 'binary' and state.binary_calls > 1 else 'same'}
    def credential(path, **kwargs):
        state.credential_calls += 1
        return {'inode': 2 if state.drift == 'credential' and state.credential_calls > 1 else 1}
    monkeypatch.setattr(probe, 'credential_identity', credential)
    def status(*args, **kwargs):
        state.status_calls += 1
        return SimpleNamespace(returncode=0, stderr=b'Logged in using ChatGPT\n')
    monkeypatch.setattr(probe.subprocess, 'run', status)
    monkeypatch.setattr(probe, 'config_has_no_forced_auth_policy', lambda x: True)
    monkeypatch.setattr(probe, 'evaluate_identity', lambda **kwargs:
                        {'passed': state.allowed, 'refusal': None if state.allowed else 'company_plan_required'})
    class Client:
        def __init__(self, argv, env, cwd):
            state.argv = argv; state.cwd = cwd
        def request(self, n, method, params):
            state.calls.append((method, copy.deepcopy(params)))
            if method == state.fail:
                raise probe.IdentityProbeError(SECRET)
            if method == 'model/list': return models()
            if method == 'account/rateLimits/read': return limits()
            return {}
        def notify(self, method): state.calls.append((method, None))
        def close(self): state.closed += 1
    monkeypatch.setattr(probe, '_Client', Client)
    slot = get_slot('codex-01')
    state.kwargs = dict(binary=probe.INSTALLED_CODEX_BINARY, provider_home=slot.provider_home,
        expected_kind='device-auth', workspace_binding_class=slot.workspace_binding_class,
        worker_user=slot.worker_user, worker_group=slot.worker_group,
        worker_uid=slot.worker_uid, worker_gid=slot.worker_gid)
    return state


def test_default_identity_does_not_gain_diagnostic_rpc(live):
    assert probe.live_probe(**live.kwargs)['passed'] is True
    assert [x[0] for x in live.calls] == ['initialize', 'initialized', 'config/read', 'account/read']
    assert live.closed == 1


def test_opt_in_exact_order_null_params_and_no_readiness(live):
    result = probe.live_probe(**live.kwargs, diagnostic_slot_id='codex-01')
    assert [x[0] for x in live.calls] == ['initialize', 'initialized', 'config/read', 'account/read', 'model/list', 'account/rateLimits/read']
    assert live.calls[3][1] == {'refreshToken': False}
    assert live.calls[4][1] == {'limit': 100, 'includeHidden': False}
    assert live.calls[5][1] is None
    assert result['schema_version'] == 'mastermind.executive_provider_model_capacity_diagnostic/v1'
    assert result['observation_status'] == 'observed'
    assert result['diagnostic_only'] is True and result['readiness_issued'] is False
    assert 'passed' not in result and SECRET not in json.dumps(result)
    assert live.closed == 1 and live.status_calls == 2


def test_identity_denial_prevents_new_rpc(live):
    live.allowed = False
    result = probe.live_probe(**live.kwargs, diagnostic_slot_id='codex-01')
    assert result['observation_status'] == 'refused'
    assert result['refusal'] == 'company_plan_required'
    assert all(x[0] not in {'model/list', 'account/rateLimits/read'} for x in live.calls)
    assert live.closed == 1


@pytest.mark.parametrize('which', ['binary', 'credential'])
def test_identity_drift_cannot_deliver_observation(live, which):
    live.drift = which
    with pytest.raises(probe.IdentityProbeError, match=which + '_identity_changed_during_probe'):
        probe.live_probe(**live.kwargs, diagnostic_slot_id='codex-01')
    assert live.closed == 1


@pytest.mark.parametrize('method', ['initialize', 'config/read', 'account/read', 'model/list', 'account/rateLimits/read'])
def test_every_rpc_failure_closes_client(live, method):
    live.fail = method
    with pytest.raises(probe.IdentityProbeError):
        probe.live_probe(**live.kwargs, diagnostic_slot_id='codex-01')
    assert live.closed == 1


def test_internal_override_refused_before_filesystem_or_process(live):
    live.kwargs['worker_uid'] += 1
    with pytest.raises(probe.IdentityProbeError, match='diagnostic_arguments_invalid'):
        probe.live_probe(**live.kwargs, diagnostic_slot_id='codex-01')
    assert live.binary_calls == 0 and not live.calls


@pytest.mark.parametrize('extra', [['--binary', SECRET], ['--provider-home', SECRET],
    ['--worker-uid', '0'], ['--model', SECRET], ['--compare-seat-stdin'], ['--refusal-code-stdin'],
    ['--slot-id', 'codex-pro-01'], ['--expected-kind', SECRET]])
def test_cli_override_or_mixed_mode_refuses_without_echo(monkeypatch, capsys, extra):
    monkeypatch.setattr(probe, 'live_probe', lambda **kwargs: pytest.fail('must not launch'))
    rc = probe.main(['--model-capacity-diagnostic', '--slot-id', 'codex-01', '--expected-kind', 'device-auth', *extra])
    out = capsys.readouterr(); assert rc == 2 and not out.err and SECRET not in out.out
    doc = json.loads(out.out)
    assert doc['observation_status'] == 'refused' and doc['readiness_issued'] is False


def test_cli_binds_catalogued_slot(monkeypatch, capsys):
    captured = []
    monkeypatch.setattr(probe.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(probe.sys, 'platform', 'darwin')
    def fake(**kwargs):
        captured.append(kwargs)
        return probe.diagnostic_document('codex-01', probe.normalize_model_capacity(models(), limits()))
    monkeypatch.setattr(probe, 'live_probe', fake)
    assert probe.main(['--model-capacity-diagnostic', '--slot-id', 'codex-01', '--expected-kind', 'device-auth']) == 0
    assert captured[0]['worker_uid'] == 451
    assert captured[0]['provider_home'] == get_slot('codex-01').provider_home
    assert captured[0]['binary'] == probe.INSTALLED_CODEX_BINARY
    assert json.loads(capsys.readouterr().out)['readiness_issued'] is False


@pytest.mark.parametrize('flag', ['--model-capacity', '--model-capacity-diagnostic-extra',
                                 '--model-capacity-diagnostic=true'])
def test_abbreviated_or_extended_flag_refuses_safely(monkeypatch, capsys, flag):
    monkeypatch.setattr(probe, 'live_probe', lambda **kwargs: pytest.fail('must not launch'))
    assert probe.main([flag, '--slot-id', 'codex-01', '--expected-kind', 'device-auth']) == 2
    output = capsys.readouterr()
    assert not output.err
    assert json.loads(output.out)['refusal'] == 'diagnostic_arguments_invalid'
