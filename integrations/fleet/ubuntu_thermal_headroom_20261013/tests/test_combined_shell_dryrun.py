#!/usr/bin/env python3
"""Original combined Fabric Bash CLI under mocked no-network transports."""
from pathlib import Path
import os
import subprocess
import tempfile

D=Path(__file__).resolve().parent
shell=D/'remote_sub.sh'
assert shell.is_file() and (D/'fabric_cpu_scope.py').is_file()
with tempfile.TemporaryDirectory(prefix='mmx-combined-shell-') as t:
 packet=Path(t)/'packet'
 packet.write_text('OBJECTIVE: no actual provider')
 env={**os.environ,
 'POOL_ORCHESTRATOR_ID':'original-root',
 'POOL_PARENT_RUN_ID':'original-parent',
 'REMOTE_SUB_SSH_CMD':'/usr/bin/false',
 'REMOTE_SUB_SCP_CMD':'/usr/bin/false',
 'REMOTE_SUB_RSYNC_CMD':'/usr/bin/false'}
 cmd=['/bin/bash',str(shell),'ubuntu2','glm',str(packet),
      '~/lanes/repos/macro','glm-5.3','--run-id','combined-new-test',
      '--new-macro-worktree','a'*40,
      '--cpu-scope-quota','100','--dry-run']
 def run(args):
  return subprocess.run(args,capture_output=True,text=True,env=env,timeout=25)
 pos=run(cmd)
 assert pos.returncode==0,(pos.stderr[-600:],pos.stdout[-500:])
 assert 'fabric_cpu_scope.py' in pos.stdout and '<launch:' in pos.stdout
 assert 'LEASE_WAIT pool=' in pos.stderr
 assert 'REMOTE_DONE' not in pos.stderr and 'RUN_RESERVED' not in pos.stderr
 assert packet.read_text().startswith('OBJECTIVE:')
 malformed=cmd.copy()
 malformed[malformed.index('100')]='garbage'
 neg=run(malformed)
 assert neg.returncode==78 and 'CPU_SCOPE_QUOTA_UNQUALIFIED' in neg.stderr
 malformed_commit=cmd.copy()
 malformed_commit[malformed_commit.index('a'*40)]='no-commit'
 neg2=run(malformed_commit)
 assert neg2.returncode==78 and 'FABRIC_NEW_MACRO_SCOPE_REFUSED' in neg2.stderr
 print('COMBINED_SHELL_POSITIVE_NO_NETWORK_DRYRUN_PASS',
  {'positive_rc':pos.returncode,'bad_cpu_rc':neg.returncode,
   'bad_commit_rc':neg2.returncode,'original_support_module':True,
   'host': 'ubuntu2','source_cwd':'~/lanes/repos/macro'})
