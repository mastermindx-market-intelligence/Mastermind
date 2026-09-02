"""A small but real stand-in language server for adapter falsification.

It implements its own AST logic rather than importing the experiment's ground
truth, so the adapter is never graded against the same code that produced the
answer key. It exists to prove ADAPTER behaviour — root binding, refusals,
position mapping, degradation — and NOT to stand in for a real language server
in any benchmark claim.

Modes (argv[2]):
  ok            normal behaviour
  wrong_root    answers using a hard-coded foreign root (must be caught)
  no_impl       does not support textDocument/implementation
  slow          never answers documentSymbol
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

MODE = sys.argv[1] if len(sys.argv) > 1 else "ok"
ROOT: Path | None = None
REFUSED: list[str] = []


def _write(obj: object) -> None:
    body = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    sys.stdout.buffer.flush()


def _read() -> dict | None:
    headers = b""
    while not headers.endswith(b"\r\n\r\n"):
        char = sys.stdin.buffer.read(1)
        if not char:
            return None
        headers += char
    length = 0
    for line in headers.decode("ascii", "replace").split("\r\n"):
        if line.lower().startswith("content-length"):
            length = int(line.split(":", 1)[1].strip())
    body = sys.stdin.buffer.read(length)
    return json.loads(body) if body else None


def _to_path(uri: str) -> Path:
    return Path(unquote(urlparse(uri).path))


def _to_uri(path: Path) -> str:
    return "file://" + str(path)


def _py_files() -> list[Path]:
    assert ROOT is not None
    return sorted(p for p in ROOT.rglob("*.py") if p.is_file() and ".git" not in p.parts)


def _defs(path: Path) -> list[tuple[str, int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    out = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out.append((node.name, node.lineno, "class"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.name, node.lineno, "function"))
    return out


def _occurrences(path: Path, symbol: str) -> list[int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == symbol:
            lines.add(node.lineno)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            lines.add(node.lineno)
        elif isinstance(node, ast.alias) and symbol in (node.name, node.asname):
            lines.add(node.lineno)
    return sorted(lines)


def _methods(path: Path, class_name: str) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return set()



def _symbol_at(path: Path, zero_based_line: int) -> str:
    """Map an LSP position back to the definition name on that line."""
    for name, line, _kind in _defs(path):
        if line - 1 == zero_based_line:
            return name
    return ""

def _location(path: Path, line: int) -> dict:
    base = Path("/somewhere/else") if MODE == "wrong_root" else path
    return {
        "uri": _to_uri(base),
        "range": {
            "start": {"line": line - 1, "character": 0},
            "end": {"line": line - 1, "character": 1},
        },
    }


def main() -> None:
    global ROOT
    while True:
        message = _read()
        if message is None:
            return
        method = message.get("method")
        params = message.get("params") or {}
        request_id = message.get("id")

        if method in ("workspace/didChangeWorkspaceFolders", "workspace/executeCommand"):
            REFUSED.append(method)
            if request_id is not None:
                _write({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "refused"}})
            continue

        if method == "initialize":
            ROOT = _to_path(params["rootUri"])
            _write({
                "jsonrpc": "2.0", "id": request_id,
                "result": {"capabilities": {
                    "documentSymbolProvider": True,
                    "workspaceSymbolProvider": True,
                    "referencesProvider": True,
                    "implementationProvider": MODE != "no_impl",
                }, "serverInfo": {"name": "fake-lsp", "version": "0.0.1"}},
            })
            continue

        if method == "__refused_census__":
            _write({"jsonrpc": "2.0", "id": request_id, "result": {"refused": REFUSED}})
            continue

        if request_id is None:
            continue

        if method == "textDocument/documentSymbol":
            if MODE == "slow":
                continue
            path = _to_path(params["textDocument"]["uri"])
            _write({"jsonrpc": "2.0", "id": request_id, "result": [
                {"name": name, "kind": 5 if kind == "class" else 12,
                 "location": _location(path, line)}
                for name, line, kind in _defs(path)
            ]})
            continue

        if method == "workspace/symbol":
            query = params.get("query") or ""
            rows = []
            for path in _py_files():
                for name, line, kind in _defs(path):
                    if query in name:
                        rows.append({"name": name, "kind": 5 if kind == "class" else 12,
                                     "location": _location(path, line)})
            _write({"jsonrpc": "2.0", "id": request_id, "result": rows})
            continue

        if method == "textDocument/references":
            anchor = _to_path(params["textDocument"]["uri"])
            symbol = _symbol_at(anchor, params["position"]["line"])
            rows = []
            for path in _py_files():
                for line in _occurrences(path, symbol):
                    rows.append(_location(path, line))
            _write({"jsonrpc": "2.0", "id": request_id, "result": rows})
            continue

        if method == "textDocument/implementation":
            if MODE == "no_impl":
                _write({"jsonrpc": "2.0", "id": request_id,
                        "error": {"code": -32601, "message": "unsupported"}})
                continue
            anchor = _to_path(params["textDocument"]["uri"])
            symbol = _symbol_at(anchor, params["position"]["line"])
            wanted = set()
            for path in _py_files():
                wanted |= _methods(path, symbol)
            rows = []
            if wanted:
                for path in _py_files():
                    for name, line, kind in _defs(path):
                        if kind == "class" and name != symbol and _methods(path, name) >= wanted:
                            rows.append(_location(path, line))
            _write({"jsonrpc": "2.0", "id": request_id, "result": rows})
            continue

        if method == "textDocument/diagnostic":
            path = _to_path(params["textDocument"]["uri"])
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                _write({"jsonrpc": "2.0", "id": request_id, "result": {"items": []}})
                continue
            bound = set(dir(__builtins__)) | {"__file__", "__name__"}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    bound.add(node.name)
                    bound |= {a.arg for a in node.args.args}
                elif isinstance(node, ast.ClassDef):
                    bound.add(node.name)
                elif isinstance(node, ast.alias):
                    bound.add((node.asname or node.name).split(".")[0])
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        for sub in ast.walk(target):
                            if isinstance(sub, ast.Name):
                                bound.add(sub.id)
            items = [
                {"range": {"start": {"line": n.lineno - 1, "character": 0},
                           "end": {"line": n.lineno - 1, "character": 1}},
                 "severity": 1, "message": f"undefined name '{n.id}'", "code": "undefined-name"}
                for n in ast.walk(tree)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound
            ]
            _write({"jsonrpc": "2.0", "id": request_id, "result": {"items": items}})
            continue

        if method == "shutdown":
            _write({"jsonrpc": "2.0", "id": request_id, "result": None})
            continue

        _write({"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": f"unknown method {method}"}})


if __name__ == "__main__":
    main()
