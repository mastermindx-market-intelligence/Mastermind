"""Cold code/data joins only; disposable owner data and explicit root-stat fixture.

No provider/authentication/host/service proof is asserted by these tests.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
QUOTA=ROOT/'ops/native_fabric/quota_continuity'

@pytest.fixture
def staged(tmp_path):
    out=tmp_path/'review'
    p=subprocess.run([sys.executable,str(QUOTA/'rollout/build_review_stage.py'),'--output',str(out)],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    return out/'native-code-stage/ext'

# Only filesystem UID qualification is represented by this inert fixture.
# Hash/mode/nofollow/source closure/YAML/filter/ledger decisions run unchanged.
ROOT_STAT_FIXTURE='''
root_files=[stage,stage/'paid_pyyaml_6_0_3.zip',stage/'paid_pyyaml_provenance.json',
 stage/'glm_keys.py',stage.parent.parent,stage.parent.parent/'native-manifest.json']
root_ids={(p.stat().st_dev,p.stat().st_ino) for p in root_files}
real_fstat,real_stat,real_lstat=os.fstat,os.stat,os.lstat
def qualify(s):
 if (s.st_dev,s.st_ino) not in root_ids:return s
 class RootFixture:
  st_uid=0
  def __getattr__(self,name):return getattr(s,name)
 return RootFixture()
os.fstat=lambda fd:qualify(real_fstat(fd))
os.stat=lambda *a,**k:qualify(real_stat(*a,**k))
os.lstat=lambda *a,**k:qualify(real_lstat(*a,**k))
'''

def run_cold(staged,code,*,fixture=True):
    setup="import os,sys\nfrom pathlib import Path\nstage=Path(sys.argv[1])\nsys.path.insert(0,str(stage))\n"
    p=subprocess.run([sys.executable,'-I','-S','-B','-c',setup+(ROOT_STAT_FIXTURE if fixture else '')+code,str(staged)],capture_output=True,text=True,timeout=20)
    return p


def test_exact_locked_pure_yaml_no_ambient_extension_or_package_fallback(staged):
    code='''
import paid_yaml_runtime as y
old=list(sys.path)
m=y.load_yaml()
assert m.__version__=='6.0.3' and m.__with_libyaml__ is False
assert m.safe_load('providers:\n  glm:\n    accounts: [one, two]\n')=={'providers':{'glm':{'accounts':['one','two']}}}
assert sys.path==old and '.zip/yaml/' in m.loader.__file__
assert not any(n in sys.modules for n in ('site','yaml._yaml','_yaml'))
assert y.load_yaml() is m
'''
    # The literal newlines belong inside the supplied YAML string.
    code=code.replace("m.safe_load('providers:\n  glm:\n    accounts: [one, two]\n')","m.safe_load('providers:\\n  glm:\\n    accounts: [one, two]\\n')")
    p=run_cold(staged,code);assert p.returncode==0,p.stderr
    p=run_cold(staged,"import types\nsys.modules['yaml']=types.ModuleType('yaml')\nimport paid_yaml_runtime as y\ny.load_yaml()")
    assert p.returncode!=0 and 'paid_yaml_ambient_refused' in p.stderr
    archive=staged/'paid_pyyaml_6_0_3.zip';archive.write_bytes(archive.read_bytes()+b'changed')
    p=run_cold(staged,'import paid_yaml_runtime as y\ny.load_yaml()')
    assert p.returncode!=0 and 'paid_yaml_source_refused' in p.stderr


def test_private_wrapper_actual_broker_host_filter_and_ledger_data(staged,tmp_path):
    owner=tmp_path/'incumbent/ext';(owner/'state/hosts').mkdir(parents=True)
    policy=owner.parent/'orch/fabric';policy.mkdir(parents=True)
    (owner/'broker').mkdir();(owner/'slots').mkdir()
    (owner/'glm_shim').mkdir()
    (policy/'accounts.yaml').write_text('providers:\n  glm:\n    enabled: true\n    accounts:\n      - name: ready\n        per_account_cap: 2\n')
    (policy/'pools.yaml').write_text('routing:\n  cost_usd_per_mtok_estimates:\n    glm: 0.25\n')
    validator=(staged/'glm_keys.py').read_bytes();(owner/'glm_keys.py').write_bytes(validator)
    (owner/'hosts.json').write_text(json.dumps({'h':dict(roles=['lanes'],allowed_modes=['glm'],qualification_only_modes=[],ssh_alias='route')}))
    (owner/'state/hosts/h.json').write_text(json.dumps(dict(host='h',reachable=True,ts=1000,glm_local_account_readiness=dict(schema='mastermind.glm_local_account_readiness.v1',host='h',transport_alias='route',mode='glm',config_scope='launcher_glm_config.v1',status='known',validator_sha256=hashlib.sha256(validator).hexdigest(),observed_at=1000,accounts={'ready':True}))))
    code='''
import socket
socket.create_connection=lambda *a,**k:(_ for _ in ()).throw(AssertionError('network forbidden'))
import paid_incumbent_state as state
state.OWNER=Path(OWNER_FIXTURE)
os.environ.update(FABRIC_CANONICAL_PAID_MODE='sealed-model-only-v1',FABRIC_CANONICAL_PAID_STATE_EXT=str(state.OWNER))
for k,p in dict(POOL_BROKER_DB='ext/broker/leases.sqlite',POOL_BROKER_LOCK='ext/broker/leases.lock',POOL_ACCOUNTS_YAML='orch/fabric/accounts.yaml',POOL_STATUS_JSON='orch/fabric/status.json',POOL_LEDGER_PATH='orch/fabric/ledger.jsonl',POOL_POLICY_YAML='orch/fabric/pools.yaml').items():os.environ[k]=str(state.OWNER.parent/p)
b=state.configure('lease_broker')
import quota_remote
quota_remote.read_provider=lambda *a,**k:(_ for _ in ()).throw(AssertionError('refresh forbidden'))
br=b.Broker(db_path=str(state.OWNER/'broker/test.sqlite'),lock_path=str(state.OWNER/'broker/test.lock'),accounts_path=os.environ['POOL_ACCOUNTS_YAML'],now_fn=lambda:1000,check_pid=False,external_gates=False,this_host='fixture',status_json=os.environ['POOL_STATUS_JSON'],hosts_path=str(state.OWNER/'hosts.json'))
r,_,_=br._try_acquire('inert-root','glm','ready','remote-glm','h',os.getpid(),60,None,model='glm-5.3-flash')
assert r.ok,r.reason
# Exact existing telemetry predicate, no caller filter stub or capacity fallback.
(state.OWNER/'glm_keys.py').write_bytes(b'changed')
try:br._try_acquire('another','glm','ready','remote-glm','h',os.getpid(),60,None,model='glm-5.3-flash')
except ValueError:pass
else:raise AssertionError('changed original validator accepted')
ledger=state.configure('pool_ledger')
assert ledger.load_cost_table()=={'glm':0.25}
assert ledger.LEDGER_DIR==str(state.OWNER.parent/'orch/fabric')
assert state.main(['lease_broker','status'])==78
assert state.main(['pool_ledger','outcome'])==78
'''.replace('OWNER_FIXTURE',repr(str(owner)))
    p=run_cold(staged,code);assert p.returncode==0,p.stderr
    assert not (staged/'state').exists() and not (staged/'orch').exists()


def test_default_remote_support_uses_only_verified_physical_owner(staged,tmp_path):
    sys.path.insert(0,str(staged))
    try:
        for name in ('support_bundle','paid_model_owner'):sys.modules.pop(name,None)
        import support_bundle as support
        import paid_model_owner as owner
        assert owner._PAID_SUPPORT_FILES==support.PAID_MODEL_SOURCE_FILES
        assert owner._SUPPORT_EXT_LINKS==support._EXT_SYMLINKS
        lanes=(tmp_path/'lanes').resolve();stable=lanes/'ext';stable.mkdir(parents=True)
        (lanes/'support-releases').mkdir();(stable/'active').mkdir();(stable/'lanes').mkdir()
        sources=tmp_path/'sources';sources.mkdir()
        manifest={}
        for name in support.PAID_MODEL_SOURCE_FILES:
            raw=(b'fixture: policy\n' if name=='pools.yaml' else (staged/name).read_bytes());(sources/name).write_bytes(raw);manifest[name]=hashlib.sha256(raw).hexdigest()
        # Only policy publication qualification is fixture DATA; alias/file
        # validation and the actual support publisher/remote helper are real.
        import fabric_policy_snapshot
        old=fabric_policy_snapshot.validate_publication
        fabric_policy_snapshot.validate_publication=lambda *a:None
        try:release=support.publish(sources,stable,manifest).parent
        finally:fabric_policy_snapshot.validate_publication=old
        env=dict(REMOTE_SUB_LANES=str(lanes),SUPPORT_DIGEST=release.name)
        assert owner.canonical_state_ext(release/'ext',env)==stable
        (release/'ext').chmod(0o755)
        (release/'ext/lanes').unlink();(release/'ext/lanes').symlink_to(tmp_path/'foreign')
        (release/'ext').chmod(0o555)
        with pytest.raises(ValueError):owner.canonical_state_ext(release/'ext',env)
    finally:sys.path.remove(str(staged))


def test_native_manifest_accepts_only_named_pure_dependency_containers():
    from ops.native_fabric.quota_continuity.rollout import native_generation as generation
    for name in ('ext/paid_pyyaml_6_0_3.zip','ext/paid_pyyaml_provenance.json'):
        generation.file_name(name)
    for name in ('ext/other.zip','ext/other.json','ext/pools.yaml','ext/../paid_pyyaml_6_0_3.zip'):
        with pytest.raises(ValueError):generation.file_name(name)
