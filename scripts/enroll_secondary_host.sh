#!/bin/bash
# One-command base enrollment for a non-control macOS fleet host.
# This wrapper adds no new privilege or lifecycle authority: it composes the
# existing bootstrap, Python, privileged-broker, power, preflight, and workspace owners.
set -euo pipefail
umask 077

[ "$#" -eq 0 ] || { /bin/echo "enroll_secondary_host.sh accepts no arguments" >&2; exit 64; }
[ "$(/usr/bin/id -u)" -ne 0 ] || { /bin/echo "run as the logged-in operator, not root" >&2; exit 77; }
[ "$(/usr/bin/uname -s)" = "Darwin" ] || { /bin/echo "macOS only" >&2; exit 69; }

SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && /bin/pwd)"
SOURCE_REPO="$(cd "$SCRIPT_DIR/.." && /bin/pwd -P)"
OPERATOR_USER="$(/usr/bin/id -un)"
SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
PYTHON_BINARY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
STAGING=""
HARDENED=0
COMPLETE=0

refuse() {
  /bin/echo "secondary host enrollment refused: $1" >&2
  exit 65
}

cleanup_unhardened() {
  if [ "$COMPLETE" != "1" ] && [ "$HARDENED" = "0" ] && [ -n "$STAGING" ]; then
    case "$STAGING" in /private/tmp/mastermind-secondary-enroll.*) ;; *) return ;; esac
    [ -d "$STAGING" ] && [ ! -L "$STAGING" ] && /bin/rm -rf -- "$STAGING"
  fi
}
trap cleanup_unhardened EXIT

HEAD_SHA="$(/usr/bin/git -C "$SOURCE_REPO" rev-parse HEAD)"
REMOTE_SHA="$(/usr/bin/git -C "$SOURCE_REPO" rev-parse refs/remotes/origin/master)"
[ "$HEAD_SHA" = "$REMOTE_SHA" ] || refuse "source HEAD is not exact origin/master"
[ -z "$(/usr/bin/git -C "$SOURCE_REPO" status --porcelain=v1 --untracked-files=normal)" ] \
  || refuse "source checkout is not clean"
RELEASE_SHA="$HEAD_SHA"

STAGING="$(/usr/bin/mktemp -d "/private/tmp/mastermind-secondary-enroll.${RELEASE_SHA:0:12}.XXXXXX")"
HARDENED_SOURCE="$STAGING/source"
GIT_ENV=(/usr/bin/env -i HOME="$HOME" PATH=/usr/bin:/bin:/usr/sbin:/sbin
  LANG=C.UTF-8 LC_ALL=C.UTF-8 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
  GIT_NO_LAZY_FETCH=1 GIT_NO_REPLACE_OBJECTS=1 GIT_TERMINAL_PROMPT=0)

"${GIT_ENV[@]}" /usr/bin/git clone --no-hardlinks --no-checkout "$SOURCE_REPO" "$HARDENED_SOURCE"
"${GIT_ENV[@]}" /usr/bin/git -C "$HARDENED_SOURCE" checkout --detach "$RELEASE_SHA"
[ "$("${GIT_ENV[@]}" /usr/bin/git -C "$HARDENED_SOURCE" rev-parse HEAD)" = "$RELEASE_SHA" ] \
  || refuse "staged checkout HEAD differs"
[ "$("${GIT_ENV[@]}" /usr/bin/git -C "$HARDENED_SOURCE" rev-parse refs/remotes/origin/master)" = "$RELEASE_SHA" ] \
  || refuse "staged checkout origin/master differs"
[ -z "$("${GIT_ENV[@]}" /usr/bin/git -C "$HARDENED_SOURCE" status --porcelain=v1 --untracked-files=all)" ] \
  || refuse "staged checkout is not clean"
if "${GIT_ENV[@]}" /usr/bin/git -C "$HARDENED_SOURCE" config --local --get-regexp \
  '^(extensions\.partialclone|remote\..*\.(promisor|partialclonefilter))$' >/dev/null 2>&1; then
  refuse "staged checkout retains partial-clone authority"
fi
"${GIT_ENV[@]}" /usr/bin/git -C "$HARDENED_SOURCE" fsck --full --no-dangling >/dev/null

/bin/echo "Administrator authorization is required once for reviewed host bootstrap."
/usr/bin/sudo -v
/usr/bin/sudo -n /usr/sbin/chown -R root:wheel "$STAGING"
/usr/bin/sudo -n /bin/chmod -R go-w "$STAGING"
HARDENED=1
[ "$(/usr/bin/stat -f '%u:%g' "$STAGING")" = "0:0" ] || refuse "staging custody did not harden"
[ -d "$HARDENED_SOURCE/.git" ] && [ ! -L "$HARDENED_SOURCE/.git" ] \
  || refuse "hardened checkout is not direct"

# Every root-executed repository script is now read from the hardened exact-master copy.
/usr/bin/sudo -n /bin/bash "$HARDENED_SOURCE/ops/executive_os/bootstrap-host.sh" \
  --operator-user "$OPERATOR_USER"
/usr/bin/sudo -n /bin/bash "$HARDENED_SOURCE/ops/executive_os/provision-python-runtime.sh"
/usr/bin/sudo -n /bin/bash "$HARDENED_SOURCE/ops/executive_os/provision-python-runtime.sh" --verify-only
/usr/bin/sudo -n /bin/bash "$HARDENED_SOURCE/ops/executive_os/prepare-secondary-privileged-host.sh" \
  --source-repo "$HARDENED_SOURCE" --expected-sha "$RELEASE_SHA" --operator-user "$OPERATOR_USER"

POWER_CLIENT="$SYSTEM_ROOT/bin/mmx-secondary-host-power"
[ -x "$POWER_CLIENT" ] && [ ! -L "$POWER_CLIENT" ] || refuse "installed power client is unavailable"
POWER_REQUEST_ID="fleet-secondary-enroll-power-${RELEASE_SHA:0:12}"
set +e
POWER_OUTPUT="$("$POWER_CLIENT" --request-id "$POWER_REQUEST_ID")"
POWER_RC=$?
set -e
if [ "$POWER_RC" -eq 75 ]; then
  /bin/echo "$POWER_OUTPUT"
  /bin/echo "power action is EFFECT_UNKNOWN; reconcile this request id on this host before any retry" >&2
  exit 75
fi
[ "$POWER_RC" -eq 0 ] || { /bin/echo "$POWER_OUTPUT"; refuse "governed power action failed"; }

RELEASE_ROOT="$SYSTEM_ROOT/releases/$RELEASE_SHA"
PREFLIGHT="$RELEASE_ROOT/ops/executive_os/host_recovery_readiness.py"
[ -x "$PYTHON_BINARY" ] && [ -f "$PREFLIGHT" ] && [ ! -L "$PREFLIGHT" ] \
  || refuse "installed release preflight is unavailable"
PREFLIGHT_OUTPUT="$("$PYTHON_BINARY" -I -S -B "$PREFLIGHT" --profile fleet-secondary-host-preflight/v1)"
PREFLIGHT_STATE="$(/usr/bin/printf '%s\n' "$PREFLIGHT_OUTPUT" | "$PYTHON_BINARY" -I -S -B -c \
  'import json,sys; print(json.load(sys.stdin).get("recovery_state",""))')"
if [ "$PREFLIGHT_STATE" != "READY" ]; then
  /bin/echo "$PREFLIGHT_OUTPUT" >&2
  refuse "host is not physically ready after governed remediation"
fi

# The attended workspace launcher is user-level. Re-prove the mutable operator
# checkout before consuming it so its installed payload remains this exact release.
[ "$(/usr/bin/git -C "$SOURCE_REPO" rev-parse HEAD)" = "$RELEASE_SHA" ] \
  || refuse "operator source moved during enrollment"
[ "$(/usr/bin/git -C "$SOURCE_REPO" rev-parse refs/remotes/origin/master)" = "$RELEASE_SHA" ] \
  || refuse "operator origin/master moved during enrollment"
[ -z "$(/usr/bin/git -C "$SOURCE_REPO" status --porcelain=v1 --untracked-files=normal)" ] \
  || refuse "operator source became dirty during enrollment"
WORKSPACE_INSTALLER="$SOURCE_REPO/scripts/install_"'mastermind'"_workspace_cli.sh"
/bin/sh "$WORKSPACE_INSTALLER" >/dev/null
WORKSPACE_STORAGE="$("$HOME/.local/bin/mmx-workspace" storage)"

case "$STAGING" in /private/tmp/mastermind-secondary-enroll.*) ;; *) refuse "staging path escaped fixed root" ;; esac
[ -d "$STAGING" ] && [ ! -L "$STAGING" ] || refuse "staging path changed before cleanup"
/usr/bin/sudo -n /bin/rm -rf -- "$STAGING"
STAGING=""
COMPLETE=1
trap - EXIT

/bin/echo "$PREFLIGHT_OUTPUT"
/bin/echo "$WORKSPACE_STORAGE"
/usr/bin/printf '{"schema":"mastermind.secondary_host_base_enrollment/v1","outcome":"READY_FOR_WORKER_AND_GATEWAY_ENROLLMENT","release_sha":"%s","power_request_id":"%s"}\n' \
  "$RELEASE_SHA" "$POWER_REQUEST_ID"
