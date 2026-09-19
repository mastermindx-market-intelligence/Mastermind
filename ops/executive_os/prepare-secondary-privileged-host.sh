#!/bin/bash
# Prepare one non-control macOS host with only the exact-release privileged
# broker needed for governed secondary-host remediation. This script never
# installs or mutates the canonical Executive control, MCP, or relay services.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && /bin/pwd)"
SCRIPT_SOURCE_REPO="$(cd "$SCRIPT_DIR/../.." && /bin/pwd -P)"
PYTHON_PROVISIONER="$SCRIPT_DIR/provision-python-runtime.sh"
SOURCE_POLICY="$SCRIPT_DIR/install_source_policy.py"
BOOTSTRAP_SOURCE="$SCRIPT_DIR/bootstrap-host.sh"

CONTROL_LABEL="com.mastermind.executive.control"
MCP_LABEL="com.mastermind.executive.mcp"
RELAY_LABEL="com.mastermind.executive.sol-state-relay"
PRIVILEGED_LABEL="com.mastermind.executive.privileged"
CENTRAL_LABELS=("$CONTROL_LABEL" "$MCP_LABEL" "$RELAY_LABEL")

CONTROL_USER=""
CONTROL_GROUP=""
CONTROL_UID=""
CONTROL_GID=""
OPS_GROUP=""
OPS_GID=""
BROKER_TIMEOUT_SECONDS="$((10 * 60))"
CONFIG_MODE="400"
LAUNCHER_MODE="555"
PLIST_MODE="644"
SOCKET_MODE_TEXT="0660"
SOCKET_MODE_DECIMAL="$(/usr/bin/printf '%d' "$SOCKET_MODE_TEXT")"
SOCKET_MODE_STAT="${SOCKET_MODE_TEXT#0}"

PYTHON_RUNTIME_ROOT="/Library/Frameworks/Python.framework/Versions/3.12"
PYTHON_BINARY="$PYTHON_RUNTIME_ROOT/bin/python3.12"
SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
RUNTIME_ROOT="/var/db/mastermind-executive"
PRIVILEGED_CONFIG="$SYSTEM_ROOT/config/privileged-broker.json"
PRIVILEGED_RECEIPT_ROOT="$RUNTIME_ROOT/privileged-actions/receipts"
PRIVILEGED_SOCKET="/var/run/mastermind-executive/privileged.sock"
PRIVILEGED_PLIST="/Library/LaunchDaemons/$PRIVILEGED_LABEL.plist"
MMX_ADMIN="$SYSTEM_ROOT/bin/mmx-admin"

SOURCE_REPO=""
EXPECTED_SHA=""
OPERATOR_USER=""
OPERATOR_UID=""
TREE_SHA=""
RELEASE_ROOT=""
STAGING=""
CONFIG_CANDIDATE=""
ADMIN_CANDIDATE=""
POWER_CANDIDATE=""
PLIST_CANDIDATE=""
BROKER_ARM_MUTATION_STARTED="0"
COMPLETED="0"

usage() {
  /bin/echo "usage: sudo /bin/bash $0 --source-repo PATH --expected-sha SHA --operator-user NAME" >&2
  exit 64
}

refuse() {
  /bin/echo "secondary privileged host preparation refused: $1" >&2
  exit 65
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-repo) SOURCE_REPO="${2:-}"; shift 2 ;;
    --expected-sha) EXPECTED_SHA="${2:-}"; shift 2 ;;
    --operator-user) OPERATOR_USER="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

case "$EXPECTED_SHA" in
  ''|*[!0-9a-f]*) refuse "expected SHA must contain exactly 40 lowercase hexadecimal characters" ;;
esac
[ "${#EXPECTED_SHA}" -eq 40 ] || refuse "expected SHA must contain exactly 40 lowercase hexadecimal characters"
[ -n "$SOURCE_REPO" ] && [ -n "$OPERATOR_USER" ] || usage
case "$SOURCE_REPO" in /*) ;; *) refuse "source repo must be absolute" ;; esac
case "$OPERATOR_USER" in
  [A-Za-z_]* ) ;;
  *) refuse "operator account name is invalid" ;;
esac
case "$OPERATOR_USER" in *[!A-Za-z0-9_.-]*) refuse "operator account name is invalid" ;; esac

[ "$(/usr/bin/id -u)" -eq 0 ] || { /bin/echo "prepare-secondary-privileged-host.sh must run as root" >&2; exit 77; }
[ "$(/usr/bin/uname -s)" = "Darwin" ] || { /bin/echo "prepare-secondary-privileged-host.sh supports macOS only" >&2; exit 69; }

assert_central_absent() {
  local label plist
  for label in "${CENTRAL_LABELS[@]}"; do
    plist="/Library/LaunchDaemons/$label.plist"
    [ ! -e "$plist" ] && [ ! -L "$plist" ] || refuse "central Executive LaunchDaemon is installed: $label"
    if /bin/launchctl print "system/$label" >/dev/null 2>&1; then
      refuse "central Executive LaunchDaemon is loaded: $label"
    fi
  done
}

assert_direct_file_metadata() {
  local path="$1" expected="$2"
  [ -f "$path" ] && [ ! -L "$path" ] || return 1
  [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$path")" = "$expected" ] || return 1
  case "$(/usr/bin/stat -f '%Sp' "$path")" in *+) return 1 ;; esac
}

install_or_verify_generated_file() {
  local candidate="$1" destination="$2" uid="$3" gid="$4" mode="$5"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    assert_direct_file_metadata "$destination" "$uid:$gid:$mode:1"       || refuse "existing installed artifact metadata differs: $destination"
    /usr/bin/cmp -s "$candidate" "$destination"       || refuse "existing installed artifact content differs: $destination"
    /bin/rm -f -- "$candidate"
    return 0
  fi
  /usr/sbin/chown "$uid:$gid" "$candidate"
  /bin/chmod "0$mode" "$candidate"
  /bin/mv "$candidate" "$destination"
  assert_direct_file_metadata "$destination" "$uid:$gid:$mode:1"     || refuse "installed artifact metadata differs: $destination"
}

cleanup_on_failure() {
  if [ "$COMPLETED" != "1" ] && [ "$BROKER_ARM_MUTATION_STARTED" = "1" ]; then
    /bin/launchctl bootout "system/$PRIVILEGED_LABEL" >/dev/null 2>&1 || true
    /bin/launchctl disable "system/$PRIVILEGED_LABEL" >/dev/null 2>&1 || true
  fi
  for candidate in "$CONFIG_CANDIDATE" "$ADMIN_CANDIDATE" "$POWER_CANDIDATE" "$PLIST_CANDIDATE"; do
    if [ -n "$candidate" ] && [ -e "$candidate" ] && [ ! -L "$candidate" ]; then
      /bin/rm -f -- "$candidate"
    fi
  done
  if [ -n "$STAGING" ] && [ -d "$STAGING" ] && [ ! -L "$STAGING" ]; then
    /bin/rm -rf -- "$STAGING"
  fi
}
trap cleanup_on_failure EXIT

# Anti-duplication is a PRE-MUTATION gate. Do not "repair" a secondary host by
# disabling or booting out a central control plane; that would hide a role error.
assert_central_absent

[ -d "$SOURCE_REPO" ] && [ ! -L "$SOURCE_REPO" ] || refuse "source repo must be a direct directory"
[ -d "$SOURCE_REPO/.git" ] && [ ! -L "$SOURCE_REPO/.git" ] || refuse "source repo must be a direct Git checkout"
SOURCE_PARENT="$(cd "$SOURCE_REPO/.." && /bin/pwd -P)"
[ "$(/usr/bin/stat -f '%u:%g' "$SOURCE_PARENT")" = "0:0" ] || refuse "source parent must be root:wheel"
[ -z "$(/usr/bin/find "$SOURCE_PARENT" -maxdepth 0 -perm +022 -print -quit)" ] || refuse "source parent is group/other writable"
[ -z "$(/usr/bin/find "$SOURCE_REPO" ! -type l ! -user root -print -quit)" ] || refuse "source checkout contains a non-root-owned non-symlink object"
[ -z "$(/usr/bin/find "$SOURCE_REPO" ! -type l -perm +022 -print -quit)" ] || refuse "source checkout contains a group/other-writable non-symlink object"
[ -z "$(/usr/bin/find "$SOURCE_REPO" -type f -links +1 -print -quit)" ] || refuse "source checkout contains a hard-linked file"
case "$(/usr/bin/stat -f '%Sp' "$SOURCE_PARENT")" in *+) refuse "source parent has a filesystem ACL" ;; esac
[ -z "$(/usr/bin/find "$SOURCE_REPO" ! -type l -exec /usr/bin/stat -f '%Sp' {} \; | /usr/bin/awk '/\+/{print "ACL"; exit}')" ] || refuse "source checkout contains a filesystem ACL on a non-symlink object"

# Consume the canonical service identity owner instead of redeclaring users/IDs.
[ -f "$BOOTSTRAP_SOURCE" ] && [ ! -L "$BOOTSTRAP_SOURCE" ] || refuse "canonical bootstrap identity source is unavailable"
bootstrap_value() {
  local key="$1" value
  value="$(/usr/bin/awk -F= -v key="$key" '$1 == key && $2 ~ /^"[A-Za-z0-9_.-]+"$/ {gsub(/"/, "", $2); print $2}' "$BOOTSTRAP_SOURCE")"
  case "$value" in ''|*SOURCE_REPO_REAL="$(cd "$SOURCE_REPO" && /bin/pwd -P)"
[ "$SOURCE_REPO_REAL" = "$SCRIPT_SOURCE_REPO" ] || refuse "script and source repo must be the same checkout"
[ "$(/usr/bin/git -C "$SOURCE_REPO" rev-parse HEAD)" = "$EXPECTED_SHA" ] || refuse "source HEAD differs from expected SHA"
[ -z "$('/usr/bin/git' -C "$SOURCE_REPO" status --porcelain=v1 --untracked-files=all)" ] || refuse "source repo is not clean"
[ -f "$SOURCE_POLICY" ] && [ ! -L "$SOURCE_POLICY" ] || refuse "source policy helper is unavailable"
[ -x "$PYTHON_PROVISIONER" ] && [ ! -L "$PYTHON_PROVISIONER" ] || refuse "Python runtime verifier is unavailable"

# The role-specific preparation consumes existing bootstrap/runtime owners. It
# never creates principals and never provisions a Python runtime by itself.
"$PYTHON_PROVISIONER" --verify-only >/dev/null || refuse "reviewed Python runtime did not verify"
[ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || refuse "reviewed Python binary is unavailable"
"$PYTHON_BINARY" -I -S -B "$SOURCE_POLICY" --source-repo "$SOURCE_REPO" --expected-sha "$EXPECTED_SHA" >/dev/null   || refuse "source checkout failed the reviewed Executive install policy"
TREE_SHA="$(/usr/bin/git -C "$SOURCE_REPO" rev-parse "$EXPECTED_SHA^{tree}")"

[ "$(/usr/bin/id -u "$CONTROL_USER" 2>/dev/null || true)" = "$CONTROL_UID" ]   || refuse "canonical control principal is unavailable; run bootstrap-host.sh first"
[ "$(/usr/bin/id -g "$CONTROL_USER" 2>/dev/null || true)" = "$CONTROL_GID" ]   || refuse "canonical control principal group differs"
[ "$(/usr/bin/dscl . -read "/Groups/$CONTROL_GROUP" PrimaryGroupID 2>/dev/null | /usr/bin/awk '{print $NF}')" = "$CONTROL_GID" ]   || refuse "canonical control group differs"
[ "$(/usr/bin/dscl . -read "/Groups/$OPS_GROUP" PrimaryGroupID 2>/dev/null | /usr/bin/awk '{print $NF}')" = "$OPS_GID" ]   || refuse "canonical ops group differs"
[ -n "$(/usr/bin/id -u "$OPERATOR_USER" 2>/dev/null || true)" ] || refuse "operator user does not exist"
if ! /usr/bin/id -Gn "$OPERATOR_USER" | /usr/bin/tr ' ' '\n' | /usr/bin/grep -qx "$OPS_GROUP"; then
  refuse "operator is not a member of the canonical ops group; run bootstrap-host.sh first"
fi
OPERATOR_UID="$(/usr/bin/id -u "$OPERATOR_USER")"

# Cross the mutation boundary only after central-role absence, exact source,
# pinned runtime, and principal admission are all proven.
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT" "$SYSTEM_ROOT/bin" "$SYSTEM_ROOT/config" "$SYSTEM_ROOT/releases"
/usr/bin/install -d -o root -g wheel -m 0711 "$RUNTIME_ROOT"
/usr/bin/install -d -o root -g wheel -m 0700 "$RUNTIME_ROOT/privileged-actions" "$PRIVILEGED_RECEIPT_ROOT"
/usr/bin/install -d -o root -g wheel -m 0755 /var/run/mastermind-executive
/usr/bin/install -d -o root -g wheel -m 0700 /var/log/mastermind-executive /var/log/mastermind-executive/privileged

RELEASE_ROOT="$SYSTEM_ROOT/releases/$EXPECTED_SHA"
if [ ! -e "$RELEASE_ROOT" ] && [ ! -L "$RELEASE_ROOT" ]; then
  STAGING="$(/usr/bin/mktemp -d "$SYSTEM_ROOT/releases/.secondary-install.$EXPECTED_SHA.XXXXXX")"
  /usr/bin/git -C "$SOURCE_REPO" archive --format=tar "$EXPECTED_SHA" | /usr/bin/tar -xf - -C "$STAGING"
  /usr/sbin/chown -R root:wheel "$STAGING"
  /bin/chmod -R go-w "$STAGING"
  /bin/chmod 0755 "$STAGING"
  "$PYTHON_BINARY" -I -S -B "$STAGING/ops/executive_os/release_manifest.py" create     --root "$STAGING" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA"
  /usr/sbin/chown root:wheel "$STAGING/.executive-release-manifest.json"
  "$PYTHON_BINARY" -I -S -B "$STAGING/ops/executive_os/release_manifest.py" verify     --root "$STAGING" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA" >/dev/null     || refuse "staged exact release did not verify"
  /bin/mv "$STAGING" "$RELEASE_ROOT"
  STAGING=""
else
  [ -d "$RELEASE_ROOT" ] && [ ! -L "$RELEASE_ROOT" ] || refuse "existing release path is ambiguous"
fi
"$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/ops/executive_os/release_manifest.py" verify   --root "$RELEASE_ROOT" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA" >/dev/null   || refuse "exact installed release did not verify"

for required in   "$RELEASE_ROOT/control_plane/executive_privileged_action.py"   "$RELEASE_ROOT/control_plane/executive_privileged_broker.py"   "$RELEASE_ROOT/scripts/executive_os_privileged_broker.py"   "$RELEASE_ROOT/scripts/mmx_admin.py"   "$RELEASE_ROOT/scripts/mmx_secondary_host_power.py"   "$RELEASE_ROOT/ops/executive_os/com.mastermind.executive.privileged.plist.template"   "$RELEASE_ROOT/ops/executive_os/render_launchd_program_arguments.py"; do
  [ -f "$required" ] && [ ! -L "$required" ] || refuse "exact release lacks required privileged-substrate source"
done

CONFIG_CANDIDATE="$(/usr/bin/mktemp "$SYSTEM_ROOT/config/.privileged-broker.secondary.XXXXXX")"
"$PYTHON_BINARY" -I -S -B - "$CONFIG_CANDIDATE" "$RELEASE_ROOT" "$PRIVILEGED_RECEIPT_ROOT" "$CONTROL_UID" "$OPERATOR_UID" "$BROKER_TIMEOUT_SECONDS" <<'PY'
import json, os, pathlib, sys
path, release_root, receipt_root, control_uid, operator_uid, broker_timeout = sys.argv[1:]
value = {
    "schema": "mastermind.executive_privileged_broker_config.v1",
    "release_root": release_root,
    "receipt_root": receipt_root,
    "allowed_peer_uids": sorted({int(control_uid), int(operator_uid)}),
    "timeout_seconds": int(broker_timeout),
    "broker_version": "1",
}
out = pathlib.Path(path)
out.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
os.chmod(out, 0o400)
PY
install_or_verify_generated_file "$CONFIG_CANDIDATE" "$PRIVILEGED_CONFIG" 0 0 "$CONFIG_MODE"

ADMIN_CANDIDATE="$(/usr/bin/mktemp "$SYSTEM_ROOT/bin/.mmx-admin.secondary.XXXXXX")"
/usr/bin/printf '%s\n' '#!/bin/bash'   "exec \"$PYTHON_BINARY\" -I -S -B \"$RELEASE_ROOT/scripts/mmx_admin.py\" \"\$@\""   >"$ADMIN_CANDIDATE"
install_or_verify_generated_file "$ADMIN_CANDIDATE" "$MMX_ADMIN" 0 0 "$LAUNCHER_MODE"

POWER_LAUNCHER="$SYSTEM_ROOT/bin/mmx-secondary-host-power"
POWER_CANDIDATE="$(/usr/bin/mktemp "$SYSTEM_ROOT/bin/.mmx-secondary-host-power.XXXXXX")"
/usr/bin/printf '%s\n' '#!/bin/bash'   "exec \"$PYTHON_BINARY\" -I -S -B \"$RELEASE_ROOT/scripts/mmx_secondary_host_power.py\" \"\$@\""   >"$POWER_CANDIDATE"
install_or_verify_generated_file "$POWER_CANDIDATE" "$POWER_LAUNCHER" 0 0 "$LAUNCHER_MODE"

PLIST_CANDIDATE="$(/usr/bin/mktemp "/Library/LaunchDaemons/.$PRIVILEGED_LABEL.secondary.XXXXXX")"
/usr/bin/install -o root -g wheel -m 0644   "$RELEASE_ROOT/ops/executive_os/$PRIVILEGED_LABEL.plist.template" "$PLIST_CANDIDATE"
"$PYTHON_BINARY" -I -S -B   "$RELEASE_ROOT/ops/executive_os/render_launchd_program_arguments.py"   "$PLIST_CANDIDATE" --   "$PYTHON_BINARY" -I -S -B   "$RELEASE_ROOT/scripts/executive_os_privileged_broker.py"   serve --config "$PRIVILEGED_CONFIG"
/usr/bin/plutil -replace WorkingDirectory -string "$RELEASE_ROOT" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace Sockets.PrivilegedActions.SockPathName -string "$PRIVILEGED_SOCKET" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace Sockets.PrivilegedActions.SockPathOwner -integer "$CONTROL_UID" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace Sockets.PrivilegedActions.SockPathGroup -integer "$OPS_GID" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace Sockets.PrivilegedActions.SockPathMode -integer "$SOCKET_MODE_DECIMAL" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace StandardOutPath -string /var/log/mastermind-executive/privileged/stdout.log "$PLIST_CANDIDATE"
/usr/bin/plutil -replace StandardErrorPath -string /var/log/mastermind-executive/privileged/stderr.log "$PLIST_CANDIDATE"
/usr/bin/plutil -lint "$PLIST_CANDIDATE" >/dev/null || refuse "rendered privileged plist is invalid"
install_or_verify_generated_file "$PLIST_CANDIDATE" "$PRIVILEGED_PLIST" 0 0 "$PLIST_MODE"

# Re-prove the exact release after every generated path is bound to it.
"$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/ops/executive_os/release_manifest.py" verify   --root "$RELEASE_ROOT" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA" >/dev/null   || refuse "release changed during privileged-substrate installation"
assert_central_absent

if ! /bin/launchctl print "system/$PRIVILEGED_LABEL" >/dev/null 2>&1; then
  BROKER_ARM_MUTATION_STARTED="1"
  /bin/launchctl enable "system/$PRIVILEGED_LABEL"
  /bin/launchctl bootstrap system "$PRIVILEGED_PLIST"
fi
for attempt in 1 2 3 4 5; do
  [ -S "$PRIVILEGED_SOCKET" ] && break
  /bin/sleep 1
done
[ -S "$PRIVILEGED_SOCKET" ]   && [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$PRIVILEGED_SOCKET")" = "$CONTROL_UID:$OPS_GID:$SOCKET_MODE_STAT" ]   || refuse "privileged broker socket is absent or has unsafe metadata"

OPERATOR_HOME="$(/usr/bin/dscl . -read "/Users/$OPERATOR_USER" NFSHomeDirectory 2>/dev/null | /usr/bin/awk '{$1=""; sub(/^ /,""); print}')"
case "$OPERATOR_HOME" in /*) ;; *) refuse "operator home is unavailable" ;; esac
set +e
STATUS_OUTPUT="$(/usr/bin/sudo -u "$OPERATOR_USER" /usr/bin/env -i   HOME="$OPERATOR_HOME" PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C.UTF-8 LC_ALL=C.UTF-8   "$MMX_ADMIN" status --request-id fleet-secondary-prep-probe 2>/dev/null)"
STATUS_RC=$?
set -e
[ "$STATUS_RC" -eq 4 ] || refuse "privileged broker read-only status probe did not return NOT_FOUND"
/bin/echo "$STATUS_OUTPUT" | "$PYTHON_BINARY" -I -S -B - "$EXPECTED_SHA" <<'PY'   || refuse "privileged broker read-only status response is invalid"
import json, sys
value = json.load(sys.stdin)
expected_sha = sys.argv[1]
expected = {
    "schema", "ok", "query", "status", "request_id", "installed_release_sha",
}
if set(value) != expected:
    raise RuntimeError("status response shape differs")
if value.get("schema") != "mastermind.executive_privileged_action_response.v1":
    raise RuntimeError("status response schema differs")
if value.get("ok") is not True or value.get("query") is not True:
    raise RuntimeError("status response is not a successful query")
if value.get("status") != "NOT_FOUND" or value.get("request_id") != "fleet-secondary-prep-probe":
    raise RuntimeError("status response identity differs")
if value.get("installed_release_sha") != expected_sha:
    raise RuntimeError("installed release identity differs")
PY

# The install is not complete unless the central-control anti-duplication fact
# survived every release/config/plist/launchd mutation above.
assert_central_absent
COMPLETED="1"
/bin/echo "{\"schema\":\"mastermind.secondary_privileged_host_preparation/v1\",\"outcome\":\"READY_FOR_GOVERNED_POWER_REMEDIATION\",\"release_sha\":\"$EXPECTED_SHA\"}"
\n'*) refuse "canonical bootstrap identity field is missing or ambiguous: $key" ;; esac
  /usr/bin/printf '%s\n' "$value"
}
CONTROL_USER="$(bootstrap_value CONTROL_USER)"
CONTROL_GROUP="$(bootstrap_value CONTROL_GROUP)"
CONTROL_UID="$(bootstrap_value CONTROL_UID)"
CONTROL_GID="$(bootstrap_value CONTROL_GID)"
OPS_GROUP="$(bootstrap_value OPS_GROUP)"
OPS_GID="$(bootstrap_value OPS_GID)"
case "$CONTROL_UID:$CONTROL_GID:$OPS_GID" in *[!0-9:]*|'') refuse "canonical bootstrap numeric identity is invalid" ;; esac

# Only after filesystem custody is immutable may root invoke Git or helpers from it.
SOURCE_REPO_REAL="$(cd "$SOURCE_REPO" && /bin/pwd -P)"
[ "$SOURCE_REPO_REAL" = "$SCRIPT_SOURCE_REPO" ] || refuse "script and source repo must be the same checkout"
[ "$(/usr/bin/git -C "$SOURCE_REPO" rev-parse HEAD)" = "$EXPECTED_SHA" ] || refuse "source HEAD differs from expected SHA"
[ -z "$('/usr/bin/git' -C "$SOURCE_REPO" status --porcelain=v1 --untracked-files=all)" ] || refuse "source repo is not clean"
[ -f "$SOURCE_POLICY" ] && [ ! -L "$SOURCE_POLICY" ] || refuse "source policy helper is unavailable"
[ -x "$PYTHON_PROVISIONER" ] && [ ! -L "$PYTHON_PROVISIONER" ] || refuse "Python runtime verifier is unavailable"

# The role-specific preparation consumes existing bootstrap/runtime owners. It
# never creates principals and never provisions a Python runtime by itself.
"$PYTHON_PROVISIONER" --verify-only >/dev/null || refuse "reviewed Python runtime did not verify"
[ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || refuse "reviewed Python binary is unavailable"
"$PYTHON_BINARY" -I -S -B "$SOURCE_POLICY" --source-repo "$SOURCE_REPO" --expected-sha "$EXPECTED_SHA" >/dev/null   || refuse "source checkout failed the reviewed Executive install policy"
TREE_SHA="$(/usr/bin/git -C "$SOURCE_REPO" rev-parse "$EXPECTED_SHA^{tree}")"

[ "$(/usr/bin/id -u "$CONTROL_USER" 2>/dev/null || true)" = "$CONTROL_UID" ]   || refuse "canonical control principal is unavailable; run bootstrap-host.sh first"
[ "$(/usr/bin/id -g "$CONTROL_USER" 2>/dev/null || true)" = "$CONTROL_GID" ]   || refuse "canonical control principal group differs"
[ "$(/usr/bin/dscl . -read "/Groups/$CONTROL_GROUP" PrimaryGroupID 2>/dev/null | /usr/bin/awk '{print $NF}')" = "$CONTROL_GID" ]   || refuse "canonical control group differs"
[ "$(/usr/bin/dscl . -read "/Groups/$OPS_GROUP" PrimaryGroupID 2>/dev/null | /usr/bin/awk '{print $NF}')" = "$OPS_GID" ]   || refuse "canonical ops group differs"
[ -n "$(/usr/bin/id -u "$OPERATOR_USER" 2>/dev/null || true)" ] || refuse "operator user does not exist"
if ! /usr/bin/id -Gn "$OPERATOR_USER" | /usr/bin/tr ' ' '\n' | /usr/bin/grep -qx "$OPS_GROUP"; then
  refuse "operator is not a member of the canonical ops group; run bootstrap-host.sh first"
fi
OPERATOR_UID="$(/usr/bin/id -u "$OPERATOR_USER")"

# Cross the mutation boundary only after central-role absence, exact source,
# pinned runtime, and principal admission are all proven.
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT" "$SYSTEM_ROOT/bin" "$SYSTEM_ROOT/config" "$SYSTEM_ROOT/releases"
/usr/bin/install -d -o root -g wheel -m 0711 "$RUNTIME_ROOT"
/usr/bin/install -d -o root -g wheel -m 0700 "$RUNTIME_ROOT/privileged-actions" "$PRIVILEGED_RECEIPT_ROOT"
/usr/bin/install -d -o root -g wheel -m 0755 /var/run/mastermind-executive
/usr/bin/install -d -o root -g wheel -m 0700 /var/log/mastermind-executive /var/log/mastermind-executive/privileged

RELEASE_ROOT="$SYSTEM_ROOT/releases/$EXPECTED_SHA"
if [ ! -e "$RELEASE_ROOT" ] && [ ! -L "$RELEASE_ROOT" ]; then
  STAGING="$(/usr/bin/mktemp -d "$SYSTEM_ROOT/releases/.secondary-install.$EXPECTED_SHA.XXXXXX")"
  /usr/bin/git -C "$SOURCE_REPO" archive --format=tar "$EXPECTED_SHA" | /usr/bin/tar -xf - -C "$STAGING"
  /usr/sbin/chown -R root:wheel "$STAGING"
  /bin/chmod -R go-w "$STAGING"
  /bin/chmod 0755 "$STAGING"
  "$PYTHON_BINARY" -I -S -B "$STAGING/ops/executive_os/release_manifest.py" create     --root "$STAGING" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA"
  /usr/sbin/chown root:wheel "$STAGING/.executive-release-manifest.json"
  "$PYTHON_BINARY" -I -S -B "$STAGING/ops/executive_os/release_manifest.py" verify     --root "$STAGING" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA" >/dev/null     || refuse "staged exact release did not verify"
  /bin/mv "$STAGING" "$RELEASE_ROOT"
  STAGING=""
else
  [ -d "$RELEASE_ROOT" ] && [ ! -L "$RELEASE_ROOT" ] || refuse "existing release path is ambiguous"
fi
"$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/ops/executive_os/release_manifest.py" verify   --root "$RELEASE_ROOT" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA" >/dev/null   || refuse "exact installed release did not verify"

for required in   "$RELEASE_ROOT/control_plane/executive_privileged_action.py"   "$RELEASE_ROOT/control_plane/executive_privileged_broker.py"   "$RELEASE_ROOT/scripts/executive_os_privileged_broker.py"   "$RELEASE_ROOT/scripts/mmx_admin.py"   "$RELEASE_ROOT/scripts/mmx_secondary_host_power.py"   "$RELEASE_ROOT/ops/executive_os/com.mastermind.executive.privileged.plist.template"   "$RELEASE_ROOT/ops/executive_os/render_launchd_program_arguments.py"; do
  [ -f "$required" ] && [ ! -L "$required" ] || refuse "exact release lacks required privileged-substrate source"
done

CONFIG_CANDIDATE="$(/usr/bin/mktemp "$SYSTEM_ROOT/config/.privileged-broker.secondary.XXXXXX")"
"$PYTHON_BINARY" -I -S -B - "$CONFIG_CANDIDATE" "$RELEASE_ROOT" "$PRIVILEGED_RECEIPT_ROOT" "$CONTROL_UID" "$OPERATOR_UID" <<'PY'
import json, os, pathlib, sys
path, release_root, receipt_root, control_uid, operator_uid = sys.argv[1:]
value = {
    "schema": "mastermind.executive_privileged_broker_config.v1",
    "release_root": release_root,
    "receipt_root": receipt_root,
    "allowed_peer_uids": sorted({int(control_uid), int(operator_uid)}),
    "timeout_seconds": int(broker_timeout),
    "broker_version": "1",
}
out = pathlib.Path(path)
out.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
os.chmod(out, 0o400)
PY
install_or_verify_generated_file "$CONFIG_CANDIDATE" "$PRIVILEGED_CONFIG" 0 0 "$CONFIG_MODE"

ADMIN_CANDIDATE="$(/usr/bin/mktemp "$SYSTEM_ROOT/bin/.mmx-admin.secondary.XXXXXX")"
/usr/bin/printf '%s\n' '#!/bin/bash'   "exec \"$PYTHON_BINARY\" -I -S -B \"$RELEASE_ROOT/scripts/mmx_admin.py\" \"\$@\""   >"$ADMIN_CANDIDATE"
install_or_verify_generated_file "$ADMIN_CANDIDATE" "$MMX_ADMIN" 0 0 "$LAUNCHER_MODE"

POWER_LAUNCHER="$SYSTEM_ROOT/bin/mmx-secondary-host-power"
POWER_CANDIDATE="$(/usr/bin/mktemp "$SYSTEM_ROOT/bin/.mmx-secondary-host-power.XXXXXX")"
/usr/bin/printf '%s\n' '#!/bin/bash'   "exec \"$PYTHON_BINARY\" -I -S -B \"$RELEASE_ROOT/scripts/mmx_secondary_host_power.py\" \"\$@\""   >"$POWER_CANDIDATE"
install_or_verify_generated_file "$POWER_CANDIDATE" "$POWER_LAUNCHER" 0 0 "$LAUNCHER_MODE"

PLIST_CANDIDATE="$(/usr/bin/mktemp "/Library/LaunchDaemons/.$PRIVILEGED_LABEL.secondary.XXXXXX")"
/usr/bin/install -o root -g wheel -m 0644   "$RELEASE_ROOT/ops/executive_os/$PRIVILEGED_LABEL.plist.template" "$PLIST_CANDIDATE"
"$PYTHON_BINARY" -I -S -B   "$RELEASE_ROOT/ops/executive_os/render_launchd_program_arguments.py"   "$PLIST_CANDIDATE" --   "$PYTHON_BINARY" -I -S -B   "$RELEASE_ROOT/scripts/executive_os_privileged_broker.py"   serve --config "$PRIVILEGED_CONFIG"
/usr/bin/plutil -replace WorkingDirectory -string "$RELEASE_ROOT" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace Sockets.PrivilegedActions.SockPathName -string "$PRIVILEGED_SOCKET" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace Sockets.PrivilegedActions.SockPathOwner -integer "$CONTROL_UID" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace Sockets.PrivilegedActions.SockPathGroup -integer "$OPS_GID" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace Sockets.PrivilegedActions.SockPathMode -integer "$SOCKET_MODE_DECIMAL" "$PLIST_CANDIDATE"
/usr/bin/plutil -replace StandardOutPath -string /var/log/mastermind-executive/privileged/stdout.log "$PLIST_CANDIDATE"
/usr/bin/plutil -replace StandardErrorPath -string /var/log/mastermind-executive/privileged/stderr.log "$PLIST_CANDIDATE"
/usr/bin/plutil -lint "$PLIST_CANDIDATE" >/dev/null || refuse "rendered privileged plist is invalid"
install_or_verify_generated_file "$PLIST_CANDIDATE" "$PRIVILEGED_PLIST" 0 0 "$PLIST_MODE"

# Re-prove the exact release after every generated path is bound to it.
"$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/ops/executive_os/release_manifest.py" verify   --root "$RELEASE_ROOT" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA" >/dev/null   || refuse "release changed during privileged-substrate installation"
assert_central_absent

if ! /bin/launchctl print "system/$PRIVILEGED_LABEL" >/dev/null 2>&1; then
  BROKER_ARM_MUTATION_STARTED="1"
  /bin/launchctl enable "system/$PRIVILEGED_LABEL"
  /bin/launchctl bootstrap system "$PRIVILEGED_PLIST"
fi
for attempt in 1 2 3 4 5; do
  [ -S "$PRIVILEGED_SOCKET" ] && break
  /bin/sleep 1
done
[ -S "$PRIVILEGED_SOCKET" ]   && [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$PRIVILEGED_SOCKET")" = "$CONTROL_UID:$OPS_GID:$SOCKET_MODE_STAT" ]   || refuse "privileged broker socket is absent or has unsafe metadata"

OPERATOR_HOME="$(/usr/bin/dscl . -read "/Users/$OPERATOR_USER" NFSHomeDirectory 2>/dev/null | /usr/bin/awk '{$1=""; sub(/^ /,""); print}')"
case "$OPERATOR_HOME" in /*) ;; *) refuse "operator home is unavailable" ;; esac
set +e
STATUS_OUTPUT="$(/usr/bin/sudo -u "$OPERATOR_USER" /usr/bin/env -i   HOME="$OPERATOR_HOME" PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C.UTF-8 LC_ALL=C.UTF-8   "$MMX_ADMIN" status --request-id fleet-secondary-prep-probe 2>/dev/null)"
STATUS_RC=$?
set -e
[ "$STATUS_RC" -eq 4 ] || refuse "privileged broker read-only status probe did not return NOT_FOUND"
/bin/echo "$STATUS_OUTPUT" | "$PYTHON_BINARY" -I -S -B - "$EXPECTED_SHA" <<'PY'   || refuse "privileged broker read-only status response is invalid"
import json, sys
value = json.load(sys.stdin)
expected_sha = sys.argv[1]
expected = {
    "schema", "ok", "query", "status", "request_id", "installed_release_sha",
}
if set(value) != expected:
    raise RuntimeError("status response shape differs")
if value.get("schema") != "mastermind.executive_privileged_action_response.v1":
    raise RuntimeError("status response schema differs")
if value.get("ok") is not True or value.get("query") is not True:
    raise RuntimeError("status response is not a successful query")
if value.get("status") != "NOT_FOUND" or value.get("request_id") != "fleet-secondary-prep-probe":
    raise RuntimeError("status response identity differs")
if value.get("installed_release_sha") != expected_sha:
    raise RuntimeError("installed release identity differs")
PY

# The install is not complete unless the central-control anti-duplication fact
# survived every release/config/plist/launchd mutation above.
assert_central_absent
COMPLETED="1"
/bin/echo "{\"schema\":\"mastermind.secondary_privileged_host_preparation/v1\",\"outcome\":\"READY_FOR_GOVERNED_POWER_REMEDIATION\",\"release_sha\":\"$EXPECTED_SHA\"}"
