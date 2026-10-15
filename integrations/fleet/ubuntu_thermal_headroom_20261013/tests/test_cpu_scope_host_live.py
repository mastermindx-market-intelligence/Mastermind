#!/usr/bin/env python3
"""Live user-scope quota + detached-child cleanup proof on an Ubuntu host.

Only short, low-CPU fixture processes. No original Fabric provider, host
configuration, power profile or live worker is changed.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time

STAGE=Path(__file__).resolve().parent
lib_path=STAGE/'fabric_cpu_scope.py'
spec=importlib.util.spec_from_file_location('fabric_cpu_scope_test',lib_path)
quota=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=quota
spec.loader.exec_module(quota)

H=Path.home()
source_sha='966869a4137545203faa2269faeed15cd0a096b5611161d242e2fb13b7c27937'
sources=[p for p in (H/'lanes/support-releases').glob('*/ext/lane_runtime.py')
         if hashlib.sha256(p.read_bytes()).hexdigest()==source_sha]
if not sources:raise SystemExit('REFUSED_NO_CANONICAL_OWNED_RUNTIME')
source=max(sources,key=lambda x:x.stat().st_mtime)
spec=importlib.util.spec_from_file_location('actual_lane_runtime_quota_test',source)
lane=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=lane
spec.loader.exec_module(lane)

def env_for(rid,pct='100'):
 return {**os.environ,'LANE_REMOTE_HOST':'ubuntu3',
    'REMOTE_SUB_RUN_ID':rid,'POOL_ORCHESTRATOR_ID':'fixture-root',
    'POOL_PARENT_RUN_ID':'fixture-parent','POOL_LEASE_ID':'fixture-lease',
    'SUPPORT_DIGEST':'a'*64,'FABRIC_CPU_SCOPE_QUOTA_PCT':pct}

results=[]
rid='mmx-quota-host-proof-'+str(os.getpid())
env=env_for(rid)
child='''import os,time,json
from pathlib import Path
cg=Path('/proc/self/cgroup').read_text().strip().split('::')[-1]
maxcpu=(Path('/sys/fs/cgroup')/cg.strip('/')/'cpu.max').read_text().strip()
print(json.dumps({'cgroup':cg,'cpu_max':maxcpu,'pid':os.getpid(),'pgid':os.getpgrp()}),flush=True)
time.sleep(.3)
'''
program=['/usr/bin/python3','-c',child]
assert quota.prepare_scope('legacy-fixture','glm',program,{**env,'FABRIC_CPU_SCOPE_QUOTA_PCT':''}) is None
for invalid in ('150','500','-1','garbage'):
 try:quota.prepare_scope(rid,'glm',program,env_for(rid,pct=invalid))
 except quota.CpuScopeRefused:pass
 else:raise AssertionError('INVALID_QUOTA_ACCEPTED: '+invalid)
for change in (
 {'LANE_REMOTE_HOST':'ubuntu1'},{'REMOTE_SUB_RUN_ID':'other'},
 {'POOL_LEASE_ID':''},{'POOL_PARENT_RUN_ID':''},
):
 try:quota.prepare_scope(rid,'glm',program,{**env,**change})
 except quota.CpuScopeRefused:pass
 else:raise AssertionError('INVALID_OWNER_ACCEPTED: '+str(change))
results.append('invalid_quota_and_original_scope_fail_closed')

plan=quota.prepare_scope(rid,'glm',program,env)
assert plan and plan.quota_percent==100
r=lane.run_owned_process(plan.command,env=plan.env,cwd=str(H),
                         timeout=8,nice=10,label='quota-normal-probe')
j=next((json.loads(s) for s in r.stdout.splitlines() if s.startswith('{')),None)
assert r.returncode==0 and r.cleanup_proven and not r.timed_out
assert j and j['cpu_max'].split()[0]=='100000' and j['pgid']==r.pgid
assert j['cgroup'].endswith('/'+plan.unit)
receipt=quota.settle_scope(plan)
assert receipt['scope_inactive'] and receipt['remaining_pids']==0
results.append('real_owner_quota_one_cpu_and_normal_settlement')

rid2=rid+'-timeout'
program2='''import subprocess,json,os,time
from pathlib import Path
kid=subprocess.Popen(['/usr/bin/python3','-c','import time;time.sleep(22)'],
 start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
 stderr=subprocess.DEVNULL,close_fds=True)
cg=Path('/proc/self/cgroup').read_text().strip().split('::')[-1]
print(json.dumps({'descendant_pid':kid.pid,'cgroup':cg,'leader_pg':os.getpgrp(),
 'detached_pg':os.getpgid(kid.pid)}),flush=True)
time.sleep(25)
'''
plan2=quota.prepare_scope(rid2,'glm',['/usr/bin/python3','-c',program2],env_for(rid2,'100'))
r2=lane.run_owned_process(plan2.command,env=plan2.env,cwd=str(H),
                          timeout=1.4,terminate_grace=.1,nice=10,
                          label='quota-detached-child-timeout-probe',timeout_returncode=124)
j2=next((json.loads(s) for s in r2.stdout.splitlines() if s.startswith('{')),None)
assert j2 and r2.timed_out and r2.cleanup_proven
assert j2['cgroup'].endswith('/'+plan2.unit)
assert j2['detached_pg']!=r2.pgid
desc=Path('/proc')/str(j2['descendant_pid'])
assert desc.exists(), 'fixture must reproduce original escaped child'
before=(plan2.cgroup_path/'cgroup.procs').read_text().split()
assert str(j2['descendant_pid']) in before
receipt2=quota.settle_scope(plan2)
assert receipt2['stop_issued'] and receipt2['killed_remaining_child_processes']
assert not desc.exists() and not (plan2.cgroup_path/'cgroup.procs').exists()
results.append('reaped_detached_child_after_owned_process_timeout')

print('ORIGINAL_USER_CPU_SCOPE_TEST_PASS',json.dumps({
 'host':os.uname().nodename,'runtime_sha256':source_sha,
 'tests':results,'normal_scope':plan.unit,'normal_quota':j['cpu_max'],
 'timeout_scope':plan2.unit,'timeout_child_was_running_after_pgid_cleanup':True,
 'timeout_child_stopped_by_original_scope':True,
 'worker_count_changed':False,'power_profile_changed':False,
},separators=(',',':')))
