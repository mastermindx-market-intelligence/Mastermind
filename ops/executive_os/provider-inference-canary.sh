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

SLOT_ID="codex-01"
SLOT_MODE="codex"

usage() {
  /bin/echo "usage: $0 [--slot-id codex-01|codex-pro-01|codex-pro-02|codex-pro-03 | --subscription-slot-id alibaba-token-01|minimax-token-01]" >&2
  exit 64
}

if [ "$#" -gt 0 ]; then
  [ "$#" -eq 2 ] || usage
  case "$1" in
    --slot-id)
      case "$2" in
        codex-01|codex-pro-01|codex-pro-02|codex-pro-03) SLOT_ID="$2" ;;
        *) usage ;;
      esac
      ;;
    --subscription-slot-id)
      case "$2" in
        alibaba-token-01|minimax-token-01)
          SLOT_ID="$2"
          SLOT_MODE="subscription"
          ;;
        *) usage ;;
      esac
      ;;
    *) usage ;;
  esac
fi

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

if [ "$SLOT_MODE" = "subscription" ]; then
  "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_inference_canary.py" \
    --subscription-slot-id "$SLOT_ID"
else
  "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/provider_inference_canary.py" \
    --slot-id "$SLOT_ID"
fi
status=$?
exit "$status"
