"""Inert original-result validation against installed production dependencies."""
import base64
import copy
import json
from pathlib import Path
import pytest
import mac_policy_return as m
import artifact_delivery as delivery
import artifact_production as production

@pytest.fixture
def bundle(monkeypatch,tmp_path):
    support_files = {'native_remote.py': 'a'*64, 'artifact_production.py':m.digest(Path(production.__file__).read_bytes())}
    packet=tmp_path/'packet.txt';packet.write_text('fixture');monkeypatch.setattr(m,'PACKET',packet);monkeypatch.setattr(m,'PACKET_SHA',m.digest(b'fixture'))
    monkeypatch.setattr(m, 'SUPPORT', m.digest(m.canonical(dict(schema='remote-support-code.v1',files=support_files))))
    contract = production.parse_packet(production.encode_packet('fixture',root=m.ROOT,parent=m.ROOT,
        run_id=m.RUN,names=['unified.patch','bootstrap_host_policy.py','test_host_policy.py'],support_digest=m.SUPPORT))
    manifest = dict(schema=production.RESULT_SCHEMA,request_sha256=m.digest(m.canonical(contract)),
        root=m.ROOT,parent=m.ROOT,run_id=m.RUN,host=m.HOST,
        files=[dict(path=p,bytes=1,sha256=m.digest(b'x')) for p in production.paths(contract)])
    stdout = (production.RESULT_PREFIX+m.canonical(manifest).decode()+'\n').encode()
    cleanup = dict(census_proven=True,identity_verified=True,residual_count=0,status='not_needed',error_code=None)
    for stem in ('stdin_delivery','stdout_capture','stderr_capture'):
        cleanup[stem+'_complete']=True;cleanup[stem+'_error']=None
    capture = dict(stdout_bytes=10,stderr_bytes=0,stdout_truncated=False,stderr_truncated=False)
    process = dict(schema='mastermind.local_owned_process_receipt.v1',label=m.RUN,returncode=0,
        timed_out=False,runtime_failure_code=None,cleanup=cleanup,stdout_sha256=m.digest(b'0123456789'),**capture)
    terminal = dict(schema='mastermind.native.remote-terminal.v1',run_id=m.RUN,root=m.ROOT,host=m.HOST,
        mode='grok',model='grok-4.6',lease_id='fixturelease',account='default',started=True,returncode=0,
        output_complete=True,cleanup_proven=True,cleanup=cleanup,capture=capture,
        launch_timing={'support_digest':m.SUPPORT})
    terminal['output_binding']=dict(schema='mastermind.grok_normalized_output.v1',algorithm='grok_plaintext_and_usage_v1',
        root=m.ROOT,parent=m.ROOT,run_id=m.RUN,host=m.HOST,lease_id='fixturelease',account='default',support_digest=m.SUPPORT,
        mode='grok',model='grok-4.6',raw_bytes=10,raw_sha256=process['stdout_sha256'],
        normalized_bytes=len(stdout),normalized_sha256=m.digest(stdout),contract=contract,manifest=manifest)
    lease=dict(id='fixturelease',orchestrator_id=m.ROOT,host=m.HOST,pool='grok',account='default',model='grok-4.6',state='held')
    monkeypatch.setattr(delivery,'retained_lease',lambda *a,**k:lease)
    return dict(terminal=terminal,process=process,stdout=stdout,rc=b'0\n'),support_files,lease

def encoded(bundle):
    files,support,_=bundle
    raw={k:m.canonical(v) if isinstance(v,dict) else v for k,v in files.items()}
    return m.canonical(dict(schema=m.SCHEMA,request_sha256=m.digest(m.canonical(m.request_for(m.RUN,m.ROOT))),
        support_files=support,files={k:dict(bytes=len(v),sha256=m.digest(v),content_b64=base64.b64encode(v).decode()) for k,v in raw.items()}))

def test_exact_held_lease_result_is_evidence_only(bundle):
    files,binding=m.validate_response(encoded(bundle),m.request_for(m.RUN,m.ROOT))
    assert files['rc']==b'0\n' and binding['observed_lease_state']=='held'

@pytest.mark.parametrize('case',['root','parent','raw_sha','normalized_sha','missing_binding','cleanup','capture','lease','rc_bool','rc_nonzero'])
def test_identity_capture_cleanup_negatives(bundle,case):
    files,_,lease=bundle;t=files['terminal'];p=files['process']
    if case=='root':t['root']='other'
    elif case=='parent':t['output_binding']['parent']='other'
    elif case=='raw_sha':p['stdout_sha256']='0'*64
    elif case=='normalized_sha':t['output_binding']['normalized_sha256']='0'*64
    elif case=='missing_binding':t.pop('output_binding')
    elif case=='cleanup':p['cleanup']['stdout_capture_complete']=False
    elif case=='capture':t['capture']['stdout_truncated']=True
    elif case=='lease':lease['orchestrator_id']='other'
    elif case=='rc_bool':t['returncode']=False
    elif case=='rc_nonzero':files['rc']=b'76\n'
    with pytest.raises(ValueError):m.validate_response(encoded(bundle),m.request_for(m.RUN,m.ROOT))

def test_other_run_and_parent_never_reach_transport(monkeypatch,tmp_path):
    monkeypatch.setattr(delivery,'transport',lambda *a,**k:pytest.fail('transport attempted'))
    for run,root in [('b-j1-history-candidate-review-01a128b7-v1',m.ROOT),(m.RUN,'other')]:
        with pytest.raises(ValueError):m.recover(run,root,tmp_path/'uncreated')
    assert not (tmp_path/'uncreated').exists()

def test_transport_failure_retains_one_intent_and_never_repeats(monkeypatch,tmp_path):
    monkeypatch.setattr(delivery,'DESTINATION_ROOT',tmp_path)
    monkeypatch.setattr(m,'qualify',lambda r:dict(ssh_alias='fixture',sources={}))
    calls=[]
    def fail(*a,**k):calls.append(1);raise ValueError('transport_unavailable')
    monkeypatch.setattr(delivery,'transport',fail)
    result=m.recover(m.RUN,m.ROOT,tmp_path/'read')
    assert result['state']=='UNAVAILABLE' and result['outcome_accepted'] is False
    with pytest.raises((ValueError,FileExistsError)):m.recover(m.RUN,m.ROOT,tmp_path/'read')
    assert calls==[1]


def test_contract_from_another_packet_is_rejected(bundle):
    files,_,_=bundle
    t=files['terminal']
    other=production.parse_packet(production.encode_packet('different commission',root=m.ROOT,parent=m.ROOT,
        run_id=m.RUN,names=['unified.patch','bootstrap_host_policy.py','test_host_policy.py'],support_digest=m.SUPPORT))
    t['output_binding']['contract']=other
    with pytest.raises(ValueError,match='original_packet_contract_mismatch'):
        m.validate_response(encoded(bundle),m.request_for(m.RUN,m.ROOT))


def test_publication_checks_all_written_bytes(bundle,monkeypatch,tmp_path):
    monkeypatch.setattr(delivery,'DESTINATION_ROOT',tmp_path)
    monkeypatch.setattr(m,'qualify',lambda r:dict(ssh_alias='fixture',sources={}))
    monkeypatch.setattr(delivery,'transport',lambda *a,**k:encoded(bundle))
    result=m.recover(m.RUN,m.ROOT,tmp_path/'read')
    assert result['state']=='RETAINED_ORIGINAL_RESULT'
    assert result['original_controller_inactive_proven'] is False
    assert result['effect_state_changed'] is False and result['outcome_accepted'] is False
    for f in result['files']:
        assert m.digest((tmp_path/'read'/f['local_name']).read_bytes())==f['sha256']


def test_local_write_corruption_never_publishes_success(bundle,monkeypatch,tmp_path):
    monkeypatch.setattr(delivery,'DESTINATION_ROOT',tmp_path)
    monkeypatch.setattr(m,'qualify',lambda r:dict(ssh_alias='fixture',sources={}))
    monkeypatch.setattr(delivery,'transport',lambda *a,**k:encoded(bundle))
    original=delivery.write_exclusive
    def corrupt(fd,name,data):
        return original(fd,name,b'corrupted' if name=='stdout.bin' else data)
    monkeypatch.setattr(delivery,'write_exclusive',corrupt)
    try:
        result=m.recover(m.RUN,m.ROOT,tmp_path/'corrupt')
    except ValueError:
        return
    assert result['state']=='UNAVAILABLE'
