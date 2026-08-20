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
SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
SYSTEM_BIN="$SYSTEM_ROOT/bin"
SYSTEM_CONFIG="$SYSTEM_ROOT/config"
VERIFY_ONLY="false"
VERIFY_READY="false"
ENROLL_SERVICE_ACCOUNT="false"
ENROLL_PERSONAL_ACCESS_TOKEN="false"
REAUTHORIZE_DEVICE="false"
REPLACE_EXISTING="false"
RECOVER_READINESS_TRANSACTION="false"
EXPECTED_CREDENTIAL_KIND=""
WORKSPACE_BINDING_CLASS=""
CREDENTIAL_EXPIRES_AT=""
READINESS_RECEIPT="/Library/Application Support/MastermindExecutive/config/provider-readiness-v2.json"
READINESS_TRANSACTION_LOCK="$SYSTEM_CONFIG/provider-readiness.transaction.lock"
READINESS_LOCK_HELD="false"
READINESS_LOCK_RELEASE_ON_EXIT="true"
INSTALLED_CODEX_BINARY=""
PINNED_CODEX_BINARY=""
IDENTITY_RESULT=""
POST_IDENTITY_RESULT=""
CANARY_RESULT=""

cleanup() {
  if [ -n "$PINNED_CODEX_BINARY" ] && [ -f "$PINNED_CODEX_BINARY" ]; then
    /bin/rm -f -- "$PINNED_CODEX_BINARY"
  fi
  [ -z "$IDENTITY_RESULT" ] || /bin/rm -f -- "$IDENTITY_RESULT"
  [ -z "$POST_IDENTITY_RESULT" ] || /bin/rm -f -- "$POST_IDENTITY_RESULT"
  [ -z "$CANARY_RESULT" ] || /bin/rm -f -- "$CANARY_RESULT"
  if [ "$READINESS_LOCK_HELD" = "true" ] \
    && [ "$READINESS_LOCK_RELEASE_ON_EXIT" = "true" ]; then
    lock_owner="$READINESS_TRANSACTION_LOCK/owner-pid"
    if [ -d "$READINESS_TRANSACTION_LOCK" ] && [ ! -L "$READINESS_TRANSACTION_LOCK" ] \
      && [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$READINESS_TRANSACTION_LOCK" 2>/dev/null || true)" = "0:0:700" ]; then
      if [ -f "$lock_owner" ] && [ ! -L "$lock_owner" ] \
        && [ "$(/bin/cat "$lock_owner" 2>/dev/null || true)" = "$$" ]; then
        /bin/rm -f -- "$lock_owner"
        /bin/rmdir -- "$READINESS_TRANSACTION_LOCK"
      elif [ ! -e "$lock_owner" ] && [ ! -L "$lock_owner" ]; then
        /bin/rmdir -- "$READINESS_TRANSACTION_LOCK"
      else
        /bin/echo "provider readiness transaction lock was not released because its owner changed" >&2
      fi
    else
      /bin/echo "provider readiness transaction lock was not released because its identity changed" >&2
    fi
  elif [ "$READINESS_LOCK_HELD" = "true" ]; then
    /bin/echo "provider readiness transaction lock preserved after termination signal" >&2
  fi
}
trap cleanup EXIT

preserve_readiness_lock_on_signal() {
  READINESS_LOCK_RELEASE_ON_EXIT="false"
  exit "$1"
}
trap 'preserve_readiness_lock_on_signal 129' HUP
trap 'preserve_readiness_lock_on_signal 130' INT
trap 'preserve_readiness_lock_on_signal 131' QUIT
trap 'preserve_readiness_lock_on_signal 143' TERM

usage() {
  /bin/echo "usage: sudo /bin/bash $0 MODE [--replace-existing] [--expected-credential-kind KIND] [--workspace-binding-class company-workspace-admin-attested] [--credential-expires-at UTC] [options]" >&2
  /bin/echo "modes: --verify-only | --verify-ready | --enroll-service-account | --enroll-personal-access-token | --reauthorize-device | --recover-readiness-transaction" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --verify-only) VERIFY_ONLY="true"; shift ;;
    --verify-ready) VERIFY_READY="true"; shift ;;
    --enroll-service-account) ENROLL_SERVICE_ACCOUNT="true"; shift ;;
    --enroll-personal-access-token) ENROLL_PERSONAL_ACCESS_TOKEN="true"; shift ;;
    --reauthorize-device) REAUTHORIZE_DEVICE="true"; shift ;;
    --replace-existing) REPLACE_EXISTING="true"; shift ;;
    --recover-readiness-transaction) RECOVER_READINESS_TRANSACTION="true"; shift ;;
    --expected-credential-kind) EXPECTED_CREDENTIAL_KIND="${2:-}"; shift 2 ;;
    --workspace-binding-class) WORKSPACE_BINDING_CLASS="${2:-}"; shift 2 ;;
    --credential-expires-at) CREDENTIAL_EXPIRES_AT="${2:-}"; shift 2 ;;
    --codex-binary) CODEX_BINARY="${2:-}"; shift 2 ;;
    --codex-version) CODEX_VERSION="${2:-}"; shift 2 ;;
    --worker-uid) WORKER_UID="${2:-}"; WORKER_GID="${2:-}"; shift 2 ;;
    --provider-home) PROVIDER_HOME="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

mode_count=0
[ "$VERIFY_ONLY" = "true" ] && mode_count=$((mode_count + 1))
[ "$VERIFY_READY" = "true" ] && mode_count=$((mode_count + 1))
[ "$ENROLL_SERVICE_ACCOUNT" = "true" ] && mode_count=$((mode_count + 1))
[ "$ENROLL_PERSONAL_ACCESS_TOKEN" = "true" ] && mode_count=$((mode_count + 1))
[ "$REAUTHORIZE_DEVICE" = "true" ] && mode_count=$((mode_count + 1))
[ "$RECOVER_READINESS_TRANSACTION" = "true" ] && mode_count=$((mode_count + 1))
[ "$mode_count" -eq 1 ] || usage

if [ "$REPLACE_EXISTING" = "true" ] \
  && [ "$ENROLL_SERVICE_ACCOUNT" != "true" ] \
  && [ "$ENROLL_PERSONAL_ACCESS_TOKEN" != "true" ] \
  && [ "$REAUTHORIZE_DEVICE" != "true" ]; then
  /bin/echo "--replace-existing is valid only with an explicit enrollment mode" >&2
  exit 65
fi

if [ "$VERIFY_READY" = "true" ]; then
  case "$EXPECTED_CREDENTIAL_KIND" in
    service-account|personal-access-token|device-auth) ;;
    *) /bin/echo "--verify-ready requires an explicit reviewed credential kind" >&2; exit 65 ;;
  esac
  [ "$WORKSPACE_BINDING_CLASS" = "company-workspace-admin-attested" ] || {
    /bin/echo "--verify-ready requires the company workspace admin attestation class" >&2
    exit 65
  }
  case "$CREDENTIAL_EXPIRES_AT" in
    ????-??-??T??:??:??Z) ;;
    *) /bin/echo "--verify-ready requires an exact UTC credential expiry" >&2; exit 65 ;;
  esac
elif [ -n "$EXPECTED_CREDENTIAL_KIND" ] || [ -n "$WORKSPACE_BINDING_CLASS" ] \
  || [ -n "$CREDENTIAL_EXPIRES_AT" ]; then
  /bin/echo "identity policy arguments are valid only with --verify-ready" >&2
  exit 65
fi

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
INSTALLED_CODEX_BINARY="$SYSTEM_BIN/codex-$CODEX_VERSION"
for absolute_path in "$PROVIDER_HOME" "$CODEX_BINARY"; do
  case "$absolute_path" in
    /*) ;;
    *) /bin/echo "worker-auth paths must be absolute: $absolute_path" >&2; exit 65 ;;
  esac
done

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
      /bin/echo "worker account has an unreadable authentication authority" >&2
      exit 65
      ;;
  esac
  case "$authority" in
    ''|';DisabledUser;') ;;
    *)
      /bin/echo "worker account has an unreviewed authentication authority" >&2
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
    /bin/echo "worker account is not authentication-disabled" >&2
    exit 65
  }
}

run_codex_as_worker() {
  (
    # Codex loads project .codex/config.toml layers from the current working
    # directory upward. Never let this dedicated principal discover an
    # operator checkout or the operator's personal ~/.codex configuration.
    cd -- "$PROVIDER_HOME"
    exec /usr/bin/sudo -n -u "$WORKER_USER" -g "$WORKER_GROUP" \
      /usr/bin/env -i \
        HOME="$PROVIDER_HOME" \
        CODEX_HOME="$PROVIDER_HOME" \
        PWD="$PROVIDER_HOME" \
        LANG="C.UTF-8" \
        LC_ALL="C.UTF-8" \
        NO_COLOR="1" \
        PATH="/usr/bin:/bin" \
        "$PINNED_CODEX_BINARY" "$@"
  )
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
  && [ "$(read_dscl_attribute "/Users/$WORKER_USER" Password)" = "*" ] || {
    /bin/echo "worker account does not match the bootstrapped disabled-account policy" >&2
    exit 65
  }
verify_authentication_disabled "$WORKER_USER"

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

SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "$0")" && /bin/pwd)"
PYTHON_BINARY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"

verify_readiness_transaction_chain() {
  local ancestor mode
  for ancestor in /Library "/Library/Application Support" "$SYSTEM_ROOT" "$SYSTEM_CONFIG"; do
    [ -d "$ancestor" ] && [ ! -L "$ancestor" ] || {
      /bin/echo "provider readiness ancestor is not a direct directory: $ancestor" >&2
      exit 65
    }
    [ "$(/usr/bin/stat -f '%u' "$ancestor")" = "0" ] || {
      /bin/echo "provider readiness ancestor is not root-owned: $ancestor" >&2
      exit 65
    }
    mode="$(/usr/bin/stat -f '%Lp' "$ancestor")"
    [ $((8#$mode & 022)) -eq 0 ] || {
      /bin/echo "provider readiness ancestor is group/other writable: $ancestor" >&2
      exit 65
    }
    case "$(/usr/bin/stat -f '%Sp' "$ancestor")" in
      *+) /bin/echo "provider readiness ancestor has an unexpected ACL: $ancestor" >&2; exit 65 ;;
    esac
  done
}

fsync_readiness_config_directory() {
  "$PYTHON_BINARY" -I -S -B -c \
    'import os,sys; fd=os.open(sys.argv[1], os.O_RDONLY); os.fsync(fd); os.close(fd)' \
    "$SYSTEM_CONFIG"
}

fsync_readiness_lock_state() {
  "$PYTHON_BINARY" -I -S -B -c \
    'import os,sys; [(lambda fd: (os.fsync(fd),os.close(fd)))(os.open(p,os.O_RDONLY)) for p in sys.argv[1:]]' \
    "$READINESS_TRANSACTION_LOCK/owner-pid" "$READINESS_TRANSACTION_LOCK" "$SYSTEM_CONFIG"
}

acquire_readiness_transaction_lock() {
  verify_readiness_transaction_chain
  if ! /bin/mkdir -m 0700 -- "$READINESS_TRANSACTION_LOCK" 2>/dev/null; then
    /bin/echo "another provider readiness or credential transaction is active; fail closed" >&2
    exit 65
  fi
  READINESS_LOCK_HELD="true"
  /usr/sbin/chown root:wheel "$READINESS_TRANSACTION_LOCK"
  /bin/chmod 0700 "$READINESS_TRANSACTION_LOCK"
  /bin/echo "$$" >"$READINESS_TRANSACTION_LOCK/owner-pid"
  /usr/sbin/chown root:wheel "$READINESS_TRANSACTION_LOCK/owner-pid"
  /bin/chmod 0400 "$READINESS_TRANSACTION_LOCK/owner-pid"
  [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$READINESS_TRANSACTION_LOCK")" = "0:0:700" ] \
    && [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$READINESS_TRANSACTION_LOCK/owner-pid")" = "0:0:400:1" ] || {
      /bin/echo "provider readiness transaction lock metadata is unsafe" >&2
      exit 65
    }
  for lock_path in "$READINESS_TRANSACTION_LOCK" "$READINESS_TRANSACTION_LOCK/owner-pid"; do
    case "$(/usr/bin/stat -f '%Sp' "$lock_path")" in
      *+) /bin/echo "provider readiness transaction lock has an unexpected ACL" >&2; exit 65 ;;
    esac
  done
  fsync_readiness_lock_state
}

recover_readiness_transaction_lock() {
  local lock_owner owner_pid
  verify_readiness_transaction_chain
  lock_owner="$READINESS_TRANSACTION_LOCK/owner-pid"
  [ -d "$READINESS_TRANSACTION_LOCK" ] && [ ! -L "$READINESS_TRANSACTION_LOCK" ] \
    && [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$READINESS_TRANSACTION_LOCK")" = "0:0:700" ] \
    && [ -f "$lock_owner" ] && [ ! -L "$lock_owner" ] \
    && [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$lock_owner")" = "0:0:400:1" ] || {
      /bin/echo "no safely recoverable provider readiness transaction lock exists" >&2
      exit 65
    }
  for lock_path in "$READINESS_TRANSACTION_LOCK" "$lock_owner"; do
    case "$(/usr/bin/stat -f '%Sp' "$lock_path")" in
      *+) /bin/echo "provider readiness transaction lock has an unexpected ACL" >&2; exit 65 ;;
    esac
  done
  owner_pid="$(/bin/cat "$lock_owner")"
  case "$owner_pid" in
    ''|*[!0-9]*) /bin/echo "provider readiness transaction owner PID is malformed" >&2; exit 65 ;;
  esac
  if /bin/kill -0 "$owner_pid" 2>/dev/null; then
    /bin/echo "provider readiness transaction owner is still alive; recovery refused" >&2
    exit 65
  fi
  if /usr/bin/pgrep -U "$WORKER_UID" >/dev/null 2>&1; then
    /bin/echo "a dedicated worker process is still alive; recovery refused" >&2
    exit 65
  fi
  /bin/rm -f -- "$lock_owner"
  /bin/rmdir -- "$READINESS_TRANSACTION_LOCK"
  fsync_readiness_config_directory
  /bin/echo "stale provider readiness transaction lock cleared; no receipt or credential changed"
}

invalidate_readiness_receipt() {
  if [ -e "$READINESS_RECEIPT" ] || [ -L "$READINESS_RECEIPT" ]; then
    [ -f "$READINESS_RECEIPT" ] && [ ! -L "$READINESS_RECEIPT" ] \
      && [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$READINESS_RECEIPT")" = "0:0:400:1" ] || {
        /bin/echo "existing provider readiness receipt is unsafe" >&2
        exit 65
      }
    case "$(/usr/bin/stat -f '%Sp' "$READINESS_RECEIPT")" in
      *+) /bin/echo "existing provider readiness receipt has an ACL" >&2; exit 65 ;;
    esac
    /bin/rm -f -- "$READINESS_RECEIPT"
  fi
}

prepare_explicit_replacement() {
  if [ -e "$AUTH_PATH" ] || [ -L "$AUTH_PATH" ]; then
    [ "$REPLACE_EXISTING" = "true" ] || {
      /bin/echo "credential exists; explicit --replace-existing is required for rotation" >&2
      exit 65
    }
    verify_auth_metadata
    invalidate_readiness_receipt
    run_codex_as_worker logout -c 'cli_auth_credentials_store="file"' \
      >/dev/null 2>&1 || true
    [ ! -e "$AUTH_PATH" ] && [ ! -L "$AUTH_PATH" ] || {
      /bin/echo "Codex logout did not remove the prior dedicated credential" >&2
      exit 65
    }
  else
    invalidate_readiness_receipt
  fi
}

enroll_access_token_from_stdin() {
  /usr/bin/tty -s && {
    /bin/echo "access-token enrollment requires a non-terminal stdin stream" >&2
    exit 65
  }
  prepare_explicit_replacement
  # The token remains on the caller's stdin descriptor through the privilege
  # drop to Codex running as UID 451.  It is never a shell variable, argv,
  # environment entry, temporary file, command substitution, or receipt field.
  run_codex_as_worker login --with-access-token -c 'cli_auth_credentials_store="file"' \
    >/dev/null 2>&1
  verify_complete_auth
}

verify_installed_binary_available() {
  verify_pinned_python_available
  [ -x "$INSTALLED_CODEX_BINARY" ] && [ ! -L "$INSTALLED_CODEX_BINARY" ] || {
    /bin/echo "install the exact release before --verify-ready" >&2
    exit 65
  }
}

verify_pinned_python_available() {
  [ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || {
    /bin/echo "pinned Python is required for provider readiness transactions" >&2
    exit 65
  }
}

if [ "$RECOVER_READINESS_TRANSACTION" = "true" ]; then
  verify_pinned_python_available
  recover_readiness_transaction_lock
  exit 0
fi

if [ "$VERIFY_READY" = "true" ] || [ "$ENROLL_SERVICE_ACCOUNT" = "true" ] \
  || [ "$ENROLL_PERSONAL_ACCESS_TOKEN" = "true" ] || [ "$REAUTHORIZE_DEVICE" = "true" ]; then
  verify_pinned_python_available
  acquire_readiness_transaction_lock
fi

if [ "$VERIFY_ONLY" = "true" ]; then
  verify_complete_auth
  /bin/echo "dedicated worker login status passed; provider inference canary not run; not READY"
  exit 0
fi

if [ "$VERIFY_READY" = "true" ]; then
  verify_complete_auth
  verify_installed_binary_available
  if "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_readiness.py" reuse \
      --receipt "$READINESS_RECEIPT" --auth "$AUTH_PATH" \
      --binary "$INSTALLED_CODEX_BINARY" \
      --expected-kind "$EXPECTED_CREDENTIAL_KIND" \
      --workspace-binding-class "$WORKSPACE_BINDING_CLASS" \
      --credential-expires-at "$CREDENTIAL_EXPIRES_AT" >/dev/null 2>&1; then
    /bin/echo "dedicated worker auth is READY; current passing receipt reused; no canary spent"
    exit 0
  else
    reuse_status=$?
  fi
  [ "$reuse_status" -eq 3 ] || {
    /bin/echo "existing provider readiness receipt is stale or invalid; fail closed" >&2
    exit 65
  }

  IDENTITY_RESULT="$(/usr/bin/mktemp /private/tmp/mastermind-provider-identity.XXXXXX)"
  if ! "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_identity_probe.py" \
      --binary "$INSTALLED_CODEX_BINARY" --provider-home "$PROVIDER_HOME" \
      --expected-kind "$EXPECTED_CREDENTIAL_KIND" \
      --workspace-binding-class "$WORKSPACE_BINDING_CLASS" \
      >"$IDENTITY_RESULT" 2>/dev/null; then
    /bin/echo "provider identity policy refused before inference; no canary spent" >&2
    exit 65
  fi

  if ! "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_readiness.py" reserve \
      --receipt "$READINESS_RECEIPT" --auth "$AUTH_PATH" \
      --binary "$INSTALLED_CODEX_BINARY" --identity-json "$IDENTITY_RESULT" \
      --expected-kind "$EXPECTED_CREDENTIAL_KIND" \
      --workspace-binding-class "$WORKSPACE_BINDING_CLASS" \
      --credential-expires-at "$CREDENTIAL_EXPIRES_AT" >/dev/null 2>&1; then
    /bin/echo "provider canary reservation failed; no canary spent" >&2
    exit 65
  fi

  CANARY_RESULT="$(/usr/bin/mktemp /private/tmp/mastermind-provider-canary.XXXXXX)"
  canary_status=0
  /bin/bash "$SCRIPT_DIR/provider-inference-canary.sh" \
    >"$CANARY_RESULT" 2>/dev/null || canary_status=$?

  POST_IDENTITY_RESULT="$(/usr/bin/mktemp /private/tmp/mastermind-provider-post-identity.XXXXXX)"
  post_identity_status=0
  "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_identity_probe.py" \
    --binary "$INSTALLED_CODEX_BINARY" --provider-home "$PROVIDER_HOME" \
    --expected-kind "$EXPECTED_CREDENTIAL_KIND" \
    --workspace-binding-class "$WORKSPACE_BINDING_CLASS" \
    >"$POST_IDENTITY_RESULT" 2>/dev/null || post_identity_status=$?

  if "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_readiness.py" finalize \
      --receipt "$READINESS_RECEIPT" --auth "$AUTH_PATH" \
      --binary "$INSTALLED_CODEX_BINARY" --post-identity-json "$POST_IDENTITY_RESULT" \
      --canary-json "$CANARY_RESULT" --expected-kind "$EXPECTED_CREDENTIAL_KIND" \
      --post-identity-command-status "$post_identity_status" \
      --canary-command-status "$canary_status" \
      --workspace-binding-class "$WORKSPACE_BINDING_CLASS" \
      --credential-expires-at "$CREDENTIAL_EXPIRES_AT" >/dev/null 2>&1; then
    /bin/echo "dedicated worker auth is READY; one inference canary spent and composite receipt created"
    exit 0
  fi
  /bin/echo "provider readiness failed closed after one inference canary" >&2
  exit 65
fi

if [ "$ENROLL_SERVICE_ACCOUNT" = "true" ]; then
  enroll_access_token_from_stdin
  /bin/echo "service-account token enrolled; login status passed; inference canary not run; not READY"
  exit 0
fi

if [ "$ENROLL_PERSONAL_ACCESS_TOKEN" = "true" ]; then
  enroll_access_token_from_stdin
  /bin/echo "personal company-workspace token enrolled as explicit fallback; inference canary not run; not READY"
  exit 0
fi

if [ "$REAUTHORIZE_DEVICE" = "true" ]; then
  /usr/bin/tty -s || {
    /bin/echo "device authorization requires an interactive controlling terminal" >&2
    exit 65
  }
  prepare_explicit_replacement
  /bin/echo "Starting OpenAI device authorization for the dedicated worker account."
  /bin/echo "Open the URL shown by Codex, enter its one-time code, and finish sign-in; do not share the code."
  /bin/echo "Do not select a ChatGPT workspace because it happens to work; stop if the intended workspace cannot be bound."
  run_codex_as_worker login --device-auth -c 'cli_auth_credentials_store="file"' \
    </dev/tty >/dev/tty 2>/dev/tty
  verify_complete_auth
  /bin/echo "device fallback enrolled; login status passed; inference canary not run; not READY"
  exit 0
fi

usage
