#!/bin/bash
# One-time, root-only macOS account and filesystem bootstrap for Executive OS.
# This script never installs code, copies credentials, starts services, or
# removes existing data. Re-running it verifies the established identities.
set -euo pipefail
umask 077

CONTROL_USER="_mastermind_exec"
CONTROL_GROUP="_mastermind_exec"
WORKER_USER="_mastermind_worker"
WORKER_GROUP="_mastermind_worker"
OPS_GROUP="_mastermind_ops"
CONTROL_UID="450"
CONTROL_GID="450"
WORKER_UID="451"
WORKER_GID="451"
OPS_GID="453"
OPERATOR_USER=""

usage() {
  /bin/echo "usage: $0 --operator-user NAME [--control-uid N] [--worker-uid N] [--ops-gid N]" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --operator-user) OPERATOR_USER="${2:-}"; shift 2 ;;
    --control-uid) CONTROL_UID="${2:-}"; CONTROL_GID="${2:-}"; shift 2 ;;
    --worker-uid) WORKER_UID="${2:-}"; WORKER_GID="${2:-}"; shift 2 ;;
    --ops-gid) OPS_GID="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "bootstrap-host.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "bootstrap-host.sh supports macOS only" >&2
  exit 69
}
[ -n "$OPERATOR_USER" ] || usage
case "$OPERATOR_USER" in
  [A-Za-z_]* ) ;;
  *) /bin/echo "operator account name is invalid" >&2; exit 65 ;;
esac
case "$OPERATOR_USER" in *[!A-Za-z0-9_.-]*) /bin/echo "operator account name is invalid" >&2; exit 65 ;; esac
/usr/bin/id "$OPERATOR_USER" >/dev/null 2>&1 || {
  /bin/echo "operator user does not exist: $OPERATOR_USER" >&2
  exit 65
}
OPERATOR_UID="$(/usr/bin/id -u "$OPERATOR_USER")"

for numeric in "$CONTROL_UID" "$WORKER_UID" "$OPS_GID"; do
  case "$numeric" in
    ''|*[!0-9]*) /bin/echo "UID/GID values must be decimal integers" >&2; exit 65 ;;
  esac
  [ "$numeric" -ge 400 ] && [ "$numeric" -lt 500 ] || {
    /bin/echo "service UID/GID values must be in the reviewed 400-499 range" >&2
    exit 65
  }
done
[ "$CONTROL_UID" -ne "$WORKER_UID" ] || {
  /bin/echo "control and worker UIDs must be distinct" >&2
  exit 65
}

read_attribute() {
  local record="$1"
  local attribute="$2"
  LC_ALL=C LANG=C /usr/bin/dscl . -read "$record" "$attribute" 2>/dev/null \
    | /usr/bin/awk -v attribute="$attribute" '
        NR == 1 {
          standard=attribute ":"
          native="dsAttrTypeNative:" attribute ":"
          if (index($0, standard) == 1) {
            value=substr($0, length(standard) + 1)
          } else if (index($0, native) == 1) {
            value=substr($0, length(native) + 1)
          } else {
            malformed=1
            next
          }
          sub(/^[[:space:]]*/, "", value)
          next
        }
        {value=value " " $0}
        END {
          if (NR == 0 || malformed) exit 65
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
          print value
        }
      '
}

valid_uuid() {
  /bin/echo "$1" | /usr/bin/grep -Eq \
    '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'
}

sorted_words() {
  /bin/echo "$1" | /usr/bin/awk '{for (index=1; index<=NF; index++) print $index}' \
    | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
}

assert_reviewed_authentication_authority() {
  local name="$1"
  local authority authority_err authority_error authority_out authority_status
  authority_out="$(/usr/bin/mktemp /private/tmp/mastermind-authority.stdout.XXXXXX)"
  authority_err="$(/usr/bin/mktemp /private/tmp/mastermind-authority.stderr.XXXXXX)"
  if LC_ALL=C LANG=C /usr/bin/dscl . -read "/Users/$name" AuthenticationAuthority \
    >"$authority_out" 2>"$authority_err"; then
    authority_status=0
  else
    authority_status=$?
  fi
  authority="$(/bin/cat "$authority_out")"
  authority_error="$(/bin/cat "$authority_err")"
  /bin/rm -f -- "$authority_out" "$authority_err"
  [ "$authority_status" -eq 0 ] || {
    /bin/echo "could not inspect the authentication authority for $name" >&2
    exit 65
  }
  case "$authority|$authority_error" in
    '|No such key: AuthenticationAuthority') authority='' ;;
    'AuthenticationAuthority: ;DisabledUser;|') authority=';DisabledUser;' ;;
    *)
      /bin/echo "service account $name has an unreadable authentication authority" >&2
      exit 65
      ;;
  esac
  case "$authority" in
    ''|';DisabledUser;') ;;
    *)
      /bin/echo "service account $name has an unreviewed authentication authority" >&2
      exit 65
      ;;
  esac
}

authentication_state() {
  local name="$1"
  local disabled_expected observed probe status unsupported_expected
  probe="$(/usr/bin/uuidgen)"
  if observed="$(LC_ALL=C LANG=C /usr/bin/dscl . -authonly "$name" "$probe" 2>&1)"; then
    status=0
  else
    status=$?
  fi
  disabled_expected='<dscl_cmd> DS Error: -14167 (eDSAuthAccountDisabled)
Authentication for node /Local/Default failed. (-14167, eDSAuthAccountDisabled)'
  unsupported_expected='<dscl_cmd> DS Error: -14091 (eDSAuthMethodNotSupported)
Authentication for node /Local/Default failed. (-14091, eDSAuthMethodNotSupported)'
  if [ "$status" -eq 87 ] && [ "$observed" = "$disabled_expected" ]; then
    /bin/echo disabled
    return
  fi
  if [ "$status" -eq 11 ] && [ "$observed" = "$unsupported_expected" ]; then
    /bin/echo needs_disable
    return
  fi
  /bin/echo "service account $name has an unreviewed authentication state" >&2
  return 65
}

assert_authentication_disabled() {
  local name="$1"
  local state
  assert_reviewed_authentication_authority "$name"
  state="$(authentication_state "$name")" || {
    /bin/echo "could not inspect authentication for service account $name" >&2
    exit 65
  }
  [ "$state" = disabled ] || {
    /bin/echo "service account $name is not authentication-disabled" >&2
    exit 65
  }
}

ensure_authentication_disabled() {
  local name="$1"
  local state
  assert_reviewed_authentication_authority "$name"
  state="$(authentication_state "$name")" || exit 65
  if [ "$state" = needs_disable ]; then
    LC_ALL=C LANG=C /usr/bin/pwpolicy -n /Local/Default -u "$name" -disableuser \
      >/dev/null 2>&1 || {
      /bin/echo "could not disable authentication for service account $name" >&2
      exit 65
    }
  fi
  assert_authentication_disabled "$name"
}

ensure_numeric_unused() {
  local record_type="$1"
  local attribute="$2"
  local numeric="$3"
  local expected_name="$4"
  local owners
  owners="$(numeric_owners "$record_type" "$attribute" "$numeric")"
  if [ -n "$owners" ] && [ "$owners" != "$expected_name" ]; then
    /bin/echo "$attribute $numeric has a non-exact owner set: $owners" >&2
    exit 65
  fi
}

numeric_owners() {
  local record_type="$1"
  local attribute="$2"
  local numeric="$3"
  /usr/bin/dscl . -list "/$record_type" "$attribute" \
    | /usr/bin/awk -v numeric="$numeric" '$NF == numeric {print $1}' \
    | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
}

assert_numeric_owner() {
  local record_type="$1"
  local attribute="$2"
  local numeric="$3"
  local expected_name="$4"
  local owners
  owners="$(numeric_owners "$record_type" "$attribute" "$numeric")"
  [ "$owners" = "$expected_name" ] || {
    /bin/echo "$record_type $attribute $numeric owner set is not exactly $expected_name: $owners" >&2
    exit 65
  }
}

ensure_group() {
  local name="$1"
  local gid="$2"
  ensure_numeric_unused Groups PrimaryGroupID "$gid" "$name"
  if /usr/bin/dscl . -read "/Groups/$name" >/dev/null 2>&1; then
    [ "$(read_attribute "/Groups/$name" PrimaryGroupID)" = "$gid" ] || {
      /bin/echo "existing group $name has the wrong GID" >&2
      exit 65
    }
    [ "$(read_attribute "/Groups/$name" RealName)" = "$name service group" ] || {
      /bin/echo "existing group $name has the wrong reviewed identity" >&2
      exit 65
    }
    valid_uuid "$(read_attribute "/Groups/$name" GeneratedUID)" || {
      /bin/echo "existing group $name has no valid GeneratedUID" >&2
      exit 65
    }
    return
  fi
  /usr/bin/dscl . -create "/Groups/$name"
  /usr/bin/dscl . -create "/Groups/$name" PrimaryGroupID "$gid"
  /usr/bin/dscl . -create "/Groups/$name" RealName "$name service group"
  /usr/bin/dscl . -create "/Groups/$name" GeneratedUID "$(/usr/bin/uuidgen)"
}

ensure_user() {
  local name="$1"
  local uid="$2"
  local gid="$3"
  local home="$4"
  ensure_numeric_unused Users UniqueID "$uid" "$name"
  if /usr/bin/dscl . -read "/Users/$name" >/dev/null 2>&1; then
    [ "$(read_attribute "/Users/$name" UniqueID)" = "$uid" ] || {
      /bin/echo "existing user $name has the wrong UID" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" PrimaryGroupID)" = "$gid" ] || {
      /bin/echo "existing user $name has the wrong primary GID" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" RealName)" = "$name service account" ] || {
      /bin/echo "existing user $name has the wrong reviewed identity" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" NFSHomeDirectory)" = "$home" ] || {
      /bin/echo "existing user $name has the wrong home" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" UserShell)" = "/usr/bin/false" ] || {
      /bin/echo "existing user $name does not have the disabled shell" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" IsHidden)" = "1" ] || {
      /bin/echo "existing user $name is not hidden" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" Password)" = "*" ] || {
      /bin/echo "existing user $name does not have a disabled password" >&2
      exit 65
    }
    valid_uuid "$(read_attribute "/Users/$name" GeneratedUID)" || {
      /bin/echo "existing user $name has no valid GeneratedUID" >&2
      exit 65
    }
    ensure_authentication_disabled "$name"
    return
  fi
  /usr/bin/dscl . -create "/Users/$name"
  /usr/bin/dscl . -create "/Users/$name" UniqueID "$uid"
  /usr/bin/dscl . -create "/Users/$name" PrimaryGroupID "$gid"
  /usr/bin/dscl . -create "/Users/$name" RealName "$name service account"
  /usr/bin/dscl . -create "/Users/$name" NFSHomeDirectory "$home"
  /usr/bin/dscl . -create "/Users/$name" UserShell /usr/bin/false
  /usr/bin/dscl . -create "/Users/$name" IsHidden 1
  /usr/bin/dscl . -create "/Users/$name" Password '*'
  valid_uuid "$(read_attribute "/Users/$name" GeneratedUID)" || {
    /bin/echo "new user $name has no valid auto-generated GeneratedUID" >&2
    exit 65
  }
  ensure_authentication_disabled "$name"
}

SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
RUNTIME_ROOT="/var/db/mastermind-executive"
CONTROL_HOME="$RUNTIME_ROOT/control/home"
PROVIDER_HOME="$RUNTIME_ROOT/workers/codex-01/provider-home"

ensure_numeric_unused Users UniqueID "$OPERATOR_UID" "$OPERATOR_USER"
ensure_group "$CONTROL_GROUP" "$CONTROL_GID"
ensure_group "$WORKER_GROUP" "$WORKER_GID"
ensure_group "$OPS_GROUP" "$OPS_GID"
ensure_user "$CONTROL_USER" "$CONTROL_UID" "$CONTROL_GID" "$CONTROL_HOME"
ensure_user "$WORKER_USER" "$WORKER_UID" "$WORKER_GID" "$PROVIDER_HOME"

# Control may inspect worker-created run artifacts through the worker primary
# group. The worker LaunchDaemon sets InitGroups=false, so the worker receives
# no supplementary control/operator groups.
/usr/sbin/dseditgroup -o edit -a "$CONTROL_USER" -t user "$WORKER_GROUP"
/usr/sbin/dseditgroup -o edit -a "$OPERATOR_USER" -t user "$OPS_GROUP"

/usr/sbin/dseditgroup -o checkmember -m "$CONTROL_USER" "$WORKER_GROUP" \
  | /usr/bin/grep -q 'yes' || {
    /bin/echo "control user is not a member of the worker artifact group" >&2
    exit 65
  }
/usr/sbin/dseditgroup -o checkmember -m "$OPERATOR_USER" "$OPS_GROUP" \
  | /usr/bin/grep -q 'yes' || {
    /bin/echo "operator user is not a member of the Executive ops group" >&2
    exit 65
  }

assert_exact_members() {
  local group="$1"
  local gid="$2"
  local expected_primary="$3"
  local expected_named="$4"
  local primary named uuid_members expected_uuids nested member member_uuid
  primary="$(
    /usr/bin/dscl . -list /Users PrimaryGroupID \
      | /usr/bin/awk -v gid="$gid" '$NF == gid {print $1}' \
      | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
  )"
  [ "$primary" = "$(sorted_words "$expected_primary")" ] || {
    /bin/echo "group $group contains an unreviewed primary-GID user" >&2
    exit 65
  }
  named="$(read_attribute "/Groups/$group" GroupMembership 2>/dev/null || true)"
  named="$(sorted_words "$named")"
  [ "$named" = "$(sorted_words "$expected_named")" ] || {
    /bin/echo "group $group contains unreviewed members" >&2
    exit 65
  }
  expected_uuids=""
  for member in $expected_named; do
    member_uuid="$(read_attribute "/Users/$member" GeneratedUID)"
    valid_uuid "$member_uuid" || {
      /bin/echo "reviewed member $member has no valid GeneratedUID" >&2
      exit 65
    }
    expected_uuids="$expected_uuids $member_uuid"
  done
  uuid_members="$(read_attribute "/Groups/$group" GroupMembers 2>/dev/null || true)"
  uuid_members="$(sorted_words "$(/bin/echo "$uuid_members" | /usr/bin/tr '[:lower:]' '[:upper:]')")"
  expected_uuids="$(sorted_words "$(/bin/echo "$expected_uuids" | /usr/bin/tr '[:lower:]' '[:upper:]')")"
  [ "$uuid_members" = "$expected_uuids" ] || {
    /bin/echo "group $group contains UUID-only or stale members" >&2
    exit 65
  }
  nested="$(read_attribute "/Groups/$group" NestedGroups 2>/dev/null || true)"
  if [ -n "$(sorted_words "$nested")" ]; then
    /bin/echo "group $group contains unreviewed nested groups" >&2
    exit 65
  fi
}

assert_exact_members "$CONTROL_GROUP" "$CONTROL_GID" "$CONTROL_USER" ""
assert_exact_members "$WORKER_GROUP" "$WORKER_GID" "$WORKER_USER" "$CONTROL_USER"
assert_exact_members "$OPS_GROUP" "$OPS_GID" "" "$OPERATOR_USER"
assert_numeric_owner Users UniqueID "$CONTROL_UID" "$CONTROL_USER"
assert_numeric_owner Users UniqueID "$WORKER_UID" "$WORKER_USER"
assert_numeric_owner Users UniqueID "$OPERATOR_UID" "$OPERATOR_USER"
assert_numeric_owner Groups PrimaryGroupID "$CONTROL_GID" "$CONTROL_GROUP"
assert_numeric_owner Groups PrimaryGroupID "$WORKER_GID" "$WORKER_GROUP"
assert_numeric_owner Groups PrimaryGroupID "$OPS_GID" "$OPS_GROUP"

/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT"
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT/bin"
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT/config"
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT/releases"

/usr/bin/install -d -o root -g wheel -m 0711 "$RUNTIME_ROOT"
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/control"
for directory in home db policy admin-checkout launch-receipts backups canaries; do
  /usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/control/$directory"
done
/usr/bin/install -d -o "$CONTROL_USER" -g "$WORKER_GROUP" -m 0710 "$RUNTIME_ROOT/jobs"
/usr/bin/install -d -o "$CONTROL_USER" -g "$WORKER_GROUP" -m 0710 "$RUNTIME_ROOT/jobs/workspaces"
/usr/bin/install -d -o "$CONTROL_USER" -g "$WORKER_GROUP" -m 0710 "$RUNTIME_ROOT/jobs/runs"
/usr/bin/install -d -o root -g wheel -m 0711 "$RUNTIME_ROOT/workers"
/usr/bin/install -d -o "$WORKER_USER" -g "$WORKER_GROUP" -m 0700 "$RUNTIME_ROOT/workers/codex-01"
/usr/bin/install -d -o "$WORKER_USER" -g "$WORKER_GROUP" -m 0700 "$PROVIDER_HOME"
/usr/bin/install -d -o "$WORKER_USER" -g "$WORKER_GROUP" -m 0700 "$RUNTIME_ROOT/workers/codex-01/state"

# Explicit forbidden fixtures for the real secret-canary proof. Values are
# generated later by the acceptance command and never by this bootstrap.
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/canary-fixtures"
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/canary-fixtures/other-worker-home"
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/canary-fixtures/production-like"

/usr/bin/install -d -o root -g wheel -m 0755 /var/run/mastermind-executive
/usr/bin/install -d -o root -g wheel -m 0755 /var/log/mastermind-executive
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 /var/log/mastermind-executive/control
/usr/bin/install -d -o "$WORKER_USER" -g "$WORKER_GROUP" -m 0700 /var/log/mastermind-executive/worker

for protected_path in \
  "$SYSTEM_ROOT" "$SYSTEM_ROOT/bin" "$SYSTEM_ROOT/config" "$SYSTEM_ROOT/releases" \
  "$RUNTIME_ROOT" "$RUNTIME_ROOT/control" "$RUNTIME_ROOT/jobs" \
  "$RUNTIME_ROOT/jobs/workspaces" "$RUNTIME_ROOT/jobs/runs" \
  "$RUNTIME_ROOT/workers" "$RUNTIME_ROOT/workers/codex-01" "$PROVIDER_HOME" \
  /var/run/mastermind-executive /var/log/mastermind-executive; do
  case "$(/usr/bin/stat -f '%Sp' "$protected_path")" in
    *+) /bin/echo "unexpected filesystem ACL on $protected_path" >&2; exit 65 ;;
  esac
done

/bin/echo "host bootstrap complete"
/bin/echo "next: provision $PROVIDER_HOME/auth.json as $WORKER_USER mode 0600, then run install.sh"
