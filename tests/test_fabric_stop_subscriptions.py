"""Inert explicit subscription, batching and durable at-most-once negatives."""
import json
import os
from pathlib import Path

import pytest
from integrations.session_bridge import fabric_stop_return as stop

ROOT = 'original-parent'
RUN = 'new-paid-leaf'
PIN = 'a' * 64
PAYLOAD = b'untrusted worker command text'


@pytest.fixture
def setup(tmp_path):
    state = tmp_path / 'attention'
    state.mkdir(mode=0o700)
    stop.register_subscription(ROOT, RUN, state)
    event = dict(hook_event_name='Stop', session_id=ROOT, turn_id='turn-original', stop_hook_active=False)
    status = dict(schema='mastermind.fabric_task_status.v1', run_id=RUN, root_id=ROOT,
                  parent_run_id=ROOT, state='TERMINAL', rc=0, signal='ok', result_available=True,
                  result_bytes=len(PAYLOAD), accepted=False, acceptance_state='NOT_ACCEPTED',
                  acceptance_reason='NO_OUTCOME')
    calls = []
    def read(operation, run):
        calls.append((operation, run))
        return json.dumps(dict(status, run_id=run)).encode() if operation == 'status' else PAYLOAD
    return state, event, status, read, calls


def call(s, **kwargs):
    return stop.prepare_subscribed_stop(s[1], adapter_sha256=PIN, read_adapter=s[3], state_dir=s[0], **kwargs)


def attempts(s):
    return s[0] / (stop.digest(ROOT.encode()) + '.attempts.json')


def test_two_jobs_one_frame_and_never_reemit(setup):
    stop.register_subscription(ROOT, 'second-paid-leaf', setup[0])
    out = call(setup)
    assert out['decision'] == 'block' and RUN in out['reason'] and 'second-paid-leaf' in out['reason']
    assert PAYLOAD.decode() not in out['reason']
    rows = json.loads(attempts(setup).read_text())['runs']
    assert len(rows) == 2 and len({r['frame_sha256'] for r in rows.values()}) == 1
    setup[4].clear();setup[1]['turn_id'] = 'new-turn'
    assert call(setup) == {} and setup[4] == []


@pytest.mark.parametrize('field,value', [('session_id','other'), ('agent_id','child'),
    ('hook_event_name','SubagentStop'), ('stop_hook_active',True)])
def test_foreign_or_reentered_callback_reads_no_runs(setup, field, value):
    setup[1][field] = value
    assert call(setup) == {} and setup[4] == [] and not attempts(setup).exists()


@pytest.mark.parametrize('field,value', [('state','ACTIVE_OR_WAITING'), ('state','EFFECT_UNKNOWN'),
    ('state','TERMINAL_FAILURE'), ('root_id','other'), ('parent_run_id','other'),
    ('rc',False), ('result_available',False), ('accepted',True), ('acceptance_reason','OUTCOME_NOT_ACCEPTED')])
def test_unqualified_runs_never_consume_result(setup, field, value):
    setup[2][field] = value
    assert call(setup) == {} and setup[4] == [('status',RUN)]
    assert not attempts(setup).exists()


def test_no_auto_discovery_or_duplicate_registration(setup):
    with pytest.raises(stop.ReturnUnavailable, match='already subscribed'):
        stop.register_subscription(ROOT, RUN, setup[0])
    (setup[0]/'unsubscribed.json').write_text('{}')
    call(setup)
    assert all(run == RUN for _,run in setup[4])


def test_index_bound_refuses_before_new_registration(setup, monkeypatch):
    monkeypatch.setattr(stop,'MAX_SUBSCRIPTIONS',1)
    with pytest.raises(stop.ReturnUnavailable, match='bound reached'):
        stop.register_subscription(ROOT,'second',setup[0])


def test_batch_bound_preserves_unattempted_jobs(setup, monkeypatch):
    stop.register_subscription(ROOT,'second',setup[0])
    monkeypatch.setattr(stop,'MAX_RETURNS',1)
    assert RUN in call(setup)['reason']
    assert 'second' not in json.loads(attempts(setup).read_text())['runs']
    setup[4].clear()
    assert 'second' in call(setup)['reason']
    assert all(run == 'second' for _,run in setup[4])


def test_time_bound_does_not_prepare_partial_frame(setup):
    times=iter([0,0,11])
    with pytest.raises(stop.ReturnUnavailable, match='time bound'):
        call(setup,clock=lambda:next(times))
    assert not attempts(setup).exists()


def test_result_change_prepares_nothing(setup):
    original=setup[3]; count=0
    def read(op,run):
        nonlocal count
        if op=='result':
            count+=1
            return PAYLOAD if count==1 else b'x'*len(PAYLOAD)
        return original(op,run)
    with pytest.raises(stop.ReturnUnavailable, match='result changed'):
        stop.prepare_subscribed_stop(setup[1],adapter_sha256=PIN,read_adapter=read,state_dir=setup[0])
    assert not attempts(setup).exists()


@pytest.mark.parametrize('when',[1,2])
def test_failed_fsync_prevents_emission_and_future_replay(setup,monkeypatch,when):
    real=os.fsync; calls=0
    def fail(fd):
        nonlocal calls
        calls+=1
        if calls==when:raise OSError('fixture durability failure')
        real(fd)
    with monkeypatch.context() as m:
        m.setattr(os,'fsync',fail)
        with pytest.raises(OSError):call(setup)
    if when==1:
        with pytest.raises(FileExistsError):call(setup)
    else:
        setup[4].clear()
        assert call(setup)=={} and setup[4]==[]


def test_directory_replacement_during_read_cannot_redirect_receipt(setup):
    state,event,status,read,calls=setup
    original=state.with_name('original')
    replaced=False
    def changed(op,run):
        nonlocal replaced
        raw=read(op,run)
        if not replaced:
            replaced=True;state.rename(original);state.mkdir(mode=0o700)
        return raw
    with pytest.raises(stop.ReturnUnavailable, match='changed subscription directory'):
        stop.prepare_subscribed_stop(event,adapter_sha256=PIN,read_adapter=changed,state_dir=state)
    assert not list(state.iterdir()) and not (original/attempts(setup).name).exists()


def test_symlink_index_and_writable_state_are_refused(setup,tmp_path):
    index=setup[0]/(stop.digest(ROOT.encode())+'.subscriptions.json')
    actual=tmp_path/'retained';index.rename(actual);index.symlink_to(actual)
    with pytest.raises(OSError):call(setup)
    assert setup[4]==[]
    setup[0].chmod(0o770)
    with pytest.raises(stop.ReturnUnavailable,match='subscription directory'):call(setup)


def test_malformed_attempt_record_cannot_be_adopted(setup):
    attempts(setup).write_text(json.dumps(dict(schema='mastermind.fabric_stop_attempts.v1',root=ROOT,runs={RUN:{}})))
    attempts(setup).chmod(0o600)
    with pytest.raises(stop.ReturnUnavailable,match='prior attention record'):call(setup)
    assert setup[4]==[]
