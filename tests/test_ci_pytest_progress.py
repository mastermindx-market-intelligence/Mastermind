"""CI timing is visible before a shard exits and never grants test success."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
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


def test_real_pytest_timing_preserves_failure_and_reports_every_module(
    tmp_path, monkeypatch
):
    # This asserts the serial record contract; a shard job exporting
    # CI_PYTEST_WORKERS must not change it.
    monkeypatch.delenv("CI_PYTEST_WORKERS", raising=False)
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


def test_real_pytest_timing_reports_each_module_once_under_xdist(tmp_path):
    """pytest-xdist interleaves forwarded modules; each still reports once."""
    first = tmp_path / "test_first.py"
    second = tmp_path / "test_second.py"
    first.write_text("import time\n"
                     "def test_one(): time.sleep(0.05)\n"
                     "def test_two(): time.sleep(0.05)\n")
    second.write_text("import pytest\n"
                      "def test_skip(): pytest.skip('fixture')\n"
                      "def test_fail(): assert False, 'retained assertion'\n")
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    argv = [
        cip.sys.executable, "-u", "-m", "pytest",
        "-p", "xdist", "-p", "scripts.ci_pytest_timing",
        "--durations=25", "-q", "-n", "2", "--dist", "loadfile",
        str(first), str(second),
    ]
    result = subprocess.run(
        argv, cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 1
    assert "retained assertion" in result.stdout
    # Captured stdout renders only on failure: this print exists so that a
    # rare interleaving miss (seen once, on CI run 43015530899 with counts
    # [1, 1] for one module and no local reproduction in 30 rounds) leaves
    # the child's full record stream in the failure evidence.
    print(result.stdout)
    records = [json.loads(line.removeprefix("CI_MODULE "))
               for line in result.stdout.splitlines() if line.startswith("CI_MODULE ")]
    starts = [r for r in records if r["event"] == "start"]
    summaries = [r for r in records if r["event"] == "summary"]
    assert sorted(Path(r["module"]).name for r in starts) == [
        "test_first.py", "test_second.py",
    ]
    assert sorted(Path(r["module"]).name for r in summaries) == [
        "test_first.py", "test_second.py",
    ]
    by_module = {Path(r["module"]).name: r for r in summaries}
    assert [by_module["test_first.py"]["cases_started"],
            by_module["test_first.py"]["cases_finished"]] == [2, 2]
    assert [by_module["test_second.py"]["cases_started"],
            by_module["test_second.py"]["cases_finished"]] == [2, 2]
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
    # This child asserts the serial progress path: a shard job exporting
    # CI_PYTEST_WORKERS must not add xdist flags it cannot load.
    monkeypatch.delenv("CI_PYTEST_WORKERS", raising=False)
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
