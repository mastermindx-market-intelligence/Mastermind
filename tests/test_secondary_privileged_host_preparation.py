from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops" / "executive_os" / "prepare-secondary-privileged-host.sh"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_shell_syntax_is_valid() -> None:
    completed = subprocess.run(
        ["bash", "-n", str(SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_closed_cli_has_no_host_power_or_service_selector() -> None:
    text = _source()
    assert "--source-repo" in text
    assert "--expected-sha" in text
    assert "--operator-user" in text
    for forbidden in (
        "--host",
        "--label",
        "--command",
        "--action",
        "--power",
        "--pmset",
        "--worker-id",
        "--provider",
    ):
        assert forbidden not in text


def test_central_control_plane_is_only_observed_never_mutated() -> None:
    text = _source()
    for label in (
        "com.mastermind.executive.control",
        "com.mastermind.executive.mcp",
        "com.mastermind.executive.sol-state-relay",
    ):
        assert label in text
    mutation_lines = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"launchctl\s+(?:enable|disable|bootstrap|bootout|kickstart)", line)
    ]
    assert mutation_lines
    assert all("$PRIVILEGED_LABEL" in line or "$PRIVILEGED_PLIST" in line for line in mutation_lines)
    assert "central Executive LaunchDaemon is installed" in text
    assert "central Executive LaunchDaemon is loaded" in text


def test_antiduplication_is_proven_before_and_after_persistent_mutation() -> None:
    text = _source().split("trap cleanup_on_failure EXIT", 1)[1]
    first_guard = text.index("assert_central_absent")
    first_persistent_install = text.index("/usr/bin/install -d")
    final_guard = text.rindex("assert_central_absent")
    arm = text.index('/bin/launchctl enable "system/$PRIVILEGED_LABEL"')
    assert first_guard < first_persistent_install < arm < final_guard


def test_existing_canonical_source_runtime_and_release_owners_are_reused() -> None:
    text = _source()
    assert 'PYTHON_PROVISIONER="$SCRIPT_DIR/provision-python-runtime.sh"' in text
    assert 'SOURCE_POLICY="$SCRIPT_DIR/install_source_policy.py"' in text
    assert '"$PYTHON_PROVISIONER" --verify-only' in text
    assert '"$PYTHON_BINARY" -I -S -B "$SOURCE_POLICY"' in text
    assert "release_manifest.py" in text
    assert "render_launchd_program_arguments.py" in text
    assert "git -C \"$SOURCE_REPO\" archive --format=tar \"$EXPECTED_SHA\"" in text


def test_secondary_preparation_does_not_install_worker_or_provider_authority() -> None:
    text = _source()
    for forbidden in (
        "_mastermind_worker",
        "worker-codex.json",
        "auth.json",
        "provision-worker-auth.sh",
        "executive_os_phase1c_worker.py",
        "capacity-observe",
        "remote_worker_gateway",
        "provider_home",
        "codex-attestation",
    ):
        assert forbidden not in text.lower()


def test_privileged_broker_is_exact_release_bound() -> None:
    text = _source()
    assert '"schema": "mastermind.executive_privileged_broker_config.v1"' in text
    assert '"release_root": release_root' in text
    assert '"allowed_peer_uids": sorted({int(control_uid), int(operator_uid)})' in text
    assert '"timeout_seconds": 600' in text
    assert '"broker_version": "1"' in text
    assert '"$RELEASE_ROOT/scripts/executive_os_privileged_broker.py"' in text
    assert 'serve --config "$PRIVILEGED_CONFIG"' in text


def test_power_ceremony_requires_the_reviewed_846_wrapper() -> None:
    text = _source()
    assert '"$RELEASE_ROOT/scripts/mmx_secondary_host_power.py"' in text
    assert 'POWER_LAUNCHER="$SYSTEM_ROOT/bin/mmx-secondary-host-power"' in text
    assert 'mmx_secondary_host_power.py\\" \\"\\$@\\"' in text


def test_broker_status_probe_is_nonroot_read_only_and_correlated() -> None:
    text = _source()
    assert '/usr/bin/sudo -u "$OPERATOR_USER"' in text
    assert 'status --request-id fleet-secondary-prep-probe' in text
    assert '[ "$STATUS_RC" -eq 4 ]' in text
    assert 'value.get("status") != "NOT_FOUND"' in text
    assert 'value.get("installed_release_sha") != expected_sha' in text


def test_partial_arm_failure_only_cleans_up_privileged_broker() -> None:
    text = _source()
    cleanup = text.split("cleanup_on_failure() {", 1)[1].split("}\ntrap", 1)[0]
    assert 'bootout "system/$PRIVILEGED_LABEL"' in cleanup
    assert 'disable "system/$PRIVILEGED_LABEL"' in cleanup
    for central in ("$CONTROL_LABEL", "$MCP_LABEL", "$RELAY_LABEL"):
        assert central not in cleanup


def test_success_claim_is_bounded_to_power_remediation_readiness() -> None:
    text = _source()
    assert 'mastermind.secondary_privileged_host_preparation/v1' in text
    assert 'READY_FOR_GOVERNED_POWER_REMEDIATION' in text
    for forbidden_claim in (
        "FLEET_READY",
        "WORKER_READY",
        "CAPACITY_READY",
        "GATEWAY_READY",
        "PROVIDER_READY",
        "ENROLLED",
    ):
        assert forbidden_claim not in text


def test_root_helpers_are_not_invoked_from_a_mutable_checkout() -> None:
    text = _source()
    source_trust = text.index('SOURCE_PARENT="$(cd "$SOURCE_REPO/.."')
    runtime_verify = text.index('"$PYTHON_PROVISIONER" --verify-only')
    policy_verify = text.index('"$PYTHON_BINARY" -I -S -B "$SOURCE_POLICY"')
    assert source_trust < runtime_verify < policy_verify
    assert 'source checkout contains a non-root-owned object' in text
    assert 'source checkout contains a group/other-writable object' in text
    assert 'source checkout contains a hard-linked file' in text
    assert 'source checkout contains a filesystem ACL' in text


def test_release_manifest_is_created_and_verified_before_atomic_publish() -> None:
    text = _source()
    create = text.index('$STAGING/ops/executive_os/release_manifest.py" create')
    verify = text.index('$STAGING/ops/executive_os/release_manifest.py" verify')
    publish = text.index('/bin/mv "$STAGING" "$RELEASE_ROOT"')
    assert create < verify < publish
    assert '$RELEASE_ROOT/ops/executive_os/release_manifest.py" create' not in text
    cleanup = text.split('cleanup_on_failure() {', 1)[1].split('}\ntrap', 1)[0]
    assert '/bin/rm -rf -- "$STAGING"' in cleanup
