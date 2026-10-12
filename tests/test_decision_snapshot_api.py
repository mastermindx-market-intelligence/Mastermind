"""Real application routing and auth/cache integration, with only fixture evidence."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from portfolio import decision_snapshot as snapshots
from test_decision_snapshot import sealed


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app
    from app import response_cache
    monkeypatch.setattr(snapshots, '_ROOT', tmp_path)
    monkeypatch.setenv('MASTERMIND_VPS_AUTHORITATIVE', '1')
    monkeypatch.setenv('MASTERMIND_AUTH_TOKEN', 'fixture-operator')
    monkeypatch.delenv('MASTERMIND_SERVE_ONLY', raising=False)
    monkeypatch.setenv('MASTERMIND_RESP_CACHE_TTL', '60')
    response_cache.clear()
    yield TestClient(app)  # No lifespan startup: no scheduler/provider/process effects.
    response_cache.clear()


def get(client, params=None, authorized=True):
    return client.get('/api/decision-snapshot', params=params,
                      headers={'Authorization': 'Bearer fixture-operator'} if authorized else {})


def test_api_exists_and_absent_is_read_only(client, tmp_path):
    response = get(client)
    assert response.status_code == 200
    assert response.json()['status'] == 'ABSENT'
    assert response.json()['authority'] == {'write_permitted': False, 'execution_authority': False, 'numeric_target_authority': False}
    assert 'no-store' in response.headers['cache-control']
    assert not (tmp_path / 'data').exists()


def test_auth_runs_before_any_store_read(client, monkeypatch):
    monkeypatch.setattr(snapshots, 'read_projection', lambda *a, **k: pytest.fail('unauthorized storage access'))
    assert get(client, authorized=False).status_code == 401
    assert client.get('/api/decision-snapshot', headers={'Authorization': 'Bearer not-the-operator'}).status_code == 401


def test_cache_cannot_replay_authorized_evidence_to_guest(client):
    snapshots.persist_snapshot(sealed())
    authorized = get(client, {'section': 'book_truth'})
    assert authorized.status_code == 200 and authorized.json()['section']['rows']
    guest = get(client, {'section': 'book_truth'}, authorized=False)
    assert guest.status_code == 401
    assert 'cash' not in guest.text and 'snapshot_id' not in guest.text
    assert 'x-mm-cache' not in authorized.headers
    assert 'no-store' in authorized.headers['cache-control']


def test_revocation_is_not_hidden_by_cached_success(client, monkeypatch):
    assert get(client).status_code == 200
    monkeypatch.setenv('MASTERMIND_AUTH_TOKEN', 'rotated-fixture-operator')
    assert get(client).status_code == 401


def test_unconfigured_authoritative_instance_returns_unavailable(client, monkeypatch):
    monkeypatch.delenv('MASTERMIND_AUTH_TOKEN')
    monkeypatch.setattr(snapshots, 'read_projection', lambda *a, **k: pytest.fail('unconfigured storage access'))
    assert get(client, authorized=False).status_code == 503


def test_read_mirror_refuses_private_evidence_even_with_operator_header(client, monkeypatch):
    monkeypatch.setenv('MASTERMIND_SERVE_ONLY', '1')
    assert get(client).status_code == 403


@pytest.mark.parametrize('book', ['flagship','AUTONOMOUS','../autonomous','self_directed','unknown'])
def test_unsupported_book_refuses_before_read(client, monkeypatch, book):
    monkeypatch.setattr(snapshots, 'read_projection', lambda *a, **k: pytest.fail('invalid book reached store'))
    r = get(client, {'book': book})
    assert r.status_code == 404 and r.json()['error'] == 'unsupported_snapshot_book'


@pytest.mark.parametrize('params', [
    {'offset': '-1'}, {'offset': 'true'}, {'offset': '1.0'}, {'offset': '999999999999999999999'},
    {'limit': '0'}, {'limit': '101'}, {'limit': 'True'}, {'limit': '1e2'}, {'limit': '2.5'},
    {'snapshot_id': '../../secret'}, {'section': '../../secret'}, {'section': ''},
    {'book': 'autonomous', 'path': '/etc/passwd'}, [('limit','1'),('limit','2')], {'offset': '1'},
])
def test_invalid_or_duplicate_queries_fail_before_read(client, monkeypatch, params):
    monkeypatch.setattr(snapshots, 'read_projection', lambda *a, **k: pytest.fail('invalid query reached store'))
    assert get(client, params).status_code == 400


def test_explicit_identity_and_paging_are_bound_and_never_modify(client, tmp_path):
    p=sealed(); snapshots.persist_snapshot(p)
    before={f: f.read_bytes() for f in tmp_path.rglob('*.json')}
    r=get(client, {'snapshot_id':p['snapshot_id'],'section':'book_truth','limit':'1'})
    assert r.status_code == 200
    d=r.json(); assert d['snapshot']['snapshot_id'] == d['section']['snapshot_id'] == p['snapshot_id']
    assert d['section']['rows_returned'] == 1 and len(r.content) <= 65536
    assert {f:f.read_bytes() for f in tmp_path.rglob('*.json')} == before


def test_exact_missing_identity_is_not_reported_as_empty_history(client):
    assert get(client, {'snapshot_id':'sha256:'+'a'*64}).status_code == 404


def test_corrupt_snapshot_is_explicit_and_does_not_leak_paths(client):
    p=sealed(); record=snapshots.persist_snapshot(p); Path(record['path']).write_bytes(b'{}')
    r=get(client)
    assert r.status_code == 409 and r.json()['error']=='snapshot_corrupt'
    assert str(snapshots._ROOT) not in r.text


def test_unexpected_filesystem_error_is_sanitized(client, monkeypatch):
    def fail(*args, **kwargs): raise OSError('/private/operator/provider-secret')
    monkeypatch.setattr(snapshots, 'read_projection', fail)
    r=get(client); assert r.status_code == 503
    assert 'provider-secret' not in r.text and '/private' not in r.text


def test_corrected_snapshot_and_partial_coverage_stay_distinct(client):
    p=sealed(); snapshots.persist_snapshot(p)
    q=sealed(prior=[p['snapshot_id']],generation='b',recorded_at='2026-09-15T20:10:00Z'); snapshots.persist_snapshot(q)
    r=get(client).json()
    assert r['snapshot']['state']=='CORRECTED_GENERATION_AVAILABLE'
    assert r['snapshot']['coverage_state']=='PARTIAL'
    assert len(r['snapshots'])==2


@pytest.mark.parametrize('method', ['post','put','patch','delete'])
def test_endpoint_has_no_mutating_method(client, method):
    r=getattr(client,method)('/api/decision-snapshot',headers={'Authorization':'Bearer fixture-operator'})
    assert r.status_code in {403,405}


def test_shell_contains_no_evidence_or_credential_entry(client):
    r=client.get('/decision-evidence')
    assert r.status_code == 200
    assert 'Decision evidence' in r.text
    assert 'name="token"' not in r.text and 'type="password"' not in r.text
    assert 'script-src' in r.headers['content-security-policy']


def test_static_assets_are_exact_not_arbitrary_files(client):
    for suffix,ctype in [('js','javascript'),('css','text/css')]:
        r=client.get('/decision-evidence.'+suffix)
        assert r.status_code==200 and ctype in r.headers['content-type']
    assert client.get('/decision-evidence.env').status_code==404


def test_section_limit_applies_to_entire_http_envelope(client):
    from test_decision_snapshot import capture
    bundle=capture();bundle['sections']['book_truth']['rows'][0]['payload']='x'*64000
    p=snapshots.compose_snapshot('autonomous',decision_cutoff='2026-09-15T20:00:00Z',recorded_at='2026-09-15T20:01:00Z',capture=bundle,same_cutoff_prior_snapshot_ids=[])
    snapshots.persist_snapshot(p)
    r=get(client,{'snapshot_id':p['snapshot_id'],'section':'book_truth','limit':'1'})
    assert r.status_code==400
    assert r.json()['error']=='snapshot_response_too_large'
    assert len(r.content)<=65536
