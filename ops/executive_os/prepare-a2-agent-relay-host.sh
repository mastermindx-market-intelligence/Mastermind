#!/bin/bash
# Credential-free host preparation for the private A2 Agent Relay.
#
# This source-owned entry point creates or verifies only the fixed service
# principal and non-secret prerequisite directories. It never enrolls a token,
# writes Relay configuration or a plist, or loads and starts a service.
set -euo pipefail
umask 077

SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
CONFIG_ROOT="$SYSTEM_ROOT/config"
RUNTIME_ROOT="/var/db/mastermind-agent-relay"
RELAY_HOME="$RUNTIME_ROOT/home"
TOKEN_PATH="$CONFIG_ROOT/agent-relay.token"
CONFIG_PATH="$CONFIG_ROOT/agent-relay.json"
PLIST_PATH="/Library/LaunchDaemons/com.mastermind.executive.agent-relay.plist"

RELAY_USER="_mastermind_agent_relay"
RELAY_GROUP="_mastermind_agent_relay"
RELAY_UID="457"
RELAY_GID="457"
EXEC_USER="_mastermind_exec"
EXEC_UID="450"
EXEC_GID="450"

RELEASE_ROOT=""

usage() {
  /bin/echo "usage: $0 --release-root /Library/Application\\ Support/MastermindExecutive/releases/<40hex>" >&2
  exit 64
}

refuse() {
  /bin/echo "A2 Agent Relay host preparation refused: $1" >&2
  exit 65
}

if [ "$(/usr/bin/uname -s)" != "Darwin" ]; then
  /bin/echo "prepare-a2-agent-relay-host.sh supports macOS only" >&2
  exit 69
fi

[ "$#" -eq 2 ] || usage
[ "$1" = "--release-root" ] || usage
RELEASE_ROOT="$2"
case "$RELEASE_ROOT" in
  "$SYSTEM_ROOT"/releases/*) ;;
  *) refuse "release root must be beneath the reviewed releases root" ;;
esac
RELEASE_SHA="${RELEASE_ROOT##*/}"
case "$RELEASE_SHA" in
  ''|*[!0-9a-f]*) refuse "release root must end in one full 40-character lowercase hexadecimal SHA" ;;
esac
[ "${#RELEASE_SHA}" -eq 40 ] || {
  refuse "release root must end in one full 40-character lowercase hexadecimal SHA"
}
[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "prepare-a2-agent-relay-host.sh must run as root" >&2
  exit 77
}

[ -d "$RELEASE_ROOT" ] && [ ! -L "$RELEASE_ROOT" ] || {
  refuse "release root is unavailable or is a symlink"
}
[ "$(/usr/bin/stat -f '%u:%g' "$RELEASE_ROOT")" = "0:0" ] || {
  refuse "release root is not root:wheel"
}
RELEASE_MODE="$(/usr/bin/stat -f '%Lp' "$RELEASE_ROOT")"
[ "$((8#$RELEASE_MODE & 8#022))" -eq 0 ] || {
  refuse "release root is writable by group or other"
}
case "$(/usr/bin/stat -f '%Sp' "$RELEASE_ROOT")" in
  *+) refuse "release root has a filesystem ACL" ;;
esac

read_attribute() {
  local record="$1" attribute="$2"
  /usr/bin/dscl . -read "$record" "$attribute" 2>/dev/null \
    | /usr/bin/awk -v key="$attribute" '
        NR == 1 {
          prefix=key ":"
          if (index($0, prefix) != 1) exit 65
          value=substr($0, length(prefix) + 1)
          sub(/^[[:space:]]*/, "", value)
          next
        }
        {value=value " " $0}
        END {
          if (NR == 0) exit 65
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
          print value
        }
      '
}

numeric_owners() {
  local record_type="$1" attribute="$2" numeric="$3"
  /usr/bin/dscl . -list "/$record_type" "$attribute" \
    | /usr/bin/awk -v numeric="$numeric" '$NF == numeric {print $1}' \
    | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
}

ensure_numeric_unused() {
  local record_type="$1" attribute="$2" numeric="$3" expected="$4" owners
  owners="$(numeric_owners "$record_type" "$attribute" "$numeric")"
  if [ -n "$owners" ] && [ "$owners" != "$expected" ]; then
    refuse "$attribute $numeric has an unexpected owner set"
  fi
}

assert_exec_identity() {
  [ "$(read_attribute "/Users/$EXEC_USER" UniqueID)" = "$EXEC_UID" ] \
    && [ "$(read_attribute "/Users/$EXEC_USER" PrimaryGroupID)" = "$EXEC_GID" ] \
    || refuse "the canonical Executive principal is unavailable"
}

ensure_group() {
  ensure_numeric_unused Groups PrimaryGroupID "$RELAY_GID" "$RELAY_GROUP"
  if /usr/bin/dscl . -read "/Groups/$RELAY_GROUP" >/dev/null 2>&1; then
    [ "$(read_attribute "/Groups/$RELAY_GROUP" PrimaryGroupID)" = "$RELAY_GID" ] \
      && [ "$(read_attribute "/Groups/$RELAY_GROUP" RealName)" = "$RELAY_GROUP service group" ] \
      && [ "$(read_attribute "/Groups/$RELAY_GROUP" GroupMembership)" = "$EXEC_USER" ] \
      || refuse "existing Relay group differs from the reviewed identity"
  else
    /usr/bin/dscl . -create "/Groups/$RELAY_GROUP"
    /usr/bin/dscl . -create "/Groups/$RELAY_GROUP" PrimaryGroupID "$RELAY_GID"
    /usr/bin/dscl . -create "/Groups/$RELAY_GROUP" RealName "$RELAY_GROUP service group"
    /usr/bin/dscl . -create "/Groups/$RELAY_GROUP" GeneratedUID "$(/usr/bin/uuidgen)"
    /usr/sbin/dseditgroup -o edit -a "$EXEC_USER" -t user "$RELAY_GROUP"
    [ "$(read_attribute "/Groups/$RELAY_GROUP" GroupMembership)" = "$EXEC_USER" ] \
      || refuse "Relay group membership could not be established"
  fi
}

ensure_user() {
  ensure_numeric_unused Users UniqueID "$RELAY_UID" "$RELAY_USER"
  if /usr/bin/dscl . -read "/Users/$RELAY_USER" >/dev/null 2>&1; then
    [ "$(read_attribute "/Users/$RELAY_USER" UniqueID)" = "$RELAY_UID" ] \
      && [ "$(read_attribute "/Users/$RELAY_USER" PrimaryGroupID)" = "$RELAY_GID" ] \
      && [ "$(read_attribute "/Users/$RELAY_USER" RealName)" = "$RELAY_USER service account" ] \
      && [ "$(read_attribute "/Users/$RELAY_USER" NFSHomeDirectory)" = "$RELAY_HOME" ] \
      && [ "$(read_attribute "/Users/$RELAY_USER" UserShell)" = "/usr/bin/false" ] \
      && [ "$(read_attribute "/Users/$RELAY_USER" IsHidden)" = "1" ] \
      && [ "$(read_attribute "/Users/$RELAY_USER" Password)" = "*" ] \
      || refuse "existing Relay user differs from the reviewed identity"
  else
    /usr/bin/dscl . -create "/Users/$RELAY_USER"
    /usr/bin/dscl . -create "/Users/$RELAY_USER" UniqueID "$RELAY_UID"
    /usr/bin/dscl . -create "/Users/$RELAY_USER" PrimaryGroupID "$RELAY_GID"
    /usr/bin/dscl . -create "/Users/$RELAY_USER" RealName "$RELAY_USER service account"
    /usr/bin/dscl . -create "/Users/$RELAY_USER" NFSHomeDirectory "$RELAY_HOME"
    /usr/bin/dscl . -create "/Users/$RELAY_USER" UserShell /usr/bin/false
    /usr/bin/dscl . -create "/Users/$RELAY_USER" IsHidden 1
    /usr/bin/dscl . -create "/Users/$RELAY_USER" Password '*'
  fi
  /usr/bin/pwpolicy -n /Local/Default -u "$RELAY_USER" -disableuser >/dev/null 2>&1 \
    || refuse "Relay service-account authentication could not be disabled"
  if /usr/bin/dscl . -authonly "$RELAY_USER" "$(/usr/bin/uuidgen)" >/dev/null 2>&1; then
    refuse "Relay service account unexpectedly accepted authentication"
  fi
}

assert_not_member() {
  local group="$1" membership status=0
  membership="$(LC_ALL=C LANG=C /usr/sbin/dseditgroup -o checkmember -m "$RELAY_USER" "$group" 2>&1)" \
    || status=$?
  [ "$status" -eq 67 ] \
    && [ "$membership" = "no $RELAY_USER is NOT a member of $group" ] \
    || refuse "Relay service account isolation could not be proven"
}

ensure_directory() {
  local path="$1" owner="$2" group="$3" uid="$4" gid="$5" mode="$6"
  preflight_directory "$path" "$uid" "$gid" "$mode"
  if [ ! -e "$path" ] && [ ! -L "$path" ]; then
    /usr/bin/install -d -o "$owner" -g "$group" -m "$mode" "$path"
    [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$path")" = "$uid:$gid:$mode" ] \
      || refuse "created prerequisite directory differs from the reviewed identity"
  fi
}

preflight_directory() {
  local path="$1" uid="$2" gid="$3" mode="$4"
  if [ -e "$path" ] || [ -L "$path" ]; then
    [ -d "$path" ] && [ ! -L "$path" ] \
      && [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$path")" = "$uid:$gid:$mode" ] \
      || refuse "existing prerequisite directory differs from the reviewed identity"
  fi
}

assert_exec_identity
for reserved in "$TOKEN_PATH" "$CONFIG_PATH" "$PLIST_PATH"; do
  [ ! -e "$reserved" ] && [ ! -L "$reserved" ] \
    || refuse "existing enrollment or service artifact must be reconciled first"
done
preflight_directory "$SYSTEM_ROOT" 0 0 755
preflight_directory "$CONFIG_ROOT" 0 0 755
preflight_directory "$RUNTIME_ROOT" 0 0 711
preflight_directory "$RELAY_HOME" "$RELAY_UID" "$RELAY_GID" 700
ensure_numeric_unused Groups PrimaryGroupID "$RELAY_GID" "$RELAY_GROUP"
ensure_numeric_unused Users UniqueID "$RELAY_UID" "$RELAY_USER"

ensure_group
ensure_user
for forbidden_group in _mastermind_exec _mastermind_worker _mastermind_ops \
  _mastermind_codex_01 _mastermind_codex_02 _mastermind_codex_03; do
  assert_not_member "$forbidden_group"
done

ensure_directory "$SYSTEM_ROOT" root wheel 0 0 755
ensure_directory "$CONFIG_ROOT" root wheel 0 0 755
ensure_directory "$RUNTIME_ROOT" root wheel 0 0 711
ensure_directory "$RELAY_HOME" "$RELAY_USER" "$RELAY_GROUP" "$RELAY_UID" "$RELAY_GID" 700

/bin/echo "A2 Agent Relay host preparation complete: principal and non-secret directories only"
