"""Exercise the real uninstall shell with hermetic native-command doubles.

Only fixed host paths are relocated. Root identity and launchctl are simulated;
no test invokes sudo, changes a real service, or touches real credential state.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/executive_os/uninstall.sh"
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
