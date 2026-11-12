#!/usr/bin/env bash
# paperclip_dev.sh — isolated Paperclip dev-instance controller for MMOS lane L9.
#
# PURPOSE
#   Every module build/test on this lane runs against an isolated Paperclip
#   dev instance, never the Chairman's default instance. This script starts,
#   stops, inspects and seeds that isolated instance, installs modules into
#   it from a local source path, and triggers module worker reloads.
#
# INSTANCE/PORT MECHANISM (Paperclip CLI 2026.1106.0; direct-start launcher
#   per deputy ruling 14, 2026-11-12)
#   * `up` NEVER invokes the CLI's server-wrapper commands: their doctor
#     step resolves store paths against the DEFAULT instance home, and one
#     abandoned launch joined the real database for 90 seconds. Instead `up`
#     writes a launch-server.mjs into the instance dir and runs it with
#     node; it imports startServer() from the managed CLI install's
#     @paperclipai/server package and calls it directly, with the instance
#     pinned from this script's environment:
#       PAPERCLIP_HOME=<dev home>            (instance home)
#       PAPERCLIP_INSTANCE_ID=<instance id>  (never "default")
#       PAPERCLIP_CONFIG=<instance config>   (ports + dirs, pinned)
#     With none of those set the server falls back to ~/.paperclip/instances/
#     default — the real instance — so the pins are not optional.
#   * The instance lives at
#     <home>/instances/<id>/ (config.json, db/, logs/, data/, secrets/,
#     runtime-info.json). State is fully isolated from ~/.paperclip.
#   * Ports come from the instance config file, NOT from a CLI flag:
#       server.port                     (zod default 3100)
#       database.embeddedPostgresPort   (zod default 54329)
#   * readConfig() applies zod DEFAULTS to missing config keys, and those
#     defaults hardcode ~/.paperclip/instances/default/... paths. A partial
#     config would point the dev instance's embedded Postgres data dir at
#     the DEFAULT instance's db/. This script therefore always writes a
#     COMPLETE config.json with explicit absolute paths under the dev root.
#   * The server prints its startup banner to stdout (captured in the server
#     log) naming the config path, the database data dir and the database
#     port as "<dir> (pg:<port>)". `up` reads the banner BEFORE making any
#     request, then proves isolation (below) before calling the instance
#     ready. The server may silently move the database port when its
#     configured port is taken — the banner is where that becomes visible.
#   * The embedded PostgreSQL runs as a DIRECT CHILD of the launcher process
#     (argv: postgres -D <data dir> -p <port>), and startServer() installs
#     the SIGINT/SIGTERM handlers that stop it in an ordered shutdown.
#   * This server path does not write runtime-info.json; stop/status rely
#     on the controller pidfile plus the port listener (see identity below).
#   * Plugin install: POST <url>/api/plugins/install with
#     {"packageName":"<abs dir>","isLocalPath":true}. local_trusted mode
#     authenticates every request as an implicit instance-admin board actor,
#     so no token is needed. The loader reads <dir>/package.json
#     paperclipPlugin.{manifest,worker,ui} (or dist/manifest.js fallback).
#   * Module reload: the host runs a dev watcher over every local-path
#     plugin's declared entrypoints; touching the worker entrypoint file
#     triggers a debounced (500ms) worker restart. No server restart needed.
#
# INSTANCE IDENTITY (build 2026.1106.0)
#   Refusal side: if the /api/health body at the target URL contains a path
#   under "$HOME/.paperclip/", the script refuses — that is the default
#   instance answering. Belt-and-braces only: the reserved-port checks above
#   already keep us off 3100/3179.
#   Positive side: this build's health body carries NO instance paths when
#   database backup is disabled (no databaseBackup block; verified on the
#   2026-11-10 dev boot — /api/health answered status:ok with the server
#   banner holding the backup dir, not the health body). A path marker can
#   prove "default" but never "dev". Positive dev identity is therefore
#   argv-based: the process LISTENING on our config port was launched as
#   `<node> <DEV_HOME>/instances/<id>/launch-server.mjs` (the direct
#   startServer() launcher), so its command line contains DEV_HOME (see
#   listener_is_ours). That survives controller restarts and a pidfile
#   wipe; a foreign instance rebinding our port — including one started
#   through the CLI wrapper — shows a different argv and is refused as
#   "unknown".
#
# BOUNDARIES ENFORCED (refusal = exit 3, before any mutation or HTTP write)
#   - dev home must not be ~/.paperclip or anything under it
#   - instance id must not be "default"
#   - server port must not be 3100 or 3179; db port must not be 54329
#     (neither explicit env/config values nor auto-picked ports)
#   - API host must be loopback
#   - health body at the resolved URL must not carry the default-home marker
#   - after start, before the instance is called ready, three isolation
#     checks (deputy ruling 14). Any failure kills the launched process
#     tree, prints exactly one line "PAPERCLIP-DEV: REAL STORE REFUSED"
#     (reason on stderr) and exits 3:
#       (a) no socket on TCP:54329 held by the launcher pid or any of its
#           children (the dev embedded PostgreSQL is a child)
#       (b) the database listener is the configured dev port, serving the
#           dev data dir, and the start banner names that same port
#       (c) the start banner and log name neither port 54329 nor any path
#           under ~/.paperclip/instances/default
#
# USAGE
#   paperclip_dev.sh up | down | status | url | logs | reset
#   paperclip_dev.sh install-module <module-dir>
#   paperclip_dev.sh reload-module <module-dir>
#   paperclip_dev.sh logs plugin <pluginId> [limit]
#
#   up            : create config (first run), launch the server in the
#                   background, wait for health, seed one dev company on
#                   first healthy start. Idempotent no-op when healthy.
#   down          : terminate the dev server (SIGTERM, then SIGKILL).
#                   Idempotent no-op when stopped. Kills only the pid
#                   recorded for THIS dev instance — never pkill by name.
#   status        : print run state + health + seed info. Never mutates.
#   url           : print the dev API/dashboard URL(s). Never mutates.
#   logs          : tail the dev server log. Never mutates.
#   logs plugin <pluginId> [limit]
#                 : fetch plugin log rows from /api/plugins/:id/logs.
#   install-module <module-dir>
#                 : install a module from a local source directory into the
#                   dev instance and wait until it is ready.
#   reload-module <module-dir>
#                 : touch the module's built worker entrypoint so the host
#                   dev watcher restarts the plugin worker, then report the
#                   worker state. Requires install-module first.
#   reset         : stop if running, then wipe ONLY the dev instance dir.
#
# EXIT CODES
#   0 success (including idempotent no-ops)  1 operational failure
#   3 refusal — target resolves to the default instance / reserved port
#
# ENVIRONMENT (all optional)
#   MMOS_DEV_HOME            dev home (default ~/.mastermind/mmos-dev/paperclip)
#   MMOS_DEV_INSTANCE_ID     instance id (default mmos-dev; must not be "default")
#   MMOS_DEV_SERVER_PORT     preferred server port (default 3190; pinned into
#                            the config on first start; must not be 3100/3179)
#   MMOS_DEV_DB_PORT         preferred embedded-Postgres port (default 54390;
#                            must not be 54329)
#   MMOS_DEV_COMPANY_NAME    seed company name (default "MMOS Dev")
#   MMOS_DEV_PAPERCLIP_CLI   CLI path (default the managed paperclipai binary;
#                            used for `company create` seeding and to derive
#                            the server entry below)
#   MMOS_DEV_NODE            node interpreter for the direct-start launcher
#                            (default: `command -v node`)
#   MMOS_DEV_SERVER_ENTRY    server entry .js whose startServer() the launcher
#                            imports (default: derived from the CLI install —
#                            <cli dir>/../@paperclipai/server/dist/index.js)
#   MMOS_DEV_START_TIMEOUT   health wait seconds (default 240 — the CLI wait
#                            may time out ~70s in while the server becomes
#                            healthy ~100s in; we reconcile real health and
#                            never blind-restart)
#   MMOS_DEV_STOP_TIMEOUT    stop grace seconds (default 60)
#   MMOS_DEV_CURL_TIMEOUT    per-request curl timeout seconds (default 5)
#   MMOS_DEV_PORT_SPAN       port scan width (default 60)
#   MMOS_DEV_LOG_LINES       default tail line count for `logs` (default 50)
#   MMOS_DEV_INSTALL_TIMEOUT install readiness wait seconds (default 90)
#
# No provider API key is required or accepted. No secrets are read, printed
# or committed by this script.

set -euo pipefail

readonly PROG="[paperclip-dev]"

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
DEV_HOME_RAW="${MMOS_DEV_HOME:-$HOME/.mastermind/mmos-dev/paperclip}"
INSTANCE_ID="${MMOS_DEV_INSTANCE_ID:-mmos-dev}"
PREF_SERVER_PORT="${MMOS_DEV_SERVER_PORT:-3190}"
PREF_DB_PORT="${MMOS_DEV_DB_PORT:-54390}"
COMPANY_NAME="${MMOS_DEV_COMPANY_NAME:-MMOS Dev}"
PAPERCLIP_CLI="${MMOS_DEV_PAPERCLIP_CLI:-$HOME/.paperclip/cli/current/node_modules/.bin/paperclipai}"
NODE_BIN="${MMOS_DEV_NODE:-}"
SERVER_ENTRY="${MMOS_DEV_SERVER_ENTRY:-}"
START_TIMEOUT="${MMOS_DEV_START_TIMEOUT:-240}"
STOP_TIMEOUT="${MMOS_DEV_STOP_TIMEOUT:-60}"
CURL_TIMEOUT="${MMOS_DEV_CURL_TIMEOUT:-5}"
PORT_SPAN="${MMOS_DEV_PORT_SPAN:-60}"
LOG_LINES="${MMOS_DEV_LOG_LINES:-50}"
INSTALL_TIMEOUT="${MMOS_DEV_INSTALL_TIMEOUT:-90}"

DEFAULT_HOME="$HOME/.paperclip"
# Reserved ports: the Chairman's default instance server (3100), the other
# known Paperclip listener on this host (3179) and the default instance's
# embedded Postgres (54329). Never bound, never targeted — even if free.
RESERVED_PORTS="3100 3179 54329"

PY="$(command -v python3 || true)"
[ -z "$PY" ] && PY="/opt/homebrew/bin/python3.12"

# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
log()  { printf '%s %s\n' "$PROG" "$*"; }
err()  { printf '%s ERROR: %s\n' "$PROG" "$*" >&2; }
die()  { err "$2"; exit "$1"; }
die_refuse() { err "REFUSED: $*"; err "This controller only operates on the isolated MMOS dev instance, never the Chairman's default Paperclip instance."; exit 3; }

# Resolve a directory to an absolute physical path when it exists (follows
# symlinks via pwd -P, which defeats symlink aliases of ~/.paperclip), else
# normalize lexically.
resolve_dir() {
  local p="$1"
  if [ -d "$p" ]; then
    (cd "$p" && pwd -P)
  elif [ -L "$p" ]; then
    # symlink to a not-yet-existing target
    local target
    target="$(readlink "$p")"
    case "$target" in
      /*) resolve_dir "$target" ;;
      *)  resolve_dir "$(dirname "$p")/$target" ;;
    esac
  else
    "$PY" - "$p" <<'PYEOF'
import os, sys
print(os.path.normpath(os.path.abspath(sys.argv[1])))
PYEOF
  fi
}

is_reserved_port() {
  local p="$1" r
  for r in $RESERVED_PORTS; do
    [ "$p" = "$r" ] && return 0
  done
  return 1
}

valid_port() { [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]; }

# Busy = something answers on 127.0.0.1:<port>. Offline tests stub `nc`
# through PATH; if nc is missing fall back to a /dev/tcp connect probe.
port_busy() {
  local p="$1"
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$p" >/dev/null 2>&1
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$p") >/dev/null 2>&1 && { exec 3>&- 3<&-; return 0; } || return 1
  fi
}

http_get() { # $1=url — echoes body; rc 0 on curl success (check identity separately)
  curl -sS -m "$CURL_TIMEOUT" "$1" 2>/dev/null
}

# http_post_json <url> <json> — echoes "HTTPCODE\nbody", from ONE request.
# The body is captured to a temp file so code and body come from the same
# call: install/enable/delete are NOT idempotent, and a two-curl helper
# double-fires them (observed: second install answered "already installed"
# while the first had succeeded — the script then mis-read the error body as
# the install row).
http_post_json() {
  local url="$1" json="$2" tmp code body
  tmp="$(mktemp)"
  code="$(curl -sS -m 60 -X POST -H 'Content-Type: application/json' \
        -d "$json" -o "$tmp" -w '%{http_code}' "$url" 2>/dev/null)" || code="000"
  body="$(cat "$tmp" 2>/dev/null || true)"
  rm -f "$tmp"
  printf '%s\n%s' "${code:-000}" "$body"
}

usage() {
  sed -n '2,/^set -euo pipefail$/p' "$0" | grep -E '^#( |$)' | sed 's/^# \{0,1\}//'
  exit 1
}

# --------------------------------------------------------------------------- #
# Path layout
# --------------------------------------------------------------------------- #
DEV_HOME="$(resolve_dir "$DEV_HOME_RAW")"
INSTANCE_ROOT="$DEV_HOME/instances/$INSTANCE_ID"
CONFIG_PATH="$INSTANCE_ROOT/config.json"
STATE_PATH="$INSTANCE_ROOT/dev-state.json"
PIDFILE="$INSTANCE_ROOT/dev-controller.pid"
RUNTIME_INFO="$INSTANCE_ROOT/runtime-info.json"
LOG_DIR="$INSTANCE_ROOT/logs"
SERVER_LOG="$LOG_DIR/dev-server.stdout.log"
LAUNCHER_SCRIPT="$INSTANCE_ROOT/launch-server.mjs"

# --------------------------------------------------------------------------- #
# Refusal checks
# --------------------------------------------------------------------------- #
read_config_ports() { # prints "<server_port> <db_port> <host>" (empty fields if absent)
  [ -f "$CONFIG_PATH" ] || { echo ""; return 0; }
  "$PY" - "$CONFIG_PATH" <<'PYEOF'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(2)
server = cfg.get("server") or {}
db = cfg.get("database") or {}
print(server.get("port", ""), db.get("embeddedPostgresPort", ""), server.get("host", "127.0.0.1"))
PYEOF
}

static_refusal_checks() {
  # 1. Instance id
  if [ "$INSTANCE_ID" = "default" ]; then
    die_refuse "instance id 'default' is the Chairman's default Paperclip instance (MMOS_DEV_INSTANCE_ID=default)."
  fi
  # 2. Dev home must not be ~/.paperclip or inside it (also catches
  #    ~/.paperclip/instances/default and ~/.paperclip-worktrees aliases).
  case "$DEV_HOME" in
    "$DEFAULT_HOME"|"$DEFAULT_HOME/"*) \
      die_refuse "dev home '$DEV_HOME' is inside the default Paperclip home '$DEFAULT_HOME'." ;;
  esac
  # 3. Paranoia: never operate on $HOME itself or filesystem root.
  case "$DEV_HOME" in
    ""|"/"|"$HOME"|"$HOME/") \
      die_refuse "dev home '$DEV_HOME' is not an isolated dev directory." ;;
  esac
  # 4. Explicitly requested ports must never be reserved.
  if valid_port "$PREF_SERVER_PORT" && is_reserved_port "$PREF_SERVER_PORT"; then
    die_refuse "requested server port $PREF_SERVER_PORT is reserved for the default instance / fleet."
  fi
  if valid_port "$PREF_DB_PORT" && is_reserved_port "$PREF_DB_PORT"; then
    die_refuse "requested embedded-Postgres port $PREF_DB_PORT is reserved for the default instance."
  fi
  # 5. Existing config must not point at reserved ports or a non-loopback host.
  local ports host server_port db_port
  if ports="$(read_config_ports 2>/dev/null)"; then
    if [ -n "$ports" ]; then
      read -r server_port db_port host <<<"$ports" || true
      if [ -n "$server_port" ]; then
        valid_port "$server_port" || die 1 "config server.port '$server_port' at $CONFIG_PATH is not a valid port."
        is_reserved_port "$server_port" && \
          die_refuse "config at $CONFIG_PATH pins server port $server_port, which belongs to the default instance / fleet."
      fi
      if [ -n "$db_port" ]; then
        valid_port "$db_port" || die 1 "config database.embeddedPostgresPort '$db_port' at $CONFIG_PATH is not a valid port."
        is_reserved_port "$db_port" && \
          die_refuse "config at $CONFIG_PATH pins embedded-Postgres port $db_port, which belongs to the default instance."
      fi
      case "$host" in
        127.0.0.1|localhost|::1|"" ) ;;
        *) die_refuse "config server.host '$host' is not loopback." ;;
      esac
    fi
  else
    die 1 "cannot parse config at $CONFIG_PATH."
  fi
}

# Path-marker verdict for a health body: "default" | "dev" | "" (no marker).
# NOTE: build 2026.1106.0's /api/health body carries NO instance paths when
# database backup is disabled (no databaseBackup block), so a body path can
# prove "default" (refusal) but usually NOT "dev". Positive dev identity
# comes from listener_is_ours below.
health_body_marker() {
  local body="$1"
  case "$body" in
    *"$DEFAULT_HOME/"*) echo "default" ; return ;;
  esac
  case "$body" in
    *"$DEV_HOME/"*)     echo "dev" ; return ;;
  esac
  echo ""
}

# True when the /api/health body is a healthy Paperclip response.
health_ok() { # $1=body
  [ -n "$1" ] || return 1
  case "$1" in
    *'"status":"ok"'*|*'"status": "ok"'*) return 0 ;;
  esac
  return 1
}

# True when the process LISTENING on $port was launched for THIS dev home.
# The server runs as: <node> <DEV_HOME>/instances/<id>/launch-server.mjs (the
# direct startServer() launcher), so its argv contains the launcher path —
# and with it DEV_HOME. This is the positive dev identity in a build whose
# health body carries no instance paths; it survives controller restarts and
# pidfile wipes, and a foreign instance rebinding our port (including one
# started through the CLI wrapper) fails it.
listener_is_ours() { # $1=port
  local port="$1" pid cmd
  pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  [ -n "$pid" ] || return 1
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [ -n "$cmd" ] || return 1
  case "$cmd" in
    *"$LAUNCHER_SCRIPT"*) return 0 ;;
  esac
  return 1
}

# GET <base>/api/health, refuse on the default-instance path marker, and
# print the identity verdict:
#   "down"      nothing reachable on the port
#   "dev"       ours: healthy body AND (dev path marker OR the listener on
#               our port was launched with DEV_HOME in argv)
#   "unhealthy" something answers but status is not ok
#   "unknown"   healthy Paperclip answer we cannot prove is ours
dynamic_identity_check() { # $1=base_url
  local base="$1" body marker port
  if ! body="$(http_get "$base/api/health")"; then
    echo "down"
    return 0
  fi
  marker="$(health_body_marker "$body")"
  if [ "$marker" = "default" ]; then
    die_refuse "URL $base answers /api/health with the default instance identity (path marker under $DEFAULT_HOME/)."
  fi
  if [ "$marker" = "dev" ]; then
    if health_ok "$body"; then echo "dev"; else echo "unhealthy"; fi
    return 0
  fi
  if ! health_ok "$body"; then
    echo "unhealthy"
    return 0
  fi
  port="${base##*:}"
  if listener_is_ours "$port"; then
    echo "dev"
    return 0
  fi
  echo "unknown"
}

# --------------------------------------------------------------------------- #
# Direct-start launcher and ruling-14 isolation proof
# --------------------------------------------------------------------------- #
# All pids in the launcher's process tree (launcher + descendants). The dev
# embedded PostgreSQL runs as a direct child of the launcher process.
server_tree_pids() { # $1=root pid — echoes "root child ..." (best effort)
  local root="$1" out="" next pid kid
  local frontier="$root" seen=" $root "
  while [ -n "$frontier" ]; do
    next=""
    for pid in $frontier; do
      for kid in $(pgrep -P "$pid" 2>/dev/null || true); do
        case "$seen" in *" $kid "*) continue ;; esac
        seen="$seen$kid "
        out="$out $kid"
        next="$next $kid"
      done
    done
    frontier="$next"
  done
  printf '%s' "$root$out"
}

# SIGTERM the whole tree (startServer()'s own handlers stop the embedded
# PostgreSQL in an ordered shutdown), wait, then SIGKILL stragglers.
kill_server_tree() { # $1=root pid
  local pid pids alive grace
  pids="$(server_tree_pids "$1")"
  [ -n "$pids" ] || pids="$1"
  for pid in $pids; do kill "$pid" 2>/dev/null || true; done
  grace=$(( SECONDS + 10 ))
  while [ "$SECONDS" -lt "$grace" ]; do
    alive=0
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then alive=1; fi
    done
    [ "$alive" = "0" ] && break
    sleep 1
  done
  for pid in $pids; do kill -9 "$pid" 2>/dev/null || true; done
}

# Deputy ruling 14 refusal: kill the started process tree first, then print
# EXACTLY one line on stdout (reason goes to stderr) and exit non-zero.
real_store_refused() { # $1=launcher_pid $2=reason
  kill_server_tree "$1"
  rm -f "$PIDFILE" 2>/dev/null || true
  printf 'PAPERCLIP-DEV: REAL STORE REFUSED\n'
  err "REAL STORE REFUSED: $2"
  err "The dev process tree was terminated before any further action; nothing was mutated."
  exit 3
}

# First lines of the server log naming the REAL store: the default
# instance's embedded-Postgres port or any path under ~/.paperclip (which
# covers ~/.paperclip/instances/default). Empty output = clean.
banner_real_store_markers() {
  grep -aF -e "54329" -e "$DEFAULT_HOME/" -e "instances/default" "$SERVER_LOG" 2>/dev/null | head -n 3 || true
}

# True once the startup banner has been printed. The banner's box-drawing
# rule is printed by nothing else in the server's log output.
banner_present() {
  grep -aq '──────────' "$SERVER_LOG" 2>/dev/null && return 0
  return 1
}

# True once the banner names OUR config path, OUR database data dir and a
# database port — the positive proof that the pinned instance answered.
banner_has_dev_markers() {
  grep -aqF -- "$CONFIG_PATH" "$SERVER_LOG" 2>/dev/null || return 1
  grep -aqF -- "$INSTANCE_ROOT/db" "$SERVER_LOG" 2>/dev/null || return 1
  grep -aq -- "pg:" "$SERVER_LOG" 2>/dev/null || return 1
  return 0
}

# Ruling-14 isolation proof. Runs after the banner check and the health
# identity, BEFORE the instance is called ready; any failure refuses.
isolation_checks() { # $1=launcher_pid $2=configured_db_port
  local pid="$1" db_port="$2" tree t out pg_pid pg_cmd

  # (a) No connection to the default instance's embedded-Postgres port by
  #     the launcher or any of its children (the dev Postgres is a child).
  tree="$(server_tree_pids "$pid")"
  for t in $tree; do
    out="$(lsof -a -p "$t" -iTCP:54329 2>/dev/null || true)"
    if [ -n "$out" ]; then
      real_store_refused "$pid" "pid $t in the launcher tree holds a socket on TCP:54329 (the default instance's database port): $(printf '%s' "$out" | head -n 1)"
    fi
  done
  log "isolation a: no TCP:54329 socket held by launcher tree pid(s):$(printf ' %s' $tree)"

  # (b) The database listener is the configured dev port, serving the dev
  #     data dir, and the banner names that same port.
  pg_pid="$(lsof -tiTCP:"$db_port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  if [ -z "$pg_pid" ]; then
    real_store_refused "$pid" "nothing listens on the configured database port $db_port."
  fi
  pg_cmd="$(ps -p "$pg_pid" -o command= 2>/dev/null || true)"
  case "$pg_cmd" in
    *"-D $INSTANCE_ROOT/db"*) : ;;
    *) real_store_refused "$pid" "the listener on database port $db_port (pid ${pg_pid:-?}) is not the dev embedded cluster: ${pg_cmd:-<no argv>}" ;;
  esac
  if ! grep -aq -- "pg:$db_port" "$SERVER_LOG" 2>/dev/null; then
    real_store_refused "$pid" "the start banner does not name the configured database port $db_port."
  fi
  log "isolation b: database listener pid $pg_pid on port $db_port serves $INSTANCE_ROOT/db; banner names pg:$db_port"

  # (c) The start banner and log name neither the real database port nor
  #     any path under the default instance root.
  out="$(banner_real_store_markers)"
  if [ -n "$out" ]; then
    real_store_refused "$pid" "server log names the real store: $(printf '%s' "$out" | head -n 1)"
  fi
  log "isolation c: banner/log names neither port 54329 nor any $DEFAULT_HOME/instances/default path"
}

# The generated direct-start launcher. Fully static: the server entry is
# handed in through MMOS_DEV_SERVER_ENTRY by the caller's environment, and
# every instance path is pinned by PAPERCLIP_HOME / PAPERCLIP_INSTANCE_ID /
# PAPERCLIP_CONFIG (deputy ruling 14).
write_launcher_script() {
  cat > "$LAUNCHER_SCRIPT" <<'LAUNCHER_EOF'
// launch-server.mjs — generated by tools/mmos_dev/paperclip_dev.sh. Do not
// edit. Deputy ruling 14 (2026-11-12): a lane starts a development board
// only through a launcher that sets the instance home, the database port and
// the database folder explicitly. This script imports the managed CLI
// install's @paperclipai/server entry and calls startServer() directly; the
// CLI's server-wrapper commands (whose doctor step resolves store paths
// against the DEFAULT instance home) are never executed.
const entry = process.env.MMOS_DEV_SERVER_ENTRY;
if (!entry) {
  console.error("launch-server: MMOS_DEV_SERVER_ENTRY is not set");
  process.exit(1);
}
const { pathToFileURL } = await import("node:url");
let mod;
try {
  mod = await import(pathToFileURL(entry).href);
} catch (err) {
  console.error(`launch-server: cannot import server entry ${entry}: ${err?.stack || err}`);
  process.exit(1);
}
if (typeof mod.startServer !== "function") {
  console.error(`launch-server: ${entry} exports no startServer()`);
  process.exit(1);
}
try {
  const started = await mod.startServer();
  console.log(`launch-server: server listening on ${started.host}:${started.listenPort}`);
} catch (err) {
  console.error(`launch-server: startServer failed: ${err?.stack || err}`);
  process.exit(1);
}
// startServer() installs its own SIGINT/SIGTERM handlers; they perform the
// ordered shutdown, including the embedded PostgreSQL child process. The
// HTTP listener keeps this process alive.
LAUNCHER_EOF
}

# --------------------------------------------------------------------------- #
# Config bootstrap
# --------------------------------------------------------------------------- #
pick_free_port() { # $1=preferred  — echoes first free non-reserved port
  local p="$1" i
  if valid_port "$p" && ! is_reserved_port "$p" && ! port_busy "$p"; then
    echo "$p"; return 0
  fi
  for i in $(seq 1 "$PORT_SPAN"); do
    p=$((p + 1))
    is_reserved_port "$p" && continue
    port_busy "$p" && continue
    echo "$p"; return 0
  done
  return 1
}

write_dev_config() { # $1=server_port $2=db_port
  local sp="$1" dp="$2" ir="$INSTANCE_ROOT" now
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  mkdir -p "$ir"
  cat > "$CONFIG_PATH" <<EOF
{
  "\$meta": { "version": 1, "updatedAt": "$now", "source": "configure" },
  "database": {
    "mode": "embedded-postgres",
    "embeddedPostgresDataDir": "$ir/db",
    "embeddedPostgresPort": $dp,
    "backup": {
      "enabled": false,
      "intervalMinutes": 60,
      "retentionDays": 7,
      "dir": "$ir/data/backups"
    }
  },
  "logging": { "mode": "file", "logDir": "$ir/logs" },
  "server": {
    "deploymentMode": "local_trusted",
    "exposure": "private",
    "bind": "loopback",
    "host": "127.0.0.1",
    "port": $sp,
    "allowedHostnames": [],
    "serveUi": true
  },
  "telemetry": { "enabled": false },
  "updates": { "checkEnabled": false },
  "auth": { "baseUrlMode": "auto", "disableSignUp": false },
  "storage": {
    "provider": "local_disk",
    "localDisk": { "baseDir": "$ir/data/storage" },
    "s3": { "bucket": "paperclip", "region": "us-east-1", "prefix": "", "forcePathStyle": false }
  },
  "secrets": {
    "provider": "local_encrypted",
    "strictMode": false,
    "localEncrypted": { "keyFilePath": "$ir/secrets/master.key" }
  }
}
EOF
}

# --------------------------------------------------------------------------- #
# CLI invocation (scrubbed environment; never inherits ambient PAPERCLIP_*)
# --------------------------------------------------------------------------- #
# Scrub list as an array so the launch path can hand it to nohup(1), which
# cannot exec a shell function ("nohup cli_env …" dies with ENOENT).
#
# The server launch runs NO CLI command at all (deputy ruling 14): `up`
# imports startServer() directly via the generated launcher. cli_env remains
# for `company create` (seeding) only. HOME is still redirected to an empty
# dir under the dev home for that call: the CLI's install-store probes
# resolve against $HOME, not against the -d home, and an empty HOME keeps
# them honestly empty. The script's OWN $HOME stays the real user home, so
# the default-instance identity marker (~/.paperclip/) keeps working.
ISOLATED_HOME="$DEV_HOME/home"
# env(1) stops parsing options at the first NAME=VALUE operand, so every -u
# must come BEFORE the HOME assignment or env treats "-u" as the program to
# exec ("env: -u: No such file or directory").
SCRUB_ENV=(env -u PORT -u HOST \
    -u PAPERCLIP_HOME -u PAPERCLIP_INSTANCE_ID -u PAPERCLIP_CONFIG \
    -u PAPERCLIP_CONTEXT -u PAPERCLIP_API_URL -u PAPERCLIP_COMPANY_ID \
    -u PAPERCLIP_API_KEY -u PAPERCLIP_RUN_ID \
    HOME="$ISOLATED_HOME")

# Created lazily (never before static_refusal_checks) so a refused target
# directory is not touched at all.
cli_env() { mkdir -p "$ISOLATED_HOME"; "${SCRUB_ENV[@]}" "$@"; }

# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #
seed_company() { # $1=base_url — creates one dev company, records state
  local base="$1" out company_id company_prefix
  if grep -q '"companyId"' "$STATE_PATH" 2>/dev/null; then
    return 0
  fi
  if ! out="$(cli_env "$PAPERCLIP_CLI" company create \
        -d "$DEV_HOME" -c "$CONFIG_PATH" \
        --payload-json "{\"name\":\"$COMPANY_NAME\"}" --json 2>&1)"; then
    err "company create failed:"
    printf '%s\n' "$out" >&2
    return 1
  fi
  printf '%s\n' "$out"
  if ! company_id="$("$PY" - "$STATE_PATH" "$(printf '%s' "$out")" <<'PYEOF'
import json, sys, os
raw = sys.argv[2]
start = raw.find("{")
data = json.loads(raw[start:]) if start >= 0 else {}
cid = data.get("id") or data.get("company", {}).get("id") or data.get("companyId") or ""
# Walk wrapped shapes ({company:{...}} etc.)
if not cid:
    for v in data.values():
        if isinstance(v, dict) and isinstance(v.get("id"), str) and (v.get("shortname") or v.get("prefix")):
            cid = v["id"]
            data = v
            break
print(cid)
PYEOF
)" || [ -z "$company_id" ]; then
    err "could not parse company id from create output"
    return 1
  fi
  company_prefix="$("$PY" - "$STATE_PATH" "$(printf '%s' "$out")" <<'PYEOF'
import json, sys
raw = sys.argv[2]
start = raw.find("{")
data = json.loads(raw[start:]) if start >= 0 else {}
prefix = (data.get("shortname") or data.get("prefix") or data.get("shortName")
          or data.get("issuePrefix") or data.get("company", {}).get("shortname")
          or data.get("company", {}).get("issuePrefix") or "")
if not prefix:
    for v in data.values():
        if isinstance(v, dict) and isinstance(v.get("shortname") or v.get("prefix") or v.get("issuePrefix"), str):
            prefix = v.get("shortname") or v.get("prefix") or v.get("issuePrefix")
            break
print(prefix)
PYEOF
)" || company_prefix=""
  cli_env "$PY" - "$STATE_PATH" "$company_id" "$company_prefix" "$COMPANY_NAME" "$base" <<'PYEOF'
import json, sys, datetime
state_path, company_id, prefix, name, base = sys.argv[1:6]
state = {
    "schemaVersion": 1,
    "companyId": company_id,
    "companyPrefix": prefix,
    "companyName": name,
    "createdWith": (
        "paperclipai company create -d <dev-home> -c <dev-home>/instances/mmos-dev/config.json "
        '--payload-json {"name":"%s"} --json' % name
    ),
    "apiUrl": base,
    "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
}
with open(state_path, "w") as fh:
    json.dump(state, fh, indent=2)
    fh.write("\n")
PYEOF
  log "seeded dev company '$COMPANY_NAME' (prefix: ${company_prefix:-?}, id: $company_id)"
}

# --------------------------------------------------------------------------- #
# State printers
# --------------------------------------------------------------------------- #
api_base() { # echoes http://127.0.0.1:<port> using the config as source of truth
  local ports server_port
  ports="$(read_config_ports 2>/dev/null || echo "")"
  [ -n "$ports" ] || return 1
  read -r server_port _ _ <<<"$ports"
  [ -n "$server_port" ] || return 1
  echo "http://127.0.0.1:$server_port"
}

company_id_from_state() {
  [ -f "$STATE_PATH" ] || return 1
  "$PY" - "$STATE_PATH" <<'PYEOF' 2>/dev/null
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("companyId", ""))
except Exception:
    pass
PYEOF
}

print_info_block() { # $1=base $2=identity $3=pid_desc
  log "home        : $DEV_HOME"
  log "instance id : $INSTANCE_ID"
  log "config      : $CONFIG_PATH"
  log "api url     : $1"
  log "health      : $2"
  log "pid         : $3"
  if [ -f "$STATE_PATH" ]; then
    "$PY" - "$STATE_PATH" <<'PYEOF'
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
print("[paperclip-dev] company      : %s (prefix: %s, id: %s)" % (
    s.get("companyName", "?"), s.get("companyPrefix", "?"), s.get("companyId", "?")))
PYEOF
  fi
}

live_pid() { # echoes a live pid for the dev server, or nothing
  local pid
  if [ -f "$PIDFILE" ]; then
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"; return 0
    fi
  fi
  if [ -f "$RUNTIME_INFO" ]; then
    pid="$("$PY" - "$RUNTIME_INFO" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    info = json.load(open(sys.argv[1]))
    print(info.get("pid", ""))
except Exception:
    print("")
PYEOF
)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"; return 0
    fi
  fi
  return 1
}

# Resolve the worker entrypoint of a module dir from its package.json
# (paperclipPlugin.worker, else dist/worker.js convention).
module_worker_entry() { # $1=module_dir — echoes abs path or returns 1
  local dir="$1" rel
  [ -f "$dir/package.json" ] || { err "no package.json in $dir"; return 1; }
  rel="$("$PY" - "$dir/package.json" <<'PYEOF' 2>/dev/null
import json, sys
try:
    pkg = json.load(open(sys.argv[1]))
    pc = pkg.get("paperclipPlugin") or {}
    print(pc.get("worker") or "")
except Exception:
    print("")
PYEOF
)"
  if [ -z "$rel" ]; then
    rel="dist/worker.js"
  fi
  local abs="$dir/$rel"
  [ -f "$abs" ] || { err "worker entrypoint missing: $abs (run the module build first)"; return 1; }
  echo "$abs"
}

# Print the installed plugin record whose packagePath matches $1, as JSON.
worker_pid() { # $1=base $2=plugin_id — echoes the plugin worker pid ("" if none)
  local diag pid
  diag="$(http_get "$1/api/plugins/$2/dashboard" 2>/dev/null)" || { echo ""; return 0; }
  pid="$(printf '%s' "$diag" | "$PY" -c 'import json,sys
try:
    d = json.load(sys.stdin)
    w = d.get("worker") or {}
    print(w.get("pid") if w.get("status") == "running" else "")
except Exception: print("")' 2>/dev/null || true)"
  echo "${pid:-}"
}

installed_plugin_by_path() { # $1=base $2=module_dir
  local base="$1" dir="$2" out
  # No status filter: a plugin in error status is exactly when a reload is
  # needed, and /api/plugins?status=ready would hide it.
  out="$(http_get "$base/api/plugins")" || return 1
  # Data goes in as an argument, NOT stdin: this python reads its script from
  # a heredoc on stdin, and a pipe into the same stdin is overridden by the
  # heredoc (json.load would read EOF).
  "$PY" - "$(resolve_dir "$dir")" "$out" <<'PYEOF'
import json, sys, os
target = sys.argv[1]
try:
    rows = json.loads(sys.argv[2])
except Exception:
    sys.exit(1)
for row in rows:
    if row.get("packagePath") and os.path.realpath(row["packagePath"]) == target:
        print(json.dumps(row))
        sys.exit(0)
sys.exit(1)
PYEOF
}

# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #
cmd_up() {
  static_refusal_checks
  mkdir -p "$LOG_DIR"
  # Re-resolve now that the directory exists (symlink safety), re-check.
  DEV_HOME="$(resolve_dir "$DEV_HOME_RAW")"
  INSTANCE_ROOT="$DEV_HOME/instances/$INSTANCE_ID"
  CONFIG_PATH="$INSTANCE_ROOT/config.json"
  STATE_PATH="$INSTANCE_ROOT/dev-state.json"
  PIDFILE="$INSTANCE_ROOT/dev-controller.pid"
  RUNTIME_INFO="$INSTANCE_ROOT/runtime-info.json"
  LOG_DIR="$INSTANCE_ROOT/logs"
  SERVER_LOG="$LOG_DIR/dev-server.stdout.log"
  LAUNCHER_SCRIPT="$INSTANCE_ROOT/launch-server.mjs"
  static_refusal_checks

  local server_port db_port base identity
  if [ ! -f "$CONFIG_PATH" ]; then
    server_port="$(pick_free_port "$PREF_SERVER_PORT")" || die 1 "no free server port found above $PREF_SERVER_PORT (scanned $PORT_SPAN)."
    db_port="$(pick_free_port "$PREF_DB_PORT")" || die 1 "no free embedded-Postgres port found above $PREF_DB_PORT (scanned $PORT_SPAN)."
    [ "$server_port" != "$db_port" ] || db_port="$(pick_free_port "$((db_port + 1))")" || die 1 "no distinct free db port."
    write_dev_config "$server_port" "$db_port"
    log "wrote dev config $CONFIG_PATH (server port $server_port, embedded-Postgres port $db_port)"
  fi

  # The configured database port is what every isolation check compares
  # against; read it from the config we just wrote/verified.
  local ports_line
  ports_line="$(read_config_ports 2>/dev/null)" || die 1 "cannot parse config at $CONFIG_PATH."
  read -r server_port db_port _ <<<"$ports_line" || true
  [ -n "$db_port" ] || die 1 "config at $CONFIG_PATH pins no database.embeddedPostgresPort."

  base="$(api_base)" || die 1 "cannot determine api base from $CONFIG_PATH."
  identity="$(dynamic_identity_check "$base")"

  if [ "$identity" = "dev" ]; then
    # Already-running healthy dev instance: idempotent no-op (and finish any
    # unfinished first-start seeding).
    seed_company "$base" || die 1 "instance healthy but company seeding failed; retry 'up'."
    log "already running and healthy — no-op."
    local pid; pid="$(live_pid || true)"
    print_info_block "$base" "healthy (identity: dev)" "${pid:-unknown (external)}"
    exit 0
  fi
  if [ "$identity" = "unknown" ] || [ "$identity" = "unhealthy" ]; then
    die 1 "port from $CONFIG_PATH is already serving a foreign/unhealthy Paperclip instance at $base (identity: $identity); refusing to launch."
  fi

  # identity = down → launch. Deputy ruling 14: start the board through the
  # direct-start launcher only — never through the CLI's wrapper commands.
  [ -x "$PAPERCLIP_CLI" ] || die 1 "Paperclip CLI not executable at $PAPERCLIP_CLI (set MMOS_DEV_PAPERCLIP_CLI)."
  if [ -z "$SERVER_ENTRY" ]; then
    local cli_modules
    cli_modules="$(cd "$(dirname "$PAPERCLIP_CLI")/.." 2>/dev/null && pwd)" || cli_modules=""
    if [ -n "$cli_modules" ]; then
      SERVER_ENTRY="$cli_modules/@paperclipai/server/dist/index.js"
    fi
  fi
  [ -n "$SERVER_ENTRY" ] || die 1 "cannot derive the server entry from $PAPERCLIP_CLI; set MMOS_DEV_SERVER_ENTRY."
  [ -f "$SERVER_ENTRY" ] || die 1 "server entry not found at $SERVER_ENTRY (set MMOS_DEV_SERVER_ENTRY)."
  if [ -z "$NODE_BIN" ]; then
    NODE_BIN="$(command -v node || true)"
  fi
  { [ -n "$NODE_BIN" ] && [ -x "$NODE_BIN" ]; } || die 1 "node interpreter not found (set MMOS_DEV_NODE)."

  write_launcher_script
  log "starting dev instance via: $NODE_BIN $LAUNCHER_SCRIPT (direct startServer from $SERVER_ENTRY)"
  log "instance pins: PAPERCLIP_HOME=$DEV_HOME PAPERCLIP_INSTANCE_ID=$INSTANCE_ID PAPERCLIP_CONFIG=$CONFIG_PATH"
  log "server log: $SERVER_LOG"
  mkdir -p "$ISOLATED_HOME"
  {
    printf '%s [%s] dev controller launching node launcher (direct startServer)\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PROG"
  } >> "$SERVER_LOG"
  local launch_env=( "${SCRUB_ENV[@]}" \
      PAPERCLIP_HOME="$DEV_HOME" \
      PAPERCLIP_INSTANCE_ID="$INSTANCE_ID" \
      PAPERCLIP_CONFIG="$CONFIG_PATH" \
      MMOS_DEV_SERVER_ENTRY="$SERVER_ENTRY" )
  nohup "${launch_env[@]}" "$NODE_BIN" "$LAUNCHER_SCRIPT" \
      </dev/null >>"$SERVER_LOG" 2>&1 &
  local srv_pid=$!
  echo "$srv_pid" > "$PIDFILE"

  # Ruling 14: read the start banner BEFORE making any request. Wait for the
  # banner without any HTTP; its Database row names the data dir and port.
  local deadline=$(( SECONDS + START_TIMEOUT )) markers verdict
  while :; do
    if banner_present; then
      break
    fi
    if ! kill -0 "$srv_pid" 2>/dev/null; then
      sleep 3
      if banner_present; then
        break
      fi
      err "launcher exited before printing the start banner. Last log lines:"
      tail -n 30 "$SERVER_LOG" >&2 || true
      rm -f "$PIDFILE"
      die 1 "dev instance failed to start."
    fi
    [ "$SECONDS" -lt "$deadline" ] || {
      err "no start banner after ${START_TIMEOUT}s. Terminating; last log lines:"
      tail -n 30 "$SERVER_LOG" >&2 || true
      kill_server_tree "$srv_pid"
      rm -f "$PIDFILE"
      die 1 "dev instance did not print its start banner in ${START_TIMEOUT}s."
    }
    sleep 1
  done

  # Banner read. A banner naming the real database port or a path under the
  # default instance root means stop the process at once and report.
  markers="$(banner_real_store_markers)"
  if [ -n "$markers" ]; then
    real_store_refused "$srv_pid" "start banner names the real store: $(printf '%s' "$markers" | head -n 1)"
  fi
  if ! banner_has_dev_markers; then
    kill_server_tree "$srv_pid"
    rm -f "$PIDFILE"
    err "the start banner does not name this dev instance's config, data dir and database port. Banner:"
    grep -a "Config\|Database\|Server" "$SERVER_LOG" 2>/dev/null | tail -n 6 >&2 || true
    die 1 "dev instance did not prove its dev identity in the start banner."
  fi

  # Banner is clean and ours. Now wait for health identity.
  deadline=$(( SECONDS + START_TIMEOUT ))
  while :; do
    verdict="$(dynamic_identity_check "$base" 2>/dev/null || echo down)"
    if [ "$verdict" = "dev" ]; then
      break
    fi
    if ! kill -0 "$srv_pid" 2>/dev/null; then
      err "launcher exited after the start banner. Last log lines:"
      tail -n 30 "$SERVER_LOG" >&2 || true
      kill_server_tree "$srv_pid"
      rm -f "$PIDFILE"
      die 1 "dev instance failed to start."
    fi
    [ "$SECONDS" -lt "$deadline" ] || {
      err "not healthy after ${START_TIMEOUT}s (identity: $verdict). Terminating; last log lines:"
      tail -n 30 "$SERVER_LOG" >&2 || true
      kill_server_tree "$srv_pid"
      rm -f "$PIDFILE"
      die 1 "dev instance did not become healthy in ${START_TIMEOUT}s."
    }
    sleep 2
  done

  # Ruling 14: prove isolation before calling the instance ready.
  isolation_checks "$srv_pid" "$db_port"

  seed_company "$base" || die 1 "instance healthy but company seeding failed; instance left running — retry 'up'."
  log "dev instance is healthy and isolated."
  print_info_block "$base" "healthy (identity: dev)" "$srv_pid (pidfile)"
  log "dashboard: use '$0 url'"
  exit 0
}

cmd_down() {
  static_refusal_checks
  local base pid identity
  base="$(api_base 2>/dev/null || true)"
  if [ -n "$base" ]; then
    identity="$(dynamic_identity_check "$base")"
  else
    identity="down"
  fi
  pid="$(live_pid || true)"
  if [ -z "$pid" ]; then
    if [ "$identity" != "dev" ]; then
      log "not running — no-op."
      rm -f "$PIDFILE" 2>/dev/null || true
      exit 0
    fi
    # Healthy dev server but no recorded pid: locate the listener on OUR port.
    local port="${base##*:}"
    pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
    [ -n "$pid" ] || die 1 "dev instance healthy at $base but no pid found; refusing blind kill."
    log "warning: no pidfile; using listener pid $pid on our dev port $port."
  fi

  log "stopping dev instance pid $pid (SIGTERM)…"
  # Collect the tree (embedded PostgreSQL is a child) BEFORE signalling, so
  # an ordered shutdown that does not reach the child can still be finished.
  local tree_pids pid2
  tree_pids="$(server_tree_pids "$pid")"
  kill "$pid" 2>/dev/null || true
  local deadline=$(( SECONDS + STOP_TIMEOUT ))
  while kill -0 "$pid" 2>/dev/null; do
    [ "$SECONDS" -lt "$deadline" ] || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    err "pid $pid did not exit within ${STOP_TIMEOUT}s; sending SIGKILL."
    kill -9 "$pid" 2>/dev/null || true
    sleep 2
  fi
  for pid2 in $tree_pids; do
    if [ "$pid2" != "$pid" ] && kill -0 "$pid2" 2>/dev/null; then
      log "stopping orphaned child pid $pid2"
      kill "$pid2" 2>/dev/null || true
    fi
  done
  sleep 1
  for pid2 in $tree_pids; do
    if [ "$pid2" != "$pid" ] && kill -0 "$pid2" 2>/dev/null; then
      kill -9 "$pid2" 2>/dev/null || true
    fi
  done
  rm -f "$PIDFILE"
  # Clean stale runtime-info written by the server (inside the dev dir only).
  if [ -f "$RUNTIME_INFO" ]; then
    local ripid
    ripid="$("$PY" - "$RUNTIME_INFO" <<'PYEOF' 2>/dev/null || echo ""
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("pid", ""))
except Exception:
    print("")
PYEOF
)"
    if [ -z "$ripid" ] || ! kill -0 "$ripid" 2>/dev/null; then
      rm -f "$RUNTIME_INFO"
    fi
  fi
  local after
  if [ -n "$base" ]; then
    after="$(dynamic_identity_check "$base")"
    [ "$after" = "down" ] || die 1 "instance at $base still answers after stop; investigate $SERVER_LOG."
  fi
  log "stopped."
  exit 0
}

cmd_status() {
  static_refusal_checks
  local base identity pid
  base="$(api_base 2>/dev/null || true)"
  if [ -n "$base" ]; then
    identity="$(dynamic_identity_check "$base")"
  else
    identity="unconfigured (no config yet — run 'up')"
  fi
  pid="$(live_pid || true)"
  if [ -n "$pid" ]; then
    pid="$pid (alive)"
  elif [ -f "$RUNTIME_INFO" ] || [ -f "$PIDFILE" ]; then
    pid="recorded but not alive (stale)"
  else
    pid="not running"
  fi
  print_info_block "${base:-unknown}" "$identity" "$pid"
  # Installed plugins summary (read-only).
  if [ -n "$base" ] && [ "$identity" = "dev" ]; then
    local rows
    rows="$(http_get "$base/api/plugins")" || rows=""
    if [ -n "$rows" ] && [ "$rows" != "[]" ]; then
      "$PY" - "$rows" <<'PYEOF'
import json, sys
try:
    rows = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
for r in rows:
    if r.get("status") == "uninstalled":
        continue
    m = r.get("manifestJson") or {}
    name = r.get("displayName") or m.get("displayName") or r.get("pluginKey")
    print("[paperclip-dev] plugin       : %s (%s %s) status=%s" % (
        r.get("pluginKey"), name, r.get("version"), r.get("status")))
PYEOF
    fi
  fi
  exit 0
}

cmd_url() {
  static_refusal_checks
  local base prefix
  base="$(api_base 2>/dev/null)" || die 1 "no config yet at $CONFIG_PATH — run 'up' first."
  echo "$base"
  if [ -f "$STATE_PATH" ]; then
    prefix="$("$PY" - "$STATE_PATH" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("companyPrefix", ""))
except Exception:
    print("")
PYEOF
)"
    [ -n "$prefix" ] && echo "$base/$prefix"
  fi
  exit 0
}

cmd_logs() {
  static_refusal_checks
  if [ "${1:-}" = "plugin" ]; then
    local plugin_id="${2:-}" limit="${3:-25}"
    [ -n "$plugin_id" ] || die 1 "usage: $0 logs plugin <pluginId> [limit]"
    local base
    base="$(api_base 2>/dev/null)" || die 1 "no config yet at $CONFIG_PATH — run 'up' first."
    local identity; identity="$(dynamic_identity_check "$base")"
    [ "$identity" = "dev" ] || die 1 "dev instance not healthy (identity: $identity)."
    local rows
    rows="$(http_get "$base/api/plugins/$plugin_id/logs?limit=$limit")" || rows=""
    "$PY" - "$rows" <<'PYEOF'
import json, sys
try:
    rows = json.loads(sys.argv[1])
except Exception:
    print("(no parseable log rows)")
    sys.exit(0)
if not rows:
    # Truthful, not silent: build 2026.1106.0 persists metrics.write rows to
    # plugin_logs; ctx.logger lines only reach the server log.
    print("(plugin_logs has no rows; worker ctx.logger lines go to the server log: paperclip_dev.sh logs)")
    sys.exit(0)
for r in rows:
    meta = r.get("meta")
    meta_s = json.dumps(meta, separators=(",", ":")) if meta else ""
    print("%s [%s] %s %s" % (r.get("createdAt"), r.get("level"), r.get("message"), meta_s))
PYEOF
    exit 0
  fi
  local lines="${1:-$LOG_LINES}"
  [ -f "$SERVER_LOG" ] || die 1 "no server log yet at $SERVER_LOG."
  tail -n "$lines" "$SERVER_LOG"
  exit 0
}

cmd_install_module() {
  static_refusal_checks
  local module_dir="${1:-}"
  [ -n "$module_dir" ] || die 1 "usage: $0 install-module <module-dir>"
  [ -d "$module_dir" ] || die 1 "module dir not found: $module_dir"
  module_dir="$(resolve_dir "$module_dir")"
  [ -f "$module_dir/package.json" ] || die 1 "no package.json in $module_dir"
  module_worker_entry "$module_dir" >/dev/null || die 1 "module has no built worker entrypoint (run its build first)."

  local base identity
  base="$(api_base 2>/dev/null)" || die 1 "no config yet at $CONFIG_PATH — run 'up' first."
  identity="$(dynamic_identity_check "$base")"
  [ "$identity" = "dev" ] || die 1 "dev instance not healthy (identity: $identity) — refusing to POST an install."

  log "installing module from $module_dir …"
  local resp code body
  resp="$(http_post_json "$base/api/plugins/install" "{\"packageName\":\"$module_dir\",\"isLocalPath\":true}")"
  code="${resp%%$'\n'*}"
  body="${resp#*$'\n'}"
  local already=0
  if [ "$code" != "200" ]; then
    case "$body" in
      *"already installed"*)
        already=1
        log "module already installed — waiting for it to become ready (use reload-module after a source edit)."
        ;;
      *)
        err "install failed (HTTP $code):"; printf '%s\n' "$body" >&2; die 1 "install-module failed." ;;
    esac
  fi
  if [ "$already" = "0" ]; then
    "$PY" - "$body" <<'PYEOF'
import json, sys
try:
    row = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
if row.get("error"):
    print("[paperclip-dev] install error : %s" % row["error"])
    sys.exit(0)
print("[paperclip-dev] installed   : %s (id %s, version %s, status %s)" % (
    row.get("pluginKey"), row.get("id"), row.get("version"), row.get("status")))
print("[paperclip-dev] packagePath : %s" % row.get("packagePath"))
PYEOF
  fi

  # Resolve the plugin id from the install body; if the body is not a row
  # (e.g. "already installed" — the module is still installed), fall back to
  # the registry lookup by package path.
  local deadline=$(( SECONDS + INSTALL_TIMEOUT )) plugin_id
  plugin_id="$(printf '%s' "$body" | "$PY" -c 'import json,sys
try: print(json.load(sys.stdin).get("id") or "")
except Exception: print("")')"
  if [ -z "$plugin_id" ]; then
    plugin_id="$(installed_plugin_by_path "$base" "$module_dir" 2>/dev/null \
      | "$PY" -c 'import json,sys
try: print(json.load(sys.stdin).get("id") or "")
except Exception: print("")' 2>/dev/null || true)"
  fi
  [ -n "$plugin_id" ] || die 1 "could not resolve plugin id for $module_dir."
  while :; do
    body="$(http_get "$base/api/plugins/$plugin_id")" || body=""
    if [ "$(printf '%s' "$body" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null || true)" = "ready" ]; then
      log "module is ready: $plugin_id"
      exit 0
    fi
    [ "$SECONDS" -lt "$deadline" ] || { err "module did not become ready in ${INSTALL_TIMEOUT}s:"; printf '%s\n' "$body" >&2; die 1 "install-timeout."; }
    sleep 2
  done
}

cmd_reload_module() {
  static_refusal_checks
  local module_dir="${1:-}"
  [ -n "$module_dir" ] || die 1 "usage: $0 reload-module <module-dir>"
  [ -d "$module_dir" ] || die 1 "module dir not found: $module_dir"
  module_dir="$(resolve_dir "$module_dir")"

  local base identity
  base="$(api_base 2>/dev/null)" || die 1 "no config yet at $CONFIG_PATH — run 'up' first."
  identity="$(dynamic_identity_check "$base")"
  [ "$identity" = "dev" ] || die 1 "dev instance not healthy (identity: $identity)."

  local worker plugin_row plugin_id plugin_key
  worker="$(module_worker_entry "$module_dir")" || die 1
  plugin_row="$(installed_plugin_by_path "$base" "$module_dir")" || \
    die 1 "no installed plugin with packagePath == $module_dir; run 'install-module' first."
  plugin_id="$(printf '%s' "$plugin_row" | "$PY" -c 'import json,sys
try: print(json.load(sys.stdin)["id"])
except Exception: print("")')"
  plugin_key="$(printf '%s' "$plugin_row" | "$PY" -c 'import json,sys
try: print(json.load(sys.stdin)["pluginKey"])
except Exception: print("")')"
  [ -n "$plugin_id" ] || die 1 "could not read plugin id from registry row."

  worker_pid_before="$(worker_pid "$base" "$plugin_id")"

  # The host dev watcher attaches ONLY at server startup (app.js: watch after
  # loadAll()), so a plugin installed at runtime is NOT watched and touching
  # its worker entry does nothing. Touch first; if the worker pid did not
  # change, fall back to delete + reinstall (soft uninstall keeps the row and
  # the plugin id; the install re-forks the CURRENT dist).
  log "touching $worker (host dev watcher restarts the worker, 500ms debounce)"
  touch "$worker"
  sleep 4

  local pid_after
  pid_after="$(worker_pid "$base" "$plugin_id")"
  if [ -z "$pid_after" ] || [ "$pid_after" = "$worker_pid_before" ]; then
    log "watcher did not restart the worker (pid unchanged: ${pid_after:-none}) — reinstalling the module."
    local resp code body
    resp="$(curl -sS -m 60 -X DELETE -o /dev/null -w '%{http_code}' \
      -H 'x-instance-role: local_trusted' "$base/api/plugins/$plugin_id" 2>/dev/null || echo 000)"
    [ "$resp" = "200" ] || [ "$resp" = "204" ] || \
      { err "reload: DELETE /api/plugins/$plugin_id failed (HTTP $resp)."; die 1 "reload-module failed."; }
    sleep 1
    resp="$(http_post_json "$base/api/plugins/install" "{\"packageName\":\"$module_dir\",\"isLocalPath\":true}")"
    code="${resp%%$'\n'*}"
    body="${resp#*$'\n'}"
    if [ "$code" != "200" ]; then
      err "reload: reinstall failed (HTTP $code):"; printf '%s\n' "$body" >&2; die 1 "reload-module failed."
    fi
  fi

  # Report worker diagnostics via the plugin dashboard route (read-only).
  local diag
  diag="$(http_get "$base/api/plugins/$plugin_id/dashboard")" || diag=""
  "$PY" - "$plugin_key" "$diag" <<'PYEOF'
import json, sys
key = sys.argv[1]
try:
    d = json.loads(sys.argv[2])
except Exception:
    print("[paperclip-dev] reload     : dashboard unreadable; check 'logs plugin %s'" % key)
    sys.exit(0)
w = d.get("worker") or {}
print("[paperclip-dev] reload     : worker status=%s pid=%s uptime=%ss crashes=%s" % (
    w.get("status"), w.get("pid"), int(w.get("uptime") or 0), w.get("totalCrashes")))
h = d.get("health") or {}
print("[paperclip-dev] health     : %s %s" % (h.get("status"), h.get("message") or ""))
PYEOF
  exit 0
}

cmd_reset() {
  static_refusal_checks
  local base identity
  if [ ! -d "$INSTANCE_ROOT" ]; then
    log "nothing to reset (no $INSTANCE_ROOT) — no-op."
    exit 0
  fi
  base="$(api_base 2>/dev/null || true)"
  if [ -n "$base" ]; then
    identity="$(dynamic_identity_check "$base")"
    if [ "$identity" = "dev" ]; then
      log "dev instance is running — stopping it before reset."
      cmd_down
    elif [ "$identity" = "unknown" ]; then
      die 1 "port from $CONFIG_PATH serves an unknown instance at $base; refusing to wipe."
    fi
  fi
  # Final guards on the exact directory we are about to remove.
  local target
  target="$(resolve_dir "$INSTANCE_ROOT")"
  case "$target" in
    "$DEV_HOME/instances/"*) : ;;
    *) die_refuse "reset target '$target' is not <dev-home>/instances/<id>." ;;
  esac
  case "$target" in
    "$DEFAULT_HOME"|"$DEFAULT_HOME/"*|"/"|"$HOME"|"$HOME/"*) \
      die_refuse "reset target '$target' touches the default Paperclip home." ;;
  esac
  rm -rf "$target"
  log "wiped $target"
  exit 0
}

# --------------------------------------------------------------------------- #
main() {
  [ $# -ge 1 ] || usage
  case "$1" in
    up)              cmd_up ;;
    down)            cmd_down ;;
    status)          cmd_status ;;
    url)             cmd_url ;;
    logs)            shift; cmd_logs "$@" ;;
    install-module)  shift; cmd_install_module "$@" ;;
    reload-module)   shift; cmd_reload_module "$@" ;;
    reset)           cmd_reset ;;
    -h|--help|help)  usage ;;
    *) err "unknown subcommand: $1"; usage ;;
  esac
}

main "$@"
