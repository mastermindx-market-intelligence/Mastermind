#!/bin/bash
# Install one clean exact-SHA Executive OS release and two non-root system
# LaunchDaemons. Root is used only for this bootstrap/install operation.
set -euo pipefail
umask 077

CONTROL_LABEL="com.mastermind.executive.control"
WORKER_LABEL="com.mastermind.executive.worker.codex"
CONTROL_USER="_mastermind_exec"
CONTROL_GROUP="_mastermind_exec"
WORKER_USER="_mastermind_worker"
WORKER_GROUP="_mastermind_worker"
CONTROL_UID="450"
CONTROL_GID="450"
WORKER_UID="451"
WORKER_GID="451"
OPS_GID="453"
SOURCE_REPO=""
EXPECTED_SHA=""
CONTROL_CONFIG_SOURCE=""
OPERATOR_USER=""
PYTHON_BINARY=""
PYTHON_RUNTIME_ROOT=""
PYTHON_TEAM_ID="BMM5U3QVKW"
PYTHON_VERSION="3.12.10"
PYTHON_PACKAGE_SHA256="8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4"
PYTHON_BINARY_SHA256="d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"
PYTHON_FRAMEWORK_SHA256="14e61fb22a897d238248dfd8fe3b472b4541338c293368b4747803055b8bb3aa"
PINNED_PYTHON_RUNTIME_ROOT="/Library/Frameworks/Python.framework/Versions/3.12"
PINNED_PYTHON_BINARY="$PINNED_PYTHON_RUNTIME_ROOT/bin/python3.12"
PYTHON_RUNTIME_RECEIPT="/Library/Application Support/MastermindExecutive/python-runtime.json"
CODEX_BINARY="/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex"
CODEX_VERSION="0.147.0"
CODEX_SHA256="19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"

usage() {
  /bin/echo "usage: $0 --source-repo PATH --expected-sha SHA --operator-user NAME [--control-config PATH] [options]" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-repo) SOURCE_REPO="${2:-}"; shift 2 ;;
    --expected-sha) EXPECTED_SHA="${2:-}"; shift 2 ;;
    --operator-user) OPERATOR_USER="${2:-}"; shift 2 ;;
    --control-config) CONTROL_CONFIG_SOURCE="${2:-}"; shift 2 ;;
    --python-binary) PYTHON_BINARY="${2:-}"; shift 2 ;;
    --python-runtime-root) PYTHON_RUNTIME_ROOT="${2:-}"; shift 2 ;;
    --python-team-identifier) PYTHON_TEAM_ID="${2:-}"; shift 2 ;;
    --codex-binary) CODEX_BINARY="${2:-}"; shift 2 ;;
    --codex-version) CODEX_VERSION="${2:-}"; shift 2 ;;
    --control-uid) CONTROL_UID="${2:-}"; CONTROL_GID="${2:-}"; shift 2 ;;
    --worker-uid) WORKER_UID="${2:-}"; WORKER_GID="${2:-}"; shift 2 ;;
    --ops-gid) OPS_GID="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "install.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "install.sh supports macOS only" >&2
  exit 69
}
[ -n "$SOURCE_REPO" ] && [ -n "$EXPECTED_SHA" ] && [ -n "$OPERATOR_USER" ] || usage
case "$OPERATOR_USER" in
  [A-Za-z_]* ) ;;
  *) /bin/echo "operator account name is invalid" >&2; exit 65 ;;
esac
case "$OPERATOR_USER" in *[!A-Za-z0-9_.-]*) /bin/echo "operator account name is invalid" >&2; exit 65 ;; esac
[ -n "$PYTHON_BINARY" ] && [ -n "$PYTHON_RUNTIME_ROOT" ] || {
  /bin/echo "install requires --python-binary and --python-runtime-root for a pre-provisioned root-owned signed Python 3.12 standard-library runtime" >&2
  exit 65
}
[ "$PYTHON_RUNTIME_ROOT" = "$PINNED_PYTHON_RUNTIME_ROOT" ] \
  && [ "$PYTHON_BINARY" = "$PINNED_PYTHON_BINARY" ] \
  && [ "$PYTHON_TEAM_ID" = "BMM5U3QVKW" ] || {
    /bin/echo "install requires the exact reviewed Executive Python runtime path and PSF signer" >&2
    exit 65
  }
case "$EXPECTED_SHA" in
  *[!0-9a-f]*|'') /bin/echo "expected SHA must be lowercase hexadecimal" >&2; exit 65 ;;
esac
[ "${#EXPECTED_SHA}" -eq 40 ] || {
  /bin/echo "expected SHA must contain exactly 40 hexadecimal characters" >&2
  exit 65
}
for install_path in "$SOURCE_REPO" "$PYTHON_BINARY" "$PYTHON_RUNTIME_ROOT" "$CODEX_BINARY"; do
  case "$install_path" in /*) ;; *) /bin/echo "install paths must be absolute: $install_path" >&2; exit 65 ;; esac
done
if [ -n "$CONTROL_CONFIG_SOURCE" ]; then
  case "$CONTROL_CONFIG_SOURCE" in /*) ;; *) /bin/echo "control config path must be absolute" >&2; exit 65 ;; esac
fi
[ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || {
  /bin/echo "Python binary must be a direct executable file" >&2
  exit 65
}
[ -d "$PYTHON_RUNTIME_ROOT" ] && [ ! -L "$PYTHON_RUNTIME_ROOT" ] || {
  /bin/echo "Python runtime root must be a direct directory" >&2
  exit 65
}
for python_ancestor in \
  /Library \
  /Library/Frameworks \
  /Library/Frameworks/Python.framework \
  /Library/Frameworks/Python.framework/Versions; do
  [ -d "$python_ancestor" ] && [ ! -L "$python_ancestor" ] \
    && [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$python_ancestor")" = "0:0:755" ] || {
      /bin/echo "Python runtime ancestor is not a direct root:wheel mode 0755 directory: $python_ancestor" >&2
      exit 65
    }
  case "$(/usr/bin/stat -f '%Sp' "$python_ancestor")" in
    *+) /bin/echo "Python runtime ancestor has a filesystem ACL: $python_ancestor" >&2; exit 65 ;;
  esac
done
case "$PYTHON_BINARY" in
  "$PYTHON_RUNTIME_ROOT"/*) ;;
  *) /bin/echo "Python binary must be contained by its pinned runtime root" >&2; exit 65 ;;
esac
[ "$(/usr/bin/stat -f '%l' "$PYTHON_BINARY")" -eq 1 ] || {
  /bin/echo "Python executable must have exactly one hard link" >&2
  exit 65
}
[ "$(/usr/bin/stat -f '%u' "$PYTHON_BINARY")" -eq 0 ] || {
  /bin/echo "Python executable must be root-owned" >&2
  exit 65
}
PYTHON_MODE="$(/usr/bin/stat -f '%Lp' "$PYTHON_BINARY")"
[ "$((8#$PYTHON_MODE & 8#022))" -eq 0 ] || {
  /bin/echo "Python executable must not be writable by group or other" >&2
  exit 65
}
if [ -n "$(/usr/bin/find "$PYTHON_RUNTIME_ROOT" ! -user root -print -quit)" ]; then
  /bin/echo "Python runtime contains a non-root-owned object" >&2
  exit 65
fi
if [ -n "$(/usr/bin/find "$PYTHON_RUNTIME_ROOT" ! -group wheel -print -quit)" ]; then
  /bin/echo "Python runtime contains an object outside the wheel group" >&2
  exit 65
fi
if [ -n "$(/usr/bin/find "$PYTHON_RUNTIME_ROOT" -perm +022 -print -quit)" ]; then
  /bin/echo "Python runtime contains a group/other-writable object" >&2
  exit 65
fi
while IFS= read -r -d '' runtime_link; do
  runtime_target="$(/usr/bin/readlink -f "$runtime_link")" || {
    /bin/echo "Python runtime contains a dangling symlink" >&2
    exit 65
  }
  case "$runtime_target" in
    "$PYTHON_RUNTIME_ROOT"/*) ;;
    *) /bin/echo "Python runtime symlink escapes the pinned root" >&2; exit 65 ;;
  esac
done < <(/usr/bin/find "$PYTHON_RUNTIME_ROOT" -type l -print0)
if [ -n "$(/usr/bin/find "$PYTHON_RUNTIME_ROOT" -exec /usr/bin/stat -f '%Sp' {} \; \
  | /usr/bin/awk '/\+/{found=1} END {if(found) print "ACL"}')" ]; then
  /bin/echo "Python runtime contains a filesystem ACL" >&2
  exit 65
fi
/usr/bin/codesign --verify --deep --strict "$PYTHON_RUNTIME_ROOT" >/dev/null 2>&1 || {
  /bin/echo "Python runtime signature/sealed resources are invalid" >&2
  exit 65
}
OBSERVED_PYTHON_TEAM="$(/usr/bin/codesign -dv --verbose=4 "$PYTHON_BINARY" 2>&1 | /usr/bin/awk -F= '$1 == "TeamIdentifier" {print $2}')"
[ "$OBSERVED_PYTHON_TEAM" = "$PYTHON_TEAM_ID" ] || {
  /bin/echo "Python runtime signer team is not the explicit allowlist" >&2
  exit 65
}
OBSERVED_PYTHON_BINARY_SHA256="$(/usr/bin/shasum -a 256 "$PYTHON_BINARY" | /usr/bin/awk '{print $1}')"
OBSERVED_PYTHON_FRAMEWORK_SHA256="$(/usr/bin/shasum -a 256 "$PYTHON_RUNTIME_ROOT/Python" | /usr/bin/awk '{print $1}')"
[ "$OBSERVED_PYTHON_BINARY_SHA256" = "$PYTHON_BINARY_SHA256" ] \
  && [ "$OBSERVED_PYTHON_FRAMEWORK_SHA256" = "$PYTHON_FRAMEWORK_SHA256" ] || {
    /bin/echo "Python runtime bytes differ from the reviewed package allowlist" >&2
    exit 65
  }
"$PYTHON_BINARY" -I -S -B -c 'import asyncio,ctypes,hashlib,json,plistlib,sqlite3,ssl,sys; assert sys.version.split()[0] == "3.12.10"' || {
  /bin/echo "pinned runtime is not exact Python 3.12.10 with the required standard library" >&2
  exit 65
}
"$PYTHON_BINARY" -I -S -B - "$PYTHON_RUNTIME_ROOT" "$PYTHON_BINARY" <<'PY' || {
import _ctypes
import _sqlite3
import _ssl
import asyncio
import ctypes
import pathlib
import sqlite3
import ssl
import sys
import sysconfig


class DlInfo(ctypes.Structure):
    _fields_ = [
        ("dli_fname", ctypes.c_char_p),
        ("dli_fbase", ctypes.c_void_p),
        ("dli_sname", ctypes.c_char_p),
        ("dli_saddr", ctypes.c_void_p),
    ]


root = pathlib.Path(sys.argv[1]).resolve(strict=True)
expected_binary = pathlib.Path(sys.argv[2]).resolve(strict=True)


def require_inside(raw: str, label: str) -> pathlib.Path:
    observed = pathlib.Path(raw).resolve(strict=True)
    if observed != root and root not in observed.parents:
        raise RuntimeError(f"{label} escapes the pinned runtime root")
    return observed


if pathlib.Path(sys.executable).resolve(strict=True) != expected_binary:
    raise RuntimeError("live Python executable differs from the attested binary")
if pathlib.Path(sys.prefix).resolve(strict=True) != root:
    raise RuntimeError("live Python prefix differs from the attested runtime root")
if pathlib.Path(sys.base_prefix).resolve(strict=True) != root:
    raise RuntimeError("live Python base prefix differs from the attested runtime root")

require_inside(sysconfig.get_path("stdlib"), "standard library")
for module in (asyncio, sqlite3, ssl, _ctypes, _sqlite3, _ssl):
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        raise RuntimeError(f"module {module.__name__} has no file origin")
    require_inside(origin, f"module {module.__name__}")

libc = ctypes.CDLL(None)
libc.dladdr.argtypes = (ctypes.c_void_p, ctypes.POINTER(DlInfo))
libc.dladdr.restype = ctypes.c_int
info = DlInfo()
address = ctypes.cast(ctypes.pythonapi.Py_GetVersion, ctypes.c_void_p)
if libc.dladdr(address, ctypes.byref(info)) != 1 or not info.dli_fname:
    raise RuntimeError("could not attest the loaded Python framework")
require_inside(info.dli_fname.decode("utf-8"), "loaded Python framework")
PY
  /bin/echo "live Python runtime or module origin escapes the pinned root" >&2
  exit 65
}
[ -f "$PYTHON_RUNTIME_RECEIPT" ] && [ ! -L "$PYTHON_RUNTIME_RECEIPT" ] \
  && [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$PYTHON_RUNTIME_RECEIPT")" = "0:0:400:1" ] || {
    /bin/echo "Python runtime provenance receipt is missing or has unsafe metadata" >&2
    exit 65
  }
case "$(/usr/bin/stat -f '%Sp' "$PYTHON_RUNTIME_RECEIPT")" in
  *+) /bin/echo "Python runtime provenance receipt has a filesystem ACL" >&2; exit 65 ;;
esac
"$PYTHON_BINARY" -I -S -B - "$PYTHON_RUNTIME_RECEIPT" "$PYTHON_RUNTIME_ROOT" \
  "$PYTHON_BINARY" "$PYTHON_VERSION" "$PYTHON_TEAM_ID" "$PYTHON_PACKAGE_SHA256" \
  "$PYTHON_BINARY_SHA256" "$PYTHON_FRAMEWORK_SHA256" <<'PY' || {
import hashlib
import json
import pathlib
import sys

(
    receipt_path, runtime_root, python_binary, version, team, package_sha,
    binary_sha, framework_sha,
) = sys.argv[1:]
receipt = json.loads(pathlib.Path(receipt_path).read_text(encoding="utf-8"))
expected_keys = {
    "schema_version", "python_version", "runtime_root", "python_binary",
    "team_identifier", "package_sha256", "python_binary_sha256",
    "python_framework_sha256", "prior_runtime_archive",
    "prior_runtime_receipt_archive",
}
if set(receipt) != expected_keys:
    raise RuntimeError("Python runtime receipt shape differs from v1")
expected = {
    "schema_version": "mastermind.executive_python_runtime/v1",
    "python_version": version,
    "runtime_root": runtime_root,
    "python_binary": python_binary,
    "team_identifier": team,
    "package_sha256": package_sha,
    "python_binary_sha256": binary_sha,
    "python_framework_sha256": framework_sha,
}
for key, value in expected.items():
    if receipt.get(key) != value:
        raise RuntimeError(f"Python runtime receipt mismatch: {key}")
prior = receipt.get("prior_runtime_archive")
if not isinstance(prior, str):
    raise RuntimeError("Python runtime receipt prior archive must be a string")
if prior and not prior.startswith(
    "/Library/Application Support/MastermindExecutive/python-archive/prior-3.12-"
):
    raise RuntimeError("Python runtime receipt prior archive escapes its fixed root")
prior_receipt = receipt.get("prior_runtime_receipt_archive")
if not isinstance(prior_receipt, str):
    raise RuntimeError("Python runtime prior receipt archive must be a string")
if prior_receipt and not prior_receipt.startswith(
    "/Library/Application Support/MastermindExecutive/python-archive/prior-receipt-3.12-"
):
    raise RuntimeError("Python runtime prior receipt archive escapes its fixed root")
for path, expected_sha in (
    (pathlib.Path(python_binary), binary_sha),
    (pathlib.Path(runtime_root) / "Python", framework_sha),
):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise RuntimeError("Python runtime receipt hash differs from installed bytes")
PY
  /bin/echo "Python runtime provenance receipt validation failed" >&2
  exit 65
}
[ -x "$CODEX_BINARY" ] && [ ! -L "$CODEX_BINARY" ] || {
  /bin/echo "Codex binary must be a direct executable file" >&2
  exit 65
}
if [ -n "$CONTROL_CONFIG_SOURCE" ]; then
  [ -f "$CONTROL_CONFIG_SOURCE" ] && [ ! -L "$CONTROL_CONFIG_SOURCE" ] || {
    /bin/echo "control config source must be a regular non-symlink file" >&2
    exit 65
  }
fi

/usr/bin/id "$CONTROL_USER" >/dev/null 2>&1 || {
  /bin/echo "missing control account; run bootstrap-host.sh first" >&2
  exit 65
}
/usr/bin/id "$WORKER_USER" >/dev/null 2>&1 || {
  /bin/echo "missing worker account; run bootstrap-host.sh first" >&2
  exit 65
}
/usr/bin/id "$OPERATOR_USER" >/dev/null 2>&1 || {
  /bin/echo "operator user does not exist: $OPERATOR_USER" >&2
  exit 65
}

read_dscl_attribute() {
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
  /bin/echo "$1" \
    | /usr/bin/awk '{for (field_number=1; field_number<=NF; field_number++) print $field_number}' \
    | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
}

verify_authentication_disabled() {
  local name="$1"
  local authority authority_err authority_error authority_out authority_status
  local expected observed probe status
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
  probe="$(/usr/bin/uuidgen)"
  if observed="$(LC_ALL=C LANG=C /usr/bin/dscl . -authonly "$name" "$probe" 2>&1)"; then
    status=0
  else
    status=$?
  fi
  expected='<dscl_cmd> DS Error: -14167 (eDSAuthAccountDisabled)
Authentication for node /Local/Default failed. (-14167, eDSAuthAccountDisabled)'
  [ "$status" -eq 87 ] && [ "$observed" = "$expected" ] || {
    /bin/echo "service account $name is not authentication-disabled" >&2
    exit 65
  }
}

numeric_owners() {
  local record_type="$1"
  local attribute="$2"
  local numeric="$3"
  /usr/bin/dscl . -list "/$record_type" "$attribute" \
    | /usr/bin/awk -v numeric="$numeric" '$NF == numeric {print $1}' \
    | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
}

verify_numeric_owner() {
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

verify_service_account() {
  local name="$1"
  local uid="$2"
  local gid="$3"
  local home="$4"
  [ "$(read_dscl_attribute "/Users/$name" UniqueID)" = "$uid" ] \
    && [ "$(read_dscl_attribute "/Users/$name" PrimaryGroupID)" = "$gid" ] \
    && [ "$(read_dscl_attribute "/Users/$name" RealName)" = "$name service account" ] \
    && [ "$(read_dscl_attribute "/Users/$name" NFSHomeDirectory)" = "$home" ] \
    && [ "$(read_dscl_attribute "/Users/$name" UserShell)" = "/usr/bin/false" ] \
    && [ "$(read_dscl_attribute "/Users/$name" IsHidden)" = "1" ] \
    && [ "$(read_dscl_attribute "/Users/$name" Password)" = "*" ] || {
      /bin/echo "service account $name attributes differ from the disabled-account policy" >&2
      exit 65
    }
  valid_uuid "$(read_dscl_attribute "/Users/$name" GeneratedUID)" || {
    /bin/echo "service account $name has no valid GeneratedUID" >&2
    exit 65
  }
  verify_authentication_disabled "$name"
}

verify_group_members() {
  local group="$1"
  local gid="$2"
  local expected_primary="$3"
  local expected_named="$4"
  local primary named uuid_members expected_uuids nested member member_uuid
  [ "$(read_dscl_attribute "/Groups/$group" PrimaryGroupID)" = "$gid" ] \
    && [ "$(read_dscl_attribute "/Groups/$group" RealName)" = "$group service group" ] \
    && valid_uuid "$(read_dscl_attribute "/Groups/$group" GeneratedUID)" || {
      /bin/echo "protected group $group identity drifted" >&2
      exit 65
    }
  primary="$(
    /usr/bin/dscl . -list /Users PrimaryGroupID \
      | /usr/bin/awk -v gid="$gid" '$NF == gid {print $1}' \
      | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
  )"
  [ "$primary" = "$(sorted_words "$expected_primary")" ] || {
    /bin/echo "group $group contains an unreviewed primary-GID user" >&2
    exit 65
  }
  named="$(read_dscl_attribute "/Groups/$group" GroupMembership 2>/dev/null || true)"
  named="$(sorted_words "$named")"
  [ "$named" = "$(sorted_words "$expected_named")" ] || {
    /bin/echo "group $group contains unreviewed members" >&2
    exit 65
  }
  expected_uuids=""
  for member in $expected_named; do
    member_uuid="$(read_dscl_attribute "/Users/$member" GeneratedUID)"
    valid_uuid "$member_uuid" || {
      /bin/echo "reviewed member $member has no valid GeneratedUID" >&2
      exit 65
    }
    expected_uuids="$expected_uuids $member_uuid"
  done
  uuid_members="$(read_dscl_attribute "/Groups/$group" GroupMembers 2>/dev/null || true)"
  uuid_members="$(sorted_words "$(/bin/echo "$uuid_members" | /usr/bin/tr '[:lower:]' '[:upper:]')")"
  expected_uuids="$(sorted_words "$(/bin/echo "$expected_uuids" | /usr/bin/tr '[:lower:]' '[:upper:]')")"
  [ "$uuid_members" = "$expected_uuids" ] || {
    /bin/echo "group $group contains UUID-only or stale members" >&2
    exit 65
  }
  nested="$(read_dscl_attribute "/Groups/$group" NestedGroups 2>/dev/null || true)"
  if [ -n "$(sorted_words "$nested")" ]; then
    /bin/echo "group $group contains unreviewed nested groups" >&2
    exit 65
  fi
}
[ "$(/usr/bin/id -u "$CONTROL_USER")" = "$CONTROL_UID" ] || {
  /bin/echo "control UID does not match install arguments" >&2
  exit 65
}
[ "$(/usr/bin/id -u "$WORKER_USER")" = "$WORKER_UID" ] || {
  /bin/echo "worker UID does not match install arguments" >&2
  exit 65
}
if ! /usr/bin/id -Gn "$OPERATOR_USER" | /usr/bin/tr ' ' '\n' | /usr/bin/grep -qx '_mastermind_ops'; then
  /bin/echo "operator user is not a member of _mastermind_ops; run bootstrap-host.sh" >&2
  exit 65
fi
OPERATOR_UID="$(/usr/bin/id -u "$OPERATOR_USER")"

HEAD_SHA="$(/usr/bin/git -C "$SOURCE_REPO" rev-parse HEAD)"
[ "$HEAD_SHA" = "$EXPECTED_SHA" ] || {
  /bin/echo "source checkout HEAD is not the exact expected SHA" >&2
  exit 65
}
[ -z "$(/usr/bin/git -C "$SOURCE_REPO" status --porcelain=v1 --untracked-files=normal)" ] || {
  /bin/echo "source checkout is not clean" >&2
  exit 65
}
REMOTE_SHA="$(/usr/bin/git -C "$SOURCE_REPO" rev-parse refs/remotes/origin/master 2>/dev/null || true)"
[ "$REMOTE_SHA" = "$EXPECTED_SHA" ] || {
  /bin/echo "expected SHA is not the checkout's exact origin/master" >&2
  exit 65
}
TREE_SHA="$(/usr/bin/git -C "$SOURCE_REPO" rev-parse "$EXPECTED_SHA^{tree}")"

SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
RUNTIME_ROOT="/var/db/mastermind-executive"
RELEASE_ROOT="$SYSTEM_ROOT/releases/$EXPECTED_SHA"
CONTROL_CONFIG="$SYSTEM_ROOT/config/control.json"
WORKER_CONFIG="$SYSTEM_ROOT/config/worker-codex.json"
CONTROL_HOME="$RUNTIME_ROOT/control/home"
PROVIDER_HOME="$RUNTIME_ROOT/workers/codex-01/provider-home"
WORKSPACE_ROOT="$RUNTIME_ROOT/jobs/workspaces"
RUN_ROOT="$RUNTIME_ROOT/jobs/runs"
CONTROL_RUNTIME_ROOT="$RUNTIME_ROOT/control/db"
RECEIPTS_ROOT="$RUNTIME_ROOT/control/launch-receipts"
BACKUP_ROOT="$RUNTIME_ROOT/control/backups"
CANARY_RECEIPT="$RUNTIME_ROOT/control/canaries/secret-canary.json"
CONTROL_ENV_ATTESTATION="$RUNTIME_ROOT/control/canaries/control-environment-attestation.json"
CONTROL_SENTINEL_FILE="$SYSTEM_ROOT/config/control-env-canary"
AUTH_PATH="$PROVIDER_HOME/auth.json"

verify_service_account "$CONTROL_USER" "$CONTROL_UID" "$CONTROL_GID" "$CONTROL_HOME"
verify_service_account "$WORKER_USER" "$WORKER_UID" "$WORKER_GID" "$PROVIDER_HOME"
verify_group_members "$CONTROL_GROUP" "$CONTROL_GID" "$CONTROL_USER" ""
verify_group_members "$WORKER_GROUP" "$WORKER_GID" "$WORKER_USER" "$CONTROL_USER"
verify_group_members "_mastermind_ops" "$OPS_GID" "" "$OPERATOR_USER"
verify_numeric_owner Users UniqueID "$CONTROL_UID" "$CONTROL_USER"
verify_numeric_owner Users UniqueID "$WORKER_UID" "$WORKER_USER"
verify_numeric_owner Users UniqueID "$OPERATOR_UID" "$OPERATOR_USER"
verify_numeric_owner Groups PrimaryGroupID "$CONTROL_GID" "$CONTROL_GROUP"
verify_numeric_owner Groups PrimaryGroupID "$WORKER_GID" "$WORKER_GROUP"
verify_numeric_owner Groups PrimaryGroupID "$OPS_GID" "_mastermind_ops"

[ -f "$AUTH_PATH" ] && [ ! -L "$AUTH_PATH" ] || {
  /bin/echo "dedicated worker auth is missing: $AUTH_PATH" >&2
  exit 65
}
[ "$(/usr/bin/stat -f '%u' "$AUTH_PATH")" = "$WORKER_UID" ] || {
  /bin/echo "dedicated worker auth has the wrong owner" >&2
  exit 65
}
AUTH_MODE="$(/usr/bin/stat -f '%Lp' "$AUTH_PATH")"
[ "$((8#$AUTH_MODE & 8#077))" -eq 0 ] || {
  /bin/echo "dedicated worker auth is accessible to group or other" >&2
  exit 65
}

# Cross the mutation boundary only after the identity, runtime, source, auth,
# and exact-SHA preflight above. From here to process exit the trap keeps both
# old and new daemon definitions disabled and booted out, including on error.
STAGING=""
leave_installed_services_stopped() {
  /bin/launchctl disable "system/$CONTROL_LABEL" >/dev/null 2>&1 || true
  /bin/launchctl disable "system/$WORKER_LABEL" >/dev/null 2>&1 || true
  /bin/launchctl bootout "system/$CONTROL_LABEL" >/dev/null 2>&1 || true
  /bin/launchctl bootout "system/$WORKER_LABEL" >/dev/null 2>&1 || true
  if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
    /bin/rm -rf -- "$STAGING"
  fi
}
trap leave_installed_services_stopped EXIT
/bin/launchctl disable "system/$CONTROL_LABEL"
/bin/launchctl disable "system/$WORKER_LABEL"
/bin/launchctl bootout "system/$CONTROL_LABEL" >/dev/null 2>&1 || true
/bin/launchctl bootout "system/$WORKER_LABEL" >/dev/null 2>&1 || true
if /bin/launchctl print "system/$CONTROL_LABEL" >/dev/null 2>&1; then
  /bin/echo "control LaunchDaemon remained loaded after bootout" >&2
  exit 65
fi
if /bin/launchctl print "system/$WORKER_LABEL" >/dev/null 2>&1; then
  /bin/echo "worker LaunchDaemon remained loaded after bootout" >&2
  exit 65
fi

if [ ! -d "$RELEASE_ROOT" ]; then
  STAGING="$(/usr/bin/mktemp -d "$SYSTEM_ROOT/releases/.install.$EXPECTED_SHA.XXXXXX")"
  /usr/bin/git -C "$SOURCE_REPO" archive --format=tar "$EXPECTED_SHA" | /usr/bin/tar -xf - -C "$STAGING"
  /usr/sbin/chown -R root:wheel "$STAGING"
  /bin/chmod -R go-w "$STAGING"
  # mktemp creates the staging root as 0700. Both non-root service UIDs need
  # read/traverse access to the immutable release, while only root may mutate.
  /bin/chmod 0755 "$STAGING"
  /bin/mv "$STAGING" "$RELEASE_ROOT"
  STAGING=""
  "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/ops/executive_os/release_manifest.py" create \
    --root "$RELEASE_ROOT" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA"
  /usr/sbin/chown root:wheel "$RELEASE_ROOT/.executive-release-manifest.json"
else
  "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/ops/executive_os/release_manifest.py" verify \
    --root "$RELEASE_ROOT" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA"
fi
if [ -n "$(/usr/bin/find "$RELEASE_ROOT" -exec /usr/bin/stat -f '%Sp' {} \; \
  | /usr/bin/awk '/\+/{found=1} END {if(found) print "ACL"}')" ]; then
  /bin/echo "installed release contains a filesystem ACL" >&2
  exit 65
fi

INSTALLED_CODEX="$SYSTEM_ROOT/bin/codex-$CODEX_VERSION"
if [ ! -f "$INSTALLED_CODEX" ]; then
  CODEX_TEMP="$(/usr/bin/mktemp "$SYSTEM_ROOT/bin/.codex-$CODEX_VERSION.XXXXXX")"
  /bin/rm -f -- "$CODEX_TEMP"
  /usr/bin/ditto --noqtn "$CODEX_BINARY" "$CODEX_TEMP"
  /usr/sbin/chown root:wheel "$CODEX_TEMP"
  /bin/chmod 0555 "$CODEX_TEMP"
  /bin/mv "$CODEX_TEMP" "$INSTALLED_CODEX"
fi
/usr/bin/codesign --verify --strict "$INSTALLED_CODEX" >/dev/null 2>&1 || {
  /bin/echo "installed Codex signature is invalid" >&2
  exit 65
}
INSTALLED_TEAM="$(/usr/bin/codesign -dv --verbose=4 "$INSTALLED_CODEX" 2>&1 | /usr/bin/awk -F= '$1 == "TeamIdentifier" {print $2}')"
[ "$INSTALLED_TEAM" = "2DC432GLL2" ] || {
  /bin/echo "installed Codex signer team is not OpenAI" >&2
  exit 65
}
INSTALLED_VERSION="$("$INSTALLED_CODEX" --version 2>/dev/null | /usr/bin/awk '$1 == "codex-cli" {print $2}')"
[ "$INSTALLED_VERSION" = "$CODEX_VERSION" ] || {
  /bin/echo "installed Codex version does not match the explicit allowlist" >&2
  exit 65
}
INSTALLED_HASH="$(/usr/bin/shasum -a 256 "$INSTALLED_CODEX" | /usr/bin/awk '{print $1}')"
[ "$INSTALLED_HASH" = "$CODEX_SHA256" ] || {
  /bin/echo "installed Codex bytes do not match the exact reviewed 0.147.0 allowlist" >&2
  exit 65
}
[ "$(/usr/bin/stat -f '%u:%g:%Lp' "$INSTALLED_CODEX")" = "0:0:555" ] || {
  /bin/echo "installed Codex is not root:wheel mode 0555" >&2
  exit 65
}
[ ! -L "$INSTALLED_CODEX" ] && [ "$(/usr/bin/stat -f '%l' "$INSTALLED_CODEX")" -eq 1 ] || {
  /bin/echo "installed Codex must be a direct single-link file" >&2
  exit 65
}
case "$(/usr/bin/stat -f '%Sp' "$INSTALLED_CODEX")" in
  *+) /bin/echo "installed Codex has a filesystem ACL" >&2; exit 65 ;;
esac

ADMIN_CHECKOUT="$RUNTIME_ROOT/control/admin-checkout/$EXPECTED_SHA"
if [ ! -d "$ADMIN_CHECKOUT/.git" ]; then
  /usr/bin/git clone --no-hardlinks --no-checkout "$SOURCE_REPO" "$ADMIN_CHECKOUT"
  /usr/bin/git -C "$ADMIN_CHECKOUT" checkout --detach "$EXPECTED_SHA"
  /usr/bin/git -C "$ADMIN_CHECKOUT" remote remove origin
  /usr/sbin/chown -R "$CONTROL_USER:$CONTROL_GROUP" "$ADMIN_CHECKOUT"
  /bin/chmod -R go-rwx "$ADMIN_CHECKOUT"
fi

(
  cd "$RELEASE_ROOT"
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BINARY" -I -S -B - "$RELEASE_ROOT" "$CONTROL_CONFIG" "$CONTROL_CONFIG_SOURCE" \
    "$CONTROL_RUNTIME_ROOT" "$ADMIN_CHECKOUT" "$WORKSPACE_ROOT" "$EXPECTED_SHA" \
    "$BACKUP_ROOT" "$RECEIPTS_ROOT" "$PROVIDER_HOME" "$RUN_ROOT" \
    "$CANARY_RECEIPT" "$CONTROL_ENV_ATTESTATION" "$CONTROL_UID" "$WORKER_UID" "$WORKER_GID" \
    "$OPERATOR_UID" <<'PY'
import json, os, pathlib, re, sys
release_root = sys.argv.pop(1)
sys.path.insert(0, release_root)
from scripts.executive_os_phase1c import (
    CONTROL_CONFIG_SCHEMA_VERSION,
    _CONFIG_OPTIONAL,
    _CONFIG_REQUIRED,
)

(
    destination,
    source,
    runtime_root,
    source_repository,
    workspace_root,
    expected_sha,
    backup_root,
    receipts_root,
    provider_home,
    run_root,
    canary_receipt,
    control_environment_attestation,
    control_uid,
    worker_uid,
    worker_gid,
    operator_uid,
) = sys.argv[1:]

expected = {
    "schema_version": CONTROL_CONFIG_SCHEMA_VERSION,
    "runtime_root": runtime_root,
    "control_socket_path": "/var/run/mastermind-executive/control.sock",
    "launchd_socket_name": "Operator",
    "worker_broker_socket_path": "/var/run/mastermind-executive/worker.sock",
    "worker_provider_home": provider_home,
    "worker_runs_root": run_root,
    "receipts_root": receipts_root,
    "proof_source_repository": source_repository,
    "proof_workspace_root": workspace_root,
    "proof_base_sha": expected_sha,
    "backup_root": backup_root,
    "control_uid": int(control_uid),
    "worker_uid": int(worker_uid),
    "worker_gid": int(worker_gid),
    "worker_user": "_mastermind_worker",
    "shared_run_gid": int(worker_gid),
    "allowed_peer_uids": sorted({int(control_uid), int(operator_uid)}),
    "secret_canary_receipt_path": canary_receipt,
    "control_environment_attestation_path": control_environment_attestation,
}
defaults = {
    "proof_branch": "codex/phase1c-a-proof",
    "worker_id": "codex-01",
    "worker_account_label": "dedicated-codex-home",
    "quota_class": "codex-native",
    "model": "gpt-5.6-sol",
    "effort": "xhigh",
    "cost_class": "standard",
    "broker_timeout_seconds": 30.0,
    "shutdown_grace_seconds": 10.0,
}
if source:
    source_path = pathlib.Path(source)
    value = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("control config source must contain an object")
else:
    value = {**expected, **defaults}

keys = set(value)
missing = _CONFIG_REQUIRED - keys
unknown = keys - _CONFIG_REQUIRED - _CONFIG_OPTIONAL
if missing or unknown:
    raise SystemExit(
        f"control config schema drift; missing={sorted(missing)}, unknown={sorted(unknown)}"
    )
for key, expected_value in expected.items():
    if value.get(key) != expected_value:
        raise SystemExit(f"control config {key} differs from the reviewed host policy")
blocked = re.compile(
    r"(?i)(password|credential|lease[_-]?token|api[_-]?key|access[_-]?token|secret_value)"
)
for key in value:
    if blocked.search(str(key)):
        raise SystemExit(f"control config contains forbidden secret-bearing key: {key}")

path = pathlib.Path(destination)
temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
temporary.write_text(
    json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
os.chmod(temporary, 0o440)
os.replace(temporary, path)
PY
)
/usr/sbin/chown "root:$CONTROL_GROUP" "$CONTROL_CONFIG"
/bin/chmod 0440 "$CONTROL_CONFIG"

if [ -e "$CONTROL_SENTINEL_FILE" ] || [ -L "$CONTROL_SENTINEL_FILE" ]; then
  [ -f "$CONTROL_SENTINEL_FILE" ] && [ ! -L "$CONTROL_SENTINEL_FILE" ] \
    && [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$CONTROL_SENTINEL_FILE")" = "0:$CONTROL_GID:440" ] || {
      /bin/echo "existing control environment canary file is unsafe" >&2
      exit 65
    }
else
  CONTROL_SENTINEL_TEMP="$(/usr/bin/mktemp "$SYSTEM_ROOT/config/.control-env-canary.XXXXXX")"
  /usr/bin/openssl rand -hex 32 >"$CONTROL_SENTINEL_TEMP"
  /usr/sbin/chown "root:$CONTROL_GROUP" "$CONTROL_SENTINEL_TEMP"
  /bin/chmod 0440 "$CONTROL_SENTINEL_TEMP"
  /bin/mv "$CONTROL_SENTINEL_TEMP" "$CONTROL_SENTINEL_FILE"
fi
/usr/bin/grep -Eq '^[0-9a-f]{64}$' "$CONTROL_SENTINEL_FILE" || {
  /bin/echo "control environment canary file has invalid content" >&2
  exit 65
}

PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BINARY" -I -S -B - "$WORKER_CONFIG" "$CONTROL_UID" "$WORKER_UID" "$WORKER_GID" \
  "$WORKSPACE_ROOT" "$RUN_ROOT" "$PROVIDER_HOME" "$INSTALLED_CODEX" "$CODEX_VERSION" <<'PY'
import json, os, pathlib, sys
(
    destination, control_uid, worker_uid, worker_gid, workspace_root,
    run_root, provider_home, codex_binary, codex_version,
) = sys.argv[1:]
value = {
    "schema_version": "mastermind.executive_worker_broker_config/v1",
    "control_uid": int(control_uid),
    "worker_uid": int(worker_uid),
    "worker_gid": int(worker_gid),
    "worker_user": "_mastermind_worker",
    "worker_id": "codex-01",
    "workspace_root": workspace_root,
    "run_root": run_root,
    "provider_home": provider_home,
    "codex_binary": codex_binary,
    "allowed_codex_versions": [codex_version],
    "required_team_identifier": "2DC432GLL2",
    "launchd_socket_name": "WorkerBroker",
    "uid_sweep_receipt": str(pathlib.Path(provider_home).parent / "state" / "uid-sweep.json"),
    "require_secret_canary": True,
}
path = pathlib.Path(destination)
temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
os.chmod(temporary, 0o440)
os.replace(temporary, path)
PY
/usr/sbin/chown "root:$WORKER_GROUP" "$WORKER_CONFIG"
/bin/chmod 0440 "$WORKER_CONFIG"

CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"
WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"
/usr/bin/install -o root -g wheel -m 0644 "$RELEASE_ROOT/ops/executive_os/$CONTROL_LABEL.plist.template" "$CONTROL_PLIST"
/usr/bin/install -o root -g wheel -m 0644 "$RELEASE_ROOT/ops/executive_os/$WORKER_LABEL.plist.template" "$WORKER_PLIST"

/usr/bin/plutil -replace ProgramArguments.0 -string "$PYTHON_BINARY" "$CONTROL_PLIST"
/usr/bin/plutil -replace ProgramArguments.4 -string "$RELEASE_ROOT/scripts/executive_os_phase1c_control_wrapper.py" "$CONTROL_PLIST"
/usr/bin/plutil -replace ProgramArguments.6 -string "$CONTROL_CONFIG" "$CONTROL_PLIST"
/usr/bin/plutil -replace ProgramArguments.8 -string "$CONTROL_SENTINEL_FILE" "$CONTROL_PLIST"
/usr/bin/plutil -replace ProgramArguments.10 -string "$CONTROL_ENV_ATTESTATION" "$CONTROL_PLIST"
/usr/bin/plutil -replace ProgramArguments.12 -string "$RELEASE_ROOT" "$CONTROL_PLIST"
/usr/bin/plutil -replace WorkingDirectory -string "$RELEASE_ROOT" "$CONTROL_PLIST"
/usr/bin/plutil -replace UserName -string "$CONTROL_USER" "$CONTROL_PLIST"
/usr/bin/plutil -replace GroupName -string "$CONTROL_GROUP" "$CONTROL_PLIST"
/usr/bin/plutil -replace EnvironmentVariables.HOME -string "$CONTROL_HOME" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.Operator.SockPathName -string /var/run/mastermind-executive/control.sock "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.Operator.SockPathOwner -integer "$CONTROL_UID" "$CONTROL_PLIST"
/usr/bin/plutil -replace Sockets.Operator.SockPathGroup -integer "$OPS_GID" "$CONTROL_PLIST"
/usr/bin/plutil -replace StandardOutPath -string /var/log/mastermind-executive/control/stdout.log "$CONTROL_PLIST"
/usr/bin/plutil -replace StandardErrorPath -string /var/log/mastermind-executive/control/stderr.log "$CONTROL_PLIST"
/usr/sbin/chown root:wheel "$CONTROL_PLIST"
/bin/chmod 0644 "$CONTROL_PLIST"

/usr/bin/plutil -replace ProgramArguments.0 -string "$PYTHON_BINARY" "$WORKER_PLIST"
/usr/bin/plutil -replace ProgramArguments.4 -string "$RELEASE_ROOT/scripts/executive_os_phase1c_worker.py" "$WORKER_PLIST"
/usr/bin/plutil -replace ProgramArguments.7 -string "$WORKER_CONFIG" "$WORKER_PLIST"
/usr/bin/plutil -replace WorkingDirectory -string "$RELEASE_ROOT" "$WORKER_PLIST"
/usr/bin/plutil -replace UserName -string "$WORKER_USER" "$WORKER_PLIST"
/usr/bin/plutil -replace GroupName -string "$WORKER_GROUP" "$WORKER_PLIST"
/usr/bin/plutil -replace EnvironmentVariables.HOME -string "$PROVIDER_HOME" "$WORKER_PLIST"
/usr/bin/plutil -replace Sockets.WorkerBroker.SockPathName -string /var/run/mastermind-executive/worker.sock "$WORKER_PLIST"
# The controller owns the connect-only path. launchd passes the already-open
# listener FD to the worker daemon, so the worker needs no socket-path access.
/usr/bin/plutil -replace Sockets.WorkerBroker.SockPathOwner -integer "$CONTROL_UID" "$WORKER_PLIST"
/usr/bin/plutil -replace Sockets.WorkerBroker.SockPathGroup -integer "$CONTROL_GID" "$WORKER_PLIST"
/usr/bin/plutil -replace Sockets.WorkerBroker.SockPathMode -integer 384 "$WORKER_PLIST"
/usr/bin/plutil -replace StandardOutPath -string /var/log/mastermind-executive/worker/stdout.log "$WORKER_PLIST"
/usr/bin/plutil -replace StandardErrorPath -string /var/log/mastermind-executive/worker/stderr.log "$WORKER_PLIST"

for installed_policy_file in "$CONTROL_CONFIG" "$WORKER_CONFIG" "$CONTROL_SENTINEL_FILE" "$CONTROL_PLIST" "$WORKER_PLIST"; do
  case "$(/usr/bin/stat -f '%Sp' "$installed_policy_file")" in
    *+) /bin/echo "installed policy file has a filesystem ACL: $installed_policy_file" >&2; exit 65 ;;
  esac
done

/usr/bin/plutil -lint "$CONTROL_PLIST" "$WORKER_PLIST"
(
  cd "$RELEASE_ROOT"
  /usr/bin/sudo -u "$WORKER_USER" /usr/bin/env -i \
    HOME="$PROVIDER_HOME" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/scripts/executive_os_phase1c_worker.py" check-config --config "$WORKER_CONFIG"
  /usr/bin/sudo -u "$CONTROL_USER" /usr/bin/env -i \
    HOME="$CONTROL_HOME" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BINARY" -I -S -B -c \
      'import sys; sys.path.insert(0,sys.argv[1]); from scripts.executive_os_phase1c import load_control_config; load_control_config(sys.argv[2])' \
      "$RELEASE_ROOT" "$CONTROL_CONFIG"
)

"$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/ops/executive_os/release_manifest.py" verify \
  --root "$RELEASE_ROOT" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA"

/bin/echo "installed exact Executive OS release $EXPECTED_SHA"
/bin/echo "services remain stopped until the secret canary has a passing receipt"
/bin/echo "next: sudo /bin/bash '$RELEASE_ROOT/ops/executive_os/acceptance.sh' --source-repo '$SOURCE_REPO' --expected-sha '$EXPECTED_SHA' --operator-user '$OPERATOR_USER'"
