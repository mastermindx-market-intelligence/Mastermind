from __future__ import annotations

import os
import socket
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "executive_os"
SERVICE_CONTROL = OPS / "service-control.sh"
STATUS = OPS / "status.sh"

RELAY_LABEL = "com.mastermind.executive.agent-relay"
RELAY_PLIST = f"/Library/LaunchDaemons/{RELAY_LABEL}.plist"
RELAY_SOCKET = "/var/run/mastermind-executive/agent-relay/agent-relay.sock"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o700)


def _fake_tools(tmp_path: Path, *, services_loaded: bool) -> tuple[dict[str, str], Path]:
    tools = tmp_path / "tools"
    tools.mkdir()
    call_log = tmp_path / "calls.log"

    _write_executable(
        tools / "id",
        "#!/bin/bash\n"
        "if [ \"${1:-}\" = \"-u\" ]; then /bin/echo 0; else /bin/echo \"uid=450($1)\"; fi\n",
    )
    _write_executable(tools / "uname", "#!/bin/bash\n/bin/echo Darwin\n")
    _write_executable(tools / "plutil", "#!/bin/bash\nexit 0\n")
    _write_executable(
        tools / "stat",
        "#!/bin/bash\n/bin/echo \"metadata=${@: -1}\"\n",
    )
    _write_executable(
        tools / "lsof",
        "#!/bin/bash\n"
        "/bin/echo \"lsof $*\" >> \"$CALL_LOG\"\n"
        "exit 1\n",
    )
    print_result = (
        "/bin/echo 'state = running'\n/bin/echo 'pid = 4242'\nexit 0"
        if services_loaded
        else "exit 1"
    )
    _write_executable(
        tools / "launchctl",
        "#!/bin/bash\n"
        "/bin/echo \"$*\" >> \"$CALL_LOG\"\n"
        "if [ \"${1:-}\" = \"print\" ]; then\n"
        f"  {print_result}\n"
        "fi\n"
        "exit 0\n",
    )
    replacements = {
        "/usr/bin/id": str(tools / "id"),
        "/usr/bin/uname": str(tools / "uname"),
        "/usr/bin/plutil": str(tools / "plutil"),
        "/usr/bin/stat": str(tools / "stat"),
        "/usr/sbin/lsof": str(tools / "lsof"),
        "/bin/launchctl": str(tools / "launchctl"),
    }
    return replacements, call_log


def _render_script(
    source_path: Path,
    destination: Path,
    replacements: dict[str, str],
) -> None:
    source = source_path.read_text(encoding="utf-8")
    for original, replacement in replacements.items():
        source = source.replace(original, replacement)
    destination.write_text(source, encoding="utf-8")
    destination.chmod(0o700)


def _run_service_control(tmp_path: Path, command: str) -> list[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    replacements, call_log = _fake_tools(tmp_path, services_loaded=False)
    launch_daemons = tmp_path / "LaunchDaemons"
    launch_daemons.mkdir()
    for label in (
        "com.mastermind.executive.control",
        "com.mastermind.executive.worker.codex",
        RELAY_LABEL,
    ):
        (launch_daemons / f"{label}.plist").write_text("<plist/>\n", encoding="utf-8")
        replacements[f"/Library/LaunchDaemons/{label}.plist"] = str(
            launch_daemons / f"{label}.plist"
        )
    replacements["/Library/LaunchDaemons/$CONTROL_LABEL.plist"] = str(
        launch_daemons / "com.mastermind.executive.control.plist"
    )
    replacements["/Library/LaunchDaemons/$WORKER_LABEL.plist"] = str(
        launch_daemons / "com.mastermind.executive.worker.codex.plist"
    )
    script = tmp_path / "service-control.sh"
    _render_script(SERVICE_CONTROL, script, replacements)
    completed = subprocess.run(
        ["/bin/bash", str(script), command],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "CALL_LOG": str(call_log)},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return call_log.read_text(encoding="utf-8").splitlines()


def test_service_control_uses_fixed_agent_relay_identity_and_start_stop_order(
    tmp_path: Path,
) -> None:
    source = SERVICE_CONTROL.read_text(encoding="utf-8")
    assert RELAY_LABEL in source
    assert RELAY_PLIST in source
    assert "--label" not in source and "eval " not in source

    start_calls = _run_service_control(tmp_path / "start", "start")
    assert [line for line in start_calls if line.startswith("bootstrap ")] == [
        f"bootstrap system {tmp_path / 'start/LaunchDaemons' / (RELAY_LABEL + '.plist')}",
        f"bootstrap system {tmp_path / 'start/LaunchDaemons/com.mastermind.executive.worker.codex.plist'}",
        f"bootstrap system {tmp_path / 'start/LaunchDaemons/com.mastermind.executive.control.plist'}",
    ]

    stop_calls = _run_service_control(tmp_path / "stop", "stop")
    assert [line for line in stop_calls if line.startswith("disable ")] == [
        "disable system/com.mastermind.executive.control",
        "disable system/com.mastermind.executive.worker.codex",
        f"disable system/{RELAY_LABEL}",
    ]


def test_service_control_restart_preserves_bounded_stop_then_start_order(
    tmp_path: Path,
) -> None:
    calls = _run_service_control(tmp_path, "restart")
    assert [line for line in calls if line.startswith("disable ")] == [
        "disable system/com.mastermind.executive.control",
        "disable system/com.mastermind.executive.worker.codex",
        f"disable system/{RELAY_LABEL}",
    ]
    assert [line for line in calls if line.startswith("bootstrap ")] == [
        f"bootstrap system {tmp_path / 'LaunchDaemons' / (RELAY_LABEL + '.plist')}",
        f"bootstrap system {tmp_path / 'LaunchDaemons/com.mastermind.executive.worker.codex.plist'}",
        f"bootstrap system {tmp_path / 'LaunchDaemons/com.mastermind.executive.control.plist'}",
    ]


def test_status_reports_agent_relay_plist_service_socket_and_no_control_tcp_listener(
    tmp_path: Path,
) -> None:
    replacements, call_log = _fake_tools(tmp_path, services_loaded=True)
    launch_daemons = tmp_path / "LaunchDaemons"
    launch_daemons.mkdir()
    for label in (
        "com.mastermind.executive.control",
        "com.mastermind.executive.worker.codex",
        RELAY_LABEL,
    ):
        plist = launch_daemons / f"{label}.plist"
        plist.write_text("<plist/>\n", encoding="utf-8")
        replacements[f"/Library/LaunchDaemons/{label}.plist"] = str(plist)
    replacements["/Library/LaunchDaemons/$CONTROL_LABEL.plist"] = str(
        launch_daemons / "com.mastermind.executive.control.plist"
    )
    replacements["/Library/LaunchDaemons/$WORKER_LABEL.plist"] = str(
        launch_daemons / "com.mastermind.executive.worker.codex.plist"
    )

    with tempfile.TemporaryDirectory(prefix="agent-relay-") as short_root:
        socket_root = Path(short_root)
        sockets: list[socket.socket] = []
        try:
            for name, fixed_path in (
                ("control.sock", "/var/run/mastermind-executive/control.sock"),
                ("worker.sock", "/var/run/mastermind-executive/worker.sock"),
                ("agent-relay.sock", RELAY_SOCKET),
            ):
                path = socket_root / name
                listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                listener.bind(str(path))
                sockets.append(listener)
                replacements[fixed_path] = str(path)

            script = tmp_path / "status.sh"
            _render_script(STATUS, script, replacements)
            completed = subprocess.run(
                ["/bin/bash", str(script)],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "CALL_LOG": str(call_log)},
            )
        finally:
            for listener in sockets:
                listener.close()

        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert RELAY_LABEL in completed.stdout
        assert str(launch_daemons / f"{RELAY_LABEL}.plist") in completed.stdout
        assert str(socket_root / "agent-relay.sock") in completed.stdout
        assert "tcp_listener_count=0 account=_mastermind_exec" in completed.stdout
        calls = call_log.read_text(encoding="utf-8")
        assert "lsof -nP -a -u _mastermind_exec -iTCP -sTCP:LISTEN" in calls
