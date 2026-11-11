"""The real RWE wrapper exposes an unfinished gate without granting success."""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from scripts import rwe_env as rwe


def test_stream_gate_drains_both_pipes_and_preserves_split_unicode(tmp_path, capsys):
    child = tmp_path / "streams.py"
    child.write_text(
        "import os, sys\n"
        "os.write(1, b'A' * 150000 + b'\\n')\n"
        "os.write(2, b'B' * 150000 + b'\\n')\n"
        "os.write(1, b'\\xe2'); os.write(1, b'\\x82\\xac\\r\\n')\n"
        "sys.exit(7)\n"
    )
    completed = rwe._stream_gate([sys.executable, "-u", str(child)], cwd=tmp_path)
    displayed = capsys.readouterr()
    assert completed.returncode == 7
    assert completed.stdout == "A" * 150000 + "\n€\n"
    assert completed.stderr == "B" * 150000 + "\n"
    assert displayed.out == completed.stdout
    assert displayed.err == completed.stderr


def _gate_fixture(tmp_path, monkeypatch, script):
    root = Path(__file__).resolve().parents[1]
    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    gate = tmp_path / "gate.py"
    gate.write_text(script)
    monkeypatch.setattr(rwe, "_venv_python", lambda env: Path(sys.executable))
    # This suite tests the child/receipt path, independently of the existing
    # interpreter and vendored-input prerequisite refusal tests.
    monkeypatch.setattr(rwe, "require_supported_interpreter", lambda executable: None)
    monkeypatch.setattr(rwe, "vendor_present", lambda root: True)
    monkeypatch.setattr(rwe, "GATE_SCRIPT_RELATIVE", gate)
    monkeypatch.setenv("PYTHONPATH", str(root))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    # This child asserts the serial progress path: a shard job exporting
    # CI_PYTEST_WORKERS must not change the gate shape under test here.
    monkeypatch.delenv("CI_PYTEST_WORKERS", raising=False)
    return argparse.Namespace(root=str(root), env=str(env_dir), subset=None), env_dir


def test_cmd_gate_reports_real_module_before_original_child_finishes(tmp_path, monkeypatch):
    release = tmp_path / "release"
    case = tmp_path / "test_waiting.py"
    case.write_text(
        "import pathlib, time\n"
        "def test_waiting():\n"
        f"    while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\n"
        "    assert False, 'original blocked child failure remains a gate failure'\n"
    )
    script = (
        "import sys\nfrom scripts import ci_pytest as cip\n"
        f"cip.resolve_gate = lambda root: {{'included': ({str(case)!r},), "
        "'plan': {'discovered': 1, 'excluded': 0, 'running': 1}}\n"
        "print('stderr remains separate', file=sys.stderr, flush=True)\n"
        "raise SystemExit(cip.main(sys.argv[1:]))\n"
    )
    args, env_dir = _gate_fixture(tmp_path, monkeypatch, script)
    progress = threading.Event()

    class ObservedOutput(io.StringIO):
        def write(self, text):
            count = super().write(text)
            if '"event": "start"' in self.getvalue() and "test_waiting.py" in self.getvalue():
                progress.set()
            return count

    output, errors = ObservedOutput(), io.StringIO()
    monkeypatch.setattr(rwe.sys, "stdout", output)
    monkeypatch.setattr(rwe.sys, "stderr", errors)
    codes, exceptions = [], []

    def run():
        try:
            codes.append(rwe.cmd_gate(args))
        except BaseException as exc:
            exceptions.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        arrived_before_exit = progress.wait(8)
        no_early_receipt = not (env_dir / rwe.RECEIPT_FILENAME).exists()
    finally:
        release.write_text("finish")
        worker.join(8)
    assert not worker.is_alive()
    assert exceptions == []
    assert arrived_before_exit
    assert no_early_receipt
    assert codes == [1]
    assert "original blocked child failure remains a gate failure" in output.getvalue()
    assert output.getvalue().count('"event": "start"') == 1
    assert errors.getvalue().count("stderr remains separate") == 1
    receipt = json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text())
    assert receipt["proof"]["gate"]["exit"] == 1
    assert receipt["proof"]["gate"]["discovered"] == 1
    assert receipt["proof"]["gate"]["command"].endswith("--progress")


def test_cmd_gate_observation_failure_cannot_write_completed_receipt(tmp_path, monkeypatch):
    script = (
        "import time\n"
        "print('original child started', flush=True)\n"
        "while True: time.sleep(0.01)\n"
    )
    args, env_dir = _gate_fixture(tmp_path, monkeypatch, script)
    processes = []
    original_popen = subprocess.Popen

    def capture_process(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    class RefusedOutput(io.StringIO):
        def write(self, text):
            raise OSError("fixture observation interrupted")

    monkeypatch.setattr(rwe.subprocess, "Popen", capture_process)
    monkeypatch.setattr(rwe.sys, "stdout", RefusedOutput())
    with pytest.raises(OSError, match="fixture observation interrupted"):
        rwe.cmd_gate(args)
    assert len(processes) == 1
    assert processes[0].poll() is not None
    assert not (env_dir / rwe.RECEIPT_FILENAME).exists()
