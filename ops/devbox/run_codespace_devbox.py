"""Run the authenticated Mastermind DevBox MCP inside one bound Codespace.

GitHub owns Codespace lifecycle. This process composes one exact already-running
Codespace workspace with existing Mastermind auth/audit and the four-tool DevBox
facade. It never creates a Codespace, GitHub credential, Executive lifecycle row,
worker identity, target registry, retry plane, or source-publication path.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import stat
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from integrations.business_mcp_auth.audit import DurableAuthAuditSink
from integrations.business_mcp_auth.contracts import (
    ResourcePolicy,
    load_resource_policy,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache, HttpxJwksFetcher
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.devbox_mcp.app import create_authenticated_devbox_server
from integrations.devbox_mcp.codespace_runtime import CodespaceBinding, CodespaceDevBoxRuntime
from integrations.devbox_mcp.deployment import BoundDevBoxPort, StableDevBoxLease
from ops.devbox.codespace_preflight import (
    CodespacePreflight,
    qualify_codespace_environment,
)

_LEASE_SCHEMA = "mastermind.devbox_lease.v1"
_MAX_CONFIG_BYTES = 64 * 1024
_SERVICE_ENV_MARKER = "MASTERMIND_DEVBOX_ENV_SANITIZED"
_SERVICE_ENV_ALLOWLIST = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM", "COLORTERM",
    "CODESPACES", "CODESPACE_NAME",
    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "GITHUB_REPOSITORY",
)
_SERVICE_ENV_REQUIRED = (
    "PATH", "HOME", "CODESPACES", "CODESPACE_NAME",
    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "GITHUB_REPOSITORY",
)


class DevBoxServiceConfigurationError(RuntimeError):
    pass


def build_sanitized_service_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Strip ambient credentials before the long-lived MCP process exists."""
    if not isinstance(source, Mapping):
        raise DevBoxServiceConfigurationError("service environment is invalid")
    selected: dict[str, str] = {}
    for name in _SERVICE_ENV_ALLOWLIST:
        value = source.get(name)
        if value is None:
            continue
        if type(value) is not str or not value or "\x00" in value:
            raise DevBoxServiceConfigurationError("service environment is invalid")
        selected[name] = value
    if any(name not in selected for name in _SERVICE_ENV_REQUIRED):
        raise DevBoxServiceConfigurationError("required Codespace service environment is absent")
    if selected["CODESPACES"] != "true":
        raise DevBoxServiceConfigurationError("qualified Codespace service environment is required")
    selected[_SERVICE_ENV_MARKER] = "1"
    return selected


def _configuration(message: str) -> None:
    raise DevBoxServiceConfigurationError(message)


def _read_owned_json(path: Path | str) -> dict[str, Any]:
    selected = Path(path).absolute()
    if selected.is_symlink():
        _configuration("configuration file must not be a symlink")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not cloexec:
        _configuration("secure configuration open is not qualified")
    try:
        named = selected.lstat()
    except OSError as exc:
        raise DevBoxServiceConfigurationError("configuration file is unavailable") from exc
    if (
        not stat.S_ISREG(named.st_mode)
        or named.st_uid != os.geteuid()
        or named.st_nlink != 1
        or stat.S_IMODE(named.st_mode) & 0o022
        or named.st_size <= 0
        or named.st_size > _MAX_CONFIG_BYTES
    ):
        _configuration("configuration file security refused")
    fd = -1
    try:
        fd = os.open(selected, os.O_RDONLY | nofollow | cloexec)
        observed = os.fstat(fd)
        if (
            observed.st_dev != named.st_dev
            or observed.st_ino != named.st_ino
            or observed.st_uid != named.st_uid
            or observed.st_mode != named.st_mode
            or observed.st_nlink != named.st_nlink
            or observed.st_size != named.st_size
            or os.get_inheritable(fd)
        ):
            _configuration("configuration identity changed")
        raw = os.read(fd, _MAX_CONFIG_BYTES + 1)
        if len(raw) != named.st_size or len(raw) > _MAX_CONFIG_BYTES:
            _configuration("configuration read is incomplete or oversized")
    except DevBoxServiceConfigurationError:
        raise
    except OSError as exc:
        raise DevBoxServiceConfigurationError("configuration read failed") from exc
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DevBoxServiceConfigurationError("configuration JSON is invalid") from exc
    if type(value) is not dict:
        _configuration("configuration root must be an object")
    return value


def load_devbox_lease(path: Path | str) -> StableDevBoxLease:
    value = _read_owned_json(path)
    expected = {
        "schema",
        "expected_subject_digest",
        "expected_client_ref",
        "resource",
        "required_scopes",
        "target_ref",
        "generation",
        "owner_ref",
        "repository",
        "committed_head",
        "lease_expires_at",
    }
    if set(value) != expected or value.get("schema") != _LEASE_SCHEMA:
        _configuration("DevBox lease schema is invalid")
    scopes = value.get("required_scopes")
    if type(scopes) is not list or any(type(item) is not str for item in scopes):
        _configuration("DevBox lease scopes are invalid")
    try:
        return StableDevBoxLease(
            expected_subject_digest=value["expected_subject_digest"],
            expected_client_ref=value["expected_client_ref"],
            resource=value["resource"],
            required_scopes=tuple(scopes),
            target_ref=value["target_ref"],
            generation=value["generation"],
            owner_ref=value["owner_ref"],
            repository=value["repository"],
            committed_head=value["committed_head"],
            lease_expires_at=value["lease_expires_at"],
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise DevBoxServiceConfigurationError("DevBox lease is invalid") from exc


def load_devbox_policy(path: Path | str) -> ResourcePolicy:
    try:
        return load_resource_policy(_read_owned_json(path))
    except DevBoxServiceConfigurationError:
        raise
    except Exception as exc:
        raise DevBoxServiceConfigurationError("DevBox auth policy is invalid") from exc


@dataclasses.dataclass
class CodespaceDevBoxService:
    preflight: CodespacePreflight
    lease: StableDevBoxLease
    policy: ResourcePolicy
    runtime: CodespaceDevBoxRuntime
    port: BoundDevBoxPort
    server: Any
    audit_sink: DurableAuthAuditSink
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.audit_sink.close()


def _open_audit_sink(state_root: Path, policy_id: str) -> DurableAuthAuditSink:
    directory = state_root / "auth-audit"
    try:
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
        info = directory.lstat()
    except OSError as exc:
        raise DevBoxServiceConfigurationError("audit directory could not be prepared") from exc
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or directory.is_symlink()
    ):
        _configuration("audit directory security refused")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    host_fd = -1
    try:
        host_fd = os.open(directory, flags)
        return DurableAuthAuditSink.open(host_fd, policy_id=policy_id)
    except Exception as exc:
        raise DevBoxServiceConfigurationError("durable auth audit could not be opened") from exc
    finally:
        if host_fd >= 0:
            os.close(host_fd)


def build_codespace_service(
    *,
    repo_root: Path | str,
    state_root: Path | str,
    policy_file: Path | str,
    lease_file: Path | str,
    port: int,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    shell_path: Path | str = Path("/bin/bash"),
    now: Any = None,
) -> CodespaceDevBoxService:
    """Compose, but do not start, one exact Codespace DevBox MCP service."""

    lease = load_devbox_lease(lease_file)
    policy = load_devbox_policy(policy_file)
    preflight = qualify_codespace_environment(
        repo_root=repo_root,
        state_root=state_root,
        expected_repository=lease.repository,
        port=port,
        env=env,
        platform_name=platform_name,
    )
    if (
        lease.repository != preflight.repository
        or lease.committed_head != preflight.observed_head
        or lease.resource != preflight.forwarded_mcp_url
        or policy.resource != lease.resource
        or policy.required_scopes != lease.required_scopes
        or policy.allowed_subject_digests != (lease.expected_subject_digest,)
    ):
        _configuration("policy, lease, Codespace and current source do not compose exactly")

    binding = CodespaceBinding(
        target_ref=lease.target_ref,
        generation=lease.generation,
        owner_ref=lease.owner_ref,
        repository=lease.repository,
        committed_head=lease.committed_head,
    )
    runtime = CodespaceDevBoxRuntime.open(
        repo_root=preflight.repo_root,
        state_root=preflight.state_root,
        binding=binding,
        platform_name=sys.platform if platform_name is None else platform_name,
        shell_path=shell_path,
    )
    clock = (lambda: int(time.time())) if now is None else now
    if not callable(clock):
        _configuration("service clock is invalid")
    port_adapter = BoundDevBoxPort(runtime=runtime, lease=lease, now=clock)
    audit_sink: DurableAuthAuditSink | None = None
    try:
        audit_sink = _open_audit_sink(runtime.state_root, policy.policy_id)
        cache = BoundedJwksCache(
            policy=policy,
            fetcher=HttpxJwksFetcher(policy),
            monotonic=time.monotonic,
        )
        authenticator = JwtAuthenticator(policy=policy, jwks_cache=cache)
        server = create_authenticated_devbox_server(
            authenticator=authenticator,
            policy=policy,
            now=clock,
            audit_sink=audit_sink,
            devbox_port=port_adapter,
            allowed_hosts=(
                preflight.forwarded_host,
                "127.0.0.1",
                "127.0.0.1:*",
            ),
        )
    except BaseException:
        if audit_sink is not None:
            try:
                audit_sink.close()
            except Exception:
                pass
        raise
    return CodespaceDevBoxService(
        preflight=preflight,
        lease=lease,
        policy=policy,
        runtime=runtime,
        port=port_adapter,
        server=server,
        audit_sink=audit_sink,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Mastermind DevBox MCP inside GitHub Codespaces")
    parser.add_argument("--repo-root", default=os.getcwd())
    parser.add_argument("--state-root", default=str(Path.home() / ".mastermind-devbox-state"))
    parser.add_argument("--policy-file", required=True)
    parser.add_argument("--lease-file", required=True)
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--host", default="127.0.0.1")
    return parser


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get(_SERVICE_ENV_MARKER) != "1":
        clean_environment = build_sanitized_service_environment(os.environ)
        os.execve(
            sys.executable,
            [sys.executable, "-m", "ops.devbox.run_codespace_devbox", *effective_argv],
            clean_environment,
        )
        raise AssertionError("os.execve unexpectedly returned")
    args = _parser().parse_args(effective_argv)
    if args.host != "127.0.0.1":
        raise SystemExit("DevBox V1 binds loopback; use GitHub Codespaces port forwarding")
    service = build_codespace_service(
        repo_root=args.repo_root,
        state_root=args.state_root,
        policy_file=args.policy_file,
        lease_file=args.lease_file,
        port=args.port,
    )
    app = service.server.streamable_http_app()
    print(f"DEVBOX_LOCAL=http://127.0.0.1:{args.port}", flush=True)
    print(f"DEVBOX_MCP={service.preflight.forwarded_mcp_url}", flush=True)
    try:
        import uvicorn

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
            access_log=False,
            proxy_headers=False,
        )
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CodespaceDevBoxService",
    "DevBoxServiceConfigurationError",
    "build_codespace_service",
    "build_sanitized_service_environment",
    "load_devbox_lease",
    "load_devbox_policy",
    "main",
]
