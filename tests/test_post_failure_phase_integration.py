"""Inert joined phase tests. No real held run, native parent or SSH is invoked."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
from unittest import mock

import pytest

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'ops/native_fabric/quota_continuity'
sys.path[:0]=[str(NATIVE/'candidate'),str(NATIVE/'source')]
import post_failure_observation as phase
import post_failure_observation_delivery as owner

WITNESS=json.loads((Path(__file__).parent/'fixtures/post-failure-routing-observation.json').read_text())

@pytest.fixture(autouse=True)
def inert_content_reader(request,monkeypatch):
    # Parser/transport tests use inert declared-file bytes. Separate tests below
    # exercise the actual held-inode wrapper and unchanged existing byte reader.
    if request.node.name.startswith(('test_same_artifact_reader','test_private_single_link','test_actual_content_fd')):return
    monkeypatch.setattr(phase,'snapshot_artifact',lambda files,path,remaining:files['read_one'](path,remaining))



def fixture():
    old=WITNESS['request'];run=old['run_id'];contract=copy.deepcopy(old['artifact']['contract'])
    body=b'INERT TEST PACKET; NOT A RETAINED ORIGINAL\n'
    contract['body_sha256']=hashlib.sha256(body).hexdigest()
    packet=b'FABRIC_ARTIFACT_REQUEST_V1 '+phase.canonical(contract)+b'\n'+body
    request={k:old[k] for k in ('run_id','root','parent','host','support_digest')}
    request.update(schema=phase.SCHEMA,artifact={
        'packet_sha256':hashlib.sha256(packet).hexdigest(),
        'support_files':copy.deepcopy(old['artifact']['support_files'])},
        prior_receipt_sha256=phase.SCOPES[run]['prior_receipt_sha256'],
        launch_binding_sha256='a'*64,terminal_log_sha256='b'*64,
        request_record_sha256='c'*64,request_launch_sha256='d'*64,invocation_id='e'*32)
    return request,contract,packet


def replica(request,packet,*,report=None):
    calls=[]
    class FixedReader:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,path,limit):
            calls.append(path)
            assert path==('lanes','tmp',request['run_id']+'.txt')
            return packet,None
        def verify(self):pass
    original=copy.deepcopy(WITNESS['report'] if report is None else report)
    def observe(run,digest,*,observe_pid,artifact):
        assert (run,digest,observe_pid)==(request['run_id'],phase.SUPPORT,False)
        phase.validate_contract(run,artifact)
        return original
    base={'Reader':FixedReader,'strict_json':json.loads,'observe':observe}
    return base,calls


def test_join_reads_actual_hash_bound_packet_then_only_its_declared_files():
    request,contract,packet=fixture();base,calls=replica(request,packet)
    reads=[]
    def read(path,remaining,**kwargs):
        reads.append((path,kwargs))
        return {'path':path,'status':'NOT_FOUND','reason':'missing_at_read'}
    result=phase.observe_original(base,{'MAX_TOTAL':1000,'read_one':read},request)
    directory='/tmp/fabric-'+hashlib.sha256(phase.canonical({k:contract[k] for k in ('root','parent','run_id')})).hexdigest()[:40]
    assert [x[0] for x in reads]==[directory+'/'+n for n in contract['names']]
    assert all(x[1]=={} for x in reads)
    assert len(calls)==1 and result['snapshot_state']=='PARTIAL_UNSETTLED'
    assert result['report']['state']=='UNKNOWN' and result['source_adoption_allowed'] is False


@pytest.mark.parametrize('fault',['missing','changed','foreign-header','foreign-name'])
def test_actual_packet_missing_or_substitution_stops_before_artifact_read(fault):
    request,contract,packet=fixture()
    if fault=='missing':packet=b''
    elif fault=='changed':packet+=b'x'
    else:
        contract['parent' if fault=='foreign-header' else 'names']='foreign' if fault=='foreign-header' else ['credential.txt']
        packet=b'FABRIC_ARTIFACT_REQUEST_V1 '+phase.canonical(contract)+b'\nINERT'
        request['artifact']['packet_sha256']=hashlib.sha256(packet).hexdigest()
    base,_=replica(request,packet)
    read=mock.Mock(side_effect=AssertionError('artifact read after invalid contract'))
    with pytest.raises(ValueError):phase.observe_original(base,{'MAX_TOTAL':1000,'read_one':read},request)
    read.assert_not_called()


@pytest.mark.parametrize('stop',['unavailable','permission','directory'])
def test_metadata_refusal_or_unavailable_never_continues_via_tmp_reader(stop):
    request,_,packet=fixture();report=copy.deepcopy(WITNESS['report'])
    report['status']='unavailable'
    if stop=='permission':report.update(request_stopped=True,reason='os_permission_denied',errno=13)
    if stop=='directory':report['directory_diagnostic']={'kind':'unknown'}
    base,_=replica(request,packet,report=report)
    read=mock.Mock(side_effect=AssertionError('onward read'))
    value=phase.observe_original(base,{'MAX_TOTAL':1000,'read_one':read},request)
    assert value['files'][0]['reason']=='original_metadata_unqualified'
    if stop=='permission':assert value['report']['permission_refusal_observed'] is True
    read.assert_not_called()


def test_first_file_unavailable_stops_the_same_reader_without_retry():
    request,_,packet=fixture();base,_=replica(request,packet)
    read=mock.Mock(side_effect=lambda path,*a,**k:{'path':path,'status':'UNAVAILABLE','reason':'filesystem_refused'})
    value=phase.observe_original(base,{'MAX_TOTAL':1000,'read_one':read},request)
    assert len(value['files'])==1 and read.call_count==1


def response(request,bundle):
    return phase.canonical({'schema':phase.SCHEMA,'request_sha256':hashlib.sha256(phase.canonical(request)).hexdigest(),'report':bundle})


def bundle_fixture():
    request,_,packet=fixture();base,_=replica(request,packet)
    private=b'INERT_PRIVATE_CANARY_DO_NOT_PRINT'
    def read(path,*a,**k):
        return {'path':path,'status':'RETRIEVED','bytes':len(private),'sha256':hashlib.sha256(private).hexdigest(),
                'data_base64':base64.b64encode(private).decode(),'observed_file':{
                    'device':1,'inode':2,'mtime_ns':3,'uid':1000,'mode':0o600,'links':1}}
    return request,phase.observe_original(base,{'MAX_TOTAL':1000,'read_one':read},request),private


@pytest.mark.parametrize('fault',['nonce','path','name','hash','bytes','base64','links','mode','authority','state','unknown-key'])
def test_response_binding_custody_and_authority_negatives(fault):
    request,bundle,_=bundle_fixture();raw=response(request,bundle)
    if fault=='nonce':request['invocation_id']='f'*32
    elif fault=='path':bundle['files'][0]['path']='/tmp/fabric-other/credential.txt'
    elif fault=='name':bundle['original_contract']['names']=['credential.txt']
    elif fault=='hash':bundle['files'][0]['sha256']='0'*64
    elif fault=='bytes':bundle['files'][0]['bytes']=True
    elif fault=='base64':bundle['files'][0]['data_base64']='!'
    elif fault=='links':bundle['files'][0]['observed_file']['links']=2
    elif fault=='mode':bundle['files'][0]['observed_file']['mode']=0o644
    elif fault=='authority':bundle['report']['export_authorized']=True
    elif fault=='state':bundle['snapshot_state']='COMPLETED'
    else:bundle['files'][0]['token']='INERT_SECRET'
    if fault!='nonce':raw=response(request,bundle)
    with pytest.raises(ValueError):owner.validate_response(raw,request)


def test_snapshot_retains_bytes_without_printing_content_or_adopting_them(tmp_path,monkeypatch):
    request,bundle,private=bundle_fixture();fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    class Chain:
        def __init__(self):self.fd=fd
        def verify(self):pass
        def close(self):os.close(self.fd)
    chain=Chain();captured=[]
    proof={'ssh_alias':'fixture-only','source_sha256':{}}
    monkeypatch.setattr(owner,'qualify',lambda r:proof)
    monkeypatch.setattr(owner.delivery,'reserve_destination',lambda p:chain)
    monkeypatch.setattr(owner.delivery,'transport',lambda *a,**k:response(request,bundle))
    monkeypatch.setattr(owner.delivery,'publish_receipt',lambda c,r,q,**k:captured.append(copy.deepcopy(r)))
    result=owner.observe(request,tmp_path)
    assert result['state']=='PARTIAL_UNSETTLED' and result['source_adoption_allowed'] is False
    assert private not in phase.canonical(result) and b'data_base64' not in phase.canonical(result)
    assert (tmp_path/'unsettled-routing.patch').read_bytes()==private
    assert all(x['status']=='RETAINED_UNSETTLED' for x in result['files'])
    assert captured and result['effect_state_changed'] is False


@pytest.mark.parametrize('fault',['private','hardlink','symlink','changed','legacy','parent'])
def test_same_artifact_reader_strict_snapshot_guards_preserve_legacy_default(tmp_path,monkeypatch,fault):
    # Local filesystem replica of Linux /tmp; no actual worker area is touched.
    files=owner.reader
    directory=tmp_path/'fabric-inert';directory.mkdir(mode=0o700)
    target=directory/'routing.patch';target.write_bytes(b'INERT_SNAPSHOT');target.chmod(0o600)
    if fault=='private':target.chmod(0o644)
    if fault=='hardlink':os.link(target,directory/'other.patch')
    if fault=='parent':directory.chmod(0o777)
    if fault=='symlink':
        target.unlink();target.symlink_to(directory/'missing')
    proxy=types.SimpleNamespace(**vars(os))
    realopen=os.open;realread=os.read
    def open_fixed(path,*args,**kwargs):
        return realopen(tmp_path if path=='/tmp' else path,*args,**kwargs)
    changed=[]
    def read_changed(fd,n):
        value=realread(fd,n)
        if fault=='changed' and value and not changed:
            changed.append(True);target.write_bytes(b'CHANGED_INERT')
        return value
    proxy.open=open_fixed;proxy.read=read_changed
    monkeypatch.setattr(files,'os',proxy)
    path='/tmp/fabric-inert/routing.patch'
    if fault=='legacy':
        target.chmod(0o644)
        item=files.read_one(path,1024)
        assert item['status']=='RETRIEVED' and 'links' not in item['observed_file']
    else:
        item=phase.snapshot_artifact(vars(files),path,1024)
        assert item['status']=='UNAVAILABLE'
        assert 'data_base64' not in item


def test_private_single_link_snapshot_positive(tmp_path,monkeypatch):
    files=owner.reader;directory=tmp_path/'fabric-inert';directory.mkdir(mode=0o700)
    target=directory/'routing.patch';target.write_bytes(b'INERT');target.chmod(0o600)
    proxy=types.SimpleNamespace(**vars(os));original=os.open
    proxy.open=lambda path,*a,**k:original(tmp_path if path=='/tmp' else path,*a,**k)
    monkeypatch.setattr(files,'os',proxy)
    item=phase.snapshot_artifact(vars(files),'/tmp/fabric-inert/routing.patch',1024)
    assert item['status']=='RETRIEVED' and item['observed_file']['links']==1
    assert base64.b64decode(item['data_base64'])==b'INERT'


def test_publication_failure_is_never_retried(tmp_path,monkeypatch):
    request,bundle,_=bundle_fixture();fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    class Chain:
        def __init__(self):self.fd=fd
        def verify(self):pass
        def close(self):os.close(self.fd)
    proof={'ssh_alias':'fixture-only','source_sha256':{}}
    monkeypatch.setattr(owner,'qualify',lambda r:proof)
    monkeypatch.setattr(owner.delivery,'reserve_destination',lambda p:Chain())
    monkeypatch.setattr(owner.delivery,'transport',lambda *a,**k:response(request,bundle))
    publish=mock.Mock(side_effect=ValueError('inert ambiguous publication'))
    monkeypatch.setattr(owner.delivery,'publish_receipt',publish)
    with pytest.raises(ValueError):owner.observe(request,tmp_path)
    assert publish.call_count==1


@pytest.mark.parametrize('name',['run_observation.py','post_failure_observation.py','artifact_reader.py'])
def test_exact_executable_bundle_race_stops_before_any_ssh(monkeypatch,name):
    request,_,_=fixture()
    root=NATIVE/'candidate'
    raw={n:(root/n if (root/n).exists() else NATIVE/'source'/n).read_bytes() for n in ('run_observation.py','post_failure_observation.py','artifact_reader.py')}
    expected={n:hashlib.sha256(v).hexdigest() for n,v in raw.items()}
    monkeypatch.setattr(owner,'qualify',lambda req:{'source_sha256':expected})
    def changed(path,*args):
        data=raw[Path(path).name]
        return data+b'\nUNQUALIFIED_CODE_CANARY' if Path(path).name==name else data
    monkeypatch.setattr(owner.delivery,'local_file',changed)
    popen=mock.Mock(side_effect=AssertionError('SSH must not start'))
    monkeypatch.setattr(owner.delivery.subprocess,'Popen',popen)
    with pytest.raises(ValueError,match='post_failure_local_preparation_failed'):
        owner.delivery.transport('fixture-only',request,current_sources_sha256=expected)
    popen.assert_not_called()


def test_command_consumes_one_retained_qualified_byte_bundle(monkeypatch):
    request,_,_=fixture();root=NATIVE/'candidate'
    raw={n:(root/n if (root/n).exists() else NATIVE/'source'/n).read_bytes() for n in ('run_observation.py','post_failure_observation.py','artifact_reader.py')}
    expected={n:hashlib.sha256(v).hexdigest() for n,v in raw.items()}
    monkeypatch.setattr(owner,'qualify',lambda req:{'source_sha256':expected})
    reads=[]
    def once(path,*args):
        name=Path(path).name;reads.append(name)
        if reads.count(name)>1:return b'UNQUALIFIED_CODE_CANARY'
        return raw[name]
    monkeypatch.setattr(owner.delivery,'local_file',once)
    command=owner.code_for_request(request,expected_sources=expected)
    assert reads==list(expected)
    assert 'UNQUALIFIED_CODE_CANARY' not in command
    compile(command,'inert_generated_reader','exec')  # not executed


@pytest.mark.parametrize('fault',['swap','mode','links'])
def test_actual_content_fd_is_checked_before_any_disallowed_read(tmp_path,monkeypatch,fault):
    files=owner.reader;directory=tmp_path/'fabric-inert';directory.mkdir(mode=0o700)
    target=directory/'routing.patch';target.write_bytes(b'ORIGINAL_INERT');target.chmod(0o600)
    proxy=types.SimpleNamespace(**vars(os));original_open=os.open;original_read=os.read
    opened=[];read_spy=[]
    def open_race(path,*args,**kwargs):
        if path=='routing.patch':
            opened.append(path)
            if len(opened)==2:
                if fault=='swap':
                    target.rename(directory/'held-original.patch')
                    target.write_bytes(b'FOREIGN_INERT_CANARY');target.chmod(0o600)
                elif fault=='mode':target.chmod(0o644)
                else:os.link(target,directory/'other.patch')
        return original_open(tmp_path if path=='/tmp' else path,*args,**kwargs)
    def read(fd,n):
        read_spy.append(fd);return original_read(fd,n)
    proxy.open=open_race;proxy.read=read;monkeypatch.setattr(files,'os',proxy)
    item=phase.snapshot_artifact(vars(files),'/tmp/fabric-inert/routing.patch',1024)
    assert item['status']=='UNAVAILABLE' and 'data_base64' not in item
    assert len(opened)==2 and read_spy==[]


def test_canonical_reader_and_historical_consumers_are_byte_exact():
    import subprocess
    paths=['ops/native_fabric/quota_continuity/source/'+name for name in
           ('artifact_reader.py','operator_stdout_delivery.py','current_failed_artifact_evidence.py')]
    for path in paths:
        assert (ROOT/path).read_bytes()==subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT)
    assert hashlib.sha256(Path(owner.reader.__file__).read_bytes()).hexdigest()==owner.delivery._ORIGINAL_READER_SHA256
    assert not (NATIVE/'candidate/artifact_reader.py').exists()
