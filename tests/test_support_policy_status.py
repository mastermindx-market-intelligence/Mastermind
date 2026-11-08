"""Actual incumbent primitives and adapter consumer, disposable local fixtures only."""
from __future__ import annotations
import base64
import copy
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest
import test_provider_plan_auto_routing as auto

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'ops/native_fabric/support_policy_status'
source_stage = auto.source_stage


@pytest.fixture(scope='module')
def patched_source(source_stage, tmp_path_factory):
    # Production default composition supplies the exact helper bytes retained
    # across current39→40. This tests those component APIs, NOT a whole native40
    # cohort or the unrelated provider-plan rows/Memory118 union.
    stage = tmp_path_factory.mktemp('support-policy-source') / 'component'
    shutil.copytree(source_stage, stage / 'ext')
    meta = json.loads((COMPONENT / 'component.json').read_text())
    for relative, row in meta['patches'].items():
        assert hashlib.sha256((stage / relative).read_bytes()).hexdigest() == row['before']
        patch = COMPONENT / row['patch']
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == row['patch_sha256']
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=stage, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=stage, check=True)
        assert hashlib.sha256((stage / relative).read_bytes()).hexdigest() == row['after']
    shutil.copyfile(COMPONENT / 'reader.py', stage / 'ext/support_policy_status.py')
    return stage / 'ext'


@pytest.fixture
def runtime(patched_source, monkeypatch):
    # The production custody primitive rejects shared/writable ancestors. Keep
    # these tests inside this already-owned source tree, not shared /tmp.
    with tempfile.TemporaryDirectory(prefix='.policy-status-test-', dir=ROOT) as raw:
        home = Path(raw).resolve(); ext = home / 'source/ext'
        shutil.copytree(patched_source, ext)
        names = {p.stem for p in ext.glob('*.py')}
        previous = {name: sys.modules.get(name) for name in names}
        for name in names: sys.modules.pop(name, None)
        monkeypatch.syspath_prepend(str(ext))
        try:
            status = importlib.import_module('support_policy_status')
            delivery = importlib.import_module('artifact_delivery')
            lane = importlib.import_module('lane_runtime')
            host = importlib.import_module('host_pick')
            task = importlib.import_module('fabric_task')
            broker = importlib.import_module('lease_broker')
            def forbidden(*a, **kw): raise AssertionError('no broker/provider/worker/policy mutation')
            monkeypatch.setattr(broker, 'default_broker', forbidden)
            monkeypatch.setattr(status.support, 'ensure_policy', forbidden)
            monkeypatch.setattr(status.support, 'publish', forbidden)
            root = home / 'remote/lanes'
            for relative in ('tmp','ext','ext/active','ext/lanes','orch','orch/fabric','support-releases'):
                (root / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
            lock = root / 'ext/active/.admission.lock'; lock.write_bytes(b''); lock.chmod(0o600)
            doc = {'routing': {'execute_order': ['glm','grok'], 'grok_expiring_priority': {'enabled': False}},
                'pools': {'glm': {'models': {'executor': 'fixture'}}, 'grok': {'windows': {'weekly': {'limit': 100, 'remaining_pct': 70}}}}}
            desired = json.dumps(doc, sort_keys=True).encode()
            policy = root / 'orch/fabric/pools.yaml'; policy.write_bytes(desired); policy.chmod(0o600)
            source_policy = ext.parent / 'orch/fabric/pools.yaml'
            source_policy.parent.mkdir(parents=True)
            source_policy.write_bytes(desired); source_policy.chmod(0o600)
            registry = {'ubuntu0': {'ssh_alias': 'qualified-fixture', 'physical_lane_root': str(root)}}
            monkeypatch.setattr(host, 'load_registry', lambda: copy.deepcopy(registry))
            run, original_root, parent = 'fixture-prelaunch', 'fixture-root', 'fixture-parent'
            monkeypatch.setenv('CODEX_THREAD_ID', parent)
            state = ext / 'state/remote_sub'; state.mkdir(parents=True)
            request = {'schema':'mastermind.fabric_request_artifact.v1','run_id':run,
                'root_id':original_root,'parent_run_id':parent,'packet_sha256':'1'*64}
            request_raw = json.dumps(request).encode(); (state / (run+'.request.json')).write_bytes(request_raw)
            launch = {'schema':'mastermind.fabric_request_launch.v1','run_id':run,
                'root_id':original_root,'parent_run_id':parent,'packet_sha256':'1'*64,
                'request_sha256':hashlib.sha256(request_raw).hexdigest(),'state':'LAUNCH_ATTEMPT_RESERVED',
                'route':{'POOL':'glm','MODE':'glm','MODEL':'fixture','HOST':'ubuntu0'}}
            (state / (run+'.request-launch.json')).write_text(json.dumps(launch))
            manifest = {'schema':'remote-support-code.v1','files':{
                name:hashlib.sha256(desired).hexdigest() if name=='pools.yaml' else '2'*64
                for name in status.support.SOURCE_FILES}}
            (state / (run+'.support.json')).write_text(json.dumps(manifest))
            for path in state.iterdir(): path.chmod(0o600)
            req, frame, alias = status.original_request(run, original_root, parent)
            yield SimpleNamespace(status=status,delivery=delivery,lane=lane,host=host,task=task,
                ext=ext,root=root,lock=lock,policy=policy,desired=desired,doc=doc,registry=registry,
                run=run,original_root=original_root,parent=parent,request=req,state=state)
        finally:
            for name in names:
                sys.modules.pop(name,None)
                if previous[name] is not None: sys.modules[name]=previous[name]


def snapshot(root):
    return {str(p.relative_to(root)):(p.lstat().st_mode,p.lstat().st_ino,p.read_bytes())
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def test_identical_policy_under_actual_lock_and_no_mutation(runtime):
    r=runtime; before=snapshot(r.root)
    out=r.status.observe(r.request)
    assert out['state']=='OBSERVED' and out['comparison']=='IDENTICAL'
    assert out['counts']['nonexempt_entries']==0
    assert out['desired_critical_sha256']==out['current_critical_sha256']
    assert snapshot(r.root)==before
    assert r.status.validate_response(json.dumps(out).encode(),r.request)==out
    for key in ('maintenance_authorized','admission_authorized','historical_release_ack','execution_replayed'):
        assert out[key] is False


@pytest.mark.parametrize('kind',['compatible','critical','absent'])
def test_policy_comparison_uses_actual_fingerprint(runtime,kind):
    r=runtime
    if kind=='absent':r.policy.unlink()
    else:
        doc=copy.deepcopy(r.doc)
        if kind=='compatible':doc['pools']['grok']['windows']['weekly']['remaining_pct']=20
        else:doc['pools']['glm']['models']['executor']='other'
        r.policy.write_text(json.dumps(doc))
    out=r.status.observe(r.request)
    assert out['comparison']=={'compatible':'CRITICALLY_COMPATIBLE','critical':'CRITICAL_MISMATCH','absent':'ABSENT'}[kind]
    assert r.status.validate_response(json.dumps(out).encode(),r.request)==out


@pytest.mark.parametrize('name',['private-ordinary-marker','.unknown-sidecar','.original.preexec-settlement.json'])
def test_nonexempt_including_dot_and_invalid_receipt_are_not_ignored(runtime,name):
    r=runtime;p=r.root/'ext/active'/name;p.write_text('private unknown content');p.chmod(0o600)
    out=r.status.observe(r.request)
    assert out['state']=='OBSERVED' and out['counts']['nonexempt_entries']==1
    assert out['counts']['unknown_entries']==1
    encoded=json.dumps(out)
    assert name not in encoded and 'private unknown content' not in encoded


def test_actual_locked_lease_is_counted_without_settlement(runtime):
    r=runtime;p=r.root/'ext/active/lease';p.write_text(json.dumps({'schema':r.lane.LEASE_SCHEMA}));p.chmod(0o600)
    with p.open('rb') as held:
        fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=r.status.observe(r.request)
    assert out['state']=='OBSERVED' and out['counts']['held_entries']==1
    assert p.exists()


@pytest.mark.parametrize('kind',['missing','busy','symlink'])
def test_existing_admission_lock_never_created_or_bypassed(runtime,kind):
    r=runtime;held=None
    if kind=='missing':r.lock.unlink()
    if kind=='symlink':r.lock.unlink();r.lock.symlink_to(r.policy)
    if kind=='busy':held=r.lock.open('rb');fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        out=r.status.observe(r.request)
        assert out['state']=='UNAVAILABLE'
        assert 'current_critical_sha256' not in out
        if kind=='missing':assert not r.lock.exists()
    finally:
        if held is not None:held.close()


@pytest.mark.parametrize('kind',['marker','replacement_lock','replacement_active','policy'])
def test_blocking_observation_drift_withholds_current_report(runtime,monkeypatch,kind):
    r=runtime;original=r.lane.read_lane_occupancy
    def altered(path):
        value=original(path)
        if kind=='marker':(r.root/'ext/active/.late-unknown').write_text('private')
        if kind=='replacement_lock':r.lock.unlink();r.lock.write_bytes(b'');r.lock.chmod(0o600)
        if kind=='replacement_active':
            old=r.root/'ext/old-active';path.rename(old);path.mkdir(mode=0o700)
            (path/'.admission.lock').write_bytes(b'');(path/'.admission.lock').chmod(0o600)
        if kind=='policy':r.policy.write_bytes(r.desired+b'\n')
        return value
    monkeypatch.setattr(r.lane,'read_lane_occupancy',altered)
    out=r.status.observe(r.request)
    assert out['state']=='UNAVAILABLE' and 'counts' not in out


@pytest.mark.parametrize('kind',['foreign_root','foreign_parent','request_hash','manifest','policy_source','caller'])
def test_prelaunch_owner_join_refuses_foreign_or_unretained_facts(runtime,monkeypatch,kind):
    r=runtime;root,parent=r.original_root,r.parent
    if kind=='foreign_root':root='foreign'
    if kind=='foreign_parent':parent='foreign'
    if kind=='request_hash':
        p=r.state/(r.run+'.request-launch.json');value=json.loads(p.read_text());value['request_sha256']='0'*64;p.write_text(json.dumps(value))
    if kind=='manifest':
        p=r.state/(r.run+'.support.json');value=json.loads(p.read_text());value['files']['arbitrary']='0'*64;p.write_text(json.dumps(value))
    if kind=='policy_source':(r.ext.parent/'orch/fabric/pools.yaml').write_bytes(r.desired+b'\n')
    if kind=='caller':monkeypatch.setenv('CODEX_THREAD_ID','foreign')
    with pytest.raises(ValueError):r.status.original_request(r.run,root,parent)


def test_no_packet_result_log_or_broker_needed_for_true_prelaunch_join(runtime):
    r=runtime
    # None of those originals exists; LAUNCH_ATTEMPT_RESERVED is not START.
    assert not (r.state/(r.run+'.log')).exists()
    req,frame,alias=r.status.original_request(r.run,r.original_root,r.parent)
    assert req['support_digest'] and alias=='qualified-fixture'


def test_actual_adapter_consumer_once_and_retained_intent_blocks_replay(runtime,monkeypatch,capsys):
    r=runtime;calls=[]
    def read(alias,request,**kwargs):
        calls.append(alias)
        return json.dumps(r.status.observe(request)).encode()
    monkeypatch.setattr(r.delivery,'transport',read)
    args=['support-policy-status',r.run,'--root',r.original_root,'--parent',r.parent]
    assert r.task.main(args)==0
    out=json.loads(capsys.readouterr().out);assert out['state']=='OBSERVED'
    assert r.task.main(args)==78
    assert json.loads(capsys.readouterr().out)['state']=='PRIOR_OR_UNKNOWN_READ'
    assert calls==['qualified-fixture']


def test_parent_or_registry_withdrawal_after_read_scrubs_response(runtime,monkeypatch):
    r=runtime
    def read(alias,request,**kwargs):
        value=r.status.observe(request)
        r.registry['ubuntu0']['physical_lane_root']=str(r.root/'different')
        return json.dumps(value).encode()
    monkeypatch.setattr(r.delivery,'transport',read)
    out=r.status.inspect_original(r.run,r.original_root,r.parent,qualified_sources=r.status.source_hashes())
    assert out['state']=='PRIOR_OR_UNKNOWN_READ' and 'counts' not in out
    assert (r.state/(r.run+'.support-policy-status.intent.json')).exists()


@pytest.mark.parametrize('field,value',[('root','foreign'),('maintenance_authorized',True),('comparison','fake'),('current_policy_sha256','bad')])
def test_response_scope_authority_and_shape_cannot_be_forged(runtime,field,value):
    r=runtime;out=r.status.observe(r.request);out[field]=value
    with pytest.raises(ValueError):r.status.validate_response(json.dumps(out).encode(),r.request)


def test_generated_isolated_reader_executes_with_real_existing_parser(runtime):
    import venv
    import yaml
    r=runtime
    # Isolated development fixture only. Reuse the already installed declared
    # dependency; no pip/network/provider/host operation or fake parser.
    environment=r.root.parent/'parser-runtime'
    venv.EnvBuilder(with_pip=False).create(environment)
    site=environment/'lib'/('python%d.%d'%sys.version_info[:2])/'site-packages'
    site.mkdir(parents=True,exist_ok=True)
    shutil.copytree(Path(yaml.__file__).parent,site/'yaml')
    sources=r.status.source_hashes()
    code=r.status.code_for_request(r.request,
        expected_hash=sources['support_policy_status.py'],expected_sources=sources)
    before=snapshot(r.root)
    proc=subprocess.run([str(environment/'bin/python'),'-I','-S','-c',code],
        input=json.dumps(r.request).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    assert proc.returncode==0,proc.stderr.decode()
    report=r.status.validate_response(proc.stdout,r.request)
    assert report['state']=='OBSERVED',report
    assert report['comparison']=='IDENTICAL' and snapshot(r.root)==before
    assert len(code.encode())<120000
    changed=copy.deepcopy(r.request);changed['root']='foreign'
    denied=subprocess.run([str(environment/'bin/python'),'-I','-S','-c',code],
        input=json.dumps(changed).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    assert denied.returncode!=0 and not denied.stdout


def test_embedded_source_drift_refused_before_transport_code(runtime):
    r=runtime;sources=r.status.source_hashes()
    (r.ext/'support_bundle.py').write_bytes((r.ext/'support_bundle.py').read_bytes()+b'\n# drift\n')
    with pytest.raises(ValueError,match='reader_sources_changed'):
        r.status.code_for_request(r.request,
            expected_hash=sources['support_policy_status.py'],expected_sources=sources)


def test_valid_retained_settlement_metadata_reuses_exact_exemption_without_ack(runtime):
    r=runtime;expected,proof=r.lane._preexec_incident_contract(None)
    pid,started=r.lane._preexec_original_identity(expected[0])
    receipt={'schema':'mastermind.lane.preexec-settlement.v1','run_id':expected[0],
        'root_id':expected[1],'lease_id':expected[2],'marker_sha256':expected[3],
        'original_lease':{'schema':r.lane.LEASE_SCHEMA,'key':expected[0],'label':expected[0],
            'host':'ubuntu2','pid':pid,'started_at':started,'source_sha256':None,
            'admission':{},'reconcile_unreleased':True},'marker_identity':{'device':1,'inode':2},
        'proof':proof,'census':[],'created_at':1794148000,'phase':'removal_authorized'}
    receipt['receipt_sha256']=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    r.lane.validate_preexec_settlement_receipt(receipt)
    p=r.root/'ext/active'/('.'+expected[0]+'.preexec-settlement.json')
    p.write_text(json.dumps(receipt));p.chmod(0o600)
    assert r.status.support._is_retained_settlement_metadata(p)
    out=r.status.observe(r.request)
    assert out['state']=='OBSERVED' and out['counts']['nonexempt_entries']==0
    assert out['counts']['retained_metadata_entries']==1 and out['historical_release_ack'] is False
    assert p.exists()


def test_policy_drift_during_final_layout_qualification_is_withheld(runtime,monkeypatch):
    r=runtime;original=r.delivery.observe_remote_lane_layout
    def drift(binding,expected=None):
        value=original(binding,expected=expected)
        if expected is not None:r.policy.write_bytes(r.desired+b'\n')
        return value
    monkeypatch.setattr(r.delivery,'observe_remote_lane_layout',drift)
    out=r.status.observe(r.request)
    assert out['state']=='UNAVAILABLE' and out['reason']=='POLICY_CHANGED'
    assert 'current_policy_sha256' not in out


def test_false_fingerprint_or_comparison_cannot_be_promoted(runtime):
    r=runtime;out=r.status.observe(r.request)
    out['desired_critical_sha256']='0'*64
    with pytest.raises(ValueError,match='response_desired_fingerprint'):
        r.status.validate_response(json.dumps(out).encode(),r.request)
    out=r.status.observe(r.request);out['comparison']='CRITICAL_MISMATCH'
    with pytest.raises(ValueError,match='response_comparison'):
        r.status.validate_response(json.dumps(out).encode(),r.request)


def test_only_named_incumbent_functions_change(source_stage,patched_source):
    import ast
    for name,allowed in [('fabric_task.py',{'main'}),('artifact_delivery.py',{'transport'})]:
        def functions(path):
            tree=ast.parse(path.read_text())
            return {node.name:ast.dump(node,include_attributes=False) for node in tree.body
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
        before=functions(source_stage/name);after=functions(patched_source/name)
        assert set(before)==set(after)
        assert {key for key in before if before[key]!=after[key]}==allowed


def test_closed_adapter_cli_rejects_path_host_and_account(runtime,capsys):
    r=runtime
    for option in ('--host','--path','--account'):
        with pytest.raises(SystemExit) as stopped:
            r.task.main(['support-policy-status',r.run,'--root',r.original_root,
                '--parent',r.parent,option,'arbitrary'])
        assert stopped.value.code==2
    assert not (r.state/(r.run+'.support-policy-status.intent.json')).exists()


def test_adapter_static_reader_pin_refuses_before_module_execution(runtime,monkeypatch,capsys):
    r=runtime;marker=r.root/'never-executed'
    source=r.ext/'support_policy_status.py'
    source.write_text(source.read_text().replace('from __future__ import annotations',
        'from __future__ import annotations\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text("unsafe")',1))
    def forbidden(*args,**kwargs):raise AssertionError('transport reached drifted module')
    monkeypatch.setattr(r.delivery,'transport',forbidden)
    assert r.task.main(['support-policy-status',r.run,'--root',r.original_root,'--parent',r.parent])==78
    assert json.loads(capsys.readouterr().out)['state']=='UNAVAILABLE'
    assert not marker.exists() and not (r.state/(r.run+'.support-policy-status.intent.json')).exists()


def test_portable_export_uses_verified_delivery_bytes_not_inspect_reread(runtime,monkeypatch):
    r=runtime;sources=r.status.source_hashes()
    def forbidden():raise AssertionError('fresh inspect.getsource export must not run')
    monkeypatch.setattr(r.delivery,'remote_lane_root_source',forbidden)
    assert r.status.code_for_request(r.request,expected_hash=sources['support_policy_status.py'],expected_sources=sources)


@pytest.mark.parametrize('comparison',['IDENTICAL','CRITICALLY_COMPATIBLE','CRITICAL_MISMATCH'])
@pytest.mark.parametrize('field',['current_policy_sha256','current_critical_sha256'])
def test_nonabsent_comparison_rejects_each_single_null(runtime,comparison,field):
    r=runtime;out=r.status.observe(r.request)
    out['comparison']=comparison
    if comparison!='IDENTICAL':out['current_policy_sha256']='1'*64
    if comparison=='CRITICAL_MISMATCH':out['current_critical_sha256']='2'*64
    out[field]=None
    with pytest.raises(ValueError,match='response_comparison'):
        r.status.validate_response(json.dumps(out).encode(),r.request)


def test_native_desired_policy_uses_existing_orch_owner_not_ext_shadow(runtime):
    r=runtime
    incumbent=r.ext.parent/'orch/fabric/pools.yaml';incumbent.parent.mkdir(parents=True,exist_ok=True)
    incumbent.write_bytes(r.desired);incumbent.chmod(0o600)
    assert not (r.ext/'pools.yaml').exists()
    request,_,_=r.status.original_request(r.run,r.original_root,r.parent)
    assert request['desired_policy_sha256']==hashlib.sha256(r.desired).hexdigest()
    # A conflicting ext shadow is not a policy source or fallback.
    (r.ext/'pools.yaml').write_bytes(b'unqualified shadow')
    assert r.status.original_request(r.run,r.original_root,r.parent)[0]==request
    incumbent.write_bytes(r.desired+b'\n')
    with pytest.raises(ValueError,match='original_policy_source_unavailable'):
        r.status.original_request(r.run,r.original_root,r.parent)
