"""Exercise the real uninstall shell with hermetic native-command doubles.

Only fixed host paths are relocated. Root identity and launchctl are simulated;
no test invokes sudo, changes a real service, or touches real credential state.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    canonical_request_bytes,
    validate_request,
)
from control_plane.executive_privileged_broker import (
    PrivilegedActionBroker,
    PrivilegedBrokerConfig,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/executive_os/uninstall.sh"
BROKER_SPEC = ROOT / "docs/superpowers/specs/2026-09-13-executive-privileged-action-broker-design.md"
PERMANENT_PLAN = ROOT / "docs/superpowers/plans/2026-09-14-permanent-privileged-execution-program.md"
PRIVILEGED = "com.mastermind.executive.privileged"
CONTROL = "com.mastermind.executive.control"
WORKER = "com.mastermind.executive.worker.codex"
LABELS = (PRIVILEGED, CONTROL, WORKER)


@pytest.fixture
def host(tmp_path: Path):
    for name in ("plists", "loaded", "disabled", "sockets", "runtime"):
        (tmp_path / name).mkdir()
    for label in LABELS:
        (tmp_path / "loaded" / label).touch()
        (tmp_path / "plists" / f"{label}.plist").write_text("reviewed plist\n")
    receipts = tmp_path / "runtime/privileged-actions/receipts"
    (receipts / "inflight").mkdir(parents=True)
    (receipts / "completed.json").write_text('{"evidence":"retain"}\n')
    (tmp_path / "runtime/auth-sentinel").write_text("fixture-not-a-secret\n")
    return tmp_path


_TARGET_ID = "req-reconciled-001"
_TARGET_RELEASE = "a" * 40
_CURRENT_RELEASE = "b" * 40
_READINESS_SHA = "c" * 64
_AUTH_IDENTITY = {"uid": 451, "gid": 451, "mode": 0o600, "inode": 101}
_BINARY_IDENTITY = {
    "path": "/Library/Application Support/MastermindExecutive/bin/codex-0.147.0",
    "version": "0.147.0",
    "sha256": "1" * 64,
    "team_identifier": "2DC432GLL2",
    "uid": 0,
    "gid": 0,
    "mode": 0o555,
    "inode": 202,
}


def _write_reconciled_pair(host: Path) -> tuple[Path, Path]:
    receipt_root = host / "runtime/privileged-actions/receipts"
    release = host / "release" / _CURRENT_RELEASE
    release.mkdir(parents=True, exist_ok=True)
    readiness = {
        "readiness_receipt_sha256": _READINESS_SHA,
        "readiness_document": {
            "schema_version": "mastermind.executive_provider_readiness/v2",
            "passed": True,
            "refusal": None,
            "observed_at": "2026-09-21T22:49:00Z",
            "expected_credential_kind": "device-auth",
            "workspace_binding_class": "company-workspace-admin-attested",
            "credential_expires_at": "2026-09-22T10:30:00Z",
            "credential_lstat": dict(_AUTH_IDENTITY),
            "codex_binary": dict(_BINARY_IDENTITY),
            "provider_identity": {
                "credential_lstat": dict(_AUTH_IDENTITY),
                "codex_binary": dict(_BINARY_IDENTITY),
            },
        },
        "readiness_transaction_lock_present": False,
        "verify_ready_processes": (),
        "current_auth_identity": dict(_AUTH_IDENTITY),
        "current_binary_identity": dict(_BINARY_IDENTITY),
    }
    broker = PrivilegedActionBroker(
        PrivilegedBrokerConfig(
            release_root=release,
            receipt_root=receipt_root,
            allowed_peer_uids=(450, 501),
            timeout_seconds=30,
            broker_version="test",
        ),
        require_root=False,
        trust_validator=lambda _config: None,
        reconciliation_observer=lambda: readiness,
    )
    raw = {
        "schema": REQUEST_SCHEMA,
        "request_id": _TARGET_ID,
        "action": "executive.worker_auth.verify_ready",
        "args": {
            "expected_credential_kind": "device-auth",
            "workspace_binding_class": "company-workspace-admin-attested",
            "credential_expires_at": "2026-09-30T02:00:00Z",
        },
    }
    validated = validate_request(raw)
    digest = hashlib.sha256(canonical_request_bytes(validated)).hexdigest()
    marker_value = {
        "schema": "mastermind.executive_privileged_action_inflight.v1",
        "request_id": _TARGET_ID,
        "request_sha256": digest,
        "action": validated.action,
        "effect_class": validated.effect_class,
        "started_at": "2026-09-23T01:46:34Z",
        "release_sha": _TARGET_RELEASE,
    }
    marker_raw = (
        json.dumps(marker_value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    marker = broker.inflight_path(_TARGET_ID)
    marker.write_bytes(marker_raw)
    marker.chmod(0o600)
    request = {
        "schema": "mastermind.executive_privileged_action_reconcile_not_applied_request.v1",
        "target_request_id": _TARGET_ID,
        "target_request_sha256": digest,
        "target_marker_sha256": hashlib.sha256(marker_raw).hexdigest(),
        "target_release_sha": _TARGET_RELEASE,
        "readiness_receipt_sha256": _READINESS_SHA,
        "expected_credential_kind": "device-auth",
        "workspace_binding_class": "company-workspace-admin-attested",
        "credential_expires_at": "2026-09-30T02:00:00Z",
    }
    broker.reconcile_not_applied(request, peer_uid=501)
    return marker, broker.reconciliation_path(_TARGET_ID)


_NATIVE_DOUBLES = r'''
function /usr/bin/id() { printf '%s\n' "${TEST_UID:-0}"; }
function /usr/bin/uname() { printf '%s\n' "${TEST_OS:-Darwin}"; }
function /bin/sleep() { :; }
function /bin/launchctl() {
  printf '%s\n' "$*" >> "$TEST_HOST/calls"
  local verb="$1" label="${2#system/}"
  case "$verb" in
    disable)
      [ "${TEST_DISABLE_FAIL:-}" != "$label" ] || return 5
      [ "${TEST_DISABLE_SILENT:-}" != "$label" ] || return 0
      command /usr/bin/touch "$TEST_HOST/disabled/$label" ;;
    bootout)
      [ "${TEST_STUBBORN:-}" != "$label" ] || return 5
      command /bin/rm -f "$TEST_HOST/loaded/$label"
      [ "${TEST_INFLIGHT_RACE:-}" != "$label" ] || command /usr/bin/touch "$TEST_HOST/runtime/privileged-actions/receipts/inflight/race.json"
      return 0 ;;
    print)
      if [ "${TEST_UNKNOWN:-}" = "$label" ]; then printf 'Permission denied\n' >&2; return 5; fi
      if [ -e "$TEST_HOST/loaded/$label" ]; then printf 'state = running\n'; return 0; fi
      if [ "${TEST_PRINT_NOISE:-}" = "$label" ]; then printf 'unexpected absent-service message\n' >&2; return 113; fi
      printf 'Bad request.\nCould not find service "%s" in domain for system\n' "$label" >&2
      return 113 ;;
    print-disabled)
      [ "${TEST_DISABLED_QUERY_FAIL:-}" != "1" ] || return 5
      printf 'disabled services = {\n'
      local path item value
      for path in "$TEST_HOST"/disabled/*; do
        [ -e "$path" ] || continue
        item="${path##*/}"; value="${TEST_DISABLED_VALUE:-disabled}"
        printf '\t"%s" => %s\n' "$item" "$value"
        [ "${TEST_DUPLICATE:-}" != "$item" ] || printf '\t"%s" => disabled\n' "$item"
      done
      printf '}\n' ;;
    *) return 64 ;;
  esac
}
function /bin/rm() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      -f|--) ;;
      "$TEST_HOST"/plists/*.plist) printf 'remove %s\n' "${arg##*/}" >> "$TEST_HOST/calls"; command /bin/rm -f -- "$arg" ;;
      *) printf 'test refused non-plist removal\n' >&2; return 97 ;;
    esac
  done
}
'''


def run_uninstall(host: Path, *args: str, **changes: str):
    text = SCRIPT.read_text()
    text = text.replace("/Library/LaunchDaemons", str(host / "plists"))
    text = text.replace("/var/db/mastermind-executive", str(host / "runtime"))
    text = text.replace("/var/run/mastermind-executive", str(host / "sockets"))
    text = text.replace(
        'RELEASE_ROOT="$(cd -P "$SCRIPT_DIR/../.." && /bin/pwd)"',
        f'RELEASE_ROOT="{ROOT}"',
    )
    text = text.replace(
        'PYTHON_BINARY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"',
        f'PYTHON_BINARY="{Path(sys.executable).resolve()}"',
    )
    script = host / "uninstall.sh"
    script.write_text(text)
    doubles = host / "native-doubles.sh"
    doubles.write_text(_NATIVE_DOUBLES)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(host), "LANG": "C", "BASH_ENV": str(doubles), "TEST_HOST": str(host), **changes}
    result = subprocess.run(["/bin/bash", str(script), *args], env=env, capture_output=True, text=True, timeout=10)
    calls = (host / "calls").read_text().splitlines() if (host / "calls").exists() else []
    return result, calls


def test_default_uninstall_revokes_privileged_service_and_preserves_evidence(host):
    result, calls = run_uninstall(host)
    assert result.returncode == 0, result.stderr
    assert not (host / "loaded" / PRIVILEGED).exists()
    assert not (host / "plists" / f"{PRIVILEGED}.plist").exists()
    assert (host / "disabled" / PRIVILEGED).exists()
    assert calls.index(f"disable system/{PRIVILEGED}") < calls.index(f"remove {PRIVILEGED}.plist")
    for label in LABELS:
        assert not (host / "loaded" / label).exists()
        assert not (host / "plists" / f"{label}.plist").exists()
        assert (host / "disabled" / label).exists()
        assert calls.index(f"bootout system/{label}") < calls.index(f"remove {PRIVILEGED}.plist")
    assert calls.index(f"bootout system/{PRIVILEGED}") < calls.index(f"bootout system/{CONTROL}") < calls.index(f"bootout system/{WORKER}")
    assert (host / "runtime/privileged-actions/receipts/completed.json").read_text() == '{"evidence":"retain"}\n'
    assert (host / "runtime/auth-sentinel").read_text() == "fixture-not-a-secret\n"


def test_privileged_only_revokes_no_unrelated_service(host):
    result, calls = run_uninstall(host, "--privileged-only")
    assert result.returncode == 0, result.stderr
    assert not (host / "loaded" / PRIVILEGED).exists()
    assert all((host / "loaded" / label).exists() for label in (CONTROL, WORKER))
    assert all(label not in "\n".join(calls) for label in (CONTROL, WORKER))


@pytest.mark.parametrize("change", [{"TEST_STUBBORN": PRIVILEGED}, {"TEST_UNKNOWN": PRIVILEGED}, {"TEST_DISABLE_FAIL": PRIVILEGED}, {"TEST_DUPLICATE": PRIVILEGED}, {"TEST_DISABLED_VALUE": "false"}])
def test_unproven_revocation_never_removes_plist_or_reports_success(host, change):
    result, calls = run_uninstall(host, "--privileged-only", **change)
    assert result.returncode != 0
    assert (host / "plists" / f"{PRIVILEGED}.plist").exists()
    assert not any(call.startswith("remove ") for call in calls)
    assert "services removed" not in result.stdout


def test_unknown_argument_is_refused_before_service_changes(host):
    result, calls = run_uninstall(host, "--anything")
    assert result.returncode == 64
    assert calls == []


@pytest.mark.parametrize("value", ["true", "disabled"])
def test_both_reviewed_native_disabled_formats_are_accepted(host, value):
    result, _calls = run_uninstall(host, "--privileged-only", TEST_DISABLED_VALUE=value)
    assert result.returncode == 0, result.stderr


def test_inflight_race_preserves_uncertain_effect_and_does_not_claim_clean_removal(host):
    result, calls = run_uninstall(host, "--privileged-only", TEST_INFLIGHT_RACE=PRIVILEGED)
    assert result.returncode != 0
    assert "EFFECT_RECONCILIATION_REQUIRED" in result.stderr
    assert (host / "runtime/privileged-actions/receipts/inflight/race.json").exists()
    assert not any(call.startswith("remove ") for call in calls)


def test_valid_reconciled_marker_allows_revocation_and_preserves_both_records(host):
    marker, reconciliation = _write_reconciled_pair(host)
    marker_before = marker.read_bytes()
    reconciliation_before = reconciliation.read_bytes()

    result, calls = run_uninstall(host, "--privileged-only")

    assert result.returncode == 0, result.stderr
    assert marker.read_bytes() == marker_before
    assert reconciliation.read_bytes() == reconciliation_before
    assert any(call.startswith("remove ") for call in calls)


def test_tampered_reconciliation_keeps_revocation_fail_closed(host):
    marker, reconciliation = _write_reconciled_pair(host)
    document = json.loads(reconciliation.read_text())
    document["target_marker_sha256"] = "f" * 64
    reconciliation.write_text(json.dumps(document, sort_keys=True) + "\n")

    result, calls = run_uninstall(host, "--privileged-only")

    assert result.returncode == 75
    assert "EFFECT_RECONCILIATION_REQUIRED" in result.stderr
    assert marker.exists() and reconciliation.exists()
    assert not any(call.startswith("remove ") for call in calls)


def test_orphan_reconciliation_record_keeps_revocation_fail_closed(host):
    marker, reconciliation = _write_reconciled_pair(host)
    marker.unlink()

    result, calls = run_uninstall(host, "--privileged-only")

    assert result.returncode == 75
    assert "EFFECT_RECONCILIATION_REQUIRED" in result.stderr
    assert reconciliation.exists()
    assert not any(call.startswith("remove ") for call in calls)


def test_governing_contracts_name_reconciled_not_applied_status_and_revocation_semantics():
    spec = BROKER_SPEC.read_text()
    plan = PERMANENT_PLAN.read_text()

    assert "RECONCILED_NOT_APPLIED" in spec
    assert "RECONCILED_NOT_APPLIED" in plan
    assert "marker" in plan and "reconciliation" in plan
    assert "preserv" in plan.lower()


@pytest.mark.parametrize("changes,code", [({"TEST_UID": "501"}, 77), ({"TEST_OS": "Linux"}, 69)])
def test_root_and_platform_guards_precede_every_host_effect(host, changes, code):
    result, calls = run_uninstall(host, **changes)
    assert result.returncode == code
    assert calls == []


def test_privileged_revocation_is_repeatable_when_label_was_never_installed(host):
    (host / "loaded" / PRIVILEGED).unlink()
    (host / "plists" / f"{PRIVILEGED}.plist").unlink()
    first, _ = run_uninstall(host, "--privileged-only")
    second, _ = run_uninstall(host, "--privileged-only")
    assert first.returncode == second.returncode == 0
    assert (host / "disabled" / PRIVILEGED).exists()


def test_stale_socket_is_not_deleted_or_claimed_revoked(host):
    socket = host / "sockets/privileged.sock"
    socket.touch()
    result, calls = run_uninstall(host, "--privileged-only")
    assert result.returncode == 65
    assert "UNINSTALL_PRIVILEGED_SOCKET_STILL_PRESENT" in result.stderr
    assert socket.exists()
    assert not any(call.startswith("remove ") for call in calls)


@pytest.mark.parametrize("name", ["inflight/unresolved.json", "inflight/.partial", "legacy.inflight.json"])
def test_all_unresolved_marker_shapes_are_preserved(host, name):
    marker = host / "runtime/privileged-actions/receipts" / name
    marker.write_text("incomplete evidence\n")
    result, calls = run_uninstall(host, "--privileged-only")
    assert result.returncode == 75
    assert marker.read_text() == "incomplete evidence\n"
    assert not any(call.startswith("remove ") for call in calls)


def test_symlinked_receipt_namespace_is_refused_without_following_it(host):
    inflight = host / "runtime/privileged-actions/receipts/inflight"
    inflight.rmdir()
    outside = host / "outside"
    outside.mkdir()
    (outside / "retained").touch()
    inflight.symlink_to(outside, target_is_directory=True)
    result, calls = run_uninstall(host, "--privileged-only")
    assert result.returncode == 65
    assert "UNINSTALL_RECEIPT_PATH_UNSAFE" in result.stderr
    assert (outside / "retained").exists()
    assert not any(call.startswith("remove ") for call in calls)


@pytest.mark.parametrize("change,reason", [
    ({"TEST_PRINT_NOISE": PRIVILEGED}, "UNINSTALL_SERVICE_STATE_UNKNOWN"),
    ({"TEST_DISABLE_SILENT": PRIVILEGED}, "UNINSTALL_DISABLED_STATE_UNPROVEN"),
    ({"TEST_DISABLED_QUERY_FAIL": "1"}, "UNINSTALL_DISABLED_STATE_UNKNOWN"),
])
def test_exact_native_observation_is_required_before_removal(host, change, reason):
    result, calls = run_uninstall(host, "--privileged-only", **change)
    assert result.returncode == 65
    assert reason in result.stderr
    assert (host / "plists" / f"{PRIVILEGED}.plist").exists()
    assert not any(call.startswith("remove ") for call in calls)


@pytest.mark.parametrize("stubborn", [CONTROL, WORKER])
def test_default_scope_failure_keeps_all_registration_files(host, stubborn):
    result, calls = run_uninstall(host, TEST_STUBBORN=stubborn)
    assert result.returncode == 65
    assert "UNINSTALL_SERVICE_STILL_LOADED" in result.stderr
    assert all((host / "plists" / f"{label}.plist").exists() for label in LABELS)
    assert not any(call.startswith("remove ") for call in calls)
    assert "services removed" not in result.stdout
