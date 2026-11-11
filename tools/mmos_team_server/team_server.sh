#!/bin/sh
# team_server.sh — install and run a Mastermind team T3 server (lane T6,
# PROGRAM_PLAN_V4 §11: headless, loopback-only, launchd-kept-alive, own home,
# separate from the Chairman's T3 Code app).
#
# Usage:
#   team_server.sh install  --root DIR --port N --label ID [--server-bin PATH]
#                           [--replace]
#   team_server.sh doctor --root DIR --label ID
#   team_server.sh start|stop|status|capture|uninstall  --root DIR --label ID
#   team_server.sh selftest
#
# Reuses the guard logic of tools/mmos_dev/t3_dev.sh (sourced as a library via
# its T3_DEV_LIB_ONLY opt-in) instead of copying it. The pairing credential the
# server prints is captured to <root>/run/access.txt (mode 0600) and never
# printed, logged by this tool, or written into the plist. Route keys come from
# <root>/fabric.env (0600, written by seed_dev_home.py), sourced by the runner —
# never from the plist text.
set -u
# Everything this tool creates (root subdirs, port file, server.log,
# access.txt) is private state or credential-bearing: create it 0700/0600
# from the start instead of chmod-racing after a world-readable write
# (attack findings 8 and 9).
umask 077

SELFTEST_ONLY=0

die() { echo "team_server: $1" >&2; exit 1; }

# ---------- library reuse: t3_dev.sh guards (narrow opt-in) ----------
REPO_DIR=$(cd "$(dirname "$0")/../.." && pwd -P)
T3_DEV="$REPO_DIR/tools/mmos_dev/t3_dev.sh"
[ -f "$T3_DEV" ] || die "cannot find $T3_DEV"
# Item 13 / F27: the interpreter that guards every check is chosen by
# explicit absolute path BEFORE the library is sourced — never through the
# caller's PATH (whoever controls PATH would pick the program that validates
# the runtime). Set it for the library's port_busy too.
PYTHON3_BIN="${PYTHON3_BIN:-}"
if [ -z "$PYTHON3_BIN" ]; then
  if [ -x /opt/homebrew/bin/python3.12 ]; then PYTHON3_BIN=/opt/homebrew/bin/python3.12
  elif [ -x /usr/bin/python3 ]; then PYTHON3_BIN=/usr/bin/python3
  fi
fi
case "$PYTHON3_BIN" in
  /*) [ -f "$PYTHON3_BIN" ] && [ -x "$PYTHON3_BIN" ] \
    || die "python3 interpreter missing or not executable: ${PYTHON3_BIN:-none found} (set PYTHON3_BIN to an absolute python3)" ;;
  *) die "PYTHON3_BIN must be an absolute path, got: $PYTHON3_BIN" ;;
esac
# Panel R8: after F27 pinned python3 because "whoever controls PATH would
# pick the program that validates the runtime", launchctl/curl/lsof/stat/ps
# were still PATH-resolved — a fake `curl` printing 200 forced INSTALLED with
# no server started. Absolute paths; the MMOS_*_BIN seams exist for the test
# harness's fake launchd only.
LAUNCHCTL="${MMOS_LAUNCHCTL_BIN:-/bin/launchctl}"
CURL="${MMOS_CURL_BIN:-/usr/bin/curl}"
LSOF="${MMOS_LSOF_BIN:-/usr/sbin/lsof}"
STAT="${MMOS_STAT_BIN:-/usr/bin/stat}"
PS_BIN="${MMOS_PS_BIN:-/bin/ps}"
for _tool in LAUNCHCTL CURL LSOF STAT PS_BIN; do
  eval "_val=\$$_tool"
  case "$_val" in /*) ;; *) die "$_tool must be an absolute path, got: $_val" ;; esac
done
T3_DEV_LIB_ONLY=1
# shellcheck disable=SC1090
. "$T3_DEV"
T3_DEV_LIB_ONLY=0
# t3_dev.sh redefines die() with its own prefix; re-assert ours so this
# tool's refusals are attributed correctly (attack finding 14).
die() { echo "team_server: $1" >&2; exit 1; }
# t3_dev.sh guards reused below: realpath_of, check_home_safe (HOME_DIR),
# port_forbidden, port_busy, canonical_port. Its own DEV_ROOT/HOME_DIR are
# re-pointed per call.

# Resolve a possibly-nonexistent path fully (symlinks resolved on the existing
# prefix, like os.path.realpath strict=False). Unlike realpath_of, this works
# for paths that do not exist yet (fresh roots, a HOME without ~/.t3).
resolve_path() {
  "$PYTHON3_BIN" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}
REAL_T3_RESOLVED=$(resolve_path "$HOME/.t3")
[ -n "$REAL_T3_RESOLVED" ] || die "cannot resolve $HOME/.t3 (realpath of HOME failed)"

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
  "$LAUNCHCTL" print "gui/$(id -u)/$1" >/dev/null 2>&1
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
  # F9: the old `port_forbidden 3805 || echo ok || { FAIL }` could never
  # fail — the middle echo always succeeded, so a broken guard passed
  # selftest. Each allowed/refused guard is now an if-test of the guard
  # itself. Same for label_valid.
  if port_forbidden 3805; then echo "guard 3805 allowed: FAIL"; fail=1; else echo "guard 3805 allowed: ok"; fi
  label_valid com.mastermind.t3-team && echo "label valid form: ok" || { echo "label valid form: FAIL"; fail=1; }
  if label_valid "bad label;rm"; then echo "label invalid refused: FAIL"; fail=1; else echo "label invalid refused: ok"; fi
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
  # Every command that builds a plist path from $LABEL must go through this
  # check: an unvalidated label reaches rm -f, launchctl bootstrap and the
  # plist heredoc write (attack finding 2).
  label_valid "$LABEL" || die "invalid label: $LABEL"
  [ -L "$ROOT" ] && die "refusing symlinked root: $ROOT"
  ROOT=$(root_is_safe "$ROOT") || die "refusing unsafe root: $ROOT (at/inside/resolves into $HOME/.t3)"
}

require_curl() {
  # Attack finding 9: a missing curl made wait_http spin its whole window and
  # report "server did not answer" while the server was healthy the entire
  # time (and then got taken down). Name the prerequisite before launchd is
  # touched.
  [ -x "$CURL" ] \
    || die "curl missing or not executable: $CURL — required to probe the server port; install curl or fix PATH"
}

wait_http() {
  _port="$1"; _want="${2:-60}"; _i=0
  while [ "$_i" -lt "$_want" ]; do
    # F20: on a connection failure curl prints 000 AND exits non-zero, so
    # `|| echo 000` produced "000000". Capture, then default only an empty
    # result.
    _code=$("$CURL" -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$_port/" 2>/dev/null) || _code=""
    [ -n "$_code" ] || _code=000
    [ "$_code" = "200" ] && return 0
    _i=$((_i + 1)); sleep 1
  done
  return 1
}

# One live HTTP-200 probe of a recorded port (used to prove a server is
# actually serving before its log is trusted — attack finding 5).
port_answered() {
  _p="$1"
  canonical_port "$_p" >/dev/null 2>&1 || return 1
  _code=$("$CURL" -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$_p/" 2>/dev/null) || _code=""
  [ -n "$_code" ] || _code=000
  [ "$_code" = "200" ]
}

# The pid launchd's job for LABEL is currently running, if any.
job_pid() {
  "$LAUNCHCTL" print "gui/$(id -u)/$1" 2>/dev/null \
    | grep -E '^[[:space:]]*pid = [0-9]+' | head -1 | grep -oE '[0-9]+'
}

# True when $1's parent chain (bounded walk) includes $2 — server workers
# spawned by the job count as the job; an unrelated pid does not.
# The walk verdict is cached per (child, ancestor) pair: wait_ours asks the
# same question up to 180 times and each ps spawn costs ~30 ms; the relation
# only changes when one of the two pids dies — and then so does the pair.
_pid_desc_cache=""
pid_descendant_of() {
  _child="$1"; _anc="$2"
  [ "$_child" = "$_anc" ] && return 0
  case "$_pid_desc_cache" in
    "$_child|$_anc|no")  return 1 ;;
    "$_child|$_anc|yes") return 0 ;;
  esac
  _c="$_child"; _hops=0
  _verdict=no
  while [ -n "$_c" ] && [ "$_c" != "1" ] && [ "$_c" != "0" ] && [ "$_hops" -lt 12 ]; do
    _c=$("$PS_BIN" -o ppid= -p "$_c" 2>/dev/null | tr -d ' ')
    _hops=$((_hops + 1))
    if [ "$_c" = "$_anc" ]; then _verdict=yes; break; fi
  done
  _pid_desc_cache="$_child|$_anc|$_verdict"
  [ "$_verdict" = "yes" ]
}

# Panel R4: an HTTP-200 answer proves this root's server ONLY when the
# listener pid is the launchd job's pid or one of its descendants. A foreign
# same-user listener that grabbed the port (before or after the port_busy
# pre-check) — or a crash-looping job beside one — must never be reported
# INSTALLED, healthy or capturable.
# Cost note: a FULL lsof scan costs >1 s on a loaded machine, and wait_ours
# asks up to 180 times. The fast path asks only the job's own pid (~0.1 s);
# the full scan runs at most once per (job pid, port) — a negative verdict
# only repeats when the job pid changes (respawn) or the port does.
_answer_full_cache=""
answer_ours() {
  _p="$1"; _l="$2"
  port_answered "$_p" || return 1
  _jp=$(job_pid "$_l")
  [ -n "$_jp" ] || return 1
  # fast path: the job's own process holds the LISTEN socket
  if [ -n "$("$LSOF" -a -p "$_jp" -tP -iTCP:"$_p" -sTCP:LISTEN -n 2>/dev/null)" ]; then
    return 0
  fi
  # slow path: a worker child of the job listens — full scan, verdict cached
  case "$_answer_full_cache" in
    "$_jp|$_p|foreign") return 1 ;;
  esac
  for _lp in $("$LSOF" -tP -iTCP:"$_p" -sTCP:LISTEN -n 2>/dev/null); do
    pid_descendant_of "$_lp" "$_jp" && return 0
  done
  _answer_full_cache="$_jp|$_p|foreign"
  return 1
}

# wait_http, but the 200 must come from THIS label's job (panel R4).
wait_ours() {
  _p="$1"; _l="$2"; _i=0; _w="$3"
  while [ "$_i" -lt "$_w" ]; do
    answer_ours "$_p" "$_l" && return 0
    _i=$((_i + 1)); sleep 1
  done
  return 1
}

# Emit the last complete pairing banner from stdin (never print it elsewhere).
banner_filter() {
  awk '/^(Connection string|Token|Pairing URL):/ {
    blk = blk $0 "\n"
    if ($0 ~ /^Pairing URL:/) { last = blk; blk = "" }
  } END { printf "%s", last }'
}

# Capture the LIVE pairing banner (never print it) into
# <root>/run/access.txt 0600. Each server start mints a fresh one-time token
# and launchd APPENDS banners across restarts. After install/restart the live
# banner is the first one appended AFTER this call begins — the previous one
# in the log is a dead token (attack finding 1). But `start` on an
# already-running server appends nothing (kickstart does not bounce a healthy
# job): then the live token is the last complete banner in the whole log —
# and that fallback is sound ONLY while this label's server is verifiably
# running (label loaded AND the recorded port answering HTTP 200, attack
# finding 5: on a stopped server the last logged banner is a DEAD one-time
# token and must never be installed as the credential).
# The existing access.txt is replaced only when a banner was actually found,
# so a failed capture can never truncate the live credential away.
# F11/F29: capture returns 0 on success and 1 when no complete banner was
# found — the caller decides what that means (a server that is up must not
# be reported as a failed install step). The mv is checked and a directory
# in place of the credential file is refused, not silently swallowed.
capture_access() {
  _log="$ROOT/run/server.log"; _acc="$ROOT/run/access.txt"; _tmp="$_acc.new"
  _off=$("$STAT" -f%z "$_log" 2>/dev/null || echo 0)
  rm -f "$_tmp"
  _i=0
  while [ "$_i" -lt 20 ]; do
    tail -c +"$((_off + 1))" "$_log" 2>/dev/null | banner_filter > "$_tmp" 2>/dev/null || true
    grep -q '^Pairing URL:' "$_tmp" 2>/dev/null && break
    _i=$((_i + 1)); sleep 1
  done
  if ! grep -q '^Pairing URL:' "$_tmp" 2>/dev/null; then
    # nothing new was appended while waiting. Fall back to the whole log ONLY
    # when this label's job is verifiably the server answering right now
    # (attack finding 5 + panel R4: loaded + answered is not enough — the
    # listener pid must be this job's pid or a descendant).
    _cport=$(cat "$ROOT/run/port" 2>/dev/null || echo "")
    if answer_ours "$_cport" "$LABEL"; then
      banner_filter < "$_log" > "$_tmp" 2>/dev/null || true
      grep -q '^Pairing URL:' "$_tmp" 2>/dev/null || { rm -f "$_tmp"; return 1; }
    else
      rm -f "$_tmp"; return 1
    fi
  fi
  # umask 077 made the temp 0600; a chmod failure here is a live credential
  # sitting world-readable — fatal, never swallowed (attack finding 9).
  chmod 600 "$_tmp" 2>/dev/null || { rm -f "$_tmp"; die "cannot secure $_acc"; }
  [ -d "$_acc" ] && { rm -f "$_tmp"; die "$_acc exists as a directory; move it away"; }
  mv "$_tmp" "$_acc" 2>/dev/null || { rm -f "$_tmp"; die "cannot install $_acc"; }
  return 0
}

# F17: small config files (run/port, config/server-bin) are written to a
# temp and renamed into place, so a kill mid-write can never leave a partial
# value for the runner to exec with.
atomic_write() {
  _f="$1"; _c="$2"; _t="$_f.new"
  [ -d "$_f" ] && die "$_f exists as a directory; move it away"
  rm -f "$_t" || die "cannot clear stale temp: $_t"
  printf '%s\n' "$_c" > "$_t" || { rm -f "$_t"; die "cannot write $_f"; }
  mv "$_t" "$_f" || { rm -f "$_t"; die "cannot install $_f"; }
}

# True when no live server holds <root>/run/home.lock (attack finding 8:
# `stop` uses the same probe `install` uses, so "the server is down" is
# always verified, never asserted from a missing file).
root_lock_free() {
  "$PYTHON3_BIN" - "$1" <<'PYLOCK'
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
}

cmd_install() {
  [ -n "$PORT" ] || die "missing --port"
  # F10: canonical decimal only. A leading zero ("03773") passed the old
  # integer check while curl/nc/Node all stripped it — installing straight
  # onto a live T3 server's port.
  canonical_port "$PORT" \
    || die "port must be a canonical decimal integer 1024..65535 without leading zero, got: $PORT"
  require_root_label
  label_valid "$LABEL" || die "invalid label: $LABEL"
  port_forbidden "$PORT" && die "port $PORT is reserved for the live T3 servers"
  require_curl
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
      # -F: $ROOT is data, never a regex. A root containing `[` made grep exit
      # 2 (skip the plist); `.*` false-matched a different root (attack finding 3).
      grep -qF "<string>$ROOT/bin/server_runner.sh</string>" "$_p" 2>/dev/null || continue
      _pl=$(basename "$_p" .plist)
      [ "$_pl" = "$LABEL" ] || die "root already used by label $_pl ($_p); one label per root"
    done
  }
  scan_dir_for_root "$(plist_dir)"
  _def_la=$(resolve_path "$HOME/Library/LaunchAgents")
  [ "$_def_la" = "$(resolve_path "$(plist_dir)")" ] || scan_dir_for_root "$_def_la"
  # Panel R5: --server-bin is the documented rollback path, and the runner
  # still requires config/python3-path — only runbook step 3
  # (node_install.py install) writes it. Refuse up front, naming step 3,
  # instead of installing a job that crash-loops at runner exit 78 with a
  # printed recovery ("re-run install") that cannot fix it.
  if [ -n "$SERVER_BIN" ]; then
    _py3=""
    if [ -s "$ROOT/config/python3-path" ]; then
      _py3=$(head -1 "$ROOT/config/python3-path" 2>/dev/null)
    fi
    case "$_py3" in
      /*) [ -f "$_py3" ] && [ -x "$_py3" ] || _py3="" ;;
      *) _py3="" ;;
    esac
    [ -n "$_py3" ] || die "--server-bin refused: $ROOT/config/python3-path is missing or invalid — the runner would crash-loop at exit 78. Runbook step 3 (node_install.py install) records it, and its repair branch re-records it; run step 3, then re-run this command"
  fi
  # LOW3 (panel): every static refusal fires BEFORE the live label is booted
  # out, so a refused install no longer takes a previously healthy server
  # down. port_busy may fire on OUR OWN running job — attribute the holder
  # first; only a holder that is not this label's job refuses.
  if port_busy "$PORT"; then
    if answer_ours "$PORT" "$LABEL"; then
      : # our own job holds the port; the --replace bootout below stops it
    else
      die "port $PORT is busy"
    fi
  fi
  # Hygiene and live-lock checks precede runtime selection: selecting a pack
  # must never obscure these existing protections or this root's writer state.
  if [ -n "$SERVER_BIN" ] && [ ! -x "$SERVER_BIN" ]; then
    die "server binary not executable: $SERVER_BIN"
  fi
  [ -f "$ROOT/fabric.env" ] || die "missing $ROOT/fabric.env; run tools/mmos_dev/t3/seed_dev_home.py with MMOS_T3_DEV_ROOT=$ROOT first"
  [ "$("$STAT" -f '%Lp' "$ROOT/fabric.env")" = "600" ] || die "$ROOT/fabric.env must be mode 600"
  # Attack a4: never mutate a root that is being served RIGHT NOW — its
  # runner holds <root>/run/home.lock across exec for the whole server
  # lifetime. This stays BEFORE runtime selection so a refused packed-runtime
  # resolution can never mask it. LOW3 adds only attribution: the one holder
  # that may pass is THIS label's own job, which the --replace bootout below
  # stops; every other holder (bare process, hidden other-label job) refuses.
  if ! root_lock_free "$ROOT"; then
    _holder_pid=$("$LSOF" -t "$ROOT/run/home.lock" 2>/dev/null | head -1)
    _ours=0
    if [ -n "$_holder_pid" ] && label_loaded "$LABEL"; then
      _jp=$(job_pid "$LABEL")
      if [ -n "$_jp" ] && { [ "$_holder_pid" = "$_jp" ] || pid_descendant_of "$_holder_pid" "$_jp"; }; then
        _ours=1
      fi
    fi
    if [ "$_ours" -ne 1 ]; then
      die "root $ROOT is live under a running server (home.lock held); stop or uninstall it first"
    fi
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
  # install (including the --server-bin rollback path, which skips the Python
  # installer's own validation) applies the same root rule the installer does:
  # an existing root must be a real 0700 directory we own (attack finding 11).
  if [ -e "$ROOT" ]; then
    [ -d "$ROOT" ] || die "root is not a directory: $ROOT"
    [ "$("$STAT" -f '%Lp' "$ROOT")" = "700" ] \
      || die "root must be mode 0700 (chmod 700 $ROOT); it holds fabric.env, logs and thread state"
  fi
  # mkdir -p follows symlinked subdirs; a pre-planted home -> /tmp/victim link
  # would let the copy/port-write below land outside the root (attack finding
  # 10). Refuse any symlink among the subdirs we create or write through.
  for _d in home home/userdata run bin config scratch-project claude-home; do
    [ -L "$ROOT/$_d" ] && die "refusing symlinked subdir: $ROOT/$_d"
  done
  [ -L "$ROOT/fabric.env" ] && die "refusing symlinked fabric.env: $ROOT/fabric.env"
  # LOW10 (panel): sibling files got symlink checks; these in-run files did
  # not — a planted link at run/server.log would send the truncate/chmod and
  # the banner reads through it, run/port likewise the port reads/writes.
  for _f in run/server.log run/port run/access.txt run/home.lock; do
    [ -L "$ROOT/$_f" ] && die "refusing symlinked $ROOT/$_f (planted link would redirect a write/read through it)"
  done
  # Boot out a previous job for this label before replacing (idempotent) —
  # AFTER every static refusal above (LOW3). The a4 pre-check above let this
  # job's lock pass on the promise this bootout stops it, so re-verify: if
  # anything still holds the lock, refuse before the first mutation rather
  # than racing a live server.
  if label_loaded "$LABEL"; then
    "$LAUNCHCTL" bootout "gui/$(id -u)/$LABEL" 2>/dev/null; sleep 2
  fi
  if ! root_lock_free "$ROOT"; then
    die "root $ROOT is still locked after booting out $LABEL (home.lock held); the server is still shutting down — wait a moment and re-run"
  fi
  # Pre-existing owned subdirs (a legacy root's 0755 home/ run/ bin/) are
  # tightened to 0700, mirroring the installer's owned-subdir rule; the ROOT
  # itself is never auto-tightened — that stays the operator's explicit act.
  for _d in home home/userdata run bin config scratch-project claude-home; do
    if [ -d "$ROOT/$_d" ]; then
      chmod 700 "$ROOT/$_d" || die "cannot tighten $ROOT/$_d to 0700"
    fi
  done
  mkdir -p "$ROOT/home/userdata" "$ROOT/run" "$ROOT/bin" "$ROOT/config" "$ROOT/scratch-project" "$ROOT/claude-home" \
    || die "cannot create root subdirectories under $ROOT"
  # F18: an unchecked cp left the plist pointing at a missing runner and
  # surfaced 90 s later as "server did not answer". Every copy is checked.
  cp "$REPO_DIR/tools/mmos_team_server/server_runner.sh" "$ROOT/bin/server_runner.sh" \
    || die "cannot copy server_runner.sh into $ROOT/bin"
  cp "$REPO_DIR/tools/mmos_team_server/node_install.py" "$ROOT/bin/node_install.py" \
    || die "cannot copy node_install.py into $ROOT/bin"
  chmod 700 "$ROOT/bin/node_install.py" || die "cannot chmod $ROOT/bin/node_install.py"
  chmod 700 "$ROOT/bin/server_runner.sh" || die "cannot chmod $ROOT/bin/server_runner.sh"
  # F17: temp+rename so a kill cannot leave a partial port or server-bin.
  atomic_write "$ROOT/run/port" "$PORT"
  atomic_write "$ROOT/config/server-bin" "$SERVER_BIN"
  : > "$ROOT/run/server.log" || die "cannot truncate $ROOT/run/server.log"
  chmod 600 "$ROOT/run/server.log" || die "cannot chmod $ROOT/run/server.log"
  mkdir -p "$(plist_dir)"
  # LOW4 (panel): write the plist to a private temp and rename it into place
  # — a kill mid-heredoc can no longer leave a partial plist on disk (or in
  # launchd's hands). umask 077 keeps the temp private until the chmod.
  PLIST_TMP="$(plist_dir)/.$LABEL.plist.tmp.$$"
  cat > "$PLIST_TMP" <<EOF
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
  chmod 644 "$PLIST_TMP"
  mv -f "$PLIST_TMP" "$PLIST" || { rm -f "$PLIST_TMP"; die "cannot publish plist $PLIST"; }
  # Bootstrap from an empty environment: launchd snapshots the caller's env
  # into the job ("inherited environment"); env -i keeps provider keys from
  # riding into `launchctl print` and the server process.
  env -i "$LAUNCHCTL" bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null \
    || "$LAUNCHCTL" load -w "$PLIST" 2>/dev/null \
    || die "launchctl bootstrap failed for $LABEL"
  # F15/F29: separate the two failure kinds. A server that answered is never
  # a failed install step (banner capture may legitimately miss); a server
  # that never answered gets a cleanup whose OWN result is checked and
  # reported truthfully.
  # 180 s, not 90: the first boot after moving receipts runs the state-DB
  # migrations (the real root carries a large existing DB); measured first
  # boots on a busy machine exceed 90 s while remaining perfectly healthy.
  # Panel R4: the 200 must come from THIS label's job (listener pid = job pid
  # or a descendant), not from any process that grabbed the port.
  if ! wait_ours "$PORT" "$LABEL" 180; then
    _why="server did not answer on 127.0.0.1:$PORT"
    if port_answered "$PORT"; then
      _jp=$(job_pid "$LABEL")
      _lp=$("$LSOF" -tP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1)
      _why="port $PORT answered HTTP 200 from pid ${_lp:-not identified}, which is NOT label $LABEL's job (job pid ${_jp:-none}) — another process is serving this port"
    fi
    "$LAUNCHCTL" bootout "gui/$(id -u)/$LABEL" 2>/dev/null
    sleep 1
    if label_loaded "$LABEL"; then
      die "$_why and cleanup FAILED: label $LABEL is STILL LOADED (KeepAlive will crash-loop it) — run: launchctl bootout gui/$(id -u)/$LABEL — then see $ROOT/run/server.log"
    fi
    die "$_why; the label was unloaded; see $ROOT/run/server.log"
  fi
  if capture_access; then
    echo "INSTALLED label=$LABEL root=$ROOT port=$PORT server_bin=$SERVER_BIN"
    echo "pairing access saved to $ROOT/run/access.txt (mode 0600; not printed)"
  else
    # F29: the server is up and answering; a missing banner is not a failed
    # install. Say it plainly and name the recovery command.
    echo "INSTALLED label=$LABEL root=$ROOT port=$PORT server_bin=$SERVER_BIN"
    echo "pairing access was NOT captured (no complete banner in $ROOT/run/server.log); to retry: $0 capture --root $ROOT --label $LABEL"
  fi
}

cmd_capture() {
  require_root_label
  [ -f "$ROOT/run/server.log" ] || die "no $ROOT/run/server.log; run install first"
  capture_access \
    && echo "pairing access saved to $ROOT/run/access.txt (mode 0600; not printed)" \
    || die "no complete live pairing banner: nothing new in $ROOT/run/server.log and this label's job is not verified serving (port answered by the job's own pid). A stopped server's logged banner is a DEAD one-time token and is never saved; start the server, then retry"
}

cmd_start() {
  require_root_label
  PLIST="$(plist_dir)/$LABEL.plist"
  [ -f "$PLIST" ] || die "no plist for $LABEL at $PLIST; run install"
  PORT=$(cat "$ROOT/run/port" 2>/dev/null) || die "no port file; run install"
  # F21: an empty or non-canonical port file must refuse now, not spin for
  # 90 s inside wait_http (the old `[ -z ... ] || die` never fired on "").
  canonical_port "$PORT" || die "port file holds a non-canonical port: '$PORT'; re-run install"
  require_curl
  if label_loaded "$LABEL"; then
    "$LAUNCHCTL" kickstart "gui/$(id -u)/$LABEL" || die "kickstart failed"
  else
    env -i "$LAUNCHCTL" bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || "$LAUNCHCTL" load -w "$PLIST" 2>/dev/null || die "bootstrap failed"
  fi
  # Panel R4: the 200 must come from THIS label's job, not any listener.
  # Panel R7: a failed start must not leave the label loaded and KeepAlive
  # crash-looping it every 10 s — boot it out, VERIFY, and name the recovery.
  if ! wait_ours "$PORT" "$LABEL" 90; then
    _why="START_FAILED — server did not answer on 127.0.0.1:$PORT"
    if port_answered "$PORT"; then
      _jp=$(job_pid "$LABEL")
      _lp=$("$LSOF" -tP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1)
      _why="START_FAILED — port $PORT answered HTTP 200 from pid ${_lp:-not identified}, which is NOT label $LABEL's job (job pid ${_jp:-none}) — another process is serving this port"
    fi
    "$LAUNCHCTL" bootout "gui/$(id -u)/$LABEL" 2>/dev/null
    sleep 1
    if label_loaded "$LABEL"; then
      die "$_why and cleanup FAILED: label $LABEL is STILL LOADED (KeepAlive will crash-loop it) — run: launchctl bootout gui/$(id -u)/$LABEL — then see $ROOT/run/server.log"
    fi
    die "$_why; the label was unloaded (cleanup verified) — fix the cause, then re-run: $0 start --root $ROOT --label $LABEL; see $ROOT/run/server.log"
  fi
  if capture_access; then
    echo "STARTED label=$LABEL port=$PORT"
  else
    echo "STARTED label=$LABEL port=$PORT"
    echo "pairing access was NOT captured (no complete banner in $ROOT/run/server.log); to retry: $0 capture --root $ROOT --label $LABEL"
  fi
}

cmd_stop() {
  require_root_label
  PLIST="$(plist_dir)/$LABEL.plist"
  # Attack finding 7: capture the job's pid BEFORE bootout, so a port still
  # held afterwards can be attributed — our own server closing its socket
  # after SIGTERM is not "another process" and must not send the operator
  # hunting a process that is about to vanish.
  _job_pid=""
  if label_loaded "$LABEL"; then
    _job_pid=$(job_pid "$LABEL")
    "$LAUNCHCTL" bootout "gui/$(id -u)/$LABEL" 2>/dev/null \
      || "$LAUNCHCTL" unload -w "$PLIST" 2>/dev/null
  fi
  # F14: report one of exactly three truthful states. The old code ignored
  # bootout's own failure, sampled the port once, and printed
  # "STOPPED ... free" while KeepAlive was restarting the server.
  _i=0
  while label_loaded "$LABEL" && [ "$_i" -lt 10 ]; do _i=$((_i + 1)); sleep 1; done
  if label_loaded "$LABEL"; then
    die "STOP_FAILED label=$LABEL is still loaded; run by hand: launchctl bootout gui/$(id -u)/$LABEL"
  fi
  PORT=$(cat "$ROOT/run/port" 2>/dev/null || echo "")
  if [ -z "$PORT" ]; then
    # Attack finding 8: a missing port file must not ASSERT the server is
    # down — a server started outside launchd holds run/home.lock with no
    # launchd label. Verify the same lock install checks.
    if ! root_lock_free "$ROOT"; then
      die "STOP_FAILED no port file and $ROOT/run/home.lock is HELD — a server is still serving this root outside launchd; find it: ps ax -o pid,args= | grep -F '$ROOT/bin/server_runner.sh'"
    fi
    echo "STOPPED label=$LABEL (no port file; runner lock free)"
    return 0
  fi
  # Attack finding 7: if the listener is still OUR job's pid the server is
  # shutting down (a graceful close can outlast 10 s) — wait longer and say
  # so; only a pid that is not ours is "another process", and it is named.
  _limit=10
  [ -n "$_job_pid" ] && _limit=30
  _j=0
  while [ "$_j" -lt "$_limit" ]; do
    port_busy "$PORT" || break
    _holder=$("$LSOF" -tP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1)
    if [ -n "$_job_pid" ] && [ -n "$_holder" ] && [ "$_holder" != "$_job_pid" ]; then
      break  # genuinely foreign holder — no point waiting
    fi
    _j=$((_j + 1)); sleep 1
  done
  if port_busy "$PORT"; then
    _holder=$("$LSOF" -tP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1)
    if [ -n "$_job_pid" ] && [ "$_holder" = "$_job_pid" ]; then
      die "STOPPED label=$LABEL (unloaded) but our server pid $_job_pid is still closing port $PORT; it frees it as it exits — re-check: lsof -nP -iTCP:$PORT -sTCP:LISTEN"
    fi
    die "STOPPED label=$LABEL (unloaded) but port $PORT is still held by another process (pid ${_holder:-not identified}); find it: lsof -nP -iTCP:$PORT -sTCP:LISTEN"
  fi
  if ! root_lock_free "$ROOT"; then
    die "STOP_FAILED port $PORT is free but $ROOT/run/home.lock is HELD — a server is still serving this root outside launchd; find it: ps ax -o pid,args= | grep -F '$ROOT/bin/server_runner.sh'"
  fi
  echo "STOPPED label=$LABEL port=$PORT free"
  return 0
}

cmd_status() {
  require_root_label
  PORT=$(cat "$ROOT/run/port" 2>/dev/null || echo "?")
  echo "root=$ROOT"
  echo "label=$LABEL loaded=$(label_loaded "$LABEL" && echo yes || echo no)"
  _pid=""
  if label_loaded "$LABEL"; then
    _pid=$("$LAUNCHCTL" print "gui/$(id -u)/$LABEL" 2>/dev/null \
           | grep -E '^[[:space:]]*pid = [0-9]+' | head -1 | grep -oE '[0-9]+')
  fi
  echo "pid=${_pid:-none}"
  if [ "$PORT" != "?" ]; then
    # F20: same 000000 fix as wait_http.
    _code=$("$CURL" -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null) || _code=""
    [ -n "$_code" ] || _code=000
    echo "port=$PORT http_root=$_code"
    echo "listeners:"
    "$LSOF" -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tail -n +2 || true
  else
    echo "port=none (not installed?)"
  fi
  [ -f "$ROOT/config/server-bin" ] && echo "server_bin=$(cat "$ROOT/config/server-bin")"
  [ -f "$ROOT/run/access.txt" ] && echo "access_file=$ROOT/run/access.txt (mode $("$STAT" -f '%Lp' "$ROOT/run/access.txt"); not printed)"
}

cmd_doctor() {
  require_root_label
  label_valid "$LABEL" || die "invalid label: $LABEL"
  "$PYTHON3_BIN" "$REPO_DIR/tools/mmos_team_server/node_install.py" doctor \
    --root "$ROOT" --label "$LABEL"
}

cmd_uninstall() {
  require_root_label
  PLIST="$(plist_dir)/$LABEL.plist"
  # Panel R6: uninstall gets stop's truthful three-state treatment — a
  # bootout that fails must not be silenced into UNINSTALLED while the job
  # still serves and its plist is deleted.
  if label_loaded "$LABEL"; then
    "$LAUNCHCTL" bootout "gui/$(id -u)/$LABEL" 2>/dev/null || "$LAUNCHCTL" unload -w "$PLIST" 2>/dev/null
  fi
  _i=0
  while label_loaded "$LABEL" && [ "$_i" -lt 10 ]; do _i=$((_i + 1)); sleep 1; done
  if label_loaded "$LABEL"; then
    die "UNINSTALL_FAILED label=$LABEL is still loaded — nothing was removed; run by hand: launchctl bootout gui/$(id -u)/$LABEL"
  fi
  # F19: the old unchecked `rm -f` printed UNINSTALLED even with the plist
  # still on disk, so the next install died on "plist already exists".
  rm -f "$PLIST" 2>/dev/null
  if [ -e "$PLIST" ] || [ -L "$PLIST" ]; then
    die "could not remove $PLIST; remove it by hand before re-installing"
  fi
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
  capture) cmd_capture ;;
  uninstall) cmd_uninstall ;;
  selftest) cmd_selftest ;;
  *) usage ;;
esac
