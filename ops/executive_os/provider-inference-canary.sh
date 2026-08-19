#!/bin/bash
# Root-gated wrapper for the zero-Executive-write Codex inference canary.
# This does not start services, open the control database, or write production
# workspaces. It never prints credential contents.
#
# Live production CLI paths are frozen. This wrapper does not forward caller
# arguments: --probe-root, --operator-home, and --receipt-path are not public
# options. The Python helper creates its own disposable probe root.
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

"$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_inference_canary.py"
status=$?
exit "$status"
