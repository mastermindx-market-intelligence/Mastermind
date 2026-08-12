#!/bin/bash
# Bounded lifecycle controller for exactly the two Executive OS system jobs.
# It never accepts a label, plist path, domain, or arbitrary launchctl verb.
set -euo pipefail
umask 077

CONTROL_LABEL="com.mastermind.executive.control"
WORKER_LABEL="com.mastermind.executive.worker.codex"
CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"
WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"
SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "$0")" && /bin/pwd)"

usage() {
  /bin/echo "usage: $0 {start|stop|restart|status}" >&2
  exit 64
}

require_root() {
  [ "$(/usr/bin/id -u)" -eq 0 ] || {
    /bin/echo "service lifecycle changes require root" >&2
    exit 77
  }
  [ "$(/usr/bin/uname -s)" = "Darwin" ] || {
    /bin/echo "service-control.sh supports macOS only" >&2
    exit 69
  }
}

validate_plist() {
  local path="$1"
  [ -f "$path" ] && [ ! -L "$path" ] || {
    /bin/echo "missing or unsafe launchd plist: $path" >&2
    exit 65
  }
  /usr/bin/plutil -lint "$path" >/dev/null
}

start_one() {
  local label="$1"
  local plist="$2"
  /bin/launchctl enable "system/$label"
  if /bin/launchctl print "system/$label" >/dev/null 2>&1; then
    /bin/launchctl kickstart "system/$label"
  else
    /bin/launchctl bootstrap system "$plist"
  fi
}

stop_one() {
  local label="$1"
  /bin/launchctl disable "system/$label"
  /bin/launchctl bootout "system/$label" >/dev/null 2>&1 || true
}

[ "$#" -eq 1 ] || usage
case "$1" in
  start)
    require_root
    validate_plist "$WORKER_PLIST"
    validate_plist "$CONTROL_PLIST"
    start_one "$WORKER_LABEL" "$WORKER_PLIST"
    start_one "$CONTROL_LABEL" "$CONTROL_PLIST"
    ;;
  stop)
    require_root
    # Stop the control plane before removing its worker execution boundary.
    stop_one "$CONTROL_LABEL"
    stop_one "$WORKER_LABEL"
    ;;
  restart)
    require_root
    validate_plist "$WORKER_PLIST"
    validate_plist "$CONTROL_PLIST"
    stop_one "$CONTROL_LABEL"
    stop_one "$WORKER_LABEL"
    start_one "$WORKER_LABEL" "$WORKER_PLIST"
    start_one "$CONTROL_LABEL" "$CONTROL_PLIST"
    ;;
  status)
    exec /bin/bash "$SCRIPT_DIR/status.sh"
    ;;
  *) usage ;;
esac
