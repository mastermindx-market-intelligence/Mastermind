"""A pytest-xdist shard that loses a worker or tests never exits 0."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import ci_pytest as cip
from scripts.ci_xdist_guard import XdistCompletionGuard

ROOT = Path(__file__).resolve().parents[1]


def _run(argv, *, timeout=90):
    env = dict(os.environ)
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
    return subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)


def test_worker_lost_during_import_fails_the_shard_instead_of_no_tests_ran(tmp_path):
    # Reproduces the xdist 3.8.0 hole: one worker exits while importing, the
    # others collect, nothing is scheduled, pytest prints "no tests ran" and
    # would exit 0. The guard turns that into a failed shard.
    pytest.importorskip("xdist")
    (tmp_path / "test_dies_on_one_worker.py").write_text(
        "import os\n"
        "if os.environ.get('PYTEST_XDIST_WORKER') == 'gw1':\n"
        "    os._exit(0)\n"
        "def test_one(): pass\n"
        "def test_two(): pass\n"
    )
    (tmp_path / "test_healthy.py").write_text("def test_three(): pass\n")
    modules = [str(tmp_path / "test_dies_on_one_worker.py"), str(tmp_path / "test_healthy.py")]
    result = _run(cip.pytest_argv(modules, progress=True, workers=2))
    assert result.returncode != 0, result.stdout + result.stderr
    assert "CI_XDIST_GUARD shard incomplete" in result.stdout
    assert "went down" in result.stdout


def test_complete_parallel_run_is_untouched(tmp_path):
    pytest.importorskip("xdist")
    (tmp_path / "test_a.py").write_text("def test_one(): pass\n")
    (tmp_path / "test_b.py").write_text("import pytest\ndef test_two(): pytest.skip('x')\n")
    modules = [str(tmp_path / "test_a.py"), str(tmp_path / "test_b.py")]
    result = _run(cip.pytest_argv(modules, progress=True, workers=2))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CI_XDIST_GUARD" not in result.stdout
    # A real failure still fails for its own reason, without a guard line.
    (tmp_path / "test_a.py").write_text("def test_one(): assert False, 'real failure'\n")
    result = _run(cip.pytest_argv(modules, progress=True, workers=2))
    assert result.returncode == 1
    assert "real failure" in result.stdout
    assert "CI_XDIST_GUARD" not in result.stdout


def test_guard_forces_nonzero_only_when_something_was_lost():
    lines = []
    reporter = SimpleNamespace(write_line=lines.append)
    guard = XdistCompletionGuard(reporter)
    session = SimpleNamespace(testscollected=3, exitstatus=0)
    for nodeid in ("t.py::a", "t.py::b", "t.py::c"):
        guard.pytest_runtest_logfinish(nodeid, None)
    guard.pytest_testnodedown(SimpleNamespace(gateway=SimpleNamespace(id="gw0")), None)
    guard.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 0 and lines == []

    guard = XdistCompletionGuard(reporter)
    session = SimpleNamespace(testscollected=3, exitstatus=0)
    guard.pytest_runtest_logfinish("t.py::a", None)
    guard.pytest_testnodedown(SimpleNamespace(gateway=SimpleNamespace(id="gw1")), "Not properly terminated")
    guard.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 1
    assert "worker gw1 went down: Not properly terminated" in lines[-1]
    assert "finished 1 of 3 collected test cases" in lines[-1]

    # An already-failed session keeps its own exit status.
    guard = XdistCompletionGuard(reporter)
    session = SimpleNamespace(testscollected=2, exitstatus=1)
    guard.pytest_sessionfinish(session, 1)
    assert session.exitstatus == 1


def test_guard_is_absent_from_serial_argv_and_workers_do_not_register():
    assert "scripts.ci_xdist_guard" not in cip.pytest_argv(["tests/test_x.py"], progress=True)
    argv = cip.pytest_argv(["tests/test_x.py"], progress=True, workers=3)
    assert argv[argv.index("-p", argv.index("-q")) + 1] == "scripts.ci_xdist_guard"
    from scripts import ci_xdist_guard
    registered = []
    config = SimpleNamespace(
        workerinput={"workerid": "gw0"}, option=SimpleNamespace(numprocesses=3),
        pluginmanager=SimpleNamespace(register=lambda *a, **k: registered.append(a),
                                      getplugin=lambda name: object()),
    )
    ci_xdist_guard.pytest_sessionstart(SimpleNamespace(config=config))
    assert registered == []
    del config.workerinput
    config.option.numprocesses = None
    ci_xdist_guard.pytest_sessionstart(SimpleNamespace(config=config))
    assert registered == []
    config.option.numprocesses = 3
    ci_xdist_guard.pytest_sessionstart(SimpleNamespace(config=config))
    assert len(registered) == 1 and registered[0][1] == "ci-xdist-completion-guard"
