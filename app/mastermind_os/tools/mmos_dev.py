#!/usr/bin/env python3
"""One-command dev harness launcher for the Mastermind OS app.

Fixture mode (``up --fixture``) is the only implemented front today:

* ensure app dependencies (``npm install --no-audit --no-fund`` when
  ``node_modules`` is absent),
* build the existing browser-proof bundle
  (``node_modules/.bin/vite build --config vite.browser-proof.config.ts``),
* serve ``dist-browser-proof`` on ``127.0.0.1`` with a fixed default port and
  strict port binding,
* record every started process under the dev root.

All persistent state (pidfiles, ``state.json``, logs) lives under the dev root,
``~/.mastermind/mmos_dev/`` (override with ``MMOS_DEV_ROOT``).  The harness
never writes to the production Executive directory, a checkout's
``data/control_plane/`` or ``/tmp``.

``down`` signals only pids recorded by this harness whose *live* command line
still references this harness's paths.  Processes are never matched by name, so
the installed Mastermind OS app and other lanes' processes are untouchable here.

Exit codes:
  0   ok
  1   failure (dependency install, build, or preview startup)
  3   requested port is already in use (strict port binding)
  4   a recorded harness process is still alive; run ``down`` first
  5   dev root refused (production Executive path, a checkout's
      ``data/control_plane/``, or ``/tmp``)
  78  ``NOT_IMPLEMENTED_YET`` (real dev Executive / native front)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5192
FIXTURE_PAGE = "browser-proof.html"
PREVIEW_READY_TIMEOUT = 30.0

DEV_ROOT_ENV = "MMOS_DEV_ROOT"
DEFAULT_DEV_ROOT = Path.home() / ".mastermind" / "mmos_dev"
PRODUCTION_EXECUTIVE_ROOT = Path("/Library/Application Support/MastermindExecutive")
SYSTEM_TMP = Path("/tmp")

APP_DIR = Path(__file__).resolve().parent.parent  # app/mastermind_os

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PORT_IN_USE = 3
EXIT_ALREADY_RUNNING = 4
EXIT_DEV_ROOT_REFUSED = 5
EXIT_NOT_IMPLEMENTED = 78

NOT_IMPLEMENTED_MESSAGE = (
    "NOT_IMPLEMENTED_YET: real dev Executive waits on lane L4 "
    "(LOCAL_OPERATOR_CONTRACT)"
)


# ---------------------------------------------------------------------------
# Dev root resolution and refusal of forbidden locations
# ---------------------------------------------------------------------------


class DevRootRefused(RuntimeError):
    """Raised when the requested dev root is a location the harness must not use."""


def resolve_dev_root(env: Mapping[str, str] | None = None) -> Path:
    """Return the dev root: an explicit ``MMOS_DEV_ROOT`` override, else the default."""
    environment = os.environ if env is None else env
    override = environment.get(DEV_ROOT_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_DEV_ROOT


def dev_root_refusal_reason(dev_root: os.PathLike[str] | str, *, allow_tmp: bool = False) -> str | None:
    """Explain why ``dev_root`` is forbidden, or return ``None`` when it is usable.

    ``allow_tmp`` exists for programmatic test seams only; the CLI never sets it,
    so an explicit ``MMOS_DEV_ROOT`` pointing into /tmp is still refused.
    """
    resolved = Path(dev_root).expanduser().resolve()
    production = PRODUCTION_EXECUTIVE_ROOT.resolve()
    if resolved == production or production in resolved.parents:
        return f"production Executive directory {production} is read-only for the dev harness"
    if "MastermindExecutive" in resolved.parts:
        return "a MastermindExecutive path belongs to the installed production Executive"
    parts = resolved.parts
    for index in range(len(parts) - 1):
        if parts[index] == "data" and parts[index + 1] == "control_plane":
            return "a checkout's data/control_plane/ is the Executive's scratch root, not the dev harness"
    if not allow_tmp:
        tmp = SYSTEM_TMP.resolve()
        if resolved == tmp or tmp in resolved.parents:
            return "/tmp must not hold persistent harness state"
    return None


def refuse_forbidden_dev_root(dev_root: os.PathLike[str] | str, *, allow_tmp: bool = False) -> None:
    """Raise :class:`DevRootRefused` when ``dev_root`` is a forbidden location."""
    reason = dev_root_refusal_reason(dev_root, allow_tmp=allow_tmp)
    if reason is not None:
        raise DevRootRefused(f"refusing dev root {Path(dev_root).expanduser()}: {reason}")


# ---------------------------------------------------------------------------
# Real process layer
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _joined(argv: Sequence[os.PathLike[str] | str]) -> str:
    return " ".join(str(part) for part in argv)


class SystemProcessOps:
    """Real OS process operations.

    Every process operation the harness performs goes through this object so the
    test suite can substitute a fake and never run npm, vite, or the network.
    """

    def run(self, argv: Sequence[os.PathLike[str] | str], *, cwd: Path, log_path: Path) -> int:
        """Run a synchronous command (install/build), appending its output to ``log_path``."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            log.write(f"\n=== {_now_iso()} $ {_joined(argv)}\n")
            log.flush()
            completed = subprocess.run(
                [str(part) for part in argv],
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        return completed.returncode

    def spawn(self, argv: Sequence[os.PathLike[str] | str], *, cwd: Path, log_path: Path) -> int:
        """Start a detached long-lived process; return its pid.

        ``start_new_session`` makes the child its own session leader, so its
        process group id equals its pid and ``down`` can stop exactly that tree.
        """
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("a", encoding="utf-8", errors="replace")
        try:
            log.write(f"\n=== {_now_iso()} $ {_joined(argv)}\n")
            log.flush()
            process = subprocess.Popen(
                [str(part) for part in argv],
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log.close()
        return process.pid

    def command_of(self, pid: int) -> str | None:
        """Return the live command line for ``pid`` (full width), or ``None``."""
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        command = result.stdout.strip()
        return command or None

    def is_alive(self, pid: int) -> bool:
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        stat = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
        )
        if stat.returncode != 0:
            return False
        return not stat.stdout.strip().startswith("Z")

    def terminate(self, pid: int, *, timeout: float = 8.0) -> str:
        """SIGTERM the recorded process (its whole session when it leads one).

        Returns ``"terminated"``, ``"killed"`` (needed SIGKILL) or ``"gone"``.
        """
        if not self.is_alive(pid):
            return "gone"
        try:
            pgid = os.getpgid(pid)
        except OSError:
            pgid = None
        owns_group = pgid == pid
        try:
            if owns_group:
                os.killpg(pgid, signal.SIGTERM)  # type: ignore[arg-type]
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return "gone"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_alive(pid):
                return "terminated"
            time.sleep(0.1)
        try:
            if owns_group:
                os.killpg(pgid, signal.SIGKILL)  # type: ignore[arg-type]
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return "terminated"
        for _ in range(50):
            if not self.is_alive(pid):
                break
            time.sleep(0.1)
        return "killed"

    def port_available(self, port: int) -> bool:
        """True when 127.0.0.1:``port`` can be bound right now (strict-port check)."""
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((DEFAULT_HOST, port))
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def wait_for_port(self, port: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(0.5)
            try:
                if probe.connect_ex((DEFAULT_HOST, port)) == 0:
                    return True
            finally:
                probe.close()
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)

    def wait_for_http(self, url: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if 200 <= response.status < 300:
                        return True
            except (urllib.error.URLError, OSError, ValueError):
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class DevHarness:
    """Fixture-mode dev harness.  All state lives under ``dev_root``."""

    def __init__(
        self,
        *,
        app_dir: os.PathLike[str] | str | None = None,
        dev_root: os.PathLike[str] | str | None = None,
        ops: SystemProcessOps | None = None,
        allow_tmp_dev_root: bool = False,
    ) -> None:
        self.app_dir = Path(app_dir) if app_dir is not None else APP_DIR
        self.dev_root = Path(dev_root) if dev_root is not None else resolve_dev_root()
        self.ops = ops if ops is not None else SystemProcessOps()
        # ``allow_tmp_dev_root`` is a programmatic test seam; the CLI leaves it False.
        self.allow_tmp_dev_root = allow_tmp_dev_root

    # -- paths ---------------------------------------------------------------

    @property
    def state_path(self) -> Path:
        return self.dev_root / "state.json"

    @property
    def pids_dir(self) -> Path:
        return self.dev_root / "pids"

    @property
    def logs_dir(self) -> Path:
        return self.dev_root / "logs"

    @property
    def socket_path(self) -> Path:
        return self.dev_root / "control.sock"

    @property
    def install_log(self) -> Path:
        return self.logs_dir / "npm-install.log"

    @property
    def build_log(self) -> Path:
        return self.logs_dir / "vite-build.log"

    @property
    def preview_log(self) -> Path:
        return self.logs_dir / "vite-preview.log"

    def log_paths(self) -> dict[str, Path]:
        return {
            "npm-install": self.install_log,
            "build": self.build_log,
            "preview": self.preview_log,
        }

    def url_for(self, port: int) -> str:
        return f"http://{DEFAULT_HOST}:{port}/{FIXTURE_PAGE}"

    # -- state ---------------------------------------------------------------

    def _read_state(self) -> dict[str, Any] | None:
        try:
            raw = self.state_path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return None
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return state if isinstance(state, dict) else None

    def _write_state(self, state: dict[str, Any]) -> None:
        self.dev_root.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(self.state_path.name + ".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.state_path)

    def _clear_state(self) -> None:
        try:
            self.state_path.unlink()
        except FileNotFoundError:
            pass

    def _write_pidfile(self, record: dict[str, Any]) -> Path:
        self.pids_dir.mkdir(parents=True, exist_ok=True)
        pidfile = self.pids_dir / f"{record['role']}.pid"
        pidfile.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return pidfile

    def _load_records(self) -> list[dict[str, Any]]:
        """Merge state.json procs and pidfiles into one record list (pidfiles win)."""
        records: dict[int, dict[str, Any]] = {}
        state = self._read_state()
        if state:
            for proc in state.get("procs") or []:
                pid = proc.get("pid")
                if isinstance(pid, int):
                    records[pid] = dict(proc, source="state")
        pidfiles = sorted(self.pids_dir.glob("*.pid")) if self.pids_dir.exists() else []
        for pidfile in pidfiles:
            try:
                record = json.loads(pidfile.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                print(f"ignoring unreadable pidfile {pidfile}")
                continue
            if not isinstance(record, dict) or not isinstance(record.get("pid"), int):
                print(f"ignoring malformed pidfile {pidfile}")
                continue
            record = dict(record)
            record.setdefault("role", pidfile.stem)
            record["pidfile"] = pidfile
            records[record["pid"]] = record
        return list(records.values())

    # -- verification --------------------------------------------------------

    def _command_belongs_to_harness(self, live_command: str, recorded_command: str | None) -> bool:
        """Decide custody from the live command line, never from a process name."""
        live = " ".join(str(live_command).split())
        if not live:
            return False
        markers = (
            str(self.app_dir),
            str(self.dev_root),
            str(self.app_dir / "dist-browser-proof"),
        )
        recorded = " ".join(str(recorded_command).split()) if recorded_command else ""
        # The live command line must reference this harness's own paths before the
        # pid counts as ours, even if it happens to equal the recorded argv.
        if not any(marker in live for marker in markers):
            return False
        if not recorded:
            return True
        if live == recorded:
            return True
        # ps may render argv slightly differently; require the same argv[0] plus a
        # harness path marker (checked above) before we trust it.
        return live.split(" ", 1)[0] == recorded.split(" ", 1)[0]

    def _describe_proc(self, record: dict[str, Any]) -> str:
        pid = record.get("pid")
        role = record.get("role") or "unknown"
        if not self.ops.is_alive(pid):
            return f"pid {pid} ({role}): not running"
        live = self.ops.command_of(pid)
        if live is None:
            return f"pid {pid} ({role}): alive; command could not be read"
        if self._command_belongs_to_harness(live, record.get("command")):
            return f"pid {pid} ({role}): running (command verified)"
        return f"pid {pid} ({role}): alive but command does not reference this harness (not ours)"

    # -- commands ------------------------------------------------------------

    def _refuse_if_forbidden(self) -> int | None:
        reason = dev_root_refusal_reason(self.dev_root, allow_tmp=self.allow_tmp_dev_root)
        if reason is None:
            return None
        print(f"refusing dev root {self.dev_root}: {reason}")
        return EXIT_DEV_ROOT_REFUSED

    def up(self, *, fixture: bool, app: str, port: int) -> int:
        refused = self._refuse_if_forbidden()
        if refused is not None:
            return refused

        if not fixture:
            print(NOT_IMPLEMENTED_MESSAGE)
            print("reason: real dev Executive needs lane L4's local operator contract; use `up --fixture`.")
            return EXIT_NOT_IMPLEMENTED
        if app != "browser":
            print(NOT_IMPLEMENTED_MESSAGE)
            print("reason: --app native dev Tauri front lands in a later slice; --app browser is the default.")
            return EXIT_NOT_IMPLEMENTED
        if not 1 <= port <= 65535:
            print(f"invalid port {port}; expected 1-65535")
            return EXIT_ERROR

        existing = self._load_records()
        alive = [record for record in existing if self.ops.is_alive(record.get("pid"))]
        if alive:
            for record in alive:
                print(self._describe_proc(record))
            print("a recorded harness process is still alive; run `mmos_dev.py down` first")
            return EXIT_ALREADY_RUNNING
        self._prune_stale_records(existing)

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.pids_dir.mkdir(parents=True, exist_ok=True)

        node_modules = self.app_dir / "node_modules"
        if not node_modules.is_dir():
            print(f"installing app dependencies in {self.app_dir} ...")
            install_rc = self.ops.run(
                ["npm", "install", "--no-audit", "--no-fund"],
                cwd=self.app_dir,
                log_path=self.install_log,
            )
            if install_rc != 0:
                self._report_failure("npm install", self.install_log, install_rc)
                return EXIT_ERROR

        vite = self.app_dir / "node_modules" / ".bin" / "vite"
        if not vite.exists():
            print(f"missing {vite}; run `npm install` in {self.app_dir}")
            return EXIT_ERROR

        if not self.ops.port_available(port):
            print(f"port {port} is already in use on {DEFAULT_HOST} (strictPort); pass --port")
            return EXIT_PORT_IN_USE

        build_argv = [str(vite), "build", "--config", "vite.browser-proof.config.ts"]
        print(f"building browser-proof bundle (log: {self.build_log}) ...")
        build_rc = self.ops.run(build_argv, cwd=self.app_dir, log_path=self.build_log)
        if build_rc != 0:
            self._report_failure("vite build", self.build_log, build_rc)
            return EXIT_ERROR

        preview_argv = [
            str(vite),
            "preview",
            "--config",
            "vite.browser-proof.config.ts",
            "--host",
            DEFAULT_HOST,
            "--port",
            str(port),
            "--strictPort",
        ]
        pid = self.ops.spawn(preview_argv, cwd=self.app_dir, log_path=self.preview_log)
        url = self.url_for(port)
        if not self.ops.wait_for_http(url, PREVIEW_READY_TIMEOUT):
            self.ops.terminate(pid)
            self._report_failure("vite preview startup", self.preview_log, None)
            return EXIT_ERROR

        record = {
            "role": "vite-preview",
            "pid": pid,
            "command": _joined(preview_argv),
            "cwd": str(self.app_dir),
            "log_path": str(self.preview_log),
        }
        self._write_pidfile(record)
        self._write_state(
            {
                "mode": "fixture",
                "app": "browser",
                "dev_root": str(self.dev_root),
                "host": DEFAULT_HOST,
                "port": port,
                "url": url,
                "socket_path": str(self.socket_path),
                "started_at": _now_iso(),
                "procs": [record],
                "logs": {name: str(path) for name, path in self.log_paths().items()},
            }
        )

        print("MMOS dev harness up - mode=fixture app=browser")
        print(f"Open: {url}")
        print("Text control for this mode is the browser DOM (details in the harness runbook).")
        print(f"pid {pid} (vite-preview); dev root {self.dev_root}")
        return EXIT_OK

    def down(self) -> int:
        refused = self._refuse_if_forbidden()
        if refused is not None:
            return refused

        records = self._load_records()
        if not records:
            print("no recorded harness processes; nothing to stop")
            self._clear_state()
            return EXIT_OK

        stopped = 0
        skipped = 0
        seen: set[int] = set()
        for record in records:
            pid = record.get("pid")
            if not isinstance(pid, int) or pid in seen:
                continue
            seen.add(pid)
            role = record.get("role") or "unknown"
            pidfile = record.get("pidfile")
            if not self.ops.is_alive(pid):
                print(f"pid {pid} ({role}): not running; removed stale record")
                self._remove_pidfile(pidfile)
                continue
            live = self.ops.command_of(pid)
            if live is None:
                print(f"pid {pid} ({role}): alive but command could not be read; skipped, record kept")
                skipped += 1
                continue
            if not self._command_belongs_to_harness(live, record.get("command")):
                print(
                    f"pid {pid} ({role}): live command does not reference this harness's paths; "
                    "skipped (not ours), record removed"
                )
                skipped += 1
                self._remove_pidfile(pidfile)
                continue
            result = self.ops.terminate(pid)
            print(f"pid {pid} ({role}): {result}")
            stopped += 1
            self._remove_pidfile(pidfile)
        self._clear_state()
        print(f"down complete: stopped {stopped}, skipped {skipped}")
        return EXIT_OK

    def status(self) -> int:
        refused = self._refuse_if_forbidden()
        if refused is not None:
            return refused

        state = self._read_state()
        procs: list[dict[str, Any]]
        if state:
            procs = [proc for proc in state.get("procs") or [] if isinstance(proc, dict)]
        elif self.pids_dir.exists():
            procs = self._load_records()
        else:
            procs = []

        lines: list[str] = []
        if state:
            lines.append(f"mode: {state.get('mode', 'unknown')}")
            lines.append(f"app: {state.get('app', 'unknown')}")
        else:
            lines.append("mode: (not started)")
            lines.append("app: (none)")
        lines.append(f"dev root: {self.dev_root}")
        lines.append(f"control socket (planned): {self.socket_path}")
        running = any(self.ops.is_alive(proc.get("pid")) for proc in procs)
        lines.append(f"state: {'running' if running else 'stopped'}")
        if state:
            lines.append(f"port: {state.get('port')}")
            lines.append(f"url: {state.get('url')}")
            lines.append(f"started: {state.get('started_at')}")
        for record in procs:
            lines.append(self._describe_proc(record))
        lines.append("logs:")
        for name, path in self.log_paths().items():
            marker = "present" if path.exists() else "not created"
            lines.append(f"  {name}: {path} ({marker})")
        print("\n".join(lines))
        return EXIT_OK

    # -- helpers -------------------------------------------------------------

    def _prune_stale_records(self, records: Sequence[dict[str, Any]]) -> None:
        """Drop records whose pid is gone, plus any leftover state file."""
        for record in records:
            pid = record.get("pid")
            if not self.ops.is_alive(pid):
                self._remove_pidfile(record.get("pidfile"))
        if not any(self.ops.is_alive(record.get("pid")) for record in records):
            self._clear_state()

    def _remove_pidfile(self, pidfile: Any) -> None:
        if isinstance(pidfile, Path):
            try:
                pidfile.unlink()
            except FileNotFoundError:
                pass

    def _report_failure(self, stage: str, log_path: Path, returncode: int | None) -> None:
        detail = f" (exit {returncode})" if returncode is not None else ""
        print(f"{stage} failed{detail}; see {log_path}")
        tail = _tail(log_path, 20)
        if tail:
            print("--- last log lines ---")
            print(tail)


def _tail(path: Path, lines: int) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mmos_dev.py", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    up = subparsers.add_parser("up", help="build and start the dev harness")
    up.add_argument("--fixture", action="store_true", help="fixture mode (the only implemented front)")
    up.add_argument("--app", choices=("browser", "native"), default="browser")
    up.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"loopback port (default {DEFAULT_PORT})")

    subparsers.add_parser("down", help="stop exactly the processes this harness recorded")
    subparsers.add_parser("status", help="render recorded harness state as plain text")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    ops: SystemProcessOps | None = None,
    dev_root: os.PathLike[str] | str | None = None,
    app_dir: os.PathLike[str] | str | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    harness = DevHarness(
        app_dir=app_dir,
        dev_root=dev_root,
        ops=ops,
        allow_tmp_dev_root=dev_root is not None,
    )
    if args.command == "up":
        return harness.up(fixture=args.fixture, app=args.app, port=args.port)
    if args.command == "down":
        return harness.down()
    return harness.status()


if __name__ == "__main__":
    raise SystemExit(main())
