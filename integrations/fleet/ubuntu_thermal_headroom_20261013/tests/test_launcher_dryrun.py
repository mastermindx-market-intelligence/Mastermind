#!/usr/bin/env python3
"""Original remote_sub.sh positive sparse planning without a provider/SSH call.

The dry run uses a copy of the real original host registry and replaces
transport binaries with /usr/bin/false. It cannot dispatch a paid worker.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

STAGE=Path(__file__).resolve().parent
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
shell=STAGE/'remote_sub.sh'
assert shell.is_file()
subprocess.run(['/bin/bash','-n',str(shell)],check=True,timeout=6)
source=EXT/'hosts.json'
assert source.is_file()

with tempfile.TemporaryDirectory(prefix='mmx-sparse-shell-dryrun-') as tmp:
    # Original shell locates its helpers/hosts under dirname($SCRIPT_SOURCE).
    # Source is staged already, and the previous full dry-run copied a
    # protected read-only registry snapshot in this same test directory.
    registry=STAGE/'hosts.json'
    if not registry.is_file():
        shutil.copyfile(source,registry)
    assert registry.is_file()
    packet=Path(tmp)/'packet.txt'
    packet.write_text('OBJECTIVE: dry-run, not worker execution')
    env={**os.environ,
        'POOL_ORCHESTRATOR_ID':'fixture-root',
        'POOL_PARENT_RUN_ID':'fixture-parent',
        'REMOTE_SUB_SSH_CMD':'/usr/bin/false',
        'REMOTE_SUB_SCP_CMD':'/usr/bin/false',
        'REMOTE_SUB_RSYNC_CMD':'/usr/bin/false',
        'REMOTE_SUB_LOG_DIR':str(Path(tmp)/'logs')}
    cmd=['/bin/bash',str(shell),'ubuntu2','glm',str(packet),
         '~/lanes/repos/macro','glm-5.3',
         '--run-id','fixture-sparse-no-network',
         '--new-macro-worktree','a'*40,'--dry-run']
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=22,env=env)
    assert p.returncode==0,(p.returncode,p.stderr[-800:])
    assert '<launch:' in p.stdout
    assert 'ubuntu2' in p.stdout
    assert 'LEASE_WAIT' in p.stderr
    assert 'RUN_RESERVED' not in p.stderr
    assert 'REMOTE_DONE' not in p.stderr
    assert packet.read_text().startswith('OBJECTIVE:')
    bad=cmd[:]
    bad[bad.index('a'*40)]='garbage'
    q=subprocess.run(bad,capture_output=True,text=True,timeout=6,env=env)
    assert q.returncode==78
    assert 'FABRIC_NEW_MACRO_SCOPE_REFUSED' in q.stderr
print('FABRIC_SPARSE_LAUNCHER_DRYRUN_PASS: positive preview and early invalid-SHA refusal; no SSH/provider call')
