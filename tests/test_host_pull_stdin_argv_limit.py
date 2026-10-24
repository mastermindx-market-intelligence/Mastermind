"""Inert MAX_ARG_STRLEN regression for the existing host-pull SSH carrier.

Never contacts SSH, provider accounts, or a live host-pull collector.
"""
from pathlib import Path
import subprocess

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
    assert 0 < len(result.stdout) < 1024
    assert "mktemp" in result.stdout and "trap" in result.stdout
    return result.stdout


def test_oversized_probe_executes_via_stdin_and_propagates_status(tmp_path):
    wrapper = _fixed_remote_wrapper(tmp_path)
    env = {"HOME": str(tmp_path), "PATH": ""}
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


def test_local_execution_and_strict_diagnostic_ssh_policy_unchanged():
    source = SOURCE.read_text()
    assert 'sh -c "$probe" 2>/dev/null' in source
    assert "fixed-hook-inspection" in source
    assert "fixed-physical-diagnostic" in source
    assert "StrictHostKeyChecking=yes" in source
    assert "UpdateHostKeys=no" in source
