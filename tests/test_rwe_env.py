"""RWE-P0: unit tests for the hash-locked worker environment task interface.

No network access and no real venv creation -- every test exercises the pure
selection/refusal/digest/parsing functions in ``scripts/rwe_env.py`` directly,
mocking ``subprocess.run`` wherever an external process would otherwise be
invoked. See ``docs/RWE_RUNBOOK.md`` for the live (network-using) walkthrough.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load_rwe_env():
    path = _ROOT / "scripts" / "rwe_env.py"
    spec = importlib.util.spec_from_file_location("rwe_env_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rwe = _load_rwe_env()


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

CI_YML_FIXTURE = """\
name: CI

on:
  pull_request:
  push:
    branches:
      - master

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Checkout pinned Macro engine
        uses: actions/checkout@v4
        with:
          repository: mastermindx-market-intelligence/macro
          ref: 256c757b3c4f0ec759571c29a30a71387d0a18f8
          path: vendor/macro_src
          sparse-checkout: |
            engine
            lib

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Run repository test gate
        run: python scripts/ci_pytest.py
"""


def _fake_repo(tmp_path: Path, *, lock_bytes: bytes | None = None,
                ci_yml: str | None = None) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'rwe-fixture'\nversion = '0.0.1'\n", encoding="utf-8"
    )
    if lock_bytes is not None:
        (tmp_path / "requirements").mkdir(parents=True, exist_ok=True)
        (tmp_path / "requirements" / "gate-macos-arm64-py312.lock").write_bytes(lock_bytes)
    if ci_yml is not None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True, exist_ok=True)
        (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# platform -> lock selection
# ---------------------------------------------------------------------------


def test_platform_locks_cover_darwin_arm64_and_linux_x86_64():
    assert rwe.PLATFORM_LOCKS[("darwin", "arm64")] == "gate-macos-arm64-py312.lock"
    assert rwe.PLATFORM_LOCKS[("linux", "x86_64")] == "gate-linux-x86_64-py312.lock"


def test_select_lock_finds_platform_lock(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    resolved = rwe.select_lock(root, platform_key=("darwin", "arm64"))
    assert resolved == root / "requirements" / "gate-macos-arm64-py312.lock"


def test_select_lock_refuses_when_absent(tmp_path):
    root = _fake_repo(tmp_path)  # no requirements/ at all
    with pytest.raises(rwe.EnvError, match="platform lock is absent"):
        rwe.select_lock(root, platform_key=("darwin", "arm64"))


def test_select_lock_refuses_unsupported_platform(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake\n")
    with pytest.raises(rwe.EnvError, match="no platform lock registered"):
        rwe.select_lock(root, platform_key=("windows", "x86_64"))


def test_select_lock_explicit_override(tmp_path):
    root = _fake_repo(tmp_path)
    custom = root / "custom.lock"
    custom.write_text("custom\n", encoding="utf-8")
    resolved = rwe.select_lock(root, lock_override="custom.lock", platform_key=("darwin", "arm64"))
    assert resolved == custom


def test_select_lock_explicit_override_missing_refuses(tmp_path):
    root = _fake_repo(tmp_path)
    with pytest.raises(rwe.EnvError, match="does not exist"):
        rwe.select_lock(root, lock_override="missing.lock", platform_key=("darwin", "arm64"))


def test_detect_platform_key_darwin_arm64(monkeypatch):
    monkeypatch.setattr(rwe.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(rwe.platform, "machine", lambda: "arm64")
    assert rwe.detect_platform_key() == ("darwin", "arm64")


def test_detect_platform_key_linux_x86_64(monkeypatch):
    monkeypatch.setattr(rwe.platform, "system", lambda: "Linux")
    monkeypatch.setattr(rwe.platform, "machine", lambda: "x86_64")
    assert rwe.detect_platform_key() == ("linux", "x86_64")


def test_detect_platform_key_refuses_unsupported_os(monkeypatch):
    monkeypatch.setattr(rwe.platform, "system", lambda: "Windows")
    monkeypatch.setattr(rwe.platform, "machine", lambda: "AMD64")
    with pytest.raises(rwe.EnvError, match="unsupported operating system"):
        rwe.detect_platform_key()


# ---------------------------------------------------------------------------
# interpreter-version refusal
# ---------------------------------------------------------------------------


class _FakeCompleted:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_require_supported_interpreter_accepts_cpython_312(monkeypatch):
    def fake_run(argv, **kwargs):
        return _FakeCompleted("CPython\n3 12\n")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)
    rwe.require_supported_interpreter("/fake/python3.12")  # must not raise


def test_require_supported_interpreter_refuses_wrong_minor(monkeypatch):
    def fake_run(argv, **kwargs):
        return _FakeCompleted("CPython\n3 14\n")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)
    with pytest.raises(rwe.EnvError, match="refusing unsupported interpreter"):
        rwe.require_supported_interpreter("/fake/python3.14")


def test_require_supported_interpreter_refuses_non_cpython(monkeypatch):
    def fake_run(argv, **kwargs):
        return _FakeCompleted("PyPy\n3 12\n")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)
    with pytest.raises(rwe.EnvError, match="refusing unsupported interpreter"):
        rwe.require_supported_interpreter("/fake/pypy3.12")


def test_probe_interpreter_refuses_missing_binary(monkeypatch):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError("no such file")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)
    with pytest.raises(rwe.EnvError, match="interpreter not found"):
        rwe.probe_interpreter("/no/such/python")


# ---------------------------------------------------------------------------
# environment_id determinism
# ---------------------------------------------------------------------------


def test_environment_id_deterministic_for_same_inputs():
    first = rwe.compute_environment_id(lock_sha256="abc123", os_name="darwin", arch="arm64")
    second = rwe.compute_environment_id(lock_sha256="abc123", os_name="darwin", arch="arm64")
    assert first == second
    assert len(first) == 16


def test_environment_id_changes_with_platform():
    darwin_id = rwe.compute_environment_id(lock_sha256="abc123", os_name="darwin", arch="arm64")
    linux_id = rwe.compute_environment_id(lock_sha256="abc123", os_name="linux", arch="x86_64")
    assert darwin_id != linux_id


def test_environment_id_changes_with_lock_digest():
    first = rwe.compute_environment_id(lock_sha256="abc123", os_name="darwin", arch="arm64")
    second = rwe.compute_environment_id(lock_sha256="def456", os_name="darwin", arch="arm64")
    assert first != second


def _build_test_receipt(root: Path, lock_path: Path) -> dict:
    return rwe.build_receipt(
        root=root,
        env_dir=root / "fake-env",
        lock_path=lock_path,
        os_name="darwin",
        arch="arm64",
        python_implementation="CPython",
        python_version="3.12.13",
        python_executable_class="homebrew",
        packages_installed={"count": 3, "freeze_sha256": "0" * 64},
        realized_at="2026-09-01T00:00:00Z",
        pip_check_ok=True,
    )


def test_receipt_environment_id_deterministic_across_builds(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"

    first = _build_test_receipt(root, lock_path)
    second = _build_test_receipt(root, lock_path)

    assert first["environment_id"] == second["environment_id"]
    assert first["environment_id"] == second["environment_id"]  # same-inputs stability
    assert first["definition"]["lock_sha256"] == second["definition"]["lock_sha256"]


def test_receipt_environment_id_changes_when_lock_content_changes(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"

    before = _build_test_receipt(root, lock_path)

    lock_path.write_bytes(b"fake-lock-content-v2-different\n")
    after = _build_test_receipt(root, lock_path)

    assert before["definition"]["lock_sha256"] != after["definition"]["lock_sha256"]
    assert before["environment_id"] != after["environment_id"]


def test_receipt_schema_and_definition_kind(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    receipt = _build_test_receipt(root, lock_path)

    assert receipt["schema"] == "mastermind.worker_environment/v1"
    assert receipt["definition"]["kind"] == "pip-hash-lock"
    assert receipt["definition"]["lock_path"] == "requirements/gate-macos-arm64-py312.lock"
    assert receipt["platform"]["python_executable_class"] == "homebrew"
    assert receipt["degraded"] == []


# ---------------------------------------------------------------------------
# receipt contains no forbidden keys/substrings
# ---------------------------------------------------------------------------

FORBIDDEN_SUBSTRINGS = ("TOKEN", "SECRET", "KEY=", "/Users/", "HOME")


def test_receipt_contains_no_forbidden_substrings(tmp_path):
    root = _fake_repo(
        tmp_path,
        lock_bytes=b"fake-lock-content-v1\n",
        ci_yml=CI_YML_FIXTURE,
    )
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    receipt = _build_test_receipt(root, lock_path)
    receipt["proof"]["gate"] = {
        "command": "<env>/bin/python -m pytest -q tests/test_rwe_env.py",
        "exit": 0,
        "discovered": 42,
        "seconds": 1.23,
    }

    serialized = json.dumps(receipt)
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in serialized, f"receipt leaked forbidden substring: {forbidden!r}"


def test_receipt_vendored_inputs_has_no_raw_repo_root_path(tmp_path):
    root = _fake_repo(
        tmp_path,
        lock_bytes=b"fake-lock-content-v1\n",
        ci_yml=CI_YML_FIXTURE,
    )
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    receipt = _build_test_receipt(root, lock_path)

    vendored = receipt["vendored_inputs"][0]
    assert vendored["repo"] == "mastermindx-market-intelligence/macro"
    assert vendored["ref"] == "256c757b3c4f0ec759571c29a30a71387d0a18f8"
    assert vendored["dest"] == "vendor/macro_src"
    assert vendored["present"] is False
    assert str(root) not in json.dumps(vendored)


# ---------------------------------------------------------------------------
# vendored macro ref parser (fixture copy of the ci.yml checkout step)
# ---------------------------------------------------------------------------


def test_parse_pinned_ref_reads_the_pinned_sha():
    ref = rwe.parse_pinned_ref(CI_YML_FIXTURE)
    assert ref == "256c757b3c4f0ec759571c29a30a71387d0a18f8"


def test_parse_pinned_ref_raises_when_repo_not_pinned():
    text = "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n"
    with pytest.raises(rwe.EnvError, match="no checkout step pins repository"):
        rwe.parse_pinned_ref(text)


def test_parse_pinned_ref_raises_when_ref_missing_in_step():
    text = (
        "jobs:\n  test:\n    steps:\n"
        "      - name: Checkout pinned Macro engine\n"
        "        uses: actions/checkout@v4\n"
        "        with:\n"
        "          repository: mastermindx-market-intelligence/macro\n"
        "          path: vendor/macro_src\n"
        "      - name: Next step\n"
        "        run: echo hi\n"
    )
    with pytest.raises(rwe.EnvError, match="no ref: within its checkout step"):
        rwe.parse_pinned_ref(text)


def test_read_pinned_ref_returns_none_when_workflow_absent(tmp_path):
    root = _fake_repo(tmp_path)  # no .github/workflows/ci.yml
    assert rwe.read_pinned_ref(root) is None


def test_read_pinned_ref_reads_from_real_repo_layout(tmp_path):
    root = _fake_repo(tmp_path, ci_yml=CI_YML_FIXTURE)
    assert rwe.read_pinned_ref(root) == "256c757b3c4f0ec759571c29a30a71387d0a18f8"


def test_checkout_command_for_includes_ref_and_sparse_paths():
    command = rwe.checkout_command_for("deadbeef")
    assert "git checkout deadbeef" in command
    assert "git sparse-checkout set engine lib" in command
    assert "mastermindx-market-intelligence/macro" in command


# ---------------------------------------------------------------------------
# path -> class derivation (never a raw path in the receipt)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/opt/homebrew/bin/python3.12", "homebrew"),
        ("/opt/homebrew/opt/python@3.12/bin/python3.12", "homebrew"),
        ("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12", "framework"),
        ("/opt/hostedtoolcache/Python/3.12.7/x64/bin/python3.12", "toolcache"),
        ("/usr/bin/python3", "other"),
    ],
)
def test_classify_python_executable_path(path, expected):
    assert rwe.classify_python_executable_path(path) == expected


# ---------------------------------------------------------------------------
# packages_installed reduction (count + digest, never the raw list)
# ---------------------------------------------------------------------------


def test_compute_packages_installed_counts_and_hashes():
    freeze_text = "zeta==2.0\nalpha==1.0\n\nalpha==1.0\n"
    result = rwe.compute_packages_installed(freeze_text)
    # blank lines dropped, sorted, but NOT de-duplicated (a real freeze
    # output has no duplicates; this only proves sort+join+hash behavior)
    assert result["count"] == 3
    import hashlib

    expected_digest = hashlib.sha256("alpha==1.0\nalpha==1.0\nzeta==2.0".encode("utf-8")).hexdigest()
    assert result["freeze_sha256"] == expected_digest


def test_compute_packages_installed_deterministic_regardless_of_input_order():
    a = rwe.compute_packages_installed("zeta==2.0\nalpha==1.0\n")
    b = rwe.compute_packages_installed("alpha==1.0\nzeta==2.0\n")
    assert a == b


# ---------------------------------------------------------------------------
# gate: refuses fail-closed on absent vendored input, no subprocess needed
# ---------------------------------------------------------------------------


def test_gate_refuses_full_gate_without_vendor(tmp_path, monkeypatch, capsys):
    import argparse

    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n", ci_yml=CI_YML_FIXTURE)
    env_dir = tmp_path / "fake-venv"
    (env_dir / "bin").mkdir(parents=True)
    (env_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    called = {"subprocess": False}

    def fake_run(*args, **kwargs):
        called["subprocess"] = True
        raise AssertionError("gate must refuse before invoking a subprocess")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    args = argparse.Namespace(root=str(root), env=str(env_dir), subset=None)
    rc = rwe.cmd_gate(args)

    assert rc == 2
    assert called["subprocess"] is False
    captured = capsys.readouterr()
    assert "git sparse-checkout set engine lib" in captured.err


def test_gate_refuses_when_no_interpreter_present(tmp_path):
    import argparse

    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    env_dir = tmp_path / "no-such-env"

    args = argparse.Namespace(root=str(root), env=str(env_dir), subset=None)
    rc = rwe.cmd_gate(args)
    assert rc == 2


# ---------------------------------------------------------------------------
# repo_root resolution
# ---------------------------------------------------------------------------


def test_repo_root_resolves_the_real_repository():
    root = rwe.repo_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "scripts" / "rwe_env.py").is_file()
