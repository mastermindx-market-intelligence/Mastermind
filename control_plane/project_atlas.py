"""Pure deterministic parsers for the Mastermind Project Atlas.

This module indexes immutable source blobs. It performs no filesystem, Git, network,
cache, lifecycle, authority, or source-write operations. The cache/acquisition adapter
lives in scripts/project_atlas.py.

Atlas records are derived navigation artifacts. They never establish repository
ownership, organizational identity, runtime authority, or permission.
"""

from __future__ import annotations

import ast
import hashlib
import re
import warnings
from collections.abc import Mapping
from typing import Any

from control_plane.session_truth_contract import canonical_json

BLOB_SCHEMA = "mastermind.project_atlas_blob.v1"
PARSER_VERSION = "atlas-parser-1"
MAX_BLOB_BYTES = 1024 * 1024
MAX_SYMBOLS = 8192
MAX_IMPORTS = 8192
MAX_HEADINGS = 8192
MAX_REFERENCES = 8192

_GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_WS_RE = re.compile(r"\bWS:[A-Z0-9][A-Z0-9-]*\b")
_MAS_RE = re.compile(r"\bMAS-[0-9]+\b")
_REPO_RE = re.compile(r"\bmastermindx-market-intelligence/[A-Za-z0-9_.-]+\b")
_PR_RE = re.compile(r"\bPR[ \t]*#([0-9]+)\b", re.IGNORECASE)

_SUPPORTED = {
    ".py": "python",
    ".md": "markdown",
    ".markdown": "markdown",
}

_SENSITIVE_BASENAMES = {
    ".env",
    "credentials",
    "credentials.json",
    "secrets",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
    "auth.json",
}
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_SENSITIVE_PARTS = {".ssh", ".aws", ".gnupg"}


class ProjectAtlasError(ValueError):
    """Raised when an immutable blob cannot be indexed safely."""


def _blob_sha(value: object) -> str:
    if not isinstance(value, str) or _GIT_OBJECT_RE.fullmatch(value) is None:
        raise ProjectAtlasError("blob sha is invalid")
    return value


def detect_language(path: object) -> str | None:
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ProjectAtlasError("path is invalid")
    lower = path.lower()
    for suffix, language in _SUPPORTED.items():
        if lower.endswith(suffix):
            return language
    return None


def is_sensitive_path(path: object) -> bool:
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ProjectAtlasError("path is invalid")
    normalized = path.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    lower_parts = [part.lower() for part in parts]
    if any(part in _SENSITIVE_PARTS for part in lower_parts):
        return True
    if not lower_parts:
        return False
    base = lower_parts[-1]
    if base in _SENSITIVE_BASENAMES or base.startswith(".env."):
        return True
    return base.endswith(_SENSITIVE_SUFFIXES)


def _text(content: object) -> str:
    if isinstance(content, bytes):
        if len(content) > MAX_BLOB_BYTES:
            raise ProjectAtlasError("blob exceeds byte bound")
        try:
            return content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ProjectAtlasError("blob is not UTF-8 text") from exc
    if isinstance(content, str):
        if len(content.encode("utf-8")) > MAX_BLOB_BYTES:
            raise ProjectAtlasError("blob exceeds byte bound")
        return content
    raise ProjectAtlasError("blob content must be bytes or string")


def _decorator_name(node: ast.expr) -> str:
    target = node
    first_literal: str | None = None
    if isinstance(node, ast.Call):
        target = node.func
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            first_literal = node.args[0].value[:256]

    def name(value: ast.AST) -> str:
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            prefix = name(value.value)
            return f"{prefix}.{value.attr}" if prefix else value.attr
        return ""

    rendered = name(target)
    if first_literal is not None and rendered:
        return f"{rendered}:{first_literal}"
    return rendered


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.imports: set[str] = set()

    def _symbol(self, node: ast.AST, *, kind: str, name: str) -> None:
        qualname = ".".join((*self.stack, name))
        decorators = []
        for decorator in getattr(node, "decorator_list", ()):
            rendered = _decorator_name(decorator)
            if rendered:
                decorators.append(rendered)
        self.symbols.append(
            {
                "kind": kind,
                "name": name,
                "qualname": qualname,
                "line": int(getattr(node, "lineno", 0) or 0),
                "end_line": int(
                    getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0
                ),
                "decorators": sorted(set(decorators)),
            }
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._symbol(node, kind="class", name=node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._symbol(node, kind="function", name=node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._symbol(node, kind="async_function", name=node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name:
                self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        prefix = "." * int(node.level or 0)
        module = node.module or ""
        root = prefix + module
        for alias in node.names:
            if alias.name == "*":
                value = f"{root}:*"
            else:
                value = f"{root}:{alias.name}" if root else alias.name
            if value:
                self.imports.add(value)
        self.generic_visit(node)


def _python_record(text: str) -> dict[str, Any]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text)
    except SyntaxError as exc:
        line = int(exc.lineno or 0)
        raise ProjectAtlasError(f"python syntax error at line {line}") from exc
    visitor = _PythonVisitor()
    visitor.visit(tree)
    if len(visitor.symbols) > MAX_SYMBOLS:
        raise ProjectAtlasError("python symbol count exceeds bound")
    if len(visitor.imports) > MAX_IMPORTS:
        raise ProjectAtlasError("python import count exceeds bound")
    return {
        "symbols": sorted(
            visitor.symbols,
            key=lambda item: (
                item["line"],
                item["qualname"],
                item["kind"],
            ),
        ),
        "imports": sorted(visitor.imports),
        "headings": [],
        "references": [],
    }


def _section_end(headings: list[dict[str, Any]], index: int, total_lines: int) -> int:
    current = headings[index]
    for later in headings[index + 1 :]:
        if later["level"] <= current["level"]:
            return max(current["line"], later["line"] - 1)
    return total_lines


def _references(text: str) -> list[str]:
    refs = set(_WS_RE.findall(text))
    refs.update(_MAS_RE.findall(text))
    refs.update(_REPO_RE.findall(text))
    refs.update(f"PR #{number}" for number in _PR_RE.findall(text))
    if len(refs) > MAX_REFERENCES:
        raise ProjectAtlasError("reference count exceeds bound")
    return sorted(refs)


def _markdown_record(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    headings: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        headings.append(
            {
                "level": len(match.group(1)),
                "text": match.group(2).strip(),
                "line": index,
                "end_line": index,
            }
        )
    if len(headings) > MAX_HEADINGS:
        raise ProjectAtlasError("heading count exceeds bound")
    for index, heading in enumerate(headings):
        heading["end_line"] = _section_end(headings, index, len(lines))
    return {
        "symbols": [],
        "imports": [],
        "headings": headings,
        "references": _references(text),
    }


def index_blob(
    *,
    blob_sha: str,
    language: str,
    content: bytes | str,
) -> dict[str, Any]:
    """Return one deterministic content record for an immutable Git blob."""

    blob_sha = _blob_sha(blob_sha)
    text = _text(content)
    if language == "python":
        parsed = _python_record(text)
    elif language == "markdown":
        parsed = _markdown_record(text)
    else:
        raise ProjectAtlasError("language is unsupported")
    record = {
        "schema": BLOB_SCHEMA,
        "parser_version": PARSER_VERSION,
        "blob_sha": blob_sha,
        "language": language,
        "byte_length": len(text.encode("utf-8")),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        **parsed,
    }
    return record


def record_digest(record: Mapping[str, Any]) -> str:
    if not isinstance(record, Mapping) or record.get("schema") != BLOB_SCHEMA:
        raise ProjectAtlasError("atlas record schema is invalid")
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def validate_cached_record(
    value: object,
    *,
    blob_sha: str,
    language: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProjectAtlasError("cached atlas record is invalid")
    record = value.get("record")
    digest = value.get("record_digest")
    if not isinstance(record, Mapping) or not isinstance(digest, str):
        raise ProjectAtlasError("cached atlas record is invalid")
    if record.get("schema") != BLOB_SCHEMA:
        raise ProjectAtlasError("cached atlas schema is invalid")
    if record.get("parser_version") != PARSER_VERSION:
        raise ProjectAtlasError("cached atlas parser version is stale")
    if record.get("blob_sha") != _blob_sha(blob_sha):
        raise ProjectAtlasError("cached atlas blob identity is stale")
    if record.get("language") != language:
        raise ProjectAtlasError("cached atlas language is stale")
    normalized = dict(record)
    if record_digest(normalized) != digest:
        raise ProjectAtlasError("cached atlas digest is invalid")
    return normalized
