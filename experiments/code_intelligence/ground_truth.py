"""LSP-independent ground truth for the C0 corpora.

Ground truth must never come from a language server, or the experiment would
be grading each candidate against itself. Everything here is derived with the
standard-library ``ast`` module plus committed fixture declarations.

The undefined-name census is deliberately *conservative*: it reports a load
only when the name is not bound anywhere in the module by any construct. It
therefore cannot produce a false positive, and it is not a general linter — it
exists to pin the single planted diagnostic in each corpus.
"""

from __future__ import annotations

import ast
import builtins
import json
from pathlib import Path
from typing import Any, Iterator

__all__ = [
    "census_definitions",
    "census_diagnostics",
    "census_references",
    "corpus_manifest_digest",
    "load_answer_key",
    "python_source_files",
]

_BUILTINS = frozenset(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__"}


def load_answer_key(corpus: Path | str) -> dict[str, Any]:
    """Read the committed declaration for a corpus."""
    path = Path(corpus) / "answer_key.json"
    return json.loads(path.read_text(encoding="utf-8"))


def python_source_files(corpus: Path | str) -> list[tuple[str, Path]]:
    """Sorted (repository-relative-to-corpus, path) pairs for the corpus."""
    corpus_root = Path(corpus)
    key = load_answer_key(corpus_root)
    found: list[tuple[str, Path]] = []
    for source_root in key["source_roots"]:
        base = corpus_root / source_root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if path.is_file():
                found.append((path.relative_to(corpus_root).as_posix(), path))
    found.sort()
    return found


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def census_definitions(corpus: Path | str) -> list[dict[str, Any]]:
    """Module-level class and function definitions across the corpus."""
    rows: list[dict[str, Any]] = []
    for relative, path in python_source_files(corpus):
        tree = _parse(path)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                kind = "class"
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "function"
            else:
                continue
            rows.append(
                {
                    "symbol": node.name,
                    "relative_file": relative,
                    "line": node.lineno,
                    "kind": kind,
                }
            )
    rows.sort(key=lambda row: (row["relative_file"], row["line"], row["symbol"]))
    return rows


def census_references(corpus: Path | str, symbol: str) -> list[dict[str, Any]]:
    """Every syntactic occurrence of a symbol name, definition included."""
    rows: list[dict[str, Any]] = []
    for relative, path in python_source_files(corpus):
        for node in ast.walk(_parse(path)):
            line: int | None = None
            if isinstance(node, ast.Name) and node.id == symbol:
                line = node.lineno
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == symbol:
                    line = node.lineno
            elif isinstance(node, ast.Attribute) and node.attr == symbol:
                line = node.lineno
            elif isinstance(node, ast.alias):
                if symbol in (node.name, node.asname):
                    line = node.lineno
            if line is not None:
                rows.append({"relative_file": relative, "line": line})
    unique = sorted({(row["relative_file"], row["line"]) for row in rows})
    return [{"relative_file": item[0], "line": item[1]} for item in unique]


def _bound_names(tree: ast.Module) -> set[str]:
    """Every name bound anywhere in the module, by any construct."""
    bound: set[str] = set()

    def bind_target(target: ast.AST) -> None:
        for node in ast.walk(target):
            if isinstance(node, ast.Name):
                bound.add(node.id)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
            args = node.args
            for arg in (
                *args.posonlyargs,
                *args.args,
                *args.kwonlyargs,
                *( [args.vararg] if args.vararg else [] ),
                *( [args.kwarg] if args.kwarg else [] ),
            ):
                bound.add(arg.arg)
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                bind_target(target)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            bind_target(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            bind_target(node.target)
        elif isinstance(node, ast.withitem):
            if node.optional_vars is not None:
                bind_target(node.optional_vars)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.NamedExpr):
            bind_target(node.target)
        elif isinstance(node, ast.MatchAs) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            bound.add(node.name)
    return bound


def census_diagnostics(corpus: Path | str) -> list[dict[str, Any]]:
    """Conservative undefined-name census: the planted diagnostics."""
    rows: list[dict[str, Any]] = []
    for relative, path in python_source_files(corpus):
        tree = _parse(path)
        bound = _bound_names(tree) | _BUILTINS
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in bound:
                    rows.append(
                        {
                            "relative_file": relative,
                            "line": node.lineno,
                            "kind": "undefined-name",
                            "symbol": node.id,
                        }
                    )
    rows.sort(key=lambda row: (row["relative_file"], row["line"], row["symbol"]))
    return rows


def _iter_corpus_bytes(corpus: Path | str) -> Iterator[tuple[str, bytes]]:
    corpus_root = Path(corpus)
    for path in sorted(corpus_root.rglob("*")):
        if path.is_file():
            yield path.relative_to(corpus_root).as_posix(), path.read_bytes()


def corpus_manifest_digest(corpus: Path | str) -> str:
    """Content digest of a corpus, so trials name the exact bytes they ran on."""
    import hashlib

    digest = hashlib.sha256()
    for relative, payload in _iter_corpus_bytes(corpus):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
