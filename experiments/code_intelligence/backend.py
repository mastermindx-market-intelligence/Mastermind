"""Backend protocol, identity and response bounding for the C0 falsifier.

Both candidates answer through this one shape. The response guard is the mirror
image of the request contract: just as no caller may name a root, no backend
may hand one back. Anything that would leak host paths, environment, process
identity or secret material out of the sandbox is refused rather than trimmed,
because a silently trimmed leak is still a leak that happened.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from experiments.code_intelligence.semantic_contract import MAX_LIMIT, canonical_json
from experiments.code_intelligence.workspace_seal import WorkspaceSeal

__all__ = [
    "MAX_COLLECTION_WIDTH",
    "MAX_PAYLOAD_BYTES",
    "MAX_PAYLOAD_DEPTH",
    "BackendIdentity",
    "BackendPayloadError",
    "ExecutableSpec",
    "SemanticBackend",
    "backend_identity_payload",
    "backend_identity_digest",
    "guard_payload",
    "guard_wire_payload",
]

MAX_PAYLOAD_DEPTH = 20
MAX_PAYLOAD_BYTES = 1024 * 1024
MAX_COLLECTION_WIDTH = 1000

# Keys a backend may never place in a response. The contract's steering tokens,
# plus process/host identity names that are not request-shaped.
_FORBIDDEN_KEY_TOKENS = (
    "root",
    "path",
    "project",
    "attempt",
    "worker",
    "session",
    "endpoint",
    "command",
    "executable",
    "cwd",
    "env",
    "memory",
    "edit",
    "shell",
    "argv",
    "pid",
    "hostname",
    "homedir",
)

_SECRET_MARKERS = (
    "-----BEGIN",
    "ghp_",
    "gho_",
    "ghs_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "AKIA",
    "sk-ant-",
    "ASIA",
    "AIza",
)

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class BackendPayloadError(Exception):
    """Typed refusal of a backend response."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class BackendIdentity:
    """Exactly what was run, so a trial can be reproduced or refused."""

    kind: str
    source_version: str
    source_commit: str
    executable_sha256: str
    language_servers: tuple[tuple[str, str], ...]
    configuration_digest: str
    launcher_name: str = ""
    canonical_argv: tuple[str, ...] = ()
    argv_file_digests: tuple[tuple[int, str, str], ...] = ()
    targets: tuple[tuple[str, str, str, str, str, str], ...] = ()
    dependency_manifests: tuple[tuple[str, str], ...] = ()
    provenance: str = "real"


@dataclass(frozen=True, slots=True)
class ExecutableSpec:
    """A host-injected, digest-pinned executable. Never model-facing.

    ``argv_digests`` binds the *artifacts named in argv* — the server script,
    bundle entry point or package — because pinning only the interpreter pins
    almost nothing: the same python can run any code.
    """

    path: Path
    sha256: str
    argv_suffix: tuple[str, ...]
    argv_digests: tuple[tuple[str, str], ...] = ()
    targets: tuple[tuple[str, str, str, str, str, str], ...] = ()
    target_sources: tuple[tuple[str, Path], ...] = ()
    dependency_manifests: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.sha256, str) or not _HEX64.match(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character hex digest")
        if not isinstance(self.argv_suffix, tuple):
            raise TypeError("argv_suffix must be a tuple")
        for item in self.argv_suffix:
            if not isinstance(item, str):
                raise TypeError("argv_suffix must contain only strings")
        if not isinstance(self.argv_digests, tuple):
            raise TypeError("argv_digests must be a tuple")
        for entry in self.argv_digests:
            if not (isinstance(entry, tuple) and len(entry) == 2):
                raise TypeError("argv_digests entries must be (path, sha256) pairs")
            if not _HEX64.match(entry[1]):
                raise ValueError("argv_digests entries need a 64-char hex digest")
        if not isinstance(self.targets, tuple):
            raise TypeError("targets must be a tuple")
        for entry in self.targets:
            if not (isinstance(entry, tuple) and len(entry) == 6):
                raise TypeError(
                    "targets entries must be (name, sha256, ecosystem, package, version, binding)"
                )
            if not isinstance(entry[0], str) or not entry[0]:
                raise ValueError("targets entries need a non-empty name")
            if not isinstance(entry[1], str) or not _HEX64.match(entry[1]):
                raise ValueError("targets entries need a 64-char hex digest")
            if any(not isinstance(item, str) or not item for item in entry[2:]):
                raise ValueError(
                    "targets entries need ecosystem, package, version and binding"
                )
        if not isinstance(self.target_sources, tuple):
            raise TypeError("target_sources must be a tuple")
        target_names = {entry[0] for entry in self.targets}
        for entry in self.target_sources:
            if not (isinstance(entry, tuple) and len(entry) == 2):
                raise TypeError("target_sources entries must be (name, Path) pairs")
            if entry[0] not in target_names or not isinstance(entry[1], Path):
                raise ValueError("target_sources must name a declared target Path")
        if not isinstance(self.dependency_manifests, tuple):
            raise TypeError("dependency_manifests must be a tuple")
        for ecosystem, digest in self.dependency_manifests:
            if ecosystem not in {"python", "npm"} or not _HEX64.match(digest):
                raise ValueError("dependency manifest requires python/npm and sha256")

    @property
    def launcher_name(self) -> str:
        return self.path.name

    @property
    def argv_file_digests(self) -> tuple[tuple[int, str, str], ...]:
        """Path-free identity for every digest-pinned argv file."""
        pinned = {str(Path(path)): digest for path, digest in self.argv_digests}
        return tuple(
            (index, Path(item).name, pinned[str(Path(item))])
            for index, item in enumerate(self.argv_suffix, start=1)
            if str(Path(item)) in pinned
        )

    @property
    def canonical_argv(self) -> tuple[str, ...]:
        """Exact invocation with host paths replaced by digest-bound tokens."""
        files = {index: (name, digest) for index, name, digest in self.argv_file_digests}
        suffix = []
        for index, item in enumerate(self.argv_suffix, start=1):
            if index in files:
                name, digest = files[index]
                suffix.append(f"<argv-file:{index}:{name}:{digest}>")
            elif Path(item).is_absolute():
                suffix.append(f"<unbound-absolute-argv:{index}:{Path(item).name}>")
            else:
                suffix.append(item)
        return (
            f"<launcher:{self.launcher_name}:{self.sha256}>",
            *suffix,
        )

    @property
    def target_digests(self) -> tuple[tuple[str, str, str, str, str, str], ...]:
        return self.targets

    @property
    def provenance(self) -> str:
        """Classify repository-owned test servers without trusting callers."""
        marker = ("tests", "code_intelligence", "servers")
        candidates = [
            self.path,
            *(
                Path(item)
                for item in self.argv_suffix
                if Path(item).is_absolute() or Path(item).exists()
            ),
            *(Path(path) for path, _digest in self.argv_digests),
        ]
        candidates.extend(path for _name, path in self.target_sources)
        for path in candidates:
            parts = path.resolve(strict=False).parts
            if any(tuple(parts[index:index + 3]) == marker for index in range(len(parts) - 2)):
                return "stand_in"
        return "real"


@runtime_checkable
class SemanticBackend(Protocol):
    """The single shape both C0 candidates must satisfy."""

    @property
    def identity(self) -> BackendIdentity: ...

    def start(self, *, seal: WorkspaceSeal, scratch: Path) -> None: ...

    def workspace_status(self) -> Mapping[str, object]: ...

    def symbol_overview(
        self, *, relative_file: str | None, query: str | None, limit: int
    ) -> Mapping[str, object]: ...

    def find_symbol(
        self, *, name: str, relative_file: str | None, limit: int
    ) -> Mapping[str, object]: ...

    def find_references(
        self, *, name: str, relative_file: str | None, limit: int
    ) -> Mapping[str, object]: ...

    def find_implementations(
        self, *, name: str, relative_file: str | None, limit: int
    ) -> Mapping[str, object]: ...

    def diagnostics(
        self, *, relative_file: str | None, limit: int
    ) -> Mapping[str, object]: ...

    def close(self) -> None: ...


def backend_identity_payload(identity: BackendIdentity) -> dict[str, Any]:
    """Path-free canonical serialization shared by receipts and digests."""
    return {
        "kind": identity.kind,
        "source_version": identity.source_version,
        "source_commit": identity.source_commit,
        "executable_sha256": identity.executable_sha256,
        "language_servers": [list(item) for item in identity.language_servers],
        "configuration_digest": identity.configuration_digest,
        "launcher_name": identity.launcher_name,
        "canonical_argv": list(identity.canonical_argv),
        "argv_file_digests": [list(item) for item in identity.argv_file_digests],
        "targets": [list(item) for item in identity.targets],
        "dependency_manifests": [list(item) for item in identity.dependency_manifests],
        "provenance": identity.provenance,
    }


def backend_identity_digest(identity: BackendIdentity) -> str:
    """SHA-256 over every identity field, so any substitution is visible."""
    return hashlib.sha256(
        canonical_json(backend_identity_payload(identity)).encode("utf-8")
    ).hexdigest()


def _check_key(key: str) -> None:
    normalized = key.lower()
    for token in _FORBIDDEN_KEY_TOKENS:
        if token in normalized:
            raise BackendPayloadError(
                "PAYLOAD_HOST_LEAK", f"response key {key!r} exposes {token!r}"
            )


def _check_string(key: str | None, value: str) -> None:
    if "\x00" in value:
        raise BackendPayloadError("PAYLOAD_MALFORMED", "NUL byte in response")
    if value.startswith("/") or _WINDOWS_DRIVE.match(value):
        raise BackendPayloadError("PAYLOAD_ABSOLUTE_PATH", value[:120])
    for marker in _SECRET_MARKERS:
        if marker in value:
            raise BackendPayloadError("PAYLOAD_SECRET_SUSPECTED", f"marker {marker!r}")
    if key == "relative_file":
        if value.startswith("~"):
            raise BackendPayloadError("PAYLOAD_ABSOLUTE_PATH", value[:120])
        parts = value.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise BackendPayloadError("PAYLOAD_PATH_TRAVERSAL", value[:120])


def _walk(node: Any, depth: int, key: str | None) -> None:
    if depth > MAX_PAYLOAD_DEPTH:
        raise BackendPayloadError("PAYLOAD_TOO_DEEP", f"depth exceeds {MAX_PAYLOAD_DEPTH}")
    if isinstance(node, Mapping):
        for child_key, child in node.items():
            if not isinstance(child_key, str):
                raise BackendPayloadError("PAYLOAD_MALFORMED", "non-string key")
            _check_key(child_key)
            _walk(child, depth + 1, child_key)
    elif isinstance(node, (list, tuple)):
        if len(node) > MAX_COLLECTION_WIDTH:
            raise BackendPayloadError(
                "PAYLOAD_TOO_WIDE",
                f"collection of {len(node)} exceeds {MAX_COLLECTION_WIDTH}",
            )
        for child in node:
            _walk(child, depth + 1, key)
    elif isinstance(node, str):
        _check_string(key, node)
    elif isinstance(node, bool) or node is None:
        return
    elif isinstance(node, int):
        return
    elif isinstance(node, float):
        raise BackendPayloadError("PAYLOAD_MALFORMED", "floats are not deterministic")
    else:
        raise BackendPayloadError(
            "PAYLOAD_MALFORMED", f"unsupported value type {type(node).__name__}"
        )


def _bound_size_and_width(value: Any) -> None:
    """Bound total canonical bytes and nested collection width."""
    try:
        rendered = canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise BackendPayloadError("PAYLOAD_MALFORMED", str(exc)[:160]) from exc
    if len(rendered.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise BackendPayloadError(
            "PAYLOAD_TOO_LARGE", f"canonical payload exceeds {MAX_PAYLOAD_BYTES} bytes"
        )

    def width(node: Any, depth: int) -> None:
        if depth > MAX_PAYLOAD_DEPTH:
            raise BackendPayloadError("PAYLOAD_TOO_DEEP", "wire payload too deep")
        if isinstance(node, Mapping):
            for child in node.values():
                width(child, depth + 1)
        elif isinstance(node, (list, tuple)):
            if len(node) > MAX_COLLECTION_WIDTH:
                raise BackendPayloadError(
                    "PAYLOAD_TOO_WIDE",
                    f"collection of {len(node)} exceeds {MAX_COLLECTION_WIDTH}",
                )
            for child in node:
                width(child, depth + 1)

    width(value, 0)


def guard_wire_payload(value: Any) -> Any:
    """Bound a RAW backend wire response before any mapping or file access."""
    _bound_size_and_width(value)
    return value


def guard_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse — never trim — any response that breaches the sandbox."""
    if not isinstance(payload, Mapping):
        raise BackendPayloadError("PAYLOAD_MALFORMED", "payload must be a mapping")

    rows = payload.get("rows")
    if rows is not None:
        if not isinstance(rows, (list, tuple)):
            raise BackendPayloadError("PAYLOAD_MALFORMED", "rows must be a list")
        if len(rows) > MAX_LIMIT:
            raise BackendPayloadError(
                "PAYLOAD_TOO_MANY_ROWS", f"{len(rows)} rows exceeds {MAX_LIMIT}"
            )

    _bound_size_and_width(payload)
    _walk(payload, 0, None)
    return payload
