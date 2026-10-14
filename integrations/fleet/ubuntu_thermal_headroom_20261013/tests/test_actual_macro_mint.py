#!/usr/bin/env python3
"""Real reviewed Macro helper + actual owned process in an isolated Git repo.

No live worker, host repo, broker lease, source branch or provider is used.
The original physical-lease ordering is proved separately by the start-order test.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

STAGE=Path(__file__).resolve().parent
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0,str(EXT))
spec=importlib.util.spec_from_file_location('fabric_actual_helper',STAGE/'remote_sub_exec.py')
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
src=STAGE/'fixture_reviewed_macro_helper.py'
data=src.read_bytes()
sha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
assert sha==mod._MACRO_FABRIC_SPARSE_BLOB,(sha,mod._MACRO_FABRIC_SPARSE_BLOB)

def git(repo,*args):
    q=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,timeout=12)
    if q.returncode:raise AssertionError((args,q.stderr[:400],q.stdout[:200]))
    return q.stdout.strip()

with tempfile.TemporaryDirectory(prefix='mmx-real-sparse-launch-') as tmp:
    home=Path(tmp)/'home'
    donor=home/'lanes/repos/macro'
    donor.mkdir(parents=True)
    git(donor,'init','-q')
    git(donor,'config','user.name','Fixture')
    git(donor,'config','user.email','fixture@example.test')
    scripts=donor/'scripts'
    scripts.mkdir()
    shutil.copy2(src,scripts/'worktree_sparse.py')
    (scripts/'keep.py').write_text('print("kept")\n')
    cfg=donor/'config/sparse_worktree.json'
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({'enabled':True,'exclude_dirs':['data','site','mockups','verify_shots']}))
    for name in ('data','site','mockups','verify_shots'):
        p=donor/name
        p.mkdir()
        (p/'tracked.txt').write_text(name+'-'+'X'*3200)
    git(donor,'add','-A')
    git(donor,'commit','-qm','pinned-fixture')
    commit=git(donor,'rev-parse','HEAD')
    root=home/'lanes/support-releases/integration/ext'
    (root/'lanes').mkdir(parents=True)
    env={'HOME':str(home),'FABRIC_NEW_MACRO_COMMIT':commit,
         'REMOTE_SUB_RUN_ID':'actual-proven',
         'POOL_ORCHESTRATOR_ID':'fixture-root','POOL_PARENT_RUN_ID':'fixture-parent',
         'POOL_LEASE_ID':'fixture-real-lease','LANE_REMOTE_HOST':'ubuntu0'}
    with patch.dict(os.environ,env),patch.object(Path,'home',return_value=home):
        target=mod._new_macro_workspace('actual-proven',str(donor),root,dict(os.environ),
                                        SimpleNamespace(nice=10))
        target=Path(target)
        assert target==home/'lanes/wt/actual-proven'
        assert git(target,'rev-parse','HEAD')==commit
        assert git(target,'branch','--show-current')=='lane/actual-proven'
        assert git(target,'config','--get','core.sparseCheckout')=='true'
        assert git(target,'status','--porcelain=v1','-uall')==''
        assert (target/'scripts/keep.py').is_file()
        for name in ('data','site','mockups','verify_shots'):
            assert not (target/name/'tracked.txt').exists()
        receipts=list((root/'lanes').glob('*.process.jsonl'))
        assert len(receipts)==1
        receipt=json.loads(receipts[0].read_text().splitlines()[-1])
        assert receipt['schema']=='mastermind.local_owned_process_receipt.v1'
        assert receipt['label']=='actual-proven:workspace-mint'
        assert receipt['returncode']==0
        assert mod.cleanup_receipt_is_proven(receipt.get('cleanup') or {})
        # One original run never reuses or remints the new branch. This second
        # read-only refusal leaves all prior bytes untouched.
        try:mod._new_macro_workspace('actual-proven',str(donor),root,dict(os.environ),SimpleNamespace(nice=10))
        except mod.SparseWorkspaceRefused as ex:
            assert str(ex)=='FABRIC_SPARSE_DESTINATION_EXISTS'
            assert not ex.effect_unknown
        else:raise AssertionError('DUPLICATE_NOT_REFUSED')
        assert git(target,'rev-parse','HEAD')==commit
        print('ACTUAL_MACRO_FABRIC_MINT_PASS',json.dumps({
          'host':'isolated-temp-on-M2','test_root':str(home),
          'reviewed_helper_git_blob':sha,'head':commit,'sparse':True,
          'checkout_dir':'lanes/wt/actual-proven','worker_spawned':False,
          'owned_process_receipt':True,'no_duplicate':True},separators=(',',':')))
