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
ENV_FILE="$ROOT/fabric.env"
BIN_CONF="$ROOT/config/server-bin"
CAP_CONF="$ROOT/config/log-cap"
SCRATCH="$ROOT/scratch-project"
CAP=52428800   # 50 MiB default
# launchd passes NO environment, so a cap set via TEAM_SERVER_LOG_CAP at
# install time never reaches the runner; the root's own config file does.
if [ -s "$CAP_CONF" ]; then
  CAP=$(head -1 "$CAP_CONF")
  case "$CAP" in ''|*[!0-9]*) CAP=52428800 ;; esac
elif [ -n "${TEAM_SERVER_LOG_CAP:-}" ]; then
  CAP="$TEAM_SERVER_LOG_CAP"
fi

mkdir -p "$RUN_DIR" "$SCRATCH" 2>/dev/null || true
[ -f "$ENV_FILE" ] || { echo "server_runner: missing $ENV_FILE (seed the root first)" >&2; exit 78; }

# Bound the log before the server can add more (crash-loop disk-fill guard).
if [ -f "$LOG_FILE" ] && [ "$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$CAP" ]; then
  : > "$LOG_FILE" || true
fi
chmod 600 "$LOG_FILE" 2>/dev/null || true

# Read the server binary setting (default: the stock vendor CLI).
SERVER_BIN="$HOME/.t3/bin/t3"
if [ -s "$BIN_CONF" ]; then
  SERVER_BIN=$(cat "$BIN_CONF")
fi
[ -x "$SERVER_BIN" ] || { echo "server_runner: server binary not executable: $SERVER_BIN" >&2; exit 69; }

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PYTHON3=$(command -v python3 || echo /usr/bin/python3)

# flock survives execve (fd is made inheritable), so the lock is held for the
# whole server lifetime; launchd retries every ThrottleInterval while held out.
exec "$PYTHON3" - "$ROOT" "$SERVER_BIN" "$ENV_FILE" "$LOG_FILE" <<'PY'
import fcntl, os, sys

root, server_bin, env_file, log_file = sys.argv[1:5]
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

env["T3CODE_HOME"] = os.path.join(root, "home")
env["T3CODE_PORT"] = port
env["T3CODE_HOST"] = "127.0.0.1"
env["T3CODE_NO_BROWSER"] = "1"
os.chdir(os.path.join(root, "scratch-project"))
os.execve(server_bin, [server_bin, "serve"], env)
PY
