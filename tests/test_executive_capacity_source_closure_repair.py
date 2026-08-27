from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "repair-capacity-source-closure.sh"
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
        "/usr/bin/sudo /usr/bin/env -i",
        "No network command runs as root",
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

    repair = """/bin/bash "$ROOT_CARRIER/ops/executive_os/repair-capacity-source-closure.sh" repair \\
  --expected-source-closure-repair-commit \"$REPAIR_MERGE_SHA\" \\
  --operator-user \"$OPERATOR_USER\" \\
  --macro-transport \"$MACRO_TRANSPORT\" \\
  --macro-transport-sha256 \"$MACRO_TRANSPORT_SHA256\""""
    verify = """/bin/bash "$ROOT_CARRIER/ops/executive_os/repair-capacity-source-closure.sh" verify-only \\
  --expected-source-closure-repair-commit \"$REPAIR_MERGE_SHA\""""
    assert repair in runbook
    assert runbook.count(verify) == 2
    assert "\n  sudo /bin/bash -s -- \\" not in runbook


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
        "root-created `0700`",
        "verify-repair-carrier",
        ".repair-carrier-commit",
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
