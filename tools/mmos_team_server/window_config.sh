#!/bin/sh
# window_config.sh — write, inspect or clear the fixed per-user window config
# that the Mastermind OS window reads when no MM_SHELL_URL / MM_SHELL_URL_FILE
# environment variable is set (lane T8: the app a person opens from Finder or
# the Dock has no environment).
#
# The window maps bundle identifiers to config directories exactly like
# shell_mode.rs::fixed_config_dir:
#   release (com.mastermind.os)         -> ~/.mastermind/window
#   dev    (com.mastermind.os.dev)      -> ~/.mastermind/mmos_dev/window-dev
#   t8     (com.mastermind.os.dev.t8)   -> ~/.mastermind/mmos_dev/window-dev-t8
#
# Files inside: `shell-url` (one line, the loopback thread address; never a
# pairing token) and `pair-helper` (one line, absolute path to
# window_pair_helper.sh or a wrapper). Both must be mode 0600 and owned by
# the user, or the window refuses them.
#
# Usage:
#   window_config.sh write --bundle release|dev|t8 --url URL [--pair-helper PATH]
#   window_config.sh show   --bundle release|dev|t8
#   window_config.sh clear  --bundle release|dev|t8
set -eu

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

BUNDLE=""
URL=""
HELPER=""
CMD="${1:-}"
[ $# -ge 1 ] && shift
while [ $# -gt 0 ]; do
  case "$1" in
    --bundle) [ $# -ge 2 ] || usage; BUNDLE="$2"; shift 2 ;;
    --url) [ $# -ge 2 ] || usage; URL="$2"; shift 2 ;;
    --pair-helper) [ $# -ge 2 ] || usage; HELPER="$2"; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$BUNDLE" ] || usage

case "$BUNDLE" in
  release) DIR="$HOME/.mastermind/window" ;;
  dev)     DIR="$HOME/.mastermind/mmos_dev/window-dev" ;;
  t8)      DIR="$HOME/.mastermind/mmos_dev/window-dev-t8" ;;
  *) echo "window_config: unknown bundle '$BUNDLE' (release|dev|t8)" >&2; exit 2 ;;
esac

write_one() { # file content
  tmp="$1.tmp.$$"
  printf '%s\n' "$2" > "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$1"
}

case "$CMD" in
  write)
    [ -n "$URL" ] || { echo "window_config: --url is required for write" >&2; exit 2; }
    # The address must be loopback http with a real path (the server root '/'
    # opens a new empty thread), and must never carry a fragment: pairing
    # tokens do not belong in the config file.
    case "$URL" in
      http://127.0.0.1:*/?*|http://127.0.0.1/?*|http://localhost:*/?*|http://localhost/?*) ;;
      *) echo "window_config: refusing '$URL': must be http://127.0.0.1:<port>/<thread-path>" >&2; exit 1 ;;
    esac
    case "$URL" in
      *#*) echo "window_config: refusing a URL with a fragment (pairing tokens never belong in the config)" >&2; exit 1 ;;
    esac
    if [ -n "$HELPER" ]; then
      case "$HELPER" in
        /*) [ -x "$HELPER" ] || { echo "window_config: pair helper is not executable: $HELPER" >&2; exit 1; } ;;
        *) echo "window_config: --pair-helper must be an absolute path" >&2; exit 2 ;;
      esac
    fi
    mkdir -p "$DIR"
    chmod 700 "$DIR"
    write_one "$DIR/shell-url" "$URL"
    if [ -n "$HELPER" ]; then
      write_one "$DIR/pair-helper" "$HELPER"
    fi
    # With no --pair-helper given, an existing pair-helper file is kept.
    echo "wrote $DIR/shell-url (mode 0600)"
    if [ -f "$DIR/pair-helper" ]; then
      echo "pair helper: $DIR/pair-helper (mode 0600)"
    fi
    ;;
  show)
    if [ ! -d "$DIR" ]; then echo "no config directory: $DIR"; exit 1; fi
    for name in shell-url pair-helper; do
      f="$DIR/$name"
      if [ -f "$f" ]; then
        printf '%s mode=%s owner=%s -> %s\n' "$f" "$(stat -f '%Lp' "$f")" "$(stat -f '%u' "$f")" "$(cat "$f")"
      else
        printf '%s (absent)\n' "$f"
      fi
    done
    ;;
  clear)
    [ -d "$DIR" ] || { echo "no config directory: $DIR"; exit 0; }
    rm -f "$DIR/shell-url" "$DIR/pair-helper"
    echo "cleared $DIR"
    ;;
  *) usage ;;
esac
