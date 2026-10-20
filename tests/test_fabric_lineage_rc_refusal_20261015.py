"""Hermetic shell regression for original Fabric lineage refusal rc propagation.

The source under test is the source-only PR patch, not a live worker, broker,
credential, host, support generation, or physical admission. No network calls.
"""
from pathlib import Path
import os
import shlex
import subprocess

import pytest

PATCH = Path(os.environ["FABRIC_RC_PATCH"]) if "FABRIC_RC_PATCH" in os.environ else (
    Path(__file__).resolve().parents[1] / "integrations/fleet/ubuntu_thermal_headroom_20261013"
    / "FABRIC_ACCEPTED_WORKTREE_RECLAIM_PLAN_20261015.patch"
)
LINE = 'RC=78; log "FABRIC_NEW_MACRO_LINEAGE_REFUSED rc=$RC before_launch=1"; exit "$RC"'


def _reviewed_launcher_block():
    full = PATCH.read_text(encoding="utf-8")
    assert full.count("+++ b/remote_sub.sh") == 1
    remote = full.split("+++ b/remote_sub.sh", 1)[1]
    begin = remote.index('\n+if [ -n "$NEW_MACRO_COMMIT" ]; then') + 1
    end = remote.index('\n log "LAUNCH stdout=$REMOTE_STDOUT', begin)
    added = remote[begin:end].splitlines()
    assert all(s.startswith("+") for s in added)
    block = "\n".join(s[1:] for s in added) + "\n"
    assert block.count(LINE) == 1
    return block


def _isolated_shell(block, *, enabled=True, root="valid-root", parent="valid-parent"):
    assignments = {
        "RC": "1",
        "NEW_MACRO_COMMIT": "a" * 40 if enabled else "",
        "POOL_ORCHESTRATOR_ID": root,
        "POOL_PARENT_RUN_ID": parent,
        "ID": "safe-case-1",
    }
    init = "\n".join(k + "=" + shlex.quote(v) for k, v in assignments.items())
    script = (init + '\nlog() { printf "%s\\n" "$*"; }\n'
              + 'trap \'exit "$RC"\' EXIT\n' + block + '\nRC=0\n')
    return subprocess.run(["/bin/bash", "-c", script], check=False,
                          text=True, capture_output=True, timeout=4,
                          env={"PATH": "/usr/bin:/bin"})


@pytest.mark.parametrize("root,parent", [
    ("bad/root", "valid-parent"),
    ("valid-root", "bad/parent"),
    ("", "valid-parent"),
    ("valid-root", ""),
])
def test_invalid_lineage_is_typed_prelaunch_refusal(root, parent):
    r = _isolated_shell(_reviewed_launcher_block(), root=root, parent=parent)
    assert r.returncode == 78, (r.stdout, r.stderr)
    assert "FABRIC_NEW_MACRO_LINEAGE_REFUSED rc=78 before_launch=1" in r.stdout
    assert "FABRIC_NEW_MACRO_WORKTREE" not in r.stdout
    assert not r.stderr


def test_valid_optin_still_emits_unique_intent():
    r = _isolated_shell(_reviewed_launcher_block())
    assert r.returncode == 0
    assert r.stdout.count("FABRIC_NEW_MACRO_WORKTREE") == 1
    assert "root=valid-root parent=valid-parent" in r.stdout
    assert "LINEAGE_REFUSED" not in r.stdout


def test_no_optin_keeps_original_behavior():
    r = _isolated_shell(_reviewed_launcher_block(), enabled=False,
                        root="bad/root", parent="bad/parent")
    assert r.returncode == 0
    assert not r.stdout and not r.stderr


def test_old_untyped_line_would_reproduce_incorrect_exit_one():
    block = _reviewed_launcher_block()
    previous = block.replace(LINE, 'log "FABRIC_NEW_MACRO_LINEAGE_REFUSED before_launch=1"; exit 78')
    assert previous != block
    r = _isolated_shell(previous, root="bad/root")
    assert r.returncode == 1
    assert "FABRIC_NEW_MACRO_LINEAGE_REFUSED" in r.stdout
