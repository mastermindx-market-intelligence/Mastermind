"""Heredocs in the native remote launcher must never be fed through a pipe.

bash >=5.1 writes a heredoc below its pipe size into a pipe before the reader
runs; on M2 (homebrew bash 5.3.9) a 777-byte heredoc blocked there forever.
The deadlock needs a transient low pipe capacity and cannot be reproduced on
demand, so these tests assert the transport (temp file vs pipe) under every
available interpreter, each bounded by a timeout. No host, lease or provider.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "ops/native_fabric/quota_continuity/candidate/remote_sub.sh"
PROBE = r'''d=$(printf '%04096d' 0)
( if [ -p /dev/stdin ]; then echo pipe; elif [ -f /dev/stdin ]; then echo file; else echo other; fi ) <<EOF
$d
EOF
'''


def _interpreters():
    found = {}
    for path in ("/bin/bash", shutil.which("bash"), "/opt/homebrew/bin/bash", "/usr/local/bin/bash"):
        if path and os.access(path, os.X_OK):
            found.setdefault(os.path.realpath(path), path)
    return sorted(found.values())


def _env():
    env = dict(os.environ)
    env.pop("BASH_COMPAT", None)
    return env


def _version(bash):
    out = subprocess.run([bash, "-c", 'echo "${BASH_VERSINFO[0]} ${BASH_VERSINFO[1]}"'],
                         env=_env(), capture_output=True, text=True, timeout=10, check=True)
    return tuple(int(part) for part in out.stdout.split())


@pytest.mark.parametrize("bash", _interpreters())
def test_selftest_proves_tempfile_heredoc_within_timeout(bash):
    run = subprocess.run([bash, str(CANDIDATE), "--selftest-heredoc"], env=_env(),
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert run.stdout.startswith("HEREDOC_SELFTEST_OK transport=file bytes=4097 "), run.stdout
    assert run.stdout.rstrip().endswith(" compat=50")


@pytest.mark.parametrize("bash", _interpreters())
def test_unguarded_control_shows_the_pipe_hazard(bash):
    if _version(bash) < (5, 1):
        pytest.skip("bash < 5.1 always uses temp-file heredocs")
    run = subprocess.run([bash, "-c", PROBE], env=_env(), capture_output=True, text=True, timeout=30)
    assert run.stdout.strip() == "pipe"
    guarded = subprocess.run([bash, "-c", "export BASH_COMPAT=50\n" + PROBE], env=_env(),
                             capture_output=True, text=True, timeout=30)
    assert guarded.stdout.strip() == "file"


def test_guard_precedes_every_heredoc_and_is_never_reset():
    lines = CANDIDATE.read_text().splitlines()
    code = [(i, line) for i, line in enumerate(lines) if not line.lstrip().startswith("#")]
    guard = [i for i, line in code if line == "export BASH_COMPAT=50"]
    assert len(guard) == 1
    first_heredoc = min(i for i, line in code if "<<" in line)
    assert guard[0] < first_heredoc
    # First statement after `set -u`, ahead of every exec/early-exit branch.
    between = lines[lines.index("set -u") + 1:guard[0]]
    assert all(not line.strip() or line.lstrip().startswith("#") for line in between)
    writes = [line for _, line in code if "BASH_COMPAT" in line
              and "${BASH_COMPAT:-unset}" not in line and line != "export BASH_COMPAT=50"]
    assert writes == []
