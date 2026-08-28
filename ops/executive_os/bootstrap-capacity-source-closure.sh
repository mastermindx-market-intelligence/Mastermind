#!/bin/bash
# Unprivileged, disposable CF2-H0 exact-commit carrier bootstrap.
exec 2>/dev/null
set -u
set -o pipefail
umask 077

ROOT_NAMESPACE="/private/var/root/mastermind-h0-root-carrier"
ROOT_NAMESPACE_CREATED=0
FINISHED=0
TEST_ADAPTER="false"
ACTIVE_CHILD_PID=""
ACTIVE_CHILD_PGID=""
CHILD_OUTPUT=""
CHILD_GATE=""
CHILD_REGISTRATION_ACTIVE=0
PENDING_INTERRUPT=0
CARRIER_STATUS=65
CARRIER_OUTPUT="H0_SOURCE_CLOSURE_REPAIR_REFUSED"
EXPECTED_UID=0
EXPECTED_GID=0
INSTALL_OWNER="root"
INSTALL_GROUP="wheel"
INSTALL_PRINCIPAL="root:wheel"

REFUSED_OUTPUT="H0_SOURCE_CLOSURE_REPAIR_REFUSED"
INTERRUPTED_OUTPUT="H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER"

valid_commit() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }
valid_digest() { [[ "$1" =~ ^[0-9a-f]{64}$ ]]; }
valid_local_name() { [[ "$1" =~ ^[a-z_][a-z0-9._-]{0,63}$ ]]; }
valid_absolute_path() {
  local value="$1"
  case "$value" in
    /*) ;;
    *) return 1 ;;
  esac
  case "$value" in
    /|*/|*//*|*/./*|*/../*|*/.|*/..|*$'\r'*|*$'\n'*) return 1 ;;
  esac
  return 0
}

run_root() {
  if [ "$TEST_ADAPTER" = "true" ]; then
    "$@"
  else
    /usr/bin/sudo "$@"
  fi
}

safe_root_git() {
  run_root /usr/bin/env -i \
    HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_LOCAL=/dev/null \
    GIT_ATTR_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false GIT_OPTIONAL_LOCKS=0 GIT_NO_LAZY_FETCH=1 \
    GIT_NO_REPLACE_OBJECTS=1 GIT_EXTERNAL_DIFF=/usr/bin/false GIT_ALLOW_PROTOCOL=file \
    /usr/bin/git --no-replace-objects \
      -c protocol.allow=never -c protocol.file.allow=always \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.attributesFile=/dev/null -c diff.external=/usr/bin/false "$@"
}

run_authenticated_carrier() {
  run_root /usr/bin/env -i \
    HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
    /bin/bash "$@"
}

active_child_group_exists() {
  [ -n "$ACTIVE_CHILD_PGID" ] \
    && run_root /bin/kill -0 -- "-$ACTIVE_CHILD_PGID"
}

terminate_active_child() {
  local attempts=0
  [ -n "$ACTIVE_CHILD_PID" ] || return 0

  run_root /bin/kill -TERM -- "-$ACTIVE_CHILD_PGID" || true
  while active_child_group_exists && [ "$attempts" -lt 10 ]; do
    /bin/sleep 0.1
    attempts=$((attempts + 1))
  done
  if active_child_group_exists; then
    run_root /bin/kill -KILL -- "-$ACTIVE_CHILD_PGID" || true
  fi
  wait "$ACTIVE_CHILD_PID" || true

  attempts=0
  while active_child_group_exists && [ "$attempts" -lt 50 ]; do
    /bin/sleep 0.1
    attempts=$((attempts + 1))
  done
  if active_child_group_exists; then
    return 1
  fi
  ACTIVE_CHILD_PID=""
  ACTIVE_CHILD_PGID=""
  return 0
}

run_authenticated_carrier_tracked() {
  local child_status
  if [ "$TEST_ADAPTER" = "true" ]; then
    CHILD_OUTPUT="$(/usr/bin/mktemp \
      "$MMX_H0_BOOTSTRAP_TEST_ROOT/child-output.XXXXXXXX")" \
      || finish 65 "$REFUSED_OUTPUT"
    CHILD_GATE="$(/usr/bin/mktemp \
      "$MMX_H0_BOOTSTRAP_TEST_ROOT/child-gate.XXXXXXXX")" \
      || finish 65 "$REFUSED_OUTPUT"
  else
    CHILD_OUTPUT="$(/usr/bin/mktemp \
      /private/tmp/mastermind-h0-child-output.XXXXXXXX)" \
      || finish 65 "$REFUSED_OUTPUT"
    CHILD_GATE="$(/usr/bin/mktemp \
      /private/tmp/mastermind-h0-child-gate.XXXXXXXX)" \
      || finish 65 "$REFUSED_OUTPUT"
  fi
  /bin/chmod 0600 "$CHILD_OUTPUT" || finish 65 "$REFUSED_OUTPUT"
  /bin/chmod 0600 "$CHILD_GATE" || finish 65 "$REFUSED_OUTPUT"

  set -m
  PENDING_INTERRUPT=0
  CHILD_REGISTRATION_ACTIVE=1
  (
    while [ -e "$CHILD_GATE" ]; do
      /bin/sleep 0.01
    done
    run_authenticated_carrier "$@"
  ) >"$CHILD_OUTPUT" &
  ACTIVE_CHILD_PID=$!
  ACTIVE_CHILD_PGID=$ACTIVE_CHILD_PID
  CHILD_REGISTRATION_ACTIVE=0
  if [ "$PENDING_INTERRUPT" -eq 1 ]; then
    interrupted
  fi
  /bin/rm -f "$CHILD_GATE" || finish 65 "$REFUSED_OUTPUT"
  [ ! -e "$CHILD_GATE" ] || finish 65 "$REFUSED_OUTPUT"
  CHILD_GATE=""
  wait "$ACTIVE_CHILD_PID"
  child_status=$?
  ACTIVE_CHILD_PID=""
  ACTIVE_CHILD_PGID=""
  set +m

  CARRIER_OUTPUT="$(/bin/cat "$CHILD_OUTPUT")" \
    || finish 65 "$REFUSED_OUTPUT"
  /bin/rm -f "$CHILD_OUTPUT" || finish 65 "$REFUSED_OUTPUT"
  [ ! -e "$CHILD_OUTPUT" ] || finish 65 "$REFUSED_OUTPUT"
  CHILD_OUTPUT=""
  CARRIER_STATUS=$child_status
}

cleanup_namespace() {
  local cleanup_failed=0
  if [ -n "$CHILD_GATE" ]; then
    /bin/rm -f "$CHILD_GATE" || cleanup_failed=1
    if [ -e "$CHILD_GATE" ]; then
      cleanup_failed=1
    else
      CHILD_GATE=""
    fi
  fi
  if [ -n "$CHILD_OUTPUT" ]; then
    /bin/rm -f "$CHILD_OUTPUT" || cleanup_failed=1
    if [ -e "$CHILD_OUTPUT" ]; then
      cleanup_failed=1
    else
      CHILD_OUTPUT=""
    fi
  fi
  if [ -n "$ACTIVE_CHILD_PID" ]; then
    cleanup_failed=1
  fi
  if [ "$ROOT_NAMESPACE_CREATED" -eq 1 ]; then
    if [ -n "$ACTIVE_CHILD_PID" ]; then
      cleanup_failed=1
    else
      run_root /bin/rm -rf "$ROOT_NAMESPACE" || cleanup_failed=1
      if run_root /bin/test -e "$ROOT_NAMESPACE"; then
        cleanup_failed=1
      else
        ROOT_NAMESPACE_CREATED=0
      fi
    fi
    if [ "$TEST_ADAPTER" = "true" ] \
      && [ "${MMX_H0_BOOTSTRAP_TEST_CLEANUP_FAIL:-}" = "1" ]; then
      cleanup_failed=1
    fi
  fi
  return "$cleanup_failed"
}

finish() {
  local code="$1" output="$2"
  trap - EXIT HUP INT TERM
  FINISHED=1
  if ! cleanup_namespace; then
    if [ "$code" -eq 0 ]; then
      code=65
      output="$REFUSED_OUTPUT"
    fi
  fi
  /usr/bin/printf '%s\n' "$output"
  exit "$code"
}

unexpected_exit() {
  if [ "$FINISHED" -eq 0 ]; then
    terminate_active_child || true
    finish 65 "$REFUSED_OUTPUT"
  fi
}

interrupted() {
  trap - HUP INT TERM
  CHILD_REGISTRATION_ACTIVE=0
  terminate_active_child || true
  finish 70 "$INTERRUPTED_OUTPUT"
}

signal_received() {
  if [ "$CHILD_REGISTRATION_ACTIVE" -eq 1 ]; then
    PENDING_INTERRUPT=1
    return 0
  fi
  interrupted
}

finish_carrier_failure() {
  local code="$1" output="$2"
  case "$code:$output" in
    "64:INVALID_INVOCATION"|\
    "65:H0_SOURCE_CLOSURE_REPAIR_REFUSED"|\
    "70:H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER"|\
    "75:H0_LOCK_HELD"|\
    "77:ROOT_REQUIRED")
      finish "$code" "$output"
      ;;
    *)
      finish 65 "$REFUSED_OUTPUT"
      ;;
  esac
}

trap unexpected_exit EXIT
trap signal_received HUP INT TERM

CALLER_UID="$(/usr/bin/id -u)" || finish 64 "INVALID_INVOCATION"
CALLER_USER="$(/usr/bin/id -un)" || finish 64 "INVALID_INVOCATION"
case "$CALLER_UID" in
  0|[1-9][0-9]*) ;;
  *) finish 64 "INVALID_INVOCATION" ;;
esac
valid_local_name "$CALLER_USER" || finish 64 "INVALID_INVOCATION"
[ "$CALLER_UID" -ne 0 ] || finish 64 "INVALID_INVOCATION"

if [ -n "${MMX_H0_BOOTSTRAP_TEST_ROOT:-}" ]; then
  valid_absolute_path "$MMX_H0_BOOTSTRAP_TEST_ROOT" || finish 64 "INVALID_INVOCATION"
  case "$MMX_H0_BOOTSTRAP_TEST_ROOT" in
    /private/tmp/*|/private/var/folders/*) ;;
    *) finish 64 "INVALID_INVOCATION" ;;
  esac
  [ -d "$MMX_H0_BOOTSTRAP_TEST_ROOT" ] || finish 64 "INVALID_INVOCATION"
  TEST_ADAPTER="true"
  ROOT_NAMESPACE="$MMX_H0_BOOTSTRAP_TEST_ROOT/mastermind-h0-root-carrier"
  EXPECTED_UID="$(/usr/bin/id -u)"
  EXPECTED_GID="$(/usr/bin/id -g)"
  INSTALL_OWNER="$EXPECTED_UID"
  INSTALL_GROUP="$EXPECTED_GID"
  INSTALL_PRINCIPAL="$EXPECTED_UID:$EXPECTED_GID"
  case "${MMX_H0_BOOTSTRAP_TEST_CALLER_UID:-$CALLER_UID}" in
    0|[1-9][0-9]*) CALLER_UID="${MMX_H0_BOOTSTRAP_TEST_CALLER_UID:-$CALLER_UID}" ;;
    *) finish 64 "INVALID_INVOCATION" ;;
  esac
fi

[ "$CALLER_UID" -ne 0 ] || finish 64 "INVALID_INVOCATION"

if [ "$#" -ne 6 ] \
  || ! valid_commit "$1" \
  || ! valid_local_name "$2" \
  || ! valid_absolute_path "$3" \
  || ! valid_digest "$4" \
  || ! valid_absolute_path "$5" \
  || ! valid_digest "$6"; then
  finish 64 "INVALID_INVOCATION"
fi

REPAIR_MERGE_SHA="$1"
OPERATOR_USER="$2"
MACRO_TRANSPORT="$3"
MACRO_TRANSPORT_SHA256="$4"
REPAIR_BUNDLE="$5"
REPAIR_BUNDLE_SHA256="$6"
[ "$OPERATOR_USER" = "$CALLER_USER" ] || finish 64 "INVALID_INVOCATION"

# The operator bundle is inert input. Refuse an initially observed symlink
# before any privileged namespace exists and freeze its source inode relation
# across the root-owned copy.
[ ! -L "$REPAIR_BUNDLE" ] || finish 65 "$REFUSED_OUTPUT"
[ -f "$REPAIR_BUNDLE" ] || finish 65 "$REFUSED_OUTPUT"
SOURCE_STATE_BEFORE="$(/usr/bin/stat -f '%HT|%l|%d|%i|%u|%g|%Lp' "$REPAIR_BUNDLE")" \
  || finish 65 "$REFUSED_OUTPUT"
case "$SOURCE_STATE_BEFORE" in
  "Regular File|1|"*) ;;
  *) finish 65 "$REFUSED_OUTPUT" ;;
esac

# mkdir is the sole creator and therefore the no-replace authority. An old
# literal namespace is refused and never removed by this invocation.
run_root /bin/mkdir "$ROOT_NAMESPACE" || finish 65 "$REFUSED_OUTPUT"
ROOT_NAMESPACE_CREATED=1
if [ "$TEST_ADAPTER" = "true" ]; then
  run_root /bin/chmod 0700 "$ROOT_NAMESPACE" || finish 65 "$REFUSED_OUTPUT"
else
  run_root /usr/sbin/chown root:wheel "$ROOT_NAMESPACE" || finish 65 "$REFUSED_OUTPUT"
  run_root /usr/bin/chflags 0 "$ROOT_NAMESPACE" || finish 65 "$REFUSED_OUTPUT"
  run_root /bin/chmod -N "$ROOT_NAMESPACE" || finish 65 "$REFUSED_OUTPUT"
  run_root /usr/bin/xattr -c "$ROOT_NAMESPACE" || finish 65 "$REFUSED_OUTPUT"
  run_root /bin/chmod 0700 "$ROOT_NAMESPACE" || finish 65 "$REFUSED_OUTPUT"
fi

if [ "$TEST_ADAPTER" = "true" ] \
  && [ -n "${MMX_H0_BOOTSTRAP_TEST_PAUSE_MARKER:-}" ]; then
  valid_absolute_path "$MMX_H0_BOOTSTRAP_TEST_PAUSE_MARKER" \
    || finish 65 "$REFUSED_OUTPUT"
  /usr/bin/touch "$MMX_H0_BOOTSTRAP_TEST_PAUSE_MARKER" \
    || finish 65 "$REFUSED_OUTPUT"
  while [ -e "$MMX_H0_BOOTSTRAP_TEST_PAUSE_MARKER" ]; do
    /bin/sleep 1
  done
fi

ROOT_BUNDLE="$ROOT_NAMESPACE/repair.bundle"
ROOT_REPOSITORY="$ROOT_NAMESPACE/repository.git"
ROOT_CARRIER="$ROOT_NAMESPACE/carrier"

run_root /bin/cp -X "$REPAIR_BUNDLE" "$ROOT_BUNDLE" \
  || finish 65 "$REFUSED_OUTPUT"
SOURCE_STATE_AFTER="$(/usr/bin/stat -f '%HT|%l|%d|%i|%u|%g|%Lp' "$REPAIR_BUNDLE")" \
  || finish 65 "$REFUSED_OUTPUT"
[ "$SOURCE_STATE_AFTER" = "$SOURCE_STATE_BEFORE" ] \
  || finish 65 "$REFUSED_OUTPUT"

if [ "$TEST_ADAPTER" = "true" ]; then
  run_root /bin/chmod 0400 "$ROOT_BUNDLE" || finish 65 "$REFUSED_OUTPUT"
else
  run_root /usr/sbin/chown root:wheel "$ROOT_BUNDLE" || finish 65 "$REFUSED_OUTPUT"
  run_root /usr/bin/chflags 0 "$ROOT_BUNDLE" || finish 65 "$REFUSED_OUTPUT"
  run_root /bin/chmod -N "$ROOT_BUNDLE" || finish 65 "$REFUSED_OUTPUT"
  run_root /usr/bin/xattr -c "$ROOT_BUNDLE" || finish 65 "$REFUSED_OUTPUT"
  run_root /bin/chmod 0400 "$ROOT_BUNDLE" || finish 65 "$REFUSED_OUTPUT"
fi
ROOT_BUNDLE_STATE="$(run_root /usr/bin/stat -f '%HT|%l|%u|%g|%Lp' "$ROOT_BUNDLE")" \
  || finish 65 "$REFUSED_OUTPUT"
[ "$ROOT_BUNDLE_STATE" = "Regular File|1|$EXPECTED_UID|$EXPECTED_GID|400" ] \
  || finish 65 "$REFUSED_OUTPUT"
ROOT_BUNDLE_DIGEST_LINE="$(run_root /usr/bin/shasum -a 256 "$ROOT_BUNDLE")" \
  || finish 65 "$REFUSED_OUTPUT"
ROOT_BUNDLE_DIGEST="${ROOT_BUNDLE_DIGEST_LINE%% *}"
[ "$ROOT_BUNDLE_DIGEST" = "$REPAIR_BUNDLE_SHA256" ] \
  || finish 65 "$REFUSED_OUTPUT"

safe_root_git init --bare --quiet "$ROOT_REPOSITORY" \
  || finish 65 "$REFUSED_OUTPUT"
safe_root_git -C "$ROOT_REPOSITORY" bundle verify "$ROOT_BUNDLE" >/dev/null \
  || finish 65 "$REFUSED_OUTPUT"
safe_root_git -C "$ROOT_REPOSITORY" bundle unbundle "$ROOT_BUNDLE" >/dev/null \
  || finish 65 "$REFUSED_OUTPUT"
AUTHENTICATED_COMMIT="$(safe_root_git -C "$ROOT_REPOSITORY" rev-parse --verify \
  "$REPAIR_MERGE_SHA^{commit}")" || finish 65 "$REFUSED_OUTPUT"
[ "$AUTHENTICATED_COMMIT" = "$REPAIR_MERGE_SHA" ] \
  || finish 65 "$REFUSED_OUTPUT"
[ "$(safe_root_git -C "$ROOT_REPOSITORY" rev-parse --show-object-format)" = "sha1" ] \
  || finish 65 "$REFUSED_OUTPUT"

run_root /usr/bin/install -d -m 0700 -o "$INSTALL_OWNER" -g "$INSTALL_GROUP" \
  "$ROOT_CARRIER" "$ROOT_CARRIER/ops" "$ROOT_CARRIER/ops/executive_os" \
  || finish 65 "$REFUSED_OUTPUT"

MATERIAL_PATHS=(
  ops/executive_os/repair-capacity-source-closure.sh
  ops/executive_os/capacity_host_artifacts.py
  ops/executive_os/capacity_source_contract.py
  ops/executive_os/provider_worker_slots.py
  ops/executive_os/provider_identity_policy.py
)
for MATERIAL_PATH in "${MATERIAL_PATHS[@]}"; do
  case "$MATERIAL_PATH" in
    ops/executive_os/repair-capacity-source-closure.sh)
      GIT_MODE=100755
      HOST_MODE=0500
      ;;
    *)
      GIT_MODE=100644
      HOST_MODE=0400
      ;;
  esac
  TREE_ROW="$(safe_root_git -C "$ROOT_REPOSITORY" ls-tree \
    "$REPAIR_MERGE_SHA" -- "$MATERIAL_PATH")" || finish 65 "$REFUSED_OUTPUT"
  if [[ ! "$TREE_ROW" =~ ^$GIT_MODE\ blob\ ([0-9a-f]{40})$'\t'"$MATERIAL_PATH"$ ]]; then
    finish 65 "$REFUSED_OUTPUT"
  fi
  GIT_BLOB="${BASH_REMATCH[1]}"
  DESTINATION="$ROOT_CARRIER/$MATERIAL_PATH"
  run_root /usr/bin/touch "$DESTINATION" || finish 65 "$REFUSED_OUTPUT"
  run_root /usr/sbin/chown "$INSTALL_PRINCIPAL" "$DESTINATION" \
    || finish 65 "$REFUSED_OUTPUT"
  run_root /bin/chmod 0600 "$DESTINATION" || finish 65 "$REFUSED_OUTPUT"
  safe_root_git -C "$ROOT_REPOSITORY" cat-file blob "$GIT_BLOB" \
    | run_root /bin/dd "of=$DESTINATION" bs=65536 \
    || finish 65 "$REFUSED_OUTPUT"
  if [ "$TEST_ADAPTER" != "true" ]; then
    run_root /usr/bin/chflags 0 "$DESTINATION" || finish 65 "$REFUSED_OUTPUT"
    run_root /bin/chmod -N "$DESTINATION" || finish 65 "$REFUSED_OUTPUT"
    run_root /usr/bin/xattr -c "$DESTINATION" || finish 65 "$REFUSED_OUTPUT"
  fi
  run_root /bin/chmod "$HOST_MODE" "$DESTINATION" || finish 65 "$REFUSED_OUTPUT"
  [ "$(safe_root_git hash-object --no-filters "$DESTINATION")" = "$GIT_BLOB" ] \
    || finish 65 "$REFUSED_OUTPUT"
done

run_root /usr/bin/touch "$ROOT_CARRIER/.repair-carrier-commit" \
  || finish 65 "$REFUSED_OUTPUT"
run_root /usr/sbin/chown "$INSTALL_PRINCIPAL" \
  "$ROOT_CARRIER/.repair-carrier-commit" || finish 65 "$REFUSED_OUTPUT"
run_root /bin/chmod 0600 "$ROOT_CARRIER/.repair-carrier-commit" \
  || finish 65 "$REFUSED_OUTPUT"
/usr/bin/printf '%s\n' "$REPAIR_MERGE_SHA" \
  | run_root /bin/dd "of=$ROOT_CARRIER/.repair-carrier-commit" bs=64 \
  || finish 65 "$REFUSED_OUTPUT"
if [ "$TEST_ADAPTER" != "true" ]; then
  run_root /usr/bin/chflags 0 "$ROOT_CARRIER/.repair-carrier-commit" \
    || finish 65 "$REFUSED_OUTPUT"
  run_root /bin/chmod -N "$ROOT_CARRIER/.repair-carrier-commit" \
    || finish 65 "$REFUSED_OUTPUT"
  run_root /usr/bin/xattr -c "$ROOT_CARRIER/.repair-carrier-commit" \
    || finish 65 "$REFUSED_OUTPUT"
fi
run_root /bin/chmod 0400 "$ROOT_CARRIER/.repair-carrier-commit" \
  || finish 65 "$REFUSED_OUTPUT"

# Every executable/interpreted carrier byte is independently rebound to the
# authenticated commit immediately before the first Python or shell launch.
for MATERIAL_PATH in "${MATERIAL_PATHS[@]}"; do
  TREE_ROW="$(safe_root_git -C "$ROOT_REPOSITORY" ls-tree \
    "$REPAIR_MERGE_SHA" -- "$MATERIAL_PATH")" || finish 65 "$REFUSED_OUTPUT"
  if [[ ! "$TREE_ROW" =~ ^[0-9]{6}\ blob\ ([0-9a-f]{40})$'\t'"$MATERIAL_PATH"$ ]]; then
    finish 65 "$REFUSED_OUTPUT"
  fi
  [ "$(safe_root_git hash-object --no-filters "$ROOT_CARRIER/$MATERIAL_PATH")" = \
    "${BASH_REMATCH[1]}" ] || finish 65 "$REFUSED_OUTPUT"
done

run_root /usr/bin/env -i \
  HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
  /usr/bin/python3 -I -S -B \
    "$ROOT_CARRIER/ops/executive_os/capacity_host_artifacts.py" \
    verify-repair-carrier --path "$ROOT_CARRIER" --repository "$ROOT_REPOSITORY" \
    --expected-commit "$REPAIR_MERGE_SHA" --expected-uid "$EXPECTED_UID" \
    --expected-gid "$EXPECTED_GID" >/dev/null \
  || finish 65 "$REFUSED_OUTPUT"

run_authenticated_carrier_tracked \
  "$ROOT_CARRIER/ops/executive_os/repair-capacity-source-closure.sh" repair \
  --expected-source-closure-repair-commit "$REPAIR_MERGE_SHA" \
  --operator-user "$OPERATOR_USER" \
  --macro-transport "$MACRO_TRANSPORT" \
  --macro-transport-sha256 "$MACRO_TRANSPORT_SHA256"
REPAIR_OUTPUT="$CARRIER_OUTPUT"
REPAIR_STATUS="$CARRIER_STATUS"
if [ "$REPAIR_STATUS" -ne 0 ]; then
  finish_carrier_failure "$REPAIR_STATUS" "$REPAIR_OUTPUT"
fi
[ "$REPAIR_OUTPUT" = "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED" ] \
  || finish 65 "$REFUSED_OUTPUT"

run_authenticated_carrier_tracked \
  "$ROOT_CARRIER/ops/executive_os/repair-capacity-source-closure.sh" verify-only \
  --expected-source-closure-repair-commit "$REPAIR_MERGE_SHA"
VERIFY_ONE_OUTPUT="$CARRIER_OUTPUT"
VERIFY_ONE_STATUS="$CARRIER_STATUS"
if [ "$VERIFY_ONE_STATUS" -ne 0 ]; then
  finish_carrier_failure "$VERIFY_ONE_STATUS" "$VERIFY_ONE_OUTPUT"
fi
[ "$VERIFY_ONE_OUTPUT" = "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED" ] \
  || finish 65 "$REFUSED_OUTPUT"

run_authenticated_carrier_tracked \
  "$ROOT_CARRIER/ops/executive_os/repair-capacity-source-closure.sh" verify-only \
  --expected-source-closure-repair-commit "$REPAIR_MERGE_SHA"
VERIFY_TWO_OUTPUT="$CARRIER_OUTPUT"
VERIFY_TWO_STATUS="$CARRIER_STATUS"
if [ "$VERIFY_TWO_STATUS" -ne 0 ]; then
  finish_carrier_failure "$VERIFY_TWO_STATUS" "$VERIFY_TWO_OUTPUT"
fi
[ "$VERIFY_TWO_OUTPUT" = "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED" ] \
  || finish 65 "$REFUSED_OUTPUT"

finish 0 "$REPAIR_OUTPUT
$VERIFY_ONE_OUTPUT
$VERIFY_TWO_OUTPUT"
