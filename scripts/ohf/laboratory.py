"""Production-inert laboratory: isolated workspace, JSON-RPC client, no Executive I/O."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import queue
import signal
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from scripts.ohf.redaction import redact_evidence, redact_text

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ohf_probe_skill"

FORBIDDEN_IMPORT_PREFIXES = (
    "control_plane.executive_runtime",
    "control_plane.executive_service",
    "control_plane.executive_supervisor",
    "control_plane.executive_workspace",
    "control_plane.executive_worker_broker",
    "control_plane.executive_inbox",
    "control_plane.worker_adapter",
    "control_plane.codex_worker",
    "control_plane.executive_authority",
    "control_plane.executive_canary",
    "app.scheduler",
)

FORBIDDEN_WRITE_NAMES = (
    "executive.sqlite",
    "executive.db",
    "auth.json",
    "executive_worker_routes.json",
    "strategic_state.yml",
)


def _strip_toml_table(text: str, header: str) -> str:
    lines: list[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            skipping = stripped == header
        if not skipping:
            lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


def default_user_codex_home() -> Path:
    return (Path.home() / ".codex").resolve()


def inspect_codex_home(path: Path) -> dict[str, Any]:
    """Safe directory metadata.  Never reads credential bytes."""
    resolved = Path(path).expanduser().resolve()
    return {
        "path": str(resolved),
        "exists": resolved.is_dir(),
        "auth_json_present": (resolved / "auth.json").is_file(),
        "config_toml_present": (resolved / "config.toml").is_file(),
        "is_default_user_home": resolved == default_user_codex_home(),
    }


def validate_live_codex_home(path: Path) -> dict[str, Any]:
    meta = inspect_codex_home(path)
    if meta["is_default_user_home"]:
        raise RuntimeError(
            "live mode refuses the implicit ~/.codex home; pass a dedicated --codex-home"
        )
    if not meta["exists"]:
        raise RuntimeError(f"--codex-home is not a directory: {meta['path']}")
    if not meta["auth_json_present"]:
        raise RuntimeError(
            "dedicated CODEX_HOME is not authenticated independently "
            "(auth.json missing). Prepare it with: "
            f"CODEX_HOME={meta['path']} codex login"
        )
    return meta


@dataclass
class Laboratory:
    root: Path
    backend: str
    requested_model: str = "gpt-5.6-sol"
    dedicated_codex_home: Path | None = None
    probe_id: str = field(default_factory=lambda: f"ohf-p0-{uuid.uuid4().hex[:12]}")

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.workspace = self.root / "workspace"
        self.codex_home = self.root / "codex_home"
        self.evidence = self.root / "evidence"
        self.state_path = self.codex_home / "ohf_fake_state.json"
        self.config_path = self.codex_home / "config.toml"
        if self.dedicated_codex_home is not None:
            self.dedicated_codex_home = (
                Path(self.dedicated_codex_home).expanduser().resolve()
            )
        for path in (self.workspace, self.codex_home, self.evidence):
            path.mkdir(parents=True, exist_ok=True)
        self._write_isolated_config()
        self._install_skill()
        self.live_home_meta: dict[str, Any] = {}
        if self.backend == "live":
            if self.dedicated_codex_home is None:
                raise RuntimeError("live mode requires an explicit --codex-home")
            self.live_home_meta = validate_live_codex_home(self.dedicated_codex_home)
            self._merge_live_probe_config()

    def _write_isolated_config(self, *, include_mcp: bool = True) -> None:
        python = shutil.which("python3") or shutil.which("python") or "python3"
        mcp_block = ""
        if include_mcp:
            mcp_block = "\n".join(
                [
                    "",
                    "[mcp_servers.ohf_probe]",
                    f'command = "{python}"',
                    f'args = ["-m", "scripts.ohf.fixtures.ohf_probe_mcp"]',
                    f'cwd = "{REPO_ROOT}"',
                    "startup_timeout_sec = 10",
                ]
            )
        self.config_path.write_text(
            "\n".join(
                [
                    f'model = "{self.requested_model}"',
                    'approval_policy = "never"',
                    'sandbox_mode = "read-only"',
                    mcp_block,
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _install_skill(self) -> None:
        dest = self.workspace / ".agents" / "skills" / "ohf-probe"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SKILL_FIXTURE / "SKILL.md", dest / "SKILL.md")

    def expected_bundle(self) -> dict[str, Any]:
        return {
            "mcp": ["ohf_probe"],
            "skills": ["ohf-probe"],
            "plugins": [],
            "model": self.requested_model,
            "config_source": str(self.config_path),
        }

    def config_digest(self) -> str:
        return hashlib.sha256(self.config_path.read_bytes()).hexdigest()

    def host_facts(self) -> dict[str, str]:
        return {
            "platform": platform.system().lower(),
            "architecture": platform.machine(),
            "principal": f"uid-{os.geteuid()}",
        }

    def _merge_live_probe_config(self) -> None:
        """Write non-secret probe MCP/model overlay into the dedicated home.

        Never copies, reads, or symlinks auth.json.
        """
        assert self.dedicated_codex_home is not None
        dest = self.dedicated_codex_home / "config.toml"
        overlay = self.config_path.read_text(encoding="utf-8")
        dest.write_text(overlay, encoding="utf-8")

    def drop_mcp(self) -> None:
        self._write_isolated_config(include_mcp=False)
        if self.backend == "live" and self.dedicated_codex_home is not None:
            dest = self.dedicated_codex_home / "config.toml"
            if dest.is_file():
                text = dest.read_text(encoding="utf-8")
                for header in (
                    "[mcp_servers.ohf_probe]",
                    "[mcp_servers.ohf_probe_removed]",
                ):
                    text = _strip_toml_table(text, header)
                dest.write_text(text, encoding="utf-8")

    def drop_skill(self) -> None:
        dest = self.workspace / ".agents" / "skills" / "ohf-probe"
        if dest.exists():
            shutil.rmtree(dest)

    def mutate_config_for_drift(self) -> None:
        current = self.config_path.read_text(encoding="utf-8")
        self.config_path.write_text(
            current + '\n# ohf-drift-marker = "1"\n', encoding="utf-8"
        )
        if self.backend == "live" and self.dedicated_codex_home is not None:
            dest = self.dedicated_codex_home / "config.toml"
            if dest.is_file():
                dest.write_text(
                    dest.read_text(encoding="utf-8") + '\n# ohf-drift-marker = "1"\n',
                    encoding="utf-8",
                )

    def destroy_workspace(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def live_codex_home(self) -> Path:
        if self.backend != "live" or self.dedicated_codex_home is None:
            raise RuntimeError("live Codex home is only available in live mode")
        return self.dedicated_codex_home

    def env(self) -> dict[str, str]:
        if self.backend == "live":
            if self.dedicated_codex_home is None:
                raise RuntimeError("live mode requires an explicit --codex-home")
            if self.dedicated_codex_home == default_user_codex_home():
                raise RuntimeError("live mode refuses implicit ~/.codex fallback")
            codex_home = str(self.dedicated_codex_home)
        else:
            codex_home = str(self.codex_home)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.root / "home"),
            "CODEX_HOME": codex_home,
            "OHF_FAKE_STATE": str(self.state_path),
            "OHF_FAKE_WORKSPACE": str(self.workspace),
            "OHF_FAKE_SKILL_ROOT": str(self.workspace / ".agents" / "skills"),
            "OHF_FAKE_MODEL": self.requested_model,
            "OHF_INERT": "1",
            "PYTHONPATH": str(REPO_ROOT),
            "LC_ALL": "C",
        }
        Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
        for key, value in os.environ.items():
            if key.startswith("OHF_FAKE_"):
                env[key] = value
        return env


class JsonRpcError(RuntimeError):
    def __init__(self, message: str, payload: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = dict(payload or {})


@dataclass(frozen=True)
class AppServerStopProof:
    """Typed containment result for a locally-owned App Server process group."""

    controller_returncode: int | None
    private_group_id: int | None
    private_group_empty: bool
    leader_exit_confirmed_graceful: bool
    survivors_detected_after_controller_exit: bool
    termination_outcome: str


class AppServerClient:
    """Line-delimited JSON-RPC client.  Codex omits the jsonrpc header on the wire."""

    def __init__(
        self,
        argv: list[str],
        *,
        env: Mapping[str, str],
        cwd: Path,
        start_new_session: bool = False,
    ) -> None:
        self.argv = list(argv)
        self.env = dict(env)
        self.cwd = Path(cwd)
        self.proc: subprocess.Popen[bytes] | None = None
        self._stdout: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._stderr_chunks: list[str] = []
        self._next_id = 1
        self._reader: threading.Thread | None = None
        self._err_reader: threading.Thread | None = None
        self.notifications: list[dict[str, Any]] = []
        self._responses: dict[int, queue.Queue[dict[str, Any] | None]] = {}
        self._transport_lock = threading.Lock()
        self._notification_condition = threading.Condition(self._transport_lock)
        self._write_lock = threading.Lock()
        self._transport_closed = False
        self.pid: int | None = None
        self.start_new_session = start_new_session
        self._private_pgid: int | None = None
        self.last_termination_outcome: str | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.cwd),
            env=self.env,
            start_new_session=self.start_new_session,
        )
        self.pid = self.proc.pid
        if self.start_new_session:
            observed_pgid = os.getpgid(self.proc.pid)
            if observed_pgid != self.proc.pid or observed_pgid == os.getpgrp():
                self.proc.kill()
                self.proc.wait(timeout=5)
                raise RuntimeError(
                    "contained app-server did not obtain a private process group"
                )
            self._private_pgid = observed_pgid
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._err_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._err_reader.start()

    def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                self._stdout.put({"_malformed": True, "raw": redact_text(line)})
                continue
            if isinstance(payload, dict):
                observed = redact_evidence(payload)
                with self._notification_condition:
                    response_id = observed.get("id")
                    target = (
                        self._responses.get(response_id)
                        if isinstance(response_id, int)
                        else None
                    )
                    if target is not None:
                        target.put(observed)
                    else:
                        self.notifications.append(observed)
                        self._notification_condition.notify_all()
        with self._notification_condition:
            self._transport_closed = True
            for target in self._responses.values():
                target.put(None)
            self._notification_condition.notify_all()

    def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for raw in self.proc.stderr:
            self._stderr_chunks.append(
                redact_text(raw.decode("utf-8", errors="replace"))
            )

    def stderr_text(self) -> str:
        return redact_text("".join(self._stderr_chunks))

    def _send(self, payload: Mapping[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise JsonRpcError("app-server stdin is closed")
        with self._write_lock:
            self.proc.stdin.write((json.dumps(dict(payload)) + "\n").encode("utf-8"))
            self.proc.stdin.flush()

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params:
            message["params"] = dict(params)
        self._send(message)

    def send_malformed(self) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise JsonRpcError("app-server stdin is closed")
        with self._write_lock:
            self.proc.stdin.write(b"{not-json\n")
            self.proc.stdin.flush()

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        response_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=1)
        with self._notification_condition:
            if self._transport_closed:
                raise JsonRpcError(f"app-server exited before answering {method}")
            request_id = self._next_id
            self._next_id += 1
            self._responses[request_id] = response_queue
        message: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = dict(params)
        try:
            self._send(message)
            try:
                payload = response_queue.get(timeout=timeout)
            except queue.Empty as exc:
                raise JsonRpcError(f"timeout waiting for {method}") from exc
            if payload is None:
                raise JsonRpcError(f"app-server exited before answering {method}")
            if "error" in payload:
                raise JsonRpcError(
                    redact_text(
                        str(
                            (payload.get("error") or {}).get("message")
                            or payload["error"]
                        )
                    ),
                    payload,
                )
            result = payload.get("result")
            return result if isinstance(result, dict) else {"value": result}
        finally:
            with self._notification_condition:
                self._responses.pop(request_id, None)

    def wait_notification(
        self, method: str, *, timeout: float = 15.0
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self._notification_condition:
            while True:
                for existing in self.notifications:
                    if existing.get("method") == method:
                        self.notifications.remove(existing)
                        return existing
                if self._transport_closed:
                    raise JsonRpcError(f"app-server exited before {method}")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise JsonRpcError(f"timeout waiting for notification {method}")
                self._notification_condition.wait(timeout=remaining)

    def drain_notifications(self) -> list[dict[str, Any]]:
        with self._notification_condition:
            drained = list(self.notifications)
            self.notifications.clear()
            return drained

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _private_group_status(self) -> Literal["ALIVE", "EMPTY", "UNKNOWN"]:
        """Return the observable state of the independently-owned process group.

        This deliberately never probes or signals an inherited/controller process
        group.  A private group is accepted only when ``start()`` observed that
        its PGID equals the child controller PID and differs from ours.
        """

        if self._private_pgid is None:
            return "EMPTY"
        if self.pid is None or self._private_pgid != self.pid:
            raise RuntimeError("refusing to inspect an unverified process group")
        if self._private_pgid == os.getpgrp():
            raise RuntimeError("refusing to inspect the controller process group")
        try:
            os.killpg(self._private_pgid, 0)
        except ProcessLookupError:
            return "EMPTY"
        except PermissionError:
            # This may be a recycled PGID or an inaccessible survivor.  It is
            # never proof of emptiness and must not authorize a later signal.
            return "UNKNOWN"
        return "ALIVE"

    def private_group_alive(self) -> bool:
        status = self._private_group_status()
        if status == "UNKNOWN":
            raise RuntimeError("private process-group emptiness is unprovable")
        return status == "ALIVE"

    def _wait_for_private_group_exit(self, *, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.001, timeout)
        while True:
            status = self._private_group_status()
            if status == "EMPTY":
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def _record_termination(self, outcome: str) -> str:
        self.last_termination_outcome = outcome
        return outcome

    def graceful_close(self, *, wait: float = 5.0) -> AppServerStopProof:
        """Close stdin, then prove the entire contained process group is gone.

        A clean App Server leader exit is not sufficient evidence: a same-group
        descendant can continue operating after the leader exits.  In that case
        containment escalates TERM then KILL for the verified private group.  An
        uncontained or unprovable group never yields an empty proof.
        """

        if self.proc is None:
            return AppServerStopProof(
                controller_returncode=None,
                private_group_id=None,
                private_group_empty=False,
                leader_exit_confirmed_graceful=False,
                survivors_detected_after_controller_exit=False,
                termination_outcome="not-started",
            )
        if self._private_pgid is None:
            return AppServerStopProof(
                controller_returncode=self.proc.poll(),
                private_group_id=None,
                private_group_empty=False,
                leader_exit_confirmed_graceful=False,
                survivors_detected_after_controller_exit=False,
                termination_outcome="uncontained",
            )
        graceful_leader_exit = True
        outcome = "stdin-close"
        try:
            if self.proc.poll() is None and self.proc.stdin is not None:
                self.proc.stdin.close()
                self.proc.wait(timeout=wait)
        except (OSError, subprocess.SubprocessError) as exc:
            # Contain an unresponsive/transport-broken leader before returning
            # control, but retain that the graceful exit itself is unproven.
            graceful_leader_exit = False
            try:
                outcome = self.terminate(wait=wait)
            except (OSError, RuntimeError, subprocess.SubprocessError) as stop_exc:
                raise RuntimeError(
                    "graceful App Server leader exit and containment are unproven"
                ) from stop_exc

        survivors = self.private_group_alive()
        if survivors:
            outcome = self.terminate(wait=wait)
        empty = not self.private_group_alive()
        if not empty:
            raise RuntimeError("contained App Server process group is not empty")
        return AppServerStopProof(
            controller_returncode=self.proc.returncode,
            private_group_id=self._private_pgid,
            private_group_empty=True,
            leader_exit_confirmed_graceful=graceful_leader_exit,
            survivors_detected_after_controller_exit=survivors,
            termination_outcome=outcome,
        )

    def terminate(self, *, wait: float = 5.0) -> str:
        if self.proc is None:
            return self._record_termination("already-stopped")
        if self._private_pgid is not None:
            if self.pid is None or self._private_pgid != self.pid:
                raise RuntimeError("refusing to signal an unverified process group")
            if self._private_pgid == os.getpgrp():
                raise RuntimeError("refusing to signal the controller process group")
            try:
                os.killpg(self._private_pgid, signal.SIGTERM)
            except ProcessLookupError:
                return self._record_termination("already-exited")
            try:
                self.proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                pass
            if self._wait_for_private_group_exit(timeout=0.05):
                return self._record_termination("sigterm")
            if self._private_group_status() != "ALIVE":
                raise RuntimeError("private process-group emptiness is unprovable")
            os.killpg(self._private_pgid, signal.SIGKILL)
            if self.proc.poll() is None:
                self.proc.wait(timeout=wait)
            if not self._wait_for_private_group_exit(timeout=wait):
                raise RuntimeError(
                    "contained app-server process group survived SIGKILL"
                )
            return self._record_termination("sigterm-escalated-kill")
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=wait)
                return self._record_termination("sigterm")
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=wait)
                return self._record_termination("sigterm-escalated-kill")
        return self._record_termination("already-exited")

    def kill(self) -> str:
        if self.proc is None:
            return self._record_termination("already-stopped")
        if self._private_pgid is not None:
            if self.pid is None or self._private_pgid != self.pid:
                raise RuntimeError("refusing to signal an unverified process group")
            if self._private_pgid == os.getpgrp():
                raise RuntimeError("refusing to signal the controller process group")
            try:
                os.killpg(self._private_pgid, signal.SIGKILL)
            except ProcessLookupError:
                return self._record_termination("already-exited")
            if self.proc.poll() is None:
                self.proc.wait(timeout=5)
            if not self._wait_for_private_group_exit(timeout=5):
                raise RuntimeError(
                    "contained app-server process group survived SIGKILL"
                )
            return self._record_termination("sigkill")
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)
            return self._record_termination("sigkill")
        return self._record_termination("already-exited")

    def close(self) -> None:
        if self.alive() or self.private_group_alive():
            self.terminate()


def binary_digest(path: str | None) -> str:
    if not path:
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_path_is_laboratory(path: Path, lab: Laboratory) -> None:
    resolved = path.resolve()
    if resolved.name in FORBIDDEN_WRITE_NAMES and lab.root not in resolved.parents:
        raise RuntimeError(f"refusing to write production path {resolved}")
    text = str(resolved)
    if "executive.sqlite" in text or "executive.db" in text:
        if lab.root not in resolved.parents:
            raise RuntimeError(f"refusing Executive SQLite path {resolved}")
