"""Behaviour tests for the hardened tools/mmos_team_server/team_server.sh.

Harness (see ri-d childB notes): a temp dir with controlled PATH and a
redirected HOME. `id -u` is faked to 59999, a uid with no launchd domain, so
the tool's ABSOLUTE `/bin/launchctl bootstrap gui/<uid>` is a harmless refusal
and every PATH `launchctl` call lands on fake_launchctl.py, which really starts
the installed runner (so the fake server really binds 127.0.0.1, really answers
200 and really writes its banner into run/server.log).

Never touches the real ~/Library/LaunchAgents, the real label
com.mastermind.t3-team, port 3780, or ~/.t3.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "mmos_team_server" / "team_server.sh"
T3DEV = REPO / "tools" / "mmos_dev" / "t3_dev.sh"
NODE_INSTALL = REPO / "tools" / "mmos_team_server" / "node_install.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "mmos_ops"
PY = "/opt/homebrew/bin/python3.12"
LABEL = "com.mastermind.t3-team-test"
SENTINEL = "FAKE-PAIRING-SECRET-SENTINEL"
BASE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def connect_ok(port, timeout=0.2):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def http_code(port):
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"http://127.0.0.1:{port}/"],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "000"
    return (out.stdout or "").strip() or "000"


def wait_for(predicate, seconds=10.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def load_node_install():
    import importlib.util
    spec = importlib.util.spec_from_file_location("mmos_ops_node_install", NODE_INSTALL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------

class Harness:
    """A throwaway HOME + PATH + fake launchd state for one test."""

    def __init__(self, base: Path):
        self.base = base
        self.home = base / "home"
        self.bindir = base / "bin"
        self.state = base / "launchd-state"
        self.root = base / "server-root"
        self.port = free_port()
        self._children = []
        for d in (self.home, self.bindir, self.state):
            d.mkdir(parents=True, exist_ok=True)
        self._install_fakes()

    # -- environment ------------------------------------------------------
    def _install_fakes(self):
        (self.bindir / "id").write_text(FIX.joinpath("fake_id").read_text())
        os.chmod(self.bindir / "id", 0o755)
        (self.bindir / "sleep").write_text(FIX.joinpath("fake_sleep").read_text())
        os.chmod(self.bindir / "sleep", 0o755)
        launchctl = self.bindir / "launchctl"
        launchctl.write_text(
            "#!/bin/sh\n"
            f"exec {PY} {FIX / 'fake_launchctl.py'} \"$@\"\n")
        os.chmod(launchctl, 0o755)

    def env(self, **extra):
        env = {
            "PATH": f"{self.bindir}:{BASE_PATH}",
            "HOME": str(self.home),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
            "FAKE_LAUNCHCTL_STATE": str(self.state),
            "LANG": "en_US.UTF-8",
        }
        env.update(extra)
        return env

    # -- fixtures on disk -------------------------------------------------
    def seed_root(self, mode=0o700):
        self.root.mkdir(mode=mode, exist_ok=True)
        os.chmod(self.root, mode)
        (self.root / "config").mkdir(exist_ok=True)
        (self.root / "run").mkdir(exist_ok=True)
        # The installed runner requires the absolute interpreter install
        # records (config/python3-path); team_server.sh does not write it.
        (self.root / "config" / "python3-path").write_text(PY + "\n")
        fabric = self.root / "fabric.env"
        fabric.write_text("ANTHROPIC_BASE_URL=http://127.0.0.1:1\n")
        os.chmod(fabric, 0o600)
        return self.root

    def fake_server(self, python_body: Path | None = None):
        """A server binary: a sh wrapper so the shebang does not need PATH."""
        target = self.base / "fake-t3-server"
        body = python_body or (FIX / "fake_t3_server.py")
        target.write_text(f"#!/bin/sh\nexec {PY} {body} \"$@\"\n")
        os.chmod(target, 0o755)
        return target

    # -- running the tool -------------------------------------------------
    def run(self, *args, timeout=120):
        return subprocess.run(
            ["/bin/sh", str(TOOL), *map(str, args)],
            capture_output=True, text=True, env=self.env(), timeout=timeout)

    def run_install(self, *extra, timeout=180):
        return self.run("install", "--root", self.root, "--port", self.port,
                        "--label", LABEL, *extra, timeout=timeout)

    # -- observations -----------------------------------------------------
    def plist(self):
        return self.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    def loaded(self):
        return (self.state / f"{LABEL}.loaded").exists()

    def log(self):
        path = self.root / "run" / "server.log"
        return path.read_text(errors="replace") if path.exists() else ""

    # -- cleanup ----------------------------------------------------------
    def hold_port(self, port):
        """A foreign listener: binds the port, prints no banner, serves nothing.

        It must ACCEPT: the tool's stop loop samples the port up to ten times
        back to back, and a listener that only ever queues would exhaust its
        backlog and start refusing the later probes (macOS answers a full
        accept queue with ECONNREFUSED), which would read as "port free".
        """
        script = (
            "import socket,sys,threading\n"
            "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
            "s.bind(('127.0.0.1',int(sys.argv[1])));s.listen(64)\n"
            "def loop():\n"
            "    while True:\n"
            "        try: c,_=s.accept()\n"
            "        except OSError: return\n"
            "        c.close()\n"
            "threading.Thread(target=loop,daemon=True).start()\n"
            "import time;time.sleep(120)\n")
        proc = subprocess.Popen([PY, "-c", script, str(port)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._children.append(proc)
        assert wait_for(lambda: connect_ok(port), 10), "foreign listener never bound"
        return proc

    def cleanup(self):
        for proc in self._children:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        # Tear down whatever the fake launchd thinks is loaded.
        for marker in self.state.glob("*.loaded"):
            label = marker.name[: -len(".loaded")]
            subprocess.run(
                [str(self.bindir / "launchctl"), "bootout", f"gui/59999/{label}"],
                capture_output=True, env=self.env(), timeout=30)
        for pidfile in self.state.glob("*.pid"):
            try:
                os.kill(int(pidfile.read_text().strip()), 15)
            except (OSError, ValueError):
                pass


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path / "harness")
    harness.seed_root()
    try:
        yield harness
    finally:
        harness.cleanup()


# --------------------------------------------------------------------------
# 1. install --replace success
# --------------------------------------------------------------------------

def test_install_replace_success(h):
    server = h.fake_server()
    first = h.run_install("--server-bin", server)
    assert first.returncode == 0, first.stderr

    proc = h.run_install("--server-bin", server, "--replace")
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr

    assert f"INSTALLED label={LABEL} root={h.root} port={h.port} server_bin={server}" in out
    assert f"pairing access saved to {h.root}/run/access.txt" in out
    # The credential is never echoed by the tool itself.
    assert SENTINEL not in out and SENTINEL not in proc.stderr

    assert (h.root / "config" / "server-bin").read_text().strip() == str(server)
    assert h.plist().is_file()
    assert f"<string>{h.root}/bin/server_runner.sh</string>" in h.plist().read_text()

    access = h.root / "run" / "access.txt"
    assert access.is_file()
    assert oct(access.stat().st_mode & 0o777) == "0o600"
    assert "Pairing URL:" in access.read_text()

    # The fake launchd really bootstrapped the job and the installed runner
    # really started the server: a live 200 and the banner in the log.
    assert h.loaded()
    assert wait_for(lambda: http_code(h.port) == "200", 15)
    assert "Pairing URL:" in h.log()
    assert SENTINEL in h.log()  # the server printed it; the tool did not


# --------------------------------------------------------------------------
# 2. install with a server that never answers -> truthful failure
# --------------------------------------------------------------------------

def test_install_never_answering_server_is_truthful_and_cleans_up(h):
    silent = h.fake_server(FIX / "fake_t3_silent.py")
    proc = h.run_install("--server-bin", silent)

    assert proc.returncode != 0
    assert "INSTALLED" not in proc.stdout
    assert f"server did not answer on 127.0.0.1:{h.port}" in proc.stderr
    assert "the label was unloaded" in proc.stderr
    # The cleanup really happened: the fake launchd holds no marker.
    assert not h.loaded()
    assert not connect_ok(h.port)
    assert not (h.root / "run" / "access.txt").exists()


# --------------------------------------------------------------------------
# 3. stop on a loaded + answering server
# --------------------------------------------------------------------------

def test_stop_loaded_answering_server(h):
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    assert h.loaded()

    proc = h.run("stop", "--root", h.root, "--label", LABEL)
    assert proc.returncode == 0, proc.stderr
    assert f"STOPPED label={LABEL} port={h.port} free" in proc.stdout
    assert not h.loaded()
    assert wait_for(lambda: not connect_ok(h.port), 10)


# --------------------------------------------------------------------------
# 4. stop while something else still holds the port
# --------------------------------------------------------------------------

def test_stop_reports_foreign_port_holder(h):
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0

    # Take the job out of launchd's hands and put a foreign listener on the
    # port: the label is unloaded, the port is not ours any more.
    subprocess.run([str(h.bindir / "launchctl"), "bootout", f"gui/59999/{LABEL}"],
                   capture_output=True, env=h.env(), timeout=30)
    assert wait_for(lambda: not h.loaded(), 10)
    assert wait_for(lambda: not connect_ok(h.port), 10)
    h.hold_port(h.port)

    proc = h.run("stop", "--root", h.root, "--label", LABEL)
    assert proc.returncode == 1
    assert f"port {h.port} is still held" in proc.stderr
    assert "lsof" in proc.stderr


# --------------------------------------------------------------------------
# 5. doctor on the running fake instance
# --------------------------------------------------------------------------

def _plant_packed_runtime(harness):
    """A synthetic but receipt-consistent packed runtime under the root."""
    node_install = load_node_install()
    root = harness.root
    prefix = f"node-v{node_install.VERSION}-darwin-arm64"
    install_dir = root / "runtime" / prefix
    (install_dir / "bin").mkdir(parents=True)
    node = install_dir / "bin" / "node"
    node.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(node, 0o755)
    (install_dir / "lib").mkdir()
    (install_dir / "lib" / "stamp").write_text("fake pinned tree\n")

    build = root / "runtime" / "packed" / "dist"
    for name in node_install.REQUIRED_DIST_FILES:
        target = build / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")

    tree = node_install.tree_sha256(install_dir)
    receipt = {
        "schemaVersion": node_install.SCHEMA_VERSION,
        "kind": "official-nodejs-install",
        "version": "v" + node_install.VERSION,
        "architecture": "arm64",
        "platform": "darwin",
        "nodePath": str(node),
        "installDir": str(install_dir),
        "archiveSha256": node_install.OFFICIAL_SHA256,
        "treeSha256": tree,
    }
    payload = json.dumps(receipt, indent=2) + "\n"
    (install_dir / "INSTALL_RECEIPT.json").write_text(payload)
    (root / "config" / "node-runtime.json").write_text(payload)
    (root / "config" / "server-runtime.json").write_text(json.dumps({
        "schemaVersion": node_install.SCHEMA_VERSION,
        "serverBin": str(build / "bin.mjs"),
        "buildDir": str(build),
    }))
    return receipt


def test_doctor_on_running_instance(h):
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    _plant_packed_runtime(h)
    assert wait_for(lambda: http_code(h.port) == "200", 15)

    proc = h.run("doctor", "--root", h.root, "--label", LABEL)
    assert "Traceback" not in proc.stdout + proc.stderr
    assert "doctor_error=" not in proc.stdout
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "loaded=yes" in proc.stdout
    assert f"port={h.port}" in proc.stdout
    assert f"answeringPort={h.port}" in proc.stdout
    assert SENTINEL not in proc.stdout


# --------------------------------------------------------------------------
# 6. --server-bin rollback after the packed-runtime receipts are moved aside
# --------------------------------------------------------------------------

def test_server_bin_rollback(h):
    # Incomplete receipts: default (packed) resolution must refuse.
    (h.root / "config" / "server-runtime.json").write_text("{}\n")
    (h.root / "config" / "node-runtime.json").write_text("{}\n")
    server = h.fake_server()

    default = h.run_install()
    assert default.returncode != 0
    assert "INSTALLED" not in default.stdout
    assert "packed runtime unavailable" in default.stderr

    # Move the receipts aside and roll back to an explicit server binary.
    for name in ("server-runtime.json", "node-runtime.json"):
        shutil.move(h.root / "config" / name, h.root / "config" / (name + ".aside"))

    proc = h.run_install("--server-bin", server, "--replace")
    assert proc.returncode == 0, proc.stderr
    assert f"server_bin={server}" in proc.stdout
    assert (h.root / "config" / "server-bin").read_text().strip() == str(server)
    assert not (h.root / "config" / "server-runtime.json").exists()
    assert wait_for(lambda: http_code(h.port) == "200", 15)
    assert "Pairing URL:" in h.log()


# --------------------------------------------------------------------------
# 7. F9: a broken guard must fail each tool's own selftest
# --------------------------------------------------------------------------

def _repo_skeleton(tmp_path):
    """A minimal repo copy so the tools keep resolving REPO_DIR and the library."""
    ske = tmp_path / "skeleton"
    (ske / "tools" / "mmos_team_server").mkdir(parents=True)
    (ske / "tools" / "mmos_dev").mkdir(parents=True)
    shutil.copy2(TOOL, ske / "tools" / "mmos_team_server" / "team_server.sh")
    shutil.copy2(T3DEV, ske / "tools" / "mmos_dev" / "t3_dev.sh")
    return ske


def _break_port_forbidden(path):
    text = path.read_text()
    broken = text.replace(
        'case "$FORBIDDEN_PORTS" in *" $1 "*) return 0 ;; esac',
        'case "$FORBIDDEN_PORTS" in *" $1 "*) return 1 ;; esac')
    assert broken != text, "guard snippet not found; test would be vacuous"
    path.write_text(broken)


def test_f9_selftest_detects_broken_guard(h, tmp_path):
    ske = _repo_skeleton(tmp_path)
    tool = ske / "tools" / "mmos_team_server" / "team_server.sh"
    dev = ske / "tools" / "mmos_dev" / "t3_dev.sh"

    def selftest(script, **env):
        return subprocess.run(["/bin/sh", str(script), "selftest"],
                              capture_output=True, text=True,
                              env=h.env(**env), timeout=90)

    # Unmodified: both selftests pass in this harness.
    healthy = selftest(tool)
    assert healthy.returncode == 0, healthy.stdout + healthy.stderr
    assert "selftest_fail=0" in healthy.stdout

    dev_home = tmp_path / "dev-root"
    (dev_home / "run").mkdir(parents=True)
    env_file = dev_home / "fabric.env"
    env_file.write_text("X=1\n")
    os.chmod(env_file, 0o600)
    fake_bin = tmp_path / "t3"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(fake_bin, 0o755)
    healthy_dev = selftest(dev, MMOS_T3_DEV_ROOT=str(dev_home), T3_BIN=str(fake_bin))
    assert healthy_dev.returncode == 0, healthy_dev.stdout + healthy_dev.stderr
    assert "selftest_fail=0" in healthy_dev.stdout

    # team_server.sh with the shared guard broken.
    _break_port_forbidden(dev)
    broken = selftest(tool)
    assert broken.returncode != 0
    assert "selftest_fail=1" in broken.stdout
    assert "guard 3773 forbidden: FAIL" in broken.stdout

    # t3_dev.sh's own selftest with the same guard broken.
    dev_broken = selftest(dev, MMOS_T3_DEV_ROOT=str(dev_home), T3_BIN=str(fake_bin))
    assert dev_broken.returncode != 0
    assert "selftest_fail=1" in dev_broken.stdout
    assert "guard 3773 forbidden: FAIL" in dev_broken.stdout


# --------------------------------------------------------------------------
# 8. F16: a failed capture never truncates the live credential
# --------------------------------------------------------------------------

def test_f16_failed_capture_preserves_access_file(h, tmp_path):
    log = tmp_path / "server.log"
    log.write_text("starting up\nno banner here\n")
    access = tmp_path / "access.txt"
    sentinel = b"OLD PAIRING URL http://127.0.0.1:1/?token=SENTINEL-KEEP-ME\n"
    access.write_bytes(sentinel)
    os.chmod(access, 0o600)

    # Source the real library directly; it only defines functions in lib mode.
    script = (
        f'T3_DEV_LIB_ONLY=1 . "{T3DEV}"\n'
        f'LOG_FILE="{log}"\n'
        f'ACCESS_FILE="{access}"\n'
        'capture_access_dev; echo "rc=$?"\n'
    )
    proc = subprocess.run(["/bin/sh", "-c", script], capture_output=True,
                          text=True, env=h.env(), timeout=90)
    assert "rc=1" in proc.stdout, proc.stdout + proc.stderr
    # Byte-identical: nothing truncated or replaced.
    assert access.read_bytes() == sentinel
    assert not (tmp_path / "access.txt.new").exists()


# --------------------------------------------------------------------------
# TSHc attack round: capture / stop / missing-curl truthfulness
# --------------------------------------------------------------------------

def test_capture_refuses_dead_banner_on_stopped_server(h):
    # Attack finding 5: after a stop the log still holds the old banner; its
    # one-time token is dead. capture must not install it as the credential
    # and report success.
    server = h.fake_server()
    proc = h.run_install("--replace", "--server-bin", server)
    assert "INSTALLED" in proc.stdout, proc.stdout + proc.stderr
    access = h.root / "run" / "access.txt"
    assert access.is_file()
    before = access.read_text()
    h.run("stop", "--root", h.root, "--label", LABEL)
    proc = h.run("capture", "--root", h.root, "--label", LABEL, timeout=120)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "dead" in (proc.stdout + proc.stderr)
    assert access.read_text() == before


def test_stop_names_the_foreign_port_holder_pid(h):
    # Attack finding 7: "unknown owner" sent the operator hunting a process
    # that was about to vanish (our own closing server). A genuinely foreign
    # holder must be named by pid.
    server = h.fake_server()
    h.run_install("--replace", "--server-bin", server)
    subprocess.run([str(h.bindir / "launchctl"), "bootout", f"gui/59999/{LABEL}"],
                   capture_output=True, env=h.env(), timeout=30)
    holder = h.hold_port(h.port)
    try:
        proc = h.run("stop", "--root", h.root, "--label", LABEL, timeout=120)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "unknown owner" not in proc.stderr
        assert f"pid {holder.pid}" in proc.stderr
    finally:
        holder.terminate()


def _lock_holder(path):
    return subprocess.Popen(
        [PY, "-c",
         "import fcntl, sys, time\n"
         "fd = open(sys.argv[1], 'a+')\n"
         "fcntl.flock(fd, fcntl.LOCK_EX)\n"
         "time.sleep(300)\n", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _lock_is_held(path):
    return subprocess.run(
        [PY, "-c",
         "import fcntl, sys\n"
         "try:\n"
         "    fd = open(sys.argv[1], 'a+')\n"
         "    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
         "except OSError:\n"
         "    sys.exit(1)\n", str(path)]).returncode == 1


def test_stop_without_port_file_refuses_while_lock_held(h):
    # Attack finding 8: "STOPPED (no port file)" asserted the server was down
    # without checking anything. A holder of run/home.lock (a server started
    # outside launchd) must not be reported stopped.
    server = h.fake_server()
    h.run_install("--replace", "--server-bin", server)
    subprocess.run([str(h.bindir / "launchctl"), "bootout", f"gui/59999/{LABEL}"],
                   capture_output=True, env=h.env(), timeout=30)
    (h.root / "run" / "port").unlink()
    holder = _lock_holder(h.root / "run" / "home.lock")
    h._children.append(holder)
    assert wait_for(lambda: _lock_is_held(h.root / "run" / "home.lock"), 10), \
        "lock holder never took the lock"
    proc = h.run("stop", "--root", h.root, "--label", LABEL, timeout=120)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "home.lock" in proc.stderr


def test_install_dies_early_without_curl(h, tmp_path):
    # Attack finding 9: a missing curl made wait_http spin the full window and
    # report "server did not answer" — with the server possibly healthy the
    # whole time (and then taken down). The tool must name the missing
    # prerequisite in one line, before touching launchd.
    server = h.fake_server()
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("grep", "sed", "stat", "awk", "tail", "cat", "mv", "rm",
                 "chmod", "cp", "mkdir", "ln", "env", "head", "basename",
                 "dirname"):
        src = shutil.which(name)
        if src:
            os.symlink(src, stubs / name)
    env = h.env()
    env["PATH"] = f"{h.bindir}:{stubs}:/bin"
    proc = subprocess.run(
        ["/bin/sh", str(TOOL), "install", "--root", str(h.root),
         "--port", str(h.port), "--label", LABEL, "--replace",
         "--server-bin", str(server)],
        capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "curl not found" in proc.stderr
    # the refusal fired before launchd: nothing was started
    assert not h.loaded()
