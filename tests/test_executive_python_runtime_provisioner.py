"""Static, Linux-safe checks for the reviewed macOS Python provisioner."""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "executive_os"
SCRIPT = OPS / "provision-python-runtime.sh"
INSTALL = OPS / "install.sh"
RUNBOOK = OPS / "HOST_PREREQUISITES.md"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_python_runtime_provisioner_is_executable_and_syntax_valid() -> None:
    assert stat.S_IMODE(SCRIPT.stat().st_mode) & 0o111
    completed = subprocess.run(
        ["/bin/bash", "-n", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_python_runtime_provisioner_pins_official_psf_package() -> None:
    source = _source()
    assert 'PYTHON_VERSION="3.12.10"' in source
    assert (
        'PYTHON_PACKAGE_URL="https://www.python.org/ftp/python/3.12.10/'
        'python-3.12.10-macos11.pkg"'
    ) in source
    assert (
        'PYTHON_PACKAGE_SHA256="8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4"'
        in source
    )
    assert 'PYTHON_TEAM_ID="BMM5U3QVKW"' in source
    assert (
        'PYTHON_INSTALLER_CERT_SHA256="C1A8FB2B4668D1BA221BC2A84DE43EDAA715C8FB85E320F478861ACECE5B8588"'
        in source
    )
    assert (
        'PYTHON_BINARY_SHA256="d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"'
        in source
    )
    assert (
        'PYTHON_FRAMEWORK_SHA256="14e61fb22a897d238248dfd8fe3b472b4541338c293368b4747803055b8bb3aa"'
        in source
    )
    assert "/usr/sbin/pkgutil --check-signature" in source
    assert "Notarization: trusted by the Apple notary service" in source
    assert "/usr/sbin/spctl -a -t install -vv" in source
    assert "/usr/sbin/pkgutil --expand-full" in source
    assert "/usr/sbin/installer" not in source


def test_python_runtime_provisioner_never_executes_mutable_inputs_as_root() -> None:
    source = _source()
    package_copy = '/usr/bin/ditto --noqtn "$PACKAGE_SOURCE" "$PACKAGE_PATH"'
    assert package_copy in source
    assert source.index(package_copy) < source.index("OBSERVED_PACKAGE_SHA256=")
    assert source.index("runtime_tree_static_checks \"$CANDIDATE\"") < source.index(
        '/bin/mv "$INSTALL_STAGE" "$RUNTIME_ROOT"'
    )
    assert source.index("runtime_tree_static_checks \"$INSTALL_STAGE\"") < source.index(
        '/bin/mv "$INSTALL_STAGE" "$RUNTIME_ROOT"'
    )


def test_python_runtime_provisioner_archives_and_rolls_back_without_deletion() -> None:
    source = _source()
    assert 'ARCHIVE_ROOT="$SYSTEM_ROOT/python-archive"' in source
    assert 'PRIOR_ARCHIVE="$ARCHIVE_ROOT/prior-$PYTHON_SERIES-' in source
    assert '/bin/mv "$RUNTIME_ROOT" "$PRIOR_ARCHIVE"' in source
    assert '/bin/mv "$PRIOR_ARCHIVE" "$RUNTIME_ROOT"' in source
    assert 'PRIOR_MOVED="true"' in source
    assert 'CANDIDATE_INSTALLED="true"' in source
    assert "SWAP_STARTED" not in source
    assert '/bin/mv "$RECEIPT_PATH" "$PRIOR_RECEIPT_ARCHIVE"' in source
    assert '/bin/mv "$PRIOR_RECEIPT_ARCHIVE" "$RECEIPT_PATH"' in source
    assert "archive_partial_and_restore_prior" in source
    assert 'trap cleanup EXIT' in source
    assert "trap 'interrupted 1' HUP" in source
    assert "trap 'interrupted 2' INT" in source
    assert "trap 'interrupted 15' TERM" in source
    assert "exit $((128 + signum))" in source
    assert 'rm -rf -- "$RUNTIME_ROOT"' not in source
    assert 'rm -rf -- "$PRIOR_ARCHIVE"' not in source


def test_runtime_and_installer_bind_every_live_origin_to_attested_root() -> None:
    for source in (_source(), INSTALL.read_text(encoding="utf-8")):
        assert "sys.prefix" in source
        assert "sys.base_prefix" in source
        assert 'sysconfig.get_path("stdlib")' in source
        assert "_ctypes" in source
        assert "_sqlite3" in source
        assert "_ssl" in source
        assert "ctypes.pythonapi.Py_GetVersion" in source
        assert "libc.dladdr" in source
        assert "loaded Python framework" in source
        assert "resolve(strict=True)" in source


def test_runtime_provisioner_hardens_ancestors_tree_and_symlinks() -> None:
    source = _source()
    assert 'FRAMEWORK_PARENT="/Library/Frameworks/Python.framework"' in source
    assert 'RUNTIME_ROOT="$VERSIONS_ROOT/$PYTHON_SERIES"' in source
    assert 'ensure_root_directory "$FRAMEWORK_PARENT" 0755' in source
    assert 'ensure_root_directory "$VERSIONS_ROOT" 0755' in source
    assert '/usr/sbin/chown root:wheel "$path"' in source
    assert '/bin/chmod "$mode" "$path"' in source
    assert '/usr/bin/find "$root" ! -user root' in source
    assert '/usr/bin/find "$root" ! -group wheel' in source
    assert '/usr/bin/find "$root" -perm +022' in source
    assert '/usr/bin/codesign --verify --deep --strict "$root"' in source
    assert '/usr/bin/readlink -f "$link"' in source
    assert '"$root"|"$root"/*' in source
    assert "TeamIdentifier" in source


def test_runtime_replacement_is_staged_and_quiescent_before_adjacent_swap() -> None:
    source = _source()
    stage_copy = '/usr/bin/ditto --noqtn "$CANDIDATE" "$INSTALL_STAGE"'
    stage_check = 'runtime_tree_static_checks "$INSTALL_STAGE"'
    prior_move = '/bin/mv "$RUNTIME_ROOT" "$PRIOR_ARCHIVE"'
    candidate_move = '/bin/mv "$INSTALL_STAGE" "$RUNTIME_ROOT"'
    final_census = source.rindex("assert_runtime_not_in_use", 0, source.index(prior_move))
    assert source.index(stage_copy) < source.index(stage_check) < final_census
    assert final_census < source.index(prior_move) < source.index(candidate_move)
    assert source.rindex('PRIOR_MOVED="true"') < source.index(prior_move)
    assert source.rindex('PRIOR_RECEIPT_MOVED="true"') < source.index(
        '/bin/mv "$RECEIPT_PATH" "$PRIOR_RECEIPT_ARCHIVE"'
    )
    assert source.rindex('CANDIDATE_INSTALLED="true"') < source.index(candidate_move)
    assert source.rindex('NEW_RECEIPT_INSTALLED="true"') < source.index(
        '/bin/mv "$RECEIPT_TEMP" "$RECEIPT_PATH"'
    )
    assert "/usr/sbin/lsof -t" in source
    assert "close Python-based apps and retry" in source


def test_runtime_receipt_is_exact_transactional_and_installer_required() -> None:
    source = _source()
    install = INSTALL.read_text(encoding="utf-8")
    for token in (
        "mastermind.executive_python_runtime/v1",
        "prior_runtime_receipt_archive",
        '"0:0:400:1"',
        "python_framework_sha256",
    ):
        assert token in source
        assert token in install
    assert "verify_runtime_receipt" in source
    assert 'PINNED_PYTHON_RUNTIME_ROOT="/Library/Frameworks/Python.framework/Versions/3.12"' in install
    assert 'sys.version.split()[0] == "3.12.10"' in install
    assert "Python runtime ancestor" in install
    assert "Python runtime provenance receipt validation failed" in install


def test_runtime_provisioner_verify_only_is_non_mutating_before_exit() -> None:
    source = _source()
    verify_branch = source.split('if [ "$VERIFY_ONLY" = "true" ]; then', 1)[1].split(
        "fi", 1
    )[0]
    assert "verify_installed_runtime" in verify_branch
    assert "install -d" not in verify_branch
    assert "curl" not in verify_branch
    assert "mv " not in verify_branch
    assert "rm " not in verify_branch


def test_runbook_defers_every_privileged_action_until_exact_merged_master() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    stage_one, stage_two = runbook.split(
        "## Stage 2 — exact `origin/master` provisioning, install, and acceptance",
        1,
    )
    assert "sudo " not in stage_one
    assert "REPOSITORY=/absolute/path/to/Mastermind" in stage_two
    assert 'OPERATOR_USER="$(/usr/bin/id -un)"' in stage_two
    assert "set -euo pipefail" in stage_two
    assert 'test "$OPERATOR_USER" != root' in stage_two
    assert "merge-base --is-ancestor" in stage_two
    assert "/usr/bin/mktemp -d /private/tmp/mastermind-phase1c-acceptance.XXXXXX" in stage_two
    assert "provision-python-runtime.sh" in stage_two and "--verify-only" in stage_two
