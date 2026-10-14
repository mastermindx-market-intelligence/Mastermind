import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


quota = load('quota_remote', 'quota_remote.py')
broker_module = load('account_quota_broker', os.environ.get('BROKER_SOURCE', 'lease_broker.py'))
NOW = 1791998400.0


def snapshot(**changes):
    row = dict(provider='glm', window='weekly', remaining_pct=0.0,
               source='PROVIDER_AUTHORITATIVE', observed_at=quota._iso(NOW - 30),
               reset_at=quota._iso(NOW + 3600))
    row.update(changes)
    return {'glm': {'accounts': {'empty': {'refreshed_at': NOW - 30, 'states': [row]},
                                 'spare': {'refreshed_at': NOW - 30, 'states': [dict(row, remaining_pct=60)]}}}}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / 'quota.json'
    path.write_text(json.dumps(snapshot()))
    monkeypatch.setattr(quota, 'CACHE_PATH', str(path))
    def forbidden(*args, **kwargs):
        pytest.fail('admission must never refresh quota, access credentials, or call network')
    for name in ('glm_accounts_state', '_live_glm', '_glm_accounts_dict', '_atomic_write'):
        monkeypatch.setattr(quota, name, forbidden)
    return path


def test_fresh_weekly_zero_excludes_only_exact_account(cache):
    assert quota.cached_glm_account_parked('empty', now_ts=NOW)
    assert not quota.cached_glm_account_parked('spare', now_ts=NOW)
    assert not quota.cached_glm_account_parked('absent', now_ts=NOW)


@pytest.mark.parametrize('changes,parked', [
    ({'window': '5h', 'remaining_pct': 5}, True),
    ({'remaining_pct': 5.01}, False),
    ({'remaining_pct': -1}, False),
    ({'remaining_pct': False}, False),
    ({'remaining_pct': float('nan')}, False),
    ({'remaining_pct': '0'}, False),
    ({'provider': 'other'}, False),
    ({'window': 'monthly'}, False),
    ({'source': 'LOCAL_RECONSTRUCTION'}, False),
    ({'observed_at': quota._iso(NOW - 601)}, False),
    ({'observed_at': quota._iso(NOW + 1)}, False),
    ({'reset_at': quota._iso(NOW)}, False),
    ({'reset_at': 'bad'}, False),
    ({'reset_at': None}, True),
])
def test_quota_provenance_and_boundaries(cache, changes, parked):
    cache.write_text(json.dumps(snapshot(**changes)))
    assert quota.cached_glm_account_parked('empty', now_ts=NOW) is parked


@pytest.mark.parametrize('payload', [{}, {'glm': None}, {'glm': {'accounts': []}},
                                     {'glm': {'accounts': {'empty': None}}}])
def test_unknown_never_fabricates_exhaustion(cache, payload):
    cache.write_text(json.dumps(payload))
    assert not quota.cached_glm_account_parked('empty', now_ts=NOW)


def test_stale_container_not_refreshed_or_rewritten(cache):
    payload = snapshot()
    payload['glm']['accounts']['empty']['refreshed_at'] = NOW - 601
    cache.write_text(json.dumps(payload))
    before = cache.read_bytes()
    assert not quota.cached_glm_account_parked('empty', now_ts=NOW)
    assert cache.read_bytes() == before


def make_broker(tmp_path, *, external=True):
    policy = tmp_path / 'accounts.yaml'
    policy.write_text('''schema: mastermind.provider_accounts.v1
providers:
  glm:
    enabled: true
    accounts:
      - {name: empty, per_account_cap: 2}
      - {name: spare, per_account_cap: 2}
''')
    return broker_module.Broker(db_path=str(tmp_path/'leases.db'),
        lock_path=str(tmp_path/'leases.lock'), accounts_path=str(policy),
        now_fn=lambda: NOW, check_pid=False, external_gates=external,
        grok_marker=str(tmp_path/'no-marker'), this_host='test',
        status_json=str(tmp_path/'status.json'))


def test_real_broker_candidate_filter(cache, tmp_path):
    br = make_broker(tmp_path)
    assert [a['name'] for a in br.grantable_accounts('glm')] == ['spare']
    assert br.pool_cap('glm') == 2


def test_real_broker_acquires_spare_with_original_root(cache, tmp_path):
    br = make_broker(tmp_path)
    got = br.acquire(orchestrator_id='original-root', pool='glm', task_class='census',
        host='test', pid=os.getpid(), ttl=600, wait=0, model='glm-5.3-flash')
    assert got.ok
    assert got.account == 'spare'
    assert got.orchestrator_id == 'original-root'


def test_explicit_empty_account_cannot_reach_spare(cache, tmp_path):
    br = make_broker(tmp_path)
    got = br.acquire(orchestrator_id='original-root', pool='glm', account='empty',
        task_class='census', host='test', pid=os.getpid(), wait=0, model='glm-5.3-flash')
    assert not got.ok


def test_existing_gate_disabled_test_mode_is_preserved(cache, tmp_path):
    br = make_broker(tmp_path, external=False)
    assert [a['name'] for a in br.grantable_accounts('glm')] == ['empty', 'spare']
