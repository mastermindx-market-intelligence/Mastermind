"""Original Fabric sparse-worker receipt-retention regression (no network/worker).

Executed against the actual additive source diff. The launcher must preserve
the physical process receipt after its verified copy to M2 only when the
request actually opted into a NEW sparse Macro worktree. All legacy cleanup,
unknown effects, and source custody remain owned by the original launcher.
"""
from pathlib import Path
import os
import subprocess

import pytest

HERE=Path(__file__).resolve().parent
PATCH=Path(os.environ["FABRIC_RECEIPT_PATCH"]) if os.environ.get(
    "FABRIC_RECEIPT_PATCH") else (
    HERE.parent/"integrations/fleet/ubuntu_thermal_headroom_20261013"/
    "FABRIC_SPARSE_PROCESS_RECEIPT_RETENTION_20261016.patch"
)


def _script_hunk():
    src=PATCH.read_text()
    assert src.count("+++ b/remote_sub.sh")==1
    assert src.count("-  [ \"$RECEIPT_SAVED\" -eq 1 ] && CLEAN_RECEIPT=")==1
    assert src.count('+  HOST_RECEIPT_RETAINED=0')==1
    assert src.count("host_receipt_retained=$HOST_RECEIPT_RETAINED")==1
    lines=src.splitlines()
    idx=next(i for i,v in enumerate(lines)
             if v=="+  HOST_RECEIPT_RETAINED=0")
    result=[]
    for line in lines[idx:]:
        if not line.startswith("+"): break
        result.append(line[1:])
        if line=="+  fi": break
    assert len(result)>=12 and result[-1]=="  fi",result
    assert result.count('    if [ -n "$NEW_MACRO_COMMIT" ]; then')==1
    assert result.count('  if [ "$RECEIPT_SAVED" -eq 1 ]; then')==1
    assert result.count('      HOST_RECEIPT_RETAINED=1')==1
    assert any('CLEAN_RECEIPT=' in row and r'\$HOME/lanes/ext/lanes/' in row for row in result)
    return "\n".join(result)+"\n"


def _run(receipt_saved, new_macro):
    code='''#!/bin/bash
set -u
ID=receipt-fixture
RECEIPT_SAVED=$1
NEW_MACRO_COMMIT=$2
CLEAN_RECEIPT=''
log() { printf '%s\n' "$*" >&2; }
''' + _script_hunk() + '''
printf 'retained=%s\n' "$HOST_RECEIPT_RETAINED"
printf 'clean=%s\n' "$CLEAN_RECEIPT"
'''
    return subprocess.run(
        ["bash","-c",code,"fixture",str(receipt_saved),
         "a"*40 if new_macro else ""],
        capture_output=True,text=True,timeout=8,check=False,
        env={"PATH":"/usr/bin:/bin"},
    )


@pytest.mark.parametrize("saved", [0,1])
def test_new_sparse_receipt_retained_iff_original_copy_saved(saved):
    p=_run(saved,True)
    assert p.returncode==0,(p.stderr,p.stdout)
    assert ("retained=1" if saved else "retained=0") in p.stdout
    assert "clean=\n" in p.stdout
    if saved:
        assert p.stderr.count("HOST_PROCESS_RECEIPT_RETAINED ")==1
        assert "controller_copy=1" in p.stderr
    else:
        assert "HOST_PROCESS_RECEIPT_RETAINED" not in p.stderr


@pytest.mark.parametrize("saved", [0,1])
def test_all_legacy_receipt_cleanup_semantics_preserved(saved):
    p=_run(saved,False)
    assert p.returncode==0,(p.stderr,p.stdout)
    assert "retained=0\n" in p.stdout
    if saved:
        assert 'clean= "$HOME/lanes/ext/lanes/receipt-fixture.process.jsonl"' in p.stdout
    else:
        assert "clean=\n" in p.stdout
    assert "HOST_PROCESS_RECEIPT_RETAINED" not in p.stderr


def test_exclusive_receipt_scope_and_no_unrelated_runtime_actions():
    patch=PATCH.read_text()
    assert patch.startswith("--- a/remote_sub.sh\n+++ b/remote_sub.sh\n")
    assert patch.count("\n@@ ")==1
    assert not any(s in patch for s in ("systemctl", "worktree remove", "git push",
                                       "sudo", "ssh -", "rm -rf /"))
    # Existing cleanup condition remains, with the same original $CLEAN_USAGE.
    assert ' $CLEAN_RECEIPT' not in patch
    assert '$CLEAN_RECEIPT$CLEAN_USAGE' in patch
    assert 'REMOTE_CLEANED transport=1 receipt_saved=$RECEIPT_SAVED' in patch
