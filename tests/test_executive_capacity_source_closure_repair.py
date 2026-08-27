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

    repair = """/bin/bash ops/executive_os/repair-capacity-source-closure.sh repair \\
  --expected-source-closure-repair-commit \"$REPAIR_MERGE_SHA\" \\
  --operator-user \"$OPERATOR_USER\" \\
  --macro-transport \"$MACRO_TRANSPORT\" \\
  --macro-transport-sha256 \"$MACRO_TRANSPORT_SHA256\""""
    verify = """/bin/bash ops/executive_os/repair-capacity-source-closure.sh verify-only \\
  --expected-source-closure-repair-commit \"$REPAIR_MERGE_SHA\""""
    assert repair in runbook
    assert runbook.count(verify) == 2


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
