#!/bin/bash
# Revoke the fixed Executive launchd registrations, including the privileged
# broker. Receipts, runtime state, credentials, accounts and releases survive.
# --privileged-only leaves the ordinary control/worker registrations untouched.
set -euo pipefail
umask 077
export LANG=C LC_ALL=C

PRIVILEGED_ONLY="false"
case "$#:$*" in
  0:) ;;
  1:--privileged-only) PRIVILEGED_ONLY="true" ;;
  *) /bin/echo "usage: $0 [--privileged-only]" >&2; exit 64 ;;
esac

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "uninstall.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "uninstall.sh supports macOS only" >&2
  exit 69
}

PRIVILEGED_LABEL="com.mastermind.executive.privileged"
CONTROL_LABEL="com.mastermind.executive.control"
WORKER_LABEL="com.mastermind.executive.worker.codex"
PRIVILEGED_PLIST="/Library/LaunchDaemons/$PRIVILEGED_LABEL.plist"
CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"
WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"
PRIVILEGED_SOCKET="/var/run/mastermind-executive/privileged.sock"
RECEIPT_ROOT="/var/db/mastermind-executive/privileged-actions/receipts"
INFLIGHT_ROOT="$RECEIPT_ROOT/inflight"

refuse() {
  /bin/echo "$1" >&2
  exit 65
}

assert_disabled() {
  local label="$1" output
  output="$(/bin/launchctl print-disabled system 2>/dev/null)" \
    || refuse "UNINSTALL_DISABLED_STATE_UNKNOWN"
  # Same two native encodings as c1_relay_enrollment._launchd_disabled.
  # Missing, contradictory or duplicate overrides are not revocation proof.
  /usr/bin/printf '%s\n' "$output" | /usr/bin/awk -v label="\"$label\"" '
    $1 == label && $2 == "=>" { count++; value=$3 }
    END { exit !(count == 1 && (value == "disabled" || value == "true")) }
  ' || refuse "UNINSTALL_DISABLED_STATE_UNPROVEN"
}

is_absent() {
  local label="$1" output rc expected
  if output="$(/bin/launchctl print "system/$label" 2>&1)"; then
    return 1
  else
    rc=$?
  fi
  expected="Bad request.
Could not find service \"$label\" in domain for system"
  [ "$rc" -eq 113 ] && [ "$output" = "$expected" ] && return 0
  return 2
}

stop_and_prove_absent() {
  local label="$1" probe rc
  /bin/launchctl disable "system/$label" \
    || refuse "UNINSTALL_DISABLE_FAILED"
  assert_disabled "$label"
  # A bootout error is ambiguous. Reconcile through native readback, never
  # delete a plist or call removal successful just because bootout returned.
  /bin/launchctl bootout "system/$label" >/dev/null 2>&1 || true
  for probe in 1 2 3 4 5; do
    if is_absent "$label"; then
      return 0
    else
      rc=$?
    fi
    [ "$rc" -eq 1 ] || refuse "UNINSTALL_SERVICE_STATE_UNKNOWN"
    /bin/sleep 1
  done
  refuse "UNINSTALL_SERVICE_STILL_LOADED"
}

assert_no_unresolved_privileged_effect() {
  local ancestor
  for ancestor in "/var/db/mastermind-executive" "/var/db/mastermind-executive/privileged-actions" "$RECEIPT_ROOT" "$INFLIGHT_ROOT"; do
    [ ! -L "$ancestor" ] || refuse "UNINSTALL_RECEIPT_PATH_UNSAFE"
    if [ -e "$ancestor" ]; then
      [ -d "$ancestor" ] && [ -r "$ancestor" ] && [ -x "$ancestor" ] \
        || refuse "UNINSTALL_RECEIPT_PATH_UNREADABLE"
    fi
  done
  # After socket/registration removal no new broker request can be admitted.
  # A surviving marker may represent an escaped child or a lost terminal
  # receipt. Preserve it; stopping launchd is not proof that its effect ended.
  shopt -s nullglob dotglob
  local pending=("$INFLIGHT_ROOT"/* "$RECEIPT_ROOT"/*.inflight.json)
  if [ "${#pending[@]}" -ne 0 ]; then
    /bin/echo "EFFECT_RECONCILIATION_REQUIRED: registration stopped; privileged evidence preserved" >&2
    exit 75
  fi
}

# Revoke the root admission boundary before the ordinary services. An old host
# with no broker is valid only when launchd proves the exact label absent.
stop_and_prove_absent "$PRIVILEGED_LABEL"
[ ! -e "$PRIVILEGED_SOCKET" ] && [ ! -L "$PRIVILEGED_SOCKET" ] \
  || refuse "UNINSTALL_PRIVILEGED_SOCKET_STILL_PRESENT"
assert_no_unresolved_privileged_effect

if [ "$PRIVILEGED_ONLY" != "true" ]; then
  stop_and_prove_absent "$CONTROL_LABEL"
  stop_and_prove_absent "$WORKER_LABEL"
fi
# Nothing private is deleted. launchd owns socket removal; this script removes
# only these exact registration plists after all required native proofs pass.
if [ "$PRIVILEGED_ONLY" = "true" ]; then
  /bin/rm -f -- "$PRIVILEGED_PLIST"
  [ ! -e "$PRIVILEGED_PLIST" ] && [ ! -L "$PRIVILEGED_PLIST" ] \
    || refuse "UNINSTALL_PLIST_REMOVAL_UNPROVEN"
  /bin/echo "Executive privileged broker registration removed"
else
  /bin/rm -f -- "$PRIVILEGED_PLIST" "$CONTROL_PLIST" "$WORKER_PLIST"
  for path in "$PRIVILEGED_PLIST" "$CONTROL_PLIST" "$WORKER_PLIST"; do
    [ ! -e "$path" ] && [ ! -L "$path" ] \
      || refuse "UNINSTALL_PLIST_REMOVAL_UNPROVEN"
  done
  /bin/echo "Executive OS launchd services removed"
fi
/bin/echo "preserved: /var/db/mastermind-executive and /Library/Application Support/MastermindExecutive"
