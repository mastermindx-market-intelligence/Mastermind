"""Bounded POSIX execution for this fixed upstream qualification recipe only.

Each command gets its own new session/process group. Signals target only that
created group; no process enumeration, name matching, or shared-service signal.
This does not supervise programs that deliberately escape their owned session.
"""
import os
from pathlib import Path
import signal
import subprocess
import time


def _exists(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # macOS reports EPERM for a group containing only unreaped zombies.
        # Presence is uncertain: retain ownership and wait; never call it empty.
        return True


def _wait_empty(proc, seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        proc.poll()  # reap the directly owned child
        if not _exists(proc.pid):
            return True
        time.sleep(0.01)
    proc.poll()
    return not _exists(proc.pid)


def _signal(group, sig):
    try:
        os.killpg(group, sig)
    except ProcessLookupError:
        pass


def _settle(proc, grace):
    if _wait_empty(proc, 0.05):
        return False
    _signal(proc.pid, signal.SIGTERM)
    if not _wait_empty(proc, grace):
        _signal(proc.pid, signal.SIGKILL)
        if not _wait_empty(proc, grace):
            raise RuntimeError('owned command group did not settle; teardown unproven')
    proc.wait(timeout=grace)
    return True


def run(argv, root, log, timeout=180, grace=2):
    if os.name != 'posix':
        raise RuntimeError('qualification requires an admitted POSIX process-group owner')
    if not 0 < timeout <= 180 or not 0 < grace <= 2:
        raise ValueError('invalid bounded execution budget')
    with Path(log).open('w') as output:
        proc = subprocess.Popen(argv, cwd=root, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        finally:
            # Timeout/interrupt does not release ownership at the direct child.
            # Cleanup runs for success too, so nested children cannot outlive it.
            forced = _settle(proc, grace)
        if code == 0 and forced:
            raise RuntimeError('owned descendants outlived successful command')
        if code:
            raise subprocess.CalledProcessError(code, argv)
