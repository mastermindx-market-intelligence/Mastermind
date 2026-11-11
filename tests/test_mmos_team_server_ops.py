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
import hashlib
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


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
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
        # --state baked into argv: the tool env -i's its load/unload
        # fallbacks (round 3 FU1), which strips FAKE_LAUNCHCTL_STATE from
        # the environment — argv survives env -i.
        launchctl.write_text(
            "#!/bin/sh\n"
            f"exec {PY} {FIX / 'fake_launchctl.py'} "
            f"--state {str(self.state)!r} \"$@\"\n")
        os.chmod(launchctl, 0o755)

    def env(self, **extra):
        env = {
            "PATH": f"{self.bindir}:{BASE_PATH}",
            "HOME": str(self.home),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
            "FAKE_LAUNCHCTL_STATE": str(self.state),
            "LANG": "en_US.UTF-8",
            # Panel R8: the tools call launchctl by absolute path now; the
            # fake launchd rides the explicit MMOS_*_BIN seam — which is
            # TEST-ONLY since round 3 (FU4), so the harness flag sits here.
            "MMOS_LAUNCHCTL_BIN": str(self.bindir / "launchctl"),
            "MMOS_TEST_SEAMS": "1",
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
    def run(self, *args, timeout=120, env=None):
        return subprocess.run(
            ["/bin/sh", str(TOOL), *map(str, args)],
            capture_output=True, text=True, env=env or self.env(),
            timeout=timeout)

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

    def hold_port_http(self, port, delay=0.0, after_file=None):
        """A foreign HTTP listener: answers 200 on the port, prints no banner.

        Panel R4: a same-user process that grabs the port and answers 200
        must never stand in for this root's server. Unlike hold_port this one
        really speaks HTTP, so curl sees a live "200" that is not ours.
        after_file reproduces the panel's exact race deterministically: the
        listener binds only after that file appears (the fake launchd's
        .loaded marker, written strictly AFTER install's port_busy pre-check
        has passed), so the pre-check sees a free port every time.
        """
        script = (
            "import os,sys,time\n"
            "gate=sys.argv[2]\n"
            "if gate != '-':\n"
            "    while not os.path.exists(gate):\n"
            "        time.sleep(0.02)\n"
            f"time.sleep({delay})\n"
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        body=b'ok'; self.send_response(200); "
            "self.send_header('Content-Length', str(len(body))); "
            "        self.end_headers(); self.wfile.write(body)\n"
            "    def log_message(self,*a): pass\n"
            "ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n")
        proc = subprocess.Popen(
            [PY, "-c", script, str(port), str(after_file or "-")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._children.append(proc)
        if after_file is None:
            assert wait_for(lambda: http_code(port) == "200", 25 + delay), \
                "foreign HTTP listener never bound"
        # With a gate file the caller runs the tool next; the listener binds
        # on its own once the gate appears. Do not block here.
        return proc

    def kill_job_server(self):
        """Kill the fake launchd job's process but keep its loaded marker:
        the crash-loop window (launchd still 'has' the job, nothing serves)."""
        pidfile = self.state / f"{LABEL}.pid"
        pid = int(pidfile.read_text().strip())
        try:
            os.kill(pid, 9)
        except OSError:
            pass
        assert wait_for(lambda: not _pid_alive(pid), 10), "job server never died"

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

def _plant_packed_runtime(harness, serving: Path | None = None):
    """A synthetic but receipt-consistent packed runtime under the root.

    With `serving` (a fake-t3 fixture path) dist/bin.mjs is a real executable
    wrapper around it, so the runner goes through BOTH resolves and still
    answers HTTP — the shape install uses on a packed root."""
    node_install = load_node_install()
    root = harness.root
    prefix = f"node-v{node_install.VERSION}-darwin-arm64"
    install_dir = root / "runtime" / prefix
    (install_dir / "bin").mkdir(parents=True)
    node = install_dir / "bin" / "node"
    if serving is None:
        node.write_text("#!/bin/sh\nexit 0\n")
    else:
        # A packed boot execs NODE_BIN with [node, server_bin, "serve"]; the
        # stub plays that role by exec'ing the fake server directly — no
        # real node needed, and bin.mjs's bytes never run.
        node.write_text(f'#!/bin/sh\nexec {PY} {serving} "$@"\n')
    os.chmod(node, 0o755)
    (install_dir / "lib").mkdir()
    (install_dir / "lib" / "stamp").write_text("fake pinned tree\n")

    build = root / "runtime" / "packed" / "dist"
    recorded = []
    for name in node_install.REQUIRED_DIST_FILES:
        target = build / name
        target.parent.mkdir(parents=True, exist_ok=True)
        body = b"x"
        target.write_bytes(body)
        if name == "bin.mjs":
            os.chmod(target, 0o755)   # install --server-bin requires -x
        recorded.append({"path": name, "bytes": len(body),
                         "sha256": hashlib.sha256(body).hexdigest()})
    # Panel R1: the packed tree carries its digest list beside dist/ and the
    # post-hash BUILD_RECEIPT inside it, exactly as pack_server.mjs leaves it.
    (build / "BUILD_RECEIPT.json").write_text("{}\n")
    (root / "runtime" / "packed" / "file-digests.json").write_text(
        json.dumps(recorded, indent=2) + "\n")

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
    # Panel R8: curl is invoked by absolute path now (PATH injection alone
    # can no longer steer or break the probe) — a broken install exercises
    # the refusal through the same MMOS_*_BIN seam the harness uses for
    # launchctl: point it at a path that does not exist.
    env["MMOS_CURL_BIN"] = str(stubs / "curl")
    proc = subprocess.run(
        ["/bin/sh", str(TOOL), "install", "--root", str(h.root),
         "--port", str(h.port), "--label", LABEL, "--replace",
         "--server-bin", str(server)],
        capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "curl missing or not executable" in proc.stderr
    # the refusal fired before launchd: nothing was started
    assert not h.loaded()


# ==========================================================================
# Panel round 2 (repair round on c89427598) — R4: bind the HTTP-200 answer
# to the launchd job's pid at install, doctor and capture.
# ==========================================================================

def test_r4_install_refuses_foreign_listener_on_recorded_port(h):
    # Panel R4 (HIGH): install's success test was "some process answered 200
    # on the port". In the panel's race a same-user listener binds the port
    # AFTER the port_busy pre-check while our job crash-loops on EADDRINUSE —
    # and got INSTALLED printed over it. The listener's pid must be this
    # label's job pid (or a descendant) for INSTALLED to print.
    h.hold_port_http(h.port, after_file=h.state / f"{LABEL}.loaded")  # binds after port_busy
    slow = h.fake_server(FIX / "fake_t3_slowbind.py")  # loses the race, dies
    proc = h.run_install("--server-bin", slow, timeout=180)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "INSTALLED" not in proc.stdout
    # the refusal names the impostor and the job it does not belong to
    assert f"NOT label {LABEL}" in proc.stderr
    assert "another process" in proc.stderr
    # the crash-looping job was booted out, not left in launchd
    assert not h.loaded()


def test_r4_doctor_refuses_foreign_listener(h):
    # Panel R4 (HIGH): doctor's verdict was "label loaded + HTTP 200" with
    # nothing attributing the responder to this root's job. With our server
    # dead and a foreign 200 listener on the port, doctor must not exit 0.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    _plant_packed_runtime(h)
    assert wait_for(lambda: http_code(h.port) == "200", 15)
    h.kill_job_server()
    holder = h.hold_port_http(h.port)
    try:
        proc = h.run("doctor", "--root", h.root, "--label", LABEL, timeout=120)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "answeringProcess=foreign" in proc.stdout
        assert "doctor_error=" in proc.stdout
        assert "Traceback" not in proc.stdout + proc.stderr
    finally:
        holder.terminate()


def test_r4_capture_refuses_foreign_listener_dead_banner(h):
    # Panel R4 (capture aspect): capture's whole-log fallback trusted
    # "label loaded + port answered". With our server dead and a foreign
    # listener answering, the last logged banner is a DEAD one-time token and
    # must not be installed as the credential.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    access = h.root / "run" / "access.txt"
    assert access.is_file()
    before = access.read_text()
    h.kill_job_server()
    holder = h.hold_port_http(h.port)
    try:
        proc = h.run("capture", "--root", h.root, "--label", LABEL, timeout=120)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert access.read_text() == before
    finally:
        holder.terminate()


# ==========================================================================
# Panel repair round 2 (SCORE.md): R5-R8, LOWs 3/4/10/13, atk-7 (fake level)
# ==========================================================================

def test_r5_install_server_bin_refuses_without_python3_path(h):
    # Panel R5: `install --server-bin` on a root whose config/python3-path is
    # missing must refuse EARLY, naming runbook step 3 — not install a job
    # that crash-loops at runner exit 78 with an unreachable recovery.
    (h.root / "config" / "python3-path").unlink()
    server = h.fake_server()
    proc = h.run_install("--server-bin", server)
    assert proc.returncode != 0
    assert "INSTALLED" not in proc.stdout
    assert "step 3" in proc.stderr
    assert "python3-path" in proc.stderr
    assert not h.loaded()  # refused before anything was started


def test_r6_uninstall_truthful_when_bootout_fails(h):
    # Panel R6: uninstall must give bootout failures the same three-state
    # treatment as stop — never print UNINSTALLED over a still-loaded job.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    assert h.loaded()
    # Round 3: the state-dir marker (not the env var) — uninstall's unload
    # fallback is env -i'd now, and env -i strips the environment.
    (h.state / f"{LABEL}.BOTOUT_FAIL").write_text("1")
    proc = h.run("uninstall", "--root", h.root, "--label", LABEL)
    assert proc.returncode != 0
    assert "UNINSTALLED" not in proc.stdout
    assert h.loaded()  # the job is still there and the tool said so
    assert "still loaded" in proc.stderr or "STILL LOADED" in proc.stderr


def test_r7_start_failure_boots_the_label_out(h):
    # Panel R7: a failed `start` must not leave the label crash-looping under
    # KeepAlive — boot it out and verify, or name the loop and its recovery.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    assert h.run("stop", "--root", h.root, "--label", LABEL).returncode == 0
    holder = h.hold_port_http(h.port)  # the server can never bind
    try:
        proc = h.run("start", "--root", h.root, "--label", LABEL, timeout=120)
        assert proc.returncode != 0
        assert "INSTALLED" not in proc.stdout
        # The exact repair: the label is not left loaded/crash-looping.
        assert not h.loaded(), proc.stdout + proc.stderr
    finally:
        holder.terminate()


def test_r8_install_ignores_a_path_injected_fake_curl(h):
    # Panel R8: curl/launchctl/lsof/stat must be absolute so a PATH-injected
    # fake `curl` printing 200 cannot manufacture INSTALLED. The fake curl
    # writes a marker when invoked; it must never run.
    marker = h.base / "fake-curl-invoked"
    (h.bindir / "curl").write_text(
        "#!/bin/sh\n"
        f"echo x >> {marker}\n"
        "echo 200\n")
    os.chmod(h.bindir / "curl", 0o755)
    silent = h.fake_server(FIX / "fake_t3_silent.py")
    proc = h.run_install("--server-bin", silent, timeout=120)
    assert proc.returncode != 0
    assert "INSTALLED" not in proc.stdout
    assert f"server did not answer on 127.0.0.1:{h.port}" in proc.stderr
    assert not marker.exists()  # the fake was never invoked
    assert not h.loaded()


def test_low3_static_refusals_come_before_the_bootout(h):
    # Panel LOW 3: --replace booted the live label out BEFORE several
    # refusals — a refusal then took a previously healthy server down.
    # Static refusals (here: a foreign-held requested port) must fire first.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    assert h.loaded()
    assert wait_for(lambda: http_code(h.port) == "200", 15)
    other = free_port()
    holder = h.hold_port_http(other)
    try:
        proc = h.run("install", "--replace", "--root", h.root, "--port", other,
                     "--label", LABEL)
        assert proc.returncode != 0
        assert "INSTALLED" not in proc.stdout
        # The live label was untouched by the refusal.
        assert h.loaded(), proc.stdout + proc.stderr
        assert http_code(h.port) == "200"
    finally:
        holder.terminate()


def test_low4_plist_written_atomically_no_debris(h):
    # Panel LOW 4: the plist is written to a temp file and renamed into
    # place; success leaves no temp debris and a complete plist.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    agents = h.home / "Library" / "LaunchAgents"
    names = sorted(p.name for p in agents.iterdir())
    assert names == [f"{LABEL}.plist"], names
    body = h.plist().read_text()
    for needle in (f"<string>{LABEL}</string>",
                   f"<string>{h.root}/bin/server_runner.sh</string>",
                   f"<string>{h.root}</string>"):
        assert needle in body


def test_low10_symlink_at_run_files_refused(h):
    # Panel LOW 10: a symlink planted at run/server.log (or run/port) was
    # followed by install's truncate/chmod. Install must refuse naming the
    # symlink and leave the victim file untouched.
    victim = h.root / "victim.log"
    victim.write_text("PRECIOUS\n")
    (h.root / "run" / "server.log").symlink_to(victim)
    server = h.fake_server()
    proc = h.run_install("--server-bin", server)
    assert proc.returncode != 0
    assert "INSTALLED" not in proc.stdout
    assert "symlink" in proc.stderr
    assert victim.read_text() == "PRECIOUS\n"  # not truncated through


def test_low13_doctor_recovery_command_is_runnable(h):
    # Panel LOW 13: post-rollback, doctor's printed recovery must be
    # executable as written — step 6 without --server-bin refuses because
    # the receipts doctor itself demanded are gone. The printed command must
    # name the rollback binary, and running it must work.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    assert h.run("stop", "--root", h.root, "--label", LABEL).returncode == 0
    # Rollback root: no server receipt, config/server-bin present.
    assert not (h.root / "config" / "server-runtime.json").exists()

    proc = h.run("doctor", "--root", h.root, "--label", LABEL, timeout=120)
    assert proc.returncode == 1
    assert "treeVerified=none(rollback)" in proc.stdout
    line = next(l for l in proc.stdout.splitlines()
                if l.startswith("doctor_error=label not loaded"))
    # Extract the command between the parentheses and RUN it verbatim.
    cmd = line.split("(", 1)[1].rsplit(")", 1)[0]
    assert f"--server-bin {server}" in cmd, line
    words = cmd.split()
    assert words[0] == "team_server.sh"
    assert words[1] == "install"
    assert f"--root {h.root}" in cmd and f"--label {LABEL}" in cmd
    assert f"--port {h.port}" in cmd
    assert h.run(*words[1:], timeout=120).returncode == 0, line
    assert h.loaded()
    assert h.run("doctor", "--root", h.root, "--label", LABEL,
                 timeout=120).returncode == 0


def test_atk7_doctor_names_a_foreign_plist(h):
    # Panel atk-7 (fake-launchd level): the loaded job's plist is not this
    # root's plist — a squat from /tmp. doctor must say which plist the job
    # runs from and refuse to call it healthy.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    # Swap the running job for one loaded from a foreign plist.
    subprocess.run([str(h.bindir / "launchctl"), "bootout", f"gui/59999/{LABEL}"],
                   capture_output=True, env=h.env(), timeout=30)
    squat_dir = h.base / "squat"
    squat_dir.mkdir()
    squat = squat_dir / f"{LABEL}.plist"
    squat.write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
        "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
        "<plist version=\"1.0\"><dict>\n"
        f"<key>Label</key><string>{LABEL}</string>\n"
        "<key>ProgramArguments</key><array>\n"
        "<string>/bin/sleep</string><string>300</string>\n"
        "</array>\n"
        "<key>StandardOutPath</key>\n"
        f"<string>{squat_dir / 'squat.log'}</string>\n"
        "</dict></plist>\n")
    loaded = subprocess.run(
        [str(h.bindir / "launchctl"), "load", str(squat)],
        capture_output=True, env=h.env(), timeout=30)
    assert loaded.returncode == 0, loaded.stderr
    assert h.loaded()

    proc = h.run("doctor", "--root", h.root, "--label", LABEL, timeout=120)
    assert proc.returncode == 1
    assert f"jobPlist={squat}" in proc.stdout
    errors = [l for l in proc.stdout.splitlines()
              if l.startswith("doctor_error=")]
    assert errors and str(squat) in errors[0], proc.stdout


# ==========================================================================
# Repair round 3 — B: an empty server.log must never again mean "working".
# The runner writes stage lines (stderr → server.log) plus a credential-free
# <root>/run/boot.status (stage + heartbeat), and install distinguishes
# "still verifying" from "dead" before it ever boots a job out.
# ==========================================================================

def test_b1_runner_stage_lines_and_status_file(h):
    # After a successful install the runner has recorded every stage:
    # resolve-node, resolve-server, the lock/port gate and the exec handoff
    # — both as stderr stage lines and in run/boot.status. A slow start is
    # therefore observable instead of a 0-byte log. The runtime is PACKED
    # (receipts + serving dist/bin.mjs) so both resolves really run.
    _plant_packed_runtime(h, serving=FIX / "fake_t3_server.py")
    packed_bin = h.root / "runtime" / "packed" / "dist" / "bin.mjs"
    assert h.run_install("--server-bin", packed_bin).returncode == 0
    status = h.root / "run" / "boot.status"
    assert status.exists()
    text = status.read_text()
    assert "stage=pre-flight" in text
    assert "stage=resolve-node" in text
    assert "stage=resolve-server" in text
    assert "stage=lock-port" in text
    assert "stage=exec-server" in text
    log = h.log()
    assert "server_runner: stage resolve-node" in log
    assert "server_runner: stage exec-server" in log


def test_b2_install_extends_through_a_slow_verify(h):
    # Panel B: install's wait window expired mid-verify on the real switch
    # and R7 booted a job that was still working. While boot.status shows a
    # PRE-EXEC stage that is fresh (heartbeat) and the job pid is alive,
    # install keeps waiting past the base window and says so on screen.
    # The valve holds each verify stage open, modeling the loaded-machine
    # boot that caused the outage. The runner is started by launchd with NO
    # environment (env -i at bootstrap — FU1), so the delay travels the same
    # way TEAM_SERVER_LOG_CAP does: a test-only file inside the root.
    _plant_packed_runtime(h, serving=FIX / "fake_t3_slowbind.py")  # binds 6 s late
    packed_bin = h.root / "runtime" / "packed" / "dist" / "bin.mjs"
    (h.root / "config" / "verify-delay").write_text("4\n")
    env = h.env(MMOS_TEST_SEAMS="1", MMOS_INSTALL_WAIT="3")
    proc = subprocess.run(
        ["/bin/sh", str(TOOL), "install", "--root", str(h.root),
         "--port", str(h.port), "--label", LABEL, "--replace",
         "--server-bin", str(packed_bin)],
        capture_output=True, text=True, env=env, timeout=180)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "INSTALLED" in proc.stdout
    assert "still starting" in out          # the operator saw WHY it was slow
    assert h.loaded()


def test_b3_dead_start_is_still_booted_out_with_the_stage_named(h):
    # The extension must not protect a dead job: a server that never answers
    # after exec is booted out at the window exactly as before, and the
    # failure names the last stage and its age.
    silent = h.fake_server(FIX / "fake_t3_silent.py")
    # The base window (200 fast iterations ≈ 2 s under the fake sleep)
    # deliberately outlives the exec handoff, so the expiry lands while the
    # last stage is exec-server — the post-exec state the extension must
    # refuse to cover.
    env = h.env(MMOS_TEST_SEAMS="1", MMOS_INSTALL_WAIT="200")
    proc = subprocess.run(
        ["/bin/sh", str(TOOL), "install", "--root", str(h.root),
         "--port", str(h.port), "--label", LABEL, "--replace",
         "--server-bin", str(silent)],
        capture_output=True, text=True, env=env, timeout=120)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "INSTALLED" not in proc.stdout
    assert "server did not answer" in out
    assert "last stage" in out              # B: which stage, how old
    assert not h.loaded()


# ==========================================================================
# Repair round 3 — follow-ups 1/4/6/9 from the delta panel.
# ==========================================================================

def test_fu1_env_i_on_the_load_fallback(h):
    # FU1: both bootstrap fallbacks run env -i'd. The fake launchctl finds
    # its state via a sibling marker file (env -i strips the env var), and a
    # BOOTSTRAP_FAIL state marker forces the load -w fallback. Proof the
    # fallback ran AND survived env -i: the fake logged the load -w call it
    # discovered through the sibling marker, not through the environment.
    server = h.fake_server()
    (h.state / f"{LABEL}.BOOTSTRAP_FAIL").write_text("1")
    proc = h.run_install("--server-bin", server)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert h.loaded()
    invocations = (h.state / "invocations.log").read_text()
    assert "load -w" in invocations, invocations


def test_fu4_seams_refuse_without_the_test_flag(h):
    # FU4: the MMOS_*/TEAM_SERVER_* env seams are test-only. Without
    # MMOS_TEST_SEAMS=1 the tool refuses to honor them — a hostile shell
    # cannot steer launchctl/curl/lsof or the LaunchAgents dir by env.
    env = h.env()
    env["MMOS_TEST_SEAMS"] = ""
    env["TEAM_SERVER_LAUNCHAGENTS_DIR"] = str(h.base / "elsewhere")
    proc = subprocess.run(["/bin/sh", str(TOOL), "status", "--root", str(h.root),
                           "--label", LABEL], capture_output=True, text=True,
                          env=env, timeout=30)
    assert proc.returncode != 0
    assert "MMOS_TEST_SEAMS" in proc.stderr or "TEAM_SERVER_LAUNCHAGENTS_DIR" in proc.stderr


def test_fu6_kickstart_failure_is_truthful(h):
    # FU6: start on an already-loaded label whose kickstart fails must not
    # die silently OR boot out a healthy server: it names the state and the
    # hand recovery, and the running job is untouched.
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    assert wait_for(lambda: http_code(h.port) == "200", 15)
    (h.state / f"{LABEL}.KICKSTART_FAIL").write_text("1")
    proc = h.run("start", "--root", h.root, "--label", LABEL)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "kickstart failed" in out
    assert "still running" in out or "untouched" in out
    assert h.loaded()
    assert http_code(h.port) == "200"


def test_fu9_uninstall_verifies_the_root_is_down(h):
    # FU9: uninstall's UNINSTALLED line is backed by a root-down check: a
    # surviving home.lock holder (a server process that outlived bootout)
    # is named in a warning instead of silently remaining.
    import fcntl as _fcntl
    server = h.fake_server()
    assert h.run_install("--server-bin", server).returncode == 0
    assert h.run("stop", "--root", h.root, "--label", LABEL).returncode == 0
    lock = h.root / "run" / "home.lock"
    holder = subprocess.Popen(
        [PY, "-c",
         f"import fcntl,sys,time;f=open({str(lock)!r},'a+');fcntl.flock(f,fcntl.LOCK_EX);"
         "print('held',flush=True);time.sleep(60)"],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        proc = h.run("uninstall", "--root", h.root, "--label", LABEL)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "UNINSTALLED" in proc.stdout
        assert "home.lock" in out and ("surviving" in out or "still held" in out), out
    finally:
        holder.kill(); holder.wait()
