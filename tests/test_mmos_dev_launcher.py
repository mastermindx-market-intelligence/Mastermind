"""Tests for the Mastermind OS dev-harness launcher (app/mastermind_os/tools/mmos_dev.py).

The process layer is fully faked: no npm, no vite, no sockets, no network.  The
only real filesystem use is a pytest tmp directory standing in for the dev root.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "app" / "mastermind_os" / "tools" / "mmos_dev.py"
BROWSER_DOM_LINE = "Text control for this mode is the browser DOM (details in the harness runbook)."


@pytest.fixture(scope="module")
def mmos_dev():
    spec = importlib.util.spec_from_file_location("mmos_dev_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeProcessOps:
    """In-memory stand-in for ``SystemProcessOps``."""

    def __init__(self, *, app_dir: Path | None = None):
        self.app_dir = Path(app_dir) if app_dir is not None else None
        self.run_calls: list[dict] = []
        self.spawn_calls: list[dict] = []
        self.terminated: list[int] = []
        self.alive: dict[int, bool] = {}
        self.commands: dict[int, str | None] = {}
        self.port_free = True
        self.http_ready = True
        self.run_rc = 0
        self.installs_vite = True
        self.next_pid = 4200

    def run(self, argv, *, cwd, log_path):
        argv = [str(part) for part in argv]
        self.run_calls.append({"argv": argv, "cwd": Path(cwd), "log_path": Path(log_path)})
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("fake run output\n", encoding="utf-8")
        if argv and Path(argv[0]).name == "npm" and self.installs_vite and self.app_dir:
            bin_dir = self.app_dir / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            (bin_dir / "vite").write_text("#!/bin/sh\n", encoding="utf-8")
        return self.run_rc

    def spawn(self, argv, *, cwd, log_path):
        argv = [str(part) for part in argv]
        pid = self.next_pid
        self.next_pid += 1
        self.spawn_calls.append({"argv": argv, "cwd": Path(cwd), "log_path": Path(log_path), "pid": pid})
        self.alive[pid] = True
        self.commands[pid] = " ".join(argv)
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("fake spawn\n", encoding="utf-8")
        return pid

    def command_of(self, pid):
        return self.commands.get(pid)

    def is_alive(self, pid):
        return bool(self.alive.get(pid, False))

    def terminate(self, pid, *, timeout=8.0):
        self.terminated.append(pid)
        self.alive[pid] = False
        return "terminated"

    def port_available(self, port):
        return self.port_free

    def wait_for_port(self, port, timeout):
        return True

    def wait_for_http(self, url, timeout):
        return self.http_ready


def make_app(tmp_path: Path) -> Path:
    """Fake app checkout with an installed vite binary."""
    app = tmp_path / "repo" / "app" / "mastermind_os"
    bin_dir = app / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    vite = bin_dir / "vite"
    vite.write_text("#!/bin/sh\n", encoding="utf-8")
    vite.chmod(0o755)
    (app / "package.json").write_text("{}", encoding="utf-8")
    return app


def make_bare_app(tmp_path: Path) -> Path:
    """Fake app checkout without node_modules (fresh clone)."""
    app = tmp_path / "repo" / "app" / "mastermind_os"
    app.mkdir(parents=True)
    (app / "package.json").write_text("{}", encoding="utf-8")
    return app


def dev_root_for(tmp_path: Path) -> Path:
    return tmp_path / "home" / ".mastermind" / "mmos_dev"


def run_up(mmos_dev, tmp_path, app, ops, *extra):
    return mmos_dev.main(
        ["up", "--fixture", *extra],
        ops=ops,
        dev_root=dev_root_for(tmp_path),
        app_dir=app,
    )


# ---------------------------------------------------------------------------
# up --fixture
# ---------------------------------------------------------------------------


def test_up_fixture_records_pid_port_mode_and_state(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    dev_root = dev_root_for(tmp_path)

    rc = run_up(mmos_dev, tmp_path, app, ops)

    out = capsys.readouterr().out
    assert rc == mmos_dev.EXIT_OK
    state = json.loads((dev_root / "state.json").read_text(encoding="utf-8"))
    assert state["mode"] == "fixture"
    assert state["app"] == "browser"
    assert state["port"] == mmos_dev.DEFAULT_PORT
    assert state["url"] == f"http://127.0.0.1:{mmos_dev.DEFAULT_PORT}/browser-proof.html"
    assert state["socket_path"] == str(dev_root / "control.sock")
    assert len(state["procs"]) == 1
    proc = state["procs"][0]
    assert proc["role"] == "vite-preview"
    assert proc["pid"] == ops.spawn_calls[0]["pid"]
    pidfile = dev_root / "pids" / "vite-preview.pid"
    assert json.loads(pidfile.read_text(encoding="utf-8"))["pid"] == proc["pid"]
    assert f"http://127.0.0.1:{mmos_dev.DEFAULT_PORT}/browser-proof.html" in out
    assert BROWSER_DOM_LINE in out


def test_up_fixture_builds_browser_proof_bundle_and_serves_loopback(mmos_dev, tmp_path):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)

    assert run_up(mmos_dev, tmp_path, app, ops) == mmos_dev.EXIT_OK

    build = [call for call in ops.run_calls if "build" in call["argv"]]
    assert len(build) == 1
    assert build[0]["argv"][0].endswith("node_modules/.bin/vite")
    assert "vite.browser-proof.config.ts" in build[0]["argv"]
    assert build[0]["cwd"] == app

    preview = ops.spawn_calls[0]["argv"]
    assert "preview" in preview
    assert "--strictPort" in preview
    assert preview[preview.index("--host") + 1] == "127.0.0.1"
    assert "0.0.0.0" not in " ".join(preview)


def test_up_fixture_honours_port_override(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)

    assert run_up(mmos_dev, tmp_path, app, ops, "--port", "5301") == mmos_dev.EXIT_OK

    state = json.loads((dev_root_for(tmp_path) / "state.json").read_text(encoding="utf-8"))
    assert state["port"] == 5301
    assert state["url"] == "http://127.0.0.1:5301/browser-proof.html"
    assert "--port" in ops.spawn_calls[0]["argv"]
    assert "5301" in ops.spawn_calls[0]["argv"]
    assert "5301" in capsys.readouterr().out


def test_up_fixture_installs_dependencies_when_node_modules_absent(mmos_dev, tmp_path):
    app = make_bare_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)

    assert run_up(mmos_dev, tmp_path, app, ops) == mmos_dev.EXIT_OK

    assert ops.run_calls[0]["argv"] == ["npm", "install", "--no-audit", "--no-fund"]
    assert ops.run_calls[0]["cwd"] == app
    assert (dev_root_for(tmp_path) / "logs" / "npm-install.log").exists()
    assert any("build" in call["argv"] for call in ops.run_calls)


def test_up_fixture_skips_npm_install_when_node_modules_present(mmos_dev, tmp_path):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)

    assert run_up(mmos_dev, tmp_path, app, ops) == mmos_dev.EXIT_OK

    assert not any(Path(call["argv"][0]).name == "npm" for call in ops.run_calls)


def test_up_fixture_port_in_use_exits_distinct_code(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    ops.port_free = False

    rc = run_up(mmos_dev, tmp_path, app, ops)

    assert rc == mmos_dev.EXIT_PORT_IN_USE
    assert ops.spawn_calls == []
    assert not any("build" in call["argv"] for call in ops.run_calls)
    assert not (dev_root_for(tmp_path) / "state.json").exists()
    assert "in use" in capsys.readouterr().out


def test_up_fixture_build_failure_leaves_no_state(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    ops.run_rc = 1

    rc = run_up(mmos_dev, tmp_path, app, ops)

    assert rc == mmos_dev.EXIT_ERROR
    assert ops.spawn_calls == []
    assert not (dev_root_for(tmp_path) / "state.json").exists()
    assert "failed" in capsys.readouterr().out


def test_up_fixture_preview_never_answers_stops_spawned_pid(mmos_dev, tmp_path):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    ops.http_ready = False

    rc = run_up(mmos_dev, tmp_path, app, ops)

    assert rc == mmos_dev.EXIT_ERROR
    assert ops.terminated == [ops.spawn_calls[0]["pid"]]
    assert not (dev_root_for(tmp_path) / "state.json").exists()


def test_up_refuses_when_recorded_process_still_alive(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    dev_root = dev_root_for(tmp_path)
    (dev_root / "pids").mkdir(parents=True)
    command = f"{app}/node_modules/.bin/vite preview --host 127.0.0.1 --port 5192 --strictPort"
    (dev_root / "pids" / "vite-preview.pid").write_text(
        json.dumps({"role": "vite-preview", "pid": 4188, "command": command}), encoding="utf-8"
    )
    ops = FakeProcessOps(app_dir=app)
    ops.alive[4188] = True
    ops.commands[4188] = command

    rc = run_up(mmos_dev, tmp_path, app, ops)

    assert rc == mmos_dev.EXIT_ALREADY_RUNNING
    assert ops.spawn_calls == []
    assert "down" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# NOT_IMPLEMENTED_YET paths
# ---------------------------------------------------------------------------


def test_up_without_fixture_is_not_implemented(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)

    rc = mmos_dev.main(["up"], ops=ops, dev_root=dev_root_for(tmp_path), app_dir=app)

    out = capsys.readouterr().out
    assert rc == mmos_dev.EXIT_NOT_IMPLEMENTED
    assert "NOT_IMPLEMENTED_YET: real dev Executive waits on lane L4 (LOCAL_OPERATOR_CONTRACT)" in out
    assert ops.run_calls == [] and ops.spawn_calls == []
    assert not (dev_root_for(tmp_path) / "state.json").exists()


def test_up_fixture_with_native_app_is_not_implemented(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)

    rc = mmos_dev.main(
        ["up", "--fixture", "--app", "native"],
        ops=ops,
        dev_root=dev_root_for(tmp_path),
        app_dir=app,
    )

    out = capsys.readouterr().out
    assert rc == mmos_dev.EXIT_NOT_IMPLEMENTED
    assert "NOT_IMPLEMENTED_YET: real dev Executive waits on lane L4 (LOCAL_OPERATOR_CONTRACT)" in out
    assert ops.run_calls == [] and ops.spawn_calls == []


def test_not_implemented_exit_code_is_documented(mmos_dev):
    assert mmos_dev.EXIT_NOT_IMPLEMENTED == 78
    assert mmos_dev.EXIT_NOT_IMPLEMENTED not in (0, mmos_dev.EXIT_ERROR)
    assert "78" in (mmos_dev.__doc__ or "")


# ---------------------------------------------------------------------------
# down
# ---------------------------------------------------------------------------


def write_pidfile(dev_root: Path, role: str, pid: int, command: str) -> Path:
    pids = dev_root / "pids"
    pids.mkdir(parents=True, exist_ok=True)
    pidfile = pids / f"{role}.pid"
    pidfile.write_text(json.dumps({"role": role, "pid": pid, "command": command}), encoding="utf-8")
    return pidfile


def test_down_kills_recorded_verified_pid_and_leaves_named_decoy(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    dev_root = dev_root_for(tmp_path)
    verified_pid, decoy_pid = 5001, 5002
    verified_command = f"{app}/node_modules/.bin/vite preview --host 127.0.0.1 --port 5192 --strictPort"
    decoy_command = "/usr/local/bin/vite preview --host 127.0.0.1 --port 7000"
    write_pidfile(dev_root, "vite-preview", verified_pid, verified_command)
    write_pidfile(dev_root, "vite-preview-decoy", decoy_pid, decoy_command)
    ops = FakeProcessOps(app_dir=app)
    ops.alive[verified_pid] = True
    ops.commands[verified_pid] = verified_command
    ops.alive[decoy_pid] = True
    ops.commands[decoy_pid] = decoy_command

    rc = mmos_dev.main(["down"], ops=ops, dev_root=dev_root, app_dir=app)

    out = capsys.readouterr().out
    assert rc == mmos_dev.EXIT_OK
    assert ops.terminated == [verified_pid]
    assert ops.alive[decoy_pid] is True
    assert "skipped" in out


def test_down_skips_pid_recycled_to_unrelated_command(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    dev_root = dev_root_for(tmp_path)
    recycled_pid = 5003
    recorded = f"{app}/node_modules/.bin/vite preview --host 127.0.0.1 --port 5192 --strictPort"
    write_pidfile(dev_root, "vite-preview", recycled_pid, recorded)
    ops = FakeProcessOps(app_dir=app)
    ops.alive[recycled_pid] = True
    ops.commands[recycled_pid] = "/usr/bin/python3 -m http.server 8000"

    rc = mmos_dev.main(["down"], ops=ops, dev_root=dev_root, app_dir=app)

    out = capsys.readouterr().out
    assert rc == mmos_dev.EXIT_OK
    assert ops.terminated == []
    assert ops.alive[recycled_pid] is True
    assert f"pid {recycled_pid}" in out
    assert "skipped" in out


def test_down_verification_ignores_process_name_matches(mmos_dev, tmp_path):
    app = make_app(tmp_path)
    dev_root = dev_root_for(tmp_path)
    pid = 5004
    write_pidfile(dev_root, "vite-preview", pid, f"{app}/node_modules/.bin/vite preview")
    ops = FakeProcessOps(app_dir=app)
    ops.alive[pid] = True
    # Same executable name, same role name, but a different checkout and root.
    ops.commands[pid] = "/other/checkout/app/mastermind_os/node_modules/.bin/vite preview"

    mmos_dev.main(["down"], ops=ops, dev_root=dev_root, app_dir=app)

    assert ops.terminated == []


def test_down_removes_pidfile_of_dead_record_without_signalling(mmos_dev, tmp_path):
    app = make_app(tmp_path)
    dev_root = dev_root_for(tmp_path)
    pidfile = write_pidfile(dev_root, "vite-preview", 5005, f"{app}/node_modules/.bin/vite preview")
    ops = FakeProcessOps(app_dir=app)
    ops.alive[5005] = False
    ops.commands[5005] = None

    rc = mmos_dev.main(["down"], ops=ops, dev_root=dev_root, app_dir=app)

    assert rc == mmos_dev.EXIT_OK
    assert ops.terminated == []
    assert not pidfile.exists()


def test_down_without_records_is_a_noop(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    dev_root = dev_root_for(tmp_path)

    rc = mmos_dev.main(["down"], ops=ops, dev_root=dev_root, app_dir=app)

    assert rc == mmos_dev.EXIT_OK
    assert ops.terminated == []
    assert "nothing to stop" in capsys.readouterr().out
    assert not (dev_root / "state.json").exists()


def test_down_stops_state_recorded_process_without_pidfile(mmos_dev, tmp_path):
    app = make_app(tmp_path)
    dev_root = dev_root_for(tmp_path)
    dev_root.mkdir(parents=True)
    command = f"{app}/node_modules/.bin/vite preview --host 127.0.0.1 --port 5192 --strictPort"
    (dev_root / "state.json").write_text(
        json.dumps(
            {
                "mode": "fixture",
                "app": "browser",
                "port": 5192,
                "url": "http://127.0.0.1:5192/browser-proof.html",
                "procs": [{"role": "vite-preview", "pid": 5006, "command": command}],
            }
        ),
        encoding="utf-8",
    )
    ops = FakeProcessOps(app_dir=app)
    ops.alive[5006] = True
    ops.commands[5006] = command

    assert mmos_dev.main(["down"], ops=ops, dev_root=dev_root, app_dir=app) == mmos_dev.EXIT_OK
    assert ops.terminated == [5006]
    assert not (dev_root / "state.json").exists()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_renders_recorded_state_as_text(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    dev_root = dev_root_for(tmp_path)
    assert run_up(mmos_dev, tmp_path, app, ops) == mmos_dev.EXIT_OK
    capsys.readouterr()

    rc = mmos_dev.main(["status"], ops=ops, dev_root=dev_root, app_dir=app)

    out = capsys.readouterr().out
    assert rc == mmos_dev.EXIT_OK
    assert "mode: fixture" in out
    assert f"dev root: {dev_root}" in out
    assert f"control socket (planned): {dev_root / 'control.sock'}" in out
    assert f"port: {mmos_dev.DEFAULT_PORT}" in out
    assert f"url: http://127.0.0.1:{mmos_dev.DEFAULT_PORT}/browser-proof.html" in out
    assert f"pid {ops.spawn_calls[0]['pid']} (vite-preview): running (command verified)" in out
    assert str(dev_root / "logs" / "vite-preview.log") in out
    assert "state: running" in out


def test_status_before_start_shows_planned_paths(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    dev_root = dev_root_for(tmp_path)

    rc = mmos_dev.main(["status"], ops=ops, dev_root=dev_root, app_dir=app)

    out = capsys.readouterr().out
    assert rc == mmos_dev.EXIT_OK
    assert "mode: (not started)" in out
    assert "state: stopped" in out
    assert f"dev root: {dev_root}" in out
    assert f"control socket (planned): {dev_root / 'control.sock'}" in out
    assert "logs:" in out


# ---------------------------------------------------------------------------
# Dev-root boundaries and source guard rails
# ---------------------------------------------------------------------------


def test_default_dev_root_is_outside_forbidden_locations(mmos_dev):
    resolved = mmos_dev.resolve_dev_root(env={})
    assert resolved == Path.home() / ".mastermind" / "mmos_dev"
    assert mmos_dev.dev_root_refusal_reason(resolved) is None
    assert "MastermindExecutive" not in resolved.parts
    assert "control_plane" not in resolved.parts
    assert resolved != Path("/tmp")


@pytest.mark.parametrize(
    "path",
    [
        Path("/Library/Application Support/MastermindExecutive"),
        Path("/Library/Application Support/MastermindExecutive/state"),
        Path("/Users/someone/Mastermind/data/control_plane"),
        Path("/Users/someone/other-checkout/data/control_plane/scratch"),
        Path("/tmp/mmos_dev"),
    ],
)
def test_forbidden_dev_roots_are_refused(mmos_dev, path):
    assert mmos_dev.dev_root_refusal_reason(path) is not None
    with pytest.raises(mmos_dev.DevRootRefused):
        mmos_dev.refuse_forbidden_dev_root(path)


def test_production_dev_root_refused_even_for_programmatic_seam(mmos_dev, tmp_path, capsys):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    production = Path("/Library/Application Support/MastermindExecutive")

    rc = mmos_dev.main(["up", "--fixture"], ops=ops, dev_root=production, app_dir=app)

    assert rc == mmos_dev.EXIT_DEV_ROOT_REFUSED
    assert ops.run_calls == [] and ops.spawn_calls == []
    assert "refusing dev root" in capsys.readouterr().out


def test_all_persistent_state_stays_under_dev_root(mmos_dev, tmp_path):
    app = make_app(tmp_path)
    ops = FakeProcessOps(app_dir=app)
    dev_root = dev_root_for(tmp_path)
    assert run_up(mmos_dev, tmp_path, app, ops) == mmos_dev.EXIT_OK

    created = {path for path in dev_root.rglob("*") if path.is_file()}
    assert dev_root / "state.json" in created
    assert dev_root / "pids" / "vite-preview.pid" in created
    assert dev_root / "logs" / "vite-build.log" in created
    assert dev_root / "logs" / "vite-preview.log" in created
    # No harness state written into the fake checkout or /tmp root.
    assert not (app / "state.json").exists()
    assert not (app / "pids").exists()


def test_source_never_uses_process_name_matching(mmos_dev):
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "pkill" not in source
    assert "killall" not in source
    assert "0.0.0.0" not in source


def test_source_binds_loopback_only(mmos_dev):
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert 'DEFAULT_HOST = "127.0.0.1"' in source
