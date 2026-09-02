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


def test_select_lock_refuses_explicit_lock_outside_repo_root(tmp_path):
    # MINOR-2: validated and refused BEFORE any venv work, regardless of
    # whether the out-of-repo path even exists.
    root = _fake_repo(tmp_path)
    outside = tmp_path.parent / "outside.lock"
    outside.write_text("not really a lock\n", encoding="utf-8")
    with pytest.raises(rwe.EnvError, match="outside the repository root"):
        rwe.select_lock(root, lock_override=str(outside), platform_key=("darwin", "arm64"))


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


def _interpreter_probe_response(argv, *, implementation="CPython", minor_line="3 12", full_version="3.12.13"):
    """Canned response for one of rwe_env's own interpreter probes --
    ``probe_interpreter`` (implementation + major/minor) or
    ``probe_python_version_full`` (a single full-version line). Tests that
    let MAJOR-2's head-of-command check (and, on a receipt refresh, the
    full-version probe) succeed use this so real subprocess calls are never
    needed for a CPython 3.12 fixture path."""
    script = argv[2] if len(argv) > 2 else ""
    if "python_version()" in script:
        return _FakeCompleted(f"{full_version}\n")
    return _FakeCompleted(f"{implementation}\n{minor_line}\n")


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


def test_environment_id_changes_with_python_patch_version():
    # MAJOR-1: the FULL interpreter version (incl. patch) folds into the
    # id, so a patch-level interpreter bump is never silently identical.
    a = rwe.compute_environment_id(
        lock_sha256="abc123", os_name="darwin", arch="arm64", python_version="3.12.13"
    )
    b = rwe.compute_environment_id(
        lock_sha256="abc123", os_name="darwin", arch="arm64", python_version="3.12.14"
    )
    assert a != b


def _build_test_receipt(
    root: Path,
    lock_path: Path,
    *,
    pip_check_ok: bool = True,
    pip_check_detail: str = "",
) -> dict:
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
        pip_check_ok=pip_check_ok,
        pip_check_detail=pip_check_detail,
    )


def test_receipt_environment_id_deterministic_across_builds(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"

    first = _build_test_receipt(root, lock_path)
    second = _build_test_receipt(root, lock_path)

    assert first["environment_id"] == second["environment_id"]
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


def test_build_receipt_scrubs_and_truncates_pip_check_detail(tmp_path):
    # MINOR-6: a populated pip-check failure form -- long, and carrying an
    # absolute host path that must never survive into the receipt.
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"

    long_detail = (
        "package-foo 1.2.3 requires bar<2.0, but you have bar 2.5.0 which is "
        "incompatible.\n/Users/someoperator/mastermind/.venv/lib/python3.12/"
        "site-packages/bar-2.5.0.dist-info" + ("x" * 500)
    )
    receipt = _build_test_receipt(root, lock_path, pip_check_ok=False, pip_check_detail=long_detail)

    pip_check = receipt["proof"]["pip_check"]
    assert "/Users/" not in pip_check
    assert len(pip_check) <= 420


# ---------------------------------------------------------------------------
# receipt contains no forbidden keys/substrings
# ---------------------------------------------------------------------------

# Case-insensitive matching (MAJOR-3): "/home/" and "/root/" added alongside
# the existing macOS-home and generic secret-shaped tokens.
FORBIDDEN_SUBSTRINGS = ("TOKEN", "SECRET", "KEY=", "/Users/", "HOME", "/home/", "/root/")


def _assert_no_forbidden_substrings(serialized: str) -> None:
    lowered = serialized.lower()
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden.lower() not in lowered, f"receipt leaked forbidden substring: {forbidden!r}"


def test_gate_receipt_has_no_forbidden_substrings_for_out_of_repo_subset(
    tmp_path_factory, monkeypatch
):
    # MAJOR-3: generate the receipt VIA cmd_gate (not a hand-written
    # literal) with an absolute, out-of-repo --subset path, and assert the
    # actual serialized receipt is clean.
    import argparse

    root = _fake_repo(
        tmp_path_factory.mktemp("repo"),
        lock_bytes=b"fake-lock-content-v1\n",
        ci_yml=CI_YML_FIXTURE,
    )
    env_dir = root / "fake-venv"
    (env_dir / "bin").mkdir(parents=True)
    (env_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    outside_dir = tmp_path_factory.mktemp("outside-secret-home")
    subset_path = outside_dir / "test_leak.py"
    subset_path.write_text("def test_x():\n    assert True\n", encoding="utf-8")

    def fake_run(argv, **kwargs):
        if "-c" in argv:
            return _FakeCompleted("CPython\n3 12\n")
        return _FakeCompleted("1 passed in 0.01s\n", returncode=0)

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    args = argparse.Namespace(root=str(root), env=str(env_dir), subset=str(subset_path))
    rc = rwe.cmd_gate(args)
    assert rc == 0

    serialized = (env_dir / rwe.RECEIPT_FILENAME).read_text(encoding="utf-8")

    # the strongest, most direct proof: the actual absolute path never
    # appears verbatim, whatever tmp-dir naming this host happens to use.
    assert str(outside_dir) not in serialized
    assert str(subset_path) not in serialized
    _assert_no_forbidden_substrings(serialized)


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
# MAJOR-5: measured vendor ref (resolved_ref) + match against ci.yml's pin
# ---------------------------------------------------------------------------


def test_build_receipt_records_resolved_vendor_ref_and_match(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n", ci_yml=CI_YML_FIXTURE)
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"

    vendor_git = root / rwe.VENDOR_RELATIVE / ".git"
    vendor_git.mkdir(parents=True)

    def fake_run(argv, **kwargs):
        assert argv[:3] == ["git", "-C", str(root / rwe.VENDOR_RELATIVE)]
        return _FakeCompleted("256c757b3c4f0ec759571c29a30a71387d0a18f8\n", returncode=0)

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    receipt = _build_test_receipt(root, lock_path)
    vendored = receipt["vendored_inputs"][0]
    assert vendored["resolved_ref"] == "256c757b3c4f0ec759571c29a30a71387d0a18f8"
    assert vendored["match"] is True


def test_build_receipt_records_vendor_ref_mismatch(tmp_path, monkeypatch):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n", ci_yml=CI_YML_FIXTURE)
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"

    vendor_git = root / rwe.VENDOR_RELATIVE / ".git"
    vendor_git.mkdir(parents=True)

    def fake_run(argv, **kwargs):
        return _FakeCompleted("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n", returncode=0)

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    receipt = _build_test_receipt(root, lock_path)
    vendored = receipt["vendored_inputs"][0]
    assert vendored["resolved_ref"] == "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    assert vendored["match"] is False


def test_build_receipt_resolved_vendor_ref_null_when_unavailable(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n", ci_yml=CI_YML_FIXTURE)
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    # no vendor/.git present -- resolved_vendor_ref must not shell out at all
    receipt = _build_test_receipt(root, lock_path)
    vendored = receipt["vendored_inputs"][0]
    assert vendored["resolved_ref"] is None
    assert vendored["match"] is None


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

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if "-c" in argv:
            # the MAJOR-2 head-of-command interpreter probe is expected to
            # run and succeed; the refusal under test is the vendor-absent
            # one, further down.
            return _FakeCompleted("CPython\n3 12\n")
        raise AssertionError("gate must refuse before invoking the full test-gate subprocess")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    args = argparse.Namespace(root=str(root), env=str(env_dir), subset=None)
    rc = rwe.cmd_gate(args)

    assert rc == 2
    assert calls and all("-c" in call for call in calls)
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
# MAJOR-2: fail-open closed -- receipt/gate refuse on an unsupported
# interpreter, not just realize
# ---------------------------------------------------------------------------


def test_cmd_receipt_refuses_on_unsupported_interpreter(tmp_path, monkeypatch):
    import argparse

    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    env_dir = tmp_path / "fake-venv"
    (env_dir / "bin").mkdir(parents=True)
    (env_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_run(argv, **kwargs):
        return _FakeCompleted("CPython\n3 14\n")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    args = argparse.Namespace(root=str(root), env=str(env_dir))
    rc = rwe.cmd_receipt(args)
    assert rc == 2


def test_cmd_gate_refuses_on_unsupported_interpreter(tmp_path, monkeypatch):
    import argparse

    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    env_dir = tmp_path / "fake-venv"
    (env_dir / "bin").mkdir(parents=True)
    (env_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_run(argv, **kwargs):
        return _FakeCompleted("CPython\n3 14\n")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    args = argparse.Namespace(root=str(root), env=str(env_dir), subset=None)
    rc = rwe.cmd_gate(args)
    assert rc == 2


# ---------------------------------------------------------------------------
# MAJOR-1: receipt/gate refuse when the lock file's content no longer
# matches what a prior receipt recorded (drift after realize)
# ---------------------------------------------------------------------------


def _seed_receipt_with_lock_digest(env_dir: Path, lock_sha256: str) -> None:
    rwe.write_receipt(
        env_dir,
        {
            "schema": rwe.SCHEMA,
            "definition": {
                "kind": "pip-hash-lock",
                "pyproject_sha256": "0" * 64,
                "lock_path": "requirements/gate-macos-arm64-py312.lock",
                "lock_sha256": lock_sha256,
            },
            "platform": {"os": "darwin", "architecture": "arm64"},
            "degraded": [],
            "proof": {},
        },
    )


def test_check_lock_digest_matches_refuses_on_mismatch(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    existing = {"definition": {"lock_sha256": "0" * 64}}
    with pytest.raises(rwe.EnvError, match="lock content changed since this environment was realized"):
        rwe.check_lock_digest_matches(existing, lock_path)


def test_check_lock_digest_matches_noop_without_prior_definition(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    rwe.check_lock_digest_matches({}, lock_path)  # must not raise
    rwe.check_lock_digest_matches(None, lock_path)  # must not raise


def test_cmd_receipt_refuses_when_lock_content_changed_since_realize(tmp_path, monkeypatch, capsys):
    import argparse

    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n", ci_yml=CI_YML_FIXTURE)
    env_dir = tmp_path / "fake-venv"
    (env_dir / "bin").mkdir(parents=True)
    (env_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    original_digest = rwe.sha256_file(lock_path)
    _seed_receipt_with_lock_digest(env_dir, original_digest)

    # mutate the lock content after realize
    lock_path.write_bytes(b"fake-lock-content-v2-different\n")
    mutated_digest = rwe.sha256_file(lock_path)

    monkeypatch.setattr(rwe.subprocess, "run", lambda argv, **kwargs: _interpreter_probe_response(argv))

    args = argparse.Namespace(root=str(root), env=str(env_dir))
    rc = rwe.cmd_receipt(args)
    assert rc == 2

    captured = capsys.readouterr()
    assert original_digest in captured.err
    assert mutated_digest in captured.err


def test_cmd_gate_refuses_when_lock_content_changed_since_realize(tmp_path, monkeypatch, capsys):
    import argparse

    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n", ci_yml=CI_YML_FIXTURE)
    env_dir = tmp_path / "fake-venv"
    (env_dir / "bin").mkdir(parents=True)
    (env_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    original_digest = rwe.sha256_file(lock_path)
    _seed_receipt_with_lock_digest(env_dir, original_digest)

    lock_path.write_bytes(b"fake-lock-content-v2-different\n")

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if "-c" in argv:
            return _interpreter_probe_response(argv)
        raise AssertionError("gate must refuse before invoking the pytest subprocess")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    subset_path = root / "test_subset_fixture.py"
    subset_path.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    args = argparse.Namespace(root=str(root), env=str(env_dir), subset=str(subset_path))
    rc = rwe.cmd_gate(args)
    assert rc == 2
    assert calls and all("-c" in call for call in calls)
    captured = capsys.readouterr()
    assert original_digest in captured.err


# ---------------------------------------------------------------------------
# MAJOR-4: refuse a lock that is stale relative to the live pyproject.toml
# ---------------------------------------------------------------------------


def test_read_lock_pyproject_sha256_parses_header(tmp_path):
    lock_path = tmp_path / "fake.lock"
    lock_path.write_text("# pyproject.toml sha256: " + "a" * 64 + "\nfoo==1.0\n", encoding="utf-8")
    assert rwe.read_lock_pyproject_sha256(lock_path) == "a" * 64


def test_read_lock_pyproject_sha256_returns_none_without_header(tmp_path):
    lock_path = tmp_path / "fake.lock"
    lock_path.write_text("foo==1.0\n", encoding="utf-8")
    assert rwe.read_lock_pyproject_sha256(lock_path) is None


def test_check_pyproject_not_stale_is_warn_only_when_header_missing(tmp_path):
    root = _fake_repo(tmp_path, lock_bytes=b"no-header-just-packages==1.0\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    rwe.check_pyproject_not_stale(root, lock_path)  # must not raise


def test_check_pyproject_not_stale_refuses_on_mismatch(tmp_path):
    stale_header = ("# pyproject.toml sha256: " + "0" * 64 + "\n").encode("utf-8")
    root = _fake_repo(tmp_path, lock_bytes=stale_header + b"annotated-doc==0.0.5\n")
    lock_path = root / "requirements" / "gate-macos-arm64-py312.lock"
    with pytest.raises(rwe.EnvError, match="stale lock -- regenerate"):
        rwe.check_pyproject_not_stale(root, lock_path)


def test_cmd_realize_refuses_stale_lock_before_any_subprocess(tmp_path, monkeypatch):
    import argparse

    stale_header = ("# pyproject.toml sha256: " + "0" * 64 + "\n").encode("utf-8")
    root = _fake_repo(tmp_path, lock_bytes=stale_header + b"annotated-doc==0.0.5\n")

    called = {"subprocess": False}

    def fake_run(*a, **k):
        called["subprocess"] = True
        raise AssertionError("realize must refuse before any subprocess call")

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)
    monkeypatch.setattr(rwe, "detect_platform_key", lambda: ("darwin", "arm64"))

    args = argparse.Namespace(
        dest=str(tmp_path / "venv"), lock=None, python=None, force=False, root=str(root)
    )
    rc = rwe.cmd_realize(args)
    assert rc == 2
    assert called["subprocess"] is False


# ---------------------------------------------------------------------------
# MINOR-1: sum every category on the pytest summary line; "0 passed" is a
# true zero, never dropped by an `or` chain
# ---------------------------------------------------------------------------


def test_parse_discovered_sums_all_summary_categories():
    assert rwe._parse_discovered("1 failed, 36 passed in 1.23s\n") == 37


def test_parse_discovered_zero_passed_stays_zero():
    assert rwe._parse_discovered("0 passed in 0.01s\n") == 0


def test_gate_discovered_count_prefers_stdout_over_stderr_even_when_stdout_is_zero(
    tmp_path, monkeypatch
):
    import argparse

    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n")
    env_dir = tmp_path / "fake-venv"
    (env_dir / "bin").mkdir(parents=True)
    (env_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_run(argv, **kwargs):
        if "-c" in argv:
            return _interpreter_probe_response(argv)
        return _FakeCompleted(
            "0 passed in 0.00s\n", returncode=0, stderr="5 passed (unrelated stderr noise)\n"
        )

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    subset_path = root / "test_subset_fixture.py"
    subset_path.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    args = argparse.Namespace(root=str(root), env=str(env_dir), subset=str(subset_path))
    rc = rwe.cmd_gate(args)
    assert rc == 0

    receipt = json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text(encoding="utf-8"))
    assert receipt["proof"]["gate"]["discovered"] == 0


# ---------------------------------------------------------------------------
# MINOR-3: a successful full gate clears a stale vendor-absent degraded flag
# ---------------------------------------------------------------------------


def test_gate_clears_vendor_absent_degraded_flag_on_successful_full_gate(tmp_path, monkeypatch):
    import argparse

    root = _fake_repo(tmp_path, lock_bytes=b"fake-lock-content-v1\n", ci_yml=CI_YML_FIXTURE)
    vendor_dir = root / rwe.VENDOR_RELATIVE
    vendor_dir.mkdir(parents=True)
    (vendor_dir / "marker").write_text("present\n", encoding="utf-8")

    env_dir = root / "fake-venv"
    (env_dir / "bin").mkdir(parents=True)
    (env_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    rwe.write_receipt(
        env_dir,
        {"schema": rwe.SCHEMA, "degraded": ["full_gate_unavailable:vendor_absent"], "proof": {}},
    )

    def fake_run(argv, **kwargs):
        if "-c" in argv:
            return _interpreter_probe_response(argv)
        return _FakeCompleted("36 passed in 1.0s\n", returncode=0)

    monkeypatch.setattr(rwe.subprocess, "run", fake_run)

    args = argparse.Namespace(root=str(root), env=str(env_dir), subset=None)
    rc = rwe.cmd_gate(args)
    assert rc == 0

    receipt = json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text(encoding="utf-8"))
    assert "full_gate_unavailable:vendor_absent" not in receipt["degraded"]


# ---------------------------------------------------------------------------
# repo_root resolution
# ---------------------------------------------------------------------------


def test_repo_root_resolves_the_real_repository():
    root = rwe.repo_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "scripts" / "rwe_env.py").is_file()
