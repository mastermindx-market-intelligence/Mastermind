"""Local inert R2 scope tests; no installed writes, network, or actual collection."""
import ast
import copy
import json
from pathlib import Path

import pytest
import original_delivery_collector as c
import artifact_delivery as d
from test_original_artifact_regression import world, put
from test_plain_collection import plain

PACKAGE = Path(__file__).resolve().parents[1]
EXACT_SCOPES = copy.deepcopy(c.PLAIN_SCOPES)


@pytest.fixture
def qwen(plain):
    w = plain
    w.scope.update(mode='qwen', requested_model='qwen3.8-max')
    w.binding.update(mode='qwen', requested_model='qwen3.8-max')
    log = Path(w.binding['sources']['log']['path'])
    put(log, log.read_bytes().replace(b'pool=minimax', b'pool=bailian'))
    w.binding['sources']['log']['sha256'] = c.sha(log.read_bytes())
    w.scope['source_pins'] = {name: w.binding['sources'][name]['sha256'] for name in ('log', 'support')}
    w.lease = w.here/'state/remote_sub'/(w.rid + '.lease.TEST01')
    put(w.lease, b'inert-lease-witness-only')
    w.scope['lease_witness'] = dict(path=str(w.lease), sha256=c.sha(w.lease.read_bytes()))
    put(w.binding_path, c.canonical(w.binding))
    put(w.here/'hosts.json', c.canonical({'ubuntu1': {'ssh_alias': 'ubuntu1', 'allowed_modes': ['qwen']}}))
    return w


def test_candidate_adds_only_the_two_exact_review_scopes():
    base = ast.parse((PACKAGE/'original_delivery_collector.base.py').read_text())
    incumbent = ast.literal_eval(next(n.value for n in base.body if isinstance(n, ast.Assign)
                                     and any(isinstance(t, ast.Name) and t.id == 'PLAIN_SCOPES' for t in n.targets)))
    additions = json.loads((PACKAGE/'SCOPES.json').read_text())
    assert set(EXACT_SCOPES) - set(incumbent) == set(additions)
    assert {k: EXACT_SCOPES[k] for k in incumbent} == incumbent
    assert {k: EXACT_SCOPES[k] for k in additions} == additions
    assert len(additions) == 2
    assert all(v['root'] == v['parent'] == '01a13315-332b-7102-b7c8-0c7fc01fa92c' for v in additions.values())
    assert 'r2-office-reply-review-repair-20261012-01' not in EXACT_SCOPES


def test_qwen_plain_capture_and_lease_are_preserved(qwen):
    w = qwen
    before = w.lease.read_bytes()
    receipt = w.collect()
    assert receipt['state'] == 'COMPLETE'
    assert receipt['acceptance'] == 'NOT_RECORDED'
    assert receipt['lease_settlement'] == receipt['controller_state'] == 'UNKNOWN'
    assert not receipt['plain_provenance']['producer_root_authenticated']
    assert w.lease.read_bytes() == before
    path = w.tmp_path/'delivered/receipt.json'
    assert c.read_collection(path, expected_sha256=c.sha(path.read_bytes()), run_id=w.rid,
                             root='original-root', parent='original-parent') == w.stdout
    code = c.code_for_request(w.request)
    assert 'lease_witness' not in code and str(w.lease) not in code and before.decode() not in code


@pytest.mark.parametrize('fault', ['root', 'parent', 'packet', 'support', 'log', 'lease',
                                  'lease_path', 'cross_run', 'cross_support_pin', 'cross_log_pin'])
def test_r2_local_drift_refuses_before_transport(qwen, fault):
    w = qwen
    if fault in ('root', 'parent'):
        w.binding[fault] = 'foreign'
    elif fault in ('packet', 'support', 'log'):
        path = Path(w.binding['sources'][fault]['path'])
        put(path, path.read_bytes() + b'foreign')
    elif fault == 'lease':
        put(w.lease, b'different-inert-lease')
    elif fault == 'lease_path':
        w.scope['lease_witness']['path'] = str(w.lease.with_name('foreign.lease.TEST01'))
    elif fault == 'cross_run':
        w.binding['run_id'] = 'foreign-run'
    elif fault.startswith('cross_'):
        w.scope['source_pins'][fault.split('_')[1]] = '0' * 64
    put(w.binding_path, c.canonical(w.binding))
    with pytest.raises((ValueError, OSError)):
        w.collect()
    assert w.calls == []
    assert not (w.tmp_path/'delivered').exists()


def test_lease_drift_during_read_does_not_publish(qwen, monkeypatch):
    w = qwen
    original = d.transport
    def changed(*args):
        response = original(*args)
        put(w.lease, b'changed while remote read was mocked')
        return response
    monkeypatch.setattr(d, 'transport', changed)
    with pytest.raises(ValueError, match='plain_original_lease_witness_changed'):
        w.collect()
    assert len(w.calls) == 1 and not (w.tmp_path/'delivered/receipt.json').exists()


def test_lease_drift_before_consumption_refuses(qwen):
    w = qwen
    w.collect()
    path = w.tmp_path/'delivered/receipt.json'
    put(w.lease, b'changed before local consumption')
    with pytest.raises(ValueError, match='plain_original_lease_witness_changed'):
        c.read_collection(path, expected_sha256=c.sha(path.read_bytes()), run_id=w.rid,
                          root='original-root', parent='original-parent')


@pytest.mark.parametrize('field', ['run_id', 'root', 'parent', 'host'])
def test_qwen_cross_run_remote_request_refuses(qwen, field):
    request = copy.deepcopy(qwen.request)
    request[field] = 'foreign'
    with pytest.raises(ValueError):
        c.remote_read(request, home=qwen.home)
