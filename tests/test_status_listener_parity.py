"""Status.sh `check_listeners` and acceptance.py `_assert_no_public_listener`
must agree on every TCP-listener shape and every partial / unparseable
observation: status.sh returns `FAILED=1` exactly when acceptance raises, and
`tcp_listener_count=0` exactly when acceptance passes.

The status.sh function is extracted by hashing the helper, not by re-implementing
its shape, so a drift in either side fails this test on the first affected
fixture.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATUS_SH = ROOT / "ops" / "executive_os" / "status.sh"
ACCEPTANCE_PY = ROOT / "ops" / "executive_os" / "acceptance.py"


def _extract_check_listeners(text: str) -> str:
    start = text.index("check_listeners() {")
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise AssertionError("check_listeners body not found")


LSOF_HEADER = b"COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"


def _row(account: str, name: str) -> bytes:
    return (
        f"Python 1327 {account} 5u IPv4 0x1 0t0 TCP {name} (LISTEN)\n"
    ).encode("ascii")


def _run_acceptance(monkeypatch, outcomes):
    import importlib.util

    SPEC = importlib.util.spec_from_file_location(
        "executive_acceptance_parity", ACCEPTANCE_PY
    )
    assert SPEC is not None and SPEC.loader is not None
    acceptance = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = acceptance
    SPEC.loader.exec_module(acceptance)

    class _Sock:
        def __init__(self, present: bool = True) -> None:
            self.present = present

        def is_socket(self) -> bool:
            return self.present

    calls = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return next(iter(outcomes))

    monkeypatch.setattr(acceptance, "_run", fake_run)
    monkeypatch.setattr(acceptance, "CONTROL_SOCKET", _Sock(True))
    monkeypatch.setattr(acceptance, "WORKER_SOCKET", _Sock(True))
    instance = object.__new__(acceptance.Acceptance)
    return acceptance, instance, calls


def _harness(
    tmp_path: Path,
    check_listeners_body: str,
    *,
    lsof_stdout: bytes = b"",
    lsof_stderr: bytes = b"",
    lsof_rc: int = 0,
    account: str = "_mastermind_exec",
    name: str = "bin",
) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / name
    bin_dir.mkdir(exist_ok=True)

    id_path = bin_dir / "id"
    id_path.write_text("#!/bin/sh\necho 0\n")
    id_path.chmod(0o755)

    lsof_path = bin_dir / "lsof"
    lsof_script = (
        "#!/bin/sh\n"
        f"cat <<'EOF'\n{lsof_stdout.decode('ascii', errors='ignore')}\nEOF\n"
        f"cat <<'EOF' 1>&2\n{lsof_stderr.decode('ascii', errors='ignore')}\nEOF\n"
        f"exit {lsof_rc}\n"
    )
    lsof_path.write_text(lsof_script)
    lsof_path.chmod(0o755)

    harness = tmp_path / f"harness-{name}.sh"
    body = check_listeners_body.replace("/usr/sbin/lsof", str(lsof_path)).replace(
        "/usr/bin/id", str(id_path)
    )
    harness.write_text(
        "#!/bin/bash\n"
        "set -u\n"
        "INSPECTOR_UID=0\n"
        "FAILED=0\n"
        f"{body}\n"
        f"check_listeners {account}\n"
        "printf 'FAILED=%d\\n' \"$FAILED\"\n"
        "exit 0\n"
    )
    harness.chmod(0o755)

    return subprocess.run(
        ["/bin/bash", str(harness)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_status_sh_keeps_canonical_lsof_invocation():
    text = STATUS_SH.read_text()
    body = _extract_check_listeners(text)
    assert (
        '/usr/sbin/lsof -nP -a -u "$account" -iTCP -sTCP:LISTEN' in body
    ), body


def test_status_sh_listener_parity_with_acceptance(tmp_path, monkeypatch):
    text = STATUS_SH.read_text()
    body = _extract_check_listeners(text)
    assert (
        '/usr/sbin/lsof -nP -a -u "$account" -iTCP -sTCP:LISTEN' in body
    ), body

    # Listener refusal parity: every 6.4 fixture must FAILED=1 in status.sh
    # whenever acceptance raises "owns a TCP listener".
    listener_names = (
        "*:8787",
        "127.0.0.1:8787",
        "127.0.0.1:1",
        "127.0.0.1:65535",
        "[::1]:8787",
        "[::]:443",
        "0.0.0.0:8787",
        "*:1",
        "*:65535",
        "localhost:8787",
    )
    for name in listener_names:
        row = _row("_mastermind_exec", name)
        completed = subprocess.CompletedProcess(
            ["lsof"], 0, stdout=LSOF_HEADER + row, stderr=b""
        )
        acceptance, instance, calls = _run_acceptance(monkeypatch, iter([completed]))
        with pytest.raises(acceptance.AcceptanceError, match="owns a TCP listener"):
            instance._assert_no_public_listener()

        result = _harness(
            tmp_path,
            body,
            lsof_stdout=LSOF_HEADER + row,
            lsof_rc=0,
            name=f"listener-{name.replace(':', '-').replace('*', 'wild').replace('[', '').replace(']', '')}",
        )
        assert "FAILED=1" in result.stdout, (name, result.stdout, result.stderr)

    # Empty / unparseable observation parity: every 6.5 fixture must FAILED=1
    # whenever acceptance raises "did not produce a complete observation".
    fixtures = [
        (b"", b"", 0),
        (LSOF_HEADER, b"", 0),
        (
            LSOF_HEADER + b"Python 1327 _mastermind_exec 5u IPv4 0x1 0t0 TCP *:4787\n",
            b"",
            0,
        ),
        (
            LSOF_HEADER
            + b"Python 1327 _mastermind_exec 5u IPv4 0x1 0t0 TCP *:4787 ESTABLISHED\n",
            b"",
            0,
        ),
        (b"garbled header\nPython 1327 _mastermind_exec 5u IPv4 0x1 0t0 TCP *:4787 (LISTEN)\n", b"", 0),
        (b"", b"lsof: permission denied\n", 1),
        (b"some leftover line\n", b"", 1),
        (b"", b"", 2),
        (b"", b"", 0),
    ]
    for stdout, stderr, rc in fixtures:
        completed = subprocess.CompletedProcess(["lsof"], rc, stdout=stdout, stderr=stderr)
        acceptance, instance, _calls = _run_acceptance(monkeypatch, iter([completed]))
        with pytest.raises(
            acceptance.AcceptanceError, match="did not produce a complete observation"
        ):
            instance._assert_no_public_listener()

        result = _harness(
            tmp_path,
            body,
            lsof_stdout=stdout,
            lsof_stderr=stderr,
            lsof_rc=rc,
        )
        assert "FAILED=1" in result.stdout, (rc, stdout, result.stdout, result.stderr)

    # Negative control: empty rc=1 / empty streams on both passes.
    empty_completed = subprocess.CompletedProcess(["lsof"], 1, stdout=b"", stderr=b"")
    acceptance, instance, _calls = _run_acceptance(
        monkeypatch, iter([empty_completed, empty_completed])
    )
    instance._assert_no_public_listener()

    result = _harness(
        tmp_path,
        body,
        lsof_stdout=b"",
        lsof_stderr=b"",
        lsof_rc=1,
    )
    assert "FAILED=0" in result.stdout, result.stdout
    assert "tcp_listener_count=0" in result.stdout, result.stdout