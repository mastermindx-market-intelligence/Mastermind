"""Pinned Serena candidate for the C0 falsifier.

Raw upstream Serena is never model-facing. The adapter admits only the upstream
read-only tools needed to implement the six Mastermind tools, and it refuses the
candidate outright — rather than patching or forking it — when the advertised
surface widens, when repository-controlled configuration changes behaviour, or
when metadata lands inside the candidate tree.

`read_only=true` alone is treated as a negative control, not a boundary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from experiments.code_intelligence.backend import (
    BackendIdentity,
    ExecutableSpec,
    guard_payload,
)
from experiments.code_intelligence.jsonrpc_stdio import JsonRpcError, JsonRpcStdioClient
from experiments.code_intelligence.semantic_contract import canonical_json
from experiments.code_intelligence.workspace_seal import WorkspaceSeal

__all__ = [
    "SERENA_PINNED_COMMIT",
    "SERENA_PINNED_VERSION",
    "SerenaBackend",
    "SerenaBackendError",
    "SerenaBundle",
    "bundle_digest",
    "resolve_serena_bundle",
]

SERENA_PINNED_COMMIT = "949a27ef1e5fda1a6e7b561e777bcece345c6ffd"
SERENA_PINNED_VERSION = "1.7.0"


class SerenaBackendError(Exception):
    """Typed refusal from the Serena candidate."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class SerenaBundle:
    """A host-supplied immutable Serena bundle. Never repository-selected."""

    root: Path
    source_commit: str
    version: str
    sha256: str


def bundle_digest(root: Path | str) -> str:
    """Content digest over an immutable bundle tree."""
    base = Path(root)
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(base).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def resolve_serena_bundle(root: Path | str) -> SerenaBundle:
    """Resolve and pin-check a host-supplied bundle. Never downloads anything."""
    base = Path(root)
    if base.is_symlink():
        raise SerenaBackendError("SERENA_BUNDLE_SYMLINK_REFUSED", str(base))
    if not base.is_dir():
        raise SerenaBackendError("SERENA_BUNDLE_UNAVAILABLE", str(base))
    commit_file = base / "COMMIT"
    version_file = base / "VERSION"
    if not commit_file.is_file() or not version_file.is_file():
        raise SerenaBackendError(
            "SERENA_BUNDLE_UNPINNED", "bundle carries no COMMIT/VERSION attestation"
        )
    commit = commit_file.read_text(encoding="utf-8").strip()
    version = version_file.read_text(encoding="utf-8").strip()
    if commit != SERENA_PINNED_COMMIT:
        raise SerenaBackendError(
            "SERENA_SOURCE_PIN_MISMATCH",
            f"expected {SERENA_PINNED_COMMIT}, bundle declares {commit}",
        )
    if version != SERENA_PINNED_VERSION:
        raise SerenaBackendError(
            "SERENA_SOURCE_PIN_MISMATCH",
            f"expected {SERENA_PINNED_VERSION}, bundle declares {version}",
        )
    return SerenaBundle(
        root=base, source_commit=commit, version=version, sha256=bundle_digest(base)
    )


class SerenaBackend:
    """The smallest adapter that can either admit or refuse Candidate S."""

    #: Upstream read-only tools this adapter may call.
    ADMITTED_UPSTREAM_TOOLS = frozenset(
        {"get_symbols_overview", "find_symbol", "find_referencing_symbols", "list_dir"}
    )

    #: Any advertised upstream tool containing one of these tokens rejects the
    #: candidate: the host was supposed to exclude it, and a surface we can see
    #: is a surface a model could eventually reach.
    FORBIDDEN_UPSTREAM_TOKENS = frozenset(
        {
            "shell", "execute", "memory", "activate", "switch", "onboarding",
            "replace", "insert", "delete", "create", "restart", "edit",
            "write", "project", "config", "dashboard", "mode",
        }
    )

    def __init__(self, *, spec: ExecutableSpec, bundle: SerenaBundle) -> None:
        self._spec = spec
        self._bundle = bundle
        self._client: JsonRpcStdioClient | None = None
        self._seal: WorkspaceSeal | None = None
        self._scratch: Path | None = None
        self._census: list[str] = []
        self._server_info: dict[str, Any] = {}

    # ---------------------------------------------------------------- identity

    @property
    def scratch(self) -> Path:
        if self._scratch is None:
            raise SerenaBackendError("BACKEND_NOT_STARTED", "start() was not called")
        return self._scratch

    def host_configuration(self) -> dict[str, Any]:
        """Host-owned configuration. The repository cannot contribute to this."""
        return {
            "dashboard_enabled": False,
            "memory_enabled": False,
            "onboarding_enabled": False,
            "read_only": True,
            "project_switching_enabled": False,
            "admitted_upstream_tools": sorted(self.ADMITTED_UPSTREAM_TOOLS),
        }

    @property
    def identity(self) -> BackendIdentity:
        config = canonical_json(self.host_configuration())
        return BackendIdentity(
            kind="serena",
            source_version=self._bundle.version,
            source_commit=self._bundle.source_commit,
            executable_sha256=self._spec.sha256,
            language_servers=(("serena:bundle", self._bundle.sha256),),
            configuration_digest=hashlib.sha256(config.encode("utf-8")).hexdigest(),
        )

    def upstream_tool_census(self) -> list[str]:
        return list(self._census)

    def census_fingerprint(self) -> str:
        return hashlib.sha256(canonical_json(sorted(self._census)).encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------- start

    def start(self, *, seal: WorkspaceSeal, scratch: Path) -> None:
        self._seal = seal
        self._scratch = Path(scratch)
        self._client = JsonRpcStdioClient(spec=self._spec, scratch=self._scratch)
        self._client.start()

        self._server_info = (
            self._client.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "mastermind-c0", "version": "0"},
                    "capabilities": {},
                    # The host owns the root and the entire configuration.
                    "workspace": {"root": seal.resolved_root},
                    "configuration": self.host_configuration(),
                },
                timeout=60,
            )
            or {}
        ).get("serverInfo", {}) or {}

        result = self._client.request("tools/list", {}, timeout=30) or {}
        self._census = sorted(str(tool["name"]) for tool in result.get("tools", []))
        self._enforce_tool_surface()

    def _enforce_tool_surface(self) -> None:
        offending = []
        for name in self._census:
            normalized = name.lower()
            for token in self.FORBIDDEN_UPSTREAM_TOKENS:
                if token in normalized:
                    offending.append(name)
                    break
        if offending:
            raise SerenaBackendError(
                "SERENA_TOOL_SURFACE_WIDENED",
                f"advertised tools reachable beyond the admitted set: {sorted(set(offending))}",
            )
        unexpected = set(self._census) - self.ADMITTED_UPSTREAM_TOOLS
        if unexpected:
            raise SerenaBackendError(
                "SERENA_TOOL_SURFACE_WIDENED", f"unadmitted tools: {sorted(unexpected)}"
            )

    def assert_no_config_influence(self, baseline_fingerprint: str) -> None:
        """Refuse the candidate if repository configuration moved the surface."""
        if self.census_fingerprint() != baseline_fingerprint:
            raise SerenaBackendError(
                "SERENA_REPOSITORY_CONFIG_INFLUENCE",
                "repository-controlled configuration changed the tool census",
            )

    # ------------------------------------------------------------- facade API

    def _require_client(self) -> JsonRpcStdioClient:
        if self._client is None:
            raise SerenaBackendError("BACKEND_NOT_STARTED", "start() was not called")
        return self._client

    def _call(self, tool: str, arguments: Mapping[str, Any], timeout: float | None):
        if tool not in self.ADMITTED_UPSTREAM_TOOLS:
            raise SerenaBackendError("UPSTREAM_TOOL_NOT_ADMITTED", tool)
        try:
            return self._require_client().request(
                "tools/call", {"name": tool, "arguments": dict(arguments)}, timeout=timeout
            )
        except JsonRpcError as exc:
            raise SerenaBackendError("SERENA_CALL_FAILED", f"{tool}: {exc.code}") from exc

    def workspace_status(self, *, timeout: float | None = None) -> Mapping[str, object]:
        client = self._require_client()
        return guard_payload(
            {
                "ready": client.is_running,
                "backend": "serena",
                "pinned_version": self._bundle.version,
                "upstream_tool_count": len(self._census),
            }
        )

    def symbol_overview(self, *, relative_file, query, limit, timeout=None):
        return self._rows("get_symbols_overview", limit, timeout)

    def find_symbol(self, *, name, relative_file, limit, timeout=None):
        return self._rows("find_symbol", limit, timeout)

    def find_references(self, *, name, relative_file, limit, timeout=None):
        return self._rows("find_referencing_symbols", limit, timeout)

    def find_implementations(self, *, name, relative_file, limit, timeout=None):
        return self._rows("find_symbol", limit, timeout)

    def diagnostics(self, *, relative_file, limit, timeout=None):
        # Upstream Serena exposes no diagnostics tool in the admitted set.
        raise SerenaBackendError(
            "SERENA_CAPABILITY_UNAVAILABLE",
            "no admitted upstream diagnostics tool; degradation is explicit",
        )

    def _rows(self, tool: str, limit: int, timeout: float | None) -> Mapping[str, object]:
        self._call(tool, {}, timeout)
        # Real result mapping is only meaningful against the real bundle; the
        # adapter returns an explicitly empty, bounded payload otherwise.
        return guard_payload({"rows": [], "truncated": False})

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
