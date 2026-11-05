"""CI timing is visible before a shard exits and never grants test success."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import pytest
from pathlib import Path

from scripts import ci_pytest as cip


def test_module_progress_arrives_before_shard_finishes(tmp_path, monkeypatch):
    release = tmp_path / "release"
    helper = tmp_path / "child.py"
    helper.write_text(
        "import pathlib, sys, time\n"
        "print('CI_MODULE {\"event\":\"start\",\"module\":\"test_wait.py\"}', flush=True)\n"
        "print('retained ordinary output', flush=True)\n"
        "while not pathlib.Path(sys.argv[1]).exists(): time.sleep(0.01)\n"
        "print('retained failure', file=sys.stderr, flush=True)\n"
        "sys.exit(3)\n"
    )
    monkeypatch.setattr(
        cip, "pytest_argv",
        lambda *args, **kwargs: [sys.executable, str(helper), str(release)],
    )
    progress = threading.Event()
    output = []

    def record(*args, **kwargs):
        text = " ".join(map(str, args))
        output.append(text)
        if "CI_MODULE " in text:
            progress.set()

    monkeypatch.setattr(cip, "print", record, raising=False)
    codes = []
    worker = threading.Thread(
        target=lambda: codes.append(cip.run_shards((("test_wait.py",),), root=tmp_path)),
    )
    worker.start()
    try:
        arrived_before_exit = progress.wait(5)
        retained_until_exit = "retained ordinary output" not in "\n".join(output)
    finally:
        release.write_text("finish")
        worker.join(5)
    assert not worker.is_alive()
    assert arrived_before_exit, "the unfinished shard's module must be visible"
    assert retained_until_exit
    assert codes == [3]
    rendered = "\n".join(output)
    assert "shard 1/1 progress" in rendered
    assert "retained ordinary output" in rendered
    assert "retained failure" in rendered


def test_real_pytest_timing_preserves_failure_and_reports_every_module(tmp_path):
    first = tmp_path / "test_first.py"
    second = tmp_path / "test_second.py"
    first.write_text("def test_pass(): pass\n")
    second.write_text("import pytest\ndef test_skip(): pytest.skip('fixture')\n"
                      "def test_fail(): assert False, 'retained assertion'\n")
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        cip.pytest_argv([str(first), str(second)], progress=True),
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 1
    assert "retained assertion" in result.stdout
    records = [json.loads(line.removeprefix("CI_MODULE "))
               for line in result.stdout.splitlines() if line.startswith("CI_MODULE ")]
    assert [r["event"] for r in records] == ["start", "summary", "start", "summary"]
    summaries = [r for r in records if r["event"] == "summary"]
    assert [Path(r["module"]).name for r in summaries] == ["test_first.py", "test_second.py"]
    assert [r["cases_started"] for r in summaries] == [1, 2]
    assert [r["cases_finished"] for r in summaries] == [1, 2]
    assert all(r["reported_seconds"] >= 0 for r in summaries)


def test_composed_runner_reports_real_module_before_test_returns(tmp_path, monkeypatch):
    release = tmp_path / "release"
    fixture = tmp_path / "test_waiting.py"
    fixture.write_text(
        "import pathlib, time\n"
        "def test_waiting():\n"
        f"    while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\n"
        "    assert False, 'actual child failure remains a gate failure'\n"
    )
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    progress = threading.Event()
    output = []

    def record(*args, **kwargs):
        text = " ".join(map(str, args))
        output.append(text)
        if '"event": "start"' in text and "test_waiting.py" in text:
            progress.set()

    monkeypatch.setattr(cip, "print", record, raising=False)
    codes = []
    worker = threading.Thread(target=lambda: codes.append(cip.run_shards(
        ((str(fixture),),), root=Path(__file__).resolve().parents[1],
    )))
    worker.start()
    try:
        arrived_before_exit = progress.wait(5)
    finally:
        release.write_text("finish")
        worker.join(5)
    assert not worker.is_alive()
    assert arrived_before_exit
    assert codes == [1]
    assert "actual child failure remains a gate failure" in "\n".join(output)


def test_real_xdist_run_reports_every_module_once_and_keeps_failure(tmp_path):
    # `--workers N` must not change what a shard proves: every module still
    # gets exactly one start and one summary record, the failing assertion
    # text still reaches stdout and the pytest exit status still governs.
    pytest.importorskip("xdist")
    modules = []
    for name, body in (
        ("test_alpha.py", "def test_pass(): pass\n"),
        ("test_beta.py", "import pytest\ndef test_skip(): pytest.skip('fixture')\n"
                         "def test_fail(): assert False, 'retained xdist assertion'\n"),
        ("test_gamma.py", "def test_one(): pass\ndef test_two(): pass\ndef test_three(): pass\n"),
    ):
        path = tmp_path / name
        path.write_text(body)
        modules.append(str(path))
    argv = cip.pytest_argv(modules, progress=True, workers=2)
    assert argv[argv.index("-n") + 1] == "2"
    env = dict(os.environ)
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
    result = subprocess.run(
        argv, cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "retained xdist assertion" in result.stdout
    records = [json.loads(line.removeprefix("CI_MODULE "))
               for line in result.stdout.splitlines() if line.startswith("CI_MODULE ")]
    by_module = {}
    for record in records:
        by_module.setdefault(Path(record["module"]).name, []).append(record["event"])
    assert by_module == {
        "test_alpha.py": ["start", "summary"],
        "test_beta.py": ["start", "summary"],
        "test_gamma.py": ["start", "summary"],
    }
    summaries = {Path(r["module"]).name: r for r in records if r["event"] == "summary"}
    assert {name: r["cases_started"] for name, r in summaries.items()} == {
        "test_alpha.py": 1, "test_beta.py": 2, "test_gamma.py": 3,
    }
    assert {name: r["cases_finished"] for name, r in summaries.items()} == {
        "test_alpha.py": 1, "test_beta.py": 2, "test_gamma.py": 3,
    }
    assert all(r["reported_seconds"] >= 0 for r in summaries.values())


def test_parallel_timing_closes_a_module_on_its_own_worker_not_on_interleaving():
    # Two xdist workers interleave their events on the controller. A module
    # is closed only when ITS worker reports a different module (or at
    # session end), never because another worker started something.
    from types import SimpleNamespace
    from scripts.ci_pytest_timing import ModuleTiming

    lines = []
    reporter = SimpleNamespace(write_line=lines.append)
    timing = ModuleTiming(reporter, parallel=True)
    workers = {
        "gw0": SimpleNamespace(gateway=SimpleNamespace(id="gw0")),
        "gw1": SimpleNamespace(gateway=SimpleNamespace(id="gw1")),
    }

    def report(nodeid, worker, *, failed=False, duration=0.5):
        return SimpleNamespace(
            nodeid=nodeid, duration=duration, when="call", failed=failed,
            node=workers[worker],
        )

    timing.pytest_runtest_logstart("tests/test_a.py::test_1", None)
    timing.pytest_runtest_logstart("tests/test_b.py::test_1", None)   # other worker
    timing.pytest_runtest_logreport(report("tests/test_a.py::test_1", "gw0"))
    timing.pytest_runtest_logreport(report("tests/test_b.py::test_1", "gw1"))
    timing.pytest_runtest_logfinish("tests/test_a.py::test_1", None)
    timing.pytest_runtest_logfinish("tests/test_b.py::test_1", None)
    timing.pytest_runtest_logstart("tests/test_a.py::test_2", None)
    timing.pytest_runtest_logreport(report("tests/test_a.py::test_2", "gw0"))
    timing.pytest_runtest_logfinish("tests/test_a.py::test_2", None)
    # gw0 moves on to module c: that, and only that, closes module a.
    timing.pytest_runtest_logstart("tests/test_c.py::test_1", None)
    timing.pytest_runtest_logreport(report("tests/test_c.py::test_1", "gw0"))
    timing.pytest_runtest_logfinish("tests/test_c.py::test_1", None)
    events_so_far = [json.loads(l.removeprefix("\nCI_MODULE ")) for l in lines]
    assert [(e["event"], Path(e["module"]).name) for e in events_so_far] == [
        ("start", "test_a.py"), ("start", "test_b.py"), ("start", "test_c.py"),
        ("summary", "test_a.py"),
    ]
    assert events_so_far[-1]["cases_started"] == 2
    assert events_so_far[-1]["cases_finished"] == 2
    assert events_so_far[-1]["reported_seconds"] == 1.0
    timing.pytest_sessionfinish(None, 0)
    closing = [json.loads(l.removeprefix("\nCI_MODULE ")) for l in lines[4:]]
    assert sorted(Path(e["module"]).name for e in closing) == ["test_b.py", "test_c.py"]
    assert all(e["event"] == "summary" for e in closing)
