"""Postcondition proof tests for the bounded start/stop service controller.

These tests run the real `service-control.sh` body (a per-test disposable copy
with the fixed LaunchDaemons and native-command paths pointed at tmp_path
executables). No real root, sudo, launchctl, service, or network effect occurs.
"""
from __future__ import annotations

import subprocess
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
if [ "${1:-}" = "-u" ]; then
  printf '%s\n' "${FAKE_UID:-0}"
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
[ -n "$plan_out" ] && printf '%s\n' "$plan_out"
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
    assert str(control_plist) in text and str(worker_plist) in text
    assert str(agent_relay_plist) in text
    copy_path = tmp_path / "service-control.sh"
    copy_path.write_text(text, encoding="utf-8")
    copy_path.chmod(0o755)
    control_plist.write_text("control-plist", encoding="utf-8")
    worker_plist.write_text("worker-plist", encoding="utf-8")
    relay_plist.write_text("relay-plist", encoding="utf-8")
    agent_relay_plist.write_text("agent-relay-plist", encoding="utf-8")
    return copy_path, control_plist, worker_plist


def _write_plan(path: Path, entries: list[Entry]) -> None:
    lines = ["\t".join((key, str(exit_code), out, err)) for key, exit_code, out, err in entries]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _run(
    tmp_path: Path,
    action: str,
    plan: list[Entry],
    *,
    fake_uid: str = "0",
    fake_os: str = "Darwin",
    remove_agent_relay_plist: bool = False,
) -> tuple[int, str, str, list[str], str, Path, Path]:
    script, control_plist, worker_plist = _prepare_script(tmp_path)
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
    }
    completed = subprocess.run(
        ["/bin/bash", str(script), action],
        env=env,
        capture_output=True,
        text=True,
        check=False,
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
    plan = _ensure_running_bootstrap(AGENT_RELAY_LABEL, agent_plist)

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "start-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert f"service={AGENT_RELAY_LABEL} state=running" in out
    assert not any(
        label in call
        for label in (CONTROL_LABEL, WORKER_LABEL, RELAY_LABEL, MCP_LABEL, BACKUP_LABEL)
        for call in log
    )


def test_start_agent_relay_is_idempotent_when_already_running(tmp_path: Path) -> None:
    plan = _ensure_running_already(AGENT_RELAY_LABEL)

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "start-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert "existing=1" in out
    assert not any("bootstrap" in call or "kickstart" in call for call in log)


def test_stop_agent_relay_stops_only_fixed_registered_relay(tmp_path: Path) -> None:
    plan = [
        (f"print system/{AGENT_RELAY_LABEL}", 0, "state = running", ""),
    ] + _stop_ok(AGENT_RELAY_LABEL)

    code, out, err, log, remaining, *_ = _run(
        tmp_path, "stop-agent-relay", plan
    )

    assert code == 0, err
    assert remaining == ""
    assert log == [key for key, *_ in plan]
    assert f"service={AGENT_RELAY_LABEL} state=absent" in out
    assert not any(
        label in call
        for label in (CONTROL_LABEL, WORKER_LABEL, RELAY_LABEL, MCP_LABEL, BACKUP_LABEL)
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
    plan = [
        (f"print system/{AGENT_RELAY_LABEL}", 0, "state = running", ""),
    ] + _stop_ok(AGENT_RELAY_LABEL)

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
