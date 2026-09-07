#!/bin/bash
# Nightly Executive OS backup + off-host DR export wrapper, launchd-invoked
# as com.mastermind.executive.backup (StartCalendarInterval, RunAtLoad=false,
# ships DISABLED with every other daemon here -- see DR_RUNBOOK.md for the
# one-time arming ceremony).
#
# Sequence: phase1c client `backup` over the operator socket -> `verify-backup`
# on the result -> `executive_dr_cli.py export` (client-side encrypt-then-MAC)
# -> `executive_dr_cli.py ship`. Every step writes a typed JSON receipt into
# the receipts directory. ANY failure at ANY step exits non-zero and touches
# nothing about the live runtime: this script never calls `restore-backup`,
# never stops the service, and never deletes a prior receipt or backup.
#
# Credential handling (adversarial review B3): the GitHub transport
# credential is NEVER read from this process's environment and NEVER lives
# in the launchd plist's EnvironmentVariables (that dict ships inside a
# world-readable 0644 plist, and would be silently overwritten on every
# reinstall besides). It is a 0400 file this script hands straight to
# executive_dr_cli.py's own --token-file reader, exactly like the master
# key -- the secret's bytes never appear on this script's own argv, in its
# own environment, or in any receipt.
set -euo pipefail
umask 077

PYTHON_BINARY=""
RELEASE_ROOT=""
CONTROL_CONFIG=""
DR_KEY_FILE=""
DR_RECEIPTS_DIR=""
DR_TRANSPORT="github"
DR_VAULT_REPO=""
DR_TOKEN_FILE=""

usage() {
  /bin/echo "usage: $0 --python-binary PATH --release-root PATH --config PATH --key-file PATH --receipts-dir PATH --transport {github|directory} --repo OWNER/REPO [--token-file PATH]" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --python-binary) PYTHON_BINARY="${2:-}"; shift 2 ;;
    --release-root) RELEASE_ROOT="${2:-}"; shift 2 ;;
    --config) CONTROL_CONFIG="${2:-}"; shift 2 ;;
    --key-file) DR_KEY_FILE="${2:-}"; shift 2 ;;
    --receipts-dir) DR_RECEIPTS_DIR="${2:-}"; shift 2 ;;
    --transport) DR_TRANSPORT="${2:-}"; shift 2 ;;
    --repo) DR_VAULT_REPO="${2:-}"; shift 2 ;;
    --token-file) DR_TOKEN_FILE="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

for required in PYTHON_BINARY RELEASE_ROOT CONTROL_CONFIG DR_KEY_FILE DR_RECEIPTS_DIR DR_VAULT_REPO; do
  [ -n "${!required}" ] || usage
done
case "$DR_TRANSPORT" in
  github) [ -n "$DR_TOKEN_FILE" ] || usage ;;
  directory) ;;
  *) usage ;;
esac

STAMP="$(/bin/date -u +%Y%m%dT%H%M%SZ)"
/bin/mkdir -p -m 0700 "$DR_RECEIPTS_DIR"
# Sibling of the receipts dir, NOT under WORK_DIR -- WORK_DIR is rm -rf'd on
# every exit (see the trap below), so anything a failure needs to survive
# past this process must live outside it (adversarial review M2).
FAILURES_DIR="$(/usr/bin/dirname "$DR_RECEIPTS_DIR")/dr-failed-exports"

write_receipt() {
  local name="$1"
  local status="$2"
  local body_file="$3"
  local receipt_path="$DR_RECEIPTS_DIR/${STAMP}-${name}.json"
  local tmp_path="$DR_RECEIPTS_DIR/.${STAMP}-${name}.json.tmp"
  "$PYTHON_BINARY" -I -S -B -c '
import json, sys
status, body_path, out_path = sys.argv[1:4]
try:
    body = json.loads(open(body_path, "r", encoding="utf-8").read() or "{}")
except Exception:
    body = {"raw": open(body_path, "r", encoding="utf-8", errors="replace").read()}
payload = {"status": status, "body": body}
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
' "$status" "$body_file" "$tmp_path"
  # Adversarial review minor: under `set -e`, a failed chmod here would
  # abort the WHOLE script before the receipt is ever renamed into place,
  # silently losing it. Best-effort the permission tightening; the receipt
  # itself (the thing an operator actually needs) is never allowed to be
  # lost over it.
  /bin/chmod 0600 "$tmp_path" || true
  /bin/mv -f "$tmp_path" "$receipt_path"
}

WORK_DIR="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/mastermind-dr-backup.XXXXXX")"
trap '/bin/rm -rf -- "$WORK_DIR"' EXIT
/bin/chmod 0700 "$WORK_DIR"

# `backup` and `verify-backup` are client commands that cross the already-
# running control service's operator socket (executive_os_phase1c.py:963-968)
# -- they are never given `--config` directly. The socket path is read out of
# the same root-owned control config this wrapper was handed.
CONTROL_SOCKET_PATH="$WORK_DIR/control_socket_path"
"$PYTHON_BINARY" -I -S -B -c '
import json, sys
config = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
open(sys.argv[2], "w", encoding="utf-8").write(str(config["control_socket_path"]))
' "$CONTROL_CONFIG" "$CONTROL_SOCKET_PATH"
CONTROL_SOCKET="$(cat "$CONTROL_SOCKET_PATH")"

BACKUP_OUT="$WORK_DIR/backup.out"
if ! "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/scripts/executive_os_phase1c.py" \
  --socket "$CONTROL_SOCKET" backup >"$BACKUP_OUT" 2>&1; then
  write_receipt "backup" "FAILED" "$BACKUP_OUT"
  /bin/echo "nightly Executive backup failed; runtime untouched" >&2
  exit 65
fi
write_receipt "backup" "OK" "$BACKUP_OUT"

# Discover the backup this run just created. The client response envelope is
# {"ok": true, "result": {...BackupReceipt...}} (executive_service.py:1249).
ARTIFACT_PATH="$WORK_DIR/artifact_path"
MANIFEST_PATH="$WORK_DIR/manifest_path"
"$PYTHON_BINARY" -I -S -B -c '
import json, sys
response = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
result = response["result"]
open(sys.argv[2], "w", encoding="utf-8").write(result["database_path"])
open(sys.argv[3], "w", encoding="utf-8").write(result["manifest_path"])
' "$BACKUP_OUT" "$ARTIFACT_PATH" "$MANIFEST_PATH"
ARTIFACT="$(cat "$ARTIFACT_PATH")"
MANIFEST="$(cat "$MANIFEST_PATH")"

VERIFY_OUT="$WORK_DIR/verify.out"
if ! "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/scripts/executive_os_phase1c.py" \
  --socket "$CONTROL_SOCKET" verify-backup "$(/usr/bin/basename "$ARTIFACT")" >"$VERIFY_OUT" 2>&1; then
  write_receipt "verify" "FAILED" "$VERIFY_OUT"
  /bin/echo "nightly Executive backup verification failed; runtime untouched" >&2
  exit 65
fi
write_receipt "verify" "OK" "$VERIFY_OUT"

SOURCE_RELEASE_COMMIT="$(/usr/bin/basename "$RELEASE_ROOT")"
STAGING_DIR="$WORK_DIR/staging"
EXPORT_OUT="$WORK_DIR/export.out"
if ! "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/scripts/executive_dr_cli.py" export \
  --artifact "$ARTIFACT" --manifest "$MANIFEST" --staging-dir "$STAGING_DIR" \
  --transport-target "$DR_TRANSPORT" --retention-class nightly \
  --source-release-commit "$SOURCE_RELEASE_COMMIT" --key-file "$DR_KEY_FILE" \
  >"$EXPORT_OUT" 2>"$EXPORT_OUT.err"; then
  write_receipt "export" "FAILED" "$EXPORT_OUT.err"
  /bin/echo "nightly Executive DR export failed; runtime untouched" >&2
  exit 65
fi
write_receipt "export" "OK" "$EXPORT_OUT"

CIPHERTEXT_PATH="$WORK_DIR/ciphertext_path"
ENVELOPE_PATH="$WORK_DIR/envelope_path"
"$PYTHON_BINARY" -I -S -B -c '
import json, sys
receipt = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
open(sys.argv[2], "w", encoding="utf-8").write(receipt["ciphertext_path"])
open(sys.argv[3], "w", encoding="utf-8").write(receipt["envelope_path"])
' "$EXPORT_OUT" "$CIPHERTEXT_PATH" "$ENVELOPE_PATH"
CIPHERTEXT="$(cat "$CIPHERTEXT_PATH")"
ENVELOPE="$(cat "$ENVELOPE_PATH")"

SHIP_OUT="$WORK_DIR/ship.out"
SHIP_STATUS=0
if [ "$DR_TRANSPORT" = "github" ]; then
  "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/scripts/executive_dr_cli.py" ship \
    --ciphertext "$CIPHERTEXT" --envelope "$ENVELOPE" --transport github \
    --repo "$DR_VAULT_REPO" --token-file "$DR_TOKEN_FILE" \
    >"$SHIP_OUT" 2>"$SHIP_OUT.err" || SHIP_STATUS=$?
else
  "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/scripts/executive_dr_cli.py" ship \
    --ciphertext "$CIPHERTEXT" --envelope "$ENVELOPE" --transport directory \
    --directory "$DR_VAULT_REPO" \
    >"$SHIP_OUT" 2>"$SHIP_OUT.err" || SHIP_STATUS=$?
fi

if [ "$SHIP_STATUS" -ne 0 ]; then
  # Adversarial review M2: the OLD version of this branch claimed "local
  # export retained" while the EXIT trap unconditionally rm -rf'd WORK_DIR,
  # which is where the export actually lived -- the claim was false. Copy
  # the ciphertext + envelope out to a directory that survives this
  # process's exit BEFORE reporting anything, and name the retained paths
  # in the receipt so the claim is true.
  /bin/mkdir -p -m 0700 "$FAILURES_DIR"
  RETAINED_CIPHER="$FAILURES_DIR/${STAMP}-$(/usr/bin/basename "$CIPHERTEXT")"
  RETAINED_ENVELOPE="$FAILURES_DIR/${STAMP}-$(/usr/bin/basename "$ENVELOPE")"
  RETENTION_OK=1
  /bin/cp -p "$CIPHERTEXT" "$RETAINED_CIPHER" 2>/dev/null || RETENTION_OK=0
  /bin/cp -p "$ENVELOPE" "$RETAINED_ENVELOPE" 2>/dev/null || RETENTION_OK=0
  /bin/chmod 0600 "$RETAINED_CIPHER" "$RETAINED_ENVELOPE" 2>/dev/null || true
  SHIP_FAILURE_BODY="$WORK_DIR/ship_failure_body.json"
  "$PYTHON_BINARY" -I -S -B -c '
import json, sys
stderr_path, retained_cipher, retained_envelope, retention_ok, out_path = sys.argv[1:6]
stderr_text = open(stderr_path, "r", encoding="utf-8", errors="replace").read()
payload = {
    "stderr": stderr_text,
    "export_retained": retention_ok == "1",
    "retained_ciphertext_path": retained_cipher if retention_ok == "1" else None,
    "retained_envelope_path": retained_envelope if retention_ok == "1" else None,
}
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
' "$SHIP_OUT.err" "$RETAINED_CIPHER" "$RETAINED_ENVELOPE" "$RETENTION_OK" "$SHIP_FAILURE_BODY"
  write_receipt "ship" "FAILED" "$SHIP_FAILURE_BODY"
  if [ "$RETENTION_OK" -eq 1 ]; then
    /bin/echo "nightly Executive DR ship failed; local export retained at $RETAINED_CIPHER; runtime untouched" >&2
  else
    /bin/echo "nightly Executive DR ship failed; retaining the local export ALSO failed; runtime untouched" >&2
  fi
  exit 65
fi
write_receipt "ship" "OK" "$SHIP_OUT"

/bin/echo "nightly Executive backup + off-host DR export completed"
