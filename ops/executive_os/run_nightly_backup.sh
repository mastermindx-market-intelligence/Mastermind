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
set -euo pipefail
umask 077

PYTHON_BINARY=""
RELEASE_ROOT=""
CONTROL_CONFIG=""
DR_KEY_FILE=""
DR_RECEIPTS_DIR=""
DR_TRANSPORT="github"
DR_VAULT_REPO=""
DR_TOKEN_ENV="EXECUTIVE_DR_TOKEN"

usage() {
  /bin/echo "usage: $0 --python-binary PATH --release-root PATH --config PATH --key-file PATH --receipts-dir PATH --transport {github|directory} --repo OWNER/REPO --token-env NAME" >&2
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
    --token-env) DR_TOKEN_ENV="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

for required in PYTHON_BINARY RELEASE_ROOT CONTROL_CONFIG DR_KEY_FILE DR_RECEIPTS_DIR DR_VAULT_REPO; do
  [ -n "${!required}" ] || usage
done
case "$DR_TRANSPORT" in
  github|directory) ;;
  *) usage ;;
esac

STAMP="$(/bin/date -u +%Y%m%dT%H%M%SZ)"
/bin/mkdir -p -m 0700 "$DR_RECEIPTS_DIR"

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
  /bin/chmod 0600 "$tmp_path"
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
if [ "$DR_TRANSPORT" = "github" ]; then
  SHIP_STATUS=0
  "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/scripts/executive_dr_cli.py" ship \
    --ciphertext "$CIPHERTEXT" --envelope "$ENVELOPE" --transport github \
    --repo "$DR_VAULT_REPO" --token-env "$DR_TOKEN_ENV" \
    >"$SHIP_OUT" 2>"$SHIP_OUT.err" || SHIP_STATUS=$?
else
  SHIP_STATUS=0
  "$PYTHON_BINARY" -I -S -B "$RELEASE_ROOT/scripts/executive_dr_cli.py" ship \
    --ciphertext "$CIPHERTEXT" --envelope "$ENVELOPE" --transport directory \
    --directory "$DR_VAULT_REPO" \
    >"$SHIP_OUT" 2>"$SHIP_OUT.err" || SHIP_STATUS=$?
fi
if [ "$SHIP_STATUS" -ne 0 ]; then
  write_receipt "ship" "FAILED" "$SHIP_OUT.err"
  /bin/echo "nightly Executive DR ship failed; local export retained, runtime untouched" >&2
  exit 65
fi
write_receipt "ship" "OK" "$SHIP_OUT"

/bin/echo "nightly Executive backup + off-host DR export completed"
