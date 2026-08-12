#!/bin/bash
# Provision the exact PSF-signed Python 3.12 framework used by Executive OS.
# The PSF macOS executable loads its framework from an absolute /Library path,
# so this helper installs that exact signed framework version in place, archives
# any prior 3.12 tree without deletion, and proves all live module origins.
set -euo pipefail
umask 077

PYTHON_VERSION="3.12.10"
PYTHON_SERIES="3.12"
PYTHON_TEAM_ID="BMM5U3QVKW"
PYTHON_PACKAGE_URL="https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg"
PYTHON_PACKAGE_SHA256="8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4"
PYTHON_INSTALLER_CERT_SHA256="C1A8FB2B4668D1BA221BC2A84DE43EDAA715C8FB85E320F478861ACECE5B8588"
PYTHON_BINARY_SHA256="d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"
PYTHON_FRAMEWORK_SHA256="14e61fb22a897d238248dfd8fe3b472b4541338c293368b4747803055b8bb3aa"
FRAMEWORK_PARENT="/Library/Frameworks/Python.framework"
VERSIONS_ROOT="$FRAMEWORK_PARENT/Versions"
RUNTIME_ROOT="$VERSIONS_ROOT/$PYTHON_SERIES"
PYTHON_BINARY="$RUNTIME_ROOT/bin/python3.12"
SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
ARCHIVE_ROOT="$SYSTEM_ROOT/python-archive"
RECEIPT_PATH="$SYSTEM_ROOT/python-runtime.json"
PACKAGE_PATH=""
VERIFY_ONLY="false"
WORK_ROOT=""
INSTALL_STAGE=""
PRIOR_ARCHIVE=""
PRIOR_RECEIPT_ARCHIVE=""
RECEIPT_TEMP=""
MUTATION_STARTED="false"
PRIOR_MOVED="false"
PRIOR_RECEIPT_MOVED="false"
CANDIDATE_INSTALLED="false"
NEW_RECEIPT_INSTALLED="false"
INSTALL_COMPLETE="false"

usage() {
  /bin/echo "usage: sudo /bin/bash $0 [--package /absolute/python.pkg] [--verify-only]" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --package) PACKAGE_PATH="${2:-}"; shift 2 ;;
    --verify-only) VERIFY_ONLY="true"; shift ;;
    *) usage ;;
  esac
done

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "provision-python-runtime.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "provision-python-runtime.sh supports macOS only" >&2
  exit 69
}
if [ -n "$PACKAGE_PATH" ]; then
  case "$PACKAGE_PATH" in /*) ;; *) /bin/echo "package path must be absolute" >&2; exit 65 ;; esac
  [ -f "$PACKAGE_PATH" ] && [ ! -L "$PACKAGE_PATH" ] || {
    /bin/echo "package must be a regular non-symlink file" >&2
    exit 65
  }
fi

runtime_tree_static_checks() {
  local root="$1"
  local binary="$root/bin/python3.12"
  local link target mach_o team
  [ -d "$root" ] && [ ! -L "$root" ] || return 1
  [ -f "$binary" ] && [ -x "$binary" ] && [ ! -L "$binary" ] || return 1
  [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$binary")" = "0:0:755:1" ] || return 1
  [ "$(/usr/bin/shasum -a 256 "$binary" | /usr/bin/awk '{print $1}')" = "$PYTHON_BINARY_SHA256" ] || return 1
  [ "$(/usr/bin/shasum -a 256 "$root/Python" | /usr/bin/awk '{print $1}')" = "$PYTHON_FRAMEWORK_SHA256" ] || return 1
  /usr/bin/file -b "$binary" | /usr/bin/grep -q '^Mach-O ' || return 1
  [ -z "$(/usr/bin/find "$root" ! -user root -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" ! -group wheel -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" -perm +022 -print -quit)" ] || return 1
  if [ -n "$(/usr/bin/find "$root" -exec /usr/bin/stat -f '%Sp' {} \; \
    | /usr/bin/awk '/\+/{found=1} END {if(found) print "ACL"}')" ]; then
    return 1
  fi
  while IFS= read -r -d '' link; do
    target="$(/usr/bin/readlink -f "$link")" || return 1
    case "$target" in "$root"|"$root"/*) ;; *) return 1 ;; esac
  done < <(/usr/bin/find "$root" -type l -print0)
  /usr/bin/codesign --verify --deep --strict "$root" >/dev/null 2>&1 || return 1
  while IFS= read -r -d '' mach_o; do
    if /usr/bin/file -b "$mach_o" | /usr/bin/grep -q '^Mach-O'; then
      /usr/bin/codesign --verify --strict "$mach_o" >/dev/null 2>&1 || return 1
      team="$(/usr/bin/codesign -dv --verbose=4 "$mach_o" 2>&1 \
        | /usr/bin/awk -F= '$1 == "TeamIdentifier" {print $2}')"
      [ "$team" = "$PYTHON_TEAM_ID" ] || return 1
    fi
  done < <(/usr/bin/find "$root" -type f -print0)
}

runtime_ancestor_checks() {
  local ancestor
  for ancestor in /Library /Library/Frameworks "$FRAMEWORK_PARENT" "$VERSIONS_ROOT"; do
    [ -d "$ancestor" ] && [ ! -L "$ancestor" ] || return 1
    [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$ancestor")" = "0:0:755" ] || return 1
    case "$(/usr/bin/stat -f '%Sp' "$ancestor")" in *+) return 1 ;; esac
  done
}

runtime_live_checks() {
  local root="$1"
  local binary="$root/bin/python3.12"
  "$binary" -I -S -B - "$root" "$binary" "$PYTHON_VERSION" <<'PY'
import _ctypes
import _sqlite3
import _ssl
import asyncio
import ctypes
import hashlib
import json
import pathlib
import plistlib
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
expected_version = sys.argv[3]


def require_inside(raw: str, label: str) -> pathlib.Path:
    observed = pathlib.Path(raw).resolve(strict=True)
    if observed != root and root not in observed.parents:
        raise RuntimeError(f"{label} escapes the pinned runtime root")
    return observed


if sys.version.split()[0] != expected_version:
    raise RuntimeError("live Python version differs from the package allowlist")
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
}

verify_installed_runtime_bytes() {
  runtime_ancestor_checks || return 1
  runtime_tree_static_checks "$RUNTIME_ROOT" || return 1
  runtime_live_checks "$RUNTIME_ROOT" || return 1
}

verify_runtime_receipt() {
  [ -f "$RECEIPT_PATH" ] && [ ! -L "$RECEIPT_PATH" ] || return 1
  [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$RECEIPT_PATH")" = "0:0:400:1" ] || return 1
  case "$(/usr/bin/stat -f '%Sp' "$RECEIPT_PATH")" in *+) return 1 ;; esac
  "$PYTHON_BINARY" -I -S -B - "$RECEIPT_PATH" "$RUNTIME_ROOT" "$PYTHON_BINARY" \
    "$PYTHON_VERSION" "$PYTHON_TEAM_ID" "$PYTHON_PACKAGE_SHA256" \
    "$PYTHON_BINARY_SHA256" "$PYTHON_FRAMEWORK_SHA256" "$ARCHIVE_ROOT" <<'PY'
import hashlib
import json
import pathlib
import sys

(
    receipt_path, runtime_root, python_binary, version, team, package_sha,
    binary_sha, framework_sha, archive_root,
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
if prior and not prior.startswith(archive_root + "/prior-3.12-"):
    raise RuntimeError("Python runtime receipt prior archive escapes its fixed root")
prior_receipt = receipt.get("prior_runtime_receipt_archive")
if not isinstance(prior_receipt, str):
    raise RuntimeError("Python runtime prior receipt archive must be a string")
if prior_receipt and not prior_receipt.startswith(archive_root + "/prior-receipt-3.12-"):
    raise RuntimeError("Python runtime prior receipt archive escapes its fixed root")
for path, expected_sha in (
    (pathlib.Path(python_binary), binary_sha),
    (pathlib.Path(runtime_root) / "Python", framework_sha),
):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise RuntimeError("Python runtime receipt hash differs from installed bytes")
PY
}

verify_installed_runtime() {
  verify_installed_runtime_bytes || return 1
  verify_runtime_receipt || return 1
}

ensure_root_directory() {
  local path="$1"
  local mode="$2"
  if [ -e "$path" ] || [ -L "$path" ]; then
    [ -d "$path" ] && [ ! -L "$path" ] || {
      /bin/echo "required directory is symlinked or has the wrong type: $path" >&2
      return 1
    }
    [ "$(/usr/bin/stat -f '%u' "$path")" = "0" ] || {
      /bin/echo "required directory is not root-owned: $path" >&2
      return 1
    }
  else
    /usr/bin/install -d -o root -g wheel -m "$mode" "$path"
  fi
  /bin/chmod -N "$path"
  /usr/sbin/chown root:wheel "$path"
  /bin/chmod "$mode" "$path"
}

assert_runtime_not_in_use() {
  local active_path observed_pids active_python_pids=""
  for active_path in "$RUNTIME_ROOT/Python" "$PYTHON_BINARY"; do
    if [ -e "$active_path" ] && [ ! -L "$active_path" ]; then
      observed_pids="$(/usr/sbin/lsof -t "$active_path" 2>/dev/null || true)"
      if [ -n "$observed_pids" ]; then
        active_python_pids="${active_python_pids}${active_python_pids:+ }$(/bin/echo "$observed_pids" | /usr/bin/tr '\n' ' ')"
      fi
    fi
  done
  [ -z "$active_python_pids" ] || {
    /bin/echo "Python 3.12 is in use; close Python-based apps and retry (PIDs: $active_python_pids)" >&2
    return 75
  }
}

archive_partial_and_restore_prior() {
  local failed_path
  [ "$MUTATION_STARTED" = "true" ] || return 0
  /usr/bin/install -d -o root -g wheel -m 0700 "$ARCHIVE_ROOT" || true
  if [ "$NEW_RECEIPT_INSTALLED" = "true" ] \
    && { [ -e "$RECEIPT_PATH" ] || [ -L "$RECEIPT_PATH" ]; }; then
    failed_path="$ARCHIVE_ROOT/failed-receipt-$PYTHON_SERIES-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen).json"
    /bin/mv "$RECEIPT_PATH" "$failed_path" 2>/dev/null || true
  fi
  if [ "$CANDIDATE_INSTALLED" = "true" ] \
    && { [ -e "$RUNTIME_ROOT" ] || [ -L "$RUNTIME_ROOT" ]; }; then
    failed_path="$ARCHIVE_ROOT/failed-$PYTHON_SERIES-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen)"
    /bin/mv "$RUNTIME_ROOT" "$failed_path" 2>/dev/null || true
  fi
  if [ -n "$INSTALL_STAGE" ] && { [ -e "$INSTALL_STAGE" ] || [ -L "$INSTALL_STAGE" ]; }; then
    failed_path="$ARCHIVE_ROOT/failed-stage-$PYTHON_SERIES-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen)"
    /bin/mv "$INSTALL_STAGE" "$failed_path" 2>/dev/null || true
  fi
  if [ "$PRIOR_MOVED" = "true" ] && [ -n "$PRIOR_ARCHIVE" ] \
    && [ -d "$PRIOR_ARCHIVE" ] && [ ! -e "$RUNTIME_ROOT" ]; then
    /bin/mv "$PRIOR_ARCHIVE" "$RUNTIME_ROOT" 2>/dev/null || true
  fi
  if [ "$PRIOR_RECEIPT_MOVED" = "true" ] && [ -n "$PRIOR_RECEIPT_ARCHIVE" ] \
    && [ -f "$PRIOR_RECEIPT_ARCHIVE" ] && [ ! -e "$RECEIPT_PATH" ]; then
    /bin/mv "$PRIOR_RECEIPT_ARCHIVE" "$RECEIPT_PATH" 2>/dev/null || true
  fi
  if [ -n "$RECEIPT_TEMP" ] && [ -f "$RECEIPT_TEMP" ]; then
    /bin/rm -f -- "$RECEIPT_TEMP"
  fi
}

cleanup() {
  local status="$?"
  if [ "$status" -ne 0 ] && [ "$INSTALL_COMPLETE" != "true" ]; then
    archive_partial_and_restore_prior
  fi
  if [ -n "$WORK_ROOT" ] && [ -d "$WORK_ROOT" ]; then
    /bin/rm -rf -- "$WORK_ROOT"
  fi
  exit "$status"
}
trap cleanup EXIT
interrupted() {
  local signum="$1"
  trap - HUP INT TERM
  /bin/echo "Python runtime provisioning interrupted by signal $signum" >&2
  exit $((128 + signum))
}
trap 'interrupted 1' HUP
trap 'interrupted 2' INT
trap 'interrupted 15' TERM

if [ "$VERIFY_ONLY" = "true" ]; then
  verify_installed_runtime || {
    /bin/echo "installed Executive Python runtime verification failed" >&2
    exit 65
  }
  /bin/echo "Executive Python runtime verification passed"
  /bin/echo "PYTHON_RUNTIME_ROOT='$RUNTIME_ROOT'"
  /bin/echo "PYTHON_BINARY='$PYTHON_BINARY'"
  /bin/echo "PYTHON_TEAM_IDENTIFIER='$PYTHON_TEAM_ID'"
  exit 0
fi

# Reuse only an already complete trusted runtime. Never execute a failed static
# candidate while root; a polluted or mutable tree proceeds directly to archive.
if verify_installed_runtime >/dev/null 2>&1; then
  /bin/echo "Executive Python runtime already exists and verification passed"
  /bin/echo "PYTHON_RUNTIME_ROOT='$RUNTIME_ROOT'"
  /bin/echo "PYTHON_BINARY='$PYTHON_BINARY'"
  /bin/echo "PYTHON_TEAM_IDENTIFIER='$PYTHON_TEAM_ID'"
  exit 0
fi

WORK_ROOT="$(/usr/bin/mktemp -d /private/tmp/mastermind-python-runtime.XXXXXX)"
/bin/chmod 0700 "$WORK_ROOT"
if [ -n "$PACKAGE_PATH" ]; then
  PACKAGE_SOURCE="$PACKAGE_PATH"
  PACKAGE_PATH="$WORK_ROOT/python-$PYTHON_VERSION.pkg"
  /usr/bin/ditto --noqtn "$PACKAGE_SOURCE" "$PACKAGE_PATH"
  /usr/sbin/chown root:wheel "$PACKAGE_PATH"
  /bin/chmod 0400 "$PACKAGE_PATH"
else
  PACKAGE_PATH="$WORK_ROOT/python-$PYTHON_VERSION.pkg"
  /usr/bin/curl --fail --location --proto '=https' --tlsv1.2 \
    --output "$PACKAGE_PATH" "$PYTHON_PACKAGE_URL"
fi

OBSERVED_PACKAGE_SHA256="$(/usr/bin/shasum -a 256 "$PACKAGE_PATH" | /usr/bin/awk '{print $1}')"
[ "$OBSERVED_PACKAGE_SHA256" = "$PYTHON_PACKAGE_SHA256" ] || {
  /bin/echo "Python package SHA-256 differs from the explicit allowlist" >&2
  exit 65
}
PACKAGE_SIGNATURE="$(/usr/sbin/pkgutil --check-signature "$PACKAGE_PATH")" || {
  /bin/echo "Python package signature validation failed" >&2
  exit 65
}
/bin/echo "$PACKAGE_SIGNATURE" | /usr/bin/grep -Fq \
  "Developer ID Installer: Python Software Foundation ($PYTHON_TEAM_ID)" || {
    /bin/echo "Python package signer differs from the explicit allowlist" >&2
    exit 65
  }
/bin/echo "$PACKAGE_SIGNATURE" | /usr/bin/grep -Fq \
  "Notarization: trusted by the Apple notary service" || {
    /bin/echo "Python package is not trusted by the Apple notary service" >&2
    exit 65
  }
NORMALIZED_SIGNATURE="$(/bin/echo "$PACKAGE_SIGNATURE" | /usr/bin/tr -d '[:space:]')"
/bin/echo "$NORMALIZED_SIGNATURE" | /usr/bin/grep -Fq "$PYTHON_INSTALLER_CERT_SHA256" || {
  /bin/echo "Python package certificate fingerprint differs from the allowlist" >&2
  exit 65
}
/usr/sbin/spctl -a -t install -vv "$PACKAGE_PATH" >/dev/null 2>&1 || {
  /bin/echo "Gatekeeper rejected the Python package" >&2
  exit 65
}

EXPANDED="$WORK_ROOT/expanded"
/usr/sbin/pkgutil --expand-full "$PACKAGE_PATH" "$EXPANDED"
CANDIDATE="$EXPANDED/Python_Framework.pkg/Payload/Versions/$PYTHON_SERIES"
[ -d "$CANDIDATE" ] && [ ! -L "$CANDIDATE" ] || {
  /bin/echo "Python package has no direct $PYTHON_SERIES framework payload" >&2
  exit 65
}

# Ownership and modes are filesystem metadata, not signed bytes. Harden the
# extracted candidate before trusting or installing it, then re-check signing.
/bin/chmod -RN "$CANDIDATE"
/usr/sbin/chown -R root:wheel "$CANDIDATE"
/bin/chmod -R go-w "$CANDIDATE"
/bin/chmod 0755 "$CANDIDATE" "$CANDIDATE/bin" "$CANDIDATE/bin/python3.12"
runtime_tree_static_checks "$CANDIDATE" || {
  /bin/echo "extracted Python framework failed static trust checks" >&2
  exit 65
}

# Cross the mutation boundary only after download, package signing, notarization,
# pinned digest, payload signing, ownership, modes, ACL, and symlink checks pass.
if [ -e "$RUNTIME_ROOT" ] || [ -L "$RUNTIME_ROOT" ]; then
  [ -d "$RUNTIME_ROOT" ] && [ ! -L "$RUNTIME_ROOT" ] || {
    /bin/echo "existing Python 3.12 runtime is not a direct directory" >&2
    exit 65
  }
fi
assert_runtime_not_in_use
ensure_root_directory "$SYSTEM_ROOT" 0755
ensure_root_directory "$ARCHIVE_ROOT" 0700
ensure_root_directory /Library/Frameworks 0755
ensure_root_directory "$FRAMEWORK_PARENT" 0755
ensure_root_directory "$VERSIONS_ROOT" 0755
MUTATION_STARTED="true"

INSTALL_STAGE="$VERSIONS_ROOT/.executive-$PYTHON_SERIES-$(/usr/bin/uuidgen)"
/usr/bin/ditto --noqtn "$CANDIDATE" "$INSTALL_STAGE"
/bin/chmod -RN "$INSTALL_STAGE"
/usr/sbin/chown -R root:wheel "$INSTALL_STAGE"
/bin/chmod -R go-w "$INSTALL_STAGE"
/bin/chmod 0755 "$INSTALL_STAGE" "$INSTALL_STAGE/bin" "$INSTALL_STAGE/bin/python3.12"
runtime_tree_static_checks "$INSTALL_STAGE" || {
  /bin/echo "staged Python framework failed post-copy trust checks" >&2
  exit 65
}

# A process can start while the replacement is staged, so repeat the same
# fail-closed census immediately before the two same-filesystem renames.
assert_runtime_not_in_use

if [ -e "$RUNTIME_ROOT" ] || [ -L "$RUNTIME_ROOT" ]; then
  PRIOR_ARCHIVE="$ARCHIVE_ROOT/prior-$PYTHON_SERIES-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen)"
fi
if [ -n "$PRIOR_ARCHIVE" ]; then
  PRIOR_MOVED="true"
  /bin/mv "$RUNTIME_ROOT" "$PRIOR_ARCHIVE"
fi
if [ -e "$RECEIPT_PATH" ] || [ -L "$RECEIPT_PATH" ]; then
  [ -f "$RECEIPT_PATH" ] && [ ! -L "$RECEIPT_PATH" ] || {
    /bin/echo "existing Python runtime receipt is not a direct regular file" >&2
    exit 65
  }
  PRIOR_RECEIPT_ARCHIVE="$ARCHIVE_ROOT/prior-receipt-$PYTHON_SERIES-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen).json"
  PRIOR_RECEIPT_MOVED="true"
  /bin/mv "$RECEIPT_PATH" "$PRIOR_RECEIPT_ARCHIVE"
fi
CANDIDATE_INSTALLED="true"
/bin/mv "$INSTALL_STAGE" "$RUNTIME_ROOT"
INSTALL_STAGE=""

verify_installed_runtime_bytes || {
  /bin/echo "installed Python framework failed live origin attestation" >&2
  exit 65
}

RECEIPT_TEMP="$(/usr/bin/mktemp "$SYSTEM_ROOT/.python-runtime.XXXXXX")"
/bin/cat >"$RECEIPT_TEMP" <<EOF
{"schema_version":"mastermind.executive_python_runtime/v1","python_version":"$PYTHON_VERSION","runtime_root":"$RUNTIME_ROOT","python_binary":"$PYTHON_BINARY","team_identifier":"$PYTHON_TEAM_ID","package_sha256":"$PYTHON_PACKAGE_SHA256","python_binary_sha256":"$PYTHON_BINARY_SHA256","python_framework_sha256":"$PYTHON_FRAMEWORK_SHA256","prior_runtime_archive":"$PRIOR_ARCHIVE","prior_runtime_receipt_archive":"$PRIOR_RECEIPT_ARCHIVE"}
EOF
/usr/sbin/chown root:wheel "$RECEIPT_TEMP"
/bin/chmod 0400 "$RECEIPT_TEMP"
NEW_RECEIPT_INSTALLED="true"
/bin/mv "$RECEIPT_TEMP" "$RECEIPT_PATH"
RECEIPT_TEMP=""
verify_runtime_receipt || {
  /bin/echo "installed Python runtime receipt verification failed" >&2
  exit 65
}
INSTALL_COMPLETE="true"

/bin/echo "Executive Python $PYTHON_VERSION provisioned and verified"
/bin/echo "PYTHON_RUNTIME_ROOT='$RUNTIME_ROOT'"
/bin/echo "PYTHON_BINARY='$PYTHON_BINARY'"
/bin/echo "PYTHON_TEAM_IDENTIFIER='$PYTHON_TEAM_ID'"
if [ -n "$PRIOR_ARCHIVE" ]; then
  /bin/echo "prior Python 3.12 runtime archived at: $PRIOR_ARCHIVE"
fi
