"""REV-CODE F3: the dev T3 launcher's port guard refuses the neighbour
listeners 3796 (another lane — BRIEF §4) and 3800 (reserved), keeping the
original 3773/3774 (the live T3 app).

Network-free by construction: the script is sourced with T3_DEV_LIB_ONLY=1
(define guards only, dispatch nothing); ``port_forbidden`` is a pure string
match; every ``pick_port`` test STUBS ``port_busy`` so no socket is ever
opened.  The decisive assertion is that 3796/3800 are never even PROBED —
the guard skips them before any busy check — and never picked.

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     -p no:cacheprovider tests/test_t3_dev_port_guards.py
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / ".." / "tools" / "mmos_dev" / "t3_dev.sh"


def _run_sh(body: str) -> subprocess.CompletedProcess:
    """Source the launcher in lib-only mode and run ``body``.  No command is
    dispatched and no port is probed unless ``body`` explicitly does so."""
    env = dict(os.environ)
    env["T3_DEV_LIB_ONLY"] = "1"
    env["T3_DEV_SCRIPT"] = str(SCRIPT)
    # pin the interpreter the launcher's top-level check requires (it exists
    # on this host); the guard tests themselves never invoke it
    env["PYTHON3_BIN"] = "/opt/homebrew/bin/python3.12"
    snippet = '. "$T3_DEV_SCRIPT"\n' + body
    return subprocess.run(["/bin/sh", "-c", snippet], env=env,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("port", [3773, 3774, 3796, 3800])
def test_forbidden_ports_include_the_live_app_and_neighbour_listeners(port):
    result = _run_sh(
        f'if port_forbidden {port}; then echo F; else echo A; fi')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "F", f"{port} must be forbidden"


@pytest.mark.parametrize("port", [3790, 3794, 3830, 3839])
def test_dev_ports_stay_allowed(port):
    result = _run_sh(
        f'if port_forbidden {port}; then echo F; else echo A; fi')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "A", f"{port} must stay allowed"


def test_pick_port_never_probes_the_forbidden_neighbours():
    """Over 3796..3800 with every non-forbidden port reported BUSY, pick_port
    selects nothing and — the decisive point — never probes 3796 or 3800:
    the guard skips them before any busy check."""
    body = (
        "PORT_MIN=3796\n"
        "PORT_MAX=3800\n"
        'port_busy() { echo "probe:$1" >&2; return 0; }\n'  # 0 = busy
        "if pick_port >/dev/null; then echo PICKED; else echo NONE; fi\n"
    )
    result = _run_sh(body)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "NONE", "no port may be selected"
    assert "probe:3796" not in result.stderr, "3796 must never be probed"
    assert "probe:3800" not in result.stderr, "3800 must never be probed"
    # the stub did run for the non-forbidden ports in between
    assert "probe:3797" in result.stderr


@pytest.mark.parametrize("port", [3796, 3800])
def test_pick_port_refuses_a_single_forbidden_port_even_if_free(port):
    """A range of exactly one forbidden port yields nothing even when the
    stub reports it FREE, and the port is never probed."""
    body = (
        f"PORT_MIN={port}\n"
        f"PORT_MAX={port}\n"
        'port_busy() { echo "probe:$1" >&2; return 1; }\n'  # 1 = free
        "if pick_port >/dev/null; then echo PICKED; else echo NONE; fi\n"
    )
    result = _run_sh(body)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "NONE", f"{port} must not be picked"
    assert f"probe:{port}" not in result.stderr, f"{port} must never be probed"