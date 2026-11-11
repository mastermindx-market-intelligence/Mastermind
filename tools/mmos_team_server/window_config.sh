#!/bin/sh
# window_config.sh — write, inspect, check or clear the fixed per-user window
# config that the Mastermind OS window reads when no MM_SHELL_URL /
# MM_SHELL_URL_FILE environment variable is set (lane T8: the app a person
# opens from Finder or the Dock has no environment).
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
# the user, inside a mode-0700 non-symlink directory, or the window refuses
# them.
#
# Usage:
#   window_config.sh write --bundle release|dev|t8 --url URL [--pair-helper PATH] [--keep-pair-helper]
#   window_config.sh check --bundle release|dev|t8 --app <path to the app binary>
#   window_config.sh show   --bundle release|dev|t8
#   window_config.sh clear  --bundle release|dev|t8
#
# `write` without --pair-helper removes an existing pair-helper (the window
# must not keep minting pairing addresses a config edit meant to withdraw);
# pass --keep-pair-helper to preserve one. Address and helper are staged in
# mode-0600 temporaries under umask 077 — a trap removes them on any exit —
# and committed helper-first, so a crash between the two renames never
# leaves a fresh address beside a stale helper.
#
# `check` is one judge (panel repair M): it runs the app binary itself in
# `--check-window-config` mode, which uses exactly the loader a real launch
# uses (address file, helper file, helper trust walk, config-folder check)
# and prints one `ok`/`refused <code>` line per item. `show` prints only
# the scheme, host, port and path of a stored address (panel repair L); a
# line carrying userinfo, a query or a fragment is never echoed, and
# refusals name the reason only, never the value.
#
# Address shape (panel repair F/M): exactly scheme `http`, host
# `127.0.0.1`, an all-digit port 1..65535, no userinfo, no query, no
# fragment, no control character or newline, and a path that is not the
# server root, not `/pair` and not under it. The pair helper must itself be
# a regular non-group-writable file in a non-group-writable directory — the
# window runs it, so a path anyone else can rewrite is not a credential the
# config may name.
set -eu

usage() {
  cat >&2 <<'EOF'
usage: window_config.sh write --bundle release|dev|t8 --url URL [--pair-helper PATH] [--keep-pair-helper]
       window_config.sh check --bundle release|dev|t8 --app <path to the app binary>
       window_config.sh show   --bundle release|dev|t8
       window_config.sh clear  --bundle release|dev|t8
EOF
  exit 2
}

BUNDLE=""
URL=""
HELPER=""
KEEP_HELPER=""
APP=""
CMD="${1:-}"
[ $# -ge 1 ] && shift
while [ $# -gt 0 ]; do
  case "$1" in
    --bundle) [ $# -ge 2 ] || usage; BUNDLE="$2"; shift 2 ;;
    --url) [ $# -ge 2 ] || usage; URL="$2"; shift 2 ;;
    --pair-helper) [ $# -ge 2 ] || usage; HELPER="$2"; shift 2 ;;
    --keep-pair-helper) KEEP_HELPER=yes; shift ;;
    --app) [ $# -ge 2 ] || usage; APP="$2"; shift 2 ;;
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

refuse() { # reason (panel repair L: the reason only, never the value)
  echo "window_config: refusing the address: $1" >&2
  exit 1
}

case "$CMD" in
  write)
    [ -n "$URL" ] || { echo "window_config: --url is required for write" >&2; exit 2; }
    # Panel repair M: exact checks, not globs. Every refusal names the
    # reason only (panel repair L).
    case "$URL" in
      *[[:cntrl:]]*) refuse "a control character or newline is never part of an address" ;;
    esac
    case "$URL" in
      *@*) refuse "userinfo never belongs in the config" ;;
    esac
    case "$URL" in
      *token=*) refuse "a token parameter never belongs in the config" ;;
    esac
    case "$URL" in
      *\?*) refuse "a query never belongs in the config" ;;
    esac
    case "$URL" in
      *#*) refuse "a fragment (pairing tokens) never belongs in the config" ;;
    esac
    # Scheme exactly http, host exactly 127.0.0.1 (`localhost` is refused:
    # the server prints its address as 127.0.0.1 and the spellings must not
    # diverge), port all digits, path present and extracted exactly.
    rest=$(printf '%s\n' "$URL" | sed -n 's|^http://127\.0\.0\.1:\([0-9][0-9]*\)\(/.*\)$|\1 \2|p')
    if [ -z "$rest" ]; then
      case "$URL" in
        http://localhost:*|http://LOCALHOST:*)
          refuse "use the 127.0.0.1 literal (the server prints its address as 127.0.0.1)" ;;
        *) refuse "must be exactly http://127.0.0.1:<port>/<thread-path>" ;;
      esac
    fi
    port=${rest%% *}
    addr_path=${rest#* }
    port_num=$(printf '%s\n' "$port" | sed 's/^0*//')
    [ -n "$port_num" ] || port_num=0
    # Attack round: bound the length before any numeric test so an oversized
    # port gets the named refusal instead of a shell arithmetic error.
    if [ "${#port_num}" -gt 5 ] || [ "$port_num" -lt 1 ] || [ "$port_num" -gt 65535 ]; then
      refuse "the port must be between 1 and 65535"
    fi
    # Attack round: compare a lowercased copy so `/PAIR` disguises fail, and
    # refuse dot segments (raw or percent-encoded, either case) outright —
    # the app's url parser normalizes them, so `/a/../pair` would otherwise
    # open the pairing page as the configured "thread". A leading empty
    # segment (`//pair`) is refused for the same reason.
    low_path=$(printf '%s\n' "$addr_path" | tr 'A-Z' 'a-z')
    case "$low_path" in
      *..*|*%2e*)
        refuse "dot segments never belong in the config path" ;;
      //*|/|/pair|/pair/*)
        refuse "the server root and /pair belong to the pairing flow, never to the config" ;;
    esac
    if [ -n "$HELPER" ]; then
      case "$HELPER" in
        /*) ;;
        *) echo "window_config: --pair-helper must be an absolute path" >&2; exit 2 ;;
      esac
      case "$HELPER" in
        *..*) echo "window_config: refusing a pair-helper path with '..' in it" >&2; exit 1 ;;
      esac
      [ -f "$HELPER" ] || { echo "window_config: pair helper is not a regular file" >&2; exit 1; }
      [ ! -L "$HELPER" ] || { echo "window_config: refusing a symlinked pair helper" >&2; exit 1; }
      [ -x "$HELPER" ] || { echo "window_config: pair helper is not executable" >&2; exit 1; }
      helper_mode=$(stat -f '%Lp' "$HELPER")
      g=${helper_mode#?}; g=${g%?}
      o=${helper_mode#??}
      case "$g$o" in
        *[2367]*) echo "window_config: refusing a group- or other-writable pair helper (mode $helper_mode)" >&2; exit 1 ;;
      esac
      parent_mode=$(stat -f '%Lp' "$(dirname "$HELPER")")
      pg=${parent_mode#?}; pg=${pg%?}
      po=${parent_mode#??}
      case "$pg$po" in
        *[2367]*) echo "window_config: refusing a pair helper in a group- or other-writable directory (mode $parent_mode)" >&2; exit 1 ;;
      esac
    fi
    # Panel repair N: never write into a symlinked folder. The refusal runs
    # before mkdir/chmod so a planted symlink never has its target touched
    # (attack-round ordering fix); the post-chmod check stays for the race.
    [ ! -L "$DIR" ] || { echo "window_config: refusing to write into a symlinked config directory" >&2; exit 1; }
    mkdir -p "$DIR"
    chmod 700 "$DIR"
    [ ! -L "$DIR" ] || { echo "window_config: refusing to write into a symlinked config directory" >&2; exit 1; }
    # Panel repair F: stage both files first (umask 077, trap removes the
    # temporaries on any exit), then commit. A write without --pair-helper
    # removes an existing helper *before* committing the address, so a
    # window reading the config mid-write can never pair a new address
    # through a helper the edit meant to withdraw; --keep-pair-helper
    # preserves it. The helper rename lands before the address rename: a
    # crash between the two leaves at most the old address beside the new
    # helper, which only ever mints a fresh one-time address — never the
    # dangerous converse.
    umask 077
    url_tmp="$DIR/shell-url.tmp.$$"
    helper_tmp="$DIR/pair-helper.tmp.$$"
    trap 'rm -f "$url_tmp" "$helper_tmp"' EXIT HUP INT TERM
    printf '%s\n' "$URL" > "$url_tmp"
    if [ -n "$HELPER" ]; then
      printf '%s\n' "$HELPER" > "$helper_tmp"
    fi
    if [ -z "$HELPER" ] && [ "$KEEP_HELPER" != yes ] && [ -f "$DIR/pair-helper" ]; then
      rm -f "$DIR/pair-helper"
      removed_helper=yes
    fi
    if [ -n "$HELPER" ]; then
      mv "$helper_tmp" "$DIR/pair-helper"
    fi
    mv "$url_tmp" "$DIR/shell-url"
    trap - EXIT HUP INT TERM
    echo "wrote $DIR/shell-url (mode 0600)"
    if [ "${removed_helper:-}" = yes ]; then
      echo "removed $DIR/pair-helper (no --pair-helper; pass --keep-pair-helper to keep one)"
    elif [ -f "$DIR/pair-helper" ]; then
      echo "pair helper: $DIR/pair-helper (mode 0600)"
    fi
    ;;
  check)
    # Panel repair M: the app binary is the one judge; it prints one line
    # per item and exits 0 only when all pass. This tool adds nothing.
    [ -n "$APP" ] || { echo "window_config: --app <path to the app binary> is required for check" >&2; exit 2; }
    [ -x "$APP" ] || { echo "window_config: app binary is not executable: run it as the same user who owns the config" >&2; exit 2; }
    exec "$APP" --check-window-config
    ;;
  show)
    if [ ! -d "$DIR" ]; then echo "no config directory: $DIR"; exit 1; fi
    # Attack round: a symlinked config directory is never followed, not even
    # to display.
    if [ -L "$DIR" ]; then echo "window_config: refusing to show a symlinked config directory" >&2; exit 1; fi
    for name in shell-url pair-helper; do
      f="$DIR/$name"
      if [ -f "$f" ]; then
        printf '%s mode=%s owner=%s' "$f" "$(stat -f '%Lp' "$f")" "$(stat -f '%u' "$f")"
        line=$(cat "$f")
        # Panel repair L: print scheme, host, port and path only; anything
        # carrying userinfo, a query or a fragment is never echoed. One
        # port digit is as valid as five (attack-round fix).
        case "$line" in
          *@*|*\?*|*\#*)
            printf ' -> (not shown: carries a query, fragment or userinfo)\n' ;;
          http://127.0.0.1:[0-9]*/*)
            printf ' -> %s\n' "$line" ;;
          /*)
            printf ' -> %s\n' "$line" ;;
          *)
            printf ' -> (not shown: unrecognized line)\n' ;;
        esac
      else
        printf '%s (absent)\n' "$f"
      fi
    done
    ;;
  clear)
    [ -d "$DIR" ] || { echo "no config directory: $DIR"; exit 0; }
    # Attack round: never delete through a symlinked config directory.
    if [ -L "$DIR" ]; then echo "window_config: refusing to clear a symlinked config directory" >&2; exit 1; fi
    rm -f "$DIR/shell-url" "$DIR/pair-helper"
    echo "cleared $DIR"
    ;;
  *) usage ;;
esac
