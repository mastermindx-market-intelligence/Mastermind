"""Original rejected consumption must never become acceptance or new delivery."""
import copy
import json
import pytest
from integrations.session_bridge import fabric_reject_outcome as reject
from integrations.session_bridge import fabric_stop_return as stop


@pytest.fixture
def case():
    proof = dict(schema='mastermind.fabric_prior_rejection.v1', run_id='closed-run',
                 root='original', parent='original', result_bytes=2813,
                 result_sha256='a'*64, review_reason='Previously consumed; exceeded2500bytebound',
                 prior_adjudication_path='/retained/review.json', prior_adjudication_sha256='b'*64)
    status = dict(schema='mastermind.fabric_task_status.v1', run_id='closed-run',
                  root_id='original', parent_run_id='original', state='TERMINAL', rc=0,
                  signal='ok', result_available=True, result_bytes=2813, accepted=False,
                  accepted_by=None, acceptance_state='NOT_ACCEPTED', acceptance_reason='NO_OUTCOME')
    writes, intents = [], []
    def write(run, **kwargs):
        writes.append((run, kwargs))
        status.update(accepted_by='none', acceptance_reason='OUTCOME_NOT_ACCEPTED')
        return True
    return proof, status, write, writes, intents


def run(case, **kwargs):
    p,s,w,_,intents=case
    return reject.reconcile(p, native_parent='original', status=lambda _:copy.deepcopy(s),
                            write_outcome=kwargs.get('writer',w), record_intent=intents.append)


def test_prior_rejection_records_one_negative_outcome_and_hook_skips_without_result(case,tmp_path):
    p,s,_,writes,intents=case
    assert stop.valid_terminal(s,p['root'],p['run_id'])  # the actual pre-fix failure
    r=run(case)
    assert r['state']=='REJECTION_RECONCILED' and r['result_read'] is False
    assert writes==[('closed-run',dict(accepted_by='none',review_rejected=True,strict=True))]
    assert len(intents)==1 and not stop.valid_terminal(s,p['root'],p['run_id'])
    state=tmp_path/'attention';state.mkdir(mode=0o700)
    stop.register_subscription('original','closed-run',state)
    def read(op,run_id):
        assert op=='status'  # no result, request, acceptance or attention fabrication
        return json.dumps(s).encode()
    event=dict(hook_event_name='Stop',session_id='original',stop_hook_active=False,turn_id='turn')
    assert stop.prepare_subscribed_stop(event,adapter_sha256='c'*64,read_adapter=read,state_dir=state)=={}
    assert not list(state.glob('*.attempts.json'))


@pytest.mark.parametrize('field,value',[
    ('root_id','foreign'),('parent_run_id','foreign'),('run_id','foreign'),
    ('state','EFFECT_UNKNOWN'),('rc',78),('rc',False),('signal','effect_unknown'),
    ('result_available',False),('result_bytes',2812),('result_bytes',True),
    ('accepted',True),('accepted',None),('accepted_by','reviewer'),
    ('acceptance_reason','OUTCOME_NOT_ACCEPTED'),('acceptance_state','UNVERIFIED')])
def test_unqualified_terminal_has_no_effect(case,field,value):
    case[1][field]=value
    with pytest.raises(reject.ReconcileRefused):run(case)
    assert case[3]==[] and case[4]==[]


@pytest.mark.parametrize('field,value',[
    ('parent','foreign'),('root','foreign'),('result_bytes',False),
    ('result_sha256','not-digest'),('prior_adjudication_path','relative'),
    ('prior_adjudication_sha256','bad'),('review_reason','')])
def test_invalid_prior_consumption_has_no_effect(case,field,value):
    case[0][field]=value
    with pytest.raises(reject.ReconcileRefused):run(case)
    assert case[3]==[]


def test_changed_projection_refuses_before_intent(case):
    p,s,w,writes,intents=case
    snapshots=iter([dict(s),dict(s,accepted=True)])
    with pytest.raises(reject.ReconcileRefused):
        reject.reconcile(p,native_parent='original',status=lambda _:next(snapshots),
                         write_outcome=w,record_intent=intents.append)
    assert not writes and not intents


def test_unconfirmed_write_never_becomes_accepted_or_retry_permission(case):
    def uncertain(run_id,**kwargs):
        case[2](run_id,**kwargs)
        return False  # may have written; a negative projection is not this exact ACK
    result=run(case,writer=uncertain)
    assert result['state']=='OUTCOME_ACKNOWLEDGEMENT_UNKNOWN'
    assert result['strict_acknowledgement'] is False and result['retry_authorized'] is False
    assert len(case[3])==1


def test_bad_readback_is_unknown_not_success(case):
    def acknowledged(run_id,**kwargs):return True
    assert run(case,writer=acknowledged)['state']=='OUTCOME_ACKNOWLEDGEMENT_UNKNOWN'


def test_repeat_refuses_without_second_write(case):
    run(case)
    with pytest.raises(reject.ReconcileRefused):run(case)
    assert len(case[3])==1


@pytest.mark.parametrize('kind',['symlink','world_write','oversize'])
def test_untrusted_evidence_refuses(tmp_path,kind):
    p=tmp_path/'proof';p.write_bytes(b'abc')
    if kind=='symlink':
        original=tmp_path/'original';p.rename(original);p.symlink_to(original)
    if kind=='world_write':p.chmod(0o666)
    with pytest.raises((OSError,reject.ReconcileRefused)):
        reject.owned_bytes(p,maximum=2 if kind=='oversize' else 20)


def history(proof):
    return dict(root=proof['root'], parent=proof['parent'], outcomes=[dict(
        run_id=proof['run_id'], state='CONSUMED_NOT_ACCEPTED', accept_command_executed=False,
        reason=proof['review_reason'], result=dict(bytes=proof['result_bytes'], sha256=proof['result_sha256']))])


@pytest.mark.parametrize('mutation', ['root','parent','run','duplicate','state','accepted','bytes','digest','reason'])
def test_historical_entry_is_required_not_just_a_valid_file_hash(case, mutation):
    p=case[0]; document=history(p); entry=document['outcomes'][0]
    if mutation in ('root','parent'):document[mutation]='foreign'
    elif mutation=='run':entry['run_id']='foreign'
    elif mutation=='duplicate':document['outcomes'].append(copy.deepcopy(entry))
    elif mutation=='state':entry['state']='ACCEPTED'
    elif mutation=='accepted':entry['accept_command_executed']=True
    elif mutation=='bytes':entry['result']['bytes']=True
    elif mutation=='digest':entry['result']['sha256']='e'*64
    else:entry['reason']='unrelated reason'
    with pytest.raises(reject.ReconcileRefused):reject.validate_history(document,p)
    assert not case[3]


def test_receipt_directory_swap_blocks_outcome_and_keeps_original_intent(case,tmp_path,monkeypatch):
    p,s,w,writes,_=case
    directory=tmp_path/'original'; directory.mkdir(mode=0o700)
    held=tmp_path/'held'; real_sync=reject.os.fsync; swapped=[]
    with reject.retained_receipt(directory/'receipt.jsonl') as retain:
        retain(dict(state='OWNER_PREFLIGHT'))
        def swap_on_sync(fd):
            real_sync(fd)
            if not swapped:
                directory.rename(held); directory.mkdir(mode=0o700); swapped.append(True)
        monkeypatch.setattr(reject.os,'fsync',swap_on_sync)
        with pytest.raises(reject.ReconcileRefused,match='directory changed'):
            reject.reconcile(p,native_parent='original',status=lambda _:copy.deepcopy(s),
                             write_outcome=w,record_intent=retain)
    assert not writes and not list(directory.iterdir())
    assert 'OUTCOME_WRITE_INTENT' in (held/'receipt.jsonl').read_text()


def test_main_checks_history_and_uses_pinned_owner_once(case,tmp_path,monkeypatch,capsys):
    import hashlib,sys
    p,s,_,_,_=case
    ext=tmp_path/'ext'; ext.mkdir(mode=0o700)
    adapter=ext/'fabric_task.py'; ledger=ext/'pool_ledger.py'
    adapter.write_text('import copy\nstate='+repr(s)+'\ndef inspect_run(run): return copy.deepcopy(state)\n')
    ledger.write_text('import fabric_task\nwrites=[]\ndef record_outcome(run,**kwargs):\n'
                      ' writes.append((run,kwargs))\n'
                      ' fabric_task.state.update(accepted_by="none",acceptance_reason="OUTCOME_NOT_ACCEPTED")\n'
                      ' return True\n')
    for name in ('fabric_task','pool_ledger'):monkeypatch.delitem(sys.modules,name,raising=False)
    monkeypatch.setattr(sys,'path',list(sys.path))
    monkeypatch.setenv('CODEX_THREAD_ID','original');monkeypatch.delenv('POOL_ORCHESTRATOR_ID',raising=False)
    prior=tmp_path/'prior.json'; prior.write_text(json.dumps(history(p)))
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    p.update(prior_adjudication_path=str(prior),prior_adjudication_sha256=sha(prior))
    proof=tmp_path/'proof.json'; proof.write_text(json.dumps(p))
    receipt=tmp_path/'receipt.jsonl'
    args=['--proof',str(proof),'--proof-sha256',sha(proof),'--adapter',str(adapter),
          '--adapter-sha256',sha(adapter),'--ledger-sha256',sha(ledger),'--receipt',str(receipt)]
    try:
        assert reject.main(args)==0
        records=[json.loads(line) for line in receipt.read_text().splitlines()]
        assert [r['state'] for r in records]==['OWNER_PREFLIGHT','OUTCOME_WRITE_INTENT','REJECTION_RECONCILED']
        assert len(sys.modules['pool_ledger'].writes)==1
        with pytest.raises(FileExistsError):reject.main(args)
        assert len(sys.modules['pool_ledger'].writes)==1
        # Matching the hash of unrelated historical content is insufficient.
        prior.write_text(json.dumps(dict(root='foreign',parent='original',outcomes=[])))
        p['prior_adjudication_sha256']=sha(prior);proof.write_text(json.dumps(p))
        args[3]=sha(proof);args[-1]=str(tmp_path/'other.jsonl')
        with pytest.raises(reject.ReconcileRefused,match='historical'):reject.main(args)
        assert not (tmp_path/'other.jsonl').exists()
    finally:
        for name in ('fabric_task','pool_ledger'):sys.modules.pop(name,None)


def test_receipt_name_replacement_blocks_outcome(case,tmp_path,monkeypatch):
    p,s,w,writes,_=case; path=tmp_path/'receipt.jsonl'; real_sync=reject.os.fsync;swapped=[]
    with reject.retained_receipt(path) as retain:
        retain(dict(state='OWNER_PREFLIGHT'))
        def replace_on_sync(fd):
            real_sync(fd)
            if not swapped:
                path.rename(tmp_path/'retained-old');path.write_text('replacement');swapped.append(True)
        monkeypatch.setattr(reject.os,'fsync',replace_on_sync)
        with pytest.raises(reject.ReconcileRefused,match='receipt file changed'):
            reject.reconcile(p,native_parent='original',status=lambda _:copy.deepcopy(s),
                             write_outcome=w,record_intent=retain)
    assert not writes and 'OUTCOME_WRITE_INTENT' in (tmp_path/'retained-old').read_text()
