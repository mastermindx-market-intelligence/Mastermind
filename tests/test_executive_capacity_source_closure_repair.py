from __future__ import annotations

import hashlib
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "repair-capacity-source-closure.sh"
BOOTSTRAP = ROOT / "ops" / "executive_os" / "bootstrap-capacity-source-closure.sh"
RUNBOOK = ROOT / "ops" / "executive_os" / "HOST_PREREQUISITES.md"
DESIGN = (
    ROOT
    / "docs/superpowers/specs/2026-08-27-executive-capacity-cf2-h0-source-closure-repair-design.md"
)
PLAN = (
    ROOT
    / "docs/superpowers/plans/2026-08-27-executive-capacity-cf2-h0-source-closure-repair.md"
)
INVALID = (64, "INVALID_INVOCATION\n", "")

REPAIR_CARRIER_PATHS = (
    "ops/executive_os/repair-capacity-source-closure.sh",
    "ops/executive_os/capacity_host_artifacts.py",
    "ops/executive_os/capacity_source_contract.py",
    "ops/executive_os/provider_worker_slots.py",
    "ops/executive_os/provider_identity_policy.py",
)


def _run(*arguments: str, environment: dict[str, str] | None = None) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["/bin/bash", str(SCRIPT), *arguments],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _run_script(
    script: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["/bin/bash", str(script), *arguments],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env={
            "HOME": "/var/empty",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        },
    )
    return completed.stdout.strip()


def _bootstrap_fixture(
    tmp_path: Path,
    *,
    repair_exit: int = 0,
    repair_output: str = "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED",
    mid_carrier_marker: Path | None = None,
    child_terminated_marker: Path | None = None,
    post_signal_sentinel: Path | None = None,
) -> tuple[Path, str, Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")

    executive_os = repository / "ops" / "executive_os"
    executive_os.mkdir(parents=True)
    fake_repair = executive_os / "repair-capacity-source-closure.sh"
    repair_body = (
        f"/usr/bin/printf '%s\\n' {shlex.quote(repair_output)}; "
        f"exit {repair_exit}"
    )
    if mid_carrier_marker is not None:
        assert child_terminated_marker is not None
        assert post_signal_sentinel is not None
        root_namespace = tmp_path / "bootstrap-root/mastermind-h0-root-carrier"
        repair_body = f"""
    on_signal() {{
      if [ -d {shlex.quote(str(root_namespace))} ]; then
        /usr/bin/touch {shlex.quote(str(child_terminated_marker))}
      fi
      exit 143
    }}
    trap on_signal HUP INT TERM
    (
      trap '' HUP INT TERM
      /bin/sleep 3
      /usr/bin/touch {shlex.quote(str(post_signal_sentinel))}
    ) &
    descendant_pid=$!
    /usr/bin/printf '%s %s\\n' "$$" "$descendant_pid" \
      > {shlex.quote(str(mid_carrier_marker))}
    wait "$descendant_pid"
    {repair_body}
"""
    fake_repair.write_text(
        f"""#!/bin/bash
set -u
case "$1" in
  repair) {repair_body} ;;
  verify-only) /usr/bin/printf '%s\\n' H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED ;;
  *) exit 64 ;;
esac
""",
        encoding="utf-8",
    )
    fake_repair.chmod(0o755)
    for relative in REPAIR_CARRIER_PATHS[1:]:
        destination = repository / relative
        destination.write_bytes((ROOT / relative).read_bytes())
        destination.chmod(0o644)
    _git(repository, "add", *REPAIR_CARRIER_PATHS)
    _git(repository, "commit", "-qm", "fixture carrier")
    commit = _git(repository, "rev-parse", "HEAD")
    bundle = tmp_path / "repair.bundle"
    _git(repository, "bundle", "create", str(bundle), "HEAD")

    macro_transport = tmp_path / "macro-transport.zip"
    macro_transport.write_bytes(b"inert macro transport\n")
    return repository, commit, bundle, macro_transport


def _bootstrap_arguments(
    commit: str,
    bundle: Path,
    macro_transport: Path,
    *,
    operator_user: str | None = None,
) -> tuple[str, ...]:
    if operator_user is None:
        operator_user = subprocess.run(
            ["/usr/bin/id", "-un"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    return (
        commit,
        operator_user,
        str(macro_transport),
        hashlib.sha256(macro_transport.read_bytes()).hexdigest(),
        str(bundle),
        hashlib.sha256(bundle.read_bytes()).hexdigest(),
    )


def _run_bootstrap(
    *arguments: str,
    environment: dict[str, str],
    stdin: str = "",
) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["/bin/bash", str(BOOTSTRAP), *arguments],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _bootstrap_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    test_root = tmp_path / "bootstrap-root"
    test_root.mkdir()
    environment = dict(os.environ)
    environment["MMX_H0_BOOTSTRAP_TEST_ROOT"] = str(test_root)
    return environment, test_root / "mastermind-h0-root-carrier"


def test_bootstrap_refuses_root_identity_before_bundle_or_namespace_observation(
    tmp_path: Path,
) -> None:
    _repository, commit, bundle_target, macro_transport = _bootstrap_fixture(tmp_path)
    bundle = tmp_path / "operator-bundle-symlink"
    bundle.symlink_to(bundle_target)
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment["MMX_H0_BOOTSTRAP_TEST_CALLER_UID"] = "0"

    result = _run_bootstrap(
        *_bootstrap_arguments(commit, bundle, macro_transport),
        environment=environment,
    )

    assert result == INVALID
    assert bundle.is_symlink()
    assert not root_namespace.exists()


def test_bootstrap_refuses_operator_identity_mismatch_before_bundle_observation(
    tmp_path: Path,
) -> None:
    _repository, commit, bundle_target, macro_transport = _bootstrap_fixture(tmp_path)
    bundle = tmp_path / "operator-bundle-symlink"
    bundle.symlink_to(bundle_target)
    environment, root_namespace = _bootstrap_environment(tmp_path)

    result = _run_bootstrap(
        *_bootstrap_arguments(
            commit,
            bundle,
            macro_transport,
            operator_user="definitely_not_current_user",
        ),
        environment=environment,
    )

    assert result == INVALID
    assert bundle.is_symlink()
    assert not root_namespace.exists()


def test_exact_disposable_carrier_inventory_runs_under_isolated_apple_python(
    tmp_path: Path,
) -> None:
    carrier = tmp_path / "carrier"
    for relative in REPAIR_CARRIER_PATHS:
        destination = carrier / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            "-S",
            "-B",
            str(carrier / "ops/executive_os/capacity_host_artifacts.py"),
            "--help",
        ],
        cwd="/",
        text=True,
        capture_output=True,
        check=False,
        env={
            "HOME": "/var/empty",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        },
    )
    assert (completed.returncode, completed.stderr) == (0, "")
    assert "Build or inspect inert CF2-H0 artifacts" in completed.stdout


def test_invalid_bundle_cannot_interpret_hostile_stdin_before_authentication(
    tmp_path: Path,
) -> None:
    environment, root_namespace = _bootstrap_environment(tmp_path)
    bundle = tmp_path / "malformed.bundle"
    bundle.write_bytes(b"not a git bundle\n")
    macro_transport = tmp_path / "macro.zip"
    macro_transport.write_bytes(b"inert\n")
    sentinel = tmp_path / "hostile-stdin-ran"
    hostile_stdin = f"/usr/bin/touch {sentinel}\n"

    result = _run_bootstrap(
        *_bootstrap_arguments("d" * 40, bundle, macro_transport),
        environment=environment,
        stdin=hostile_stdin,
    )

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert not sentinel.exists()
    assert not root_namespace.exists()


def test_symlink_bundle_refuses_without_touching_target(
    tmp_path: Path,
) -> None:
    environment, root_namespace = _bootstrap_environment(tmp_path)
    target = tmp_path / "bundle-target"
    target.write_bytes(b"inert target\n")
    target.chmod(0o640)
    before = target.stat()
    before_xattrs = subprocess.run(
        ["/usr/bin/xattr", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    before_acl = subprocess.run(
        ["/bin/ls", "-lde", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    bundle = tmp_path / "repair.bundle"
    bundle.symlink_to(target)
    macro_transport = tmp_path / "macro.zip"
    macro_transport.write_bytes(b"inert\n")

    result = _run_bootstrap(
        *_bootstrap_arguments("d" * 40, bundle, macro_transport),
        environment=environment,
    )
    after = target.stat()

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert target.read_bytes() == b"inert target\n"
    assert (
        after.st_dev,
        after.st_ino,
        after.st_uid,
        after.st_gid,
        after.st_mode,
        getattr(after, "st_flags", 0),
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) == (
        before.st_dev,
        before.st_ino,
        before.st_uid,
        before.st_gid,
        before.st_mode,
        getattr(before, "st_flags", 0),
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    assert subprocess.run(
        ["/usr/bin/xattr", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == before_xattrs
    assert subprocess.run(
        ["/bin/ls", "-lde", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == before_acl
    assert not root_namespace.exists()


def test_exact_bundle_runs_three_passes_and_removes_root_namespace(
    tmp_path: Path,
) -> None:
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(tmp_path)
    environment, root_namespace = _bootstrap_environment(tmp_path)

    result = _run_bootstrap(
        *_bootstrap_arguments(commit, bundle, macro_transport),
        environment=environment,
    )

    assert result == (
        0,
        "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED\n"
        "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n"
        "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n",
        "",
    )
    assert not root_namespace.exists()


def test_cleanup_failure_cannot_emit_clean_success(tmp_path: Path) -> None:
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(tmp_path)
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment["MMX_H0_BOOTSTRAP_TEST_CLEANUP_FAIL"] = "1"

    result = _run_bootstrap(
        *_bootstrap_arguments(commit, bundle, macro_transport),
        environment=environment,
    )

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert not root_namespace.exists()


@pytest.mark.parametrize(
    "repair_exit,repair_output",
    (
        (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED"),
        (70, "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER"),
        (75, "H0_LOCK_HELD"),
    ),
)
def test_bootstrap_preserves_authenticated_carrier_primary_failure(
    tmp_path: Path, repair_exit: int, repair_output: str
) -> None:
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(
        tmp_path,
        repair_exit=repair_exit,
        repair_output=repair_output,
    )
    environment, root_namespace = _bootstrap_environment(tmp_path)
    environment["MMX_H0_BOOTSTRAP_TEST_CLEANUP_FAIL"] = "1"

    result = _run_bootstrap(
        *_bootstrap_arguments(commit, bundle, macro_transport),
        environment=environment,
    )

    assert result == (repair_exit, f"{repair_output}\n", "")
    assert not root_namespace.exists()


def test_preexisting_fixed_namespace_refuses_without_deleting_unknown_residue(
    tmp_path: Path,
) -> None:
    environment, root_namespace = _bootstrap_environment(tmp_path)
    root_namespace.mkdir()
    residue = root_namespace / "unknown-residue"
    residue.write_bytes(b"must remain\n")
    bundle = tmp_path / "malformed.bundle"
    bundle.write_bytes(b"inert until namespace refusal\n")
    macro_transport = tmp_path / "macro.zip"
    macro_transport.write_bytes(b"inert\n")

    result = _run_bootstrap(
        *_bootstrap_arguments("d" * 40, bundle, macro_transport),
        environment=environment,
    )

    assert result == (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")
    assert residue.read_bytes() == b"must remain\n"


@pytest.mark.parametrize("interrupt", (signal.SIGHUP, signal.SIGINT, signal.SIGTERM))
def test_signal_removes_exclusive_root_namespace(
    tmp_path: Path, interrupt: signal.Signals
) -> None:
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(tmp_path)
    environment, root_namespace = _bootstrap_environment(tmp_path)
    marker = tmp_path / "namespace-ready"
    environment["MMX_H0_BOOTSTRAP_TEST_PAUSE_MARKER"] = str(marker)
    process = subprocess.Popen(
        [
            "/bin/bash",
            str(BOOTSTRAP),
            *_bootstrap_arguments(commit, bundle, macro_transport),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.01)
    assert marker.exists(), process.communicate(timeout=1)
    process.send_signal(interrupt)
    stdout, stderr = process.communicate(timeout=5)

    assert (process.returncode, stdout, stderr) == (
        70,
        "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n",
        "",
    )
    assert not root_namespace.exists()


@pytest.mark.parametrize("interrupt", (signal.SIGHUP, signal.SIGINT, signal.SIGTERM))
def test_signal_to_bootstrap_pid_terminates_active_carrier_tree_before_cleanup(
    tmp_path: Path, interrupt: signal.Signals
) -> None:
    carrier_started = tmp_path / "carrier-started"
    child_terminated = tmp_path / "child-terminated-before-cleanup"
    post_signal_sentinel = tmp_path / "post-signal-mutation"
    _repository, commit, bundle, macro_transport = _bootstrap_fixture(
        tmp_path,
        mid_carrier_marker=carrier_started,
        child_terminated_marker=child_terminated,
        post_signal_sentinel=post_signal_sentinel,
    )
    environment, root_namespace = _bootstrap_environment(tmp_path)
    process = subprocess.Popen(
        [
            "/bin/bash",
            str(BOOTSTRAP),
            *_bootstrap_arguments(commit, bundle, macro_transport),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not carrier_started.exists():
        time.sleep(0.01)
    assert carrier_started.exists(), process.communicate(timeout=1)
    carrier_pid, descendant_pid = (
        int(value) for value in carrier_started.read_text(encoding="utf-8").split()
    )

    process.send_signal(interrupt)
    stdout, stderr = process.communicate(timeout=10)

    assert (process.returncode, stdout, stderr) == (
        70,
        "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n",
        "",
    )
    assert child_terminated.exists()
    assert not root_namespace.exists()
    for child_pid in (carrier_pid, descendant_pid):
        observed_process = subprocess.run(
            ["/bin/ps", "-p", str(child_pid), "-o", "pid="],
            check=False,
            capture_output=True,
            text=True,
        )
        assert (observed_process.returncode, observed_process.stdout) == (1, "")
    time.sleep(3.2)
    assert not post_signal_sentinel.exists()


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--help",),
        ("repair",),
        ("verify-only",),
        ("VERIFY-ONLY", "--expected-source-closure-repair-commit", "d" * 40),
        ("verify-only", "--expected-source-closure-repair-commit", "D" * 40),
        ("verify-only", "--expected-source-closure-repair-commit", "d" * 40, "extra"),
        (
            "repair",
            "--operator-user",
            "operator",
            "--expected-source-closure-repair-commit",
            "d" * 40,
            "--macro-transport",
            "/tmp/carrier.zip",
            "--macro-transport-sha256",
            "a" * 64,
        ),
        (
            "repair",
            "--expected-source-closure-repair-commit",
            "d" * 40,
            "--operator-user",
            "operator",
            "--macro-transport",
            "relative.zip",
            "--macro-transport-sha256",
            "a" * 64,
        ),
    ),
)
def test_invalid_invocations_are_closed_before_host_adapter_read(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    unreadable = tmp_path / "must-not-read"
    environment = dict(os.environ)
    environment["MMX_CAPACITY_REPAIR_TEST_ROOT"] = str(unreadable)
    assert _run(*arguments, environment=environment) == INVALID
    assert not unreadable.exists()


def test_exact_cli_forms_cross_validation_before_preflight(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment["MMX_CAPACITY_REPAIR_TEST_ROOT"] = str(tmp_path / "host")
    repair = _run(
        "repair",
        "--expected-source-closure-repair-commit",
        "d" * 40,
        "--operator-user",
        "operator",
        "--macro-transport",
        "/tmp/carrier.zip",
        "--macro-transport-sha256",
        "a" * 64,
        environment=environment,
    )
    verify = _run(
        "verify-only",
        "--expected-source-closure-repair-commit",
        "d" * 40,
        environment=environment,
    )
    assert repair[0] != 64
    assert verify[0] != 64


def test_runbook_freezes_alternative_b_build_and_one_offline_native_ceremony() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())
    required = (
        "Alternative B",
        "dcdd939c45b23abce5ba04f95e330ac914a3904b",
        "mastermind.capacity_source_transport/v2",
        "build-source-transport-v2",
        "MACRO_TRANSPORT_SHA256",
        "REPAIR_MERGE_SHA='<40-lower-hex-protected-repair-merge-sha>'",
        "checkout --detach",
        "one native administrator dialog",
        "bootstrap-capacity-source-closure.sh",
        "root never receives a shell",
        "/private/var/root/mastermind-h0-root-carrier",
        "provider_worker_slots.py",
        "provider_identity_policy.py",
        "2b05a61f54c876f00c3f03d51bd9df72de4a73e76bc06b2e7bc13a11ee203d60",
        "02886a6c79f22534ac24234d8adb3224329976342393988541c2a50d7e297f29",
        "51c58d18869663d90c593e416c7fc7833b3725378870f576abd3647f62f40830",
        "981e880ba7d21a0003fe2dd8322c5793f2643b815d094374dd6fad3fed31e453",
        "18d83b0e164ac2e917d84c01fe1d53fc5c1ce0c33ac9580f11d684e16e495093",
        "7efba70495cbbf8bcad0c4e47e894a23f4b1618756d8c3e23cae85ad6b7250ba",
        "35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650",
        "/Library/Application Support/MastermindExecutive/locks/cf2-h0.lock",
        "one durable repair intent",
        "archive-only",
        "last semantic filesystem mutation",
    )
    for value in required:
        assert value in normalized

    bootstrap = """/bin/bash "$REPAIR_CHECKOUT/ops/executive_os/bootstrap-capacity-source-closure.sh" \\
  "$REPAIR_MERGE_SHA" "$OPERATOR_USER" "$MACRO_TRANSPORT" "$MACRO_TRANSPORT_SHA256" \\
  "$REPAIR_CARRIER" "$REPAIR_CARRIER_SHA256"""
    assert bootstrap in runbook
    for forbidden in ("/bin/bash -s", "<<'H0_SOURCE_REPAIR'", "one root shell"):
        assert forbidden not in runbook


def test_native_ceremony_materializes_one_digest_bound_root_created_carrier() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())
    required = (
        "git bundle create",
        "REPAIR_CARRIER_SHA256",
        "inert exact-commit carrier",
        "/usr/bin/env -i",
        "GIT_CONFIG_NOSYSTEM=1",
        "GIT_CONFIG_GLOBAL=/dev/null",
        "GIT_CONFIG_LOCAL=/dev/null",
        "GIT_ATTR_NOSYSTEM=1",
        "GIT_NO_REPLACE_OBJECTS=1",
        "GIT_EXTERNAL_DIFF=/usr/bin/false",
        "GIT_ALLOW_PROTOCOL=file",
        "protocol.allow=never",
        "protocol.file.allow=always",
        "core.hooksPath=/dev/null",
        "core.fsmonitor=false",
        "core.attributesFile=/dev/null",
        "--no-ext-diff --no-textconv",
        "exclusive fixed literal",
        "Git blob OID",
        "buffered until the fixed root namespace has been removed",
        "No installed release executable or Python module is launched",
    )
    for value in required:
        assert value in normalized
    forbidden = (
        'cd "$REPAIR_CHECKOUT"',
        "/usr/sbin/chown -R root:wheel .",
        '/bin/bash ops/executive_os/repair-capacity-source-closure.sh repair',
    )
    for value in forbidden:
        assert value not in runbook


def test_root_carrier_wrapper_uses_no_git_and_requires_descriptor_verification() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "/usr/bin/git" not in script
    assert "verify-repair-carrier" in script
    assert "--repository" in script
    assert ".repair-carrier-commit" in script
    assert "/usr/bin/env -i" in script


def test_runbook_fixes_output_recovery_two_axis_proof_and_all_holds() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())
    required = (
        "0 H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED",
        "0 H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED",
        "64 INVALID_INVOCATION",
        "65 H0_SOURCE_CLOSURE_REPAIR_REFUSED",
        "70 H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER",
        "75 H0_LOCK_HELD",
        "77 ROOT_REQUIRED",
        "Stderr is empty",
        "same carrier",
        "parent `fsync`",
        "e4e44867ace335ac9208a3990a10c163e199492d",
        "topology-preparer/topology-release identity",
        "source-closure/generation-repair identity",
        "does not install a release",
        "does not rerender topology",
        "P0 re-pin",
        "provider-home",
        "credential",
        "OAuth",
        "service",
        "socket",
        "provider",
        "routing",
        "worker",
        "fan-out",
        "failover",
        "CF2-I",
    )
    for value in required:
        assert value in normalized


def test_runbook_design_and_plan_preserve_only_kernel_read_atime_exception() -> None:
    required = (
        "zero program-directed and zero semantic mutation",
        "Kernel-induced access-time advancement from required reads is the sole permitted observable metadata delta",
        "Atime is non-authoritative, may only remain equal or advance",
        "never set, restored, decreased, or used to conceal another change",
        "applies only to the fixed installed H0 root",
        "writable APFS",
        "not mounted `MNT_RDONLY`",
        "does not expose `MNT_NOATIME`",
        "mandatory full independent content verification",
        "does not apply to any other filesystem, root, provider, or worker surface",
        "Namespace",
        "bytes/digests",
        "device/inode identity",
        "type",
        "mode",
        "UID/GID",
        "links",
        "size",
        "flags",
        "ACLs",
        "xattrs",
        "mtime",
        "ctime",
        "topology/rollback evidence",
        "launchd state",
        "sockets",
        "legacy state",
    )
    for authority in (RUNBOOK, DESIGN, PLAN):
        content = " ".join(authority.read_text(encoding="utf-8").split())
        for value in required:
            assert value in content, f"{authority}: missing {value}"


def _runtime_wrapper_with_bounded_lower_carrier(tmp_path: Path) -> Path:
    script_dir = tmp_path / "ops" / "executive_os"
    script_dir.mkdir(parents=True)
    wrapper = script_dir / SCRIPT.name
    wrapper.write_bytes(SCRIPT.read_bytes())
    wrapper.chmod(0o755)
    (script_dir / "capacity_host_artifacts.py").write_text(
        """
import os
import sys

arguments = sys.argv[1:]
expected_mode = os.environ["MMX_CAPACITY_REPAIR_EXPECTED_MODE"]
if (
    not arguments
    or arguments[0] != "source-repair-host"
    or arguments[1:3] != ["--mode", expected_mode]
    or "--system-root" not in arguments
    or "--lock-file" not in arguments
    or "--expected-repair-commit" not in arguments
    or "--expected-source-commit" not in arguments
    or arguments[-1] != "--test-adapter"
):
    raise SystemExit(64)
repair_only = {"--operator-user", "--transport", "--transport-sha256"}
observed_repair_only = repair_only.intersection(arguments)
if (
    (expected_mode == "repair" and observed_repair_only != repair_only)
    or (expected_mode == "verify-only" and observed_repair_only)
):
    raise SystemExit(64)
raise SystemExit(int(os.environ["MMX_CAPACITY_REPAIR_FAKE_EXIT"]))
""",
        encoding="utf-8",
    )
    return wrapper


@pytest.mark.skipif(os.geteuid() == 0, reason="root-required is a non-root boundary")
def test_bash_wrapper_renders_root_required_runtime_tuple() -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "MMX_CAPACITY_REPAIR_TEST_ROOT"
    }
    assert _run(
        "verify-only",
        "--expected-source-closure-repair-commit",
        "d" * 40,
        environment=environment,
    ) == (77, "ROOT_REQUIRED\n", "")


@pytest.mark.skipif(os.geteuid() == 0, reason="test adapter is confined to non-root")
@pytest.mark.parametrize(
    "mode,lower_exit,expected",
    (
        ("refusal", 65, (65, "H0_SOURCE_CLOSURE_REPAIR_REFUSED\n", "")),
        ("lock-held", 75, (75, "H0_LOCK_HELD\n", "")),
        (
            "incomplete",
            70,
            (70, "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER\n", ""),
        ),
        ("repair", 0, (0, "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED\n", "")),
        ("verify-only", 0, (0, "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n", "")),
    ),
)
def test_bash_wrapper_runtime_output_tuples_use_existing_adapter_boundary(
    tmp_path: Path,
    mode: str,
    lower_exit: int,
    expected: tuple[int, str, str],
) -> None:
    wrapper = _runtime_wrapper_with_bounded_lower_carrier(tmp_path)
    environment = dict(os.environ)
    environment["MMX_CAPACITY_REPAIR_TEST_ROOT"] = str(tmp_path / "host")
    environment["MMX_CAPACITY_REPAIR_FAKE_EXIT"] = str(lower_exit)
    environment["MMX_CAPACITY_REPAIR_EXPECTED_MODE"] = (
        "repair" if mode == "repair" else "verify-only"
    )
    arguments = (
        (
            "repair",
            "--expected-source-closure-repair-commit",
            "d" * 40,
            "--operator-user",
            "operator",
            "--macro-transport",
            "/tmp/carrier.zip",
            "--macro-transport-sha256",
            "a" * 64,
        )
        if mode == "repair"
        else (
            "verify-only",
            "--expected-source-closure-repair-commit",
            "d" * 40,
        )
    )
    assert _run_script(wrapper, *arguments, environment=environment) == expected


def test_bash32_empty_array_and_fixed_output_rendering() -> None:
    compatibility = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -u; values=(); if [ "${#values[@]}" -gt 0 ]; then '
            '/usr/bin/printf "%s\\n" "${values[@]}"; fi; '
            '/usr/bin/printf "%s\\n" EMPTY_ARRAY_PASS',
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert (compatibility.returncode, compatibility.stdout, compatibility.stderr) == (
        0,
        "EMPTY_ARRAY_PASS\n",
        "",
    )

    source = SCRIPT.read_text(encoding="utf-8")
    assert "/usr/bin/printf '%s\\n' \"$sentinel\"" in source
    for fixed_render in (
        'finish 64 "INVALID_INVOCATION"',
        'finish 65 "H0_SOURCE_CLOSURE_REPAIR_REFUSED"',
        'finish 70 "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER"',
        'finish 75 "H0_LOCK_HELD"',
        'finish 77 "ROOT_REQUIRED"',
        'finish 0 "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"',
        'finish 0 "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"',
    ):
        assert fixed_render in source
    for bash4_only in ("declare -A", "mapfile", "readarray", "${value,,}"):
        assert bash4_only not in source
    assert _run("--help") == INVALID
