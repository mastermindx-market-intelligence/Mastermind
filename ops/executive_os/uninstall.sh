#!/bin/bash
# Stop and remove only the two Executive OS launchd registrations. Runtime
# state, backups, provider auth, service accounts, binaries, and releases are
# intentionally preserved for recovery or reinstall.
set -euo pipefail
umask 077

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "uninstall.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "uninstall.sh supports macOS only" >&2
  exit 69
}

CONTROL_LABEL="com.mastermind.executive.control"
WORKER_LABEL="com.mastermind.executive.worker.codex"
CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"
WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"

/bin/launchctl disable "system/$CONTROL_LABEL"
/bin/launchctl disable "system/$WORKER_LABEL"
/bin/launchctl bootout "system/$CONTROL_LABEL" >/dev/null 2>&1 || true
/bin/launchctl bootout "system/$WORKER_LABEL" >/dev/null 2>&1 || true
/bin/rm -f -- "$CONTROL_PLIST" "$WORKER_PLIST"

/bin/echo "Executive OS launchd services removed"
/bin/echo "preserved: /var/db/mastermind-executive and /Library/Application Support/MastermindExecutive"
