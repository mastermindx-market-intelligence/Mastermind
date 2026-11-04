#!/usr/bin/env python3
"""Host _execute CPU scope lifecycle proof with fake original lease/provider.

This source-only contract is run on M2. Real Linux cgroup behavior is tested
separately using the actual pinned owned-process runner on Ubuntu3.
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
sys.path.insert(0,str(STAGE))
sys.path.insert(0,str(EXT))
spec=importlib.util.spec_from_file_location('host_cpu_scope_candidate',STAGE/'remote_sub_exec.py')
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)
import fabric_cpu_scope

class FakeLease:
    def __init__(self,steps):
        self.steps=steps;self.held=False
    def __enter__(self):
        self.steps.append('LEASE_ENTER');return self
    def __exit__(self,a,b,c):
        self.steps.append('LEASE_EXIT_HELD' if self.held else 'LEASE_EXIT_NORMAL')
    def hold_for_reconciliation(self,reason):
        self.held=True
        self.steps.append('LEASE_HELD:'+reason)

cases=[]
with tempfile.TemporaryDirectory(prefix='mmx-cpu-scope-host-') as tmp:
    root=Path(tmp)
    packet=root/'fixture.packet';packet.write_text('OBJECTIVE: mock only')
    here=root/'support/ext';here.mkdir(parents=True)
    (here/'lanes').mkdir()
    donor=root/'macro';donor.mkdir()
    actual=mod.__file__
    mod.__file__=str(here/'remote_sub_exec.py')
    try:
        for choice in ['default','scoped-glm','scoped-minimax','invalid','scope-unknown']:
            steps=[]
            def lease_acquire(*a,**kw):
                steps.append('PHYSICAL_LEASE_ACQUIRED')
                return FakeLease(steps)
            def prepare(key,mode,command,env):
                steps.append('SCOPE_PREPARE_AFTER_LEASE')
                assert 'LEASE_ENTER' in steps
                assert key=='original-run'
                assert mode in ('glm','minimax')
                if choice=='invalid':
                    raise fabric_cpu_scope.CpuScopeRefused('unqualified')
                return SimpleNamespace(command=('/usr/bin/systemd-run',
                    '--scope','--user','--unit=proof.scope',*command),
                    env={**env,'XDG_RUNTIME_DIR':'/run/user/1000'},
                    unit='proof.scope',quota_percent=100)
            def settled(scope):
                steps.append('SCOPE_VERIFICATION_BEFORE_LEASE_EXIT')
                assert scope.unit=='proof.scope'
                if choice=='scope-unknown':
                    raise fabric_cpu_scope.CpuScopeEffectUnknown('unit still has descendants')
                return dict(schema='mastermind.fabric_cpu_scope_settlement.v1',
                            quota_percent=100,remaining_pids=0,scope_inactive=True)
            def runner(command,*,cwd,timeout,env,nice,label,receipt_path,timeout_returncode,**kw):
                steps.append('PROVIDER_START')
                if choice=='default':
                    assert command[0]=='bash' and 'systemd-run' not in command
                    assert not env.get('XDG_RUNTIME_DIR')
                else:
                    assert command[0]=='/usr/bin/systemd-run'
                    assert command[3]=='--unit=proof.scope'
                    assert env.get('XDG_RUNTIME_DIR')=='/run/user/1000'
                assert label=='original-run'
                receipt_path.parent.mkdir(exist_ok=True,parents=True)
                receipt_path.write_text(json.dumps({'label':label,'cleanup':{'status':'verified'}})+'\n')
                return SimpleNamespace(returncode=0,stdout='mock-success',stderr='',
                    timed_out=False,stdout_truncated=False,stderr_truncated=False,
                    cleanup_proven=True)
            e={'LANE_REMOTE_HOST':'ubuntu3','REMOTE_SUB_RUN_ID':'original-run',
               'POOL_LEASE_ID':'test-lease','POOL_ORCHESTRATOR_ID':'test-root',
               'POOL_PARENT_RUN_ID':'test-parent',
               'FABRIC_CPU_SCOPE_QUOTA_PCT':'100' if choice!='default' else ''}
            with patch.dict(os.environ,e),\
                 patch.object(mod.LaneLease,'acquire',side_effect=lease_acquire),\
                 patch.object(fabric_cpu_scope,'prepare_scope',side_effect=prepare),\
                 patch.object(fabric_cpu_scope,'settle_scope',side_effect=settled),\
                 patch.object(mod,'run_owned_process',side_effect=runner),\
                 patch.object(mod,'cleanup_receipt_is_proven',return_value=True),\
                 patch.object(mod,'load_runtime_config',return_value=SimpleNamespace(nice=10)),\
                 patch.object(mod,'install_signal_cleanup'):
                state={'started':False}
                mode='minimax' if choice=='scoped-minimax' else 'glm'
                with contextlib.redirect_stdout(io.StringIO()):
                    rc=mod._execute(['remote_sub_exec.py','original-run',mode,
                                     str(packet),str(donor),'test-model'],state)
            if choice=='default':
                assert rc==0 and state['started'] and 'SCOPE_PREPARE_AFTER_LEASE' not in steps
            elif choice=='invalid':
                assert rc==78 and not state['started'] and 'PROVIDER_START' not in steps
            elif choice=='scope-unknown':
                assert rc==76 and state['started']
                assert 'LEASE_HELD:cpu_scope_cleanup_unproven' in steps
                assert steps[-1]=='LEASE_EXIT_HELD'
            else:
                assert rc==0 and state['started']
                assert steps.index('PHYSICAL_LEASE_ACQUIRED')<steps.index('LEASE_ENTER')<steps.index('SCOPE_PREPARE_AFTER_LEASE')<steps.index('PROVIDER_START')<steps.index('SCOPE_VERIFICATION_BEFORE_LEASE_EXIT')<steps.index('LEASE_EXIT_NORMAL')
            (here/'lanes/original-run.process.jsonl').unlink(missing_ok=True)
            cases.append({'case':choice,'rc':rc,'steps':steps})
    finally:
        mod.__file__=actual
print('FABRIC_CPU_SCOPE_ORIGINAL_LIFECYCLE_PASS',json.dumps(cases,separators=(',',':'))[:2400])
