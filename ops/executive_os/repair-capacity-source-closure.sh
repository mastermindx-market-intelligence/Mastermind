#!/bin/bash
# Archive-only CF2-H0 complete-source repair. This file is inert until invoked.
exec 2>/dev/null
set -euo pipefail
umask 077

SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
LOCK_FILE="$SYSTEM_ROOT/locks/cf2-h0.lock"
MACRO_COMMIT="dcdd939c45b23abce5ba04f95e330ac914a3904b"

MODE=""
EXPECTED_REPAIR_COMMIT=""
OPERATOR_USER=""
MACRO_TRANSPORT=""
MACRO_TRANSPORT_SHA256=""

finish() {
  local code="$1" sentinel="$2"
  /usr/bin/printf '%s\n' "$sentinel"
  exit "$code"
}

invalid_invocation() { finish 64 "INVALID_INVOCATION"; }
refused() { finish 65 "H0_SOURCE_CLOSURE_REPAIR_REFUSED"; }
incomplete() { finish 70 "H0_SOURCE_CLOSURE_REPAIR_INCOMPLETE_RECONCILE_SAME_CARRIER"; }

valid_commit() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }
valid_digest() { [[ "$1" =~ ^[0-9a-f]{64}$ ]]; }
valid_local_name() { [[ "$1" =~ ^[a-z_][a-z0-9._-]{0,63}$ ]]; }
valid_absolute_transport() {
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

# Complete argv validation is deliberately earlier than root, checkout, lock,
# transport, or installed-host observation.
if [ "$#" -eq 3 ] \
  && [ "$1" = "verify-only" ] \
  && [ "$2" = "--expected-source-closure-repair-commit" ] \
  && valid_commit "$3"; then
  MODE="verify-only"
  EXPECTED_REPAIR_COMMIT="$3"
elif [ "$#" -eq 9 ] \
  && [ "$1" = "repair" ] \
  && [ "$2" = "--expected-source-closure-repair-commit" ] \
  && valid_commit "$3" \
  && [ "$4" = "--operator-user" ] \
  && valid_local_name "$5" \
  && [ "$6" = "--macro-transport" ] \
  && valid_absolute_transport "$7" \
  && [ "$8" = "--macro-transport-sha256" ] \
  && valid_digest "$9"; then
  MODE="repair"
  EXPECTED_REPAIR_COMMIT="$3"
  OPERATOR_USER="$5"
  MACRO_TRANSPORT="$7"
  MACRO_TRANSPORT_SHA256="$9"
else
  invalid_invocation
fi

# Resolve the already root-created carrier only after complete argv validation.
SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && /bin/pwd)"
CARRIER_ROOT="$(cd "$SCRIPT_DIR/../.." && /bin/pwd -P)"
CARRIER_REPOSITORY="$(cd "$CARRIER_ROOT/.." && /bin/pwd -P)/repository.git"
ARTIFACTS="$SCRIPT_DIR/capacity_host_artifacts.py"
CARRIER_STAMP="$CARRIER_ROOT/.repair-carrier-commit"

TEST_ADAPTER="false"
if [ -n "${MMX_CAPACITY_REPAIR_TEST_ROOT:-}" ] && [ "$(/usr/bin/id -u)" != "0" ]; then
  TEST_ADAPTER="true"
  SYSTEM_ROOT="$MMX_CAPACITY_REPAIR_TEST_ROOT"
  LOCK_FILE="$SYSTEM_ROOT/locks/cf2-h0.lock"
else
  [ "$(/usr/bin/id -u)" = "0" ] || finish 77 "ROOT_REQUIRED"
  [ -f "$CARRIER_STAMP" ] || refused
  /usr/bin/env -i \
    HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
    /usr/bin/python3 -I -S -B "$ARTIFACTS" verify-repair-carrier \
    --path "$CARRIER_ROOT" \
    --repository "$CARRIER_REPOSITORY" \
    --expected-commit "$EXPECTED_REPAIR_COMMIT" \
    --expected-uid 0 \
    --expected-gid 0 >/dev/null || refused
fi

PYTHON_ARGUMENTS=(
  source-repair-host
  --mode "$MODE"
  --system-root "$SYSTEM_ROOT"
  --lock-file "$LOCK_FILE"
  --expected-repair-commit "$EXPECTED_REPAIR_COMMIT"
  --expected-source-commit "$MACRO_COMMIT"
)
if [ "$MODE" = "repair" ]; then
  PYTHON_ARGUMENTS+=(
    --operator-user "$OPERATOR_USER"
    --transport "$MACRO_TRANSPORT"
    --transport-sha256 "$MACRO_TRANSPORT_SHA256"
  )
fi
if [ "$TEST_ADAPTER" = "true" ]; then
  PYTHON_ARGUMENTS+=(--test-adapter)
fi

set +e
if [ "$TEST_ADAPTER" = "true" ]; then
  /usr/bin/python3 -I -S -B "$ARTIFACTS" "${PYTHON_ARGUMENTS[@]}" >/dev/null
else
  /usr/bin/env -i \
    HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
    /usr/bin/python3 -I -S -B "$ARTIFACTS" "${PYTHON_ARGUMENTS[@]}" >/dev/null
fi
RESULT="$?"
set -e
case "$RESULT" in
  0)
    if [ "$MODE" = "verify-only" ]; then
      finish 0 "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"
    fi
    finish 0 "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
    ;;
  70) incomplete ;;
  75) finish 75 "H0_LOCK_HELD" ;;
  *) refused ;;
esac
