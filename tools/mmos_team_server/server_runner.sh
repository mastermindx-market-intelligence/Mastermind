#!/bin/sh
# server_runner.sh — what launchd runs for a Mastermind team T3 server.
# Installed by team_server.sh as <root>/bin/server_runner.sh and invoked by the
# LaunchAgent as: /bin/sh <root>/bin/server_runner.sh <root>
#
# Guarantees (T6 brief item 1/7):
#   * loopback only: T3CODE_HOST=127.0.0.1, no --lan, no tailscale
#   * one server per home: an flock held across exec; a second runner on the
#     same root exits 42 without ever starting a server
#   * route keys only from <root>/fabric.env (0600), never from the plist
#   * log bounded: truncated at runner start when over TEAM_SERVER_LOG_CAP bytes
#   * the pairing credential the server prints goes to launchd's
#     StandardOutPath (<root>/run/server.log, 0600) and is never echoed here
set -u

ROOT="${1:-}"
[ -n "$ROOT" ] || { echo "server_runner: missing root argument" >&2; exit 64; }
[ -d "$ROOT" ] || { echo "server_runner: root $ROOT does not exist" >&2; exit 66; }

RUN_DIR="$ROOT/run"
LOG_FILE="$RUN_DIR/server.log"
BOOT_STATUS="$RUN_DIR/boot.status"
ENV_FILE="$ROOT/fabric.env"
BIN_CONF="$ROOT/config/server-bin"
CAP_CONF="$ROOT/config/log-cap"
SCRATCH="$ROOT/scratch-project"
CAP=52428800   # 50 MiB default
# launchd passes NO environment, so a cap set via TEAM_SERVER_LOG_CAP at
# install time never reaches the runner; the root's own config file does.
# FU4: TEAM_SERVER_LOG_CAP is a TEST-ONLY seam now — honored exclusively
# under MMOS_TEST_SEAMS=1; set otherwise it refuses rather than steering.
if [ -s "$CAP_CONF" ]; then
  CAP=$(head -1 "$CAP_CONF")
  case "$CAP" in ''|*[!0-9]*) CAP=52428800 ;; esac
elif [ -n "${TEAM_SERVER_LOG_CAP:-}" ]; then
  if [ "${MMOS_TEST_SEAMS:-}" = "1" ]; then
    CAP="$TEAM_SERVER_LOG_CAP"
  else
    echo "server_runner: TEAM_SERVER_LOG_CAP is set but MMOS_TEST_SEAMS is not 1; test-only env seams are refused" >&2
    exit 78
  fi
fi

# Round 3 B: an empty server.log must never again read as "working". Every
# boot stage is announced on stderr (launchd appends it to server.log) AND
# appended to run/boot.status as `stage=<name> <epoch>` — credential-free,
# machine-readable, freshened by the resolver's verify heartbeats. install's
# wait reads boot.status to tell "still verifying" from "dead".
BOOT_START=$(date +%s)
stage() {
  echo "server_runner: stage $1 (boot +$(( $(date +%s) - BOOT_START ))s)" >&2
  echo "stage=$1 $(date +%s)" >> "$BOOT_STATUS" 2>/dev/null || true
}
: > "$BOOT_STATUS" 2>/dev/null || true
stage pre-flight

mkdir -p "$RUN_DIR" "$SCRATCH" 2>/dev/null
# F28: the old `|| true` tolerated a failed mkdir and let the inline python
# die with a FileNotFoundError traceback into the log on every
# ThrottleInterval. One line, operator-readable, correct exit.
[ -d "$RUN_DIR" ] || { echo "server_runner: cannot create $RUN_DIR (root read-only or full?)" >&2; exit 73; }
[ -d "$SCRATCH" ] || { echo "server_runner: cannot create $SCRATCH (root read-only or full?)" >&2; exit 73; }
[ -f "$ENV_FILE" ] || { echo "server_runner: missing $ENV_FILE (seed the root first)" >&2; exit 78; }

# Item 13: the interpreter for the runtime resolver is the absolute path
# `install` recorded and validated (config/python3-path) — never a PATH
# search, never the script's own `#!/usr/bin/env python3` line, which under
# launchd resolved against whatever PATH launchd happened to pass (F13).
PY3_CONF="$ROOT/config/python3-path"
PY3=""
if [ -s "$PY3_CONF" ]; then PY3=$(head -1 "$PY3_CONF" 2>/dev/null); fi
case "$PY3" in
  /*) [ -f "$PY3" ] && [ -x "$PY3" ] || PY3="" ;;
  *) PY3="" ;;
esac
[ -n "$PY3" ] || { echo "server_runner: no recorded python3 interpreter (config/python3-path missing or invalid); recovery: runbook step 3 (node_install.py install) records it — see integrations/mmos/TSH_TEAM_SERVER_HARDENING.md" >&2; exit 78; }

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# FU4 (R8 pass 2): stat was still PATH-resolved here — pin it absolute like
# every other system tool the runner trusts.
STAT_BIN=/usr/bin/stat

# Bound the log before the server can add more (crash-loop disk-fill guard).
if [ -f "$LOG_FILE" ] && [ "$("$STAT_BIN" -f%z "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$CAP" ]; then
  : > "$LOG_FILE" || true
fi
chmod 600 "$LOG_FILE" 2>/dev/null || true

# NODE_BIN is selected atomically with the packed server. Legacy --server-bin
# overrides this path explicitly; absent that marker the old stock CLI remains.
NODE_BIN=""
PACKED=0
[ -s "$ROOT/config/server-runtime.json" ] && [ -s "$ROOT/config/node-runtime.json" ] && PACKED=1
if [ "$PACKED" -eq 1 ]; then
  stage resolve-node
  NODE_BIN="$("$PY3" -I "$ROOT/bin/node_install.py" resolve --root "$ROOT" --command node --status-file "$BOOT_STATUS")" || {
    echo "server_runner: incomplete pinned Node runtime" >&2; exit 69; }
fi
# Read the server binary setting only after the pinned-runtime validation.
# There is deliberately NO default binary: absent an explicit config/server-bin
# (legacy rollback) or a complete packed runtime, guessing one would exec an
# unvalidated binary outside this root — the pre-lane default reached into the
# Chairman's ~/.t3 (attack finding 12). Fail loudly instead.
#
# Panel R2: config/server-bin boots ONLY in rollback mode (receipts absent).
# With the packed receipts installed it is not an override — a writer of that
# one file would otherwise redirect every KeepAlive boot to any in-root file.
# It must name exactly the receipt-resolved entrypoint; a contradiction
# refuses here, at boot, naming both paths (resolve itself now also
# digest-verifies the packed server tree, panel R1).
SERVER_BIN=""
if [ "$PACKED" -eq 1 ]; then
  stage resolve-server
  RESOLVED="$("$PY3" -I "$ROOT/bin/node_install.py" resolve --root "$ROOT" --command serve --status-file "$BOOT_STATUS")" || {
    echo "server_runner: packed runtime incomplete (resolve failed)" >&2; exit 69; }
  if [ -s "$BIN_CONF" ]; then
    NAMED=$(head -1 "$BIN_CONF" 2>/dev/null)
    if [ "$NAMED" != "$RESOLVED" ]; then
      echo "server_runner: REFUSED config/server-bin names '$NAMED' but the packed receipts resolve to '$RESOLVED' — remove config/server-bin, or follow the runbook's 'Going back' to run another binary" >&2
      exit 69
    fi
  fi
  SERVER_BIN="$RESOLVED"
elif [ -s "$BIN_CONF" ]; then
  SERVER_BIN=$(head -1 "$BIN_CONF" 2>/dev/null)
else
  echo "server_runner: no server binary configured ($BIN_CONF missing and no packed runtime); refusing to guess a default" >&2
  exit 78
fi
[ -f "$SERVER_BIN" ] || { echo "server_runner: server entrypoint missing: $SERVER_BIN" >&2; exit 69; }

# flock survives execve (fd is made inheritable), so the lock is held for the
# whole server lifetime; launchd retries every ThrottleInterval while held out.
export NODE_BIN
export BOOT_STATUS
stage lock-port
exec "$PY3" -I - "$ROOT" "$SERVER_BIN" "$ENV_FILE" "$LOG_FILE" <<'PY'
import fcntl, os, sys, time

root, server_bin, env_file, log_file = sys.argv[1:5]

def _stage(name):
    # stderr goes to launchd's StandardErrorPath (server.log); boot.status is
    # the machine-readable copy install's wait loop reads (round 3 B).
    print(f"server_runner: stage {name} (handoff)", file=sys.stderr, flush=True)
    status = os.environ.get("BOOT_STATUS")
    if status:
        try:
            with open(status, "a", encoding="utf-8") as stream:
                stream.write(f"stage={name} {int(time.time())}\n")
        except OSError:
            pass

with open(env_file) as fh:
    env_rows = [ln.rstrip("\n") for ln in fh if ln.strip() and not ln.startswith("#")]

# Minimal environment: launchd may pass the installer shell's whole env (any
# unrelated provider keys) into the job; never forward it. The server env is
# exactly: the few vars a CLI needs + the root's 0600 fabric.env + T3 settings.
env = {k: v for k, v in os.environ.items()
       if k in ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "LANG", "LC_ALL")}
for row in env_rows:
    name, _, value = row.partition("=")
    if name == name.strip() and name:
        env[name] = value

lock_path = os.path.join(root, "run", "home.lock")
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("server_runner: REFUSED another server already holds the lock for this home", flush=True)
    sys.exit(42)
os.set_inheritable(fd, True)

port_file = os.path.join(root, "run", "port")
try:
    port = open(port_file).read().strip()
except OSError:
    print("server_runner: REFUSED missing port file %s (install first)" % port_file, flush=True)
    sys.exit(78)
# F21: a canonical decimal port only — an empty or leading-zero port file
# must refuse here, not ride into T3CODE_PORT.
if not (port.isdecimal() and not port.startswith("0")
        and 1024 <= int(port) <= 65535):
    print("server_runner: REFUSED non-canonical port %r in %s (re-run install)" % (port, port_file), flush=True)
    sys.exit(78)

env["T3CODE_HOME"] = os.path.join(root, "home")
env["T3CODE_PORT"] = port
env["T3CODE_HOST"] = "127.0.0.1"
env["T3CODE_NO_BROWSER"] = "1"
os.chdir(os.path.join(root, "scratch-project"))
_stage("exec-server")   # past this line the server itself owns the answer
node_bin = os.environ.get("NODE_BIN")
if node_bin:
    env["PATH"] = os.path.dirname(node_bin) + ":/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    os.execve(node_bin, [node_bin, server_bin, "serve"], env)
os.execve(server_bin, [server_bin, "serve"], env)
PY
