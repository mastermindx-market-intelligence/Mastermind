"""Shared fixtures for the Hermes runtime acceptance tests."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[3]
CENSUS = REPO / "integrations/hermes_qualification/tests/fixture-cli-toolsets.txt"
STUB = Path(__file__).resolve().parent / "fixtures" / "hermes_stub.py"
TOKEN = "local-test-gateway-token"


def write_secrets(path: Path, token: str = TOKEN, extra: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, f"HERMES_GATEWAY_TOKEN={token}\n{extra}".encode("utf-8"))
    finally:
        os.close(fd)


def yaml_scalar(value: str) -> str:
    if value == "" or any(ch in value for ch in ":#{}[]&*!|>%@`'\""):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def profile_text(
    *,
    state: Path,
    secrets: Path,
    sha: str,
    repository: str,
    role: str = "mmsecretary",
    host: str = "127.0.0.1",
    port: int = 0,
    backend: int = 0,
    auth: str = "required",
    allow: tuple[str, ...] = ("clarify",),
    provider: str = "zai",
    default: str = "glm-5.3-flash",
    restart: str = "on-failure",
    restart_sec: float = 0,
    burst: int = 5,
    sample: float = 0.02,
) -> str:
    allow_lines = "\n".join(f"  - {name}" for name in allow)
    return (
        "schema: mastermind.hermes_runtime_profile.v1\n"
        "upstream:\n"
        f"  repository: {repository}\n"
        f"  sha: {sha}\n"
        f"role: {role}\n"
        "tool_allowlist:\n"
        f"{allow_lines}\n"
        "model:\n"
        f"  provider: {provider}\n"
        f"  default: {default}\n"
        f"secrets_file: {secrets}\n"
        "gateway:\n"
        f"  host: {yaml_scalar(host)}\n"
        f"  port: {port}\n"
        f"  backend_port: {backend}\n"
        f"  auth: {auth}\n"
        "service:\n"
        f"  restart: {restart}\n"
        f"  restart_sec: {restart_sec}\n"
        f"  start_limit_burst: {burst}\n"
        "  start_limit_interval_sec: 60\n"
        "memory:\n"
        f"  sample_interval_sec: {sample}\n"
        f"state_dir: {state}\n"
    )


def http_get(url: str, token: str | None = None, timeout: float = 2) -> tuple[int, bytes]:
    request = urllib.request.Request(url)
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def load_preflight():
    path = REPO / "integrations/hermes_qualification/preflight.py"
    spec = importlib.util.spec_from_file_location("hermes_qualification_preflight", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("preflight module missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def listening_addresses(port: int) -> list[str]:
    found: list[str] = []
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        path = Path(table)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split()
            local, state = parts[1], parts[3]
            if state != "0A":
                continue
            ip, hexport = local.split(":")
            if int(hexport, 16) == port:
                found.append(ip)
    return found


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
