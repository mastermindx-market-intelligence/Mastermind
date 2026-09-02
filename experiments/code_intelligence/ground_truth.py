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
import re
from pathlib import Path
from typing import Any, Iterator

__all__ = [
    "source_files",
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


def source_files(corpus: Path | str) -> list[tuple[str, Path]]:
    """Sorted (repository-relative-to-corpus, path) pairs for the corpus."""
    corpus_root = Path(corpus)
    key = load_answer_key(corpus_root)
    extensions = key.get("file_extensions", [".py"])
    found: list[tuple[str, Path]] = []
    for source_root in key["source_roots"]:
        base = corpus_root / source_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in extensions:
                found.append((path.relative_to(corpus_root).as_posix(), path))
    found.sort()
    return found


def python_source_files(corpus: Path | str) -> list[tuple[str, Path]]:
    """Backwards-compatible alias for the Python corpora."""
    return source_files(corpus)


# --------------------------------------------------------------- TypeScript
#
# There is no TypeScript AST in the standard library and the experiment may not
# use a language server to build ground truth, so the TS census is a deliberately
# CONSERVATIVE declaration scanner over the frozen corpus. It recognises exactly
# the exported declaration forms the corpus uses and reports identifier
# occurrences by word boundary. It is not a TypeScript parser and is not used for
# anything except grading this fixed corpus, whose answer key is hand-declared
# and cross-checked against it.

_TS_DECLARATION = re.compile(
    r"^export\s+(?:default\s+)?(interface|class|function|type|const|enum)\s+"
    r"([A-Za-z_$][A-Za-z0-9_$]*)"
)
_TS_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

#: Names that are part of the language or ambient environment, never "undefined".
_TS_AMBIENT = frozenset(
    {
        "export", "default", "interface", "class", "function", "type", "const",
        "let", "var", "return", "new", "import", "from", "implements", "extends",
        "string", "number", "boolean", "void", "unknown", "any", "null",
        "undefined", "true", "false", "this", "JSX", "Element", "Promise",
        "Array", "Record", "Partial", "readonly", "as", "of", "in", "if", "else",
        "span", "className",
    }
)


def _ts_declared_names(text: str) -> set[str]:
    """Every name bound in a module: declarations, imports, parameters."""
    declared: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        match = _TS_DECLARATION.match(stripped)
        if match:
            declared.add(match.group(2))
            continue
        local = re.match(
            r"^(?:const|let|var|function|class|interface|type|enum)\s+"
            r"([A-Za-z_$][A-Za-z0-9_$]*)",
            stripped,
        )
        if local:
            declared.add(local.group(1))
        imported = re.match(r"^import\s+\{([^}]*)\}", stripped)
        if imported:
            for part in imported.group(1).split(","):
                name = part.strip().split(" as ")[-1].strip()
                if name:
                    declared.add(name)
        for params in re.findall(r"\(([^)]*)\)", stripped):
            for part in params.split(","):
                name = part.strip().split(":")[0].strip()
                if name and _TS_IDENTIFIER.fullmatch(name):
                    declared.add(name)
        # Method declarations inside a class body: `produce(): string {`
        method = re.match(r"^([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", stripped)
        if method:
            declared.add(method.group(1))
    return declared


def _ts_definitions(relative: str, text: str) -> list[dict[str, Any]]:
    rows = []
    for index, line in enumerate(text.splitlines(), start=1):
        match = _TS_DECLARATION.match(line.strip())
        if match:
            keyword, name = match.groups()
            kind = {"interface": "interface", "class": "class"}.get(keyword, "function")
            rows.append(
                {"symbol": name, "relative_file": relative, "line": index, "kind": kind}
            )
    return rows


def _ts_references(relative: str, text: str, symbol: str) -> list[dict[str, Any]]:
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    return [
        {"relative_file": relative, "line": index}
        for index, line in enumerate(text.splitlines(), start=1)
        if pattern.search(line)
    ]


def _ts_diagnostics(relative: str, text: str) -> list[dict[str, Any]]:
    """Detect exactly the planted `return <bareIdentifier>;` form.

    Deliberately narrow. A broader scanner over TypeScript without a real parser
    produces false positives on string literals, member calls and JSX (measured:
    it flagged "live", "produce", "span" and "className"). Narrowing to a return
    whose entire expression is one undeclared identifier cannot false-positive,
    which is what a ground truth must guarantee. It is not a linter.
    """
    declared = _ts_declared_names(text) | _TS_AMBIENT
    rows = []
    bare_return = re.compile(r"^return\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*;$")
    for index, line in enumerate(text.splitlines(), start=1):
        match = bare_return.match(line.strip())
        if match and match.group(1) not in declared:
            rows.append(
                {
                    "relative_file": relative,
                    "line": index,
                    "kind": "undefined-name",
                    "symbol": match.group(1),
                }
            )
    return rows


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _language(corpus: Path | str) -> str:
    return load_answer_key(corpus).get("language", "python")


def census_definitions(corpus: Path | str) -> list[dict[str, Any]]:
    """Module-level class and function definitions across the corpus."""
    if _language(corpus) == "typescript":
        rows = []
        for relative, path in source_files(corpus):
            rows.extend(_ts_definitions(relative, path.read_text(encoding="utf-8")))
        rows.sort(key=lambda row: (row["relative_file"], row["line"], row["symbol"]))
        return rows
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
    if _language(corpus) == "typescript":
        rows = []
        for relative, path in source_files(corpus):
            rows.extend(_ts_references(relative, path.read_text(encoding="utf-8"), symbol))
        unique = sorted({(r["relative_file"], r["line"]) for r in rows})
        return [{"relative_file": a, "line": b} for a, b in unique]
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
    if _language(corpus) == "typescript":
        rows = []
        for relative, path in source_files(corpus):
            rows.extend(_ts_diagnostics(relative, path.read_text(encoding="utf-8")))
        rows.sort(key=lambda row: (row["relative_file"], row["line"], row["symbol"]))
        return rows
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
