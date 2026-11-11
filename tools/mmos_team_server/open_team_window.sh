#!/bin/sh
# Open the Mastermind OS dev window on one teammate's conversation on the team
# T3 server (127.0.0.1:3780). The window must already be paired once (see
# integrations/mmos/PROGRAM_PLAN_V4.md section 15). No credential is read,
# written or printed here: the file handed to the window holds only the
# thread address.
#
# MM_SHELL_URL_FILE (this script) beats MM_SHELL_URL, and both beat the fixed
# per-user config that a Finder/Dock launch uses (lane T8; write it with
# window_config.sh). The window re-pairs itself only through that fixed
# config's pair-helper, so this env-launched flow keeps its old behaviour.
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
[ -x "$APP" ] || { echo "dev window not built: $APP" >&2; exit 1; }
mkdir -p "$WORK"; chmod 700 "$WORK"
FILE="$WORK/thread-$1.txt"
"$PY" -I -c 'import json,os,sys
urls, want, out = sys.argv[1:4]
m = [t for t in json.load(open(urls))["teammates"] if t["instanceId"] == want]
if not m: sys.exit("no teammate with instance id " + want)
url = m[0]["url"]
if not url.startswith("http://127.0.0.1:"): sys.exit("refusing a non-loopback address")
if os.path.lexists(out): os.remove(out)
with os.fdopen(os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
    f.write(url + "\n")' "$URLS" "$1" "$FILE"
MM_SHELL_URL_FILE="$FILE" MMOS_DEV_ROOT="${MMOS_DEV_ROOT:-$HOME/.mastermind/mmos_dev}" \
  nohup "$APP" >"$WORK/window.log" 2>&1 &
echo $! >"$WORK/app.pid"
echo "opened $1 (pid $!)"
