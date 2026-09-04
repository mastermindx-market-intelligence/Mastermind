#!/bin/bash
# Credential-free host preparation for the C1 SOL_STATE Relay.
#
# This wave creates/verifies one dedicated non-login service principal, renders
# the fixed Relay LaunchDaemon from an exact installed Mastermind release, and
# exposes the already-implemented CeoIngress listener to that principal through
# its own AF_UNIX socket. It does not enroll a credential, call Slack, enable or
# start the Relay, arm CeoIngress writes, or create any runtime/lifecycle state.
set -euo pipefail
umask 077

RELAY_USER="_mastermind_sol_relay"
RELAY_GROUP="_mastermind_sol_relay"
RELAY_UID="452"
RELAY_GID="452"
RELAY_LABEL="com.mastermind.executive.sol-state-relay"
CONTROL_LABEL="com.mastermind.executive.control"
CONTROL_UID="450"
CONTROL_GID="450"
OPS_GID="453"
CEO_INGRESS_SOCKET="/var/run/mastermind-executive/ceo-ingress.sock"
DIALOGUE_OBSERVATION_SOCKET="/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
DIALOGUE_RELAY_GID="457"
SOL_RUNTIME_CHANNEL_ID="C0BSGABKBFY"
WORKSPACE_ID="T0BRD2AQXQV"

SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
RUNTIME_ROOT="/var/db/mastermind-executive"
CONTROL_CONFIG="$SYSTEM_ROOT/config/control.json"
CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"
RELAY_PLIST="/Library/LaunchDaemons/$RELAY_LABEL.plist"
RELAY_CONFIG="$SYSTEM_ROOT/config/sol-state-relay.json"
RELAY_TOKEN_FILE="$SYSTEM_ROOT/config/sol-state-relay.token"
RELAY_HOME="$RUNTIME_ROOT/sol-state-relay/home"
RELAY_LOG_ROOT="/var/log/mastermind-executive/sol-state-relay"
PYTHON_BINARY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
RELEASE_ROOT=""

usage() {
  /bin/echo "usage: $0 --release-root /Library/Application\\ Support/MastermindExecutive/releases/<40hex>" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --release-root) RELEASE_ROOT="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "prepare-c1-sol-state-relay.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "prepare-c1-sol-state-relay.sh supports macOS only" >&2
  exit 69
}
[ -n "$RELEASE_ROOT" ] || usage
case "$RELEASE_ROOT" in
  "$SYSTEM_ROOT"/releases/*) ;;
  *) /bin/echo "release root must be beneath the reviewed MastermindExecutive releases root" >&2; exit 65 ;;
esac
[ -d "$RELEASE_ROOT" ] && [ ! -L "$RELEASE_ROOT" ] || {
  /bin/echo "release root is unavailable or is a symlink" >&2
  exit 65
}
RELEASE_SHA="${RELEASE_ROOT##*/}"
case "$RELEASE_SHA" in
  *[!0-9a-f]*|'') /bin/echo "release directory name is not a lowercase hexadecimal SHA" >&2; exit 65 ;;
esac
[ "${#RELEASE_SHA}" -eq 40 ] || {
  /bin/echo "release directory must be named by one full 40-character SHA" >&2
  exit 65
}
[ "$(/usr/bin/stat -f '%u:%g' "$RELEASE_ROOT")" = "0:0" ] || {
  /bin/echo "release root is not root:wheel" >&2
  exit 65
}
RELEASE_MODE="$(/usr/bin/stat -f '%Lp' "$RELEASE_ROOT")"
[ "$((8#$RELEASE_MODE & 8#022))" -eq 0 ] || {
  /bin/echo "release root is writable by group or other" >&2
  exit 65
}
case "$(/usr/bin/stat -f '%Sp' "$RELEASE_ROOT")" in
  *+) /bin/echo "release root has a filesystem ACL" >&2; exit 65 ;;
esac
[ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || {
  /bin/echo "reviewed Executive Python binary is unavailable" >&2
  exit 65
}

RELAY_ENTRYPOINT="$RELEASE_ROOT/scripts/c1_sol_state_relay.py"
RELAY_PLIST_TEMPLATE="$RELEASE_ROOT/ops/executive_os/$RELAY_LABEL.plist.template"
RENDER_PROGRAM_ARGUMENTS="$RELEASE_ROOT/ops/executive_os/render_launchd_program_arguments.py"
RELEASE_MANIFEST="$RELEASE_ROOT/.executive-release-manifest.json"
RELEASE_VERIFIER="$RELEASE_ROOT/ops/executive_os/release_manifest.py"
for required in "$RELAY_ENTRYPOINT" "$RELAY_PLIST_TEMPLATE" "$RENDER_PROGRAM_ARGUMENTS" \
  "$RELEASE_MANIFEST" "$RELEASE_VERIFIER" "$CONTROL_CONFIG" "$CONTROL_PLIST"; do
  [ -f "$required" ] && [ ! -L "$required" ] || {
    /bin/echo "required C1 installed surface is unavailable" >&2
    exit 65
  }
done

# Installed release trees intentionally contain no .git. Read the immutable
# manifest's recorded tree identity, bind it to the release-directory commit,
# then run the repository's full manifest verifier over every installed object.
TREE_SHA="$("$PYTHON_BINARY" -I -S -B - "$RELEASE_MANIFEST" "$RELEASE_SHA" <<'PY'
import json, pathlib, re, sys
path = pathlib.Path(sys.argv[1])
expected_commit = sys.argv[2]
try:
    value = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(65)
if not isinstance(value, dict):
    raise SystemExit(65)
if value.get("schema_version") != "mastermind.executive_release_manifest/v1":
    raise SystemExit(65)
if value.get("commit_sha") != expected_commit:
    raise SystemExit(65)
tree_sha = value.get("tree_sha")
if not isinstance(tree_sha, str) or re.fullmatch(r"[0-9a-f]{40}", tree_sha) is None:
    raise SystemExit(65)
print(tree_sha)
PY
)" || {
  /bin/echo "installed release manifest identity is invalid" >&2
  exit 65
}
"$PYTHON_BINARY" -I -S -B "$RELEASE_VERIFIER" verify \
  --root "$RELEASE_ROOT" --commit-sha "$RELEASE_SHA" --tree-sha "$TREE_SHA" \
  >/dev/null || {
    /bin/echo "installed release differs from its immutable manifest" >&2
    exit 65
  }

# The standard Executive installer must already have rendered control config
# from this same exact release. C1 extends that one process/listener family; it
# does not manufacture another control service or alter write arming.
"$PYTHON_BINARY" -I -S -B - "$CONTROL_CONFIG" "$RELEASE_SHA" <<'PY' || {
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
release_sha = sys.argv[2]
try:
    value = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(65)
expected = {
    "ceo_ingress_launchd_socket_name": "CeoIngress",
    "ceo_ingress_peer_uid": 452,
    "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
    "proof_base_sha": release_sha,
    "dialogue_bridge_armed": False,
    "dialogue_observation_launchd_socket_name": "DialogueObservation",
    "dialogue_observation_peer_uid": 457,
    "dialogue_observation_socket_path": "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
    "dialogue_wake_retry_policy": {
        "accepted_ttl_s": None,
        "armed": False,
        "max_delivery_attempts": None,
        "reenable_on_binding_rotation": True,
        "retry_cooldown_s": None,
        "target_unavailable_backoff_s": None,
    },
}
if not isinstance(value, dict) or any(value.get(k) != v for k, v in expected.items()):
    raise SystemExit(65)
if "ceo_ingress_armed" in value:
    raise SystemExit(65)
PY
  /bin/echo "installed Executive control config is not the reviewed C1-unarmed composition" >&2
  exit 65
}

# Never rewrite a loaded daemon definition. Existing Executive install/acceptance
# owns the later fresh restart/canary and must requalify after this change.
if /bin/launchctl print "system/$CONTROL_LABEL" >/dev/null 2>&1; then
  /bin/echo "Executive control service is loaded; stop it before C1 host preparation" >&2
  exit 75
fi
/bin/launchctl disable "system/$RELAY_LABEL" >/dev/null 2>&1 || true
/bin/launchctl bootout "system/$RELAY_LABEL" >/dev/null 2>&1 || true
if /bin/launchctl print "system/$RELAY_LABEL" >/dev/null 2>&1; then
  /bin/echo "C1 Relay remained loaded after bootout" >&2
  exit 65
fi

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
    /bin/echo "$attribute $numeric has an unexpected owner set" >&2
    exit 65
  fi
}

ensure_group() {
  ensure_numeric_unused Groups PrimaryGroupID "$RELAY_GID" "$RELAY_GROUP"
  if /usr/bin/dscl . -read "/Groups/$RELAY_GROUP" >/dev/null 2>&1; then
    [ "$(read_attribute "/Groups/$RELAY_GROUP" PrimaryGroupID)" = "$RELAY_GID" ] \
      && [ "$(read_attribute "/Groups/$RELAY_GROUP" RealName)" = "$RELAY_GROUP service group" ] || {
        /bin/echo "existing Relay group differs from the reviewed identity" >&2
        exit 65
      }
  else
    /usr/bin/dscl . -create "/Groups/$RELAY_GROUP"
    /usr/bin/dscl . -create "/Groups/$RELAY_GROUP" PrimaryGroupID "$RELAY_GID"
    /usr/bin/dscl . -create "/Groups/$RELAY_GROUP" RealName "$RELAY_GROUP service group"
    /usr/bin/dscl . -create "/Groups/$RELAY_GROUP" GeneratedUID "$(/usr/bin/uuidgen)"
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
      && [ "$(read_attribute "/Users/$RELAY_USER" Password)" = "*" ] || {
        /bin/echo "existing Relay user differs from the reviewed identity" >&2
        exit 65
      }
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
  /usr/bin/pwpolicy -n /Local/Default -u "$RELAY_USER" -disableuser >/dev/null 2>&1 || {
    /bin/echo "could not disable Relay service-account authentication" >&2
    exit 65
  }
  AUTH_PROBE="$(/usr/bin/uuidgen)"
  if /usr/bin/dscl . -authonly "$RELAY_USER" "$AUTH_PROBE" >/dev/null 2>&1; then
    /bin/echo "Relay service account unexpectedly accepted authentication" >&2
    exit 65
  fi
}

ensure_group
ensure_user

# Relay must remain out of broad Executive/worker groups. CeoIngress access is
# granted by the dedicated socket's primary GID, not by _mastermind_ops.
for forbidden_group in _mastermind_exec _mastermind_worker _mastermind_ops \
  _mastermind_codex_01 _mastermind_codex_02 _mastermind_codex_03; do
  if /usr/sbin/dseditgroup -o checkmember -m "$RELAY_USER" "$forbidden_group" 2>/dev/null \
      | /usr/bin/grep -q 'yes'; then
    /bin/echo "Relay service account is a member of a forbidden Executive group" >&2
    exit 65
  fi
done

/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT"
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT/config"
/usr/bin/install -d -o root -g wheel -m 0711 "$RUNTIME_ROOT"
/usr/bin/install -d -o "$RELAY_USER" -g "$RELAY_GROUP" -m 0700 "$RUNTIME_ROOT/sol-state-relay"
/usr/bin/install -d -o "$RELAY_USER" -g "$RELAY_GROUP" -m 0700 "$RELAY_HOME"
/usr/bin/install -d -o root -g wheel -m 0755 /var/log/mastermind-executive
/usr/bin/install -d -o "$RELAY_USER" -g "$RELAY_GROUP" -m 0700 "$RELAY_LOG_ROOT"

# This preparation wave is credential-free. Existing config/token means another
# enrollment carrier may own the host and must be reconciled, never overwritten.
[ ! -e "$RELAY_TOKEN_FILE" ] && [ ! -L "$RELAY_TOKEN_FILE" ] || {
  /bin/echo "C1 credential already exists; reconcile existing enrollment first" >&2
  exit 75
}
[ ! -e "$RELAY_CONFIG" ] && [ ! -L "$RELAY_CONFIG" ] || {
  /bin/echo "C1 runtime config already exists; reconcile existing enrollment first" >&2
  exit 75
}

/usr/bin/plutil -replace Sockets.CeoIngress.SockPathName -string "$CEO_INGRESS_SOCKET" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.CeoIngress.SockPathOwner -integer "$CONTROL_UID" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.CeoIngress.SockPathGroup -integer "$RELAY_GID" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.CeoIngress.SockPathMode -integer 432 "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.DialogueObservation.SockPathName -string "$DIALOGUE_OBSERVATION_SOCKET" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.DialogueObservation.SockPathOwner -integer "$CONTROL_UID" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.DialogueObservation.SockPathGroup -integer "$DIALOGUE_RELAY_GID" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.DialogueObservation.SockPathMode -integer 432 "$CONTROL_PLIST"

# Re-assert the broad Operator socket is unchanged and inaccessible to Relay.
/usr/bin/plutil -replace Sockets.Operator.SockPathOwner -integer "$CONTROL_UID" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.Operator.SockPathGroup -integer "$OPS_GID" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.Operator.SockPathMode -integer 432 "$CONTROL_PLIST"
CONTROL_SOCKET_POLICY="$CONTROL_UID:$OPS_GID:432"
CEO_SOCKET_POLICY="$CONTROL_UID:$RELAY_GID:432"
DIALOGUE_SOCKET_POLICY="$CONTROL_UID:$DIALOGUE_RELAY_GID:432"
"$PYTHON_BINARY" -I -S -B - "$CONTROL_PLIST" "$CONTROL_SOCKET_POLICY" "$CEO_SOCKET_POLICY" "$DIALOGUE_SOCKET_POLICY" <<'PY' || {
import plistlib, pathlib, sys
path, expected_operator, expected_ceo, expected_dialogue = sys.argv[1:]
doc = plistlib.loads(pathlib.Path(path).read_bytes())
sockets = doc.get("Sockets")
if not isinstance(sockets, dict) or set(sockets) != {"Operator", "CeoIngress", "DialogueObservation"}:
    raise SystemExit(65)
def policy(name):
    row = sockets[name]
    return f"{row.get('SockPathOwner')}:{row.get('SockPathGroup')}:{row.get('SockPathMode')}"
if (policy("Operator") != expected_operator or policy("CeoIngress") != expected_ceo
        or policy("DialogueObservation") != expected_dialogue):
    raise SystemExit(65)
if sockets["CeoIngress"].get("SockPathName") != "/var/run/mastermind-executive/ceo-ingress.sock":
    raise SystemExit(65)
if sockets["DialogueObservation"].get("SockPathName") != "/var/run/mastermind-dialogue-observation/dialogue-observation.sock":
    raise SystemExit(65)
PY
  /bin/echo "installed Executive socket policy differs from C1 freeze" >&2
  exit 65
}
/usr/sbin/chown root:wheel "$CONTROL_PLIST"
/bin/chmod 0644 "$CONTROL_PLIST"
/usr/bin/plutil -lint "$CONTROL_PLIST" >/dev/null

/usr/bin/install -o root -g wheel -m 0644 "$RELAY_PLIST_TEMPLATE" "$RELAY_PLIST"
"$PYTHON_BINARY" -I -S -B "$RENDER_PROGRAM_ARGUMENTS" "$RELAY_PLIST" -- \
  "$PYTHON_BINARY" -I -S -B "$RELAY_ENTRYPOINT" --config "$RELAY_CONFIG"
/usr/bin/plutil -replace WorkingDirectory -string "$RELEASE_ROOT" "$RELAY_PLIST"
/usr/bin/plutil -replace UserName -string "$RELAY_USER" "$RELAY_PLIST"
/usr/bin/plutil -replace GroupName -string "$RELAY_GROUP" "$RELAY_PLIST"
/usr/bin/plutil -replace EnvironmentVariables.HOME -string "$RELAY_HOME" "$RELAY_PLIST"
/usr/bin/plutil -replace StandardOutPath -string "$RELAY_LOG_ROOT/stdout.log" "$RELAY_PLIST"
/usr/bin/plutil -replace StandardErrorPath -string "$RELAY_LOG_ROOT/stderr.log" "$RELAY_PLIST"
/usr/sbin/chown root:wheel "$RELAY_PLIST"
/bin/chmod 0644 "$RELAY_PLIST"
/usr/bin/plutil -lint "$RELAY_PLIST" >/dev/null

for protected_path in "$CONTROL_CONFIG" "$CONTROL_PLIST" "$RELAY_PLIST" \
  "$RUNTIME_ROOT/sol-state-relay" "$RELAY_HOME" "$RELAY_LOG_ROOT"; do
  case "$(/usr/bin/stat -f '%Sp' "$protected_path")" in
    *+) /bin/echo "unexpected filesystem ACL on C1 prepared path" >&2; exit 65 ;;
  esac
done

# Leave the Relay inert. The later native enrollment ceremony owns final
# config/token creation, app identity/scope verification, channel membership,
# enable/start and production proof.
/bin/launchctl disable "system/$RELAY_LABEL" >/dev/null 2>&1 || true
/bin/launchctl bootout "system/$RELAY_LABEL" >/dev/null 2>&1 || true
if /bin/launchctl print "system/$RELAY_LABEL" >/dev/null 2>&1; then
  /bin/echo "C1 Relay unexpectedly loaded during credential-free preparation" >&2
  exit 65
fi

/bin/echo "C1_SOL_STATE_RELAY_HOST_PREPARED_CREDENTIAL_FREE"
/bin/echo "workspace=$WORKSPACE_ID channel=$SOL_RUNTIME_CHANNEL_ID relay_uid=$RELAY_UID"
/bin/echo "next: native Relay app/token enrollment and production proof; service remains disabled"
