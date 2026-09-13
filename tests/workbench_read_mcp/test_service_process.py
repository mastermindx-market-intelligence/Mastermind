"""Process-boundary tests for the concrete Workbench Read service launcher."""
from __future__ import annotations

import contextlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/mastermind_workbench_read_server.py"


def test_describe_remains_dependency_free_and_truthful() -> None:
    completed = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), "--describe"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "capability": "BUILT_NOT_PROVEN",
        "mode": "configured-loopback-service",
        "tool": "read_project_file",
        "config_schema": "mastermind.workbench_read_service.v1",
        "installed": False,
    }
    assert completed.stderr == ""


def test_legacy_parallel_authority_flags_are_rejected() -> None:
    launcher = importlib.import_module("scripts.mastermind_workbench_read_server")
    for args in (
        ["--host", "127.0.0.1"],
        ["--port", "8765"],
        ["--root", "/"],
        ["--factory", "evil:main"],
    ):
        with contextlib.redirect_stderr(io.StringIO()):
            with pytest.raises(SystemExit) as captured:
                launcher.main(args)
        assert captured.value.code == 2


def test_config_is_required_and_prebind_refusal_is_exit_2(tmp_path: Path) -> None:
    launcher = importlib.import_module("scripts.mastermind_workbench_read_server")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert launcher.main([]) == 2
    assert err.getvalue().strip() == "SERVICE_CONFIGURATION_REQUIRED"

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert launcher.main(["--config", str(tmp_path / "missing.json")]) == 2
    assert err.getvalue().strip() == "SERVICE_CONFIGURATION_REFUSED"


def test_launcher_delegates_exact_config_path_and_preserves_service_exit(monkeypatch, tmp_path: Path) -> None:
    launcher = importlib.import_module("scripts.mastermind_workbench_read_server")
    path = tmp_path / "service.json"
    path.write_text("{}", encoding="ascii")
    calls = []

    def fake(path_value: str) -> int:
        calls.append(path_value)
        return 4

    monkeypatch.setattr(launcher, "_run_configured_service", fake)
    assert launcher.main(["--config", str(path)]) == 4
    assert calls == [str(path)]
