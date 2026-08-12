#!/bin/bash
# Root/operator-gated wrapper for the exact-SHA real-host Phase 1C-A proof.
set -euo pipefail
umask 077

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "acceptance.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "acceptance.sh supports macOS only" >&2
  exit 69
}

SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "$0")" && /bin/pwd)"
CONTROL_PLIST="/Library/LaunchDaemons/com.mastermind.executive.control.plist"
[ -r "$CONTROL_PLIST" ] || {
  /bin/echo "private installed control plist is unavailable; run install.sh first" >&2
  exit 65
}
PYTHON_BINARY="$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "$CONTROL_PLIST")"
[ -x "$PYTHON_BINARY" ] || {
  /bin/echo "installed control Python is unavailable" >&2
  exit 65
}
exec "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/acceptance.py" "$@"
