"""Postcondition proof tests for the bounded start/stop service controller.

These tests run the real `service-control.sh` body (a per-test disposable copy
with the fixed LaunchDaemons and native-command paths pointed at tmp_path
executables). No real root, sudo, launchctl, service, or network effect occurs.
"""
from __future__ import annotations

import subprocess
import json
import plistlib
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "service-control.sh"

CONTROL_LABEL = "com.mastermind.executive.control"
WORKER_LABEL = "com.mastermind.executive.worker.codex"
RELAY_LABEL = "com.mastermind.executive.sol-state-relay"
AGENT_RELAY_LABEL = "com.mastermind.executive.agent-relay"
MCP_LABEL = "com.mastermind.executive.mcp"
BACKUP_LABEL = "com.mastermind.executive.backup"

# Test-only native command executables. The disposable script is rewritten to
# these exact paths, so production keeps using absolute macOS binaries and the
# tests do not depend on shell function interception of path-qualified commands.
ID_SHIM = r'''#!/bin/bash
if [ "${1:-}" = "-u" ] && [ "$#" -eq 1 ]; then
  printf '%s\n' "${FAKE_UID:-0}"
  exit 0
fi
if [ "${1:-}" = "-u" ] && [ "$#" -eq 2 ]; then
  [ "$2" = "${FAKE_SERVICE_USER:-}" ] || exit 1
  printf '%s\n' "${FAKE_SERVICE_UID:-458}"
  exit 0
fi
if [ "${1:-}" = "-gn" ] && [ "$#" -eq 2 ]; then
  [ "$2" = "${FAKE_SERVICE_USER:-}" ] || exit 1
  printf '%s\n' "${FAKE_SERVICE_GROUP:-_mastermind_executive_mcp}"
  exit 0
fi
exec /usr/bin/id "$@"
'''

UNAME_SHIM = r'''#!/bin/bash
if [ "${1:-}" = "-s" ]; then
  printf '%s\n' "${FAKE_OS_NAME:-Darwin}"
  exit 0
fi
exec /usr/bin/uname "$@"
'''

PLUTIL_SHIM = r'''#!/bin/bash
if [ "${1:-}" = "-lint" ]; then
  exit 0
fi
exec /usr/bin/plutil "$@"
'''

GATEWAY_PREFLIGHT_PYTHON_SHIM = r'''#!/bin/bash
[ "$#" -eq 6 ] || exit 97
[ "$1" = "-I" ] && [ "$2" = "-S" ] && [ "$3" = "-B" ] || exit 97
[ "$5" = "--expected-sha" ] || exit 97
case "$4" in
  */releases/"$6"/ops/executive_os/gateway_refresh_preflight.py) ;;
  *) exit 97 ;;
esac
exit "${FAKE_GATEWAY_PREFLIGHT_EXIT:-0}"
'''

LAUNCHCTL_SHIM = r'''#!/bin/bash
key="$*"
printf '%s\n' "$key" >> "$FAKE_LAUNCHCTL_LOG"
if [ ! -s "$FAKE_LAUNCHCTL_PLAN" ]; then
  printf 'unexpected launchctl invocation (plan exhausted): %s\n' "$key" >&2
  exit 98
fi
line="$(head -n 1 "$FAKE_LAUNCHCTL_PLAN")"
IFS=$'\t' read -r plan_key plan_exit plan_out plan_err <<< "$line"
tail -n +2 "$FAKE_LAUNCHCTL_PLAN" > "$FAKE_LAUNCHCTL_PLAN.next"
mv "$FAKE_LAUNCHCTL_PLAN.next" "$FAKE_LAUNCHCTL_PLAN"
if [ "$plan_key" != "$key" ]; then
  printf 'launchctl call out of scope: expected [%s] got [%s]\n' "$plan_key" "$key" >&2
  exit 97
fi
[ -n "$plan_out" ] && printf '%b\n' "$plan_out"
[ -n "$plan_err" ] && printf '%s\n' "$plan_err" >&2
exit "$plan_exit"
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
        "/usr/bin/uname": _write_executable(root / "uname", UNAME_SHIM),
        "/usr/bin/plutil": _write_executable(root / "plutil", PLUTIL_SHIM),
        "/bin/launchctl": _write_executable(root / "launchctl", LAUNCHCTL_SHIM),
        "/bin/sleep": _write_executable(root / "sleep", '#!/bin/bash\n[ "$*" = "1" ]\n'),
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12":
            _write_executable(root / "gateway-preflight-python", GATEWAY_PREFLIGHT_PYTHON_SHIM),
    }


Entry = tuple[str, int, str, str]


def _prepare_script(tmp_path: Path) -> tuple[Path, Path, Path]:
    text = SCRIPT.read_text(encoding="utf-8")
    for native, shim in _native_shims(tmp_path).items():
        text = text.replace(native, str(shim))
        assert native not in text
    control_plist = tmp_path / "control.plist"
    worker_plist = tmp_path / "worker.plist"
    relay_plist = tmp_path / "relay.plist"
    agent_relay_plist = tmp_path / "agent-relay.plist"
    mcp_plist = tmp_path / "mcp.plist"
    text = text.replace(
        'CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"',
        f'CONTROL_PLIST="{control_plist}"',
    )
    text = text.replace(
        'WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"',
        f'WORKER_PLIST="{worker_plist}"',
    )
    text = text.replace(
        'RELAY_PLIST="/Library/LaunchDaemons/$RELAY_LABEL.plist"',
        f'RELAY_PLIST="{relay_plist}"',
    )
    text = text.replace(
        'AGENT_RELAY_PLIST="/Library/LaunchDaemons/$AGENT_RELAY_LABEL.plist"',
        f'AGENT_RELAY_PLIST="{agent_relay_plist}"',
    )
    text = text.replace(
        'MCP_PLIST="/Library/LaunchDaemons/$MCP_LABEL.plist"',
        f'MCP_PLIST="{mcp_plist}"',
    )
    assert str(control_plist) in text and str(worker_plist) in text
    assert str(agent_relay_plist) in text
    copy_path = tmp_path / "service-control.sh"
    copy_path.write_text(text, encoding="utf-8")
    copy_path.chmod(0o755)
    control_plist.write_text("control-plist", encoding="utf-8")
    worker_plist.write_text("worker-plist", encoding="utf-8")
    relay_plist.write_text("relay-plist", encoding="utf-8")
    agent_relay_plist.write_text("agent-relay-plist", encoding="utf-8")
    mcp_plist.write_text("mcp-plist", encoding="utf-8")
    return copy_path, control_plist, worker_plist


def _write_plan(path: Path, entries: list[Entry]) -> None:
    lines = ["\t".join((key, str(exit_code), out.replace("\n", r"\n"), err)) for key, exit_code, out, err in entries]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _run(
    tmp_path: Path,
    action: str,
    plan: list[Entry],
    *,
    fake_uid: str = "0",
    fake_os: str = "Darwin",
    remove_agent_relay_plist: bool = False,
    extra_args: tuple[str, ...] = (),
    prepare: Callable[[Path], None] | None = None,
    spoof_argv0: str | None = None,
    shadow_cd: bool = False,
    cwd: Path | None = None,
) -> tuple[int, str, str, list[str], str, Path, Path]:
    script, control_plist, worker_plist = _prepare_script(tmp_path)
    if prepare is not None:
        prepare(script)
    if remove_agent_relay_plist:
        (tmp_path / "agent-relay.plist").unlink()
    plan_path = tmp_path / "launchctl.plan"
    log_path = tmp_path / "launchctl.log"
    _write_plan(plan_path, plan)
    log_path.write_text("", encoding="utf-8")
    env = {
        "HOME": "/var/empty",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "FAKE_LAUNCHCTL_PLAN": str(plan_path),
        "FAKE_LAUNCHCTL_LOG": str(log_path),
        "FAKE_UID": fake_uid,
        "FAKE_OS_NAME": fake_os,
        "FAKE_SERVICE_USER": "_mastermind_executive_mcp",
        "FAKE_SERVICE_UID": "458",
        "FAKE_SERVICE_GROUP": "_mastermind_executive_mcp",
    }
    command = ["/bin/bash", str(script), action, *extra_args]
    if spoof_argv0 is not None:
        # Execute the disposable checkout body through the source builtin
        # while supplying a forged installed-controller argv0. $0 follows the
        # caller; BASH_SOURCE[0] must continue to identify the loaded file.
        prelude = "cd() { return 0; }; " if shadow_cd else ""
        command = [
            "/bin/bash",
            "-c",
            prelude + 'source "$1" "${@:2}"',
            spoof_argv0,
            str(script),
            action,
            *extra_args,
        ]
    completed = subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
    )
    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    remaining_plan = plan_path.read_text(encoding="utf-8")
    return (
        completed.returncode,
        completed.stdout,
        completed.stderr,
        log_lines,
        remaining_plan,
        control_plist,
        worker_plist,
    )


def _stop_ok(label: str) -> list[Entry]:
    return [
        (f"disable system/{label}", 0, "", ""),
        (f"bootout system/{label}", 0, "", ""),
        (f"print system/{label}", 113, "", "absent"),
    ]


def _stop_already_absent(label: str) -> list[Entry]:
    return [
        (f"disable system/{label}", 0, "", ""),
        (f"bootout system/{label}", 3, "", "Could not find service"),
        (f"print system/{label}", 113, "", "absent"),
    ]


def _stop_stubborn(label: str, *, bootout_exit: int) -> list[Entry]:
    return [
        (f"disable system/{label}", 0, "", ""),
        (f"bootout system/{label}", bootout_exit, "", ""),
    ] + [(f"print system/{label}", 0, "state = running", "")] * 31


def _stop_unknown_readback(label: str) -> list[Entry]:
    return [
        (f"disable system/{label}", 0, "", ""),
        (f"bootout system/{label}", 0, "", ""),
        (f"print system/{label}", 5, "", "unexpected daemon error"),
    ]


def _start_via_bootstrap(label: str, plist: Path) -> list[Entry]:
    return [
        (f"enable system/{label}", 0, "", ""),
        (f"print system/{label}", 113, "", "absent"),
        (f"bootstrap system {plist}", 0, "", ""),
        (f"print system/{label}", 0, "state = running", ""),
    ]


def _start_via_kickstart(label: str) -> list[Entry]:
    return [
        (f"enable system/{label}", 0, "", ""),
        (f"print system/{label}", 0, "state = running", ""),
        (f"kickstart system/{label}", 0, "", ""),
        (f"print system/{label}", 0, "state = running", ""),
    ]


def _start_bootstrap_lies(label: str, plist: Path) -> list[Entry]:
    return [
        (f"enable system/{label}", 0, "", ""),
        (f"print system/{label}", 113, "", "absent"),
        (f"bootstrap system {plist}", 0, "", ""),
        (f"print system/{label}", 113, "", "absent"),
    ]


def _start_before_unknown(label: str) -> list[Entry]:
    return [
        (f"enable system/{label}", 0, "", ""),
        (f"print system/{label}", 5, "", "unexpected daemon error"),
    ]


def test_start_requires_root(tmp_path: Path) -> None:
    code, _out, err, log, _plan, *_ = _run(tmp_path, "start", [], fake_uid="501")
    assert code == 77
    assert "root" in err
    assert log == []


def test_start_requires_darwin(tmp_path: Path) -> None:
    code, _out, err, log, _plan, *_ = _run(tmp_path, "start", [], fake_os="Linux")
    assert code == 69
    assert log == []


def test_start_confirms_registration_after_bootstrap(tmp_path: Path) -> None:
    script, control_plist, worker_plist = _prepare_script(tmp_path)
    plan = _start_via_bootstrap(WORKER_LABEL, worker_plist) + _start_via_bootstrap(
        CONTROL_LABEL, control_plist
    )
    code, out, err, log, remaining, *_ = _run(tmp_path, "start", plan)
    assert code == 0, err
    assert remaining == ""
    assert f"service={WORKER_LABEL} state = running" in out
    assert f"service={CONTROL_LABEL} state = running" in out
    assert log == [key for key, *_ in plan]


def test_start_confirms_registration_after_kickstart(tmp_path: Path) -> None:
    plan = _start_via_kickstart(WORKER_LABEL) + _start_via_kickstart(CONTROL_LABEL)
    code, out, err, log, remaining, *_ = _run(tmp_path, "start", plan)
    assert code == 0, err
    assert remaining == ""
    assert f"service={WORKER_LABEL} state = running" in out
    assert f"service={CONTROL_LABEL} state = running" in out


def test_start_fails_when_bootstrap_claims_success_but_registration_absent(
    tmp_path: Path,
) -> None:
    script, control_plist, worker_plist = _prepare_script(tmp_path)
    plan = _start_bootstrap_lies(WORKER_LABEL, worker_plist)
    code, out, err, log, remaining, *_ = _run(tmp_path, "start", plan)
    assert code != 0
    assert "missing after start" in err
    assert log == [key for key, *_ in plan]
    assert remaining == ""


def test_start_fails_when_before_check_status_is_unknown_and_does_not_bootstrap(
    tmp_path: Path,
) -> None:
    plan = _start_before_unknown(WORKER_LABEL)
    code, out, err, log, remaining, *_ = _run(tmp_path, "start", plan)
    assert code != 0
    assert "unknown" in err
    assert log == [key for key, *_ in plan]
    # The plan is fully consumed: no bootstrap/kickstart call was ever issued.
    assert remaining == ""


def test_stop_confirms_absence_after_bootout(tmp_path: Path) -> None:
    plan = _stop_ok(CONTROL_LABEL) + _stop_ok(WORKER_LABEL)
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code == 0, err
    assert remaining == ""
    assert f"service={CONTROL_LABEL} state=absent" in out
    assert f"service={WORKER_LABEL} state=absent" in out
    assert log == [key for key, *_ in plan]


def test_stop_is_idempotent_when_service_already_absent(tmp_path: Path) -> None:
    plan = _stop_already_absent(CONTROL_LABEL) + _stop_already_absent(WORKER_LABEL)
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code == 0, err
    assert remaining == ""
    assert f"service={CONTROL_LABEL} state=absent" in out


def test_stop_fails_when_bootout_swallowed_failure_leaves_service_loaded(
    tmp_path: Path,
) -> None:
    plan = _stop_stubborn(CONTROL_LABEL, bootout_exit=1)
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code != 0
    assert "still registered" in err
    assert log == [key for key, *_ in plan]
    assert remaining == ""


def test_stop_fails_when_bootout_reports_success_but_service_stays_loaded(
    tmp_path: Path,
) -> None:
    plan = _stop_stubborn(CONTROL_LABEL, bootout_exit=0)
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code != 0
    assert "still registered" in err
    assert remaining == ""


def test_stop_fails_when_registration_readback_is_unknown(tmp_path: Path) -> None:
    plan = _stop_unknown_readback(CONTROL_LABEL)
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code != 0
    assert "unknown" in err
    assert remaining == ""


def test_restart_runs_full_stop_then_start_sequence_in_fixed_order(
    tmp_path: Path,
) -> None:
    script, control_plist, worker_plist = _prepare_script(tmp_path)
    plan = (
        _stop_ok(CONTROL_LABEL)
        + _stop_ok(WORKER_LABEL)
        + _start_via_bootstrap(WORKER_LABEL, worker_plist)
        + _start_via_bootstrap(CONTROL_LABEL, control_plist)
    )
    code, out, err, log, remaining, *_ = _run(tmp_path, "restart", plan)
    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]


def test_restart_gateway_cycles_only_fixed_mcp_and_confirms_running(
    tmp_path: Path,
) -> None:
    mcp_plist = tmp_path / "mcp.plist"
    plan = _gateway_enabled_plan() + _stop_ok(MCP_LABEL) + _ensure_running_bootstrap(MCP_LABEL, mcp_plist)
    code, out, err, log, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert code == 0, err
    assert remaining == ""
    assert f"service={MCP_LABEL} state=absent" in out
    assert f"service={MCP_LABEL} state=running existing=0" in out
    assert log == [key for key, *_ in plan]
    assert not any(CONTROL_LABEL in call for call in log)
    assert not any(WORKER_LABEL in call for call in log)
    assert not any(RELAY_LABEL in call for call in log)
    assert not any(BACKUP_LABEL in call for call in log)


def test_restart_gateway_refuses_registered_but_nonrunning_mcp(
    tmp_path: Path,
) -> None:
    mcp_plist = tmp_path / "mcp.plist"
    plan = (
        _gateway_enabled_plan() + _stop_ok(MCP_LABEL)
        + [
            (f"enable system/{MCP_LABEL}", 0, "", ""),
            (f"print system/{MCP_LABEL}", 113, "", "absent"),
            (f"bootstrap system {mcp_plist}", 0, "", ""),
        ]
        + [(f"print system/{MCP_LABEL}", 0, "state = exited", "")] * 31
    )
    code, _out, err, log, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert code == 75
    assert "did not become running" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]


def test_partial_two_service_stop_failure_remains_failed_without_rollback(
    tmp_path: Path,
) -> None:
    plan = _stop_ok(CONTROL_LABEL) + _stop_stubborn(WORKER_LABEL, bootout_exit=0)
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code != 0
    # Control's confirmed-absent effect already happened and is not rolled back.
    assert f"service={CONTROL_LABEL} state=absent" in out
    assert "still registered" in err
    assert log == [key for key, *_ in plan]
    assert remaining == ""



def _observe_running(label: str, *, pid: int | None = None) -> list[Entry]:
    output = "state = running" if pid is None else f"state = running pid = {pid}"
    return [(f"print system/{label}", 0, output, "")]


def _observe_absent(label: str) -> list[Entry]:
    return [(f"print system/{label}", 113, "", "absent")]


def _ensure_running_bootstrap(label: str, plist: Path) -> list[Entry]:
    return [
        (f"enable system/{label}", 0, "", ""),
        (f"print system/{label}", 113, "", "absent"),
        (f"bootstrap system {plist}", 0, "", ""),
        (f"print system/{label}", 0, "state = running", ""),
    ]


def _ensure_running_already(label: str) -> list[Entry]:
    return [
        (f"enable system/{label}", 0, "", ""),
        (f"print system/{label}", 0, "state = running", ""),
    ]


def _agent_relay_disabled(state: str, *, exit_code: int = 0) -> list[Entry]:
    assert state in {"enabled", "disabled"}
    return [
        (
            "print-disabled system",
            exit_code,
            f'        "{AGENT_RELAY_LABEL}" => {state}' if exit_code == 0 else "",
            "" if exit_code == 0 else "disabled-state unavailable",
        )
    ]


def _agent_relay_start_bootstrap(
    agent_plist: Path,
    *,
    enable_exit: int = 0,
    bootstrap_exit: int = 0,
) -> list[Entry]:
    return (
        _agent_relay_disabled("disabled")
        + [(f"enable system/{AGENT_RELAY_LABEL}", enable_exit, "", "enable reply lost" if enable_exit else "")]
        + _agent_relay_disabled("enabled")
        + _observe_absent(AGENT_RELAY_LABEL)
        + [(f"bootstrap system {agent_plist}", bootstrap_exit, "", "bootstrap reply lost" if bootstrap_exit else "")]
        + _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("enabled")
    )


def _agent_relay_start_already() -> list[Entry]:
    return (
        _agent_relay_disabled("enabled")
        + _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("enabled")
    )


def _agent_relay_stop(
    *,
    disable_exit: int = 0,
    bootout_exit: int = 0,
) -> list[Entry]:
    return (
        _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("enabled")
        + [(f"disable system/{AGENT_RELAY_LABEL}", disable_exit, "", "disable reply lost" if disable_exit else "")]
        + _agent_relay_disabled("disabled")
        + _observe_running(AGENT_RELAY_LABEL)
        + [(f"bootout system/{AGENT_RELAY_LABEL}", bootout_exit, "", "bootout reply lost" if bootout_exit else "")]
        + _observe_absent(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("disabled")
    )


def _readside_preflight(*, worker_pid: int | None = None) -> list[Entry]:
    worker = (
        _observe_absent(WORKER_LABEL)
        if worker_pid is None
        else _observe_running(WORKER_LABEL, pid=worker_pid)
    )
    return _observe_running(MCP_LABEL) + worker + _observe_absent(BACKUP_LABEL)


def _readside_postflight(*, worker_pid: int | None = None) -> list[Entry]:
    worker = (
        _observe_absent(WORKER_LABEL)
        if worker_pid is None
        else _observe_running(WORKER_LABEL, pid=worker_pid)
    )
    return _observe_running(MCP_LABEL) + worker + _observe_absent(BACKUP_LABEL)


def test_start_readside_starts_relay_then_control_without_worker_effect(
    tmp_path: Path,
) -> None:
    _script, control_plist, _worker_plist = _prepare_script(tmp_path)
    relay_plist = tmp_path / "relay.plist"
    plan = (
        _readside_preflight()
        + _ensure_running_bootstrap(RELAY_LABEL, relay_plist)
        + _ensure_running_bootstrap(CONTROL_LABEL, control_plist)
        + _readside_postflight()
    )
    code, out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert log.index(f"bootstrap system {relay_plist}") < log.index(
        f"bootstrap system {control_plist}"
    )
    assert not any(
        line.startswith(("enable ", "bootstrap ", "kickstart ", "disable ", "bootout "))
        and WORKER_LABEL in line
        for line in log
    )
    assert f"service={RELAY_LABEL} state=running" in out
    assert f"service={CONTROL_LABEL} state=running" in out


def test_start_readside_is_idempotent_for_already_running_read_services(
    tmp_path: Path,
) -> None:
    plan = (
        _readside_preflight()
        + _ensure_running_already(RELAY_LABEL)
        + _ensure_running_already(CONTROL_LABEL)
        + _readside_postflight()
    )
    code, out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code == 0, err
    assert remaining == ""
    assert not any("kickstart" in line or "bootstrap" in line for line in log)
    assert "existing=1" in out


def test_start_readside_preserves_running_worker_without_mutating_it(
    tmp_path: Path,
) -> None:
    plan = (
        _readside_preflight(worker_pid=4242)
        + _ensure_running_already(RELAY_LABEL)
        + _ensure_running_already(CONTROL_LABEL)
        + _readside_postflight(worker_pid=4242)
    )
    code, out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code == 0, err
    assert remaining == ""
    assert "pid=4242 preserved=pre" in out
    assert "pid=4242 preserved=post" in out
    assert not any(
        line.startswith(("enable ", "bootstrap ", "kickstart ", "disable ", "bootout "))
        and WORKER_LABEL in line
        for line in log
    )


def test_start_readside_refuses_if_running_worker_identity_changes(
    tmp_path: Path,
) -> None:
    plan = (
        _readside_preflight(worker_pid=4242)
        + _ensure_running_already(RELAY_LABEL)
        + _ensure_running_already(CONTROL_LABEL)
        + _observe_running(MCP_LABEL)
        + _observe_running(WORKER_LABEL, pid=4343)
    )
    code, _out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code != 0
    assert "worker state changed" in err
    assert "expected running pid=4242" in err
    assert remaining == ""
    assert not any(
        line.startswith(("enable ", "bootstrap ", "kickstart ", "disable ", "bootout "))
        and WORKER_LABEL in line
        for line in log
    )


def test_start_readside_refuses_before_effect_when_mcp_is_not_running(
    tmp_path: Path,
) -> None:
    plan = _observe_absent(MCP_LABEL)
    code, _out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code != 0
    assert "must be running" in err
    assert remaining == ""
    assert not any(RELAY_LABEL in line or CONTROL_LABEL in line for line in log)


def test_start_readside_partial_failure_is_terminal_and_does_not_touch_worker(
    tmp_path: Path,
) -> None:
    _script, control_plist, _worker_plist = _prepare_script(tmp_path)
    relay_plist = tmp_path / "relay.plist"
    plan = (
        _readside_preflight()
        + _ensure_running_bootstrap(RELAY_LABEL, relay_plist)
        + [
            (f"enable system/{CONTROL_LABEL}", 0, "", ""),
            (f"print system/{CONTROL_LABEL}", 5, "", "unknown"),
        ]
    )
    code, out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code != 0
    assert f"service={RELAY_LABEL} state=running" in out
    assert "unknown" in err
    assert remaining == ""
    assert not any(
        line.startswith(("enable ", "bootstrap ", "kickstart ", "disable ", "bootout "))
        and WORKER_LABEL in line
        for line in log
    )


def test_start_agent_relay_starts_only_fixed_agent_relay(tmp_path: Path) -> None:
    agent_plist = tmp_path / "agent-relay.plist"
    plan = _agent_relay_start_bootstrap(agent_plist)

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "start-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert f"service={AGENT_RELAY_LABEL} state=running" in out
    assert "disabled=enabled" in out
    assert not any(
        label in call
        for label in (CONTROL_LABEL, WORKER_LABEL, RELAY_LABEL, MCP_LABEL, BACKUP_LABEL)
        for call in log
    )


def test_start_agent_relay_is_idempotent_when_already_running(tmp_path: Path) -> None:
    plan = _agent_relay_start_already()

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "start-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert "existing=1" in out
    assert not any(
        call.startswith(("enable ", "bootstrap ", "kickstart ")) for call in log
    )


def test_start_agent_relay_recovers_nonzero_enable_and_bootstrap_from_readback(
    tmp_path: Path,
) -> None:
    agent_plist = tmp_path / "agent-relay.plist"
    plan = _agent_relay_start_bootstrap(
        agent_plist,
        enable_exit=5,
        bootstrap_exit=5,
    )

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "start-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert "effect=enable recovered=1" in out
    assert "effect=bootstrap recovered=1" in out
    assert log.count(f"enable system/{AGENT_RELAY_LABEL}") == 1
    assert log.count(f"bootstrap system {agent_plist}") == 1


def test_start_agent_relay_resumes_partial_enabled_absent_without_replaying_enable(
    tmp_path: Path,
) -> None:
    agent_plist = tmp_path / "agent-relay.plist"
    plan = (
        _agent_relay_disabled("enabled")
        + _observe_absent(AGENT_RELAY_LABEL)
        + [(f"bootstrap system {agent_plist}", 0, "", "")]
        + _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("enabled")
    )

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "start-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert f"service={AGENT_RELAY_LABEL} state=running" in out
    assert not any(call.startswith("enable ") for call in log)
    assert log.count(f"bootstrap system {agent_plist}") == 1


def test_start_agent_relay_read_only_preflight_failures_are_not_effect_unknown(
    tmp_path: Path,
) -> None:
    cases = [
        [("print-disabled system", 5, "", "disabled-state unavailable")],
        _agent_relay_disabled("enabled")
        + [(f"print system/{AGENT_RELAY_LABEL}", 5, "", "registration unavailable")],
        _agent_relay_disabled("enabled")
        + _observe_running(AGENT_RELAY_LABEL)
        + [("print-disabled system", 5, "", "final-disabled unavailable")],
    ]
    for index, plan in enumerate(cases):
        case_root = tmp_path / str(index)
        case_root.mkdir()
        code, _out, err, log, remaining, *_ = _run(case_root, "start-agent-relay", plan)
        assert code != 75
        assert "state=unknown" in err
        assert "state=effect_unknown" not in err
        assert remaining == ""
        assert log == [key for key, *_ in plan]
        assert not any(
            call.startswith(("enable ", "bootstrap ", "kickstart ")) for call in log
        )


def test_start_agent_relay_post_enable_registration_failure_is_effect_unknown(
    tmp_path: Path,
) -> None:
    plan = (
        _agent_relay_disabled("disabled")
        + [(f"enable system/{AGENT_RELAY_LABEL}", 0, "", "")]
        + _agent_relay_disabled("enabled")
        + [(f"print system/{AGENT_RELAY_LABEL}", 5, "", "registration unavailable")]
    )
    code, _out, err, log, remaining, *_ = _run(tmp_path, "start-agent-relay", plan)
    assert code == 75
    assert "state=effect_unknown stage=pre-start-registration" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert log.count(f"enable system/{AGENT_RELAY_LABEL}") == 1
    assert not any(call.startswith(("bootstrap ", "kickstart ")) for call in log)


def test_start_agent_relay_does_not_replay_bootstrap_when_readback_is_unknown(
    tmp_path: Path,
) -> None:
    agent_plist = tmp_path / "agent-relay.plist"
    plan = (
        _agent_relay_disabled("enabled")
        + _observe_absent(AGENT_RELAY_LABEL)
        + [(f"bootstrap system {agent_plist}", 5, "", "bootstrap reply lost")]
        + [(f"print system/{AGENT_RELAY_LABEL}", 5, "", "readback unavailable")]
    )

    code, _out, err, log, remaining, *_ = _run(
        tmp_path, "start-agent-relay", plan
    )

    assert code == 75
    assert "state=effect_unknown stage=bootstrap-reconcile" in err
    assert remaining == ""
    assert log.count(f"bootstrap system {agent_plist}") == 1


def test_start_agent_relay_refuses_unresolved_enable_without_next_effect(
    tmp_path: Path,
) -> None:
    plan = (
        _agent_relay_disabled("disabled")
        + [(f"enable system/{AGENT_RELAY_LABEL}", 5, "", "enable reply lost")]
        + _agent_relay_disabled("disabled")
    )

    code, _out, err, log, remaining, *_ = _run(
        tmp_path, "start-agent-relay", plan
    )

    assert code == 75
    assert "state=effect_unknown stage=enable-reconcile" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert not any(
        call.startswith(("bootstrap ", "kickstart ")) for call in log
    )


def test_stop_agent_relay_stops_only_fixed_registered_relay(tmp_path: Path) -> None:
    plan = _agent_relay_stop()

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "stop-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert f"service={AGENT_RELAY_LABEL} state=absent" in out
    assert "disabled=disabled" in out
    assert not any(
        label in call
        for label in (CONTROL_LABEL, WORKER_LABEL, RELAY_LABEL, MCP_LABEL, BACKUP_LABEL)
        for call in log
    )


def test_stop_agent_relay_recovers_nonzero_disable_and_bootout_from_readback(
    tmp_path: Path,
) -> None:
    plan = _agent_relay_stop(disable_exit=5, bootout_exit=5)

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "stop-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert "effect=disable recovered=1" in out
    assert "effect=bootout recovered=1" in out
    assert log.count(f"disable system/{AGENT_RELAY_LABEL}") == 1
    assert log.count(f"bootout system/{AGENT_RELAY_LABEL}") == 1


def test_stop_agent_relay_resumes_partial_disabled_registered_without_replaying_disable(
    tmp_path: Path,
) -> None:
    plan = (
        _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("disabled")
        + _observe_running(AGENT_RELAY_LABEL)
        + [(f"bootout system/{AGENT_RELAY_LABEL}", 0, "", "")]
        + _observe_absent(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("disabled")
    )

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "stop-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert f"service={AGENT_RELAY_LABEL} state=absent" in out
    assert not any(call.startswith("disable ") for call in log)
    assert log.count(f"bootout system/{AGENT_RELAY_LABEL}") == 1


def test_stop_agent_relay_read_only_preflight_failures_are_not_effect_unknown(
    tmp_path: Path,
) -> None:
    cases = [
        _observe_running(AGENT_RELAY_LABEL)
        + [("print-disabled system", 5, "", "disabled-state unavailable")],
        _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("disabled")
        + [(f"print system/{AGENT_RELAY_LABEL}", 5, "", "registration unavailable")],
    ]
    for index, plan in enumerate(cases):
        case_root = tmp_path / str(index)
        case_root.mkdir()
        code, _out, err, log, remaining, *_ = _run(case_root, "stop-agent-relay", plan)
        assert code != 75
        assert "state=unknown" in err
        assert "state=effect_unknown" not in err
        assert remaining == ""
        assert log == [key for key, *_ in plan]
        assert not any(call.startswith(("disable ", "bootout ")) for call in log)


def test_stop_agent_relay_post_disable_registration_failure_is_effect_unknown(
    tmp_path: Path,
) -> None:
    plan = (
        _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("enabled")
        + [(f"disable system/{AGENT_RELAY_LABEL}", 0, "", "")]
        + _agent_relay_disabled("disabled")
        + [(f"print system/{AGENT_RELAY_LABEL}", 5, "", "registration unavailable")]
    )
    code, _out, err, log, remaining, *_ = _run(tmp_path, "stop-agent-relay", plan)
    assert code == 75
    assert "state=effect_unknown stage=pre-bootout-registration" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert log.count(f"disable system/{AGENT_RELAY_LABEL}") == 1
    assert not any(call.startswith("bootout ") for call in log)


def test_stop_agent_relay_does_not_replay_bootout_when_readback_is_unknown(
    tmp_path: Path,
) -> None:
    plan = (
        _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("disabled")
        + _observe_running(AGENT_RELAY_LABEL)
        + [(f"bootout system/{AGENT_RELAY_LABEL}", 5, "", "bootout reply lost")]
        + [(f"print system/{AGENT_RELAY_LABEL}", 5, "", "readback unavailable")]
    )

    code, _out, err, log, remaining, *_ = _run(
        tmp_path, "stop-agent-relay", plan
    )

    assert code == 75
    assert "state=effect_unknown stage=bootout-reconcile" in err
    assert remaining == ""
    assert log.count(f"bootout system/{AGENT_RELAY_LABEL}") == 1


def test_stop_agent_relay_refuses_unresolved_disable_without_bootout(
    tmp_path: Path,
) -> None:
    plan = (
        _observe_running(AGENT_RELAY_LABEL)
        + _agent_relay_disabled("enabled")
        + [(f"disable system/{AGENT_RELAY_LABEL}", 5, "", "disable reply lost")]
        + _agent_relay_disabled("enabled")
    )

    code, _out, err, log, remaining, *_ = _run(
        tmp_path, "stop-agent-relay", plan
    )

    assert code == 75
    assert "state=effect_unknown stage=disable-reconcile" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert not any(call.startswith("bootout ") for call in log)


def test_status_agent_relay_is_read_only_and_reports_exact_state(
    tmp_path: Path,
) -> None:
    plan = _agent_relay_disabled("disabled") + _observe_absent(AGENT_RELAY_LABEL)

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "status-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert f"service={AGENT_RELAY_LABEL} state=absent disabled=disabled" in out
    assert log == [key for key, *_ in plan]
    assert not any(
        call.startswith(("enable ", "disable ", "bootstrap ", "kickstart ", "bootout "))
        for call in log
    )


def test_start_agent_relay_refuses_missing_plist_before_launchctl(
    tmp_path: Path,
) -> None:
    code, _out, err, log, remaining, *_ = _run(
        tmp_path,
        "start-agent-relay",
        [],
        remove_agent_relay_plist=True,
    )

    assert code == 65
    assert "missing or unsafe launchd plist" in err
    assert remaining == ""
    assert log == []


def test_stop_agent_relay_refuses_absent_service_before_disable(tmp_path: Path) -> None:
    plan = [
        (f"print system/{AGENT_RELAY_LABEL}", 113, "", "absent"),
    ]

    code, _out, err, log, remaining, *_ = _run(
        tmp_path, "stop-agent-relay", plan
    )

    assert code != 0
    assert "must be registered before stop" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert not any(
        call.startswith(("disable ", "bootout ")) for call in log
    )


def test_stop_agent_relay_can_quiesce_registered_service_if_plist_is_lost(
    tmp_path: Path,
) -> None:
    plan = _agent_relay_stop()

    code, out, err, log, remaining, *_ = _run(
        tmp_path,
        "stop-agent-relay",
        plan,
        remove_agent_relay_plist=True,
    )

    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert f"service={AGENT_RELAY_LABEL} state=absent" in out


def test_stop_readside_stops_control_then_relay_and_preserves_mcp_worker_backup(
    tmp_path: Path,
) -> None:
    plan = (
        _readside_preflight()
        + _stop_ok(CONTROL_LABEL)
        + _stop_ok(RELAY_LABEL)
        + _readside_postflight()
    )
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop-readside", plan)
    assert code == 0, err
    assert remaining == ""
    assert log.index(f"disable system/{CONTROL_LABEL}") < log.index(
        f"disable system/{RELAY_LABEL}"
    )
    assert not any(
        line.startswith(("enable ", "bootstrap ", "kickstart ", "disable ", "bootout "))
        and WORKER_LABEL in line
        for line in log
    )
    assert f"service={CONTROL_LABEL} state=absent" in out
    assert f"service={RELAY_LABEL} state=absent" in out


@pytest.mark.parametrize("kickstart", [False, True])
def test_readside_waits_for_async_start_without_repeating_effect(tmp_path, kickstart):
    _script, control_plist, _worker_plist = _prepare_script(tmp_path)
    relay_plist = tmp_path / "relay.plist"
    initial = (0, "state = waiting") if kickstart else (113, "")
    effect = (f"kickstart system/{RELAY_LABEL}" if kickstart
              else f"bootstrap system {relay_plist}")
    plan = _readside_preflight() + [
        (f"enable system/{RELAY_LABEL}", 0, "", ""),
        (f"print system/{RELAY_LABEL}", initial[0], initial[1], ""),
        (effect, 0, "", ""),
        (f"print system/{RELAY_LABEL}", 113, "", "absent"),
        (f"print system/{RELAY_LABEL}", 0, "state = waiting", ""),
        (f"print system/{RELAY_LABEL}", 0, "state = running", ""),
    ] + _ensure_running_bootstrap(CONTROL_LABEL, control_plist) + _readside_postflight()
    code, out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert log.count(effect) == 1
    assert f"service={RELAY_LABEL} state=running existing=0" in out


@pytest.mark.parametrize("status,output", [(113, ""), (0, "state = waiting")])
def test_readside_readiness_wait_is_bounded_and_preserves_partial_state(tmp_path, status, output):
    _script, control_plist, _worker_plist = _prepare_script(tmp_path)
    effect = f"bootstrap system {control_plist}"
    plan = _readside_preflight() + _ensure_running_already(RELAY_LABEL) + [
        (f"enable system/{CONTROL_LABEL}", 0, "", ""),
        (f"print system/{CONTROL_LABEL}", 113, "", "absent"),
        (effect, 0, "", ""),
    ] + [(f"print system/{CONTROL_LABEL}", status, output, "")] * 31
    code, _out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code != 0
    assert "did not become running" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert log.count(effect) == 1
    assert not any(line.startswith(("bootout ", "disable ", "kickstart ")) for line in log)


def test_readside_unknown_readiness_fails_immediately_without_restart(tmp_path):
    _script, control_plist, _worker_plist = _prepare_script(tmp_path)
    plan = _readside_preflight() + _ensure_running_already(RELAY_LABEL) + [
        (f"enable system/{CONTROL_LABEL}", 0, "", ""),
        (f"print system/{CONTROL_LABEL}", 113, "", "absent"),
        (f"bootstrap system {control_plist}", 0, "", ""),
        (f"print system/{CONTROL_LABEL}", 5, "", "unknown"),
    ]
    code, _out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code != 0
    assert "state unknown after read-side start" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]


def test_readside_failed_bootstrap_does_not_poll_or_retry(tmp_path):
    _script, control_plist, _worker_plist = _prepare_script(tmp_path)
    plan = _readside_preflight() + _ensure_running_already(RELAY_LABEL) + [
        (f"enable system/{CONTROL_LABEL}", 0, "", ""),
        (f"print system/{CONTROL_LABEL}", 113, "", "absent"),
        (f"bootstrap system {control_plist}", 5, "", "bootstrap failed"),
    ]
    code, _out, err, log, remaining, *_ = _run(tmp_path, "start-readside", plan)
    assert code == 5
    assert remaining == ""
    assert log == [key for key, *_ in plan]


@pytest.mark.parametrize("bootout_exit", [0, 5])
def test_stop_observes_async_disappearance_without_repeating_effect(
    tmp_path: Path, bootout_exit: int,
) -> None:
    plan = []
    for label in (CONTROL_LABEL, WORKER_LABEL):
        plan += [
            (f"disable system/{label}", 0, "", ""),
            (f"bootout system/{label}", bootout_exit, "", ""),
            (f"print system/{label}", 0, "state = running", ""),
            (f"print system/{label}", 0, "state = waiting", ""),
            (f"print system/{label}", 113, "", "absent"),
        ]
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    for label in (CONTROL_LABEL, WORKER_LABEL):
        assert log.count(f"disable system/{label}") == 1
        assert log.count(f"bootout system/{label}") == 1
        assert f"service={label} state=absent" in out


def test_stop_disappearance_wait_is_bounded_without_second_mutation(tmp_path: Path) -> None:
    plan = _stop_stubborn(CONTROL_LABEL, bootout_exit=0)
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code != 0
    assert "still registered after stop wait" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert log.count(f"print system/{CONTROL_LABEL}") == 31
    assert log.count(f"disable system/{CONTROL_LABEL}") == 1
    assert log.count(f"bootout system/{CONTROL_LABEL}") == 1
    assert all(WORKER_LABEL not in call for call in log)


def test_stop_refuses_unknown_during_disappearance_wait(tmp_path: Path) -> None:
    plan = [
        (f"disable system/{CONTROL_LABEL}", 0, "", ""),
        (f"bootout system/{CONTROL_LABEL}", 0, "", ""),
        (f"print system/{CONTROL_LABEL}", 0, "state = running", ""),
        (f"print system/{CONTROL_LABEL}", 5, "", "unknown"),
    ]
    code, out, err, log, remaining, *_ = _run(tmp_path, "stop", plan)
    assert code != 0
    assert "state unknown" in err
    assert remaining == ""
    assert log == [key for key, *_ in plan]


# Gateway qualification uses only disposable configuration and command shims.
GATEWAY_SHA = "a" * 40
GATEWAY_RELEASE_ROOT = "/Library/Application Support/MastermindExecutive/releases"
GATEWAY_CONFIG_PATH = "/Library/Application Support/MastermindExecutive/config/executive-mcp.json"


def _qualified_gateway_run(tmp_path, plan, *, changes=None, config_changes=None,
                           extra_args=("--expected-sha", GATEWAY_SHA),
                           missing_config=False, symlink_config=False, native_plutil=False,
                           preflight_exit=0, preflight_exits=None, helper_kind="regular",
                           controller_from_release=True,
                           source_with_spoofed_argv0=False,
                           source_with_shadowed_cd=False):
    config = {"schema": "mastermind.executive_mcp_install.v1",
              "release_sha": GATEWAY_SHA, "service_uid": 458}
    config.update(config_changes or {})
    release_root = tmp_path / "releases"
    release = str(release_root / GATEWAY_SHA)
    config_path = tmp_path / "executive-mcp.json"
    document = {
        "Label": MCP_LABEL,
        "ProgramArguments": [
            "/Library/Application Support/MastermindExecutive/network-runtimes/"
            + "b" * 64 + "/bin/python", "-I", "-B",
            release + "/ops/executive_os/executive_mcp_entry.py",
            "--config", str(config_path)],
        "WorkingDirectory": release,
        "UserName": "_mastermind_executive_mcp",
        "GroupName": "_mastermind_executive_mcp",
    }
    document.update(changes or {})
    def prepare(script):
        text = script.read_text().replace(GATEWAY_CONFIG_PATH, str(config_path))
        text = text.replace(
            f'MCP_RELEASE_ROOT="{GATEWAY_RELEASE_ROOT}"',
            f'MCP_RELEASE_ROOT="{release_root}"',
        )
        expected_dir = release_root / GATEWAY_SHA / "ops" / "executive_os"
        controller = expected_dir / "service-control.sh"
        if controller_from_release:
            source = (
                'SCRIPT_SOURCE="${BASH_SOURCE[0]}"\n'
                'SCRIPT_DIR="$(builtin cd -P "$(/usr/bin/dirname "$SCRIPT_SOURCE")" && /bin/pwd)"\n'
                'SCRIPT_PATH="$SCRIPT_DIR/$(/usr/bin/basename "$SCRIPT_SOURCE")"'
            )
            replacement = (
                f'SCRIPT_SOURCE="{controller}"\n'
                f'SCRIPT_DIR="{expected_dir}"\n'
                f'SCRIPT_PATH="{controller}"'
            )
            text = text.replace(source, replacement)
            assert source not in text
        script.write_text(text)
        helper = expected_dir / "gateway_refresh_preflight.py"
        helper.parent.mkdir(parents=True, exist_ok=True)
        controller.write_text("# disposable installed service controller\n", encoding="utf-8")
        if helper_kind == "regular":
            helper.write_text("# disposable gateway preflight fixture\n", encoding="utf-8")
        elif helper_kind == "symlink":
            target = release_root / "decoy-gateway-preflight.py"
            target.write_text("# outside expected helper coordinate\n", encoding="utf-8")
            helper.symlink_to(target)
        elif helper_kind != "missing":
            raise AssertionError(f"unsupported helper_kind: {helper_kind}")
        preflight = tmp_path / "native-shims" / "gateway-preflight-python"
        if preflight_exits is None:
            preflight.write_text(
                "#!/bin/bash\n"
                f"exit {int(preflight_exit)}\n",
                encoding="utf-8",
            )
        else:
            exit_plan = tmp_path / "gateway-preflight-exits"
            exit_plan.write_text(
                "\n".join(str(int(code)) for code in preflight_exits) + "\n",
                encoding="utf-8",
            )
            preflight.write_text(
                "#!/bin/bash\n"
                f"plan={str(exit_plan)!r}\n"
                'code="$(head -n 1 "$plan")"\n'
                '[ -n "$code" ] || exit 98\n'
                'tail -n +2 "$plan" > "$plan.next"\n'
                'mv "$plan.next" "$plan"\n'
                'exit "$code"\n',
                encoding="utf-8",
            )
        preflight.chmod(0o755)
        (tmp_path / "mcp.plist").write_bytes(plistlib.dumps(document))
        if not missing_config:
            target = tmp_path / "actual-config.json" if symlink_config else config_path
            target.write_text(json.dumps(config))
            if symlink_config:
                config_path.symlink_to(target)
        if native_plutil:
            return
        shim = tmp_path / "native-shims" / "plutil"
        shim.write_text("#!" + sys.executable + "\n" + r'''import sys,json,plistlib
from pathlib import Path
args=sys.argv[1:]
try:
    raw=Path(args[-1]).read_bytes()
    try: obj=json.loads(raw)
    except (ValueError, UnicodeError): obj=plistlib.loads(raw)
    if args[0] == '-lint': sys.exit(0)
    if args[0] == '-type':
        assert args[1] in obj
        print(type(obj[args[1]]).__name__)
        sys.exit(0)
    assert args[0] == '-extract' and args[2] == 'raw'
    value=obj
    for key in args[1].split('.'):
        value=value[int(key)] if isinstance(value,list) else value[key]
    expected=args[args.index('-expect')+1]
    kinds={'string':str,'integer':int,'array':list}
    assert type(value) is kinds[expected]
    print(len(value) if isinstance(value,list) else value)
except (OSError,ValueError,KeyError,IndexError,AssertionError,plistlib.InvalidFileException):
    sys.exit(1)
''')
        shim.chmod(0o755)
    spoof_argv0 = None
    expected_controller_dir = release_root / GATEWAY_SHA / "ops" / "executive_os"
    if source_with_spoofed_argv0 or source_with_shadowed_cd:
        spoof_argv0 = str(expected_controller_dir / "service-control.sh")
    return _run(
        tmp_path,
        "restart-gateway",
        plan,
        extra_args=extra_args,
        prepare=prepare,
        spoof_argv0=spoof_argv0,
        shadow_cd=source_with_shadowed_cd,
        cwd=expected_controller_dir if source_with_shadowed_cd else None,
    )


def _gateway_override_table(*rows):
    body = "\n".join(f'    "{label}" => {value}' for label, value in rows)
    return "disabled services = {\n" + body + ("\n" if body else "") + "}"


def _gateway_enabled_plan(value="false"):
    rows = () if value is None else ((MCP_LABEL, value),)
    return [("print-disabled system", 0, _gateway_override_table(*rows), ""),
            (f"print system/{MCP_LABEL}", 0, "state = running", "")]


@pytest.mark.parametrize("enabled_value", [None, "false", "enabled"])
def test_gateway_exact_release_qualified_before_any_cycle(tmp_path, enabled_value):
    plan = (_gateway_enabled_plan(enabled_value) + _stop_ok(MCP_LABEL)
            + _ensure_running_bootstrap(MCP_LABEL, tmp_path / "mcp.plist"))
    code, out, err, calls, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert code == 0, err
    assert remaining == ""
    assert calls == [entry[0] for entry in plan]
    assert f"release={GATEWAY_SHA}" in out
    assert not any(label in call for label in
                   (CONTROL_LABEL, WORKER_LABEL, RELAY_LABEL, AGENT_RELAY_LABEL, BACKUP_LABEL)
                   for call in calls)


@pytest.mark.parametrize("args", [(), ("--expected-sha", "a"*39),
    ("--expected-sha", "A"*40), ("--release", GATEWAY_SHA),
    ("--expected-sha", GATEWAY_SHA, "--enable-disabled")])
def test_gateway_requires_exact_closed_release_arguments(tmp_path, args):
    code, _, _, calls, _, *_ = _qualified_gateway_run(tmp_path, [], extra_args=args)
    assert code == 64
    assert calls == []


@pytest.mark.parametrize("changes,config_changes", [
    ({}, {"release_sha": "c"*40}),
    ({}, {"service_uid": 450}),
    ({}, {"schema": "wrong"}),
    ({"Label": CONTROL_LABEL}, {}),
    ({"UserName": "root"}, {}),
    ({"GroupName": "wheel"}, {}),
    ({"WorkingDirectory": GATEWAY_RELEASE_ROOT + "/" + "c"*40}, {}),
    ({"ProgramArguments": ["/bin/bash", "-c", "false"]}, {}),
    ({"Program": "/bin/bash"}, {}),
])
def test_gateway_generation_mismatch_is_pre_effect_refusal(tmp_path, changes, config_changes):
    code, _, err, calls, _, *_ = _qualified_gateway_run(
        tmp_path, [], changes=changes, config_changes=config_changes)
    assert code == 65
    assert "gateway release qualification failed" in err
    assert calls == []


def test_gateway_refuses_controller_outside_expected_release_before_lifecycle(tmp_path):
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(
        tmp_path, [], controller_from_release=False
    )
    assert code == 65
    assert "gateway deep preflight failed" in err
    assert calls == []
    assert remaining == ""


def test_gateway_refuses_sourced_checkout_even_with_installed_argv0_spoof(tmp_path):
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(
        tmp_path,
        [],
        controller_from_release=False,
        source_with_spoofed_argv0=True,
    )
    assert code == 65
    assert "gateway deep preflight failed" in err
    assert calls == []
    assert remaining == ""

def test_gateway_refuses_sourced_checkout_with_shadowed_cd_and_installed_argv0(
    tmp_path,
):
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(
        tmp_path,
        [],
        controller_from_release=False,
        source_with_shadowed_cd=True,
    )
    assert code == 65
    assert "gateway deep preflight failed" in err
    assert calls == []
    assert remaining == ""


@pytest.mark.parametrize("helper_kind", ["missing", "symlink"])
def test_gateway_refuses_untrusted_release_preflight_helper_before_lifecycle(
    tmp_path, helper_kind
):
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(
        tmp_path, [], helper_kind=helper_kind
    )
    assert code == 65
    assert "gateway deep preflight failed" in err
    assert calls == []
    assert remaining == ""


def test_gateway_deep_preflight_refusal_never_stops_service(tmp_path):
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(
        tmp_path, [], preflight_exit=65
    )
    assert code == 65
    assert "gateway deep preflight failed" in err
    assert calls == []
    assert remaining == ""


@pytest.mark.parametrize("kind", ["missing", "symlink"])
def test_gateway_missing_or_indirect_config_never_stops_service(tmp_path, kind):
    code, _, _, calls, _, *_ = _qualified_gateway_run(
        tmp_path, [], missing_config=kind=="missing", symlink_config=kind=="symlink")
    assert code == 65
    assert calls == []


@pytest.mark.parametrize("code,output", [
    (0, _gateway_override_table((MCP_LABEL, "true"))),
    (0, _gateway_override_table((MCP_LABEL, "disabled"))),
    (0, _gateway_override_table((MCP_LABEL, "false"), (MCP_LABEL, "enabled"))),
    (0, "disabled services = {}"),
    (0, 'disabled services = {\n    "bad label" => enabled\n}'),
    (5, ""),
])
def test_gateway_never_enables_previously_disabled_or_unknown_service(tmp_path, code, output):
    plan = [("print-disabled system", code, output, "")]
    result, _, err, calls, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert result == 65
    assert "gateway must already be enabled" in err
    assert calls == ["print-disabled system"]
    assert remaining == ""


@pytest.mark.parametrize("output", [
    f'    "{MCP_LABEL}" => false\ndisabled services = {{\n}}',
    'disabled services = {\n    "other.service" => false\n'
    '    "other.service" => enabled\n}',
    'disabled services = {\n}\n    "other.service" => false',
])
def test_gateway_malformed_override_structure_is_pre_effect_refusal(tmp_path, output):
    plan = [("print-disabled system", 0, output, "")]
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert code == 65
    assert "gateway must already be enabled" in err
    assert calls == ["print-disabled system"]
    assert remaining == ""


def test_gateway_registered_but_not_running_is_pre_effect_refusal(tmp_path):
    plan = _gateway_enabled_plan()
    plan[-1] = (f"print system/{MCP_LABEL}", 0, "state = exited", "")
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert code == 65
    assert "service must be running" in err
    assert calls == [entry[0] for entry in plan]
    assert remaining == ""


@pytest.mark.parametrize("index,value", [
    (0, "/usr/bin/python3"), (1, "-c"), (2, "-S"),
    (3, GATEWAY_RELEASE_ROOT + "/" + "c"*40 + "/ops/executive_os/executive_mcp_entry.py"),
    (4, "--other-config"), (5, "/tmp/other-config.json")])
def test_gateway_rejects_each_argv_coordinate_before_lifecycle(tmp_path, index, value):
    release = GATEWAY_RELEASE_ROOT + "/" + GATEWAY_SHA
    args = ["/Library/Application Support/MastermindExecutive/network-runtimes/"
            + "b"*64 + "/bin/python", "-I", "-B",
            release + "/ops/executive_os/executive_mcp_entry.py", "--config",
            str(tmp_path / "executive-mcp.json")]
    args[index] = value
    code, _, _, calls, _, *_ = _qualified_gateway_run(
        tmp_path, [], changes={"ProgramArguments": args})
    assert code == 65
    assert calls == []


def test_gateway_deep_postflight_failure_is_effect_unknown_without_retry(tmp_path):
    plan = (_gateway_enabled_plan() + _stop_ok(MCP_LABEL)
            + _ensure_running_bootstrap(MCP_LABEL, tmp_path / "mcp.plist"))
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(
        tmp_path, plan, preflight_exits=(0, 65)
    )
    assert code == 75
    assert "stage=postflight" in err and "do not replay" in err
    assert remaining == ""
    assert calls == [entry[0] for entry in plan]
    assert calls.count(f"disable system/{MCP_LABEL}") == 1
    assert calls.count(f"bootstrap system {tmp_path / 'mcp.plist'}") == 1


def test_gateway_post_start_config_disappearance_is_effect_unknown(tmp_path, monkeypatch):
    # Remove only the disposable config after the fake bootstrap succeeds.
    marker = 'exit "$plan_exit"'
    injected = ('if [[ "$key" == bootstrap* ]]; then\n'
                '  /bin/rm -f "$(dirname "$FAKE_LAUNCHCTL_PLAN")/executive-mcp.json"\n'
                'fi\n')
    monkeypatch.setattr(sys.modules[__name__], "LAUNCHCTL_SHIM",
                        LAUNCHCTL_SHIM.replace(marker, injected + marker))
    plan = (_gateway_enabled_plan() + _stop_ok(MCP_LABEL)
            + _ensure_running_bootstrap(MCP_LABEL, tmp_path / "mcp.plist"))
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert code == 75
    assert "stage=postflight" in err and "do not replay" in err
    assert remaining == ""
    assert calls == [entry[0] for entry in plan]
    assert calls.count(f"disable system/{MCP_LABEL}") == 1
    assert calls.count(f"bootstrap system {tmp_path / 'mcp.plist'}") == 1


def test_gateway_uncertain_stop_has_no_start_or_retry(tmp_path):
    plan = _gateway_enabled_plan() + _stop_stubborn(MCP_LABEL, bootout_exit=5)
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert code == 75
    assert "stage=stop" in err and "do not replay" in err
    assert remaining == ""
    assert calls.count(f"disable system/{MCP_LABEL}") == 1
    assert calls.count(f"bootout system/{MCP_LABEL}") == 1
    assert not any(call.startswith(("enable ", "bootstrap ", "kickstart ")) for call in calls)


@pytest.mark.parametrize("stage", ["disable", "enable", "bootstrap"])
def test_gateway_failed_modifying_verb_stops_without_another_effect(tmp_path, stage):
    plan = _gateway_enabled_plan()
    if stage == "disable":
        plan += [(f"disable system/{MCP_LABEL}", 5, "", "lost disable reply")]
    else:
        plan += _stop_ok(MCP_LABEL)
        if stage == "enable":
            plan += [(f"enable system/{MCP_LABEL}", 5, "", "lost enable reply")]
        else:
            plan += [(f"enable system/{MCP_LABEL}", 0, "", ""),
                     (f"print system/{MCP_LABEL}", 113, "", "absent"),
                     (f"bootstrap system {tmp_path / 'mcp.plist'}", 5, "", "lost bootstrap reply")]
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(tmp_path, plan)
    assert code == 75
    assert "do not replay" in err
    assert calls == [entry[0] for entry in plan]
    assert remaining == ""


@pytest.mark.skipif(sys.platform != "darwin", reason="requires native macOS plutil parser")
def test_gateway_qualification_uses_real_native_plutil_with_disposable_files(tmp_path):
    plan = (_gateway_enabled_plan("enabled") + _stop_ok(MCP_LABEL)
            + _ensure_running_bootstrap(MCP_LABEL, tmp_path / "mcp.plist"))
    code, _, err, calls, remaining, *_ = _qualified_gateway_run(
        tmp_path, plan, native_plutil=True)
    assert code == 0, err
    assert remaining == ""
    assert calls == [entry[0] for entry in plan]
