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
import hashlib
import json
import re
import subprocess
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
    "GroundTruthError",
    "TERMINAL_MIGRATE_LEGACY_PIN",
    "git_blob_sha",
    "materialize_terminal_case",
]

_BUILTINS = frozenset(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__"}

TERMINAL_MIGRATE_LEGACY_PIN = {
    "repository": "mastermindx-market-intelligence/mastermind-terminal",
    "commit": "fadd8b82f03ecaabe8a86d693da89f27be096d9f",
    "tree": "2ef6840d07c24456fc39e67029c45131fed53b1f",
    "path": "terminal/lib/workspaceMigrate.ts",
    "blob": "3b6feb5295d77cefa4f609b4cbafe5e6a68b5565",
}


class GroundTruthError(Exception):
    """Typed refusal to derive ground truth from an unverified source."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def git_blob_sha(payload: bytes) -> str:
    """Return Git's object identity for exact file bytes."""
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _git_read(repository: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            shell=False,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GroundTruthError("TERMINAL_GIT_READ_FAILED", "immutable source unavailable") from exc


def _repository_slug(remote: str) -> str:
    value = remote.strip()
    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    elif value.startswith("ssh://git@github.com/"):
        value = value.removeprefix("ssh://git@github.com/")
    elif value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    elif value.startswith("http://github.com/"):
        value = value.removeprefix("http://github.com/")
    else:
        return ""
    return value.removesuffix(".git").strip("/")


def _typescript_code_only(text: str) -> str:
    """Mask comments and quoted text while preserving newlines and columns."""
    output: list[str] = []
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
                output.append(char)
            else:
                output.append(" ")
        elif block_comment:
            if char == "*" and nxt == "/":
                output.extend((" ", " "))
                index += 1
                block_comment = False
            else:
                output.append("\n" if char == "\n" else " ")
        elif quote is not None:
            if escaped:
                escaped = False
                output.append("\n" if char == "\n" else " ")
            elif char == "\\":
                escaped = True
                output.append(" ")
            elif char == quote:
                quote = None
                output.append(" ")
            else:
                output.append("\n" if char == "\n" else " ")
        elif char == "/" and nxt == "/":
            output.extend((" ", " "))
            index += 1
            line_comment = True
        elif char == "/" and nxt == "*":
            output.extend((" ", " "))
            index += 1
            block_comment = True
        elif char in ("'", '"', "`"):
            quote = char
            output.append(" ")
        else:
            output.append(char)
        index += 1
    return "".join(output)


def materialize_terminal_case(
    repository: Path | str,
    *,
    expected_commit: str = TERMINAL_MIGRATE_LEGACY_PIN["commit"],
    expected_tree: str = TERMINAL_MIGRATE_LEGACY_PIN["tree"],
    expected_path: str = TERMINAL_MIGRATE_LEGACY_PIN["path"],
    expected_blob: str = TERMINAL_MIGRATE_LEGACY_PIN["blob"],
) -> dict[str, Any]:
    """Derive the migrateLegacy reference oracle from an exact external Git blob.

    The source is read from the named commit, not the checkout and not a copied
    fixture. A caller gets no case at all unless commit, tree, path and blob all
    match their immutable pins.
    """
    root = Path(repository)
    if root.is_symlink() or not root.is_dir():
        raise GroundTruthError("TERMINAL_REPOSITORY_UNAVAILABLE", "repository unavailable")
    if Path(expected_path).is_absolute() or ".." in Path(expected_path).parts:
        raise GroundTruthError("TERMINAL_PATH_INVALID", expected_path)

    try:
        repository_slug = _repository_slug(
            _git_read(root, "remote", "get-url", "origin").decode()
        )
    except GroundTruthError as exc:
        raise GroundTruthError(
            "TERMINAL_REPOSITORY_MISMATCH", "origin is unavailable"
        ) from exc
    if repository_slug != TERMINAL_MIGRATE_LEGACY_PIN["repository"]:
        raise GroundTruthError(
            "TERMINAL_REPOSITORY_MISMATCH",
            f"expected {TERMINAL_MIGRATE_LEGACY_PIN['repository']}, found {repository_slug}",
        )

    try:
        commit = _git_read(root, "rev-parse", f"{expected_commit}^{{commit}}").decode().strip()
    except GroundTruthError as exc:
        raise GroundTruthError(
            "TERMINAL_COMMIT_MISMATCH", f"commit {expected_commit} is unavailable"
        ) from exc
    if commit != expected_commit:
        raise GroundTruthError("TERMINAL_COMMIT_MISMATCH", f"expected {expected_commit}, found {commit}")
    tree = _git_read(root, "rev-parse", f"{commit}^{{tree}}").decode().strip()
    if tree != expected_tree:
        raise GroundTruthError("TERMINAL_TREE_MISMATCH", f"expected {expected_tree}, found {tree}")
    entry = _git_read(root, "ls-tree", commit, "--", expected_path).decode().strip()
    fields = entry.split(None, 3)
    if len(fields) != 4 or fields[1] != "blob" or fields[3] != expected_path:
        raise GroundTruthError("TERMINAL_PATH_MISSING", expected_path)
    if fields[2] != expected_blob:
        raise GroundTruthError("TERMINAL_BLOB_MISMATCH", f"expected {expected_blob}, found {fields[2]}")
    payload = _git_read(root, "show", f"{commit}:{expected_path}")
    if git_blob_sha(payload) != expected_blob:
        raise GroundTruthError("TERMINAL_BLOB_MISMATCH", "blob bytes do not match Git identity")

    code = _typescript_code_only(payload.decode("utf-8"))
    identifier = re.compile(r"\bmigrateLegacy\b")
    lines = [
        [expected_path, number]
        for number, line in enumerate(code.splitlines(), start=1)
        if identifier.search(line)
    ]
    if not lines:
        raise GroundTruthError("TERMINAL_SYMBOL_MISSING", "migrateLegacy not found")
    return {
        "case": "terminal_migrate_legacy",
        "tool": "find_references",
        "arguments": {"name": "migrateLegacy", "limit": 50},
        "expected": lines,
        "source": {
            "repository": repository_slug,
            "commit": commit,
            "tree": tree,
            "path": expected_path,
            "blob": expected_blob,
        },
        "payload": payload,
    }


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
    digest = hashlib.sha256()
    for relative, payload in _iter_corpus_bytes(corpus):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
