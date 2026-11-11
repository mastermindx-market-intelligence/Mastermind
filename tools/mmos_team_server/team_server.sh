#!/bin/sh
# team_server.sh — install and run a Mastermind team T3 server (lane T6,
# PROGRAM_PLAN_V4 §11: headless, loopback-only, launchd-kept-alive, own home,
# separate from the Chairman's T3 Code app).
#
# Usage:
#   team_server.sh install  --root DIR --port N --label ID [--server-bin PATH]
#                           [--replace]
#   team_server.sh doctor --root DIR --label ID
#   team_server.sh start|stop|status|uninstall  --root DIR --label ID
#   team_server.sh selftest
#
# Reuses the guard logic of tools/mmos_dev/t3_dev.sh (sourced as a library via
# its T3_DEV_LIB_ONLY opt-in) instead of copying it. The pairing credential the
# server prints is captured to <root>/run/access.txt (mode 0600) and never
# printed, logged by this tool, or written into the plist. Route keys come from
# <root>/fabric.env (0600, written by seed_dev_home.py), sourced by the runner —
# never from the plist text.
set -u

SELFTEST_ONLY=0

die() { echo "team_server: $1" >&2; exit 1; }

# ---------- library reuse: t3_dev.sh guards (narrow opt-in) ----------
REPO_DIR=$(cd "$(dirname "$0")/../.." && pwd -P)
T3_DEV="$REPO_DIR/tools/mmos_dev/t3_dev.sh"
[ -f "$T3_DEV" ] || die "cannot find $T3_DEV"
T3_DEV_LIB_ONLY=1
# shellcheck disable=SC1090
. "$T3_DEV"
T3_DEV_LIB_ONLY=0
# t3_dev.sh guards reused below: realpath_of, check_home_safe (HOME_DIR),
# port_forbidden, port_busy. Its own DEV_ROOT/HOME_DIR are re-pointed per call.

REAL_T3_RESOLVED=""  # set below, after resolve_path exists

# Resolve a possibly-nonexistent path fully (symlinks resolved on the existing
# prefix, like os.path.realpath strict=False). Unlike realpath_of, this works
# for paths that do not exist yet (fresh roots, a HOME without ~/.t3).
PYTHON3_BIN=$(command -v python3 2>/dev/null || echo /usr/bin/python3)
resolve_path() {
  "$PYTHON3_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}
REAL_T3_RESOLVED=$(resolve_path "$HOME/.t3")

# Refuse a root that is, contains, or resolves (incl. symlinks) into ~/.t3,
# BEFORE any directory is created. Returns 1 (does not die: callers run this
# inside $( ) where die would only exit the subshell).
root_is_safe() {
  _rr=$(resolve_path "$1") || return 1
  [ -n "$_rr" ] || return 1
  [ "$_rr" != "$REAL_T3_RESOLVED" ] || return 1
  case "$_rr" in "$REAL_T3_RESOLVED"/*) return 1 ;; esac
  echo "$_rr"
}

label_valid() {
  case "$1" in
    *[!a-zA-Z0-9.-]*) return 1 ;;
  esac
  case "$1" in ""|.*|-*) return 1 ;; esac
  return 0
}

label_loaded() {
  launchctl print "gui/$(id -u)/$1" >/dev/null 2>&1
}

plist_dir() { echo "${TEAM_SERVER_LAUNCHAGENTS_DIR:-$HOME/Library/LaunchAgents}"; }

# ---------- shared option parsing ----------
COMMAND="${1:-}"
[ $# -gt 0 ] && shift
ROOT=""; PORT=""; LABEL=""; SERVER_BIN=""; REPLACE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT=${2:?}; shift 2 ;;
    --port) PORT=${2:?}; shift 2 ;;
    --label) LABEL=${2:?}; shift 2 ;;
    --server-bin) SERVER_BIN=${2:?}; shift 2 ;;
    --replace) REPLACE=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

cmd_selftest() {
  fail=0
  port_forbidden 3773 && echo "guard 3773 forbidden: ok" || { echo "guard 3773 forbidden: FAIL"; fail=1; }
  port_forbidden 3774 && echo "guard 3774 forbidden: ok" || { echo "guard 3774 forbidden: FAIL"; fail=1; }
  port_forbidden 3805 || echo "guard 3805 allowed: ok" || { echo "guard 3805 allowed: FAIL"; fail=1; }
  label_valid com.mastermind.t3-team && echo "label valid form: ok" || { echo "label valid form: FAIL"; fail=1; }
  label_valid "bad label;rm" || echo "label invalid refused: ok" || { echo "label invalid refused: FAIL"; fail=1; }
  ( root_is_safe "$HOME/.t3" ) >/dev/null 2>&1 && { echo "guard root=~/.t3 refuse: FAIL"; fail=1; } \
    || echo "guard root=~/.t3 refuse: ok"
  ( root_is_safe "$HOME/.t3/team" ) >/dev/null 2>&1 && { echo "guard root inside ~/.t3 refuse: FAIL"; fail=1; } \
    || echo "guard root inside ~/.t3 refuse: ok"
  TMPD="${TMPDIR:-/tmp}"
  ln -sfn "$HOME/.t3" "$TMPD/.t6-selftest-link.$$" 2>/dev/null
  ( root_is_safe "$TMPD/.t6-selftest-link.$$/team" ) >/dev/null 2>&1 \
    && { echo "guard symlink-into-~/.t3 refuse: FAIL"; fail=1; } \
    || echo "guard symlink-into-~/.t3 refuse: ok"
  rm -f "$TMPD/.t6-selftest-link.$$"
  [ -f "$T3_DEV" ] && echo "t3_dev library present: ok" || { echo "t3_dev library present: FAIL"; fail=1; }
  echo "selftest_fail=$fail"
  return $fail
}

require_root_label() {
  [ -n "$ROOT" ] || die "missing --root"
  [ -n "$LABEL" ] || die "missing --label"
  ROOT=$(root_is_safe "$ROOT") || die "refusing unsafe root: $ROOT (at/inside/resolves into $HOME/.t3)"
}

wait_http() {
  _port="$1"; _want="${2:-60}"; _i=0
  while [ "$_i" -lt "$_want" ]; do
    _code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$_port/" 2>/dev/null || echo 000)
    [ "$_code" = "200" ] && return 0
    _i=$((_i + 1)); sleep 1
  done
  return 1
}

# Capture the LAST complete pairing banner (never print it) into
# <root>/run/access.txt 0600. Each server start mints a fresh one-time token
# and launchd appends banners across restarts, so stale blocks must not win.
capture_access() {
  _log="$ROOT/run/server.log"; _acc="$ROOT/run/access.txt"
  _i=0
  while [ "$_i" -lt 20 ]; do
    awk '/^(Connection string|Token|Pairing URL):/ {
      blk = blk $0 "\n"
      if ($0 ~ /^Pairing URL:/) { last = blk; blk = "" }
    } END { printf "%s", last }' "$_log" > "$_acc" 2>/dev/null || true
    grep -q '^Pairing URL:' "$_acc" 2>/dev/null && break
    _i=$((_i + 1)); sleep 1
  done
  chmod 600 "$_acc" 2>/dev/null || true
}

cmd_install() {
  [ -n "$PORT" ] || die "missing --port"
  case "$PORT" in ''|*[!0-9]*) die "port must be an integer" ;; esac
  require_root_label
  label_valid "$LABEL" || die "invalid label: $LABEL"
  port_forbidden "$PORT" && die "port $PORT is reserved for the live T3 servers"
  # An install over this same label must --replace; boot it out BEFORE the
  # port-busy check so our own server does not count as a foreign occupant.
  if label_loaded "$LABEL" && [ "$REPLACE" -ne 1 ]; then
    die "label $LABEL is already loaded; pass --replace to replace it"
  fi
  PLIST="$(plist_dir)/$LABEL.plist"
  if [ -f "$PLIST" ] && [ "$REPLACE" -ne 1 ]; then
    die "plist $PLIST already exists; pass --replace to replace it"
  fi
  # One label per root: refuse a second plist (any label) pointing at this
  # root. Match the exact runner path, not a bare root substring (t3-team is a
  # prefix of t3-team-b and must not collide). Scan BOTH the plist dir and the
  # real ~/Library/LaunchAgents: an attacker (or a stray TEAM_SERVER_LAUNCH-
  # AGENTS_DIR override) must not hide a live root's plist from this scan
  # (attack a4 finding: install then mutates a served root for 90s).
  scan_dir_for_root() {
    _d="$1"
    [ -d "$_d" ] || return 0
    for _p in "$_d"/*.plist; do
      [ -f "$_p" ] || continue
      grep -q "<string>$ROOT/bin/server_runner.sh</string>" "$_p" 2>/dev/null || continue
      _pl=$(basename "$_p" .plist)
      [ "$_pl" = "$LABEL" ] || die "root already used by label $_pl ($_p); one label per root"
    done
  }
  scan_dir_for_root "$(plist_dir)"
  _def_la=$(resolve_path "$HOME/Library/LaunchAgents")
  [ "$_def_la" = "$(resolve_path "$(plist_dir)")" ] || scan_dir_for_root "$_def_la"
  # Boot out a previous job for this label before replacing (idempotent).
  if label_loaded "$LABEL"; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null; sleep 2
  fi
  port_busy "$PORT" && die "port $PORT is busy"
  # Hygiene and live-lock checks precede runtime selection: selecting a pack
  # must never obscure these existing protections or this root's writer state.
  if [ -n "$SERVER_BIN" ] && [ ! -x "$SERVER_BIN" ]; then
    die "server binary not executable: $SERVER_BIN"
  fi
  [ -f "$ROOT/fabric.env" ] || die "missing $ROOT/fabric.env; run tools/mmos_dev/t3/seed_dev_home.py with MMOS_T3_DEV_ROOT=$ROOT first"
  [ "$(stat -f '%Lp' "$ROOT/fabric.env")" = "600" ] || die "$ROOT/fabric.env must be mode 600"
  # Never mutate a root that is being served RIGHT NOW: its runner holds
  # <root>/run/home.lock across exec for the whole server lifetime. A second
  # install under any label (even with plists hidden from the scan above)
  # must die here, BEFORE runtime selection and the mkdir/cp/port-write below
  # (attack a4 finding: a hidden-plist install rewrote run/port on a live
  # root; a refused packed-runtime resolution must not mask this refusal).
  if ! "$PYTHON3_BIN" - "$ROOT" <<'PYLOCK'
import fcntl, os, sys
root = sys.argv[1]
try:
    fd = os.open(os.path.join(root, "run", "home.lock"), os.O_RDWR)
except FileNotFoundError:
    sys.exit(0)  # no lock file -> nothing is serving this root
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(1)  # held by a live server for this root
os.close(fd)
PYLOCK
  then
    die "root $ROOT is live under a running server (home.lock held); stop or uninstall it first"
  fi
  # A self-contained packed runtime is the default. An explicit --server-bin
  # is the emergency legacy rollback, not a second default source-tree path.
  if [ -z "$SERVER_BIN" ]; then
    SERVER_BIN=$("$PYTHON3_BIN" "$REPO_DIR/tools/mmos_team_server/node_install.py" resolve --root "$ROOT" --command serve) \
      || die "packed runtime unavailable; run node_install.py install and pack_server.mjs first, or explicitly supply --server-bin for rollback"
    "$PYTHON3_BIN" "$REPO_DIR/tools/mmos_team_server/node_install.py" resolve --root "$ROOT" --command node >/dev/null \
      || die "pinned Node receipt or executable is incomplete"
  fi
  [ -f "$SERVER_BIN" ] || die "server entrypoint does not exist: $SERVER_BIN"
  mkdir -p "$ROOT/home/userdata" "$ROOT/run" "$ROOT/bin" "$ROOT/config" "$ROOT/scratch-project" "$ROOT/claude-home"
  cp "$REPO_DIR/tools/mmos_team_server/server_runner.sh" "$ROOT/bin/server_runner.sh"
  cp "$REPO_DIR/tools/mmos_team_server/node_install.py" "$ROOT/bin/node_install.py"
  chmod 700 "$ROOT/bin/node_install.py"
  chmod 700 "$ROOT/bin/server_runner.sh"
  printf '%s\n' "$PORT" > "$ROOT/run/port"
  printf '%s\n' "$SERVER_BIN" > "$ROOT/config/server-bin"
  : > "$ROOT/run/server.log"; chmod 600 "$ROOT/run/server.log"
  mkdir -p "$(plist_dir)"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>$ROOT/bin/server_runner.sh</string>
    <string>$ROOT</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>WorkingDirectory</key><string>$ROOT/scratch-project</string>
  <key>StandardOutPath</key><string>$ROOT/run/server.log</string>
  <key>StandardErrorPath</key><string>$ROOT/run/server.log</string>
</dict>
</plist>
EOF
  chmod 644 "$PLIST"
  # Bootstrap from an empty environment: launchd snapshots the caller's env
  # into the job ("inherited environment"); env -i keeps provider keys from
  # riding into `launchctl print` and the server process.
  env -i /bin/launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null \
    || launchctl load -w "$PLIST" 2>/dev/null \
    || die "launchctl bootstrap failed for $LABEL"
  wait_http "$PORT" 90 || { launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null; die "server did not answer on 127.0.0.1:$PORT; see $ROOT/run/server.log"; }
  capture_access
  echo "INSTALLED label=$LABEL root=$ROOT port=$PORT server_bin=$SERVER_BIN"
  echo "pairing access saved to $ROOT/run/access.txt (mode 0600; not printed)"
}

cmd_start() {
  require_root_label
  PLIST="$(plist_dir)/$LABEL.plist"
  [ -f "$PLIST" ] || die "no plist for $LABEL at $PLIST; run install"
  PORT=$(cat "$ROOT/run/port" 2>/dev/null) || die "no port file; run install"
  if label_loaded "$LABEL"; then
    launchctl kickstart "gui/$(id -u)/$LABEL" || die "kickstart failed"
  else
    env -i /bin/launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST" 2>/dev/null || die "bootstrap failed"
  fi
  wait_http "$PORT" 90 || die "server did not answer on 127.0.0.1:$PORT"
  capture_access
  echo "STARTED label=$LABEL port=$PORT"
}

cmd_stop() {
  require_root_label
  if label_loaded "$LABEL"; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload -w "$(plist_dir)/$LABEL.plist" 2>/dev/null
  fi
  PORT=$(cat "$ROOT/run/port" 2>/dev/null || echo "")
  [ -n "$PORT" ] && ! port_busy "$PORT" && echo "STOPPED label=$LABEL port=$PORT free" && return 0
  [ -z "$PORT" ] && echo "STOPPED label=$LABEL" && return 0
  die "label booted out but port $PORT still busy (unknown owner)"
}

cmd_status() {
  require_root_label
  PORT=$(cat "$ROOT/run/port" 2>/dev/null || echo "?")
  echo "root=$ROOT"
  echo "label=$LABEL loaded=$(label_loaded "$LABEL" && echo yes || echo no)"
  _pid=""
  if label_loaded "$LABEL"; then
    _pid=$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null \
           | grep -E '^[[:space:]]*pid = [0-9]+' | head -1 | grep -oE '[0-9]+')
  fi
  echo "pid=${_pid:-none}"
  if [ "$PORT" != "?" ]; then
    _code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null || echo 000)
    echo "port=$PORT http_root=$_code"
    echo "listeners:"
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tail -n +2 || true
  else
    echo "port=none (not installed?)"
  fi
  [ -f "$ROOT/config/server-bin" ] && echo "server_bin=$(cat "$ROOT/config/server-bin")"
  [ -f "$ROOT/run/access.txt" ] && echo "access_file=$ROOT/run/access.txt (mode $(stat -f '%Lp' "$ROOT/run/access.txt"); not printed)"
}

cmd_doctor() {
  require_root_label
  label_valid "$LABEL" || die "invalid label: $LABEL"
  "$PYTHON3_BIN" "$REPO_DIR/tools/mmos_team_server/node_install.py" doctor \
    --root "$ROOT" --label "$LABEL"
}

cmd_uninstall() {
  require_root_label
  if label_loaded "$LABEL"; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload -w "$(plist_dir)/$LABEL.plist" 2>/dev/null
  fi
  PLIST="$(plist_dir)/$LABEL.plist"
  rm -f "$PLIST"
  echo "UNINSTALLED label=$LABEL (plist removed; root $ROOT left in place)"
}

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

case "$COMMAND" in
  install) cmd_install ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  doctor) cmd_doctor ;;
  uninstall) cmd_uninstall ;;
  selftest) cmd_selftest ;;
  *) usage ;;
esac
