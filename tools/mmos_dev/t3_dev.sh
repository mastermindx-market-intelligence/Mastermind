#!/bin/sh
# t3_dev.sh — isolated T3 dev server for MMOS lane T1 (PROGRAM_PLAN_V4 §5, §6).
#
# Own home (~/.mastermind/mmos-dev/t3/home), own port (3790+, never 3773/3774),
# loopback only, no browser, headless `t3 serve`. The pairing token printed by
# the server is a credential: it is captured to run/access.txt (mode 0600) and
# never echoed. Fabric route env comes from DEV_ROOT/fabric.env (mode 0600).
#
# Commands: start | stop | status | selftest
set -u

DEV_ROOT="${MMOS_T3_DEV_ROOT:-$HOME/.mastermind/mmos-dev/t3}"
HOME_DIR="$DEV_ROOT/home"
RUN_DIR="$DEV_ROOT/run"
LOG_FILE="$RUN_DIR/server.log"
PID_FILE="$RUN_DIR/server.pid"
PORT_FILE="$RUN_DIR/port"
ACCESS_FILE="$RUN_DIR/access.txt"     # pairing URL + token; 0600; never print
ENV_FILE="$DEV_ROOT/fabric.env"       # ANTHROPIC_* route env; 0600; never print
T3_BIN="${T3_BIN:-$HOME/.t3/bin/t3}"
REAL_T3_HOME="$HOME/.t3"
FORBIDDEN_PORTS=" 3773 3774 "
PORT_MIN=3790
PORT_MAX=3810

die() { echo "t3_dev: $1" >&2; exit 1; }

realpath_of() { (cd "$1" 2>/dev/null && pwd -P) || echo ""; }

resolved_home() { realpath_of "$HOME_DIR"; }

check_home_safe() {
  [ -d "$HOME_DIR" ] || mkdir -p "$HOME_DIR" || die "cannot create $HOME_DIR"
  rh=$(resolved_home)
  rt=$(realpath_of "$REAL_T3_HOME")
  [ "$rh" != "$rt" ] || die "home resolves to $rt (the live T3 home); refusing"
  case "$rh" in "$rt"/*) die "home is inside $rt; refusing" ;; esac
  return 0
}

port_forbidden() {
  case "$FORBIDDEN_PORTS" in *" $1 "*) return 0 ;; esac
  return 1
}

port_busy() { nc -z 127.0.0.1 "$1" >/dev/null 2>&1; }

pick_port() {
  p="$PORT_MIN"
  while [ "$p" -le "$PORT_MAX" ]; do
    port_forbidden "$p" && { p=$((p + 1)); continue; }
    port_busy "$p" || { echo "$p"; return 0; }
    p=$((p + 1))
  done
  return 1
}

server_pid() {
  [ -f "$PID_FILE" ] && read -r pid < "$PID_FILE" || pid=""
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then echo "$pid"; return 0; fi
  return 1
}

cmd_start() {
  if pid=$(server_pid); then die "already running (pid $pid, port $(cat "$PORT_FILE" 2>/dev/null))"; fi
  check_home_safe
  PORT="${MMOS_T3_DEV_PORT:-}"
  if [ -z "$PORT" ]; then PORT=$(pick_port) || die "no free port in $PORT_MIN..$PORT_MAX"; fi
  port_forbidden "$PORT" && die "port $PORT is reserved for the live T3 servers"
  port_busy "$PORT" && die "port $PORT is busy"
  mkdir -p "$RUN_DIR" "$HOME_DIR" "$DEV_ROOT/claude-home" "$DEV_ROOT/scratch-project"
  [ -f "$ENV_FILE" ] || die "missing $ENV_FILE; run seed_dev_home.py first"
  # Env values are read from the 0600 file; never echoed.
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  : > "$LOG_FILE"
  chmod 600 "$LOG_FILE"
  T3CODE_HOME="$HOME_DIR" T3CODE_PORT="$PORT" T3CODE_HOST=127.0.0.1 \
    T3CODE_NO_BROWSER=1 nohup "$T3_BIN" serve </dev/null >> "$LOG_FILE" 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"
  echo "$PORT" > "$PORT_FILE"
  i=0
  while [ "$i" -lt 120 ]; do
    if ! kill -0 "$pid" 2>/dev/null; then die "server exited during startup; see $LOG_FILE"; fi
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null || echo 000)
    [ "$code" = "200" ] && break
    i=$((i + 1)); sleep 1
  done
  [ "$code" = "200" ] || { kill "$pid" 2>/dev/null; die "server not ready on :$PORT (last code $code)"; }
  # Capture the pairing credential into the 0600 access file; never print it.
  grep -E '^(Connection string|Token|Pairing URL):' "$LOG_FILE" > "$ACCESS_FILE" || true
  chmod 600 "$ACCESS_FILE"
  echo "STARTED pid=$pid port=$PORT home=$HOME_DIR"
  echo "pairing access saved to $ACCESS_FILE (mode 0600; not printed)"
}

cmd_stop() {
  pid=$(server_pid) || { rm -f "$PID_FILE"; echo "STOPPED (was not running)"; return 0; }
  kill "$pid" 2>/dev/null || true
  i=0
  while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 15 ]; do i=$((i + 1)); sleep 1; done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null && sleep 1
  rm -f "$PID_FILE"
  echo "STOPPED pid=$pid"
}

cmd_status() {
  echo "home=$HOME_DIR"
  rh=$(resolved_home); rt=$(realpath_of "$REAL_T3_HOME")
  if [ "$rh" = "$rt" ] || [ -z "$rh" ]; then echo "home_resolved=UNSAFE_OR_MISSING"; else echo "home_resolved=$rh"; fi
  if pid=$(server_pid); then
    PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "?")
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null || echo 000)
    echo "running=yes pid=$pid port=$PORT http_root=$code"
  else
    echo "running=no"
    PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "?")
    [ "$PORT" != "?" ] && { port_busy "$PORT" && echo "port $PORT still busy (unknown owner)"; }
  fi
  echo "port=$PORT"
  version=$("$T3_BIN" --version 2>/dev/null | tail -1)
  echo "version=$version"
  # Auth policy: web mode + loopback host => loopback-browser (EnvironmentAuthPolicy.ts).
  echo "auth_policy=loopback-browser (web mode, host 127.0.0.1; bootstrap one-time-token, session browser cookie)"
  echo "log=$LOG_FILE (0600; contains the pairing token)"
  echo "access_file=$ACCESS_FILE (0600)"
}

cmd_selftest() {
  fail=0
  port_forbidden 3773 && echo "guard 3773 forbidden: ok" || { echo "guard 3773 forbidden: FAIL"; fail=1; }
  port_forbidden 3774 && echo "guard 3774 forbidden: ok" || { echo "guard 3774 forbidden: FAIL"; fail=1; }
  port_forbidden 3790 || echo "guard 3790 allowed: ok" || { echo "guard 3790 allowed: FAIL"; fail=1; }
  ( HOME_DIR="$REAL_T3_HOME" check_home_safe ) 2>/dev/null && { echo "guard real-home refuse: FAIL"; fail=1; } \
    || echo "guard real-home refuse: ok"
  ( HOME_DIR="$REAL_T3_HOME/foo" check_home_safe ) 2>/dev/null && { echo "guard inside-real-home refuse: FAIL"; fail=1; } \
    || echo "guard inside-real-home refuse: ok"
  [ -x "$T3_BIN" ] && echo "t3 bin executable: ok" || { echo "t3 bin executable: FAIL"; fail=1; }
  [ -f "$ENV_FILE" ] && [ "$(stat -f '%Lp' "$ENV_FILE")" = "600" ] \
    && echo "fabric.env present mode 600: ok" || { echo "fabric.env present mode 600: FAIL"; fail=1; }
  echo "selftest_fail=$fail"
  return $fail
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  selftest) cmd_selftest ;;
  *) echo "usage: $0 start|stop|status|selftest" >&2; exit 2 ;;
esac
