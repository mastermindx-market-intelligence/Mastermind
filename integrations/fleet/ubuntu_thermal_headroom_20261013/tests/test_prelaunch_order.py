#!/usr/bin/env python3
"""Original Fabric worker lease/START-order regression, entirely mocked.

No subprocess is spawned; exercises _execute with the real source and fake
LaneLease, a retained local fixture packet, and an isolated log directory.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

STAGE=Path(__file__).resolve().parent
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0,str(EXT))
spec=importlib.util.spec_from_file_location('fabric_sparse_order_test',STAGE/'remote_sub_exec.py')
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

out=[]
class FakeLease:
    def __init__(self,steps):
        self.steps=steps
        self.held=False
    def __enter__(self):
        self.steps.append('LEASE_ENTERED')
        return self
    def __exit__(self,exc_type,exc,tb):
        self.steps.append('LEASE_EXIT_HELD' if self.held else 'LEASE_EXIT_NORMAL')
    def hold_for_reconciliation(self,reason):
        self.held=True
        self.steps.append('LEASE_EFFECT_UNKNOWN_HELD:'+reason)

with tempfile.TemporaryDirectory(prefix='mmx-worker-start-order-') as dirname:
    root=Path(dirname)
    donor=root/'home/lanes/repos/macro';donor.mkdir(parents=True)
    packet=root/'fixture.packet';packet.write_text('OBJECTIVE: isolated fixture only')
    support=root/'support';support.mkdir();(support/'lanes').mkdir()
    # Test _execute's actual entrypoint in the isolated directory; no
    # immutable on-host code, source repo, existing worker or transport touched.
    original_file=mod.__file__
    mod.__file__=str(support/'remote_sub_exec.py')
    try:
        for case in ('legacy','new','new-glmcodex','mint_uncertain'):
            steps=[]
            def acquire(*a,**k):
                steps.append('PHYSICAL_LEASE_ACQUIRED')
                return FakeLease(steps)
            def mint(*args):
                steps.append('MACRO_SPARSE_MINT_CALLED')
                if case=='mint_uncertain':
                    raise mod.SparseWorkspaceRefused('FABRIC_SPARSE_MINT_UNVERIFIED',effect_unknown=True)
                return str(root/'home/lanes/wt/new-worktree') if case in ('new','new-glmcodex') else args[1]
            def worker(command,*,cwd,timeout,env,nice,label,receipt_path,timeout_returncode,**kw):
                steps.append('PROVIDER_CHILD_START')
                assert label=='run-original'
                assert command[:2]==['bash',str(support.resolve()/'sub.sh')],repr(command)
                expected=str(root/'home/lanes/wt/new-worktree') if case in ('new','new-glmcodex') else str(donor)
                if case=='new-glmcodex':
                    assert command[2]=='glm-codex' and command[4]==expected,(command,expected)
                else:
                    assert command[2:4]==['--prompt-file','glm'] and command[5]==expected,(command,expected)
                if case in ('new','new-glmcodex'):
                    assert env.get('FABRIC_WORKSPACE_READY')=='1'
                    assert env.get('FABRIC_WORKSPACE_RUN_ID')=='run-original'
                else:
                    assert env.get('FABRIC_WORKSPACE_READY') is None
                assert 'MASTERMIND_FABRIC_SPARSE_NEW' not in env
                assert 'FABRIC_NEW_MACRO_COMMIT' not in env
                receipt_path.parent.mkdir(parents=True,exist_ok=True)
                receipt_path.write_text(json.dumps({'label':label,'cleanup':{'proven':True}})+'\n')
                return SimpleNamespace(returncode=0,cleanup_proven=True,
                    stdout='',stderr='',stdout_truncated=False,stderr_truncated=False,
                    timed_out=False)
            vars={
                'FABRIC_NEW_MACRO_COMMIT':'a'*40 if case!='legacy' else '',
                'POOL_LEASE_ID':'fixture-lease',
                'POOL_PARENT_RUN_ID':'fixture-parent',
                'POOL_ORCHESTRATOR_ID':'fixture-root',
                'REMOTE_SUB_RUN_ID':'run-original',
                'LANE_REMOTE_HOST':'ubuntu0',
            }
            with patch.dict(os.environ,vars), \
                 patch.object(Path,'home',return_value=root/'home'),\
                 patch.object(mod.LaneLease,'acquire',side_effect=acquire),\
                 patch.object(mod,'_new_macro_workspace',side_effect=mint),\
                 patch.object(mod,'run_owned_process',side_effect=worker),\
                 patch.object(mod,'load_runtime_config',return_value=SimpleNamespace(nice=10)),\
                 patch.object(mod,'install_signal_cleanup'),\
                 patch.object(mod,'cleanup_receipt_is_proven',return_value=True):
                state={'started':False}
                with contextlib.redirect_stdout(io.StringIO()):
                    rc=mod._execute(['remote_sub_exec.py','run-original','glm-codex' if case=='new-glmcodex' else 'glm',str(packet),str(donor),'glm-5.3'],state)
            (support/'lanes/run-original.process.jsonl').unlink(missing_ok=True)
            if case=='mint_uncertain':
                assert rc==76
                assert not state['started']
                assert 'PROVIDER_CHILD_START' not in steps
                assert 'LEASE_EFFECT_UNKNOWN_HELD:sparse_workspace_effect_unknown' in steps
            else:
                assert rc==0 and state['started']
                assert steps.index('PHYSICAL_LEASE_ACQUIRED')<steps.index('LEASE_ENTERED')
                assert steps.index('LEASE_ENTERED')<steps.index('MACRO_SPARSE_MINT_CALLED')<steps.index('PROVIDER_CHILD_START')
                assert steps[-1]=='LEASE_EXIT_NORMAL'
            out.append((case,rc,steps))
    finally:mod.__file__=original_file
print('PRELAUNCH_EFFECT_ORDER_TESTS_PASS',json.dumps(out,separators=(',',':'))[:1600])
