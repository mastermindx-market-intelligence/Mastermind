#!/bin/bash
# Root-gated wrapper for the zero-Executive-write Codex inference canary.
# This does not start services, open the control database, or write production
# workspaces. It never prints credential contents.
set -euo pipefail
umask 077

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "provider-inference-canary.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "provider-inference-canary.sh supports macOS only" >&2
  exit 69
}

SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "$0")" && /bin/pwd)"
PYTHON_BINARY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
[ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || {
  /bin/echo "pinned Python 3.12 runtime is unavailable" >&2
  exit 65
}

PROBE_ROOT="$(/usr/bin/mktemp -d /private/tmp/mastermind-provider-canary.XXXXXX)"
/bin/chmod 0700 "$PROBE_ROOT"
cleanup() {
  if [ -d "$PROBE_ROOT" ]; then
    /usr/bin/find "$PROBE_ROOT" -mindepth 1 \( -name receipt.json -prune \) -o -exec /bin/rm -rf {} + 2>/dev/null || true
  fi
}
trap cleanup EXIT

"$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_inference_canary.py" \
  --probe-root "$PROBE_ROOT" \
  --operator-home /var/empty \
  "$@"
status=$?
exit "$status"
