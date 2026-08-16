"""Production-inert laboratory: isolated workspace, JSON-RPC client, no Executive I/O."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import queue
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

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


@dataclass
class Laboratory:
    root: Path
    backend: str
    requested_model: str = "gpt-5.6-sol"
    probe_id: str = field(default_factory=lambda: f"ohf-p0-{uuid.uuid4().hex[:12]}")

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.workspace = self.root / "workspace"
        self.codex_home = self.root / "codex_home"
        self.evidence = self.root / "evidence"
        self.state_path = self.codex_home / "ohf_fake_state.json"
        self.config_path = self.codex_home / "config.toml"
        for path in (self.workspace, self.codex_home, self.evidence):
            path.mkdir(parents=True, exist_ok=True)
        self._write_isolated_config()
        self._install_skill()

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

    def copy_auth_if_present(self) -> bool:
        """Copy ChatGPT auth into the isolated home without loading it into evidence."""
        src = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
        if not src.is_file():
            return False
        dest = self.codex_home / "auth.json"
        shutil.copy2(src, dest)
        os.chmod(dest, 0o600)
        return True

    def drop_mcp(self) -> None:
        self._write_isolated_config(include_mcp=False)

    def mutate_config_for_drift(self) -> None:
        current = self.config_path.read_text(encoding="utf-8")
        self.config_path.write_text(current + '\n# ohf-drift-marker = "1"\n', encoding="utf-8")

    def destroy_workspace(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def env(self) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.root / "home"),
            "CODEX_HOME": str(self.codex_home),
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


class AppServerClient:
    """Line-delimited JSON-RPC client.  Codex omits the jsonrpc header on the wire."""

    def __init__(self, argv: list[str], *, env: Mapping[str, str], cwd: Path) -> None:
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
        self.pid: int | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.cwd),
            env=self.env,
        )
        self.pid = self.proc.pid
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
                self._stdout.put(redact_evidence(payload))
        self._stdout.put(None)

    def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for raw in self.proc.stderr:
            self._stderr_chunks.append(redact_text(raw.decode("utf-8", errors="replace")))

    def stderr_text(self) -> str:
        return redact_text("".join(self._stderr_chunks))

    def _send(self, payload: Mapping[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise JsonRpcError("app-server stdin is closed")
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
        self.proc.stdin.write(b"{not-json\n")
        self.proc.stdin.flush()

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        message: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = dict(params)
        self._send(message)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JsonRpcError(f"timeout waiting for {method}")
            try:
                payload = self._stdout.get(timeout=remaining)
            except queue.Empty as exc:
                raise JsonRpcError(f"timeout waiting for {method}") from exc
            if payload is None:
                raise JsonRpcError(f"app-server exited before answering {method}")
            if payload.get("_malformed"):
                self.notifications.append(payload)
                continue
            if payload.get("id") == request_id:
                if "error" in payload:
                    raise JsonRpcError(
                        redact_text(str((payload.get("error") or {}).get("message") or payload["error"])),
                        payload,
                    )
                result = payload.get("result")
                return result if isinstance(result, dict) else {"value": result}
            if payload.get("method"):
                self.notifications.append(payload)

    def wait_notification(self, method: str, *, timeout: float = 15.0) -> dict[str, Any]:
        for existing in self.notifications:
            if existing.get("method") == method:
                self.notifications.remove(existing)
                return existing
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JsonRpcError(f"timeout waiting for notification {method}")
            try:
                payload = self._stdout.get(timeout=remaining)
            except queue.Empty as exc:
                raise JsonRpcError(f"timeout waiting for notification {method}") from exc
            if payload is None:
                raise JsonRpcError(f"app-server exited before {method}")
            if payload.get("method") == method:
                return payload
            if payload.get("method") or payload.get("_malformed"):
                self.notifications.append(payload)

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def terminate(self, *, wait: float = 5.0) -> str:
        if self.proc is None:
            return "already-stopped"
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=wait)
                return "sigterm"
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=wait)
                return "sigterm-escalated-kill"
        return "already-exited"

    def kill(self) -> str:
        if self.proc is None:
            return "already-stopped"
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)
            return "sigkill"
        return "already-exited"

    def close(self) -> None:
        if self.alive():
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
