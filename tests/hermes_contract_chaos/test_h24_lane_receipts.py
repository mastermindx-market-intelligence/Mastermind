"""Adversarial checks for truthful qualification and disposable Git isolation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import pytest

from . import run_lane
from .fixtures import SECRET_SENTINEL
from .offline_guard import OfflineGuard, OfflineViolation


def _child_receipts(command, env, *, mode="pass", exit_code=0):
    junit = Path(next(value.split("=", 1)[1] for value in command if value.startswith("--junitxml=")))
    node = "tests/hermes_contract_chaos/test_h24_concurrency.py::test_stub"
    nodes = [] if mode == "zero" else [node]
    reports = [{"node_id": item, "when": when, "outcome": "passed"}
               for item in nodes for when in ("setup", "call", "teardown")]
    document = {"schema": "mastermind.h24_pytest_execution.v1",
                "invocation_id": env["H24_INVOCATION_ID"], "collected": nodes,
                "reports": reports, "deselected": [], "pytest_exit_code": exit_code}
    skipped = failures = 0
    if mode == "deselected":
        document["deselected"] = ["test_not_executed"]
    if mode == "missing_teardown":
        reports.pop()
    if mode == "wrong_invocation":
        document["invocation_id"] = "prior-invocation"
    if mode == "duplicate_collection":
        nodes.append(node)
    if mode == "duplicate_report":
        reports.append(reports[-1])
    if mode == "wrong_file":
        document["collected"] = ["tests/not_the_lane.py::test_other"]
        for report in reports:
            report["node_id"] = document["collected"][0]
    if mode in {"skipped", "failure"}:
        reports[1]["outcome"] = "skipped" if mode == "skipped" else "failed"
        skipped, failures = int(mode == "skipped"), int(mode == "failure")
    count = len(nodes) + int(mode == "wrong_count")
    junit.write_text("<not-xml" if mode == "malformed_junit" else
        f'<testsuites><testsuite tests="{count}" failures="{failures}" errors="0" skipped="{skipped}"/></testsuites>')
    if mode != "no_manifest":
        Path(env["H24_EXECUTION_MANIFEST"]).write_text(json.dumps(document))
    return subprocess.CompletedProcess(command, exit_code)


def _invoke(tmp_path, monkeypatch, mode="pass", exit_code=0):
    report = tmp_path / "lane.json"
    monkeypatch.setattr(run_lane.sys, "argv", ["h24", "--lane", "concurrency", "--report", str(report)])
    monkeypatch.setattr(run_lane.subprocess, "run", lambda command, **kw:
                        _child_receipts(command, kw["env"], mode=mode, exit_code=exit_code))
    actual = run_lane.main()
    return actual, json.loads(report.read_text())


def test_inherited_pytest_options_cannot_select_a_false_green(tmp_path, monkeypatch):
    report = tmp_path / "lane.json"
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only -k nothing")
    monkeypatch.setenv("PYTEST_PLUGINS", "untrusted_plugin")
    monkeypatch.setattr(run_lane.sys, "argv", ["h24", "--lane", "concurrency", "--report", str(report)])
    seen = []

    def execute(command, **kwargs):
        env = kwargs["env"]
        assert not {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_CURRENT_TEST"}.intersection(env)
        assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == env["PYTHONNOUSERSITE"] == "1"
        seen.append(command)
        return _child_receipts(command, env)

    monkeypatch.setattr(run_lane.subprocess, "run", execute)
    assert run_lane.main() == 0 and len(seen) == 1
    result = json.loads(report.read_text())
    assert result["qualification"] == "PASS" and result["execution"]["completed"] == 1


@pytest.mark.parametrize("mode", ["zero", "deselected", "skipped", "missing_teardown",
    "wrong_invocation", "duplicate_collection", "duplicate_report", "wrong_file",
    "wrong_count", "malformed_junit", "no_manifest"])
def test_partial_or_mismatched_execution_never_qualifies(tmp_path, monkeypatch, mode):
    code, result = _invoke(tmp_path, monkeypatch, mode)
    assert code == 2 and result["pytest_exit_code"] == 0
    assert result["qualification"] == "NOT_QUALIFIED" and result["receipt_errors"]


def test_actual_pytest_failure_exit_is_preserved(tmp_path, monkeypatch):
    code, result = _invoke(tmp_path, monkeypatch, "failure", exit_code=1)
    assert code == result["pytest_exit_code"] == 1
    assert result["qualification"] == "NOT_QUALIFIED" and result["pytest_summary"]["failures"] == 1


def test_source_drift_cannot_attach_new_bytes_to_old_results(tmp_path, monkeypatch):
    snapshots = iter(({"fixture.py": "before"}, {"fixture.py": "after"}))
    monkeypatch.setattr(run_lane, "source_snapshot", lambda: next(snapshots))
    code, result = _invoke(tmp_path, monkeypatch)
    assert code == 2 and not result["source_unchanged"]
    assert result["tests_sha256"] == {"fixture.py": "before"}
    assert "SOURCE_CHANGED_DURING_EXECUTION" in result["receipt_errors"]


def test_report_collision_preserves_active_writer_then_releases(tmp_path, monkeypatch):
    report = tmp_path / "lane.json"
    report.write_text("active-writer-preimage")
    monkeypatch.setattr(run_lane.sys, "argv", ["h24", "--lane", "concurrency", "--report", str(report)])
    monkeypatch.setattr(run_lane.subprocess, "run", lambda *a, **k: pytest.fail("second invocation ran"))
    with run_lane.report_lease(report):
        assert run_lane.main() == 75
        assert report.read_text() == "active-writer-preimage"
    code, result = _invoke(tmp_path, monkeypatch)
    assert code == 0 and result["qualification"] == "PASS"


def test_timeout_cannot_reuse_old_success_or_disclose_exception(tmp_path, monkeypatch, capsys):
    report = tmp_path / "lane.json"
    report.write_text('{"qualification":"PASS"}')
    monkeypatch.setattr(run_lane.sys, "argv", ["h24", "--report", str(report)])

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(SECRET_SENTINEL, 120)

    monkeypatch.setattr(run_lane.subprocess, "run", timeout)
    assert run_lane.main() == 124
    result = json.loads(report.read_text())
    assert result["pytest_exit_code"] is None and result["qualification"] == "NOT_QUALIFIED"
    assert result["invocation_error"] == "PYTEST_TIMEOUT"
    assert SECRET_SENTINEL not in report.read_text() + capsys.readouterr().out


@pytest.mark.parametrize("case", ["network_clone", "global_config", "file_config", "hook_config",
    "remote_update", "external_diff", "executable", "outside_cwd", "clone_template"])
def test_git_exception_cannot_escape_disposable_fixture(tmp_path, case):
    guard = OfflineGuard()
    guard.root = tmp_path
    called = []
    guard._popen = lambda *a, **k: called.append((a, k))
    source = tmp_path / "source"
    source.mkdir()
    tails = {
        "network_clone": ["clone", "https://invalid.example/no-request", "target"],
        "global_config": ["config", "--global", "user.name", "inert"],
        "file_config": ["config", "--file", "/outside", "user.name", "inert"],
        "hook_config": ["config", "core.hooksPath", "/outside"],
        "remote_update": ["remote", "update"],
        "external_diff": ["diff", "--ext-diff"],
        "executable": ["status"], "outside_cwd": ["status"],
        "clone_template": ["clone", "--template=/outside", str(source), "target"],
    }
    kwargs = {"executable": "/not-executed"} if case == "executable" else {}
    root = tmp_path.parent if case == "outside_cwd" else tmp_path
    with pytest.raises(OfflineViolation):
        guard.popen(["git", "-C", str(root), *tails[case]], **kwargs)
    assert called == []


def test_local_git_has_no_inherited_hook_credential_or_transport_configuration(tmp_path):
    guard = OfflineGuard()
    guard.root = tmp_path
    called = []
    guard._popen = lambda *a, **k: called.append((a, k))
    guard.popen(["git", "-C", str(tmp_path), "config", "user.name", "inert"],
        env={"PATH": os.environ["PATH"], "GIT_CONFIG_COUNT": "1",
             "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": SECRET_SENTINEL,
             "GIT_SSH_COMMAND": SECRET_SENTINEL, "GIT_CONFIG_GLOBAL": SECRET_SENTINEL})
    (argv,), kw = called[0]
    assert "core.hooksPath=" + os.devnull in argv and "protocol.allow=never" in argv
    assert kw["env"]["GIT_CONFIG_GLOBAL"] == os.devnull
    assert kw["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert SECRET_SENTINEL not in json.dumps(called)


def test_collection_phase_has_no_process_or_network_exception(tmp_path):
    guard = OfflineGuard()
    called = []
    guard._popen = lambda *a, **k: called.append("process")
    guard._connect = lambda *a, **k: called.append("network")
    with pytest.raises(OfflineViolation):
        guard.popen(["git", "init", str(tmp_path / "repo")])
    with pytest.raises(OfflineViolation):
        guard.connect(SimpleNamespace(family=socket.AF_INET), ("invalid.example", 443))
    assert called == []
