#!/bin/bash
# Provision the dedicated Executive OS Codex login by running the reviewed
# native Codex binary as the worker principal. This script never reads, copies,
# serializes, repairs, or prints credential contents.
set -euo pipefail
umask 077

WORKER_USER="_mastermind_worker"
WORKER_GROUP="_mastermind_worker"
WORKER_UID="451"
WORKER_GID="451"
PROVIDER_HOME="/var/db/mastermind-executive/workers/codex-01/provider-home"
CODEX_BINARY="/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex"
CODEX_VERSION="0.147.0"
CODEX_TEAM_ID="2DC432GLL2"
CODEX_SHA256="19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"
SYSTEM_BIN="/Library/Application Support/MastermindExecutive/bin"
VERIFY_ONLY="false"
PINNED_CODEX_BINARY=""

cleanup() {
  if [ -n "$PINNED_CODEX_BINARY" ] && [ -f "$PINNED_CODEX_BINARY" ]; then
    /bin/rm -f -- "$PINNED_CODEX_BINARY"
  fi
}
trap cleanup EXIT

usage() {
  /bin/echo "usage: sudo /bin/bash $0 [--verify-only] [--codex-binary PATH] [--codex-version VERSION] [--worker-uid N] [--provider-home PATH]" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --verify-only) VERIFY_ONLY="true"; shift ;;
    --codex-binary) CODEX_BINARY="${2:-}"; shift 2 ;;
    --codex-version) CODEX_VERSION="${2:-}"; shift 2 ;;
    --worker-uid) WORKER_UID="${2:-}"; WORKER_GID="${2:-}"; shift 2 ;;
    --provider-home) PROVIDER_HOME="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "provision-worker-auth.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "provision-worker-auth.sh supports macOS only" >&2
  exit 69
}
case "$WORKER_UID" in
  ''|*[!0-9]*) /bin/echo "worker UID must be a decimal integer" >&2; exit 65 ;;
esac
[ "$WORKER_UID" -ge 400 ] && [ "$WORKER_UID" -lt 500 ] || {
  /bin/echo "worker UID/GID must be in the reviewed 400-499 range" >&2
  exit 65
}
case "$CODEX_VERSION" in
  ''|*[!0-9A-Za-z._-]*) /bin/echo "Codex version is invalid" >&2; exit 65 ;;
esac
for absolute_path in "$PROVIDER_HOME" "$CODEX_BINARY"; do
  case "$absolute_path" in
    /*) ;;
    *) /bin/echo "worker-auth paths must be absolute: $absolute_path" >&2; exit 65 ;;
  esac
done

read_dscl_attribute() {
  /usr/bin/dscl . -read "$1" "$2" 2>/dev/null \
    | /usr/bin/awk '
        NR == 1 {sub(/^[^:]*:[[:space:]]*/, ""); value=$0; next}
        {value=value " " $0}
        END {gsub(/^[[:space:]]+|[[:space:]]+$/, "", value); print value}
      '
}

run_codex_as_worker() {
  /usr/bin/sudo -n -u "$WORKER_USER" -g "$WORKER_GROUP" \
    /usr/bin/env -i \
      HOME="$PROVIDER_HOME" \
      CODEX_HOME="$PROVIDER_HOME" \
      LANG="C.UTF-8" \
      LC_ALL="C.UTF-8" \
      NO_COLOR="1" \
      PATH="/usr/bin:/bin" \
      "$PINNED_CODEX_BINARY" "$@"
}

/usr/bin/id "$WORKER_USER" >/dev/null 2>&1 || {
  /bin/echo "missing worker account; run bootstrap-host.sh first" >&2
  exit 65
}
[ "$(/usr/bin/id -u "$WORKER_USER")" = "$WORKER_UID" ] \
  && [ "$(/usr/bin/id -g "$WORKER_USER")" = "$WORKER_GID" ] || {
    /bin/echo "worker UID/GID does not match the provisioning arguments" >&2
    exit 65
  }
[ "$(read_dscl_attribute "/Users/$WORKER_USER" PrimaryGroupID)" = "$WORKER_GID" ] \
  && [ "$(read_dscl_attribute "/Users/$WORKER_USER" NFSHomeDirectory)" = "$PROVIDER_HOME" ] \
  && [ "$(read_dscl_attribute "/Users/$WORKER_USER" UserShell)" = "/usr/bin/false" ] \
  && [ "$(read_dscl_attribute "/Users/$WORKER_USER" Password)" = "*" ] \
  && [ "$(read_dscl_attribute "/Users/$WORKER_USER" AuthenticationAuthority)" = ";DisabledUser;" ] || {
    /bin/echo "worker account does not match the bootstrapped disabled-account policy" >&2
    exit 65
  }

[ -d "$PROVIDER_HOME" ] && [ ! -L "$PROVIDER_HOME" ] || {
  /bin/echo "worker provider home must be a real directory: $PROVIDER_HOME" >&2
  exit 65
}
[ "$(/usr/bin/stat -f '%u:%g:%Lp' "$PROVIDER_HOME")" = "$WORKER_UID:$WORKER_GID:700" ] || {
  /bin/echo "worker provider home must be worker-owned mode 0700" >&2
  exit 65
}
case "$(/usr/bin/stat -f '%Sp' "$PROVIDER_HOME")" in
  *+) /bin/echo "worker provider home has an unexpected filesystem ACL" >&2; exit 65 ;;
esac
[ -d "$SYSTEM_BIN" ] && [ ! -L "$SYSTEM_BIN" ] \
  && [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$SYSTEM_BIN")" = "0:0:755" ] || {
    /bin/echo "Executive system bin must be a root:wheel mode 0755 directory" >&2
    exit 65
  }
case "$(/usr/bin/stat -f '%Sp' "$SYSTEM_BIN")" in
  *+) /bin/echo "Executive system bin has an unexpected filesystem ACL" >&2; exit 65 ;;
esac

[ -f "$CODEX_BINARY" ] && [ -x "$CODEX_BINARY" ] && [ ! -L "$CODEX_BINARY" ] || {
  /bin/echo "Codex binary must be a direct executable regular file" >&2
  exit 65
}
[ "$(/usr/bin/stat -f '%l' "$CODEX_BINARY")" -eq 1 ] || {
  /bin/echo "Codex binary must have exactly one hard link" >&2
  exit 65
}

# Never execute the Homebrew/user-owned source while this script is root. Copy
# it first to a root-owned, non-writable temporary path, then attest and execute
# only that pinned copy. A raced or partial copy cannot pass strict codesign.
PINNED_CODEX_BINARY="$(/usr/bin/mktemp "$SYSTEM_BIN/.codex-auth-$CODEX_VERSION.XXXXXX")"
/bin/rm -f -- "$PINNED_CODEX_BINARY"
/usr/bin/ditto --noqtn "$CODEX_BINARY" "$PINNED_CODEX_BINARY"
/usr/sbin/chown root:wheel "$PINNED_CODEX_BINARY"
/bin/chmod 0555 "$PINNED_CODEX_BINARY"
[ -f "$PINNED_CODEX_BINARY" ] && [ ! -L "$PINNED_CODEX_BINARY" ] \
  && [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$PINNED_CODEX_BINARY")" = "0:0:555:1" ] || {
    /bin/echo "staged Codex binary is not an immutable root-owned regular file" >&2
    exit 65
  }
case "$(/usr/bin/stat -f '%Sp' "$PINNED_CODEX_BINARY")" in
  *+) /bin/echo "staged Codex binary has an unexpected filesystem ACL" >&2; exit 65 ;;
esac
/usr/bin/file -b "$PINNED_CODEX_BINARY" | /usr/bin/grep -q '^Mach-O ' || {
  /bin/echo "Codex binary must be the native macOS executable, not a script or shim" >&2
  exit 65
}
/usr/bin/codesign --verify --strict "$PINNED_CODEX_BINARY" >/dev/null 2>&1 || {
  /bin/echo "Codex binary signature is invalid" >&2
  exit 65
}
OBSERVED_SHA256="$(/usr/bin/shasum -a 256 "$PINNED_CODEX_BINARY" | /usr/bin/awk '{print $1}')"
[ "$OBSERVED_SHA256" = "$CODEX_SHA256" ] || {
  /bin/echo "Codex binary bytes do not match the exact reviewed 0.147.0 allowlist" >&2
  exit 65
}
OBSERVED_TEAM="$(/usr/bin/codesign -dv --verbose=4 "$PINNED_CODEX_BINARY" 2>&1 | /usr/bin/awk -F= '$1 == "TeamIdentifier" {print $2}')"
[ "$OBSERVED_TEAM" = "$CODEX_TEAM_ID" ] || {
  /bin/echo "Codex binary signer is not OpenAI" >&2
  exit 65
}
OBSERVED_VERSION="$(run_codex_as_worker --version 2>/dev/null | /usr/bin/awk '$1 == "codex-cli" {print $2}')"
[ "$OBSERVED_VERSION" = "$CODEX_VERSION" ] || {
  /bin/echo "Codex binary version does not match the explicit allowlist" >&2
  exit 65
}

AUTH_PATH="$PROVIDER_HOME/auth.json"

verify_auth_metadata() {
  [ -f "$AUTH_PATH" ] && [ ! -L "$AUTH_PATH" ] || {
    /bin/echo "dedicated worker auth is missing or is not a regular non-symlink file" >&2
    exit 65
  }
  [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$AUTH_PATH")" = "$WORKER_UID:$WORKER_GID:600:1" ] || {
    /bin/echo "dedicated worker auth must be worker-owned, mode 0600, with one hard link" >&2
    exit 65
  }
  [ "$(/usr/bin/stat -f '%z' "$AUTH_PATH")" -gt 0 ] || {
    /bin/echo "dedicated worker auth file is empty" >&2
    exit 65
  }
  case "$(/usr/bin/stat -f '%Sp' "$AUTH_PATH")" in
    *+) /bin/echo "dedicated worker auth has an unexpected filesystem ACL" >&2; exit 65 ;;
  esac
}

verify_login_without_output() {
  # Codex itself validates the credential. Both streams are discarded so an
  # account identifier, token detail, or provider response cannot enter logs.
  run_codex_as_worker login status -c 'cli_auth_credentials_store="file"' \
    >/dev/null 2>&1 || {
    /bin/echo "dedicated worker Codex login is not valid" >&2
    exit 65
  }
}

verify_complete_auth() {
  verify_auth_metadata
  verify_login_without_output
  # Re-check after Codex has opened the credential so a successful result can
  # never attest metadata that changed during provider validation.
  verify_auth_metadata
}

if [ "$VERIFY_ONLY" = "true" ]; then
  verify_complete_auth
  /bin/echo "dedicated worker auth verification passed"
  exit 0
fi

if [ -e "$AUTH_PATH" ] || [ -L "$AUTH_PATH" ]; then
  verify_complete_auth
  /bin/echo "dedicated worker auth already exists and verification passed"
  exit 0
fi

/bin/echo "Starting OpenAI device authorization for the dedicated worker account."
/bin/echo "Open the URL shown by Codex, enter its one-time code, and finish sign-in; do not share the code."
/usr/bin/tty -s || {
  /bin/echo "device authorization requires an interactive controlling terminal" >&2
  exit 65
}
# Keep the provider's one-time device prompt on the controlling terminal. It is
# never sent through this script's stdout/stderr, where automation might log it.
run_codex_as_worker login --device-auth -c 'cli_auth_credentials_store="file"' \
  </dev/tty >/dev/tty 2>/dev/tty

verify_complete_auth
/bin/echo "dedicated worker auth provisioning and verification passed"
