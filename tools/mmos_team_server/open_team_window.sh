#!/bin/sh
# Open the Mastermind OS dev window on one teammate's conversation on the team
# T3 server (127.0.0.1:3780). The window must already be paired once (see
# integrations/mmos/PROGRAM_PLAN_V4.md section 15). No credential is read,
# written or printed here: the file handed to the window holds only the
# thread address.
#
# MM_SHELL_URL_FILE (this script) beats MM_SHELL_URL, and both beat the fixed
# per-user config that a Finder/Dock launch uses (lane T8; write it with
# window_config.sh). The env URL decides only the address this launch opens;
# the pairing watchdog is decided by the fixed config alone, and it is
# started whenever that config names a pair-helper — including for an
# env-launched window like this one. Because the window clears the helper's
# environment, WINDOW_PAIR_T3_BIN / WINDOW_PAIR_T3_HOME cannot aim an
# env-launched window's re-pairing at a dev server; the supported way is a
# small wrapper script that exports those two variables and execs
# window_pair_helper.sh, named in the fixed config via
# `window_config.sh write --pair-helper <wrapper>`.
set -eu
ROOT="${MMOS_TEAM_ROOT:-$HOME/.mastermind/t3-team}"
URLS="$ROOT/run/team_urls.json"
APP="${MMOS_DEV_APP:-/Volumes/Mastermind/build-cache/t3-t1w-cargo-target/debug/bundle/macos/Mastermind OS Dev.app/Contents/MacOS/mastermind-os}"
WORK="${MMOS_TEAM_WINDOW_DIR:-$HOME/.mastermind/mmos_dev/team-window}"
PY="${MMOS_PYTHON:-/usr/bin/python3}"

[ $# -eq 1 ] || { echo "usage: $0 <instance-id> | --list" >&2; exit 2; }
[ -f "$URLS" ] || { echo "no roster file: $URLS (run team_roster.py apply)" >&2; exit 1; }
if [ "$1" = "--list" ]; then
  exec "$PY" -I -c 'import json,sys
for t in json.load(open(sys.argv[1]))["teammates"]: print(t["instanceId"], "-", t["name"])' "$URLS"
fi
# Panel repair O: the instance id becomes part of a file name, so both the
# typed id and the roster entry's own id must be one word of
# [A-Za-z0-9._-] with no `..`.
case "$1" in
  ""|*[!A-Za-z0-9._-]*) echo "instance id must match ^[A-Za-z0-9._-]+\$: refusing" >&2; exit 2 ;;
  *..*) echo "instance id must not contain '..': refusing" >&2; exit 2 ;;
esac
[ -x "$APP" ] || { echo "dev window not built: $APP" >&2; exit 1; }
mkdir -p "$WORK"; chmod 700 "$WORK"
FILE="$WORK/thread-$1.txt"
"$PY" -I -c 'import json, os, re, sys
from urllib.parse import urlsplit
urls, want, out = sys.argv[1:4]
m = [t for t in json.load(open(urls))["teammates"] if t["instanceId"] == want]
if not m: sys.exit("no teammate with instance id " + want)
entry_id = m[0]["instanceId"]
if not re.fullmatch(r"[A-Za-z0-9._-]+", entry_id) or ".." in entry_id:
    sys.exit("roster entry id is not a safe file name; refusing")
url = m[0]["url"]
# Panel repair O: the roster address is parsed, not prefix-matched — the
# same exact rule window_config.sh applies (panel repair M): scheme http,
# host exactly 127.0.0.1, a real port, no userinfo, no query, no fragment,
# and a path that is neither the root nor /pair nor under it.
p = urlsplit(url)
safe = (
    p.scheme == "http"
    and p.hostname == "127.0.0.1"
    and p.port is not None and 1 <= p.port <= 65535
    and p.username is None and p.password is None
    and not p.query and not p.fragment
    and p.path.startswith("/") and p.path not in ("/", "/pair")
    and not p.path.startswith("/pair/")
)
if not safe: sys.exit("refusing a roster address that is not exactly http://127.0.0.1:<port>/<thread-path>")
if os.path.lexists(out): os.remove(out)
with os.fdopen(os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
    f.write(url + "\n")' "$URLS" "$1" "$FILE"
MM_SHELL_URL_FILE="$FILE" MMOS_DEV_ROOT="${MMOS_DEV_ROOT:-$HOME/.mastermind/mmos_dev}" \
  nohup "$APP" >"$WORK/window.log" 2>&1 &
echo $! >"$WORK/app.pid"
echo "opened $1 (pid $!)"
