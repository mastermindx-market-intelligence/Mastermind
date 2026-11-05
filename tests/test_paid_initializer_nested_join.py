"""Real finite DATA/codec join; source custody and transport are explicit fixtures."""
import copy
import hashlib
from pathlib import Path
import shlex
import stat

import pytest
from tests import test_paid_host_qualification as fixture
from ops.native_fabric.quota_continuity.candidate import paid_initializer as owner
from ops.native_fabric.quota_continuity.candidate import paid_initializer_nested_data as nested


def request():
    req=fixture.request();c=req['initializer_commitment']
    c['initialization_contract']=nested.CONTRACT
    c['host_env'].update(sha256=nested.LEGACY_SHA256,size=len(nested._ORIGINAL))
    c['nested_helper']=dict(path=c['lane_root']+'/ext/.host_glm_token.sh',sha256='d'*64,size=57,uid=1000,gid=1000,mode=0o600)
    c['initialized_context']['glm_config']=c['account']['home']+'/.glm/config.json'
    req['initializer_commitment_sha256']=fixture.m._digest(c)
    return req


def observation(req):
    value=fixture.response(req);c=req['initializer_commitment'];pre=value['pre_execution']
    pre['host_env_identity'][6]=len(nested._ORIGINAL)
    value['context_identity']['host_env_sha256']=nested.LEGACY_SHA256
    pre['snapshot_sha256']=nested.TRANSFORMED_SHA256
    pre['nested_inputs']=dict(schema_version=nested.INPUTS_SCHEMA,initialization_contract=nested.CONTRACT,
        legacy_outer_sha256=nested.LEGACY_SHA256,transformed_outer_sha256=nested.TRANSFORMED_SHA256,
        helper=dict(schema_version='mastermind.paid_helper_private_data/v1',**{k:v for k,v in c['nested_helper'].items() if k!='path'}))
    pre['helper_origin_identity']=[1,3,stat.S_IFREG|0o600,1000,1000,1,57,100,100]
    return value


@pytest.fixture
def selected_source(monkeypatch):
    # Current selected source bytes are real; Root ownership verification is the
    # explicitly simulated premise. No private helper or credential is read.
    monkeypatch.setattr(fixture.m,'_initializer_module',lambda h:(owner,fixture.INITIALIZER_RAW) if h==hashlib.sha256(fixture.INITIALIZER_RAW).hexdigest() else fixture.m._refuse())
    return fixture.m


def test_explicit_new_contract_and_two_distinct_digests(selected_source):
    req=request();assert selected_source._request(req)==req
    value=observation(req)
    assert selected_source._observation(selected_source._canonical(value),req)==value
    assert value['context_identity']['host_env_sha256']!=value['pre_execution']['snapshot_sha256']
    old=copy.deepcopy(req);old['initializer_commitment']['initialization_contract']=owner.CONTRACT
    with pytest.raises(ValueError):selected_source._request(old)


@pytest.mark.parametrize('change',[
    lambda c:c.pop('nested_helper'),lambda c:c['nested_helper'].update(path='/elsewhere/helper'),
    lambda c:c['nested_helper'].update(mode=0o640),lambda c:c['nested_helper'].update(uid=True),
    lambda c:c['nested_helper'].update(extra='not-authority'),lambda c:c['host_env'].update(size=588),
    lambda c:c['host_env'].update(sha256='e'*64),lambda c:c.update(lane_root='/other/lanes'),
    lambda c:c.update(initialization_contract=owner.CONTRACT),
])
def test_new_contract_refuses_mixed_or_unqualified_inputs(selected_source,change):
    req=request();change(req['initializer_commitment']);req['initializer_commitment_sha256']=selected_source._digest(req['initializer_commitment'])
    with pytest.raises(ValueError):selected_source._request(req)


@pytest.mark.parametrize('change',[
    lambda v:v['pre_execution'].pop('nested_inputs'),
    lambda v:v['pre_execution']['nested_inputs'].update(initialization_contract=owner.CONTRACT),
    lambda v:v['pre_execution']['nested_inputs'].update(transformed_outer_sha256=nested.LEGACY_SHA256),
    lambda v:v['pre_execution']['nested_inputs']['helper'].update(uid=True),
    lambda v:v['pre_execution']['nested_inputs']['helper'].update(sha256='e'*64),
    lambda v:v['pre_execution']['nested_inputs']['helper'].update(path='/arbitrary'),
    lambda v:v['pre_execution']['helper_origin_identity'].__setitem__(5,2),
    lambda v:v['pre_execution']['helper_origin_identity'].__setitem__(3,1001),
    lambda v:v['pre_execution'].update(snapshot_sha256=nested.LEGACY_SHA256),
])
def test_real_observation_codec_refuses_witness_drift(selected_source,change):
    req=request();value=observation(req);change(value)
    with pytest.raises(ValueError):selected_source._observation(selected_source._canonical(value),req)


def test_private_package_exact_peer_hashes_and_command(selected_source,monkeypatch):
    native=Path(owner.__file__).parent
    sources={name:(native/name).read_bytes() for name in ('paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py')}
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in sources.items()}
    namespace={};exec(selected_source._PACKAGE_LOADER,namespace)
    loaded=namespace['_load_qualified_package'](sources,hashes)
    assert loaded._NESTED_DATA.sealed_snapshot is loaded.sealed_snapshot
    assert loaded._NESTED_DATA.FrozenHelper is loaded._TOKEN_DATA.FrozenHelper
    bad=dict(sources);bad['paid_initializer_nested_data.py']+=b'\n'
    with pytest.raises(ValueError):namespace['_load_qualified_package'](bad,hashes)
    monkeypatch.setattr(selected_source,'_initializer_bundle',lambda expected:(loaded,sources))
    req=request();req['sources_sha256'].update(hashes)
    alias,command=selected_source.build_paid_probe(req)
    parts=shlex.split(command)
    assert alias==req['transport_alias'] and parts[:5]==['/usr/bin/python3','-I','-S','-B','-c']
    assert '_load_qualified_package' in parts[5]
    assert len(parts)==8 and '.host_glm_token.sh' not in parts[0]
    assert req['initializer_commitment']['nested_helper']['sha256'] not in command


def _compiled_fixture(selected_source,monkeypatch):
    native=Path(owner.__file__).parent
    sources={name:(native/name).read_bytes() for name in ('paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py')}
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in sources.items()}
    namespace={};exec(selected_source._PACKAGE_LOADER,namespace)
    loaded=namespace['_load_qualified_package'](sources,hashes)
    monkeypatch.setattr(selected_source,'_initializer_bundle',lambda expected:(loaded,sources))
    req=request();req['sources_sha256'].update(hashes)
    return req


def test_current_final_paid_command_reaches_exact_strict_ssh_argv_and_eof(selected_source,monkeypatch,tmp_path):
    import json,os,shutil,subprocess,sys
    req=_compiled_fixture(selected_source,monkeypatch)
    alias,command=selected_source.build_paid_probe(req)
    assert len(command.encode('utf-8'))+1<=selected_source.MAX_REMOTE_COMMAND_BYTES<131072
    ext=tmp_path/'ext';ext.mkdir();shutil.copyfile(Path(owner.__file__).with_name('host_pull.sh'),ext/'host_pull.sh')
    (ext/'host_pull_probe.template').write_text('unused telemetry DATA')
    (ext/'host_pull_backend.py').write_text('import sys\nsys.stdin.buffer.read()\nprint('+repr(alias)+')\nprint('+repr(command)+')\n')
    binpath=tmp_path/'bin';binpath.mkdir();record=tmp_path/'actual-ssh.json'
    (binpath/'ssh').write_text('#!'+sys.executable+'\nimport json,sys\nfrom pathlib import Path\nrecord=Path('+repr(str(record))+')\nassert not record.exists(),\"duplicate SSH launch\"\nrecord.write_text(json.dumps(dict(argv=sys.argv[1:],stdin=sys.stdin.buffer.read().decode())))\nprint("inert-not-executed")\n')
    (binpath/'ssh').chmod(0o700)
    env=dict(HOME=str(tmp_path),PATH=str(binpath)+':'+str(Path(sys.executable).parent)+':/usr/bin:/bin')
    child=subprocess.run(['/bin/bash',str(ext/'host_pull.sh'),'--paid-qualification',req['host_ref']],env=env,input=selected_source._canonical(req),capture_output=True,timeout=10)
    assert child.returncode==0 and child.stdout.strip()==b'inert-not-executed'
    actual=json.loads(record.read_bytes());assert actual['stdin']==''
    assert actual['argv'][:-2]==['-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no']
    assert actual['argv'][-2]==alias
    assert hashlib.sha256(actual['argv'][-1].encode()).digest()==hashlib.sha256(command.encode()).digest()
    assert len(actual['argv'][-1].encode())+1<=100000
    assert 'HOST_PULL_REMOTE_STDIN_EXEC' not in actual['argv'][-1]


@pytest.mark.parametrize('kind',['ascii','multibyte','quoted'])
def test_final_utf8_quoted_command_plus_terminator_bound_refuses_before_ssh(selected_source,monkeypatch,tmp_path,kind):
    req=_compiled_fixture(selected_source,monkeypatch)
    if kind=='multibyte':req['initializer_commitment']['bootstrap_python']['path']='/opt/'+'界'*30+'/python3'
    elif kind=='quoted':req['initializer_commitment']['bootstrap_python']['path']='/opt/'+"q'"*30+'/python3'
    req['initializer_commitment_sha256']=selected_source._digest(req['initializer_commitment'])
    original_probe=selected_source._REMOTE_PROBE;cap=selected_source.MAX_REMOTE_COMMAND_BYTES
    assert cap==100000
    def compile_unbounded(padding):
        probe=original_probe+' '*padding
        monkeypatch.setattr(selected_source,'_REMOTE_PROBE',probe)
        req['probe_sha256']=hashlib.sha256(probe.encode()).hexdigest()
        with monkeypatch.context() as bound:
            bound.setattr(selected_source,'MAX_REMOTE_COMMAND_BYTES',1000000)
            return selected_source.build_paid_probe(req)[1]
    low,high=0,20000
    while low<high:
        middle=(low+high)//2
        if len(compile_unbounded(middle).encode('utf-8'))+1>cap:high=middle
        else:low=middle+1
    command=compile_unbounded(low)
    assert len(command.encode('utf-8'))+1>cap
    if kind=='multibyte':assert len(command)+1<=cap
    if kind=='quoted':
        path=req['initializer_commitment']['bootstrap_python']['path']
        inflation=len(shlex.quote(path))-len(path)
        assert inflation>0 and len(command.encode())+1-inflation<=cap
    marker=tmp_path/'ssh-must-not-run'
    def transport_after_compile():
        selected_source.build_paid_probe(req)
        marker.write_text('would cross transport boundary')
    with pytest.raises(selected_source.QualificationRefused):transport_after_compile()
    assert not marker.exists()
    # Equality includes the terminating NUL: exact-size command succeeds; a
    # one-byte-smaller allowance refuses the same final command.
    size=len(command.encode('utf-8'))+1
    with monkeypatch.context() as bound:
        bound.setattr(selected_source,'MAX_REMOTE_COMMAND_BYTES',size)
        assert selected_source.build_paid_probe(req)[1]==command
        bound.setattr(selected_source,'MAX_REMOTE_COMMAND_BYTES',size-1)
        with pytest.raises(selected_source.QualificationRefused):selected_source.build_paid_probe(req)
