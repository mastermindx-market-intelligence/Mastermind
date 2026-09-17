"""MAS-115 credential entry must fail closed before unsafe input fallback.

All inputs are synthetic and all Keychain effects are replaced with fakes.
The PTY cases exercise Python's real getpass terminal behavior without using a
real credential, Security.framework, vendor, browser, profile, or account.
"""
from __future__ import annotations

import getpass
import io
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import termios
import time
from unittest.mock import patch
import warnings

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_REPO_ROOT))

from scripts import mas115_keychain_store as keychain_store

_SYNTHETIC = "A" * 64 + "." + "B" * 64 + "." + "C" * 64
_CLOSED_REFUSAL = "REFUSED: Multilogin credential was not stored.\n"


class _CountingInput(io.StringIO):
    def __init__(self, value: str):
        super().__init__(value)
        self.read_count = 0

    def readline(self, *args, **kwargs):
        self.read_count += 1
        return super().readline(*args, **kwargs)


class _FakeKeychain:
    def __init__(self, *, existing: bool = False, fail: str | None = None):
        self.calls: list[str] = []
        self.existing = existing
        self.fail = fail

    def find_item(self):
        self.calls.append("find")
        if self.fail == "find":
            raise RuntimeError("synthetic_private_error")
        return object() if self.existing else None

    def add_item(self, value):
        assert isinstance(value, bytes)
        self.calls.append("add")
        if self.fail == "add":
            raise RuntimeError("synthetic_private_error")

    def modify_item(self, _item, value):
        assert isinstance(value, bytes)
        self.calls.append("modify")
        if self.fail == "modify":
            raise RuntimeError("synthetic_private_error")

    def release_item(self, _item):
        self.calls.append("release")


def _run(*, prompt_fn=None, existing=False, fail=None):
    fake = _FakeKeychain(existing=existing, fail=fail)
    factories = []
    out = io.StringIO()
    err = io.StringIO()

    def _factory():
        factories.append("factory")
        return fake

    kwargs = {
        "api_factory": _factory,
        "stdout": out,
        "stderr": err,
    }
    if prompt_fn is not None:
        kwargs["prompt_fn"] = prompt_fn
    code = keychain_store.main(**kwargs)
    output = out.getvalue() + err.getvalue()
    return {
        "code": code,
        "calls": fake.calls,
        "factory_count": len(factories),
        "success": "stored in Keychain" in out.getvalue(),
        "stdout": out.getvalue(),
        "stderr": err.getvalue(),
        "contains_synthetic": _SYNTHETIC in output,
        "contains_dynamic_error": "synthetic_private_error" in output,
    }


def _assert_private(result):
    assert result["contains_synthetic"] is False
    assert result["contains_dynamic_error"] is False
    assert result["stderr"] in ("", _CLOSED_REFUSAL)


@pytest.mark.parametrize("outer_policy", ["default", "ignore", "once", "always", "error"])
@pytest.mark.parametrize("existing,valid", [(False, True), (True, True), (False, False)])
def test_getpass_fallback_refuses_before_input_read_or_keychain_open(
    outer_policy, existing, valid,
):
    stream = _CountingInput((_SYNTHETIC if valid else "invalid") + "\n")
    captured_stderr = io.StringIO()

    with warnings.catch_warnings(record=True):
        warnings.simplefilter(outer_policy, getpass.GetPassWarning)
        filters_before = list(warnings.filters)
        with patch.object(getpass.os, "open", side_effect=OSError("synthetic no tty")):
            with patch.object(sys, "stdin", stream), patch.object(sys, "stderr", captured_stderr):
                result = _run(existing=existing)
        assert warnings.filters == filters_before

    assert stream.read_count == 0
    assert result["code"] == 2
    assert result["calls"] == []
    assert result["factory_count"] == 0
    assert result["success"] is False
    assert "Password input may be echoed" not in captured_stderr.getvalue()
    _assert_private(result)


@pytest.mark.parametrize("mode", ["warning", "interrupt", "eof", "error", "invalid"])
def test_prompt_refusal_precedes_storage_and_restores_warning_policy(mode):
    def _prompt(_message):
        if mode == "warning":
            warnings.warn("synthetic_private_error", getpass.GetPassWarning)
            return _SYNTHETIC
        if mode == "interrupt":
            raise KeyboardInterrupt()
        if mode == "eof":
            raise EOFError()
        if mode == "error":
            raise RuntimeError("synthetic_private_error")
        return "invalid"

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("ignore", getpass.GetPassWarning)
        filters_before = list(warnings.filters)
        result = _run(prompt_fn=_prompt)
        assert warnings.filters == filters_before

    assert result["code"] == 2
    assert result["calls"] == []
    assert result["factory_count"] == 0
    assert result["success"] is False
    _assert_private(result)


@pytest.mark.parametrize("existing", [False, True])
def test_valid_hidden_value_preserves_fixed_add_or_replace(existing):
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("ignore", getpass.GetPassWarning)
        filters_before = list(warnings.filters)
        result = _run(prompt_fn=lambda _message: _SYNTHETIC, existing=existing)
        assert warnings.filters == filters_before

    assert result["code"] == 0
    assert result["success"] is True
    assert result["factory_count"] == 1
    assert result["calls"] == (
        ["find", "modify", "release"] if existing else ["find", "add"]
    )
    _assert_private(result)


@pytest.mark.parametrize(
    "failure,existing,expected_calls",
    [
        ("find", False, ["find"]),
        ("add", False, ["find", "add"]),
        ("modify", True, ["find", "modify", "release"]),
    ],
)
def test_keychain_failures_are_closed_and_existing_handle_is_released(
    failure, existing, expected_calls,
):
    result = _run(
        prompt_fn=lambda _message: _SYNTHETIC,
        existing=existing,
        fail=failure,
    )
    assert result["code"] == 2
    assert result["success"] is False
    assert result["calls"] == expected_calls
    _assert_private(result)


def test_fixed_keychain_coordinates_and_secret_limits_are_unchanged():
    assert keychain_store._KEYCHAIN_SERVICE == b"mastermind.mas115.multilogin.disposable"
    assert keychain_store._KEYCHAIN_ACCOUNT == b"mastermind-mas115-canary"
    assert keychain_store._MIN_SECRET_BYTES == 129
    assert keychain_store._MAX_SECRET_BYTES == 16 * 1024


def _pty_child(fault: str):
    fake = _FakeKeychain()
    calls = {"raw_input": 0, "disable": 0, "restore": 0}
    real_get = termios.tcgetattr
    real_set = termios.tcsetattr
    real_raw = getpass._raw_input

    def _get(fd):
        if fault == "get":
            raise termios.error(25, "synthetic_private_error")
        return real_get(fd)

    def _set(fd, flags, state):
        enabling_echo = bool(state[3] & termios.ECHO)
        calls["restore" if enabling_echo else "disable"] += 1
        if fault == "disable" and not enabling_echo:
            raise termios.error(25, "synthetic_private_error")
        if fault == "restore" and enabling_echo:
            raise termios.error(25, "synthetic_private_error")
        return real_set(fd, flags, state)

    def _raw(*args, **kwargs):
        calls["raw_input"] += 1
        if fault == "interrupt":
            raise KeyboardInterrupt()
        if fault == "eof":
            raise EOFError()
        if fault == "read_error":
            raise OSError("synthetic_private_error")
        return real_raw(*args, **kwargs)

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("ignore", getpass.GetPassWarning)
        with patch.object(getpass.termios, "tcgetattr", _get):
            with patch.object(getpass.termios, "tcsetattr", _set):
                with patch.object(getpass, "_raw_input", _raw):
                    result = _run()
    result["terminal_calls"] = calls
    print(json.dumps(result, sort_keys=True), flush=True)


def _read_available(fd, target: bytearray):
    while select.select([fd], [], [], 0)[0]:
        try:
            chunk = os.read(fd, 8192)
        except OSError:
            break
        if not chunk:
            break
        target.extend(chunk)


def _pty_case(fault: str):
    master, slave = pty.openpty()
    process = None
    captured = bytearray()
    sent = False
    try:
        initial = termios.tcgetattr(slave)
        initial[3] |= termios.ECHO
        termios.tcsetattr(slave, termios.TCSANOW, initial)
        process = subprocess.Popen(
            [sys.executable, os.fspath(Path(__file__).resolve()), "--pty-child", fault],
            stdin=slave,
            stderr=slave,
            stdout=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
            env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.02)[0]:
                try:
                    captured.extend(os.read(master, 8192))
                except OSError:
                    pass
            if not sent and b"press Return:" in captured:
                os.write(master, _SYNTHETIC.encode("ascii") + b"\n")
                sent = True
            if process.poll() is not None:
                _read_available(master, captured)
                break
        if process.poll() is None:
            raise RuntimeError("synthetic PTY test deadline exceeded")
        stdout, _ = process.communicate(timeout=1)
        assert process.returncode == 0
        result = json.loads(stdout)
        result.update(
            input_sent=sent,
            input_echoed=_SYNTHETIC.encode("ascii") in captured,
            echo_restored=bool(termios.tcgetattr(slave)[3] & termios.ECHO),
            child_exited=True,
        )
        return result
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=1)
        if process is not None and process.stdout is not None:
            process.stdout.close()
        os.close(master)
        os.close(slave)
        captured.clear()


@pytest.mark.skipif(not hasattr(termios, "ECHO"), reason="POSIX terminal proof")
@pytest.mark.parametrize("fault", ["get", "disable"])
def test_real_terminal_control_failure_never_falls_back_to_echoed_input(fault):
    result = _pty_case(fault)
    assert result["terminal_calls"]["raw_input"] == 0
    assert result["input_sent"] is False
    assert result["input_echoed"] is False
    assert result["code"] == 2
    assert result["factory_count"] == 0
    assert result["calls"] == []
    assert result["echo_restored"] is True
    assert result["child_exited"] is True
    _assert_private(result)


@pytest.mark.skipif(not hasattr(termios, "ECHO"), reason="POSIX terminal proof")
def test_real_working_terminal_accepts_without_echo_and_restores_terminal():
    result = _pty_case("none")
    assert result["code"] == 0
    assert result["input_sent"] is True
    assert result["input_echoed"] is False
    assert result["calls"] == ["find", "add"]
    assert result["terminal_calls"] == {"raw_input": 1, "disable": 1, "restore": 1}
    assert result["echo_restored"] is True
    assert result["child_exited"] is True
    _assert_private(result)


@pytest.mark.skipif(not hasattr(termios, "ECHO"), reason="POSIX terminal proof")
@pytest.mark.parametrize("fault", ["interrupt", "eof", "read_error"])
def test_terminal_abort_restores_echo_and_never_stores(fault):
    result = _pty_case(fault)
    assert result["code"] == 2
    assert result["factory_count"] == 0
    assert result["calls"] == []
    assert result["input_echoed"] is False
    assert result["echo_restored"] is True
    assert result["terminal_calls"]["restore"] == 1
    assert result["child_exited"] is True
    _assert_private(result)


@pytest.mark.skipif(not hasattr(termios, "ECHO"), reason="POSIX terminal proof")
def test_terminal_restore_failure_refuses_storage_and_does_not_read_twice():
    result = _pty_case("restore")
    assert result["code"] == 2
    assert result["factory_count"] == 0
    assert result["calls"] == []
    assert result["terminal_calls"]["raw_input"] == 1
    assert result["input_sent"] is True
    assert result["input_echoed"] is False
    assert result["echo_restored"] is False
    assert result["child_exited"] is True
    _assert_private(result)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--pty-child":
        raise SystemExit("synthetic PTY child only; run this file through pytest")
    _pty_child(sys.argv[2])
