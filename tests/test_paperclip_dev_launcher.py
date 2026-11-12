"""Launcher tests for tools/mmos_dev/paperclip_dev.sh (deputy ruling 14).

The process layer is fully faked: ``node``, ``lsof``, ``ps``, ``pgrep``,
``nc`` and ``curl`` are stub scripts placed on PATH, and the fake ``node``
prints a canned startup banner into the real server log and then idles.
No real Paperclip board is started, no socket is ever opened, and nothing
ever connects to port 54329 — the refusal scenarios are carried entirely by
the stub state files that the fake ``lsof`` reads.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "mmos_dev" / "paperclip_dev.sh"

SERVER_PORT = 3931
DB_PORT = 5493
INSTANCE_ID = "pcdev-test"

BANNER_RULE = "  ───────────────────────────────────────────────────────"


# ---------------------------------------------------------------------------
# Fake process layer
# ---------------------------------------------------------------------------

NODE_STUB = r'''
set -u
echo $$ > "$FAKE_STATE_DIR/node.pid"
{
  echo "PAPERCLIP_HOME=$PAPERCLIP_HOME"
  echo "PAPERCLIP_CONFIG=$PAPERCLIP_CONFIG"
  echo "PAPERCLIP_INSTANCE_ID=$PAPERCLIP_INSTANCE_ID"
  echo "HOME=$HOME"
  echo "launcher_arg=$1"
  echo "DATABASE_URL=${DATABASE_URL-}"
  echo "PAPERCLIP_SERVER_PORT=${PAPERCLIP_SERVER_PORT-}"
  echo "PAPERCLIP_DISABLE_CWD_ENV_FILE=${PAPERCLIP_DISABLE_CWD_ENV_FILE-}"
} > "$FAKE_STATE_DIR/launch-env"
mkdir -p "$FAKE_STATE_DIR/cmd" "$FAKE_STATE_DIR/listeners" "$FAKE_STATE_DIR/children" "$FAKE_STATE_DIR/conn"
echo $$ > "$FAKE_STATE_DIR/listeners/$FAKE_SERVER_PORT"
PG_PID=$(( $$ + 40000 ))
echo "$PG_PID" > "$FAKE_STATE_DIR/listeners/$FAKE_DB_PORT_EFFECTIVE"
echo "$PG_PID" > "$FAKE_STATE_DIR/children/$$"
printf 'node %s\n' "$1" > "$FAKE_STATE_DIR/cmd/$$"
printf 'postgres -D %s -p %s\n' "$FAKE_PG_DATADIR" "$FAKE_DB_PORT_EFFECTIVE" > "$FAKE_STATE_DIR/cmd/$PG_PID"
if [ "${FAKE_CONN_54329:-0}" = "1" ]; then
  printf 'node  %su  IPv4  TCP 127.0.0.1:%s->127.0.0.1:54329 (ESTABLISHED)\n' "$$" "$FAKE_DB_PORT_EFFECTIVE" \
    > "$FAKE_STATE_DIR/conn/$$-54329"
fi
if [ "${FAKE_NO_BANNER:-0}" != "1" ]; then
  cat "$FAKE_BANNER_FILE"
fi
touch "$FAKE_STATE_DIR/started"
trap 'exit 0' TERM INT
while :; do sleep 0.2 2>/dev/null || sleep 1; done
'''

LSOF_STUB = r'''
case " $* " in
  *" -a "*)
    pid=""; port=""
    prev=""
    for a in "$@"; do
      [ "$prev" = "-p" ] && pid="$a"
      case "$a" in -iTCP:*) port="${a#-iTCP:}" ;; esac
      prev="$a"
    done
    [ -n "$pid" ] && [ -f "$FAKE_STATE_DIR/conn/$pid-$port" ] && cat "$FAKE_STATE_DIR/conn/$pid-$port"
    exit 0
    ;;
  *-tiTCP:*)
    port=""
    for a in "$@"; do
      case "$a" in -tiTCP:*) port="${a#-tiTCP:}" ;; esac
    done
    [ -n "$port" ] && [ -f "$FAKE_STATE_DIR/listeners/$port" ] && cat "$FAKE_STATE_DIR/listeners/$port"
    exit 0
    ;;
esac
exit 0
'''

PS_STUB = r'''
[ "${1:-}" = "-p" ] || exit 1
[ -f "$FAKE_STATE_DIR/cmd/$2" ] && cat "$FAKE_STATE_DIR/cmd/$2"
exit 0
'''

PGREP_STUB = r'''
[ "${1:-}" = "-P" ] || exit 1
[ -f "$FAKE_STATE_DIR/children/$2" ] && cat "$FAKE_STATE_DIR/children/$2"
exit 0
'''

NC_STUB = "exit 1\n"

CURL_STUB = r'''
case "$*" in
  */api/health*)
    s=0
    if [ -f "$FAKE_STATE_DIR/started" ]; then
      # Health answers only while the fake server process is alive (or when
      # no node has ever run in this state dir, i.e. a foreign server).
      npid="$(cat "$FAKE_STATE_DIR/node.pid" 2>/dev/null || true)"
      if [ -z "$npid" ] || kill -0 "$npid" 2>/dev/null; then
        if [ ! -f "$FAKE_STATE_DIR/curl-down" ]; then s=1; fi
      fi
    fi
    echo "health started=$s" >> "$FAKE_STATE_DIR/curl-calls"
    if [ "$s" = "1" ]; then
      printf '{"status":"ok"}\n'
      exit 0
    fi
    exit 7
    ;;
esac
echo "other: $*" >> "$FAKE_STATE_DIR/curl-calls"
exit 7
'''


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@dataclass
class Harness:
    dev_home: Path
    state: Path
    banner_file: Path
    env: dict = field(default_factory=dict)

    @property
    def instance_root(self) -> Path:
        return self.dev_home / "instances" / INSTANCE_ID

    def write_banner(self, *, config_path: str | None = None, db_dir: str | None = None,
                     pg_port: int | None = None) -> None:
        """Canned startup banner; defaults name the dev instance."""
        config_path = config_path or str(self.instance_root / "config.json")
        db_dir = db_dir or str(self.instance_root / "db")
        pg_port = DB_PORT if pg_port is None else pg_port
        self.banner_file.write_text(
            "\n".join([
                BANNER_RULE,
                "Mode              embedded-postgres | static-ui",
                "Deploy            local_trusted (private)",
                f"Server            {SERVER_PORT}",
                f"Database          {db_dir} (pg:{pg_port})",
                f"Config            {config_path}",
                BANNER_RULE,
                "",
            ]),
            encoding="utf-8",
        )

    def node_pid(self) -> int:
        return int((self.state / "node.pid").read_text(encoding="utf-8").strip())

    def pidfile_pid(self) -> int:
        return int((self.instance_root / "dev-controller.pid").read_text(encoding="utf-8").strip())


def _write_stub(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture()
def harness(tmp_path: Path):
    dev_home = (tmp_path / "devhome").resolve()
    dev_home.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    for sub in ("cmd", "listeners", "children", "conn"):
        (state / sub).mkdir()
    banner_file = tmp_path / "banner.txt"

    _write_stub(bin_dir / "node", NODE_STUB)
    _write_stub(bin_dir / "lsof", LSOF_STUB)
    _write_stub(bin_dir / "ps", PS_STUB)
    _write_stub(bin_dir / "pgrep", PGREP_STUB)
    _write_stub(bin_dir / "nc", NC_STUB)
    _write_stub(bin_dir / "curl", CURL_STUB)

    fake_cli = tmp_path / "fakecli" / "paperclipai"
    fake_cli.parent.mkdir()
    _write_stub(fake_cli, "# unused on the launch path\n")
    fake_server_entry = tmp_path / "fakeserver" / "index.js"
    fake_server_entry.parent.mkdir()
    fake_server_entry.write_text("export function startServer() {}\n", encoding="utf-8")

    # Pre-seeded company state so `up` skips the company-create CLI call.
    instance_root = dev_home / "instances" / INSTANCE_ID
    instance_root.mkdir(parents=True)
    (instance_root / "dev-state.json").write_text(json.dumps({
        "schemaVersion": 1,
        "companyId": "cmp-test",
        "companyPrefix": "TST",
        "companyName": "Test",
        "apiUrl": f"http://127.0.0.1:{SERVER_PORT}",
    }), encoding="utf-8")

    h = Harness(dev_home=dev_home, state=state, banner_file=banner_file)
    h.write_banner()
    h.env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
        "MMOS_DEV_HOME": str(dev_home),
        "MMOS_DEV_INSTANCE_ID": INSTANCE_ID,
        "MMOS_DEV_SERVER_PORT": str(SERVER_PORT),
        "MMOS_DEV_DB_PORT": str(DB_PORT),
        "MMOS_DEV_PAPERCLIP_CLI": str(fake_cli),
        "MMOS_DEV_SERVER_ENTRY": str(fake_server_entry),
        "MMOS_DEV_NODE": str(bin_dir / "node"),
        "MMOS_DEV_START_TIMEOUT": "30",
        "MMOS_DEV_STOP_TIMEOUT": "8",
        "FAKE_STATE_DIR": str(state),
        "FAKE_BANNER_FILE": str(banner_file),
        "FAKE_SERVER_PORT": str(SERVER_PORT),
        "FAKE_DB_PORT_EFFECTIVE": str(DB_PORT),
        "FAKE_PG_DATADIR": str(instance_root / "db"),
    }
    yield h
    # Teardown: never leave the fake server running.
    pid_file = state / "node.pid"
    if pid_file.exists():
        try:
            os.kill(h.node_pid(), 15)
        except ProcessLookupError:
            pass


def run_up(h: Harness, **env_extra) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "up"],
        env={**h.env, **env_extra},
        capture_output=True,
        text=True,
        timeout=180,
    )


def run_down(h: Harness, **env_extra) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "down"],
        env={**h.env, **env_extra},
        capture_output=True,
        text=True,
        timeout=120,
    )


def assert_process_dead(pid: int) -> None:
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        import time
        time.sleep(0.1)
    pytest.fail(f"pid {pid} is still alive after the refusal")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_up_starts_via_direct_launcher_and_proves_isolation(harness):
    # A previous run's log is present and names the REAL store: the new run
    # must truncate it, not inherit its banner (review findings 1-2).
    logs_dir = harness.instance_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stale_log = logs_dir / "dev-server.stdout.log"
    stale_log.write_text(
        "\n".join([
            BANNER_RULE,
            f"Database          /real/home/.paperclip/instances/default/db (pg:54329)",
            BANNER_RULE,
            "",
        ]),
        encoding="utf-8",
    )

    # Hostile ambient environment: none of it may reach the launcher.
    proc = run_up(
        harness,
        DATABASE_URL="postgres://127.0.0.1:54329/real-store",
        PAPERCLIP_SERVER_PORT="3100",
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "PAPERCLIP-DEV: REAL STORE REFUSED" not in out
    # All three isolation checks ran, with evidence lines.
    assert "isolation a:" in out
    assert "isolation b:" in out
    assert "isolation c:" in out

    # The stale real-store bytes are gone: the log holds only this run.
    log_now = stale_log.read_text(encoding="utf-8")
    assert "54329" not in log_now
    assert "instances/default" not in log_now

    # The board was started by the node launcher, not by a CLI wrapper.
    launch_env = (harness.state / "launch-env").read_text(encoding="utf-8")
    pins = dict(line.split("=", 1) for line in launch_env.splitlines())
    assert pins["PAPERCLIP_HOME"] == str(harness.dev_home)
    assert pins["PAPERCLIP_CONFIG"] == str(harness.instance_root / "config.json")
    assert pins["PAPERCLIP_INSTANCE_ID"] == INSTANCE_ID
    assert pins["HOME"] == str(harness.dev_home / "home")
    assert pins["launcher_arg"].endswith("launch-server.mjs")
    assert str(harness.instance_root) in pins["launcher_arg"]
    # Ambient DATABASE_URL / PAPERCLIP_SERVER_PORT were scrubbed; the cwd
    # .env loader is disabled (review findings 3-5).
    assert pins["DATABASE_URL"] == ""
    assert pins["PAPERCLIP_SERVER_PORT"] == ""
    assert pins["PAPERCLIP_DISABLE_CWD_ENV_FILE"] == "true"

    # The generated launcher imports the server entry and calls startServer().
    launcher = harness.instance_root / "launch-server.mjs"
    assert launcher.is_file()
    assert "startServer" in launcher.read_text(encoding="utf-8")

    # Config pins the dev db port and data dir.
    config = json.loads((harness.instance_root / "config.json").read_text(encoding="utf-8"))
    assert config["database"]["embeddedPostgresPort"] == DB_PORT
    assert config["database"]["embeddedPostgresDataDir"] == str(harness.instance_root / "db")

    # The server process is alive and recorded in the pidfile.
    assert harness.pidfile_pid() == harness.node_pid()
    os.kill(harness.node_pid(), 0)  # still running


# ---------------------------------------------------------------------------
# Refusal paths (deputy ruling 14)
# ---------------------------------------------------------------------------


def test_refuses_when_launcher_tree_holds_a_socket_on_54329(harness):
    proc = run_up(harness, FAKE_CONN_54329="1")
    assert proc.returncode == 3
    assert proc.stdout.count("PAPERCLIP-DEV: REAL STORE REFUSED") == 1
    assert "54329" in proc.stderr
    assert_process_dead(harness.node_pid())


def test_refuses_when_database_listener_is_not_the_configured_port(harness):
    # The banner and the listener name one port above the configured one —
    # what the server does when its configured db port is taken.
    harness.write_banner(pg_port=DB_PORT + 1)
    proc = run_up(harness, FAKE_DB_PORT_EFFECTIVE=str(DB_PORT + 1))
    assert proc.returncode == 3
    assert proc.stdout.count("PAPERCLIP-DEV: REAL STORE REFUSED") == 1
    assert str(DB_PORT) in proc.stderr
    assert "isolation a:" in proc.stdout  # check (a) ran and passed first
    assert_process_dead(harness.node_pid())


def test_refuses_when_banner_names_default_instance_path(harness):
    default_root = Path.home() / ".paperclip" / "instances" / "default"
    harness.write_banner(
        config_path=str(default_root / "config.json"),
        db_dir=str(default_root / "db"),
    )
    proc = run_up(harness)
    assert proc.returncode == 3
    assert proc.stdout.count("PAPERCLIP-DEV: REAL STORE REFUSED") == 1
    assert "instances/default" in proc.stderr
    # The banner was read BEFORE any request: every health call the script
    # made happened before the fake node started.
    calls = (harness.state / "curl-calls").read_text(encoding="utf-8").splitlines()
    assert calls, "expected at least the pre-launch identity probe"
    assert all("started=0" in c for c in calls), calls
    assert_process_dead(harness.node_pid())


def test_refuses_when_banner_names_real_db_port(harness):
    harness.write_banner(pg_port=54329)
    proc = run_up(harness, FAKE_DB_PORT_EFFECTIVE="54329")
    assert proc.returncode == 3
    assert proc.stdout.count("PAPERCLIP-DEV: REAL STORE REFUSED") == 1
    assert "54329" in proc.stderr
    assert_process_dead(harness.node_pid())


# ---------------------------------------------------------------------------
# Identity of the listener
# ---------------------------------------------------------------------------


def test_foreign_listener_on_our_port_is_refused_not_adopted(harness):
    # A listener with the OLD launcher's argv (the CLI wrapper) must no
    # longer count as ours; `up` refuses to adopt the port.
    foreign_pid = 424242
    harness.state.joinpath("started").touch()  # health answers before our launch
    harness.state.joinpath("listeners", str(SERVER_PORT)).write_text(
        f"{foreign_pid}\n", encoding="utf-8")
    harness.state.joinpath("cmd", str(foreign_pid)).write_text(
        f"paperclipai run -d {harness.dev_home} -i {INSTANCE_ID}\n", encoding="utf-8")
    proc = run_up(harness)
    assert proc.returncode == 1
    assert "foreign" in proc.stderr
    assert not (harness.state / "node.pid").exists()  # nothing was launched


def test_stale_banner_from_a_previous_run_does_not_satisfy_the_checks(harness):
    # The log already holds a previous run's CLEAN dev banner, and this run's
    # node prints nothing. Without per-run truncation the old bytes would
    # satisfy banner_present/dev_markers instantly; the script must instead
    # wait for THIS run's banner, time out and kill the tree (review
    # findings 1-2).
    logs_dir = harness.instance_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "dev-server.stdout.log").write_text(
        "\n".join([
            BANNER_RULE,
            f"Server            {SERVER_PORT}",
            f"Database          {harness.instance_root / 'db'} (pg:{DB_PORT})",
            f"Config            {harness.instance_root / 'config.json'}",
            BANNER_RULE,
            "",
        ]),
        encoding="utf-8",
    )
    proc = run_up(harness, FAKE_NO_BANNER="1", MMOS_DEV_START_TIMEOUT="5")
    assert proc.returncode == 1
    assert "start banner" in proc.stderr
    assert_process_dead(harness.node_pid())
    assert not (harness.instance_root / "dev-controller.pid").exists()


def test_down_refuses_to_signal_a_reused_pid(harness):
    # Bring the board up and down normally, then poison the pidfile with a
    # live foreign pid. `down` must verify the pid's argv before signalling:
    # a reused pid (even the real service's) is refused, never killed.
    assert run_up(harness).returncode == 0
    assert run_down(harness).returncode == 0

    foreign = subprocess.Popen(["sleep", "60"])
    try:
        (harness.instance_root / "dev-controller.pid").write_text(
            f"{foreign.pid}\n", encoding="utf-8")
        proc = run_down(harness)
        assert proc.returncode == 1
        assert "refusing to signal" in proc.stderr
        assert foreign.poll() is None, "down killed a foreign pid"
    finally:
        if foreign.poll() is None:
            foreign.kill()
            foreign.wait()


# ---------------------------------------------------------------------------
# Source-level contracts
# ---------------------------------------------------------------------------


def test_script_never_invokes_the_cli_run_wrapper():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "paperclipai run" not in source
    assert "test-drive" not in source
    assert '"$PAPERCLIP_CLI" run' not in source
    # The direct-start launcher is the only launch path.
    assert "startServer" in source
    assert "launch-server.mjs" in source
