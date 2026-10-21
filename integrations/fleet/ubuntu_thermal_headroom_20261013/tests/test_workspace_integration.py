#!/usr/bin/env python3
"""Hermetic existing-lease Fabric -> original sparse owner qualification fixture.

All Git writes remain under one temporary directory, no provider or host dispatch.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

STAGE = Path(__file__).resolve().parent
EXT = Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0,str(EXT))
spec=importlib.util.spec_from_file_location('fabric_sparse_staged',STAGE/'remote_sub_exec.py')
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)

def git(path,*args):
    p=subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True,timeout=9)
    assert p.returncode==0,(args,p.stderr[:300])
    return p.stdout.strip()

def sha1blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

# In this test the original existing Macro sparse tool is replaced with a tiny
# deterministic stub. The full original Macro helper has its own 102 real-Git
# test suite and Git content-blob pin on draft #9194. No live helper is copied.
FAKE_OWNER = """#!/usr/bin/env python3
import os, pathlib, subprocess, sys
assert sys.argv[1] == 'fabric-mint' and os.environ['MASTERMIND_FABRIC_SPARSE_NEW'] == '1'
donor=pathlib.Path(__file__).resolve().parents[1]
rid,sha=sys.argv[2],sys.argv[3]
dest=pathlib.Path.home()/'lanes'/'wt'/rid
def git(path,*args):
 p=subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True,timeout=7)
 if p.returncode:raise RuntimeError(p.stderr)
git(donor,'worktree','add','--no-checkout','-b','lane/'+rid,str(dest),sha)
git(dest,'sparse-checkout','init','--cone')
git(dest,'sparse-checkout','set','scripts')
git(dest,'read-tree','-mu','HEAD')
"""

def fake_runner_factory(calls):
    def invoke(cmd,*,cwd,timeout,env,nice,label,receipt_path,timeout_returncode):
        assert cmd[1].endswith('/scripts/worktree_sparse.py')
        assert cmd[2]=='fabric-mint'
        assert env.get('MASTERMIND_FABRIC_SPARSE_NEW')=='1'
        assert label==cmd[3]+':workspace-mint'
        assert timeout==180 and nice==10
        calls.append(dict(key=cmd[3],cwd=cwd,receipt_path=str(receipt_path)))
        q=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,
                         timeout=12,env=env)
        return SimpleNamespace(returncode=q.returncode,timed_out=False,
                               cleanup_proven=True,stdout_truncated=False,
                               stderr_truncated=False,stdout=q.stdout,stderr=q.stderr)
    return invoke

def err(call,expected,uncertain=False):
    try:call()
    except mod.SparseWorkspaceRefused as ex:
        assert str(ex)==expected,(str(ex),expected)
        assert ex.effect_unknown == uncertain,(ex.effect_unknown,uncertain)
        return
    raise AssertionError('DID_NOT_REFUSE '+expected)

tests=[]
with tempfile.TemporaryDirectory(prefix='mmx-sparse-fabric-') as tmp:
    home=Path(tmp)/'home';home.mkdir()
    donor=home/'lanes/repos/macro';donor.mkdir(parents=True)
    git(donor,'init','-q')
    git(donor,'config','user.email','fixture@example.test')
    git(donor,'config','user.name','Fixture')
    helper=donor/'scripts/worktree_sparse.py'
    helper.parent.mkdir(parents=True)
    helper.write_text(FAKE_OWNER)
    (donor/'data').mkdir()
    (donor/'data'/'big.txt').write_text('H'*1500)
    (donor/'scripts'/'keep.txt').write_text('keep\n')
    git(donor,'add','-A');git(donor,'commit','-qm','source-pin')
    commit=git(donor,'rev-parse','HEAD')
    oldblob=mod._MACRO_FABRIC_SPARSE_BLOB
    mod._MACRO_FABRIC_SPARSE_BLOB=sha1blob(helper.read_bytes())
    here=home/'lanes/support-releases/fake/ext'
    (here/'lanes').mkdir(parents=True)
    expected_env=dict(os.environ,HOME=str(home),
                  REMOTE_SUB_RUN_ID='lane-a',
                  POOL_ORCHESTRATOR_ID='original-root-1',
                  POOL_PARENT_RUN_ID='original-parent-1',
                  POOL_LEASE_ID='original-lease-1',
                  FABRIC_NEW_MACRO_COMMIT=commit)
    calls=[]
    fake_runner=fake_runner_factory(calls)
    cfg=SimpleNamespace(nice=10)
    with patch.object(Path,'home',return_value=home),patch.object(mod,'run_owned_process',side_effect=fake_runner),patch.dict(os.environ,expected_env):
        target=home/'lanes/wt/lane-a'
        # Default caller is unchanged and makes no branch/worktree.
        os.environ.pop('FABRIC_NEW_MACRO_COMMIT')
        assert mod._new_macro_workspace('lane-a',str(donor),here,expected_env,cfg)==str(donor)
        assert not target.exists() and not calls
        tests.append('legacy_default_has_no_effect')
        os.environ['FABRIC_NEW_MACRO_COMMIT']=commit
        err(lambda:mod._new_macro_workspace('lane-other',str(donor),here,expected_env,cfg),'FABRIC_SPARSE_SCOPE_REFUSED')
        err(lambda:mod._new_macro_workspace('lane-a',str(home),here,expected_env,cfg),'FABRIC_SPARSE_DONOR_REFUSED')
        assert not calls
        tests.append('malformed_root_and_run_refused_before_mint')
        mod._MACRO_FABRIC_SPARSE_BLOB='0'*40
        err(lambda:mod._new_macro_workspace('lane-a',str(donor),here,expected_env,cfg),'FABRIC_SPARSE_HELPER_BLOB_MISMATCH')
        mod._MACRO_FABRIC_SPARSE_BLOB=sha1blob(helper.read_bytes())
        assert not calls
        tests.append('unreviewed_helper_refused_before_mint')
        # Full original admission contract has already been proven by caller;
        # this function runs under the same acquired physical LaneLease.
        cwd=mod._new_macro_workspace('lane-a',str(donor),here,expected_env,cfg)
        assert cwd==str(target) and len(calls)==1
        assert git(target,'rev-parse','HEAD')==commit
        assert git(target,'branch','--show-current')=='lane/lane-a'
        assert git(target,'config','--get','core.sparseCheckout')=='true'
        assert git(target,'status','--porcelain=v1','-uall')==''
        assert not (target/'data/big.txt').exists()
        assert (target/'scripts/keep.txt').exists()
        tests.append('real_git_new_sparse_before_worker_start')
        err(lambda:mod._new_macro_workspace('lane-a',str(donor),here,expected_env,cfg),'FABRIC_SPARSE_DESTINATION_EXISTS')
        assert len(calls)==1
        tests.append('same_run_refused_before_second_mint')
        # Mint invocation can be partial; it is effect-unknown and never
        # automatically retried, even if Git produced a nonzero RC.
        prior=mod.run_owned_process
        mod.run_owned_process=lambda *a,**kw:SimpleNamespace(returncode=1,timed_out=False,
            cleanup_proven=True,stdout_truncated=False,stderr_truncated=False)
        os.environ['REMOTE_SUB_RUN_ID']='lane-b'
        err(lambda:mod._new_macro_workspace('lane-b',str(donor),here,expected_env,cfg),'FABRIC_SPARSE_MINT_UNVERIFIED',True)
        mod.run_owned_process=prior
        assert not (home/'lanes/wt/lane-b').exists()
        tests.append('ambiguous_create_holds_original_effect')
        # A concurrently changed helper after verified execution cannot be
        # accepted as source-qualified, even if a mock reports rc0.
        os.environ['REMOTE_SUB_RUN_ID']='lane-c'
        def mutate_after_mint(*a, **kw):
            helper.write_text(FAKE_OWNER+'\\n#modified')
            return SimpleNamespace(returncode=0,timed_out=False,
                cleanup_proven=True,stdout_truncated=False,
                stderr_truncated=False)
        with patch.object(mod,'run_owned_process',side_effect=mutate_after_mint):
            err(lambda:mod._new_macro_workspace('lane-c',str(donor),here,expected_env,cfg),
                'FABRIC_SPARSE_HELPER_EFFECT_UNKNOWN',True)
        helper.write_text(FAKE_OWNER)
        tests.append('concurrent_helper_drift_fences_original_effect')

print('TESTS',json.dumps({'passed':len(tests),'cases':tests}))
