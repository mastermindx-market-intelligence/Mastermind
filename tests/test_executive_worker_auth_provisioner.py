"""Linux-safe security contract for dedicated worker authentication."""
from __future__ import annotations

import os
import importlib.util
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "provision-worker-auth.sh"
CANARY = ROOT / "ops" / "executive_os" / "provider_inference_canary.py"
RUNBOOK = ROOT / "ops" / "executive_os" / "HOST_PREREQUISITES.md"
INSTALL = ROOT / "ops" / "executive_os" / "install.sh"
ACCEPTANCE = ROOT / "ops" / "executive_os" / "acceptance.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_worker_auth_provisioner_is_executable_syntax_valid_and_no_mode_inert() -> None:
    assert stat.S_IMODE(SCRIPT.stat().st_mode) & 0o111
    syntax = subprocess.run(
        ["/bin/bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr
    no_mode = subprocess.run(
        ["/bin/bash", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert no_mode.returncode == 64
    assert "modes:" in no_mode.stderr
    source = _source()
    assert source.index('[ "$mode_count" -eq 1 ] || usage') < source.index(
        '"$(/usr/bin/id -u)" -eq 0'
    )


def test_primary_enrollment_is_stdin_only_and_has_no_secret_surfaces() -> None:
    source = _source()
    assert "--enroll-service-account" in source
    assert "--enroll-personal-access-token" in source
    assert "login --with-access-token" in source
    enrollment = source.split("enroll_access_token_from_stdin() {", 1)[1].split("\n}", 1)[0]
    assert "run_codex_as_worker login --with-access-token" in enrollment
    assert ">/dev/null 2>&1" in enrollment
    assert "run_inference_canary" not in enrollment
    assert "provider-inference-canary" not in enrollment
    assert "read " not in enrollment
    assert "mktemp" not in enrollment
    assert "CODEX_ACCESS_TOKEN" not in source
    assert "OPENAI_API_KEY" not in source
    assert "--with-api-key" not in source
    assert 'cp "$AUTH_PATH"' not in source
    assert 'ditto "$AUTH_PATH"' not in source
    assert "auth.json).read" not in source


def test_enrollment_and_rotation_are_explicit_and_never_ready_by_themselves() -> None:
    source = _source()
    assert "--replace-existing" in source
    assert "explicit --replace-existing is required for rotation" in source
    assert "run_codex_as_worker logout" in source
    service = source.split('if [ "$ENROLL_SERVICE_ACCOUNT" = "true" ]; then', 1)[1].split(
        "fi", 1
    )[0]
    personal = source.split(
        'if [ "$ENROLL_PERSONAL_ACCESS_TOKEN" = "true" ]; then', 1
    )[1].split("fi", 1)[0]
    device = source.split('if [ "$REAUTHORIZE_DEVICE" = "true" ]; then', 1)[1].split(
        "\nusage", 1
    )[0]
    for branch in (service, personal, device):
        assert "inference canary" in branch
        assert "not READY" in branch
        assert "provider-inference-canary.sh" not in branch
    assert "login --device-auth" in source
    assert "</dev/tty >/dev/tty 2>/dev/tty" in source


def test_personal_pro_slot_is_catalog_derived_and_cannot_take_low_level_overrides() -> None:
    source = _source()
    assert "--slot-id" in source
    assert "provider_worker_slots.py" in source
    assert 'resolve_slot_field "worker_user"' in source
    assert 'resolve_slot_field "worker_uid"' in source
    assert 'resolve_slot_field "worker_gid"' in source
    assert 'resolve_slot_field "provider_home"' in source
    assert 'resolve_slot_field "readiness_receipt"' in source
    assert 'resolve_slot_field "workspace_binding_class"' in source
    assert 'resolve_slot_field "default_credential_kind"' in source
    assert "slot identity cannot be combined with low-level identity/path overrides" in source
    assert source.index("resolve_selected_slot") < source.index(
        'case "$WORKER_UID" in'
    )
    assert "personal-pro-dedicated-worker-attested" not in source
    assert "_mastermind_codex_01" not in source
    assert "codex-pro-01/provider-home" not in source


def test_selected_slot_is_bound_through_identity_readiness_and_canary() -> None:
    source = _source()
    ready = source.split('if [ "$VERIFY_READY" = "true" ]; then', 1)[1].split(
        'if [ "$ENROLL_SERVICE_ACCOUNT" = "true" ]; then', 1
    )[0]
    assert ready.count('--worker-uid "$WORKER_UID"') >= 5
    assert ready.count('--worker-gid "$WORKER_GID"') >= 5
    assert ready.count('--worker-user "$WORKER_USER"') == 2
    assert ready.count('--worker-group "$WORKER_GROUP"') == 2
    assert 'provider-inference-canary.sh" --slot-id "$SLOT_ID"' in ready
    assert '--receipt "$READINESS_RECEIPT"' in ready
    assert 'READINESS_RECEIPT="$(resolve_slot_field "readiness_receipt")"' in source


def test_personal_pro_slot_operation_has_no_normal_mac_codex_path() -> None:
    source = _source()
    assert "/Users/chriswong/.codex" not in source
    assert 'CODEX_HOME="$HOME/.codex"' not in source
    assert 'CODEX_HOME="~/.codex"' not in source
    assert 'HOME="$PROVIDER_HOME"' in source
    assert 'CODEX_HOME="$PROVIDER_HOME"' in source
    assert 'cd -- "$PROVIDER_HOME"' in source


def test_verify_ready_is_identity_first_exactly_one_canary_and_replay_safe() -> None:
    source = _source()
    branch = source.split('if [ "$VERIFY_READY" = "true" ]; then', 1)[1].split(
        'if [ "$ENROLL_SERVICE_ACCOUNT" = "true" ]; then', 1
    )[0]
    assert branch.count("provider-inference-canary.sh") == 1
    assert branch.count("provider_identity_probe.py") == 2
    assert branch.count('provider_readiness.py" reuse') == 1
    assert branch.count('provider_readiness.py" reserve') == 1
    assert branch.count('provider_readiness.py" finalize') == 1
    assert branch.index('provider_readiness.py" reuse') < branch.index(
        "provider_identity_probe.py"
    )
    assert branch.index("provider_identity_probe.py") < branch.index(
        'provider_readiness.py" reserve'
    )
    assert branch.index('provider_readiness.py" reserve') < branch.index(
        "provider-inference-canary.sh"
    )
    assert branch.rindex("provider_identity_probe.py") > branch.index(
        "provider-inference-canary.sh"
    )
    assert branch.index('provider_readiness.py" finalize') > branch.rindex(
        "provider_identity_probe.py"
    )
    assert '--canary-command-status "$canary_status"' in branch
    assert '--post-identity-command-status "$post_identity_status"' in branch
    assert branch.count('--credential-expires-at "$CREDENTIAL_EXPIRES_AT"') == 3
    assert "no canary spent" in branch
    assert "stale or invalid; fail closed" in branch


def test_readiness_and_rotation_share_one_crash_durable_transaction_lock() -> None:
    source = _source()
    assert 'READINESS_TRANSACTION_LOCK="$SYSTEM_CONFIG/provider-readiness.transaction.lock"' in source
    assert 'acquire_readiness_transaction_lock' in source
    assert 'recover_readiness_transaction_lock' in source
    assert '"$READINESS_TRANSACTION_LOCK/owner-pid"' in source
    assert '/bin/kill -0 "$owner_pid"' in source
    assert '/usr/bin/pgrep -U "$WORKER_UID"' in source
    assert 'fsync_readiness_lock_state' in source
    assert '"/Library/Application Support" "$SYSTEM_ROOT" "$SYSTEM_CONFIG"' in source
    assert 'unexpected ACL' in source
    central_lock = source.index('acquire_readiness_transaction_lock\nfi')
    assert central_lock < source.index('provider_readiness.py" reuse')
    replacement = source.split("prepare_explicit_replacement() {", 1)[1].split("\n}", 1)[0]
    assert "invalidate_readiness_receipt" in replacement
    assert "run_codex_as_worker logout" in replacement


def test_credential_mutation_requires_verified_disarm_before_any_effect() -> None:
    source = _source()
    gate = source.index("require_autonomy_disarmed_for_credential_mutation\nfi")
    assert '"$SCRIPT_DIR/credential_rotation_interlock.py"' in source
    assert gate < source.index("acquire_readiness_transaction_lock\nfi")
    assert gate < source.index('if [ "$ENROLL_SERVICE_ACCOUNT" = "true" ]; then')
    assert gate < source.index('if [ "$ENROLL_PERSONAL_ACCESS_TOKEN" = "true" ]; then')
    assert gate < source.index('if [ "$REAUTHORIZE_DEVICE" = "true" ]; then')
    interlock = source.split(
        "require_autonomy_disarmed_for_credential_mutation() {", 1
    )[1].split("\n}", 1)[0]
    assert "AUTH_PATH" not in interlock
    assert "auth.json" not in interlock
    assert "login" not in interlock
    assert "logout" not in interlock


def test_credential_interlock_pure_state_rejects_every_armed_or_mixed_bit() -> None:
    path = ROOT / "ops" / "executive_os" / "credential_rotation_interlock.py"
    spec = importlib.util.spec_from_file_location("credential_rotation_interlock", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    CredentialInterlockError = module.CredentialInterlockError
    evaluate_credential_mutation_state = module.evaluate_credential_mutation_state

    disarmed_control = {
        "coo_autonomy_armed": False,
        "coo_operator_harness_armed": False,
    }
    disarmed_worker = {"operator_harness_armed": False}
    evaluate_credential_mutation_state(
        disarmed_control,
        disarmed_worker,
        transaction_present=False,
    )
    cases = (
        (
            {**disarmed_control, "coo_autonomy_armed": True},
            disarmed_worker,
            False,
        ),
        (
            {**disarmed_control, "coo_operator_harness_armed": True},
            disarmed_worker,
            False,
        ),
        (
            disarmed_control,
            {"operator_harness_armed": True},
            False,
        ),
        (disarmed_control, disarmed_worker, True),
    )
    for control, worker, transaction_present in cases:
        with pytest.raises(CredentialInterlockError):
            evaluate_credential_mutation_state(
                control,
                worker,
                transaction_present=transaction_present,
            )


def test_catchable_termination_preserves_lock_while_child_survives(tmp_path: Path) -> None:
    source = _source()
    function_body = source.split("preserve_readiness_lock_on_signal() {", 1)[1].split(
        "\n}", 1
    )[0]
    handler = "preserve_readiness_lock_on_signal() {" + function_body + "\n}"
    trap_lines = "\n".join(
        line
        for line in source.splitlines()
        if line.startswith("trap 'preserve_readiness_lock_on_signal")
    )
    for expected in ("HUP", "INT", "QUIT", "TERM"):
        assert expected in trap_lines

    for signal_value in (signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
        marker = tmp_path / f"marker-{signal_value.value}"
        harness = f"""
set -euo pipefail
marker="$1"
READINESS_LOCK_HELD="true"
READINESS_LOCK_RELEASE_ON_EXIT="true"
cleanup() {{
  if [ "$READINESS_LOCK_HELD" = "true" ] && [ "$READINESS_LOCK_RELEASE_ON_EXIT" = "true" ]; then
    /bin/echo released >"$marker"
  else
    /bin/echo preserved >"$marker"
  fi
}}
trap cleanup EXIT
{handler}
{trap_lines}
/bin/sleep 60 &
child_pid=$!
/bin/echo "$child_pid"
wait "$child_pid"
"""
        process = subprocess.Popen(
            ["/bin/bash", "-c", harness, "signal-harness", str(marker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None
        child_pid = int(process.stdout.readline().strip())
        try:
            time.sleep(0.1)
            os.kill(process.pid, signal_value)
            process.wait(timeout=5)
            assert marker.read_text(encoding="utf-8").strip() == "preserved"
            os.kill(child_pid, 0)
        finally:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_metadata_pinning_and_login_status_remain_strict_and_non_disclosing() -> None:
    source = _source()
    assert 'CODEX_VERSION="0.147.0"' in source
    assert 'CODEX_TEAM_ID="2DC432GLL2"' in source
    assert (
        'CODEX_SHA256="19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"'
        in source
    )
    assert "/usr/bin/codesign --verify --strict" in source
    assert '"$WORKER_UID:$WORKER_GID:600:1"' in source
    assert "auth file is empty" in source
    assert "unexpected filesystem ACL" in source
    complete = source.split("verify_complete_auth() {", 1)[1].split("\n}", 1)[0]
    assert complete.count("verify_auth_metadata") == 2
    assert "verify_login_without_output" in complete
    assert "run_codex_as_worker login status" in source
    assert ">/dev/null 2>&1" in source
    for command in ("cat", "jq", "sed", "grep", "head"):
        assert f'{command} "$AUTH_PATH"' not in source


def test_runtime_canary_still_forbids_token_and_login_paths() -> None:
    canary = CANARY.read_text(encoding="utf-8")
    assert "CODEX_ACCESS_TOKEN" in canary
    assert "OPENAI_API_KEY" in canary
    assert "--with-access-token" in canary
    assert 'item in {"remote", "login", "logout"}' in canary
    assert "forced_chatgpt_workspace_id" in canary


def test_install_auth_gate_is_exact_before_mutation() -> None:
    source = INSTALL.read_text(encoding="utf-8")
    gate = source.index('"$WORKER_UID:$WORKER_GID:600:1"')
    mutation = source.index("# Cross the mutation boundary")
    assert gate < mutation
    assert "dedicated worker auth is empty" in source[:mutation]
    assert "dedicated worker auth has an unexpected filesystem ACL" in source[:mutation]


def test_formal_acceptance_requires_current_composite_receipt_before_runtime() -> None:
    source = ACCEPTANCE.read_text(encoding="utf-8")
    validate = source.split("def validate_install(self)", 1)[1].split(
        "def initialize_runtime_and_fixtures", 1
    )[0]
    assert "PROVIDER_READINESS_RECEIPT" in validate
    assert "validate_receipt_file" in validate
    assert "auth.json" in validate
    run = source.split("def run(self)", 1)[1].split("def cleanup_after_failure", 1)[0]
    assert run.index("self.validate_install()") < run.index(
        "self.initialize_runtime_and_fixtures()"
    )


def test_runbook_documents_one_canary_gate_and_company_admin_provenance() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    flat = " ".join(runbook.split())
    assert "service account" in flat
    assert "finite-lived Codex access token" in flat
    assert "company-workspace-admin-attested" in flat
    assert "administrator evidence" in flat
    assert "--enroll-service-account" in flat
    assert "--enroll-personal-access-token" in flat
    assert "--reauthorize-device" in flat
    assert "--verify-ready" in flat
    assert "exactly one" in flat
    assert "There is no separate canary command" in flat
    assert "install-before-readiness" in flat
    assert "before it creates a Job" in flat
    assert "forced workspace IDs" in flat
    assert "never silently fall back to Personal" in flat
    assert "CREDENTIAL_EXPIRES_AT" in runbook
    assert "no more than 24 hours" in flat
    assert "at least 30 minutes" in flat
    assert "root-owned transaction lock" in flat
    assert "--recover-readiness-transaction" in flat
    assert "Provider readiness is not Git handoff Gate B" in flat
    assert "git_handoff_preflight.py" in flat
    assert "autonomy-control.sh" in flat
    assert "ARMED_READY" in flat
    assert "DISARMED" in flat
    assert "--gate-b-receipt" in flat
    assert "--expected-credential-kind" in flat
    assert "--workspace-binding-class" in flat
    assert "--credential-expires-at" in flat
    assert runbook.count("provider-inference-canary.sh") <= 1
