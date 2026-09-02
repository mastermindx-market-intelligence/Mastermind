"""Direct LSP candidate for the C0 falsifier.

The adapter owns initialization and read-only access. Only the protocol methods
the six facade tools actually need are admitted; workspace mutation, command
execution, server-initiated edits, dynamic plugin selection and external folders
are not in the admitted set at all, so they cannot be reached by accident.

One language failing is explicit. It never masquerades as global success and it
never silently falls back to another backend.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote, unquote, urlparse

from experiments.code_intelligence.backend import (
    BackendIdentity,
    ExecutableSpec,
    guard_payload,
)
from experiments.code_intelligence.jsonrpc_stdio import JsonRpcError, JsonRpcStdioClient
from experiments.code_intelligence.semantic_contract import MAX_LIMIT, canonical_json
from experiments.code_intelligence.workspace_seal import WorkspaceSeal

__all__ = ["DirectLspBackend", "LspBackendError"]

_MAX_DIAGNOSTIC_FILES = 200


class LspBackendError(Exception):
    """Typed refusal from the direct-LSP candidate."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _path_to_uri(path: Path) -> str:
    return "file://" + quote(str(path), safe="/")


def _uri_to_path(uri: str) -> Path:
    return Path(unquote(urlparse(uri).path))


class DirectLspBackend:
    """Six Mastermind tools over a pinned, digest-verified language server."""

    #: The complete set of protocol methods this adapter may ever send.
    ADMITTED_METHODS = frozenset(
        {
            "initialize",
            "initialized",
            "shutdown",
            "textDocument/documentSymbol",
            "workspace/symbol",
            "textDocument/references",
            "textDocument/implementation",
            "textDocument/diagnostic",
        }
    )

    def __init__(self, *, spec: ExecutableSpec, language: str) -> None:
        self._spec = spec
        self._language = language
        self._client: JsonRpcStdioClient | None = None
        self._seal: WorkspaceSeal | None = None
        self._root: Path | None = None
        self._capabilities: dict[str, Any] = {}
        self._server_info: dict[str, Any] = {}
        self._root_uri = ""
        self.methods_used: set[str] = set()

    # ---------------------------------------------------------------- identity

    @property
    def identity(self) -> BackendIdentity:
        config = canonical_json(
            {
                "language": self._language,
                "admitted_methods": sorted(self.ADMITTED_METHODS),
                "argv_suffix": list(self._spec.argv_suffix),
            }
        )
        name = str(self._server_info.get("name", "unknown"))
        version = str(self._server_info.get("version", "unknown"))
        return BackendIdentity(
            kind="direct_lsp",
            source_version=version,
            source_commit=str(self._server_info.get("commit", "unpinned")),
            executable_sha256=self._spec.sha256,
            language_servers=((f"{self._language}:{name}", self._spec.sha256),),
            configuration_digest=hashlib.sha256(config.encode("utf-8")).hexdigest(),
        )

    @property
    def initialized_root_uri(self) -> str:
        return self._root_uri

    # ------------------------------------------------------------------- start

    def start(self, *, seal: WorkspaceSeal, scratch: Path) -> None:
        self._seal = seal
        self._root = Path(seal.resolved_root)
        self._root_uri = _path_to_uri(self._root)
        self._client = JsonRpcStdioClient(spec=self._spec, scratch=Path(scratch))
        self._client.start()

        result = self._request(
            "initialize",
            {
                # The host supplies the root. There is no caller-facing path.
                "processId": None,
                "rootUri": self._root_uri,
                "workspaceFolders": None,
                "capabilities": {
                    "textDocument": {
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": False},
                        "references": {},
                        "implementation": {},
                    },
                    "workspace": {"symbol": {}, "workspaceFolders": False},
                },
            },
            timeout=60,
        )
        self._capabilities = (result or {}).get("capabilities", {}) or {}
        self._server_info = (result or {}).get("serverInfo", {}) or {}
        self._notify("initialized", {})

    # ---------------------------------------------------------------- plumbing

    def _require_client(self) -> JsonRpcStdioClient:
        if self._client is None or self._root is None:
            raise LspBackendError("BACKEND_NOT_STARTED", "start() was not called")
        return self._client

    def _request(
        self, method: str, params: Mapping[str, Any], timeout: float | None = None
    ) -> Any:
        if method not in self.ADMITTED_METHODS:
            raise LspBackendError("METHOD_NOT_ADMITTED", method)
        self.methods_used.add(method)
        return self._require_client().request(method, params, timeout=timeout)

    def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        if method not in self.ADMITTED_METHODS:
            raise LspBackendError("METHOD_NOT_ADMITTED", method)
        self.methods_used.add(method)
        self._require_client().notify(method, params)

    def refused_census(self) -> list[str]:
        """Harness-only introspection: what the stand-in server refused.

        Deliberately not counted in ``methods_used`` and not used in any trial;
        a real language server simply answers "method not found".
        """
        try:
            result = self._require_client().request("__refused_census__", {}, timeout=5)
        except JsonRpcError:
            return []
        return list((result or {}).get("refused", []))

    # --------------------------------------------------------------- locations

    def _resolve_file(self, relative_file: str) -> Path:
        assert self._root is not None
        parts = relative_file.split("/")
        if relative_file.startswith("/") or any(p in ("", ".", "..") for p in parts):
            raise LspBackendError("INVALID_LOCATION", relative_file)
        candidate = self._root / relative_file
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise LspBackendError("FILE_NOT_IN_SEAL", relative_file) from exc
        if not resolved.is_relative_to(self._root) or not resolved.is_file():
            raise LspBackendError("FILE_NOT_IN_SEAL", relative_file)
        return resolved

    def _row(self, location: Mapping[str, Any], symbol: str | None = None) -> dict[str, Any]:
        assert self._root is not None
        path = _uri_to_path(location["uri"])
        if not path.is_relative_to(self._root):
            raise LspBackendError("LSP_FOREIGN_LOCATION", str(path)[:160])
        start = location["range"]["start"]
        row: dict[str, Any] = {
            "relative_file": path.relative_to(self._root).as_posix(),
            "line": int(start["line"]) + 1,
            "character": int(start["character"]),
        }
        if symbol is not None:
            row["symbol"] = symbol
        return row

    @staticmethod
    def _finalize(rows: Iterable[Mapping[str, Any]], limit: int) -> Mapping[str, Any]:
        seen: set[tuple] = set()
        unique: list[dict[str, Any]] = []
        for row in rows:
            key = (
                row["relative_file"],
                row["line"],
                row.get("character", 0),
                row.get("symbol", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(dict(row))
        unique.sort(
            key=lambda item: (
                item["relative_file"],
                item["line"],
                item.get("character", 0),
                item.get("symbol", ""),
            )
        )
        bounded = unique[: min(int(limit), MAX_LIMIT)]
        return guard_payload({"rows": bounded, "truncated": len(unique) > len(bounded)})

    def _workspace_symbols(self, query: str, timeout: float | None) -> list[dict[str, Any]]:
        result = self._request("workspace/symbol", {"query": query}, timeout=timeout) or []
        rows = []
        for item in result:
            rows.append(self._row(item["location"], item.get("name")))
        return rows

    def _definition_anchor(
        self, name: str, timeout: float | None
    ) -> tuple[Path, int, int]:
        for row in sorted(
            (r for r in self._workspace_symbols(name, timeout) if r.get("symbol") == name),
            key=lambda r: (r["relative_file"], r["line"]),
        ):
            assert self._root is not None
            return (
                self._root / row["relative_file"],
                row["line"] - 1,
                row["character"],
            )
        raise LspBackendError("SYMBOL_NOT_FOUND", name)

    # ------------------------------------------------------------- facade API

    def workspace_status(self, *, timeout: float | None = None) -> Mapping[str, object]:
        client = self._require_client()
        return guard_payload(
            {
                "ready": client.is_running,
                "language": self._language,
                "server_name": str(self._server_info.get("name", "unknown")),
                "server_version": str(self._server_info.get("version", "unknown")),
                "admitted_method_count": len(self.ADMITTED_METHODS),
            }
        )

    def symbol_overview(
        self,
        *,
        relative_file: str | None,
        query: str | None,
        limit: int,
        timeout: float | None = None,
    ) -> Mapping[str, object]:
        if relative_file is not None:
            path = self._resolve_file(relative_file)
            result = self._request(
                "textDocument/documentSymbol",
                {"textDocument": {"uri": _path_to_uri(path)}},
                timeout=timeout,
            ) or []
            rows = [self._row(item["location"], item.get("name")) for item in result]
        else:
            rows = self._workspace_symbols(query or "", timeout)
        if query:
            rows = [row for row in rows if query in (row.get("symbol") or "")]
        return self._finalize(rows, limit)

    def find_symbol(
        self,
        *,
        name: str,
        relative_file: str | None,
        limit: int,
        timeout: float | None = None,
    ) -> Mapping[str, object]:
        rows = [r for r in self._workspace_symbols(name, timeout) if r.get("symbol") == name]
        if relative_file is not None:
            self._resolve_file(relative_file)
            rows = [r for r in rows if r["relative_file"] == relative_file]
        return self._finalize(rows, limit)

    def find_references(
        self,
        *,
        name: str,
        relative_file: str | None,
        limit: int,
        timeout: float | None = None,
    ) -> Mapping[str, object]:
        path, line, character = self._definition_anchor(name, timeout)
        result = self._request(
            "textDocument/references",
            {
                "textDocument": {"uri": _path_to_uri(path)},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True},
            },
            timeout=timeout,
        ) or []
        rows = [self._row(item, name) for item in result]
        if relative_file is not None:
            self._resolve_file(relative_file)
            rows = [r for r in rows if r["relative_file"] == relative_file]
        return self._finalize(rows, limit)

    def find_implementations(
        self,
        *,
        name: str,
        relative_file: str | None,
        limit: int,
        timeout: float | None = None,
    ) -> Mapping[str, object]:
        if self._capabilities.get("implementationProvider") is False:
            raise LspBackendError(
                "LSP_CAPABILITY_UNAVAILABLE", "server declares no implementationProvider"
            )
        path, line, character = self._definition_anchor(name, timeout)
        try:
            result = self._request(
                "textDocument/implementation",
                {
                    "textDocument": {"uri": _path_to_uri(path)},
                    "position": {"line": line, "character": character},
                },
                timeout=timeout,
            ) or []
        except JsonRpcError as exc:
            if exc.code == "SERVER_ERROR":
                raise LspBackendError(
                    "LSP_CAPABILITY_UNAVAILABLE", exc.detail[:160]
                ) from exc
            raise
        rows = []
        for item in result:
            row = self._row(item)
            row["symbol"] = self._symbol_name_at(row)
            rows.append(row)
        if relative_file is not None:
            self._resolve_file(relative_file)
            rows = [r for r in rows if r["relative_file"] == relative_file]
        return self._finalize(rows, limit)

    def _symbol_name_at(self, row: Mapping[str, Any]) -> str:
        """Name the definition a location points at, read-only."""
        assert self._root is not None
        path = self._root / row["relative_file"]
        try:
            line = path.read_text(encoding="utf-8").splitlines()[row["line"] - 1]
        except (OSError, IndexError):
            return ""
        stripped = line.strip()
        for keyword in ("class ", "def ", "async def "):
            if stripped.startswith(keyword):
                rest = stripped[len(keyword) :]
                for stop in ("(", ":", " "):
                    if stop in rest:
                        rest = rest.split(stop, 1)[0]
                return rest
        return ""

    def diagnostics(
        self,
        *,
        relative_file: str | None,
        limit: int,
        timeout: float | None = None,
    ) -> Mapping[str, object]:
        assert self._root is not None
        if relative_file is not None:
            targets = [self._resolve_file(relative_file)]
        else:
            targets = sorted(
                path
                for path in self._root.rglob("*.py")
                if path.is_file() and ".git" not in path.parts
            )[:_MAX_DIAGNOSTIC_FILES]

        rows: list[dict[str, Any]] = []
        for path in targets:
            result = self._request(
                "textDocument/diagnostic",
                {"textDocument": {"uri": _path_to_uri(path)}},
                timeout=timeout,
            ) or {}
            for item in result.get("items", []):
                row = self._row({"uri": _path_to_uri(path), "range": item["range"]})
                row["kind"] = str(item.get("code", "diagnostic"))
                rows.append(row)
        return self._finalize(rows, limit)

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self._request("shutdown", {}, timeout=5)
        except (JsonRpcError, LspBackendError):
            pass
        self._client.close()
