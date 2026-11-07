#!/usr/bin/env python3
"""Both Fabric opt-ins use ONE original LaneLease, one worker, one settlement.

Composes the two source-only features in an isolated mock. No provider, host,
worker, Git source, OS profile, systemd unit or real lease is modified.
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

HERE=Path(__file__).resolve().parent
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path[:0]=[str(HERE),str(EXT)]
def import_file(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 result=importlib.util.module_from_spec(spec)
 sys.modules[name]=result
 spec.loader.exec_module(result)
 return result
host=import_file('combined_host_executor',HERE/'remote_sub_exec.py')
controller=import_file('combined_controller',HERE/'fabric_task.py')
import fabric_cpu_scope
steps=[]
class Lease:
 def __init__(self):
  self.held=False
 def __enter__(self):
  steps.append('PHYSICAL_LEASE_ENTER')
  return self
 def __exit__(self,a,b,c):
  steps.append('PHYSICAL_LEASE_EXIT_HELD' if self.held else 'PHYSICAL_LEASE_EXIT')
 def hold_for_reconciliation(self,reason):
  self.held=True;steps.append('ORIGINAL_LEASE_HOLD:'+reason)
with tempfile.TemporaryDirectory(prefix='combined-optins-') as temp:
 p=Path(temp);support=p/'support';(support/'lanes').mkdir(parents=True)
 packet=p/'packet.txt';packet.write_text('OBJECTIVE: fixture only')
 donor=p/'donor';donor.mkdir()
 sparse=p/'lanes/wt/qualified-sparse-worker'
 sparse.parent.mkdir(parents=True)
 key='qualified-sparse-worker'
 env={**os.environ,'REMOTE_SUB_RUN_ID':key,
  'POOL_ORCHESTRATOR_ID':'original-root','POOL_PARENT_RUN_ID':'original-parent',
  'POOL_LEASE_ID':'original-lease','LANE_REMOTE_HOST':'ubuntu2',
  'FABRIC_NEW_MACRO_COMMIT':'a'*40,'FABRIC_CPU_SCOPE_QUOTA_PCT':'100'}
 class Scoped(SimpleNamespace):pass
 def mint(*args):
  steps.append('SPARSE_MINT_INSIDE_LEASE')
  assert 'PHYSICAL_LEASE_ENTER' in steps
  assert args[0]==key
  return str(sparse)
 def prepare(k,mode,command,scope_env):
  steps.append('CPU_SCOPE_PREPARE_AFTER_MINT')
  assert k==key and scope_env['FABRIC_CPU_SCOPE_QUOTA_PCT']=='100'
  assert 'FABRIC_NEW_MACRO_COMMIT' not in scope_env
  assert command[5]==str(sparse)
  assert 'SPARSE_MINT_INSIDE_LEASE' in steps
  return Scoped(unit='original-hashed.scope',quota_percent=100,
    command=('/usr/bin/systemd-run','--user','--scope',*command),
    env={**scope_env,'XDG_RUNTIME_DIR':'/run/user/1000'})
 def settle(scope):
  steps.append('SCOPE_SETTLED')
  assert scope.unit=='original-hashed.scope'
  return {'schema':'mastermind.fabric_cpu_scope_settlement.v1',
    'scope_inactive':True,'remaining_pids':0}
 def run_provider(command,*,cwd,env,label,receipt_path,**kwargs):
  steps.append('PROVIDER_STARTED_ONCE')
  assert command[:3]==['/usr/bin/systemd-run','--user','--scope']
  assert command[8]==str(sparse)
  assert cwd==str(sparse) and label==key
  assert 'FABRIC_NEW_MACRO_COMMIT' not in env
  assert 'MASTERMIND_FABRIC_SPARSE_NEW' not in env
  receipt_path.parent.mkdir(parents=True,exist_ok=True)
  receipt_path.write_text(json.dumps({'label':label,'cleanup':{'verified':True}})+'\n')
  return SimpleNamespace(returncode=0,stdout='mock-success',stderr='',
    timed_out=False,cleanup_proven=True,stdout_truncated=False,stderr_truncated=False)
 prior=host.__file__;host.__file__=str(support/'remote_sub_exec.py')
 try:
  with patch.dict(os.environ,env),\
       patch.object(host.LaneLease,'acquire',side_effect=lambda *a,**kw: (steps.append('PHYSICAL_LEASE_ACQUIRED') or Lease())),\
       patch.object(host,'_new_macro_workspace',side_effect=mint),\
       patch.object(fabric_cpu_scope,'prepare_scope',side_effect=prepare),\
       patch.object(fabric_cpu_scope,'settle_scope',side_effect=settle),\
       patch.object(host,'run_owned_process',side_effect=run_provider),\
       patch.object(host,'cleanup_receipt_is_proven',return_value=True),\
       patch.object(host,'load_runtime_config',return_value=SimpleNamespace(nice=10)),\
       patch.object(host,'install_signal_cleanup'):
   state={'started':False}
   with contextlib.redirect_stdout(io.StringIO()):
    rc=host._execute(['remote_sub_exec.py',key,'glm',str(packet),str(donor),'glm-5.3'],state)
 finally:host.__file__=prior
 assert rc==0 and state['started']
 assert steps==['PHYSICAL_LEASE_ACQUIRED','PHYSICAL_LEASE_ENTER','SPARSE_MINT_INSIDE_LEASE',
   'CPU_SCOPE_PREPARE_AFTER_MINT','PROVIDER_STARTED_ONCE','SCOPE_SETTLED','PHYSICAL_LEASE_EXIT'],steps
 # Both options must route together through the existing parent without
 # creating an independent run ID or taking a second provider lease.
 call=[]
 def fake_spawn(argv,env=None):
  call.append(argv)
  return SimpleNamespace(returncode=0)
 def request():
  return controller.request(key,'mechanical',cwd='~/lanes/repos/macro',
    packet=None,stdin_bytes=b'OBJECTIVE: fixture no remote',
    root_id='original-root',parent_run_id='original-parent',
    task_complexity='C0_MECHANICAL',
    new_macro_worktree='a'*40,cpu_scope_percent=100)
 with patch.object(controller.pick,'format_pick',
       return_value='POOL=glm MODEL=glm-5.3 HOST=ubuntu2 MODE=glm') as router,\
      patch.object(controller.pick,'launch_policy',return_value={'allowed':True}),\
      patch.object(controller.subprocess,'run',side_effect=fake_spawn):
  assert request()==0
  assert len(call)==1
  assert call[0][-4:]==['--new-macro-worktree','a'*40,'--cpu-scope-quota','100'],call
  assert router.call_args.kwargs.get('required_platforms')==['linux']
 print('COMBINED_FEATURES_LEASE_TO_CWD_TO_SCOPE_TO_PROVIDER_TO_CLEANUP_PASS',json.dumps({
  'steps':steps,'worker_calls':1,'original_controller_requests':1,
  'run_id':key,'no_real_dispatch':True},separators=(',',':')))
