"""Inert MAX_ARG_STRLEN regression for the existing host-pull SSH carrier.

Never contacts SSH, provider accounts, or a live host-pull collector.
"""
from pathlib import Path
import signal
import subprocess
import sys
import os
import time


def _inert_python_env(home):
    # No ordinary PATH tools become visible to the remote stub: only the
    # original Python runtime, through a newly owned temp-fixture symlink.
    target = Path(home) / 'python3'
    if not target.exists():
        target.symlink_to(sys.executable)
    return {'HOME': str(home), 'PATH': str(home)}


def _active_probe_pid(pid):
    result = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'stat='],
                            capture_output=True, text=True, timeout=2)
    if result.returncode != 0:
        return False
    state = result.stdout.strip()
    return bool(state and not state.startswith('Z'))


SOURCE = (Path(__file__).resolve().parents[1] /
          "ops/native_fabric/quota_continuity/candidate/host_pull.sh")


def _fixed_remote_wrapper(home):
    source = SOURCE.read_text()
    assignments = [line for line in source.splitlines()
                   if line.startswith("HOST_PULL_REMOTE_STDIN_EXEC=")]
    assert len(assignments) == 1
    assert '"${key_options[@]}" "$alias" "$HOST_PULL_REMOTE_STDIN_EXEC"' in source
    assert '<<< "$probe"' in source
    # Isolated shell with empty PATH: no remote shell, network, or credentials.
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c",
         assignments[0] + '\n' + 'printf "%s" "$HOST_PULL_REMOTE_STDIN_EXEC"'],
        env={"HOME": str(home), "PATH": ""},
        capture_output=True, text=True, check=True, timeout=5)
    assert 0 < len(result.stdout) < 4096
    assert "mktemp" in result.stdout and "trap" in result.stdout
    return result.stdout


def test_oversized_probe_executes_via_stdin_and_propagates_status(tmp_path):
    wrapper = _fixed_remote_wrapper(tmp_path)
    env = _inert_python_env(tmp_path)
    for exitcode in (0, 17):
        payload = ('if read line; then echo INVALID_CHILD_STDIN; exit 33; fi\n'
                   'printf "PHYSICAL_OK\\n"\n'
                   f'exit {exitcode}\n#' + "X" * 140_500 + "\n")
        assert len(payload.encode()) > 131072
        # Only the short wrapper goes in -c, the large script goes on stdin.
        # TEMP lives entirely in the isolated fixture and must be unlinked.
        result = subprocess.run(
            ["/bin/bash", "--noprofile", "--norc", "-c",
             'export TMPDIR="$HOME"; ' + wrapper],
            input=payload, env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == exitcode, result.stderr
        assert result.stdout == "PHYSICAL_OK\n"
        assert list(tmp_path.glob("host_pull_probe.*")) == []



def test_interrupts_fail_closed_and_remove_private_spool(tmp_path):
    wrapper = _fixed_remote_wrapper(tmp_path)
    env = _inert_python_env(tmp_path)
    for sig, expected in ((signal.SIGHUP, 129), (signal.SIGINT, 130),
                          (signal.SIGTERM, 143)):
        child = subprocess.Popen(
            ["/bin/sh", "-c", 'export TMPDIR="$HOME"; ' + wrapper],
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            child.stdin.write("echo CHILD_STARTED\n/bin/sleep 2\necho CHILD_COMPLETED\n")
            child.stdin.close()
            assert child.stdout.readline() == "CHILD_STARTED\n"
            child.send_signal(sig)
            assert child.wait(timeout=5) == expected, child.stderr.read()
            assert "CHILD_COMPLETED" not in child.stdout.read()
            assert list(tmp_path.glob("host_pull_probe.*")) == []
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream and not stream.closed:
                    stream.close()

def test_local_execution_and_strict_diagnostic_ssh_policy_unchanged():
    source = SOURCE.read_text()
    assert 'sh -c "$probe" 2>/dev/null' in source
    assert "fixed-hook-inspection" in source
    assert "fixed-physical-diagnostic" in source
    assert "StrictHostKeyChecking=yes" in source
    assert "UpdateHostKeys=no" in source



def test_cancel_terminates_foreground_and_background_probe_subprocesses(tmp_path):
    """Cancelled wrapper must leave no live probe shell or Python descendant.

    Each PID originates in a private fixture. The wrapper uses its own
    supervisor-owned process group; the test never targets external groups.
    """
    wrapper = _fixed_remote_wrapper(tmp_path)
    env = _inert_python_env(tmp_path)
    child_script = ('python3 -c ' +
                    repr('import os,time; print("PROBE_PID="+str(os.getpid()),flush=True); time.sleep(10)'))
    for background in (False, True):
        for sig, expected in ((signal.SIGHUP, 129), (signal.SIGINT, 130),
                              (signal.SIGTERM, 143)):
            if background:
                payload = child_script + ' &\nwait "$!"\necho CHILD_COMPLETED\n'
            else:
                payload = child_script + '\necho CHILD_COMPLETED\n'
            child = subprocess.Popen(
                ['/bin/sh', '-c', 'export TMPDIR="$HOME"; ' + wrapper],
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, start_new_session=True)
            desc_pid = None
            try:
                child.stdin.write(payload)
                child.stdin.close()
                child.stdin = None
                line = child.stdout.readline().strip()
                assert line.startswith('PROBE_PID='), (sig, background, line)
                desc_pid = int(line.split('=', 1)[1])
                assert _active_probe_pid(desc_pid)
                child.send_signal(sig)
                output, errors = child.communicate(timeout=5)
                assert child.returncode == expected, (sig, background, child.returncode, errors)
                assert 'CHILD_COMPLETED' not in output
                for _ in range(25):
                    if not _active_probe_pid(desc_pid):
                        break
                    time.sleep(0.04)
                assert not _active_probe_pid(desc_pid), (sig, background, desc_pid)
                assert list(tmp_path.glob('host_pull_probe.*')) == []
            finally:
                if desc_pid and _active_probe_pid(desc_pid):
                    os.kill(desc_pid, signal.SIGKILL)
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.communicate(timeout=5)
                for stream in (child.stdin, child.stdout, child.stderr):
                    if stream and not stream.closed:
                        stream.close()
