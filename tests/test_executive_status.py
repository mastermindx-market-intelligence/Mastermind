"""Postcondition proof tests for the read-only host status listener inspection.

These tests run the real `status.sh` body (a per-test disposable copy with the
fixed LaunchDaemon, socket, and native-command paths pointed at tmp_path
executables). Every non-listener health input is held green, so the exit code
is decided by the listener inspection alone. No real root, sudo, launchctl,
lsof, service, or network effect occurs.

The lsof table fixtures are verbatim Darwin lsof 4.91 output captured on a
Mac Studio (Darwin 25.5.0) for a real account with listeners, including the
`\\x20` escape lsof prints for a space inside COMMAND; only the USER column was
renamed to the inspected account. The same host was used to establish the two
facts the script relies on: a no-match query exits 1 with no stdout and no
stderr, and an unprivileged query for *another* account does exactly the same
(root saw 30 listener rows for root; uid 501 saw none and no error).
"""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "status.sh"

CONTROL_USER = "_mastermind_exec"
WORKER_USER = "_mastermind_worker"
CONTROL_UID = "450"
WORKER_UID = "451"
UNPRIVILEGED_UID = "501"

LSOF_ARGS = "-nP -a -u {account} -iTCP -sTCP:LISTEN"

LSOF_HEADER = "COMMAND     PID      USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME"
LSOF_ROWS = [
    r"rapportd   1240 _mastermind_exec   13u  IPv4 0x676208d9df997bda      0t0  TCP *:49154 (LISTEN)",
    r"rapportd   1240 _mastermind_exec   14u  IPv6 0x599ea11b9b64cc35      0t0  TCP *:49154 (LISTEN)",
    r"Adobe\x20  4262 _mastermind_exec   35u  IPv4 0xfbbc43b46e4b30d8      0t0  TCP 127.0.0.1:15292 (LISTEN)",
]
LSOF_LISTENER_TABLE = "\n".join([LSOF_HEADER, *LSOF_ROWS]) + "\n"

# lsof's documented incomplete-output warning form. The qualification host
# emitted no warning at all; this is the shape lsof uses when it does.
LSOF_WARNING = (
    "lsof: WARNING: can't stat() fuse file system /Volumes/example\n"
    "      Output information may be incomplete.\n"
)

# Test-only native command executables. The disposable script is rewritten to
# these exact paths, so production keeps using absolute macOS binaries and the
# tests do not depend on shell function interception of path-qualified commands.
ID_SHIM = r'''#!/bin/bash
if [ "${1:-}" = "-u" ]; then
  case "${2:-}" in
    "") printf '%s\n' "${FAKE_UID:-0}" ;;
    _mastermind_exec) printf '%s\n' "450" ;;
    _mastermind_worker) printf '%s\n' "451" ;;
    *) printf 'id: %s: no such user\n' "$2" >&2; exit 1 ;;
  esac
  exit 0
fi
case "${1:-}" in
  _mastermind_exec) printf 'uid=450(_mastermind_exec) gid=450(_mastermind_exec)\n' ;;
  _mastermind_worker) printf 'uid=451(_mastermind_worker) gid=451(_mastermind_worker)\n' ;;
  *) printf 'id: %s: no such user\n' "${1:-}" >&2; exit 1 ;;
esac
'''

LAUNCHCTL_SHIM = r'''#!/bin/bash
printf '\tstate = running\n\tpid = 4242\n\tlast exit code = 0\n'
'''

PLUTIL_SHIM = r'''#!/bin/bash
if [ "${1:-}" = "-lint" ]; then
  printf '%s: OK\n' "$2"
  exit 0
fi
exit 1
'''

STAT_SHIM = r'''#!/bin/bash
printf 'stat_shim args=%s\n' "$*"
'''

# One recorded invocation per call; output and exit code come from the test.
LSOF_SHIM = r'''#!/bin/bash
printf '%s\n' "$*" >> "$FAKE_LSOF_LOG"
if [ -n "${FAKE_LSOF_STDOUT_FILE:-}" ]; then cat "$FAKE_LSOF_STDOUT_FILE"; fi
if [ -n "${FAKE_LSOF_STDERR_FILE:-}" ]; then cat "$FAKE_LSOF_STDERR_FILE" >&2; fi
exit "${FAKE_LSOF_EXIT:-1}"
'''


def _write_executable(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return path


def _native_shims(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "native-shims"
    root.mkdir(exist_ok=True)
    return {
        "/usr/bin/id": _write_executable(root / "id", ID_SHIM),
        "/bin/launchctl": _write_executable(root / "launchctl", LAUNCHCTL_SHIM),
        "/usr/bin/plutil": _write_executable(root / "plutil", PLUTIL_SHIM),
        "/usr/bin/stat": _write_executable(root / "stat", STAT_SHIM),
        "/usr/sbin/lsof": _write_executable(root / "lsof", LSOF_SHIM),
    }


def _prepare_script(tmp_path: Path, socket_root: Path) -> tuple[Path, Path]:
    text = SCRIPT.read_text(encoding="utf-8")
    shims = _native_shims(tmp_path)
    for native, shim in shims.items():
        assert native in text, native
        text = text.replace(native, str(shim))
        assert native not in text
    control_plist = tmp_path / "control.plist"
    worker_plist = tmp_path / "worker.plist"
    text = text.replace(
        'CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"',
        f'CONTROL_PLIST="{control_plist}"',
    )
    text = text.replace(
        'WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"',
        f'WORKER_PLIST="{worker_plist}"',
    )
    assert str(control_plist) in text and str(worker_plist) in text
    assert text.count("/var/run/mastermind-executive/") == 2
    text = text.replace("/var/run/mastermind-executive/", f"{socket_root}/")
    control_plist.write_text("control-plist", encoding="utf-8")
    worker_plist.write_text("worker-plist", encoding="utf-8")
    copy_path = tmp_path / "status.sh"
    copy_path.write_text(text, encoding="utf-8")
    copy_path.chmod(0o755)
    return copy_path, shims["/usr/sbin/lsof"]


def _bind_private_sockets(socket_root: Path) -> list[socket.socket]:
    held = []
    for name in ("control.sock", "worker.sock"):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_root / name))
        held.append(listener)
    return held


def _run(
    tmp_path: Path,
    socket_root: Path,
    *,
    inspector_uid: str = "0",
    lsof_exit: int = 1,
    lsof_stdout: str = "",
    lsof_stderr: str = "",
    remove_lsof: bool = False,
) -> tuple[int, str, str, list[str]]:
    script, lsof_shim = _prepare_script(tmp_path, socket_root)
    if remove_lsof:
        lsof_shim.unlink()
    log_path = tmp_path / "lsof.log"
    log_path.write_text("", encoding="utf-8")
    stdout_path = tmp_path / "lsof.stdout"
    stderr_path = tmp_path / "lsof.stderr"
    stdout_path.write_text(lsof_stdout, encoding="utf-8")
    stderr_path.write_text(lsof_stderr, encoding="utf-8")
    env = {
        "HOME": "/var/empty",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "FAKE_UID": inspector_uid,
        "FAKE_LSOF_LOG": str(log_path),
        "FAKE_LSOF_EXIT": str(lsof_exit),
        "FAKE_LSOF_STDOUT_FILE": str(stdout_path),
        "FAKE_LSOF_STDERR_FILE": str(stderr_path),
    }
    held = _bind_private_sockets(socket_root)
    try:
        completed = subprocess.run(
            ["/bin/bash", str(script)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        for listener in held:
            listener.close()
    return (
        completed.returncode,
        completed.stdout,
        completed.stderr,
        log_path.read_text(encoding="utf-8").splitlines(),
    )


def _one_query_per_account(log: list[str]) -> None:
    assert log == [
        LSOF_ARGS.format(account=CONTROL_USER),
        LSOF_ARGS.format(account=WORKER_USER),
    ]


def _assert_unknown(out: str, account: str, reason: str) -> None:
    assert f"tcp_listener_state=UNKNOWN account={account} reason={reason}" in out
    assert f"tcp_listener_count=0 account={account}" not in out
    assert f"public_listener_violation={account}" not in out


def test_no_match_exit_is_the_only_zero_listener_proof(
    tmp_path: Path, short_socket_root: Path
) -> None:
    code, out, err, log = _run(tmp_path, short_socket_root, lsof_exit=1)
    assert code == 0, (out, err)
    assert f"tcp_listener_count=0 account={CONTROL_USER}" in out
    assert f"tcp_listener_count=0 account={WORKER_USER}" in out
    assert "UNKNOWN" not in out
    assert "public_listener_violation" not in out
    _one_query_per_account(log)


def test_listener_rows_are_a_violation_echoed_from_one_observation(
    tmp_path: Path, short_socket_root: Path
) -> None:
    code, out, err, log = _run(
        tmp_path, short_socket_root, lsof_exit=0, lsof_stdout=LSOF_LISTENER_TABLE
    )
    assert code != 0
    assert f"public_listener_violation={CONTROL_USER}" in out
    assert f"public_listener_violation={WORKER_USER}" in out
    # The evidence rows are echoed verbatim, including lsof's \x20 space escape.
    for row in LSOF_ROWS:
        assert row in out
    assert "tcp_listener_count=0" not in out
    assert "UNKNOWN" not in out
    # Exactly one lsof observation per account: no second query after detection.
    _one_query_per_account(log)


def test_lsof_diagnostics_with_no_match_exit_are_unknown_not_zero(
    tmp_path: Path, short_socket_root: Path
) -> None:
    code, out, err, log = _run(
        tmp_path, short_socket_root, lsof_exit=1, lsof_stderr=LSOF_WARNING
    )
    assert code != 0
    for account in (CONTROL_USER, WORKER_USER):
        _assert_unknown(out, account, "inspection_failed")
    assert "lsof_exit=1" in out
    # The diagnostic itself is preserved as evidence of why the state is unknown.
    assert "Output information may be incomplete." in out
    _one_query_per_account(log)


def test_missing_lsof_is_unknown_with_exit_127(
    tmp_path: Path, short_socket_root: Path
) -> None:
    code, out, err, log = _run(tmp_path, short_socket_root, remove_lsof=True)
    assert code != 0
    for account in (CONTROL_USER, WORKER_USER):
        _assert_unknown(out, account, "inspection_failed")
    assert "lsof_exit=127" in out
    assert log == []


@pytest.mark.parametrize(
    "stdout",
    [
        pytest.param("", id="success-exit-with-no-table"),
        pytest.param(LSOF_HEADER + "\n", id="header-only"),
        pytest.param("not a lsof table\n", id="garbage"),
        pytest.param(
            LSOF_LISTENER_TABLE + LSOF_WARNING, id="rows-then-incomplete-warning"
        ),
        pytest.param(
            LSOF_WARNING + LSOF_LISTENER_TABLE, id="incomplete-warning-then-rows"
        ),
    ],
)
def test_success_exit_with_unqualified_table_is_unknown(
    tmp_path: Path, short_socket_root: Path, stdout: str
) -> None:
    code, out, err, log = _run(
        tmp_path, short_socket_root, lsof_exit=0, lsof_stdout=stdout
    )
    assert code != 0
    for account in (CONTROL_USER, WORKER_USER):
        _assert_unknown(out, account, "malformed_observation")
    assert "lsof_exit=0" in out
    _one_query_per_account(log)


def test_unexpected_lsof_exit_code_is_unknown(
    tmp_path: Path, short_socket_root: Path
) -> None:
    code, out, err, log = _run(tmp_path, short_socket_root, lsof_exit=2)
    assert code != 0
    for account in (CONTROL_USER, WORKER_USER):
        _assert_unknown(out, account, "inspection_failed")
    assert "lsof_exit=2" in out


def test_unprivileged_inspector_is_unknown_without_querying_lsof(
    tmp_path: Path, short_socket_root: Path
) -> None:
    # Darwin lsof answers an unprivileged query for another account with the
    # same exit 1 / empty output as a true zero, so the script must not ask.
    code, out, err, log = _run(
        tmp_path, short_socket_root, inspector_uid=UNPRIVILEGED_UID, lsof_exit=1
    )
    assert code != 0
    for account in (CONTROL_USER, WORKER_USER):
        _assert_unknown(out, account, "insufficient_privilege")
    assert f"inspector_uid={UNPRIVILEGED_UID}" in out
    assert log == []


def test_account_may_observe_itself_but_not_the_other_account(
    tmp_path: Path, short_socket_root: Path
) -> None:
    code, out, err, log = _run(
        tmp_path, short_socket_root, inspector_uid=CONTROL_UID, lsof_exit=1
    )
    assert code != 0
    assert f"tcp_listener_count=0 account={CONTROL_USER}" in out
    _assert_unknown(out, WORKER_USER, "insufficient_privilege")
    assert log == [LSOF_ARGS.format(account=CONTROL_USER)]


def test_other_health_output_is_unchanged_around_the_inspection(
    tmp_path: Path, short_socket_root: Path
) -> None:
    code, out, err, log = _run(tmp_path, short_socket_root, lsof_exit=1)
    assert code == 0, (out, err)
    assert "service=com.mastermind.executive.control \tstate = running" in out
    assert "service=com.mastermind.executive.worker.codex \tstate = running" in out
    assert f"uid={CONTROL_UID}({CONTROL_USER})" in out
    assert f"uid={WORKER_UID}({WORKER_USER})" in out
    assert out.count("stat_shim args=") == 4
    assert "missing_unix_socket" not in out
