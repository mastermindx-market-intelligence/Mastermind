"""AST fences for the Research Read MCP package. They scan every module that lands."""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parents[2] / "integrations" / "research_read_mcp"
WRITE_NAMES = frozenset({
    "put_object",
    "delete_object",
    "delete",
    "upload",
    "upload_file",
    "upload_fileobj",
    "write_text",
    "write_bytes",
    "unlink",
    "rename",
    "rmtree",
})
WRITE_FLAGS = frozenset({"O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND"})
WRITE_IMPORTS = (
    "engine.research_vault.ingest",
    "engine.research_vault.corpus",
)


def _parse(source: str) -> ast.AST:
    return ast.parse(source)


def _modules(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            found.append(node.module or "")
    return found


def _called(node: ast.AST) -> tuple[str | None, str | None]:
    if isinstance(node, ast.Name):
        return node.id, None
    if isinstance(node, ast.Attribute):
        base = node.value.id if isinstance(node.value, ast.Name) else None
        return node.attr, base
    return None, None


def _open_mode(node: ast.Call) -> str | None:
    mode: str | None = None
    if len(node.args) >= 2:
        value = node.args[1]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            mode = value.value
        else:
            return "<dynamic>"
    for keyword in node.keywords:
        if keyword.arg != "mode":
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            mode = keyword.value.value
        else:
            return "<dynamic>"
    return mode


def _flag_names(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in WRITE_FLAGS:
            found.add(child.id)
        elif isinstance(child, ast.Attribute) and child.attr in WRITE_FLAGS:
            found.add(child.attr)
    return found


def write_fence_violations(source: str) -> list[str]:
    tree = _parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in WRITE_NAMES:
            violations.append(f"attribute {node.attr}")
        if not isinstance(node, ast.Call):
            continue
        name, base = _called(node.func)
        if name in WRITE_NAMES:
            violations.append(f"call {name}")
        if name == "open" and base in {None, "io", "pathlib"}:
            mode = _open_mode(node)
            if mode is None:
                continue
            if mode == "<dynamic>" or any(character in mode for character in "wax+"):
                violations.append(f"open mode {mode}")
        if name == "open" and base == "os" and _flag_names(node):
            violations.append("os.open write flag " + ",".join(sorted(_flag_names(node))))
    for module in _modules(tree):
        for banned in WRITE_IMPORTS:
            if module == banned or module.startswith(banned + "."):
                violations.append(f"import {module}")
        if "r2_store" in module.split("."):
            violations.append(f"import {module}")
    return violations


def import_fence_violations(source: str, filename: str) -> list[str]:
    violations: list[str] = []
    for module in _modules(_parse(source)):
        top = module.split(".", 1)[0]
        if top in {"mcp", "starlette"} and filename != "app.py":
            violations.append(f"{filename} imports {top}")
        if top == "engine" and filename != "port_adapter.py":
            violations.append(f"{filename} imports engine")
        if top == "app":
            violations.append(f"{filename} imports app")
    return violations


def auth_copy_violations(source: str) -> list[str]:
    violations: list[str] = []
    tree = _parse(source)
    for module in _modules(tree):
        top = module.split(".", 1)[0]
        if top in {"jwt", "cryptography"}:
            violations.append(f"import {top}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("Bearer"):
            violations.append("string literal Bearer")
    return violations


def _package_sources() -> list[tuple[str, str]]:
    return [
        (path.name, path.read_text(encoding="utf-8"))
        for path in sorted(PACKAGE.glob("*.py"))
    ]


def test_f2_compatibility_helper_imports_without_sdk_or_transport():
    """The helper's transitive imports stay pure, beyond the direct AST fence."""
    program = """
import importlib.abc
import sys
sys.path.insert(0, sys.argv[1])
class RefuseEdge(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.', 1)[0] in {'mcp', 'starlette'}:
            raise AssertionError('SDK_EDGE_IMPORTED_BY_PURE_HELPER')
sys.meta_path.insert(0, RefuseEdge())
from integrations.research_read_mcp.compatibility_v1 import CompatibilityPortV1, INPUT_SCHEMAS
assert set(INPUT_SCHEMAS) == {'search', 'fetch'}
assert CompatibilityPortV1.__module__ == 'integrations.research_read_mcp.compatibility_v1'
"""
    result = subprocess.run([sys.executable, "-I", "-c", program, str(PACKAGE.parents[1])],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_f1_package_has_no_write_surface():
    sources = _package_sources()
    assert any(name == "app.py" for name, _source in sources)
    violations = [
        f"{name}: {item}"
        for name, source in sources
        for item in write_fence_violations(source)
    ]
    assert violations == []


def test_f2_sdk_and_macro_imports_stay_on_their_edges():
    sources = _package_sources()
    violations = [
        item
        for name, source in sources
        for item in import_fence_violations(source, name)
    ]
    assert violations == []


def test_f3_app_does_not_copy_auth():
    source = (PACKAGE / "app.py").read_text(encoding="utf-8")
    assert auth_copy_violations(source) == []


def test_f4_each_fence_reports_a_synthetic_violation():
    assert write_fence_violations("pass\n") == []
    assert import_fence_violations("pass\n", "app.py") == []
    assert auth_copy_violations("pass\n") == []

    write_bad = (
        "import engine.research_vault.ingest\n"
        "import r2_store\n"
        "def bad(blob, os):\n"
        "    blob.put_object()\n"
        "    open('x', 'w')\n"
        "    os.open('x', os.O_WRONLY | os.O_CREAT)\n"
    )
    write_found = write_fence_violations(write_bad)
    assert any("put_object" in item for item in write_found)
    assert any("open mode" in item for item in write_found)
    assert any("O_WRONLY" in item for item in write_found)
    assert any("ingest" in item for item in write_found)
    assert any("r2_store" in item for item in write_found)

    import_bad = "import mcp\nimport starlette\nimport engine\nimport app\n"
    import_found = import_fence_violations(import_bad, "entitlement.py")
    assert any("mcp" in item for item in import_found)
    assert any("starlette" in item for item in import_found)
    assert any("engine" in item for item in import_found)
    assert any("imports app" in item for item in import_found)
    assert import_fence_violations("import engine.research_vault\n", "port_adapter.py") == []

    auth_found = auth_copy_violations('import jwt\nimport cryptography\ntoken = "Bearer leaked"\n')
    assert any("jwt" in item for item in auth_found)
    assert any("cryptography" in item for item in auth_found)
    assert any("Bearer" in item for item in auth_found)
