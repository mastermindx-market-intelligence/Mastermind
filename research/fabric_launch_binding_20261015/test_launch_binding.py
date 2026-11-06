import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

import pytest

HERE = Path(__file__).parent
EXT = Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0, str(EXT))
import artifact_production
import artifact_delivery

spec = importlib.util.spec_from_file_location('prospective_helpers', HERE/os.environ.get('BINDING_SOURCE', 'candidate')/'remote_sub_helpers.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def private_path():
    # Test data only; source and worktree remain on the approved SSD. Use a
    # private path satisfying the production guard, without weakening it.
    base=Path.home()/'.mastermind/agent-evidence/fabric-launch-binding-test-data'
    base.mkdir(mode=0o700,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fixture-',dir=base) as directory:
        yield Path(directory)


@pytest.fixture
def bound(private_path):
    tmp_path=private_path
    packet = tmp_path/'packet.txt'
    packet.write_text(artifact_production.encode_packet('Write one bounded test file.', root='original-root', parent='actual-parent', run_id='worker-v1', names=['tests.py'], support_digest='a'*64))
    acquired = tmp_path/'acquired.txt'
    acquired.write_text('LEASE=012345abcdef ACCOUNT=chairman-max-2\n')
    log = tmp_path/'worker-v1.log'
    prefix = '2026-10-15T06:00Z [remote_sub id=worker-v1 host=ubuntu1] '
    log.write_text(''.join(prefix+event+'\n' for event in ['RUN_RESERVED explicit=1','LEASE_OK pool=glm','SUPPORT_VERSION_READY digest='+('a'*64)+' policy='+('b'*64)]))
    for p in [packet, acquired, log]:p.chmod(0o600)
    kw=dict(run_id='worker-v1',root='original-root',parent='actual-parent',host='ubuntu1',mode='glm',model='glm-5.3-flash',support_digest='a'*64,launch_lease_id='012345abcdef',launch_account='chairman-max-2')
    def run(**changes): return helper.record_launch_binding(log,packet,acquired,**(kw|changes))
    return log,packet,acquired,prefix,run


def test_fresh_binding_retained_before_launch(bound):
    log,packet,acquired,prefix,run=bound
    before=log.read_bytes()
    result=run()
    assert result['state']=='RETAINED_PRE_LAUNCH'
    assert log.read_bytes().startswith(before)
    event=json.loads(log.read_text().split(' LAUNCH_BINDING ')[1])
    assert (event['lease_id'],event['account'],event['root'],event['parent'])==('012345abcdef','chairman-max-2','original-root','actual-parent')
    assert event['phase']=='PRE_LAUNCH'
    assert 'accepted' not in event


@pytest.mark.parametrize('event',['LAUNCH_ATTEMPT attempt=1','LAUNCH_BINDING {}','REMOTE_DONE rc=0','DONE rc=0 signal=ok','LEASE_PRESERVED effect_unknown=1','POLICY_REFUSED rc=75'])
def test_old_or_uncertain_runs_not_repaired(bound,event):
    log,_,_,prefix,run=bound
    log.write_text(log.read_text()+prefix+event+'\n')
    before=log.read_bytes()
    with pytest.raises(ValueError):run()
    assert log.read_bytes()==before


@pytest.mark.parametrize('change',[{'root':'foreign'},{'parent':'foreign'},{'support_digest':'f'*64},{'host':'ubuntu2'},{'mode':'grok'}])
def test_wrong_binding_refuses(bound,change):
    log,_,_,_,run=bound;before=log.read_bytes()
    with pytest.raises(ValueError):run(**change)
    assert log.read_bytes()==before


def test_duplicate_call_cannot_append_second_binding(bound):
    log,_,_,_,run=bound;run();before=log.read_bytes()
    with pytest.raises(ValueError):run()
    assert log.read_bytes()==before


def test_plain_packet_has_no_new_behavior(bound):
    log,packet,_,_,run=bound;packet.write_text('ordinary legacy prompt');before=log.read_bytes()
    assert run()=={'state':'NOT_ARTIFACT_RUN'}
    assert log.read_bytes()==before


def test_acquire_error_cannot_be_binding(bound):
    log,_,acquired,_,run=bound;acquired.write_text('LEASE=012345abcdef ACCOUNT=chairman-max-2\nERROR\n');before=log.read_bytes()
    with pytest.raises(ValueError):run()
    assert log.read_bytes()==before


def test_symlink_log_refuses(bound):
    log,_,_,_,run=bound;other=log.with_name('other.log');log.rename(other);log.symlink_to(other);before=other.read_bytes()
    with pytest.raises((OSError,ValueError)):run()
    assert other.read_bytes()==before


def test_hardlink_log_refuses(bound):
    log,_,_,_,run=bound;os.link(log,log.with_name('copy.log'));before=log.read_bytes()
    with pytest.raises(ValueError):run()
    assert log.read_bytes()==before


def test_group_writable_log_refuses(bound):
    log,_,_,_,run=bound;log.chmod(0o660);before=log.read_bytes()
    with pytest.raises(ValueError):run()
    assert log.read_bytes()==before


def test_durability_failure_never_returns_success(bound,monkeypatch):
    log,_,_,_,run=bound
    def fail(_):raise OSError('fsync failed')
    monkeypatch.setattr(os,'fsync',fail)
    with pytest.raises(OSError):run()
    assert ' LAUNCH_BINDING ' in log.read_text()  # preserve uncertain evidence


def test_packet_changed_during_binding_refuses(bound,monkeypatch):
    log,packet,_,_,run=bound;before=log.read_bytes();original=artifact_delivery.local_file;calls=0
    def read(p,limit=1048576):
        nonlocal calls
        result=original(p,limit)
        if p==packet:
            calls+=1
            if calls==2:return result+b'changed'
        return result
    monkeypatch.setattr(artifact_delivery,'local_file',read)
    with pytest.raises(ValueError):run()
    assert log.read_bytes()==before


def test_controller_invokes_before_first_launch():
    text=(HERE/os.environ.get('BINDING_SOURCE','candidate')/'remote_sub.sh').read_text()
    call=text.index('"$HERE/remote_sub_helpers.py" launch-binding')
    assert text.index('SUPPORT_VERSION_READY') < call < text.index('log "LAUNCH stdout=') < text.index('launch_attempt=$((launch_attempt + 1))')
    assert 'RC=78; log "LAUNCH_BINDING_UNCONFIRMED rc=$RC before_launch=1"; exit "$RC";' in text


def test_conflicting_support_event_refuses(bound):
    log,_,_,prefix,run=bound
    log.write_text(log.read_text()+prefix+'SUPPORT_VERSION_READY digest='+('c'*64)+' policy='+('b'*64)+'\n')
    before=log.read_bytes()
    with pytest.raises(ValueError,match='not_fresh'):run()
    assert log.read_bytes()==before


def test_private_directory_guard_is_preserved(bound):
    log,_,_,_,run=bound
    before=log.read_bytes();log.parent.chmod(0o770)
    try:
        with pytest.raises(ValueError,match='directory_owner_or_mode'):run()
        assert log.read_bytes()==before
    finally:log.parent.chmod(0o700)


def test_same_length_log_mutation_before_write_refuses(bound,monkeypatch):
    log,_,acquired,_,run=bound
    original=artifact_delivery.local_file;calls=0
    def read(p,limit=1048576):
        nonlocal calls
        result=original(p,limit)
        if p==acquired:
            calls+=1
            if calls==2:log.write_bytes(log.read_bytes().replace(b'2026-10-15',b'2026-10-14'))
        return result
    monkeypatch.setattr(artifact_delivery,'local_file',read)
    with pytest.raises(ValueError,match='log_changed'):run()
    assert b' LAUNCH_BINDING ' not in log.read_bytes()


def test_acquire_scratch_uses_existing_private_log_directory():
    text=(HERE/os.environ.get('BINDING_SOURCE','candidate')/'remote_sub.sh').read_text()
    assert 'mktemp "$LOG_DIR/${ID}.lease.XXXXXX"' in text
    assert 'TEMP_FILES+=("$LEASE_OUTPUT_FILE")' in text


def test_plain_legacy_packet_preserves_original_path_and_defaults(bound):
    log,packet,_,_,run=bound
    packet.write_text('legacy plain body');before=log.read_bytes()
    log.parent.chmod(0o770)
    try:
        assert run(model='',root='')=={'state':'NOT_ARTIFACT_RUN'}
        assert log.read_bytes()==before
    finally:log.parent.chmod(0o700)


@pytest.mark.parametrize('corrupt',[False,True])
def test_real_controller_binding_block_stops_failed_launch(bound,corrupt):
    import subprocess
    log,packet,acquired,_,_=bound
    if corrupt:acquired.write_text('not an acquire response')
    text=(HERE/'candidate/remote_sub.sh').read_text()
    start=text.index('# Retain original lease/account correlation')
    end=text.index('log "LAUNCH stdout=',start)
    block=text[start:end]
    env={**os.environ,'PYTHONPATH':str(EXT),'DRY_RUN':'0',
         'OPERATOR_CHILD_BUDGET':'0','MODE':'glm','POOL_PARENT_RUN_ID':'actual-parent',
         'HERE':str(HERE/'candidate'),'REMOTE_SUB_PYTHON':sys.executable,
         'LOG_FILE':str(log),'PACKET':str(packet),'LEASE_OUTPUT_FILE':str(acquired),
         'ID':'worker-v1','ROUTING_ROOT':'original-root','HOST_ARG':'ubuntu1',
         'MODEL':'glm-5.3-flash','SUPPORT_DIGEST':'a'*64,
         'LEASE_ID':'012345abcdef','ACCOUNT_ARG':'chairman-max-2'}
    proc=subprocess.run(['/bin/bash','-c','set -u\nlog() { printf "%s\\n" "$*"; }\n'+block+'printf "REACHED_LAUNCH\\n"'],env=env,capture_output=True,text=True,timeout=10)
    assert proc.returncode == (78 if corrupt else 0),proc.stderr
    assert ('REACHED_LAUNCH' in proc.stdout) is not corrupt
    assert (' LAUNCH_BINDING ' in log.read_text()) is not corrupt


@pytest.mark.parametrize('changed',[{'launch_lease_id':'999999abcdef'},{'launch_account':'other-account'}])
def test_record_must_match_actual_launch_values(bound,changed):
    log,_,_,_,run=bound;before=log.read_bytes()
    with pytest.raises(ValueError,match='launch_binding_launch_mismatch'):
        run(**changed)
    assert log.read_bytes()==before
