"""Lane T6 team-server tool: refusal and hygiene tests (no server started).

Covers the DONE_WHEN item 1 refusals plus credential/plist hygiene, purely by
invoking ``tools/mmos_team_server/team_server.sh`` in guarded ways (selftest,
install dry failures). Nothing here bootstraps a LaunchAgent or binds a port;
the plist tests run against a throwaway TEAM_SERVER_LAUNCHAGENTS_DIR.
"""

import os
import plistlib
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "mmos_team_server" / "team_server.sh"
RUNNER = REPO / "tools" / "mmos_team_server" / "server_runner.sh"
SECRETISH = re.compile(r"(token|cookie|pairing|auth|secret|api[_-]?key)", re.I)


def free_port():
    """A port the kernel confirms free right now (tests must not collide with
    a live dev team server on 3805)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_tool(*args, env_extra=None, input=None):
    env = dict(os.environ)
    env.pop("MMOS_T3_DEV_ROOT", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["/bin/sh", str(TOOL), *args], capture_output=True, text=True, env=env,
        timeout=60, input=input,
    )


@pytest.fixture(scope="module")
def launchagents_dir():
    with tempfile.TemporaryDirectory(prefix="t6-la-") as d:
        yield d


@pytest.fixture()
def dev_root(tmp_path):
    """A plausible root outside ~/.t3 with a 0600 fabric.env, as seed leaves it."""
    root = tmp_path / "t3-team"
    root.mkdir()
    envf = root / "fabric.env"
    envf.write_text("ANTHROPIC_BASE_URL=https://example.internal/api\n")
    envf.chmod(0o600)
    return root


def install(root, port, label, *extra, env_extra=None):
    return run_tool(
        "install", "--root", str(root), "--port", str(port), "--label", label, *extra,
        env_extra=env_extra,
    )


class TestSelftest:
    def test_selftest_passes(self):
        r = run_tool("selftest")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "selftest_fail=0" in r.stdout

    def test_usage_without_command(self):
        r = run_tool()
        assert r.returncode == 2
        assert "usage" in (r.stdout + r.stderr).lower()


class TestPortRefusals:
    @pytest.mark.parametrize("port", [3773, 3774])
    def test_reserved_ports_refused(self, dev_root, launchagents_dir, port):
        r = install(dev_root, port, "com.example.t6-port", env_extra={
            "TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0
        assert "reserved" in (r.stdout + r.stderr)

    def test_non_integer_port_refused(self, dev_root, launchagents_dir):
        r = run_tool("install", "--root", str(dev_root), "--port", "38o5",
                     "--label", "com.example.t6",
                     env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0


class TestHomeRefusals:
    def test_root_at_dot_t3_refused(self, launchagents_dir):
        r = install(Path.home() / ".t3", 3805, "com.example.t6-at")
        assert r.returncode != 0
        assert "refus" in (r.stdout + r.stderr).lower()

    def test_root_inside_dot_t3_refused(self, launchagents_dir):
        r = install(Path.home() / ".t3" / "team", 3805, "com.example.t6-in")
        assert r.returncode != 0

    def test_root_symlink_into_dot_t3_refused(self, tmp_path, launchagents_dir):
        link = tmp_path / "t3-link"
        os.symlink(Path.home() / ".t3", link)
        r = install(link, 3805, "com.example.t6-sym")
        assert r.returncode != 0
        # and nothing was created inside the real ~/.t3 by the tool
        assert not (Path.home() / ".t3" / "run").exists()


class TestLabelRefusals:
    def test_bad_label_characters_refused(self, dev_root, launchagents_dir):
        r = install(dev_root, 3805, "com.example.t6; rm -rf",
                    env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0

    def test_refuses_when_plist_exists_without_replace(self, dev_root, launchagents_dir):
        env = {"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir}
        # Simulate an existing install artifact: a plist for this label that is
        # NOT loaded (launchd untouched), so the refusal must come from the file.
        existing = Path(launchagents_dir) / "com.example.t6-dup.plist"
        existing.write_text("placeholder")
        r = install(dev_root, 3805, "com.example.t6-dup", env_extra=env)
        assert r.returncode != 0
        assert "replace" in (r.stdout + r.stderr).lower()
        assert existing.read_text() == "placeholder"  # not clobbered

    def test_second_label_same_root_refused(self, dev_root, launchagents_dir):
        env = {"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir}
        # An existing plist for another label pointing at this root.
        other = Path(launchagents_dir) / "com.example.t6-first.plist"
        other.write_text(f"<string>{dev_root}/bin/server_runner.sh</string>")
        r = install(dev_root, free_port(), "com.example.t6-second", env_extra=env)
        assert r.returncode != 0
        assert "one label per root" in (r.stdout + r.stderr).lower()

    def test_second_label_refused_even_with_plist_dir_override(self, tmp_path):
        # Attack a4: hide the live root's plist from the override dir — the
        # scan must still cover the REAL ~/Library/LaunchAgents (via HOME).
        home = tmp_path / "fakehome"
        real_la = home / "Library" / "LaunchAgents"
        real_la.mkdir(parents=True)
        other = real_la / "com.example.t6-real.plist"
        root = tmp_path / "t3-team"
        root.mkdir()
        (root / "fabric.env").write_text("ANTHROPIC_BASE_URL=https://example.internal/api\n")
        (root / "fabric.env").chmod(0o600)
        other.write_text(f"<string>{root}/bin/server_runner.sh</string>")
        away = tmp_path / "away-LaunchAgents"
        away.mkdir()
        r = install(root, free_port(), "com.example.t6-sneaky", env_extra={
            "HOME": str(home), "TEAM_SERVER_LAUNCHAGENTS_DIR": str(away)})
        assert r.returncode != 0
        assert "one label per root" in (r.stdout + r.stderr).lower()
        assert not (away / "com.example.t6-sneaky.plist").exists()

    def test_install_refused_when_home_lock_held(self, tmp_path, launchagents_dir):
        # Attack a4: a live server holds <root>/run/home.lock across exec;
        # install must refuse BEFORE mutating the root (pass-1 clobbered
        # run/port on a live dev root).
        root = tmp_path / "t3-team"
        run = root / "run"
        run.mkdir(parents=True)
        (root / "fabric.env").write_text("ANTHROPIC_BASE_URL=https://x\n")
        (root / "fabric.env").chmod(0o600)
        (root / "run" / "port").write_text(str(free_port()))
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import fcntl,sys,time\n"
             "fd=open(sys.argv[1],'w')\n"
             "fcntl.flock(fd,fcntl.LOCK_EX)\n"
             "print('held',flush=True)\n"
             "time.sleep(60)\n", str(run / "home.lock")],
            stdout=subprocess.PIPE, text=True)
        try:
            assert holder.stdout.readline().strip() == "held"
            r = install(root, free_port(), "com.example.t6-lockheld", env_extra={
                "TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
            assert r.returncode != 0
            assert "home.lock held" in (r.stdout + r.stderr)
            # the root was not mutated by the refused install
            assert (root / "run" / "port").read_text() != ""
            assert not (root / "bin").exists()
        finally:
            holder.terminate()
            holder.wait(timeout=10)


class TestInstallHygiene:
    def test_missing_fabric_env_refused(self, tmp_path, launchagents_dir):
        root = tmp_path / "t6-noenv"
        root.mkdir()
        r = install(root, free_port(), "com.example.t6-noenv",
                    env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0
        assert "fabric.env" in (r.stdout + r.stderr)

    def test_fabric_env_wrong_mode_refused(self, dev_root, launchagents_dir):
        (dev_root / "fabric.env").chmod(0o644)
        r = install(dev_root, free_port(), "com.example.t6-mode",
                    env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0
        assert "600" in (r.stdout + r.stderr)

    def test_server_bin_must_exist(self, dev_root, launchagents_dir):
        r = install(dev_root, free_port(), "com.example.t6-bin",
                    "--server-bin", "/nonexistent/t3",
                    env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0
        assert "not executable" in (r.stdout + r.stderr)


class TestAttackRoundFixes:
    """Regression tests for the 2026-11-10 attack-round findings (writer:
    glm-5.3; attacker: deepseek-v4.1-flash)."""

    def test_label_traversal_refused_for_every_command(self, tmp_path, launchagents_dir):
        # Attack finding 2: an unvalidated label reached rm -f / launchctl /
        # the plist heredoc in start|stop|status|uninstall. '../escape' must
        # be refused before any path is built from it.
        victim = Path(tmp_path) / "escape.plist"
        victim.write_text("do-not-delete")
        (tmp_path / "root").mkdir()
        for command in ("start", "stop", "status", "uninstall"):
            r = run_tool(command, "--root", str(tmp_path / "root"),
                         "--label", "../escape",
                         env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
            assert r.returncode != 0, command
            assert "invalid label" in (r.stdout + r.stderr)
        assert victim.read_text() == "do-not-delete"

    def test_bracketed_root_matches_exactly(self, tmp_path, launchagents_dir):
        # Attack finding 3: the one-label-per-root scan used grep -q (regex);
        # a root containing '[' neither matched its own plist nor reliably
        # failed. Literal (-F) matching must catch this root's own plist.
        root = tmp_path / "t3-team[1]"
        root.mkdir()
        (root / "fabric.env").write_text("ANTHROPIC_BASE_URL=https://x\n")
        (root / "fabric.env").chmod(0o600)
        other = Path(launchagents_dir) / "com.example.a5-bracket.plist"
        other.write_text(f"<string>{root}/bin/server_runner.sh</string>\n")
        r = install(root, free_port(), "com.example.a5-second",
                    env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0
        assert "one label per root" in (r.stdout + r.stderr)

    def test_symlinked_subdir_refused_before_mkdir(self, tmp_path, launchagents_dir):
        # Attack finding 10: mkdir -p follows a pre-planted 'home -> victim'
        # symlink; install must refuse before writing anything through it.
        root = tmp_path / "t3-team"
        root.mkdir(mode=0o700)
        (root / "fabric.env").write_text("ANTHROPIC_BASE_URL=https://x\n")
        (root / "fabric.env").chmod(0o600)
        victim = tmp_path / "victim"
        victim.mkdir()
        os.symlink(victim, root / "home")
        r = install(root, free_port(), "com.example.a5-sym",
                    "--server-bin", "/usr/bin/true",
                    env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0
        assert "refusing symlinked subdir" in (r.stdout + r.stderr)
        assert list(victim.iterdir()) == []  # nothing written through the link

    def test_loose_existing_root_refused_even_with_server_bin(self, tmp_path, launchagents_dir):
        # Attack finding 11: the --server-bin rollback path skipped the
        # installer's root validation entirely; an existing loose root must
        # still refuse before install mutates it.
        root = tmp_path / "t3-team"
        root.mkdir()
        root.chmod(0o755)
        (root / "fabric.env").write_text("ANTHROPIC_BASE_URL=https://x\n")
        (root / "fabric.env").chmod(0o600)
        r = install(root, free_port(), "com.example.a5-loose",
                    "--server-bin", "/usr/bin/true",
                    env_extra={"TEAM_SERVER_LAUNCHAGENTS_DIR": launchagents_dir})
        assert r.returncode != 0
        assert "0700" in (r.stdout + r.stderr)

    def test_runner_refuses_unconfigured_without_guessing_default(self, tmp_path):
        # Attack finding 12: the runner used to default to ~/.t3/bin/t3 when
        # no config/server-bin existed; it must fail loudly instead, and the
        # default must be gone from the script text.
        root = tmp_path / "root"
        run = root / "run"
        cfg = root / "config"
        run.mkdir(parents=True)
        cfg.mkdir(parents=True)
        (root / "fabric.env").write_text("DUMMY=1\n")
        (root / "fabric.env").chmod(0o600)
        (cfg / "python3-path").write_text("/opt/homebrew/bin/python3.12\n")
        (run / "port").write_text(str(free_port()))
        r = subprocess.run(["/bin/sh", str(RUNNER), str(root)],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 78
        assert "refusing to guess" in (r.stdout + r.stderr)
        assert ".t3/bin/t3" not in RUNNER.read_text()

    def test_runner_refuses_without_recorded_interpreter(self, tmp_path):
        # Item 13: no recorded interpreter means a one-line refusal — never a
        # PATH search for python3.
        root = tmp_path / "root"
        run = root / "run"
        run.mkdir(parents=True)
        (root / "fabric.env").write_text("DUMMY=1\n")
        (root / "fabric.env").chmod(0o600)
        (run / "port").write_text(str(free_port()))
        r = subprocess.run(["/bin/sh", str(RUNNER), str(root)],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 78
        assert "python3-path" in (r.stdout + r.stderr)
        # and a relative or non-executable recording is refused just the same
        for bad in ("usr/bin/python3", "/nonexistent/python3"):
            (root / "config").mkdir(exist_ok=True)
            (root / "config" / "python3-path").write_text(bad + "\n")
            r = subprocess.run(["/bin/sh", str(RUNNER), str(root)],
                               capture_output=True, text=True, timeout=30)
            assert r.returncode == 78, bad
            assert "python3-path" in (r.stdout + r.stderr)

    def test_runner_refuses_non_canonical_port_file(self, tmp_path):
        # F21: an empty or leading-zero port file must refuse at the runner,
        # not pass through to T3CODE_PORT.
        root = tmp_path / "root"
        run = root / "run"
        cfg = root / "config"
        run.mkdir(parents=True)
        cfg.mkdir(parents=True)
        (root / "fabric.env").write_text("DUMMY=1\n")
        (root / "fabric.env").chmod(0o600)
        (cfg / "python3-path").write_text("/opt/homebrew/bin/python3.12\n")
        (cfg / "server-bin").write_text("/usr/bin/false\n")
        for bad in ("", "03773", "65536", "37x3"):
            (run / "port").write_text(bad + "\n")
            r = subprocess.run(["/bin/sh", str(RUNNER), str(root)],
                               capture_output=True, text=True, timeout=30)
            assert r.returncode == 78, repr(bad)
            assert "non-canonical port" in (r.stdout + r.stderr), repr(bad)

    def test_runner_fails_closed_when_run_dir_cannot_exist(self, tmp_path):
        # F28: a read-only root must produce one operator-readable line, not a
        # python traceback every ThrottleInterval.
        root = tmp_path / "root"
        root.mkdir()
        (root / "fabric.env").write_text("DUMMY=1\n")
        (root / "fabric.env").chmod(0o600)
        root.chmod(0o500)  # read+execute only: run/ cannot be created
        try:
            r = subprocess.run(["/bin/sh", str(RUNNER), str(root)],
                               capture_output=True, text=True, timeout=30)
            assert r.returncode == 73
            assert "cannot create" in (r.stdout + r.stderr)
            assert "Traceback" not in (r.stdout + r.stderr)
        finally:
            root.chmod(0o700)


class TestRunnerHygiene:
    def test_runner_refuses_without_root(self):
        r = subprocess.run(["/bin/sh", str(RUNNER)], capture_output=True, text=True, timeout=30)
        assert r.returncode == 64

    def test_runner_refuses_missing_env_file(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        r = subprocess.run(["/bin/sh", str(RUNNER), str(root)],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 78
        assert "fabric.env" in (r.stdout + r.stderr)

    def test_runner_sources_no_plist_secrets(self):
        text = RUNNER.read_text()
        assert SECRETISH.search(text)  # mentions credentials only to protect them
        # the runner must never echo env values
        assert "printenv" not in text and "echo $" not in text

    def test_runner_truncates_log_over_config_cap(self, tmp_path):
        # launchd passes no environment: the cap must also come from the
        # root's config file, and the log must be truncated before the exec.
        root = tmp_path / "root"
        run = root / "run"
        cfg = root / "config"
        run.mkdir(parents=True)
        cfg.mkdir(parents=True)
        (root / "fabric.env").write_text("DUMMY=1\n")
        (root / "fabric.env").chmod(0o600)
        (cfg / "python3-path").write_text("/opt/homebrew/bin/python3.12\n")
        (cfg / "server-bin").write_text("/usr/bin/false\n")
        (cfg / "log-cap").write_text("1024\n")
        (run / "port").write_text(str(free_port()))
        log = run / "server.log"
        log.write_bytes(b"x" * 40960)
        r = subprocess.run(["/bin/sh", str(RUNNER), str(root)],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 1  # execve'd /usr/bin/false
        assert log.stat().st_size == 0  # truncated at runner start

    def test_no_secrets_in_plist_template(self):
        text = TOOL.read_text()
        plist_block = text[text.index("<key>Label</key>"):text.index("</plist>")]
        for key in ("ANTHROPIC", "TOKEN", "COOKIE", "Authorization", "fabric.env"):
            assert key not in plist_block.upper().replace("FABRIC.ENV", "FABRIC.ENV-X")


class TestLibraryReuse:
    def test_sources_t3_dev_library(self):
        text = TOOL.read_text()
        assert "T3_DEV_LIB_ONLY=1" in text
        assert "mmos_dev/t3_dev.sh" in text
        dev = (REPO / "tools" / "mmos_dev" / "t3_dev.sh").read_text()
        assert 'T3_DEV_LIB_ONLY' in dev  # the opt-in exists in the incumbent


class TestPlistShape:
    def test_plist_wellformed_and_minimal(self, dev_root, launchagents_dir):
        # Extract the heredoc plist from the script and validate its shape.
        text = TOOL.read_text()
        m = re.search(r"cat > \"\$PLIST\" <<EOF\n(.*?)\nEOF", text, re.S)
        assert m, "plist heredoc not found"
        body = m.group(1)
        body = body.replace("$LABEL", "com.example.shape").replace("$ROOT", "/tmp/root")
        body = body.replace("$PORT", "3805")
        data = plistlib.loads(body.encode())
        assert data["KeepAlive"] is True
        assert data["RunAtLoad"] is True
        assert data["Label"] == "com.example.shape"
        assert data["ProgramArguments"][0] == "/bin/sh"
        assert "EnvironmentVariables" not in data  # no env (thus no keys) in plist
        assert data["StandardOutPath"] == "/tmp/root/run/server.log"
